# infrastructure.py
import boto3
import time
import os
from config import AWSConfig, MySQLConfig

class CloudInfrastructure:
    def __init__(self):
        self.ec2 = boto3.client('ec2', region_name=AWSConfig.region)
        self.instances = {}
        self._create_key_pair()
        
    def _create_key_pair(self):
        """Create a new key pair and save it locally"""
        key_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'keys')
        os.makedirs(key_dir, exist_ok=True)
        key_path = os.path.join(key_dir, f"{AWSConfig.key_name}.pem")
        
        try:
            # Delete existing key pair if it exists
            try:
                self.ec2.delete_key_pair(KeyName=AWSConfig.key_name)
            except:
                pass
                
            # Create new key pair
            response = self.ec2.create_key_pair(KeyName=AWSConfig.key_name)
            
            # Save private key
            with open(key_path, 'w') as key_file:
                key_file.write(response['KeyMaterial'])
            
            # Set correct permissions for key file
            os.chmod(key_path, 0o400)
            
            print(f"Created new key pair and saved to {key_path}")
            return True
            
        except Exception as e:
            print(f"Error creating key pair: {e}")
            return False
        
    def create_security_group(self, name, description, rules):
        try:
            existing_group_id = None
            
            # Check if security group already exists
            try:
                response = self.ec2.describe_security_groups(
                    Filters=[{'Name': 'group-name', 'Values': [name]}]
                )
                if response['SecurityGroups']:
                    existing_group_id = response['SecurityGroups'][0]['GroupId']
                    print(f"Found existing security group {name}")
                    
                    # Remove all existing rules
                    try:
                        sg = response['SecurityGroups'][0]
                        if 'IpPermissions' in sg and sg['IpPermissions']:
                            self.ec2.revoke_security_group_ingress(
                                GroupId=existing_group_id,
                                IpPermissions=sg['IpPermissions']
                            )
                    except Exception as e:
                        print(f"Error removing existing rules: {e}")
                        
                    security_group_id = existing_group_id
                else:
                    # Create new security group
                    response = self.ec2.create_security_group(
                        GroupName=name,
                        Description=description
                    )
                    security_group_id = response['GroupId']
                    print(f"Created new security group {name}")
            except Exception as e:
                print(f"Error checking security group {name}: {e}")
                return None
            
            # Add SSH access rule
            try:
                self.ec2.authorize_security_group_ingress(
                    GroupId=security_group_id,
                    IpPermissions=[{
                        'IpProtocol': 'tcp',
                        'FromPort': 22,
                        'ToPort': 22,
                        'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
                    }]
                )
            except Exception as e:
                print(f"Warning: Could not add SSH rule: {e}")
            
            # Add custom rules
            for rule in rules:
                try:
                    self.ec2.authorize_security_group_ingress(
                        GroupId=security_group_id,
                        IpPermissions=[rule]
                    )
                except Exception as e:
                    print(f"Warning: Could not add rule {rule}: {e}")
                
            return security_group_id
            
        except Exception as e:
            print(f"Error creating/updating security group: {e}")
            return None
            
    def create_instance(self, name, instance_type, security_group_ids, user_data=None):
        try:
            # Check for existing instance with the same name
            existing_instances = self.ec2.describe_instances(
                Filters=[
                    {'Name': 'tag:Name', 'Values': [name]},
                    {'Name': 'instance-state-name', 'Values': ['pending', 'running']}
                ]
            )
            
            if existing_instances['Reservations']:
                print(f"Warning: Instance {name} already exists, terminating...")
                instance_id = existing_instances['Reservations'][0]['Instances'][0]['InstanceId']
                self.ec2.terminate_instances(InstanceIds=[instance_id])
                waiter = self.ec2.get_waiter('instance_terminated')
                waiter.wait(InstanceIds=[instance_id])
            
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
            
            print(f"Waiting for instance {name} to be running...")
            waiter = self.ec2.get_waiter('instance_running')
            waiter.wait(InstanceIds=[instance_id])
            
            # Wait for status checks to pass
            print(f"Waiting for instance {name} status checks...")
            waiter = self.ec2.get_waiter('instance_status_ok')
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
            
    def cleanup(self):
        """Cleanup all created resources"""
        try:
            # Terminate all instances
            if self.instances:
                instance_ids = list(self.instances.values())
                self.ec2.terminate_instances(InstanceIds=instance_ids)
                print("Terminating instances...")
                
            # Delete key pair
            try:
                self.ec2.delete_key_pair(KeyName=AWSConfig.key_name)
                key_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                                      'keys', f"{AWSConfig.key_name}.pem")
                if os.path.exists(key_path):
                    os.remove(key_path)
                print("Deleted key pair")
            except:
                pass
                
            print("Cleanup completed")
            
        except Exception as e:
            print(f"Error during cleanup: {e}")