from dataclasses import dataclass
import json
import boto3
from botocore.exceptions import ClientError
import paramiko
from scp import SCPClient
import time
from typing import Any
import os


@dataclass
class EC2Instance:
    instance: Any
    name: str

    def get_name(self):
        return f"{self.name}_{self.instance.id}"


# Function to create an SSH client
def create_ssh_client(host, user, key_path):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=host, username=user, key_filename=key_path)
    return ssh


class EC2Manager:
    def __init__(self):
        self.key_name = "key_pair_db_cluster"
        
        # Clients and resources
        self.ec2_client = boto3.client("ec2", region_name="us-east-1")
        self.ec2_resource = boto3.resource("ec2", region_name="us-east-1")

        # Create VPC
        vpc = self.ec2_client.create_vpc(
            CidrBlock='10.0.0.0/16',
            TagSpecifications=[{
                'ResourceType': 'vpc',
                'Tags': [{'Key': 'Name', 'Value': 'cluster-vpc'}]
            }]
        )['Vpc']
        self.vpc_id = vpc['VpcId']
        
        # Wait for VPC to be available
        waiter = self.ec2_client.get_waiter('vpc_available')
        waiter.wait(VpcIds=[self.vpc_id])
        
        # Enable DNS hostnames
        self.ec2_client.modify_vpc_attribute(
            VpcId=self.vpc_id,
            EnableDnsHostnames={'Value': True}
        )

        # Create and attach internet gateway
        self.igw = self.ec2_client.create_internet_gateway()['InternetGateway']
        self.ec2_client.attach_internet_gateway(
            InternetGatewayId=self.igw['InternetGatewayId'],
            VpcId=self.vpc_id
        )

        # Create subnet
        self.subnet = self.ec2_client.create_subnet(
            VpcId=self.vpc_id,
            CidrBlock='10.0.1.0/24',
            AvailabilityZone='us-east-1a'
        )['Subnet']
        
        self.ec2_client.modify_subnet_attribute(
        SubnetId=self.subnet['SubnetId'],
        MapPublicIpOnLaunch={'Value': True}
        )

        # Configure route table
        self.route_table = self.ec2_client.create_route_table(VpcId=self.vpc_id)['RouteTable']
        self.ec2_client.create_route(
            RouteTableId=self.route_table['RouteTableId'],
            DestinationCidrBlock='0.0.0.0/0',
            GatewayId=self.igw['InternetGatewayId']
        )
        self.ec2_client.associate_route_table(
            RouteTableId=self.route_table['RouteTableId'],
            SubnetId=self.subnet['SubnetId']
        )

        # Create security groups with proper rules
        self._create_security_groups()
        
        self.ami_id = self._get_latest_ubuntu_ami()
        self.ssh_key_path = os.path.expanduser(f"./{self.key_name}.pem")

        # Initialize instance variables
        self.manager_instance = None
        self.worker_instances = []
        self.proxy_instance = None
        self.gatekeeper_instance = None
        self.trusted_host_instance = None

    def create_key_pair(self) -> None:
        """Create key pair and save the private key"""
        try:
            response = self.ec2_client.create_key_pair(KeyName=self.key_name)
            private_key = response["KeyMaterial"]
        
            with open(f"{self.key_name}.pem", "w") as file:
                file.write(private_key)
            
            # Set correct permissions for key file
            os.chmod(f"{self.key_name}.pem", 0o400)
        
        except ClientError as e:
            if 'InvalidKeyPair.Duplicate' in str(e):
                self.ec2_client.delete_key_pair(KeyName=self.key_name)
                self.create_key_pair()
            else:
                raise e
    def _create_security_groups(self):
        timestamp = str(int(time.time()))
    
        self.cluster_security_group_id = self.ec2_client.create_security_group(
            GroupName=f"common_sg_{timestamp}",
            Description="Security group for manager and workers",
            VpcId=self.vpc_id
        )['GroupId']
    
        self.proxy_security_group_id = self.ec2_client.create_security_group(
            GroupName=f"proxy_sg_{timestamp}",
            Description="Proxy security group",
            VpcId=self.vpc_id
        )['GroupId']
    
        self.trusted_host_security_group_id = self.ec2_client.create_security_group(
            GroupName=f"trusted_host_sg_{timestamp}",
            Description="Trusted host security group",
            VpcId=self.vpc_id
        )['GroupId']
    
        self.gatekeeper_security_group_id = self.ec2_client.create_security_group(
            GroupName=f"gatekeeper_sg_{timestamp}",
            Description="Gatekeeper security group",
            VpcId=self.vpc_id
        )['GroupId']

    def install_network_security(self):
        """Configure IPtables rules for the trusted host"""
        iptables_commands = [
            # Flush existing rules
            "sudo iptables -F",
            # Set default policies
            "sudo iptables -P INPUT DROP",
            "sudo iptables -P FORWARD DROP",
            "sudo iptables -P OUTPUT DROP",
            # Allow established connections
            "sudo iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT",
            "sudo iptables -A OUTPUT -m state --state ESTABLISHED,RELATED -j ACCEPT",
            # Allow SSH only from specific IPs
            f"sudo iptables -A INPUT -p tcp --dport 22 -s {self.gatekeeper_instance.instance.private_ip_address} -j ACCEPT",
            # Allow application port
            "sudo iptables -A INPUT -p tcp --dport 5000 -s 10.0.0.0/16 -j ACCEPT",
            # Save rules
            "sudo netfilter-persistent save"
        ]
        
        self.execute_commands(iptables_commands, [self.trusted_host_instance])

    def get_cpu_utilization(self, instance_id, start_time, end_time):
        cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')
        response = cloudwatch.get_metric_statistics(
            Namespace='AWS/EC2',
            MetricName='CPUUtilization',
            Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=60,
            Statistics=['Average']
        )
        return response['Datapoints']

    def launch_instances(self):
        """Launch instances in the created subnet"""
        common_args = {
            'SubnetId': self.subnet['SubnetId'],
            'ImageId': self.ami_id,
            'KeyName': self.key_name,
            'Monitoring': {'Enabled': True},
            'BlockDeviceMappings': [{
                'DeviceName': '/dev/sda1',
                'Ebs': {
                    'VolumeSize': 16,
                    'VolumeType': 'gp3',
                    'DeleteOnTermination': True
                }
            }]
        }
        # Launch worker instances
        for i in range(2):
            self.worker_instances.append(
                EC2Instance(
                    self.ec2_resource.create_instances(
                        ImageId=self.ami_id,
                        InstanceType="t2.micro",
                        MinCount=1,
                        MaxCount=1,
                        SecurityGroupIds=[self.cluster_security_group_id],
                        KeyName=self.key_name,
                        SubnetId=self.subnet['SubnetId'],
                        Monitoring={'Enabled': True},
                        BlockDeviceMappings=[
                            {
                                "DeviceName": "/dev/sda1",
                                "Ebs": {
                                    "VolumeSize": 16,
                                    "VolumeType": "gp3",
                                    "DeleteOnTermination": True,
                                },
                            }
                        ],
                    )[0],
                    name=f"worker{i + 1}",
                )
            )

        # Launch manager instance
        self.manager_instance = EC2Instance(
            self.ec2_resource.create_instances(
                ImageId=self.ami_id,
                InstanceType="t2.micro",
                MinCount=1,
                MaxCount=1,
                SecurityGroupIds=[self.cluster_security_group_id],
                KeyName=self.key_name,
                SubnetId=self.subnet['SubnetId'],
                Monitoring={'Enabled': True},
                BlockDeviceMappings=[
                    {
                        "DeviceName": "/dev/sda1",
                        "Ebs": {
                            "VolumeSize": 16,
                            "VolumeType": "gp3",
                            "DeleteOnTermination": True,
                        },
                    }
                ],
            )[0],
            name="manager",
        )

        # Launch proxy instance
        self.proxy_instance = EC2Instance(
            self.ec2_resource.create_instances(
                ImageId=self.ami_id,
                InstanceType="t2.large",
                MinCount=1,
                MaxCount=1,
                SecurityGroupIds=[self.proxy_security_group_id],
                KeyName=self.key_name,
                SubnetId=self.subnet['SubnetId'],
                Monitoring={'Enabled': True},
                BlockDeviceMappings=[
                    {
                        "DeviceName": "/dev/sda1",
                        "Ebs": {
                            "VolumeSize": 16,
                            "VolumeType": "gp3",
                            "DeleteOnTermination": True,
                        },
                    }
                ],
            )[0],
            name="proxy",
        )

        # Launch trusted host instance
        self.trusted_host_instance = EC2Instance(
            self.ec2_resource.create_instances(
                ImageId=self.ami_id,
                InstanceType="t2.large",
                MinCount=1,
                MaxCount=1,
                SecurityGroupIds=[self.trusted_host_security_group_id],
                KeyName=self.key_name,
                SubnetId=self.subnet['SubnetId'],
                Monitoring={'Enabled': True},
                BlockDeviceMappings=[
                    {
                        "DeviceName": "/dev/sda1",
                        "Ebs": {
                            "VolumeSize": 16,
                            "VolumeType": "gp3",
                            "DeleteOnTermination": True,
                        },
                    }
                ],
            )[0],
            name="trusted_host",
        )

        # Launch gatekeeper instance
        self.gatekeeper_instance = EC2Instance(
            self.ec2_resource.create_instances(
                ImageId=self.ami_id,
                InstanceType="t2.large",
                MinCount=1,
                MaxCount=1,
                SecurityGroupIds=[self.gatekeeper_security_group_id],
                KeyName=self.key_name,
                SubnetId=self.subnet['SubnetId'],
                Monitoring={'Enabled': True},
                BlockDeviceMappings=[
                    {
                        "DeviceName": "/dev/sda1",
                        "Ebs": {
                            "VolumeSize": 16,
                            "VolumeType": "gp3",
                            "DeleteOnTermination": True,
                        },
                    }
                ],
            )[0],
            name="gatekeeper",
        )
        for instance in [self.manager_instance] + self.worker_instances + [self.proxy_instance, self.trusted_host_instance, self.gatekeeper_instance]:
            instance.instance.reload()
            print(f"Instance {instance.name} - VPC: {instance.instance.vpc_id}, Subnet: {instance.instance.subnet_id}")
            print(f"Instance state: {instance.instance.state['Name']}")
        return self.worker_instances + [
            self.manager_instance,
            self.proxy_instance,
            self.trusted_host_instance,
            self.gatekeeper_instance,
        ]

    def add_inbound_rules(self):
        """
        Add inbound rules for security groups
        """
        # Allow SSH access to all instances
        self.ec2_client.authorize_security_group_ingress(
            GroupId=self.cluster_security_group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [
                        {
                            "CidrIp": "0.0.0.0/0",  # Allow SSH access from anywhere
                        },
                    ],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 5000,
                    "ToPort": 5000,
                    "IpRanges": [  # Allow access from the proxy, and from the manager (for the workers)
                        {
                            "CidrIp": f"{self.manager_instance.instance.public_ip_address}/32"
                        },
                        {
                            "CidrIp": f"{self.proxy_instance.instance.public_ip_address}/32"
                        },
                    ],
                },
            ],
        )
        self.ec2_client.authorize_security_group_ingress(
            GroupId=self.proxy_security_group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 5000,
                    "ToPort": 5000,
                    "IpRanges": [
                        {
                            "CidrIp": f"{self.trusted_host_instance.instance.public_ip_address}/32"  # Allow access from the trusted host
                        }
                    ],
                },
            ],
        )
        self.ec2_client.authorize_security_group_ingress(
            GroupId=self.trusted_host_security_group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 5000,
                    "ToPort": 5000,
                    "IpRanges": [
                        {
                            "CidrIp": f"{self.gatekeeper_instance.instance.public_ip_address}/32"  # Allow access from the gatekeeper
                        }
                    ],
                },
            ],
        )
        self.ec2_client.authorize_security_group_ingress(
            GroupId=self.gatekeeper_security_group_id,
            IpPermissions=[
                {
                    "IpProtocol": "tcp",
                    "FromPort": 22,
                    "ToPort": 22,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],
                },
                {
                    "IpProtocol": "tcp",
                    "FromPort": 5000,
                    "ToPort": 5000,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}],  # Allow access from anywhere
                },
            ],
        )

    def execute_commands(
        self,
        commands: list[str],
        instances: list[EC2Instance],
        print_output: bool = True,
    ) -> None:
        """
        This function executes a list of commands on each instance.
        You can call this function to run any set of commands.
        """
        try:
            for ec2_instance in instances:
                # Connect to the instance
                ssh_client = create_ssh_client(
                    ec2_instance.instance.public_ip_address, "ubuntu", self.ssh_key_path
                )

                # Run the commands
                for command in commands:
                    print(
                        f"Executing command: {command} on instance {ec2_instance.get_name()}"
                    )
                    stdin, stdout, stderr = ssh_client.exec_command(command)

                    # Process output in real-time
                    for line in iter(stdout.readline, ""):
                        if print_output:
                            print(line, end="")  # Print each line from stdout
                    error_output = stderr.read().decode()  # Capture any error output

                    # Wait for command to complete
                    exit_status = stdout.channel.recv_exit_status()
                    if exit_status != 0:
                        print(
                            f"Command '{command}' failed with exit status {exit_status}. Error:\n{error_output}"
                        )
                ssh_client.close()
                time.sleep(2)

        except Exception as e:
            print(f"An error occurred: {e}")

    def install_cluster_dependencies(self) -> None:
        commands = [
        "sudo apt-get update",
        "sudo apt-get install -y mysql-server wget sysbench python3-pip",
        "sudo pip3 install flask mysql-connector-python requests",
        "sudo sed -i 's/bind-address.*/bind-address = 0.0.0.0/' /etc/mysql/mysql.conf.d/mysqld.cnf",
        'sudo mysql -e \'ALTER USER "root"@"localhost" IDENTIFIED WITH mysql_native_password BY "root_password";\'',
        "sudo systemctl restart mysql",
        "sudo systemctl enable mysql",
        'sudo mysql -u root -p"root_password" -e \'CREATE USER IF NOT EXISTS "root"@"%" IDENTIFIED BY "root_password";\'',
        'sudo mysql -u root -p"root_password" -e "GRANT ALL PRIVILEGES ON *.* TO \'root\'@\'%\';"',
        'sudo mysql -u root -p"root_password" -e "FLUSH PRIVILEGES;"',
        "wget https://downloads.mysql.com/docs/sakila-db.tar.gz",
        "tar -xzvf sakila-db.tar.gz",
        'sudo mysql -u root -p"root_password" -e "CREATE DATABASE IF NOT EXISTS sakila;"',
        'sudo mysql -u root -p"root_password" sakila -e "source sakila-db/sakila-schema.sql"',
        'sudo mysql -u root -p"root_password" sakila -e "source sakila-db/sakila-data.sql"',
        'sudo mysql -u root -p"root_password" -e "SHOW DATABASES;"',
        'sudo mysql -u root -p"root_password" -e "USE sakila; SHOW TABLES;"',
        'echo "MYSQL_USER=root" | sudo tee -a /etc/environment',
        'echo "MYSQL_PASSWORD=root_password" | sudo tee -a /etc/environment',
        'echo "MYSQL_DB=sakila" | sudo tee -a /etc/environment',
        'echo "MYSQL_HOST=localhost" | sudo tee -a /etc/environment',
        "source /etc/environment",
        ]

        self.execute_commands(commands, [self.manager_instance] + self.worker_instances, print_output=False)

    def install_network_instances_dependencies(self) -> None:
        commands = [
            "sudo apt-get update",
            "sudo apt-get install -y python3-pip",
            "sudo pip3 install flask requests",
        ]

        # Liste des instances au lieu de les additionner
        network_instances = [self.proxy_instance, self.trusted_host_instance, self.gatekeeper_instance]
        self.execute_commands(commands, network_instances, print_output=False)

    def run_sys_bench(self) -> None:
        sysbench_commands = [
            "sudo sysbench /usr/share/sysbench/oltp_read_only.lua --mysql-db=sakila --mysql-user='root' --mysql-password='root_password' prepare",
            "sudo sysbench /usr/share/sysbench/oltp_read_only.lua --mysql-db=sakila --mysql-user='root' --mysql-password='root_password' run > sysbench_results.txt",
        ]
        # Execute commands
        self.execute_commands(
            sysbench_commands,
            [self.manager_instance] + self.worker_instances,
            print_output=False,
        )

    def save_sys_bench_results(self) -> None:
        try:
            for ec2_instance in [self.manager_instance] + self.worker_instances:
                # Connect to the instance
                ssh_client = create_ssh_client(
                    ec2_instance.instance.public_ip_address, "ubuntu", self.ssh_key_path
                )

                # Download the sysbench results
                scp = SCPClient(ssh_client.get_transport())
                scp.get(
                    "sysbench_results.txt",
                    f"data/sysbench_results_{ec2_instance.get_name()}.txt",
                )
                print(
                    f"Sysbench results downloaded to data/sysbench_results_{ec2_instance.get_name()}.txt"
                )

        except Exception as e:
            print(f"An error occurred: {e}")

        finally:
            scp.close()
            ssh_client.close()

    def upload_flask_apps_to_instances(self):
        try:
            # Upload the Flask app to the manager instance
            ssh_client = create_ssh_client(
                self.manager_instance.instance.public_ip_address,
                "ubuntu",
                self.ssh_key_path,
            )
            scp = SCPClient(ssh_client.get_transport())
            scp.put("scripts/manager_script.py", "manager_script.py")
            scp.put("public_ips.json", "public_ips.json")

        except Exception as e:
            print(f"An error occurred: {e}")

        finally:
            scp.close()
            ssh_client.close()

        # Upload worker script to worker instances
        for worker in self.worker_instances:
            try:
                ssh_client = create_ssh_client(
                    worker.instance.public_ip_address, "ubuntu", self.ssh_key_path
                )
                scp = SCPClient(ssh_client.get_transport())
                scp.put("scripts/worker_script.py", "worker_script.py")
            except Exception as e:
                print(
                    f"Error uploading and starting worker script on {worker.get_name()}: {e}"
                )
            finally:
                scp.close()
                ssh_client.close()

        # Upload proxy script to proxy instance
        try:
            ssh_client = create_ssh_client(
                self.proxy_instance.instance.public_ip_address,
                "ubuntu",
                self.ssh_key_path,
            )
            scp = SCPClient(ssh_client.get_transport())
            scp.put("scripts/proxy_script.py", "proxy_script.py")
            scp.put("public_ips.json", "public_ips.json")

        except Exception as e:
            print(f"An error occurred: {e}")

        finally:
            scp.close()
            ssh_client.close()

        # Upload trusted host script to trusted host instance
        try:
            ssh_client = create_ssh_client(
                self.trusted_host_instance.instance.public_ip_address,
                "ubuntu",
                self.ssh_key_path,
            )
            scp = SCPClient(ssh_client.get_transport())
            scp.put("scripts/trusted_host_script.py", "trusted_host_script.py")
            scp.put("public_ips.json", "public_ips.json")

        except Exception as e:
            print(f"An error occurred: {e}")

        finally:
            scp.close()
            ssh_client.close()

        # Upload gatekeeper script to gatekeeper instance
        try:
            ssh_client = create_ssh_client(
                self.gatekeeper_instance.instance.public_ip_address,
                "ubuntu",
                self.ssh_key_path,
            )
            scp = SCPClient(ssh_client.get_transport())
            scp.put("scripts/gatekeeper_script.py", "gatekeeper_script.py")
            scp.put("public_ips.json", "public_ips.json")

        except Exception as e:
            print(f"An error occurred: {e}")

        finally:
            scp.close()
            ssh_client.close()

    def start_db_cluster_apps(self):
        # Start the Flask app on the manager instance
        commands = [
            "nohup python3 manager_script.py > manager_output.log 2>&1 &",
        ]
        self.execute_commands(commands, [self.manager_instance])

        # Start the Flask app on the worker instances
        commands = [
            "nohup python3 worker_script.py > worker_output.log 2>&1 &",
        ]
        self.execute_commands(commands, self.worker_instances)

    def start_proxy_app(self) -> None:
        # Start the Flask app on the proxy instance
        commands = [
            "nohup python3 proxy_script.py > proxy_output.log 2>&1 &",
        ]
        self.execute_commands(commands, [self.proxy_instance])

    def start_trusted_host_app(self) -> None:
        # Start the Flask app on the trusted host instance
        commands = [
            "nohup python3 trusted_host_script.py > trusted_host_output.log 2>&1 &",
        ]
        self.execute_commands(commands, [self.trusted_host_instance])

    def start_gatekeeper_app(self) -> None:
        # Start the Flask app on the gatekeeper instance
        commands = [
            "nohup python3 gatekeeper_script.py > gatekeeper_output.log 2>&1 &",
        ]
        self.execute_commands(commands, [self.gatekeeper_instance])

    def cleanup(self, all_instances):
        """Enhanced cleanup to remove all created resources"""
        try:
            # Terminate instances
            instance_ids = [i.instance.id for i in all_instances]
            self.ec2_client.terminate_instances(InstanceIds=instance_ids)
            
            waiter = self.ec2_client.get_waiter('instance_terminated')
            waiter.wait(InstanceIds=instance_ids)
            
            # Delete security groups
            for sg_id in [self.cluster_security_group_id, self.proxy_security_group_id,
                         self.trusted_host_security_group_id, self.gatekeeper_security_group_id]:
                self.ec2_client.delete_security_group(GroupId=sg_id)
            
            # Detach and delete internet gateway
            self.ec2_client.detach_internet_gateway(
                InternetGatewayId=self.igw['InternetGatewayId'],
                VpcId=self.vpc_id
            )
            self.ec2_client.delete_internet_gateway(
                InternetGatewayId=self.igw['InternetGatewayId']
            )
            
            # Delete route table
            self.ec2_client.delete_route_table(
                RouteTableId=self.route_table['RouteTableId']
            )
            
            # Delete subnet
            self.ec2_client.delete_subnet(
                SubnetId=self.subnet['SubnetId']
            )
            
            # Delete VPC
            self.ec2_client.delete_vpc(VpcId=self.vpc_id)
            
            # Delete key pair
            self.ec2_client.delete_key_pair(KeyName=self.key_name)
            os.remove(self.ssh_key_path)
            
        except ClientError as e:
            print(f"An error occurred during cleanup: {e}")
            
    def _get_latest_ubuntu_ami(self):
        """
        Get the latest Ubuntu AMI ID.
        """
        response = self.ec2_client.describe_images(
            Filters=[
                {
                    "Name": "name",
                    "Values": [
                        "ubuntu/images/hvm-ssd/ubuntu-focal-20.04-amd64-server-*"
                    ],
                },
                {"Name": "virtualization-type", "Values": ["hvm"]},
                {"Name": "architecture", "Values": ["x86_64"]},
            ],
            Owners=["099720109477"],  # Canonical
        )
        images = response["Images"]
        images.sort(key=lambda x: x["CreationDate"], reverse=True)
        return images[0]["ImageId"]


