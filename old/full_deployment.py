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
        self.key_name = 'mysql-cluster-key-3'
        self.key_path = 'mysql-cluster-key-3.pem'

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

    def verify_services(self):
        """Verify all services are running correctly"""
        def check_service(host, port):
            """Check if a service is responding"""
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((host, port))
                sock.close()
                return result == 0
            except:
                return False

        print("\nVerifying services...")
    
        # Check MySQL instances
        for i, ip in enumerate([self.instance_ips['mysql_manager'], 
                          self.instance_ips['mysql_worker1'],
                          self.instance_ips['mysql_worker2']]):
            if check_service(ip, 3306):
                print(f" {'Manager' if i == 0 else f'Worker {i}'} is running")
            else:
                print(f" {'Manager' if i == 0 else f'Worker {i}'} is not responding")

        # Check Proxy
        if check_service(self.instance_ips['proxy'], 5000):
            print("Proxy service is running")
        else:
            print("Proxy service is not responding")

        # Check Trusted Host
        if check_service(self.instance_ips['trusted_host'], 5001):
            print("Trusted Host service is running")
        else:
            print("Trusted Host service is not responding")

        # Check Gatekeeper
        if check_service(self.instance_ips['gatekeeper'], 5000):
            print("Gatekeeper service is running")
        else:
            print("Gatekeeper service is not responding")

        # Test complete infrastructure
        try:
            response = requests.get(f"http://{self.instance_ips['gatekeeper']}:5000/health")
            if response.status_code == 200:
                print("Infrastructure health check passed")
            else:
                print("Infrastructure health check failed")
        except Exception as e:
            print(f"Infrastructure health check failed: {str(e)}")
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
            time.sleep(500)  # Wait for services to start
        
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
        
        # Autoriser le trafic entre les instances dans le même VPC
        self.ec2.authorize_security_group_ingress(
            GroupId=self.security_groups['mysql'],
            IpPermissions=[{
                'IpProtocol': '-1',  # Tous les protocoles
                'FromPort': -1,
                'ToPort': -1,
                'UserIdGroupPairs': [{
                'GroupId': self.security_groups['proxy']
                }]
            }]
        )
    
        # Autoriser le trafic du Trusted Host vers le Proxy
        self.ec2.authorize_security_group_ingress(
            GroupId=self.security_groups['proxy'],
            IpPermissions=[{
                'IpProtocol': 'tcp',
                'FromPort': 5000,
                'ToPort': 5000,
                'UserIdGroupPairs': [{
                    'GroupId': self.security_groups['gatekeeper']
                }]
            }]
        )

        print("Created Security Groups")
        return self.security_groups

    # Configuration MySQL avec Sysbench
    def get_mysql_user_data(self, is_manager=False):
        """Generate user data script for MySQL setup with Sysbench"""
        base_script = '''#!/bin/bash
# Update system and install required packages
apt-get update
apt-get install -y mysql-server mysql-client wget sysbench

# Start MySQL
systemctl start mysql
systemctl enable mysql

# Secure MySQL installation and set root password
mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'root_password';"
mysql -e "CREATE USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY 'root_password';"
mysql -e "GRANT ALL PRIVILEGES ON *.* TO 'root'@'%' WITH GRANT OPTION;"
mysql -e "FLUSH PRIVILEGES;"

# Configure MySQL to accept connections from any IP
sed -i 's/bind-address.*=.*/bind-address = 0.0.0.0/' /etc/mysql/mysql.conf.d/mysqld.cnf

# Performance optimizations
cat >> /etc/mysql/mysql.conf.d/mysqld.cnf << 'EOF'
innodb_buffer_pool_size = 1G
innodb_log_file_size = 256M
innodb_log_buffer_size = 64M
innodb_flush_log_at_trx_commit = 2
innodb_flush_method = O_DIRECT
EOF
'''

        manager_script = '''
# Create user for replication
mysql -e "CREATE USER 'repl'@'%' IDENTIFIED BY 'repl_password';"
mysql -e "GRANT REPLICATION SLAVE ON *.* TO 'repl'@'%';"
mysql -e "FLUSH PRIVILEGES;"

# Configure as source
cat >> /etc/mysql/mysql.conf.d/mysqld.cnf << 'EOF'
server-id = 1
log_bin = /var/log/mysql/mysql-bin.log
binlog_format = ROW
EOF
'''

        worker_script = '''
# Configure as replica
cat >> /etc/mysql/mysql.conf.d/mysqld.cnf << 'EOF'
server-id = {worker_id}
relay-log = /var/log/mysql/mysql-relay-bin
log_bin = /var/log/mysql/mysql-bin.log
read_only = 1
EOF
'''.format(worker_id=2 if not is_manager else 3)

        common_script = '''
# Download and install Sakila database
wget https://downloads.mysql.com/docs/sakila-db.tar.gz
tar -xvf sakila-db.tar.gz
mysql -e "SOURCE sakila-db/sakila-schema.sql"
mysql -e "SOURCE sakila-db/sakila-data.sql"
mysql -e "USE sakila"

# Configure and run Sysbench tests
cat > /root/run_sysbench.sh << 'EOF'
#!/bin/bash
# Prepare the test database
sysbench oltp_read_write \
    --db-driver=mysql \
    --mysql-user=root \
    --mysql-password=root_password \
    --mysql-db=sakila \
    --table-size=1000000 \
    --threads=4 \
    prepare

# Run the benchmark
sysbench oltp_read_write \
    --db-driver=mysql \
    --mysql-user=root \
    --mysql-password=root_password \
    --mysql-db=sakila \
    --table-size=1000000 \
    --threads=4 \
    --time=60 \
    --report-interval=10 \
    run > /var/log/sysbench_results.log

# Cleanup
sysbench oltp_read_write \
    --db-driver=mysql \
    --mysql-user=root \
    --mysql-password=root_password \
    --mysql-db=sakila \
    cleanup
EOF

chmod +x /root/run_sysbench.sh

# Restart MySQL to apply changes
systemctl restart mysql

# Run Sysbench tests in background
nohup /root/run_sysbench.sh &
'''

        if is_manager:
            return base_script + manager_script + common_script
        else:
            return base_script + worker_script + common_script
        
    def get_proxy_user_data(self):
        """Generate user data script for Proxy setup with three routing strategies"""
        return '''#!/bin/bash
# Update system
apt-get update
apt-get install -y python3 python3-pip nginx

# Install required Python packages
pip3 install flask mysql-connector-python requests ping3 prometheus_client

# Create monitoring script
cat > /home/ubuntu/monitor.py << 'EOL'
from prometheus_client import Counter, Histogram, start_http_server
import time

# Métriques Prometheus
REQUEST_COUNT = Counter('mysql_proxy_requests_total', 'Total requests', ['strategy', 'query_type'])
RESPONSE_TIME = Histogram('mysql_proxy_response_seconds', 'Response time in seconds', ['strategy'])
ERROR_COUNT = Counter('mysql_proxy_errors_total', 'Total errors', ['strategy', 'error_type'])

start_http_server(8000)
EOL

# Create proxy application
cat > /home/ubuntu/proxy.py << 'EOL'
from flask import Flask, request, jsonify
import mysql.connector
import random
from ping3 import ping
import time
import json
import logging
from datetime import datetime
from monitor import REQUEST_COUNT, RESPONSE_TIME, ERROR_COUNT

# Configure logging
logging.basicConfig(
    filename='/var/log/proxy.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

# Configuration
MANAGER_HOST = "MANAGER_IP"
WORKER1_HOST = "WORKER1_IP"
WORKER2_HOST = "WORKER2_IP"
DB_USER = "root"
DB_PASS = "root_password"

def get_connection(host):
    """Create a database connection with retry logic"""
    retries = 3
    for attempt in range(retries):
        try:
            return mysql.connector.connect(
                host=host,
                user=DB_USER,
                password=DB_PASS,
                database="sakila",
                connect_timeout=5
            )
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(1)

def is_read_query(query):
    """Determine if a query is read-only"""
    query = query.strip().upper()
    return (query.startswith('SELECT') or 
            query.startswith('SHOW') or 
            query.startswith('DESCRIBE'))

def execute_query_with_metrics(connection, query, strategy):
    """Execute a query and record metrics"""
    start_time = time.time()
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query)
        
        if is_read_query(query):
            result = cursor.fetchall()
            REQUEST_COUNT.labels(strategy=strategy, query_type='read').inc()
        else:
            connection.commit()
            result = {"affected_rows": cursor.rowcount}
            REQUEST_COUNT.labels(strategy=strategy, query_type='write').inc()
        
        duration = time.time() - start_time
        RESPONSE_TIME.labels(strategy=strategy).observe(duration)
        
        cursor.close()
        return result
    except Exception as e:
        ERROR_COUNT.labels(strategy=strategy, error_type=type(e).__name__).inc()
        raise

def forward_to_manager(query, strategy='direct'):
    """Forward query to manager node"""
    try:
        conn = get_connection(MANAGER_HOST)
        result = execute_query_with_metrics(conn, query, strategy)
        
        if not is_read_query(query):
            replicate_to_workers(query)
        
        conn.close()
        return jsonify({
            "status": "success",
            "result": result,
            "source": "manager",
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logging.error(f"Error forwarding to manager: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

def forward_to_worker(worker_host, query, strategy):
    """Forward query to specific worker node"""
    try:
        conn = get_connection(worker_host)
        result = execute_query_with_metrics(conn, query, strategy)
        conn.close()
        return jsonify({
            "status": "success",
            "result": result,
            "source": worker_host,
            "timestamp": datetime.now().isoformat()
        })
    except Exception as e:
        logging.error(f"Error forwarding to worker {worker_host}: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

def replicate_to_workers(query):
    """Replicate write operations to all workers"""
    workers = [WORKER1_HOST, WORKER2_HOST]
    for worker in workers:
        try:
            conn = get_connection(worker)
            execute_query_with_metrics(conn, query, 'replication')
            conn.close()
        except Exception as e:
            logging.error(f"Replication error for {worker}: {str(e)}")
            ERROR_COUNT.labels(strategy='replication', error_type=type(e).__name__).inc()

@app.route('/direct/<query_type>', methods=['POST'])
def direct_hit(query_type):
    """Direct hit strategy - always use manager"""
    try:
        query = request.json.get('query')
        if not query:
            return jsonify({"status": "error", "message": "No query provided"}), 400
        
        logging.info(f"Direct hit query: {query}")
        return forward_to_manager(query, 'direct')
    except Exception as e:
        logging.error(f"Error in direct hit: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/random/<query_type>', methods=['POST'])
def random_worker(query_type):
    """Random routing strategy"""
    try:
        query = request.json.get('query')
        if not query:
            return jsonify({"status": "error", "message": "No query provided"}), 400
        
        logging.info(f"Random strategy query: {query}")
        
        if not is_read_query(query):
            return forward_to_manager(query, 'random')
        
        workers = [WORKER1_HOST, WORKER2_HOST]
        chosen_worker = random.choice(workers)
        logging.info(f"Randomly chosen worker: {chosen_worker}")
        return forward_to_worker(chosen_worker, query, 'random')
    except Exception as e:
        logging.error(f"Error in random worker: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/smart/<query_type>', methods=['POST'])
def smart_routing(query_type):
    """Smart routing strategy based on ping times"""
    try:
        query = request.json.get('query')
        if not query:
            return jsonify({"status": "error", "message": "No query provided"}), 400
        
        logging.info(f"Smart routing query: {query}")
        
        if not is_read_query(query):
            return forward_to_manager(query, 'smart')
        
        workers = [WORKER1_HOST, WORKER2_HOST]
        ping_times = []
        
        for worker in workers:
            try:
                ping_time = ping(worker, timeout=1)
                if ping_time:
                    ping_times.append((worker, ping_time))
                    logging.info(f"Ping time for {worker}: {ping_time}s")
            except Exception as e:
                logging.warning(f"Could not ping {worker}: {str(e)}")
                continue
        
        if not ping_times:
            logging.warning("No workers responded to ping, using manager")
            return forward_to_manager(query, 'smart')
        
        fastest_worker = min(ping_times, key=lambda x: x[1])[0]
        logging.info(f"Chosen fastest worker: {fastest_worker}")
        return forward_to_worker(fastest_worker, query, 'smart')
    except Exception as e:
        logging.error(f"Error in smart routing: {str(e)}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "timestamp": datetime.now().isoformat()})

@app.route('/metrics', methods=['GET'])
def metrics():
    """Prometheus metrics endpoint"""
    return jsonify({
        "total_requests": REQUEST_COUNT._metrics,
        "response_times": RESPONSE_TIME._metrics,
        "total_errors": ERROR_COUNT._metrics
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOL

# Create service files and configure system
mkdir -p /var/log/proxy
touch /var/log/proxy.log
chown -R ubuntu:ubuntu /var/log/proxy

# Service file for proxy
cat > /etc/systemd/system/proxy.service << EOL
[Unit]
Description=MySQL Proxy Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 /home/ubuntu/proxy.py
Restart=always
StandardOutput=append:/var/log/proxy/proxy.log
StandardError=append:/var/log/proxy/proxy.log

[Install]
WantedBy=multi-user.target
EOL

# Configure nginx
cat > /etc/nginx/sites-available/proxy << EOL
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://localhost:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    location /metrics {
        proxy_pass http://localhost:8000;
    }
}
EOL

ln -s /etc/nginx/sites-available/proxy /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Start services
systemctl daemon-reload
systemctl enable proxy
systemctl start proxy
systemctl restart nginx

# Set up firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw allow 5000/tcp
ufw allow 8000/tcp
ufw allow from 10.0.0.0/16 to any port 3306
ufw --force enable
'''

    def get_benchmark_script(self):
        """Generate comprehensive benchmark script"""
        return '''#!/bin/bash
apt-get update
apt-get install -y python3-pip
pip3 install requests concurrent-futures statistics pandas matplotlib seaborn

cat > /home/ubuntu/benchmark.py << 'EOL'
import requests
import time
import concurrent.futures
import statistics
import json
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

class ClusterBenchmark:
    def __init__(self, gatekeeper_ip):
        self.gatekeeper_url = f"http://{gatekeeper_ip}:5000"
        self.results = {
            'direct': {'read': [], 'write': []},
            'random': {'read': [], 'write': []},
            'smart': {'read': [], 'write': []}
        }
        
    def send_request(self, query, route_type):
        """Send a single request and measure response time"""
        start_time = time.time()
        try:
            response = requests.post(
                f"{self.gatekeeper_url}/{route_type}/query",
                json={'query': query},
                timeout=10
            )
            duration = time.time() - start_time
            return {
                'duration': duration,
                'status': response.status_code,
                'response': response.json() if response.status_code == 200 else None
            }
        except Exception as e:
            print(f"Error sending request: {e}")
            return None

    def run_benchmark(self, num_requests=1000):
        """Run benchmarks for all routing strategies"""
        read_queries = [
            "SELECT * FROM sakila.actor LIMIT 1;",
            "SELECT * FROM sakila.film LIMIT 1;",
            "SELECT * FROM sakila.customer LIMIT 1;"
        ]
        write_queries = [
            "INSERT INTO sakila.actor (first_name, last_name) VALUES ('Test', 'Actor');",
            "UPDATE sakila.actor SET last_name = 'Updated' WHERE first_name = 'Test';",
            "DELETE FROM sakila.actor WHERE first_name = 'Test';"
        ]
        
        results_data = []
        
        for route_type in ['direct', 'random', 'smart']:
            print(f"\nRunning benchmark for {route_type} routing...")
            
            # Benchmark READ requests
            print(f"Executing {num_requests} READ requests...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for query in read_queries:
                    futures = [
                        executor.submit(self.send_request, query, route_type)
                        for _ in range(num_requests // len(read_queries))
                    ]
                    for f in futures:
                        result = f.result()
                        if result:
                            results_data.append({
                                'strategy': route_type,
                                'type': 'read',
                                'duration': result['duration'],
                                'status': result['status'],
                                'timestamp': datetime.now().isoformat()
                            })
            
            # Benchmark WRITE requests
            print(f"Executing {num_requests} WRITE requests...")
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                for query in write_queries:
                    futures = [
                        executor.submit(self.send_request, query, route_type)
                        for _ in range(num_requests // len(write_queries))
                    ]
                    for f in futures:
                        result = f.result()
                        if result:
                            results_data.append({
                                'strategy': route_type,
                                'type': 'write',
                                'duration': result['duration'],
                                'status': result['status'],
                                'timestamp': datetime.now().isoformat()
                            })
        
        # Convert results to DataFrame for analysis
        df = pd.DataFrame(results_data)
        
        # Generate statistics
        stats = df.groupby(['strategy', 'type']).agg({
            'duration': ['mean', 'min', 'max', 'std', 'count']
        }).round(4)
        
        # Save detailed results
        df.to_csv('benchmark_detailed_results.csv', index=False)
        stats.to_csv('benchmark_statistics.csv')
        
        # Generate plots
        self.generate_plots(df)
        
        print("\nBenchmark Statistics:")
        print(stats)
        
        return df, stats
    
    def generate_plots(self, df):
        """Generate visualization plots"""
        # Response time distribution
        plt.figure(figsize=(12, 6))
        sns.boxplot(x='strategy', y='duration', hue='type', data=df)
        plt.title('Response Time Distribution by Strategy and Query Type')
        plt.ylabel('Response Time (seconds)')
        plt.savefig('response_time_distribution.png')
        plt.close()
        
        # Response time over time
        plt.figure(figsize=(12, 6))
        for strategy in df['strategy'].unique():
            strategy_data = df[df['strategy'] == strategy]
            plt.plot(range(len(strategy_data)), 
                    strategy_data['duration'], 
                    label=strategy, 
                    alpha=0.6)
        plt.title('Response Time Evolution')
        plt.xlabel('Request Number')
        plt.ylabel('Response Time (seconds)')
        plt.legend()
        plt.savefig('response_time_evolution.png')
        plt.close()
        
        # Success rate
        success_rate = df.groupby('strategy')['status'].apply(
            lambda x: (x == 200).mean() * 100
        ).reset_index()
        plt.figure(figsize=(8, 6))
        sns.barplot(x='strategy', y='status', data=success_rate)
        plt.title('Success Rate by Strategy')
        plt.ylabel('Success Rate (%)')
        plt.savefig('success_rate.png')
        plt.close()

def main():
    gatekeeper_ip = "GATEKEEPER_IP"  # Will be replaced with actual IP
    benchmark = ClusterBenchmark(gatekeeper_ip)
    benchmark.run_benchmark()

if __name__ == '__main__':
    main()
EOL

chmod +x /home/ubuntu/benchmark.py
python3 /home/ubuntu/benchmark.py
'''

    def get_test_script(self):
        """Generate test script for validating the entire infrastructure"""
        return '''#!/bin/bash
# Install requirements
pip3 install requests pytest pytest-timeout colorama

cat > /home/ubuntu/test_infrastructure.py << 'EOL'
import pytest
import requests
import time
import json
from colorama import init, Fore, Style

init()

class TestInfrastructure:
    def __init__(self, gatekeeper_ip):
        self.gatekeeper_url = f"http://{gatekeeper_ip}:5000"
        self.test_data = {
            'read': "SELECT * FROM sakila.actor LIMIT 5;",
            'write': "INSERT INTO sakila.actor (first_name, last_name) VALUES ('Test', 'Actor');"
        }

    def test_direct_strategy(self):
        """Test direct routing strategy"""
        print(f"{Fore.BLUE}Testing direct routing strategy...{Style.RESET_ALL}")
        response = requests.post(
            f"{self.gatekeeper_url}/direct/query",
            json={'query': self.test_data['read']}
        )
        assert response.status_code == 200
        print(f"{Fore.GREEN}✓ Direct routing test passed{Style.RESET_ALL}")

    def test_random_strategy(self):
        """Test random routing strategy"""
        print(f"{Fore.BLUE}Testing random routing strategy...{Style.RESET_ALL}")
        responses = []
        for _ in range(10):
            response = requests.post(
                f"{self.gatekeeper_url}/random/query",
                json={'query': self.test_data['read']}
            )
            assert response.status_code == 200
            responses.append(response.json())
        print(f"{Fore.GREEN}✓ Random routing test passed{Style.RESET_ALL}")

    def test_smart_strategy(self):
        """Test smart routing strategy"""
        print(f"{Fore.BLUE}Testing smart routing strategy...{Style.RESET_ALL}")
        response = requests.post(
            f"{self.gatekeeper_url}/smart/query",
            json={'query': self.test_data['read']}
        )
        assert response.status_code == 200
        print(f"{Fore.GREEN}✓ Smart routing test passed{Style.RESET_ALL}")

    def test_write_replication(self):
        """Test write operations and replication"""
        print(f"{Fore.BLUE}Testing write operations and replication...{Style.RESET_ALL}")
        # Perform write
        write_response = requests.post(
            f"{self.gatekeeper_url}/direct/query",
            json={'query': self.test_data['write']}
        )
        assert write_response.status_code == 200
        
        # Verify on all nodes
        time.sleep(2)  # Allow time for replication
        verify_query = "SELECT * FROM sakila.actor WHERE first_name='Test' AND last_name='Actor';"
        for strategy in ['direct', 'random', 'smart']:
            response = requests.post(
                f"{self.gatekeeper_url}/{strategy}/query",
                json={'query': verify_query}
            )
            assert response.status_code == 200
            assert len(response.json()['result']) > 0
        print(f"{Fore.GREEN}✓ Write replication test passed{Style.RESET_ALL}")

    def test_security(self):
        """Test security features"""
        print(f"{Fore.BLUE}Testing security features...{Style.RESET_ALL}")
        # Test SQL injection prevention
        malicious_queries = [
            "SELECT * FROM sakila.actor; DROP TABLE sakila.actor;",
            "SELECT * FROM sakila.actor WHERE actor_id = 1 OR 1=1;",
            "SELECT * FROM sakila.actor UNION SELECT * FROM mysql.user;",
        ]
        
        for query in malicious_queries:
            response = requests.post(
                f"{self.gatekeeper_url}/query",
                json={'query': query}
            )
            assert response.status_code in [400, 403]
        print(f"{Fore.GREEN}✓ Security tests passed{Style.RESET_ALL}")

    def run_all_tests(self):
        """Run all tests"""
        try:
            print(f"{Fore.YELLOW}Starting infrastructure tests...{Style.RESET_ALL}")
            self.test_direct_strategy()
            self.test_random_strategy()
            self.test_smart_strategy()
            self.test_write_replication()
            self.test_security()
            print(f"\n{Fore.GREEN}All tests passed successfully!{Style.RESET_ALL}")
        except Exception as e:
            print(f"\n{Fore.RED}Test failed: {str(e)}{Style.RESET_ALL}")
            raise

def main():
    gatekeeper_ip = "GATEKEEPER_IP"  # Will be replaced with actual IP
    tester = TestInfrastructure(gatekeeper_ip)
    tester.run_all_tests()

if __name__ == '__main__':
    main()
EOL

chmod +x /home/ubuntu/test_infrastructure.py
python3 /home/ubuntu/test_infrastructure.py
'''

    def get_gatekeeper_user_data(self):
        """Generate user data script for Gatekeeper setup"""
        return '''#!/bin/bash
# Update system
apt-get update
apt-get install -y python3 python3-pip nginx fail2ban

# Install required Python packages
pip3 install flask requests gunicorn prometheus_client

# Create application
cat > /home/ubuntu/gatekeeper.py << 'EOL'
from flask import Flask, request, jsonify
import re
import requests
import logging
from prometheus_client import Counter, Histogram, start_http_server
import time

# Configure logging
logging.basicConfig(
    filename='/var/log/gatekeeper.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Prometheus metrics
REQUEST_COUNT = Counter('gatekeeper_requests_total', 'Total requests received')
BLOCKED_REQUESTS = Counter('gatekeeper_blocked_requests', 'Requests blocked by validation')
RESPONSE_TIME = Histogram('gatekeeper_response_seconds', 'Response time in seconds')

app = Flask(__name__)

TRUSTED_HOST = "TRUSTED_HOST_IP"

def validate_sql_query(query):
    """Enhanced SQL injection prevention"""
    dangerous_patterns = [
        r'--',
        r';.*;',
        r'\/\*.*\*\/',
        r'UNION.*SELECT',
        r'DROP.*TABLE',
        r'DELETE.*FROM',
        r'INSERT.*INTO',
        r'UPDATE.*SET',
        r'EXEC.*sp_',
        r'EXECUTE.*sp_',
        r'DECLARE.*@',
        r'PRINT.*@@',
        r'SELECT.*INTO.*OUTFILE',
        r'LOAD.*DATA.*INFILE'
    ]
    
    query = query.upper()
    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            BLOCKED_REQUESTS.inc()
            return False
    return True

@app.route('/query', methods=['POST'])
def handle_query():
    start_time = time.time()
    REQUEST_COUNT.inc()
    
    try:
        data = request.json
        if not data or 'query' not in data:
            BLOCKED_REQUESTS.inc()
            return jsonify({"error": "Invalid request format"}), 400

        query = data['query']
        strategy = data.get('strategy', 'smart')
        
        # Validate query
        if not validate_sql_query(query):
            return jsonify({"error": "Invalid query detected"}), 400

        # Forward to trusted host
        response = requests.post(
            f'http://{TRUSTED_HOST}:5001/forward',
            json={'query': query, 'strategy': strategy},
            timeout=5
        )
        
        duration = time.time() - start_time
        RESPONSE_TIME.observe(duration)
        
        return response.json()
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request timeout"}), 504
    except Exception as e:
        logging.error(f"Error processing request: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    start_http_server(8000)
    app.run(host='0.0.0.0', port=5000)
EOL

# Configure fail2ban
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true

[nginx-http-auth]
enabled = true
EOF

# Configure nginx with rate limiting
cat > /etc/nginx/sites-available/gatekeeper << 'EOF'
limit_req_zone $binary_remote_addr zone=one:10m rate=10r/s;

server {
    listen 80;
    server_name _;

    location / {
        limit_req zone=one burst=20 nodelay;
        proxy_pass http://localhost:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 300;
        proxy_connect_timeout 300;
    }

    location /metrics {
        proxy_pass http://localhost:8000;
    }
}
EOF

ln -s /etc/nginx/sites-available/gatekeeper /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Create service file
cat > /etc/systemd/system/gatekeeper.service << EOL
[Unit]
Description=Gatekeeper Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/local/bin/gunicorn --workers 4 --bind 0.0.0.0:5000 gatekeeper:app
Restart=always
StandardOutput=append:/var/log/gatekeeper/app.log
StandardError=append:/var/log/gatekeeper/error.log

[Install]
WantedBy=multi-user.target
EOL

# Create log directories
mkdir -p /var/log/gatekeeper
chown -R ubuntu:ubuntu /var/log/gatekeeper

# Configure firewall
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw allow from 10.0.0.0/16 to any port 5000
ufw allow from 10.0.0.0/16 to any port 8000

# Secure the server
# Disable root SSH login
sed -i 's/#PermitRootLogin yes/PermitRootLogin no/' /etc/ssh/sshd_config

# Configure SSH to be more secure
cat >> /etc/ssh/sshd_config << 'EOF'
Protocol 2
MaxAuthTries 3
PermitEmptyPasswords no
X11Forwarding no
AllowTcpForwarding no
AllowAgentForwarding no
EOF

# Restart SSH
systemctl restart ssh

# Configure system security limits
cat >> /etc/security/limits.conf << 'EOF'
* soft nofile 65535
* hard nofile 65535
EOF

# Optimize kernel parameters
cat > /etc/sysctl.d/99-security.conf << 'EOF'
# Enable IP spoofing protection
net.ipv4.conf.all.rp_filter = 1

# Disable IP source routing
net.ipv4.conf.all.accept_source_route = 0

# Enable TCP SYN cookie protection
net.ipv4.tcp_syncookies = 1

# Enable bad error message protection
net.ipv4.icmp_ignore_bogus_error_responses = 1

# Enable logging of suspicious packets
net.ipv4.conf.all.log_martians = 1
EOF

# Apply sysctl settings
sysctl -p /etc/sysctl.d/99-security.conf

# Enable UFW
ufw --force enable

# Start services
systemctl daemon-reload
systemctl enable gatekeeper
systemctl start gatekeeper
systemctl enable nginx
systemctl restart nginx
systemctl enable fail2ban
systemctl start fail2ban

# Output completion message
echo "Gatekeeper setup completed successfully"
'''

    def get_trusted_host_user_data(self):
        """Generate user data script for Trusted Host setup"""
        return '''#!/bin/bash
# Update system
apt-get update
apt-get install -y python3 python3-pip nginx fail2ban

# Install required Python packages
pip3 install flask requests gunicorn prometheus_client

# Create application
cat > /home/ubuntu/trusted_host.py << 'EOL'
from flask import Flask, request, jsonify
import requests
import logging
from prometheus_client import Counter, Histogram, start_http_server
import time

# Configure logging
logging.basicConfig(
    filename='/var/log/trusted_host.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Prometheus metrics
REQUEST_COUNT = Counter('trusted_host_requests_total', 'Total requests handled')
RESPONSE_TIME = Histogram('trusted_host_response_seconds', 'Response time in seconds')
ERROR_COUNT = Counter('trusted_host_errors_total', 'Total errors encountered')

app = Flask(__name__)

PROXY_HOST = "PROXY_IP"
ROUTING_STRATEGIES = ['direct', 'random', 'smart']

def validate_request(request_data):
    """Validate incoming requests"""
    if not request_data:
        return False, "Empty request"
    if 'query' not in request_data:
        return False, "Missing query"
    if 'strategy' in request_data and request_data['strategy'] not in ROUTING_STRATEGIES:
        return False, "Invalid routing strategy"
    return True, None

@app.route('/forward', methods=['POST'])
def forward_request():
    start_time = time.time()
    REQUEST_COUNT.inc()
    
    try:
        data = request.json
        valid, error = validate_request(data)
        if not valid:
            ERROR_COUNT.inc()
            return jsonify({"error": error}), 400

        query = data['query']
        strategy = data.get('strategy', 'smart')
        
        # Forward to proxy with chosen routing strategy
        response = requests.post(
            f'http://{PROXY_HOST}:5000/{strategy}/query',
            json={'query': query},
            timeout=5
        )
        
        duration = time.time() - start_time
        RESPONSE_TIME.observe(duration)
        
        return response.json()
    except requests.exceptions.Timeout:
        ERROR_COUNT.inc()
        return jsonify({"error": "Proxy timeout"}), 504
    except Exception as e:
        ERROR_COUNT.inc()
        logging.error(f"Error processing request: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"})

if __name__ == '__main__':
    start_http_server(8000)
    app.run(host='0.0.0.0', port=5001)
EOL

# Configure fail2ban
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 3

[sshd]
enabled = true

[nginx-http-auth]
enabled = true
EOF

# Configure UFW
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow proto tcp from ${GATEKEEPER_IP} to any port 5001 comment 'Allow Gatekeeper'
ufw allow proto tcp from ${PROXY_IP} to any port mysql comment 'Allow Proxy'
ufw allow from 10.0.0.0/16 to any port 5001 comment 'Allow VPC traffic'
ufw allow 22/tcp comment 'Allow SSH'
ufw --force enable

# Create service
cat > /etc/systemd/system/trusted-host.service << EOL
[Unit]
Description=Trusted Host Service
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/local/bin/gunicorn --workers 4 --bind 0.0.0.0:5001 trusted_host:app
Restart=always
StandardOutput=append:/var/log/trusted_host/app.log
StandardError=append:/var/log/trusted_host/error.log

[Install]
WantedBy=multi-user.target
EOL

# Create log directory
mkdir -p /var/log/trusted_host
chown -R ubuntu:ubuntu /var/log/trusted_host

# Start services
systemctl daemon-reload
systemctl enable trusted-host
systemctl start trusted-host
systemctl enable fail2ban
systemctl start fail2ban
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
    try:
        print("Starting infrastructure deployment...")
        
        if infrastructure.setup_infrastructure():
            print("\nInfrastructure setup completed successfully!")
            
            # Get Gatekeeper's public IP
            gk_info = infrastructure.ec2.describe_instances(
                InstanceIds=[infrastructure.instances['gatekeeper']]
            )
            gk_public_ip = gk_info['Reservations'][0]['Instances'][0]['PublicIpAddress']
            
            print("\nWaiting for all services to be fully operational...")
            time.sleep(120)  # Attendre que tous les services soient prêts
            
            # Vérifier les services
            infrastructure.verify_services()
            
            print("\nRunning system tests...")
            test_script = infrastructure.get_test_script()
            test_script = test_script.replace('GATEKEEPER_IP', gk_public_ip)
            
            # Créer et exécuter le script de test
            with open('test_infrastructure.py', 'w') as f:
                f.write(test_script)
            os.system('python3 test_infrastructure.py')
            
            print("\nRunning benchmarks...")
            benchmark_script = infrastructure.get_benchmark_script()
            benchmark_script = benchmark_script.replace('GATEKEEPER_IP', gk_public_ip)
            
            # Créer et exécuter le script de benchmark
            with open('benchmark.py', 'w') as f:
                f.write(benchmark_script)
            os.system('python3 benchmark.py')
            
            print("\nCluster is ready to use!")
            print(f"\nGatekeeper Public IP: {gk_public_ip}")
            print("\nExample queries for different routing strategies:")
            print("\n1. Direct routing:")
            print(f'''curl -X POST http://{gk_public_ip}:5000/query \\
                -H "Content-Type: application/json" \\
                -d '{{"query": "SELECT * FROM sakila.actor LIMIT 5;", "strategy": "direct"}}\'''')
            
            print("\n2. Random routing:")
            print(f'''curl -X POST http://{gk_public_ip}:5000/query \\
                -H "Content-Type: application/json" \\
                -d '{{"query": "SELECT * FROM sakila.actor LIMIT 5;", "strategy": "random"}}\'''')
            
            print("\n3. Smart routing (default):")
            print(f'''curl -X POST http://{gk_public_ip}:5000/query \\
                -H "Content-Type: application/json" \\
                -d '{{"query": "SELECT * FROM sakila.actor LIMIT 5;"}}\'''')
            
            print("\nBenchmark results can be found in 'benchmark_results.json'")
            print("Test results can be found in the output above")
            
        else:
            print("Failed to setup infrastructure")
            
    except Exception as e:
        print(f"Error during deployment: {e}")
        raise

if __name__ == "__main__":
    main()