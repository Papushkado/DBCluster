import boto3 

def create_vpc(ec2_client):
    response = ec2_client.create_vpc(CidrBlock='10.0.0.0/16')
    vpc_id = response['Vpc']['VpcId']
    ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsSupport={'Value': True})
    ec2_client.modify_vpc_attribute(VpcId=vpc_id, EnableDnsHostnames={'Value': True})
    print(f"VPC OK with ID: {vpc_id}")
    return vpc_id

def create_subnet(ec2_client, vpc_id, cidr_block, availability_zone):
    response = ec2_client.create_subnet(VpcId=vpc_id, CidrBlock=cidr_block, AvailabilityZone=availability_zone)
    subnet_id = response['Subnet']['SubnetId']
    print(f"Subnet OK with ID: {subnet_id}")
    return subnet_id

def create_internet_gateway(ec2_client, vpc_id):
    # Créer une gateway Internet et l'attacher au VPC
    response = ec2_client.create_internet_gateway()
    igw_id = response['InternetGateway']['InternetGatewayId']
    ec2_client.attach_internet_gateway(InternetGatewayId=igw_id, VpcId=vpc_id)
    print(f"IGW OK witch ID: {igw_id}")
    return igw_id

def create_route_table(ec2_client, vpc_id, igw_id, subnet_id):
    response = ec2_client.create_route_table(VpcId=vpc_id)
    route_table_id = response['RouteTable']['RouteTableId']
    ec2_client.create_route(RouteTableId=route_table_id, DestinationCidrBlock='0.0.0.0/0', GatewayId=igw_id)
    ec2_client.associate_route_table(RouteTableId=route_table_id, SubnetId=subnet_id)
    print(f"Route table ok with ID: {route_table_id}")