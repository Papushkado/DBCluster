# config.py
import os
from dataclasses import dataclass

@dataclass
class AWSConfig:
    region = "us-west-2"
    ami_id = "ami-0735c191cf914754d"  # Ubuntu 20.04 LTS
    instance_types = {
        "mysql": "t2.micro",
        "proxy": "t2.large",
        "gatekeeper": "t2.large",
        "trusted_host": "t2.large"
    }
    key_name = "your-key-pair-name"
    
@dataclass
class MySQLConfig:
    user = "admin"
    password = "your-secure-password"
    database = "sakila"
    port = 3306

# infrastructure.py
import boto3
import time
from config import AWSConfig, MySQLConfig

class CloudInfrastructure:
    def __init__(self):
        self.ec2 = boto3.client('ec2', region_name=AWSConfig.region)
        self.instances = {}
        
    def create_security_group(self, name, description, rules):
        try:
            response = self.ec2.create_security_group(
                GroupName=name,
                Description=description
            )
            security_group_id = response['GroupId']
            
            for rule in rules:
                self.ec2.authorize_security_group_ingress(
                    GroupId=security_group_id,
                    IpPermissions=[rule]
                )
                
            return security_group_id
        except Exception as e:
            print(f"Error creating security group: {e}")
            return None
            
    def create_instance(self, name, instance_type, security_group_ids, user_data=None):
        try:
            response = self.ec2.run_instances(
                ImageId=AWSConfig.ami_id,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=1,
                KeyName=AWSConfig.key_name,
                SecurityGroupIds=security_group_ids,
                UserData=user_data,
                TagSpecifications=[{
                    'ResourceType': 'instance',
                    'Tags': [{'Key': 'Name', 'Value': name}]
                }]
            )
            
            instance_id = response['Instances'][0]['InstanceId']
            self.instances[name] = instance_id
            
            # Wait for instance to be running
            waiter = self.ec2.get_waiter('instance_running')
            waiter.wait(InstanceIds=[instance_id])
            
            return instance_id
        except Exception as e:
            print(f"Error creating instance {name}: {e}")
            return None

    def get_instance_ip(self, instance_id):
        try:
            response = self.ec2.describe_instances(InstanceIds=[instance_id])
            return response['Reservations'][0]['Instances'][0]['PublicIpAddress']
        except Exception as e:
            print(f"Error getting instance IP: {e}")
            return None

# mysql_setup.py
def get_mysql_setup_script(is_manager=False):
    return f"""#!/bin/bash
apt-get update
apt-get install -y mysql-server sysbench
systemctl start mysql
systemctl enable mysql

# Configure MySQL
mysql -e "CREATE USER '{MySQLConfig.user}'@'%' IDENTIFIED BY '{MySQLConfig.password}'"
mysql -e "GRANT ALL PRIVILEGES ON *.* TO '{MySQLConfig.user}'@'%'"
mysql -e "FLUSH PRIVILEGES"

# Download and install Sakila
wget https://downloads.mysql.com/docs/sakila-db.tar.gz
tar xvf sakila-db.tar.gz
mysql -e "SOURCE sakila-db/sakila-schema.sql"
mysql -e "SOURCE sakila-db/sakila-data.sql"

# Configure MySQL for replication if manager
{"" if not is_manager else '''
echo "
server-id=1
log_bin=/var/log/mysql/mysql-bin.log
binlog_format=ROW
" >> /etc/mysql/my.cnf
systemctl restart mysql
'''}
"""

# proxy_setup.py
def get_proxy_setup_script():
    return """#!/bin/bash
apt-get update
apt-get install -y python3-pip
pip3 install flask mysql-connector-python requests

cat > /home/ubuntu/proxy.py << 'EOL'
from flask import Flask, request, jsonify
import mysql.connector
import random
import subprocess
import json

app = Flask(__name__)

MYSQL_NODES = {
    "manager": "MANAGER_IP",
    "workers": ["WORKER1_IP", "WORKER2_IP"]
}

def get_connection(host):
    return mysql.connector.connect(
        host=host,
        user="admin",
        password="your-secure-password",
        database="sakila"
    )

def measure_ping(host):
    result = subprocess.run(['ping', '-c', '1', host], capture_output=True, text=True)
    if result.returncode == 0:
        return float(result.stdout.split('time=')[1].split()[0])
    return float('inf')

@app.route('/query', methods=['POST'])
def handle_query():
    query = request.json.get('query', '').upper()
    strategy = request.json.get('strategy', 'direct')
    
    if any(word in query for word in ['SELECT', 'SHOW', 'DESCRIBE']):
        if strategy == 'direct':
            host = MYSQL_NODES['manager']
        elif strategy == 'random':
            host = random.choice(MYSQL_NODES['workers'])
        else:  # customized - ping-based
            ping_times = {
                host: measure_ping(host) 
                for host in MYSQL_NODES['workers']
            }
            host = min(ping_times.items(), key=lambda x: x[1])[0]
    else:
        # Write operations always go to manager
        host = MYSQL_NODES['manager']
    
    try:
        conn = get_connection(host)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)
        
        if query.startswith(('INSERT', 'UPDATE', 'DELETE')):
            conn.commit()
            # Replicate to workers
            for worker in MYSQL_NODES['workers']:
                worker_conn = get_connection(worker)
                worker_cursor = worker_conn.cursor()
                worker_cursor.execute(query)
                worker_conn.commit()
                worker_cursor.close()
                worker_conn.close()
        
        results = cursor.fetchall() if not query.startswith(('INSERT', 'UPDATE', 'DELETE')) else None
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'results': results,
            'host': host
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'host': host
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOL

python3 /home/ubuntu/proxy.py &
"""

