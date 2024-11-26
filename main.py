import boto3
import time
from botocore.exceptions import ClientError

class CloudInfrastructure:
    def __init__(self, region="us-east-1"):
        self.ec2 = boto3.client('ec2', region_name=region)
        self.region = region
        self.vpc_id = None
        self.subnet_id = None
        self.security_groups = {}
        self.instances = {}

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

    def create_security_groups(self):
        """Create security groups for different components"""
        # MySQL Cluster Security Group
        mysql_sg = self.ec2.create_security_group(
            GroupName='MySQL-Cluster-SG',
            Description='Security group for MySQL Cluster',
            VpcId=self.vpc_id
        )
        self.security_groups['mysql'] = mysql_sg['GroupId']
        
        # Allow MySQL port within the security group
        self.ec2.authorize_security_group_ingress(
            GroupId=mysql_sg['GroupId'],
            IpPermissions=[
                {
                    'IpProtocol': 'tcp',
                    'FromPort': 3306,
                    'ToPort': 3306,
                    'IpRanges': [{'CidrIp': '10.0.0.0/16'}]
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
        
        # Gatekeeper Security Group
        gk_sg = self.ec2.create_security_group(
            GroupName='Gatekeeper-SG',
            Description='Security group for Gatekeeper',
            VpcId=self.vpc_id
        )
        self.security_groups['gatekeeper'] = gk_sg['GroupId']
        
        # Allow inbound HTTP/HTTPS for Gatekeeper
        self.ec2.authorize_security_group_ingress(
            GroupId=gk_sg['GroupId'],
            IpPermissions=[
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
                }
            ]
        )

        print("Created Security Groups")
        return self.security_groups

    def create_instances(self):
        """Create EC2 instances for the cluster"""
        # Ubuntu 20.04 LTS AMI ID (replace with the correct AMI ID for your region)
        ami_id = 'ami-0261755bbcb8c4a84'  # Update this for your region
        
        # Create MySQL instances (3 t2.micro)
        for i in range(3):
            instance = self.ec2.run_instances(
                ImageId=ami_id,
                InstanceType='t2.micro',
                MaxCount=1,
                MinCount=1,
                SecurityGroupIds=[self.security_groups['mysql']],
                SubnetId=self.subnet_id,
                TagSpecifications=[{
                    'ResourceType': 'instance',
                    'Tags': [{
                        'Key': 'Name',
                        'Value': f'MySQL-Node-{i}'
                    }]
                }]
            )
            self.instances[f'mysql_{i}'] = instance['Instances'][0]['InstanceId']
        
        # Create Proxy instance (t2.large)
        proxy_instance = self.ec2.run_instances(
            ImageId=ami_id,
            InstanceType='t2.large',
            MaxCount=1,
            MinCount=1,
            SecurityGroupIds=[self.security_groups['proxy']],
            SubnetId=self.subnet_id,
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [{
                    'Key': 'Name',
                    'Value': 'Proxy'
                }]
            }]
        )
        self.instances['proxy'] = proxy_instance['Instances'][0]['InstanceId']
        
        # Create Gatekeeper and Trusted Host instances (t2.large)
        for role in ['gatekeeper', 'trusted-host']:
            instance = self.ec2.run_instances(
                ImageId=ami_id,
                InstanceType='t2.large',
                MaxCount=1,
                MinCount=1,
                SecurityGroupIds=[self.security_groups['gatekeeper']],
                SubnetId=self.subnet_id,
                TagSpecifications=[{
                    'ResourceType': 'instance',
                    'Tags': [{
                        'Key': 'Name',
                        'Value': role
                    }]
                }]
            )
            self.instances[role] = instance['Instances'][0]['InstanceId']
        
        print("Created EC2 Instances")
        return self.instances
    
    def get_mysql_user_data(self, is_manager=False):
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

    def create_instances(self):
        """Create EC2 instances for the cluster"""
        # Ubuntu 20.04 LTS AMI ID
        ami_id = 'ami-0261755bbcb8c4a84'  # Update this for your region
        
        # Create MySQL instances (3 t2.micro)
        for i in range(3):
            is_manager = (i == 0)  # First instance will be the manager
            instance = self.ec2.run_instances(
                ImageId=ami_id,
                InstanceType='t2.micro',
                MaxCount=1,
                MinCount=1,
                SecurityGroupIds=[self.security_groups['mysql']],
                SubnetId=self.subnet_id,
                UserData=self.get_mysql_user_data(is_manager),  # Add MySQL setup script
                TagSpecifications=[{
                    'ResourceType': 'instance',
                    'Tags': [{
                        'Key': 'Name',
                        'Value': f'MySQL-{"Manager" if is_manager else f"Worker-{i}"}'
                    }]
                }]
            )
            self.instances[f'mysql_{i}'] = instance['Instances'][0]['InstanceId']
        
        # Create Proxy instance (t2.large)
        proxy_instance = self.ec2.run_instances(
            ImageId=ami_id,
            InstanceType='t2.large',
            MaxCount=1,
            MinCount=1,
            SecurityGroupIds=[self.security_groups['proxy']],
            SubnetId=self.subnet_id,
            TagSpecifications=[{
                'ResourceType': 'instance',
                'Tags': [{
                    'Key': 'Name',
                    'Value': 'Proxy'
                }]
            }]
        )
        self.instances['proxy'] = proxy_instance['Instances'][0]['InstanceId']
        
        # Create Gatekeeper and Trusted Host instances (t2.large)
        for role in ['gatekeeper', 'trusted-host']:
            instance = self.ec2.run_instances(
                ImageId=ami_id,
                InstanceType='t2.large',
                MaxCount=1,
                MinCount=1,
                SecurityGroupIds=[self.security_groups['gatekeeper']],
                SubnetId=self.subnet_id,
                TagSpecifications=[{
                    'ResourceType': 'instance',
                    'Tags': [{
                        'Key': 'Name',
                        'Value': role
                    }]
                }]
            )
            self.instances[role] = instance['Instances'][0]['InstanceId']
        
        print("Created EC2 Instances")
        return self.instances

    def setup_infrastructure(self):
        """Setup complete infrastructure"""
        try:
            self.create_vpc()
            time.sleep(30)  # Wait for VPC to be available
            self.create_subnet()
            time.sleep(30)  # Wait for subnet to be available
            self.create_security_groups()
            time.sleep(30)  # Wait for security groups to be available
            self.create_instances()
            return True
        except ClientError as e:
            print(f"Error setting up infrastructure: {e}")
            return False

def main():
    infrastructure = CloudInfrastructure()
    if infrastructure.setup_infrastructure():
        print("Infrastructure setup completed successfully!")
    else:
        print("Failed to setup infrastructure")

if __name__ == "__main__":
    main()