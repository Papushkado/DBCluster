# infrastructure.py
import boto3
import time
import os
from config import AWSConfig, MySQLConfig

class CloudInfrastructure:
    def __init__(self):
        self.ec2 = boto3.client('ec2', region_name=AWSConfig.region)
        self.instances = {}
        self.vpc_id = None
        self.subnet_id = None
        self.internet_gateway_id = None
        self._setup_network()
        self._create_key_pair()

    def _create_key_pair(self):
        try:
            print("Creating key pair...")
        
            # Delete existing key pair if it exists
            try:
                self.ec2.delete_key_pair(KeyName=AWSConfig.key_name)
            except:
                pass
            
            # Create new key pair
            response = self.ec2.create_key_pair(KeyName=AWSConfig.key_name)
        
            # Save private key
            key_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys')
            os.makedirs(key_dir, exist_ok=True)
            key_path = os.path.join(key_dir, f"{AWSConfig.key_name}.pem")
        
            with open(key_path, 'w') as key_file:
                key_file.write(response['KeyMaterial'])
        
            os.chmod(key_path, 0o400)
            print(f"Created key pair and saved to {key_path}")
            return True
        
        except Exception as e:
            print(f"Error creating key pair: {e}")
            return False
    def _setup_network(self):
        try:
            # Create VPC
            vpc = self.ec2.create_vpc(CidrBlock='10.0.0.0/16')
            self.vpc_id = vpc['Vpc']['VpcId']
            
            # Enable DNS hostnames
            self.ec2.modify_vpc_attribute(
                EnableDnsHostnames={'Value': True},
                VpcId=self.vpc_id
            )

            # Create subnet
            subnet = self.ec2.create_subnet(
                VpcId=self.vpc_id,
                CidrBlock='10.0.1.0/24',
                AvailabilityZone=f"{AWSConfig.region}a"
            )
            self.subnet_id = subnet['Subnet']['SubnetId']

            # Create and attach internet gateway
            igw = self.ec2.create_internet_gateway()
            self.internet_gateway_id = igw['InternetGateway']['InternetGatewayId']
            self.ec2.attach_internet_gateway(
                InternetGatewayId=self.internet_gateway_id,
                VpcId=self.vpc_id
            )

            # Create route table
            route_table = self.ec2.create_route_table(VpcId=self.vpc_id)
            route_table_id = route_table['RouteTable']['RouteTableId']
            
            # Add route to internet through gateway
            self.ec2.create_route(
                RouteTableId=route_table_id,
                DestinationCidrBlock='0.0.0.0/0',
                GatewayId=self.internet_gateway_id
            )

            # Associate route table with subnet
            self.ec2.associate_route_table(
                RouteTableId=route_table_id,
                SubnetId=self.subnet_id
            )

            print("VPC and network setup completed")
            
        except Exception as e:
            print(f"Error setting up network: {e}")
            self.cleanup()
            raise

    def create_instance(self, name, instance_type, security_group_ids, user_data=None):
        try:
            # Modified instance creation to use VPC subnet
            response = self.ec2.run_instances(
                ImageId=AWSConfig.ami_id,
                InstanceType=instance_type,
                MinCount=1,
                MaxCount=1,
                KeyName=AWSConfig.key_name,
                SecurityGroupIds=security_group_ids,
                SubnetId=self.subnet_id,  # Add subnet ID
                UserData=user_data,
                TagSpecifications=[{
                    'ResourceType': 'instance',
                    'Tags': [{'Key': 'Name', 'Value': name}]
                }]
            )
            
            instance_id = response['Instances'][0]['InstanceId']
            self.instances[name] = instance_id
            
            # Allocate and associate Elastic IP
            eip = self.ec2.allocate_address(Domain='vpc')
            self.ec2.associate_address(
                InstanceId=instance_id,
                AllocationId=eip['AllocationId']
            )
            
            print(f"Waiting for instance {name} to be running...")
            waiter = self.ec2.get_waiter('instance_running')
            waiter.wait(InstanceIds=[instance_id])
            
            return instance_id
            
        except Exception as e:
            print(f"Error creating instance {name}: {e}")
            return None

    def create_security_group(self, name, description, rules):
        try:
            response = self.ec2.create_security_group(
                GroupName=name,
                Description=description,
                VpcId=self.vpc_id  # Add VPC ID
            )
            
            security_group_id = response['GroupId']
            
            # Add SSH rule
            self.ec2.authorize_security_group_ingress(
                GroupId=security_group_id,
                IpPermissions=[{
                    'IpProtocol': 'tcp',
                    'FromPort': 22,
                    'ToPort': 22,
                    'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                }]
            )
            
            # Add custom rules
            for rule in rules:
                self.ec2.authorize_security_group_ingress(
                    GroupId=security_group_id,
                    IpPermissions=[rule]
                )
                
            return security_group_id
            
        except Exception as e:
            print(f"Error creating security group: {e}")
            return None

    def cleanup(self):
        try:
            # Terminate instances
            if self.instances:
                instance_ids = list(self.instances.values())
                self.ec2.terminate_instances(InstanceIds=instance_ids)
                print("Terminating instances...")
                
                # Wait for instances to terminate
                waiter = self.ec2.get_waiter('instance_terminated')
                waiter.wait(InstanceIds=instance_ids)

            # Delete security groups
            for sg in self.ec2.describe_security_groups(
                Filters=[{'Name': 'vpc-id', 'Values': [self.vpc_id]}]
            )['SecurityGroups']:
                try:
                    self.ec2.delete_security_group(GroupId=sg['GroupId'])
                except Exception as e:
                    print(f"Error deleting security group {sg['GroupId']}: {e}")

            # Detach and delete internet gateway
            if self.internet_gateway_id:
                self.ec2.detach_internet_gateway(
                    InternetGatewayId=self.internet_gateway_id,
                    VpcId=self.vpc_id
                )
                self.ec2.delete_internet_gateway(
                    InternetGatewayId=self.internet_gateway_id
                )

            # Delete subnet
            if self.subnet_id:
                self.ec2.delete_subnet(SubnetId=self.subnet_id)

            # Delete VPC
            if self.vpc_id:
                self.ec2.delete_vpc(VpcId=self.vpc_id)

            # Delete key pair
            self.ec2.delete_key_pair(KeyName=AWSConfig.key_name)
            key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                  'keys', f"{AWSConfig.key_name}.pem")
            if os.path.exists(key_path):
                os.remove(key_path)

            print("Cleanup completed")
            
        except Exception as e:
            print(f"Error during cleanup: {e}")
