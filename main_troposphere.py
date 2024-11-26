from troposphere import Template, Ref, Output, GetAtt, Base64, Join
from troposphere.ec2 import Instance, SecurityGroup, SecurityGroupRule

def create_template():
    template = Template()
    template.set_description("MySQL Cluster with Proxy and Gatekeeper patterns")

    # Create Security Groups
    mysql_sg = template.add_resource(SecurityGroup(
        "MySQLSecurityGroup",
        GroupDescription="Allow MySQL access",
        SecurityGroupIngress=[
            SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="3306",
                ToPort="3306",
                CidrIp="0.0.0.0/0"
            ),
            SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="22",
                ToPort="22",
                CidrIp="0.0.0.0/0"
            )
        ]
    ))

    proxy_sg = template.add_resource(SecurityGroup(
        "ProxySecurityGroup",
        GroupDescription="Security group for Proxy instance",
        SecurityGroupIngress=[
            SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="80",
                ToPort="80",
                CidrIp="0.0.0.0/0"
            ),
            SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="22",
                ToPort="22",
                CidrIp="0.0.0.0/0"
            )
        ]
    ))

    gatekeeper_sg = template.add_resource(SecurityGroup(
        "GatekeeperSecurityGroup",
        GroupDescription="Security group for Gatekeeper instance",
        SecurityGroupIngress=[
            SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="80",
                ToPort="80",
                CidrIp="0.0.0.0/0"
            ),
            SecurityGroupRule(
                IpProtocol="tcp",
                FromPort="22",
                ToPort="22",
                CidrIp="0.0.0.0/0"
            )
        ]
    ))

    # MySQL Manager Instance
    mysql_manager = template.add_resource(Instance(
        "MySQLManager",
        ImageId="ami-0aa2b7722dc1b5612",  # Ubuntu 20.04 LTS AMI ID for us-east-1
        InstanceType="t2.micro",
        SecurityGroups=[Ref(mysql_sg)],
        IamInstanceProfile="LabRole",  # Using the LabRole
        UserData=Base64(Join('\n', [
            "#!/bin/bash",
            "apt-get update",
            "apt-get install -y mysql-server",
            # Install Sakila database
            "wget https://downloads.mysql.com/docs/sakila-db.tar.gz",
            "tar -xzf sakila-db.tar.gz",
            "mysql -u root < sakila-db/sakila-schema.sql",
            "mysql -u root < sakila-db/sakila-data.sql",
            # Install sysbench
            "apt-get install -y sysbench"
        ]))
    ))

    # MySQL Worker Instances
    for i in range(2):
        worker = template.add_resource(Instance(
            f"MySQLWorker{i+1}",
            ImageId="ami-0aa2b7722dc1b5612",  # Ubuntu 20.04 LTS AMI ID for us-east-1
            InstanceType="t2.micro",
            SecurityGroups=[Ref(mysql_sg)],
            IamInstanceProfile="LabRole",  # Using the LabRole
            UserData=Base64(Join('\n', [
                "#!/bin/bash",
                "apt-get update",
                "apt-get install -y mysql-server",
                # Install Sakila database
                "wget https://downloads.mysql.com/docs/sakila-db.tar.gz",
                "tar -xzf sakila-db.tar.gz",
                "mysql -u root < sakila-db/sakila-schema.sql",
                "mysql -u root < sakila-db/sakila-data.sql",
                # Install sysbench
                "apt-get install -y sysbench"
            ]))
        ))

    # Proxy Instance
    proxy_instance = template.add_resource(Instance(
        "ProxyInstance",
        ImageId="ami-0aa2b7722dc1b5612",  # Ubuntu 20.04 LTS AMI ID for us-east-1
        InstanceType="t2.large",
        SecurityGroups=[Ref(proxy_sg)],
        IamInstanceProfile="LabRole",  # Using the LabRole
        UserData=Base64(Join('\n', [
            "#!/bin/bash",
            "apt-get update",
            "apt-get install -y python3 python3-pip",
            "pip3 install mysql-connector-python"
        ]))
    ))

    # Gatekeeper Instance
    gatekeeper_instance = template.add_resource(Instance(
        "GatekeeperInstance",
        ImageId="ami-0aa2b7722dc1b5612",  # Ubuntu 20.04 LTS AMI ID for us-east-1
        InstanceType="t2.large",
        SecurityGroups=[Ref(gatekeeper_sg)],
        IamInstanceProfile="LabRole",  # Using the LabRole
        UserData=Base64(Join('\n', [
            "#!/bin/bash",
            "apt-get update",
            "apt-get install -y python3 python3-pip nginx",
            "ufw enable",
            "ufw allow 80",
            "ufw allow 22",
            "ufw deny default"
        ]))
    ))

    # Trusted Host Instance
    trusted_host = template.add_resource(Instance(
        "TrustedHostInstance",
        ImageId="ami-0aa2b7722dc1b5612",  # Ubuntu 20.04 LTS AMI ID for us-east-1
        InstanceType="t2.large",
        SecurityGroups=[Ref(gatekeeper_sg)],
        IamInstanceProfile="LabRole",  # Using the LabRole
        UserData=Base64(Join('\n', [
            "#!/bin/bash",
            "apt-get update",
            "apt-get install -y python3 python3-pip",
            "ufw enable",
            "ufw allow 22",
            "ufw deny default"
        ]))
    ))

    # Add outputs
    template.add_output(Output(
        "MySQLManagerIP",
        Description="IP address of MySQL Manager",
        Value=GetAtt(mysql_manager, "PublicIp")
    ))

    template.add_output(Output(
        "ProxyIP",
        Description="IP address of Proxy Instance",
        Value=GetAtt(proxy_instance, "PublicIp")
    ))

    template.add_output(Output(
        "GatekeeperIP",
        Description="IP address of Gatekeeper Instance",
        Value=GetAtt(gatekeeper_instance, "PublicIp")
    ))

    return template

if __name__ == "__main__":
    template = create_template()
    save = template.to_yaml()
    with open("cloudformation_template.yaml", "w") as f:
        f.write(save)
    