# gatekeeper_setup.py
def get_gatekeeper_setup_script():
    return """#!/bin/bash
apt-get update
apt-get install -y python3-pip
pip3 install flask requests

cat > /home/ubuntu/gatekeeper.py << 'EOL'
from flask import Flask, request, jsonify
import requests
import re

app = Flask(__name__)

TRUSTED_HOST = "TRUSTED_HOST_IP:5000"

def validate_query(query):
    # Basic SQL injection prevention
    dangerous_patterns = [
        r'--',
        r';.*$',
        r'/\*.*\*/',
        r'UNION.*SELECT',
        r'DROP.*TABLE',
        r'DELETE.*FROM',
        r'INSERT.*INTO',
        r'UPDATE.*SET'
    ]
    
    query = query.upper()
    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return False
    return True

@app.route('/query', methods=['POST'])
def handle_query():
    query = request.json.get('query', '')
    strategy = request.json.get('strategy', 'direct')
    
    if not validate_query(query):
        return jsonify({
            'success': False,
            'error': 'Invalid query detected'
        }), 400
        
    try:
        response = requests.post(
            f'http://{TRUSTED_HOST}/query',
            json={'query': query, 'strategy': strategy}
        )
        return response.json()
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOL

# Configure firewall
ufw default deny incoming
ufw allow 5000/tcp
ufw allow 22/tcp
ufw enable

python3 /home/ubuntu/gatekeeper.py &
"""

# trusted_host_setup.py
def get_trusted_host_setup_script():
    return """#!/bin/bash
apt-get update
apt-get install -y python3-pip
pip3 install flask requests

cat > /home/ubuntu/trusted_host.py << 'EOL'
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

PROXY_HOST = "PROXY_IP:5000"

@app.route('/query', methods=['POST'])
def handle_query():
    try:
        response = requests.post(
            f'http://{PROXY_HOST}/query',
            json=request.json
        )
        return response.json()
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOL

# Configure firewall
ufw default deny incoming
ufw allow from GATEKEEPER_IP to any port 5000
ufw allow 22/tcp
ufw enable

python3 /home/ubuntu/trusted_host.py &
"""

# main.py
def main():
    infra = CloudInfrastructure()
    
    # Create security groups
    mysql_sg = infra.create_security_group("mysql-sg", "MySQL security group", [
        {
            'IpProtocol': 'tcp',
            'FromPort': 3306,
            'ToPort': 3306,
            'IpRanges': [{'CidrIp': '10.0.0.0/16'}]
        }
    ])
    
    proxy_sg = infra.create_security_group("proxy-sg", "Proxy security group", [
        {
            'IpProtocol': 'tcp',
            'FromPort': 5000,
            'ToPort': 5000,
            'IpRanges': [{'CidrIp': '10.0.0.0/16'}]
        }
    ])
    
    gatekeeper_sg = infra.create_security_group("gatekeeper-sg", "Gatekeeper security group", [
        {
            'IpProtocol': 'tcp',
            'FromPort': 5000,
            'ToPort': 5000,
            'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
        }
    ])
    
    trusted_host_sg = infra.create_security_group("trusted-host-sg", "Trusted host security group", [
        {
            'IpProtocol': 'tcp',
            'FromPort': 5000,
            'ToPort': 5000,
            'IpRanges': [{'CidrIp': '10.0.0.0/16'}]
        }
    ])
    
    # Create MySQL instances
    mysql_manager = infra.create_instance(
        "mysql-manager",
        AWSConfig.instance_types['mysql'],
        [mysql_sg],
        get_mysql_setup_script(is_manager=True)
    )
    
    mysql_worker1 = infra.create_instance(
        "mysql-worker1",
        AWSConfig.instance_types['mysql'],
        [mysql_sg],
        get_mysql_setup_script()
    )
    
    mysql_worker2 = infra.create_instance(
        "mysql-worker2",
        AWSConfig.instance_types['mysql'],
        [mysql_sg],
        get_mysql_setup_script()
    )
    
    # Get MySQL IPs
    manager_ip = infra.get_instance_ip(mysql_manager)
    worker1_ip = infra.get_instance_ip(mysql_worker1)
    worker2_ip = infra.get_instance_ip(mysql_worker2)
    
    # Create Proxy instance
    proxy_script = get_proxy_setup_script().replace('MANAGER_IP', manager_ip)\
                                         .replace('WORKER1_IP', worker1_ip)\
                                         .replace('WORKER2_IP', worker2_ip)
    
    proxy = infra.create_instance(
        "proxy",
        AWSConfig.instance_types['proxy'],
        [proxy_sg],
        proxy_script
    )
    
    proxy_ip = infra.get_instance_ip(proxy)
    
    # Create Trusted Host instance
    trusted_host_script = get_trusted_host_setup_script().replace('PROXY_IP', proxy_ip)
    
    trusted_host = infra.create_instance(
        "trusted-host",
        AWSConfig.instance_types['trusted_host'],
        [trusted_host_sg],
        trusted_host_script
    )
    
    trusted_host_ip = infra.get_instance_ip(trusted_host)
    
    # Create Gatekeeper instance
    gatekeeper_script = get_gatekeeper_setup_script().replace('TRUSTED_HOST_IP', trusted_host_ip)
    
    gatekeeper = infra.create_instance(
        "gatekeeper",
        AWSConfig.instance_types['gatekeeper'],
        [gatekeeper_sg],
        gatekeeper_script
    )
    
    print("Infrastructure setup complete!")
    print(f"Gatekeeper IP: {infra.get_instance_ip(gatekeeper)}")

if __name__ == "__main__":
    main()