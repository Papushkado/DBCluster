import boto3
import time
import datetime
import matplotlib.pyplot as plt
import requests

def create_instance():
   ec2 = boto3.resource('ec2')
   instance = ec2.create_instances(
       ImageId='ami-0440d3b780d96b29d', # Amazon Linux 2 AMI
       InstanceType='t2.micro',
       MinCount=1,
       MaxCount=1,
       Monitoring={'Enabled': True},
   )[0]
   
   instance.wait_until_running()
   instance.load()
   return instance

def ping_instance(ip_address, num_pings=100):
   for _ in range(num_pings):
       try:
           requests.get(f"http://{ip_address}", timeout=1)
       except:
           pass
       time.sleep(0.1)

def get_cpu_metrics(instance_id):
   cloudwatch = boto3.client('cloudwatch')
   end_time = datetime.datetime.utcnow()
   start_time = end_time - datetime.timedelta(minutes=30)
   
   metrics = cloudwatch.get_metric_statistics(
       Namespace='AWS/EC2',
       MetricName='CPUUtilization',
       Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
       StartTime=start_time,
       EndTime=end_time,
       Period=60,
       Statistics=['Average']
   )
   
   return metrics['Datapoints']

def plot_metrics(datapoints):
   times = [d['Timestamp'] for d in sorted(datapoints, key=lambda x: x['Timestamp'])]
   cpu = [d['Average'] for d in sorted(datapoints, key=lambda x: x['Timestamp'])]
   
   plt.figure(figsize=(10,6))
   plt.plot(times, cpu)
   plt.title('CPU Utilization')
   plt.xlabel('Time')
   plt.ylabel('CPU %')
   plt.grid(True)
   plt.savefig('cpu_metrics.png')
   plt.close()

if __name__ == "__main__":
   instance = create_instance()
   print(f"Instance ID: {instance.id}")
   print(f"Public IP: {instance.public_ip_address}")
   
   time.sleep(60)  # Attendre que l'instance soit prête
   ping_instance(instance.public_ip_address)
   time.sleep(300)  # Attendre que les métriques soient disponibles
   
   metrics = get_cpu_metrics(instance.id)
   print(f"Retrieved {len(metrics)} datapoints")
   plot_metrics(metrics)
   
   # Cleanup
   instance.terminate()