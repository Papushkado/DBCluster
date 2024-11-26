import boto3

def create_security_group(ec2_client, vpc_id, group_name, description):
    response = ec2_client.create_security_group(GroupName=group_name, Description=description, VpcId=vpc_id)
    sg_id = response['GroupId']
    print(f"Security Group OK with ID: {sg_id}")
    return sg_id

def configure_security_group(ec2_client, sg_id):
    # Traffic SSH (port 22) et MySQL (port 3306)
    ec2_client.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[
            {'IpProtocol': 'tcp', 'FromPort': 22, 'ToPort': 22, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]},  
            {'IpProtocol': 'tcp', 'FromPort': 3306, 'ToPort': 3306, 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}  
        ]
    )
    print(f"Security Rules ok for the SG ID: {sg_id}")