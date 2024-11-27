import boto3
import paramiko
import time
import os
from botocore.exceptions import ClientError

class CloudInfrastructure:
    def __init__(self, region="us-east-1"):
        self.ec2 = boto3.client('ec2', region_name=region)
        self.region = region
        self.vpc_id = None
        self.subnet_id = None
        self.security_groups = {}
        self.instances = {}
        self.key_name = 'mysql-cluster-key-2'
        self.key_path = 'mysql-cluster-key-2.pem'

    def create_key_pair(self):
        """Create key pair for SSH access with correct permissions"""
        try:
            # Supprimer la clé existante si elle existe
            try:
                os.remove(self.key_path)
            except OSError:
                pass

            # Créer la nouvelle paire de clés
            key_pair = self.ec2.create_key_pair(KeyName=self.key_name)
        
            # Sauvegarder dans un répertoire temporaire Linux
            temp_key_path = os.path.expanduser('~/temp_key.pem')
            with open(temp_key_path, 'w') as key_file:
                key_file.write(key_pair['KeyMaterial'])
        
            # Définir les permissions correctes
            os.chmod(temp_key_path, 0o400)
        
            # Copier vers l'emplacement final avec les bonnes permissions
            import shutil
            shutil.copy2(temp_key_path, self.key_path)
            os.remove(temp_key_path)
        
            print(f"Created key pair and saved to {self.key_path} with correct permissions")
            return True
        except Exception as e:
            print(f"Error creating key pair: {e}")
            return False
        
    def create_vpc(self):
        """Create VPC with CIDR 10.0.0.0/16"""
        vpc = self.ec2.create_vpc(CidrBlock='10.0.0.0/16')
        self.vpc_id = vpc['Vpc']['VpcId']
        
        # Enable DNS hostname for the VPC
        self.ec2.modify_vpc_attribute(
            VpcId=self.vpc_id,
            EnableDnsHostnames={'Value': True}
        )
        
        # Create and attach internet gateway
        igw = self.ec2.create_internet_gateway()
        self.ec2.attach_internet_gateway(
            InternetGatewayId=igw['InternetGateway']['InternetGatewayId'],
            VpcId=self.vpc_id
        )
        
        print(f"Created VPC: {self.vpc_id}")
        return self.vpc_id

    def create_subnet(self):
        """Create subnet with CIDR 10.0.1.0/24"""
        subnet = self.ec2.create_subnet(
            VpcId=self.vpc_id,
            CidrBlock='10.0.1.0/24',
            AvailabilityZone=f'{self.region}a'
        )
        self.subnet_id = subnet['Subnet']['SubnetId']
        
        # Enable auto-assign public IP
        self.ec2.modify_subnet_attribute(
            SubnetId=self.subnet_id,
            MapPublicIpOnLaunch={'Value': True}
        )
        
        # Create and configure route table
        route_table = self.ec2.create_route_table(VpcId=self.vpc_id)
        self.ec2.create_route(
            RouteTableId=route_table['RouteTable']['RouteTableId'],
            DestinationCidrBlock='0.0.0.0/0',
            GatewayId=self.ec2.describe_internet_gateways(
                Filters=[{'Name': 'attachment.vpc-id', 'Values': [self.vpc_id]}]
            )['InternetGateways'][0]['InternetGatewayId']
        )
        self.ec2.associate_route_table(
            RouteTableId=route_table['RouteTable']['RouteTableId'],
            SubnetId=self.subnet_id
        )
        
        print(f"Created Subnet: {self.subnet_id}")
        return self.subnet_id

    def setup_infrastructure(self):
        """Setup complete infrastructure"""
        try:
            print("Starting infrastructure setup...")
            self.create_key_pair()
            self.create_vpc()
            time.sleep(30)  # Wait for VPC to be created
            self.create_subnet()
            time.sleep(30)  # Wait for subnet to be created
            self.create_security_groups()
            time.sleep(30)  # Wait for security groups to be created
            self.instances, self.instance_ips = self.create_instances()
        
            print("\nWaiting for services to initialize...")
            time.sleep(300)  # Wait for services to start
        
            print("\nVerifying services...")
            self.verify_services()
            return True
        except Exception as e:
            print(f"Error setting up infrastructure: {e}")
            return False

    def create_security_groups(self):
        """Create security groups for different components"""
        # MySQL Cluster Security Group
        mysql_sg = self.ec2.create_security_group(
            GroupName='MySQL-Cluster-SG',
            Description='Security group for MySQL Cluster',
            VpcId=self.vpc_id
        )
        self.security_groups['mysql'] = mysql_sg['GroupId']
        
        # Allow MySQL port and SSH
        self.ec2.authorize_security_group_ingress(
            GroupId=mysql_sg['GroupId'],
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 3306,
                    'ToPort': 3306,
                    'IpRanges': [{'CidrIp': '10.0.0.0/16'}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                }
            ]
        )

        # Proxy Security Group
        proxy_sg = self.ec2.create_security_group(
            GroupName='Proxy-SG',
            Description='Security group for Proxy',
            VpcId=self.vpc_id
        )
        self.security_groups['proxy'] = proxy_sg['GroupId']
        
        # Allow port 5000 for proxy API and SSH
        self.ec2.authorize_security_group_ingress(
            GroupId=proxy_sg['GroupId'],
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 5000,
                    'ToPort': 5000,
                    'IpRanges': [{'CidrIp': '10.0.0.0/16'}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                }
            ]
        )
        
        # Gatekeeper Security Group
        gk_sg = self.ec2.create_security_group(
            GroupName='Gatekeeper-SG',
            Description='Security group for Gatekeeper',
            VpcId=self.vpc_id
        )
        self.security_groups['gatekeeper'] = gk_sg['GroupId']
        
        # Allow HTTP/HTTPS, port 5000 for API, and SSH
        self.ec2.authorize_security_group_ingress(
            GroupId=gk_sg['GroupId'],
            IpPermissions=[
                {
                'IpProtocol': 'tcp',
                'FromPort': 5000,
                'ToPort': 5000,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]  
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 80,
                    'ToPort': 80,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 443,
                    'ToPort': 443,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                },
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                }
            ]
        )

        print("Created Security Groups")
        return self.security_groups

    def get_mysql_user_data(self, is_manager=False):
        """Generate user data script for MySQL setup"""
        base_script = '''#!/bin/bash
# Update system and install required packages
apt-get update
apt-get install -y mysql-server mysql-client wget

# Start MySQL
systemctl start mysql
systemctl enable mysql

# Secure MySQL installation and set root password
mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'root_password';"
mysql -e "FLUSH PRIVILEGES;"

# Configure MySQL to accept connections from any IP
sed -i 's/bind-address.*=.*/bind-address = 0.0.0.0/' /etc/mysql/mysql.conf.d/mysqld.cnf
'''

        manager_script = '''
# Create user for replication
mysql -e "CREATE USER 'repl'@'%' IDENTIFIED BY 'repl_password';"
mysql -e "GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';"
mysql -e "FLUSH PRIVILEGES;"
'''

        end_script = '''
# Download and install Sakila database
wget https://downloads.mysql.com/docs/sakila-db.tar.gz
tar -xvf sakila-db.tar.gz
mysql -e "SOURCE sakila-db/sakila-schema.sql"
mysql -e "SOURCE sakila-db/sakila-data.sql"
mysql -e "USE sakila"

# Restart MySQL to apply changes
systemctl restart mysql
'''

        if is_manager:
            return base_script + manager_script + end_script
        else:
            return base_script + end_script

    def get_proxy_user_data(self):
        """Generate user data script for Proxy setup"""
        return '''#!/bin/bash
# Update system
apt-get update
apt-get install -y python3 python3-pip nginx

# Install required Python packages
pip3 install flask mysql-connector-python requests ping3

# Create proxy application
cat > /home/ubuntu/proxy.py << 'EOL'
from flask import Flask, request
import mysql.connector
import random
from ping3 import ping
import json

app = Flask(__name__)

# Configuration
MANAGER_HOST = "MANAGER_IP"
WORKER1_HOST = "WORKER1_IP"
WORKER2_HOST = "WORKER2_IP"
DB_USER = "root"
DB_PASS = "root_password"

def get_connection(host):
    return mysql.connector.connect(
        host=host,
        user=DB_USER,
        password=DB_PASS,
        database="sakila"
    )

# Direct hit implementation
@app.route('/direct/<query_type>', methods=['POST'])
def direct_hit(query_type):
    return forward_to_manager(request.json['query'])

# Random worker implementation
@app.route('/random/<query_type>', methods=['POST'])
def random_worker(query_type):
    if query_type.upper() == 'WRITE':
        return forward_to_manager(request.json['query'])
    else:
        workers = [WORKER1_HOST, WORKER2_HOST]
        chosen_worker = random.choice(workers)
        return forward_to_worker(chosen_worker, request.json['query'])

# Latency-based implementation
@app.route('/smart/<query_type>', methods=['POST'])
def smart_routing(query_type):
    if query_type.upper() == 'WRITE':
        return forward_to_manager(request.json['query'])
    else:
        # Measure ping times
        workers = [WORKER1_HOST, WORKER2_HOST]
        ping_times = [(host, ping(host)) for host in workers]
        fastest_worker = min(ping_times, key=lambda x: x[1])[0]
        return forward_to_worker(fastest_worker, request.json['query'])

def forward_to_manager(query):
    try:
        conn = get_connection(MANAGER_HOST)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)
        
        if query.strip().upper().startswith('SELECT'):
            result = cursor.fetchall()
        else:
            conn.commit()
            result = {"affected_rows": cursor.rowcount}
            
            # Replicate to workers
            replicate_to_workers(query)
            
        cursor.close()
        conn.close()
        return json.dumps({"status": "success", "result": result})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def forward_to_worker(worker_host, query):
    try:
        conn = get_connection(worker_host)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)
        result = cursor.fetchall()
        cursor.close()
        conn.close()
        return json.dumps({"status": "success", "result": result})
    except Exception as e:
        return json.dumps({"status": "error", "message": str(e)})

def replicate_to_workers(query):
    workers = [WORKER1_HOST, WORKER2_HOST]
    for worker in workers:
        try:
            conn = get_connection(worker)
            cursor = conn.cursor()
            cursor.execute(query)
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"Replication error for {worker}: {str(e)}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOL

# Create service file
cat > /etc/systemd/system/proxy.service << EOL
[Unit]
Description=MySQL Proxy Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=/usr/bin/python3 /home/ubuntu/proxy.py
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Start proxy service
systemctl enable proxy
systemctl start proxy
'''

    def get_gatekeeper_user_data(self):
        """Generate user data script for Gatekeeper setup"""
        return '''#!/bin/bash
# Update system
apt-get update
apt-get install -y python3 python3-pip nginx

# Install required Python packages
pip3 install flask requests

# Create gatekeeper application
cat > /home/ubuntu/gatekeeper.py << 'EOL'
from flask import Flask, request, jsonify
import re
import requests

app = Flask(__name__)

TRUSTED_HOST = "TRUSTED_HOST_IP"

def validate_sql_query(query):
    # Basic SQL injection prevention
    dangerous_patterns = [
        r'--',
        r';.*;',
        r'\/\*.*\*\/',
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
    try:
        data = request.json
        if not data or 'query' not in data:
            return jsonify({"error": "Invalid request format"}), 400

        query = data['query']
        
        # Validate query
        if not validate_sql_query(query):
            return jsonify({"error": "Invalid query detected"}), 400

        # Forward to trusted host
        response = requests.post(
            f'http://{TRUSTED_HOST}:5001/forward',
            json={'query': query}
        )
        
        return response.json()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOL

# Configure firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow 5000/tcp
ufw allow 22/tcp
ufw --force enable

# Create service file
cat > /etc/systemd/system/gatekeeper.service << EOL
[Unit]
Description=Gatekeeper Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=/usr/bin/python3 /home/ubuntu/gatekeeper.py
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Start gatekeeper service
systemctl enable gatekeeper
systemctl start gatekeeper
'''

    def get_trusted_host_user_data(self):
        """Generate user data script for Trusted Host setup"""
        return '''#!/bin/bash
# Update system
apt-get update
apt-get install -y python3 python3-pip

# Install required Python packages
pip3 install flask requests

# Create trusted host application
cat > /home/ubuntu/trusted_host.py << 'EOL'
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

PROXY_HOST = "PROXY_IP"

@app.route('/forward', methods=['POST'])
def forward_request():
    try:
        data = request.json
        query = data['query']
        
        # Determine query type
        query_type = 'read' if query.strip().upper().startswith('SELECT') else 'write'
        
        # Forward to proxy with appropriate routing strategy
        response = requests.post(
            f'http://{PROXY_HOST}:5000/smart/{query_type}',
            json={'query': query}
        )
        
        return response.json()
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
EOL

# Configure strict firewall
ufw default deny incoming
ufw default allow outgoing
ufw allow from GATEKEEPER_IP to any port 5001 proto tcp
ufw allow 22/tcp
ufw enable

# Create service file
cat > /etc/systemd/system/trusted-host.service << EOL
[Unit]
Description=Trusted Host Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
ExecStart=/usr/bin/python3 /home/ubuntu/trusted_host.py
Restart=always

[Install]
WantedBy=multi-user.target
EOL

# Start trusted host service
systemctl enable trusted-host
systemctl start trusted-host
'''

    def create_instances(self):
        """Create EC2 instances for the cluster"""
        ami_id = 'ami-0261755bbcb8c4a84'  # Update this for your region
        instance_ips = {}
        waiter = self.ec2.get_waiter('instance_running')
    
        print("\nCreating MySQL instances...")
        # Create MySQL instances first
        for i in range(3):
            is_manager = (i == 0)
            instance = self.ec2.run_instances(
                ImageId=ami_id,
                InstanceType='t2.micro',
                KeyName=self.key_name,
                MaxCount=1,
                MinCount=1,
                SecurityGroupIds=[self.security_groups['mysql']],
                SubnetId=self.subnet_id,
                UserData=self.get_mysql_user_data(is_manager),
                TagSpecifications=[{
                    'ResourceType': 'instance',
                    'Tags': [{
                        'Key': 'Name',
                        'Value': f'MySQL-{"Manager" if is_manager else f"Worker-{i}"}'
                    }]
                }]
            )
            instance_id = instance['Instances'][0]['InstanceId']
            self.instances[f'mysql_{i}'] = instance_id

            # Wait for the instance to get its IP address
            print(f"Waiting for MySQL {'Manager' if is_manager else f'Worker {i}'} to start...")
            waiter.wait(InstanceIds=[instance_id])
            
            instance_info = self.ec2.describe_instances(InstanceIds=[instance_id])
            instance_ips[f'mysql_{i}'] = instance_info['Reservations'][0]['Instances'][0]['PrivateIpAddress']
            print(f"MySQL {'Manager' if is_manager else f'Worker {i}'} IP: {instance_ips[f'mysql_{i}']}")

        # Create Proxy with MySQL IPs
        print("\nCreating Proxy instance...")
        proxy_user_data = self.get_proxy_user_data().replace('MANAGER_IP', instance_ips['mysql_0'])\
                                                   .replace('WORKER1_IP', instance_ips['mysql_1'])\
                                                   .replace('WORKER2_IP', instance_ips['mysql_2'])
        
        proxy_instance = self.ec2.run_instances(
            ImageId=ami_id,
            InstanceType='t2.large',
            KeyName=self.key_name,
            MaxCount=1,
            MinCount=1,
            SecurityGroupIds=[self.security_groups['proxy']],
            SubnetId=self.subnet_id,
            UserData=proxy_user_data,
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [{
                    'Key': 'Name',
                    'Value': 'Proxy'
                }]
            }]
        )
        proxy_id = proxy_instance['Instances'][0]['InstanceId']
        self.instances['proxy'] = proxy_id
    
        # Wait for proxy IP
        print("Waiting for Proxy to start...")
        waiter.wait(InstanceIds=[proxy_id])
        proxy_info = self.ec2.describe_instances(InstanceIds=[proxy_id])
        proxy_ip = proxy_info['Reservations'][0]['Instances'][0]['PrivateIpAddress']
        print(f"Proxy IP: {proxy_ip}")

        # Create Trusted Host first
        print("\nCreating Trusted Host instance...")
        th_user_data = self.get_trusted_host_user_data().replace('PROXY_IP', proxy_ip)
        th_instance = self.ec2.run_instances(
            ImageId=ami_id,
            InstanceType='t2.large',
            KeyName=self.key_name,
            MaxCount=1,
            MinCount=1,
            SecurityGroupIds=[self.security_groups['gatekeeper']],
            SubnetId=self.subnet_id,
            UserData=th_user_data,
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [{
                    'Key': 'Name',
                    'Value': 'trusted-host'
                }]
            }]
        )
        th_id = th_instance['Instances'][0]['InstanceId']
        self.instances['trusted-host'] = th_id

        # Wait for trusted host IP
        print("Waiting for Trusted Host to start...")
        waiter.wait(InstanceIds=[th_id])
        th_info = self.ec2.describe_instances(InstanceIds=[th_id])
        th_private_ip = th_info['Reservations'][0]['Instances'][0]['PrivateIpAddress']
        print(f"Trusted Host IP: {th_private_ip}")

        # Finally create Gatekeeper with all necessary IPs
        print("\nCreating Gatekeeper instance...")
        gk_user_data = self.get_gatekeeper_user_data().replace('TRUSTED_HOST_IP', th_private_ip)
        gk_instance = self.ec2.run_instances(
            ImageId=ami_id,
            InstanceType='t2.large',
            KeyName=self.key_name,
            MaxCount=1,
            MinCount=1,
            SecurityGroupIds=[self.security_groups['gatekeeper']],
            SubnetId=self.subnet_id,
            UserData=gk_user_data,
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [{
                    'Key': 'Name',
                    'Value': 'gatekeeper'
                }]
            }]
        )
        gk_id = gk_instance['Instances'][0]['InstanceId']
        self.instances['gatekeeper'] = gk_id
    
        # Wait for gatekeeper and get its public IP for output
        print("Waiting for Gatekeeper to start...")
        waiter.wait(InstanceIds=[gk_id])
        gk_info = self.ec2.describe_instances(InstanceIds=[gk_id])
        gk_public_ip = gk_info['Reservations'][0]['Instances'][0]['PublicIpAddress']
        gk_private_ip = gk_info['Reservations'][0]['Instances'][0]['PrivateIpAddress']
        print(f"Gatekeeper Public IP: {gk_public_ip}")
    
        # Store IPs for reference
        self.instance_ips = {
            'mysql_manager': instance_ips['mysql_0'],
            'mysql_worker1': instance_ips['mysql_1'],
            'mysql_worker2': instance_ips['mysql_2'],
            'proxy': proxy_ip,
            'trusted_host': th_private_ip,
            'gatekeeper': gk_public_ip
        }

        print("\nCreated all EC2 Instances successfully")
        return self.instances, self.instance_ips

def main():
    infrastructure = CloudInfrastructure()
    if infrastructure.setup_infrastructure():
        print("Infrastructure setup completed successfully!")
        print("Your MySQL cluster is now ready to use.")
        
        # Get Gatekeeper's public IP
        gk_info = infrastructure.ec2.describe_instances(
            InstanceIds=[infrastructure.instances['gatekeeper']]
        )
        gk_public_ip = gk_info['Reservations'][0]['Instances'][0]['PublicIpAddress']
        
        print("\nTo connect to the cluster, use the Gatekeeper's public IP address:")
        print(f"Gatekeeper Public IP: {gk_public_ip}")
        print("\nExample query request:")
        print(f'''
        curl -X POST http://{gk_public_ip}:5000/query \\
             -H "Content-Type: application/json" \\
             -d '{{"query": "SELECT * FROM sakila.actor LIMIT 5;"}}'
        ''')
    else:
        print("Failed to setup infrastructure")

if __name__ == "__main__":
    main()