# Main

# Launch instances
ec2_manager = EC2Manager()

# Clear data folder
os.system("rm -rf data")
os.system("mkdir data")

ec2_manager.create_key_pair()
time.sleep(5)
all_instances = ec2_manager.launch_instances()

# Wait for instances to be running
print("Waiting for instances to be running...")
for ec2_instance in all_instances:
    ec2_instance.instance.wait_until_running()
    ec2_instance.instance.reload()
    print(f"Instance {ec2_instance.get_name()} is running.")

print("All instances are running.")
time.sleep(10)

ec2_manager.add_inbound_rules()

# Save manager and worker ips to a JSON file
instance_data_ip = {}
for ec2_instance in all_instances:
    instance_data_ip[ec2_instance.name] = ec2_instance.instance.public_ip_address
sql_instances = []
sql_instances.append(ec2_manager.manager_instance)
sql_instances.extend(ec2_manager.worker_instances)

instance_data = {
    instance.name: {
        "instance_id": instance.instance.id
    }
    for instance in sql_instances
}

with open("instance_info.json", "w") as f:
    json.dump(instance_data, f, indent=4)

with open("public_ips.json", "w") as file:
    json.dump(instance_data_ip, file, indent=4)

print("Installing cluster dependencies...")
ec2_manager.install_cluster_dependencies()

print("Installing proxy dependencies...")
ec2_manager.install_network_instances_dependencies()

print("Running sysbench...")
ec2_manager.run_sys_bench()

print("Saving sysbench results...")
ec2_manager.save_sys_bench_results()

print("Uploading Flask apps to instances...")
ec2_manager.upload_flask_apps_to_instances()

print("Starting Flask apps for the manager and workers...")
ec2_manager.start_db_cluster_apps()

print("Starting Flask app for the proxy...")
ec2_manager.start_proxy_app()

print("Starting Flask app for the trusted host...")
ec2_manager.start_trusted_host_app()

print("Starting Flask app for the gatekeeper...")
ec2_manager.start_gatekeeper_app()

# Cleanup
'''
press_touched = input("Press any key to terminate and cleanup: ")
ec2_manager.cleanup(all_instances)
print("Cleanup complete.")
'''