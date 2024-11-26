import boto3
import time


ec2_client = boto3.client('ec2')
rds_client = boto3.client('rds')
iam_client = boto3.client('iam')