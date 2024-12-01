import requests
import time
import json
import concurrent.futures
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import boto3

def send_request(url, query, is_write=False):
   try:
       start_time = time.time()
       response = requests.post(url, json={"query": query})
       end_time = time.time()
       
       return {
           "success": response.status_code == 200,
           "time": end_time - start_time,
           "type": "write" if is_write else "read"
       }
   except Exception as e:
       return {
           "success": False,
           "time": 0,
           "error": str(e),
           "type": "write" if is_write else "read"
       }

def get_cpu_utilization(instance_id, start_time, end_time):
  cloudwatch = boto3.client('cloudwatch', region_name='us-east-1')
  response = cloudwatch.get_metric_statistics(
      Namespace='AWS/EC2',
      MetricName='CPUUtilization',
      Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
      StartTime=start_time - datetime.timedelta(minutes=1),
      EndTime=end_time + datetime.timedelta(minutes=2),
      Period=20,  # Période de 20 secondes
      Statistics=['Average']
  )
  return response['Datapoints']

def run_benchmark(gatekeeper_ip, num_requests=1000):
   url = f"http://{gatekeeper_ip}:5000/query"
   
   read_query = "SELECT * FROM actor LIMIT 1;"
   write_query = "INSERT INTO actor (first_name, last_name) VALUES ('Test', 'User');"
   
   results = []
   time.sleep(1) #temps d'attente entre les tests
   
   with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
       read_futures = [
           executor.submit(send_request, url, read_query, False)
           for _ in range(num_requests)
       ]
       
       write_futures = [
           executor.submit(send_request, url, write_query, True)
           for _ in range(num_requests)
       ]
       
       for future in concurrent.futures.as_completed(read_futures + write_futures):
           results.append(future.result())
   
   df = pd.DataFrame(results)
   
   analysis = {
       "read": {
           "avg_time": df[df["type"] == "read"]["time"].mean(),
           "success_rate": (df[df["type"] == "read"]["success"].sum() / num_requests) * 100
       },
       "write": {
           "avg_time": df[df["type"] == "write"]["time"].mean(),
           "success_rate": (df[df["type"] == "write"]["success"].sum() / num_requests) * 100
        }
    }
   return analysis

def run_benchmark_with_monitoring(gatekeeper_ip, instances, mode):
    plt.switch_backend('Agg')
    
    # Commencer à mesurer avant le benchmark
    start_time = datetime.datetime.utcnow()
    time.sleep(60)  
    
    # Exécuter le benchmark avec plus de requêtes
    results = run_benchmark(gatekeeper_ip, num_requests=1000)
    time.sleep(180)  # attendre pour cloudwatch
    
    end_time = datetime.datetime.utcnow()

    cpu_data = {}
    for instance in instances:
        data = get_cpu_utilization(
            instance.instance.id, 
            start_time, 
            end_time
        )
        # Garder uniquement les données pendant le benchmark
        cpu_data[instance.name] = sorted(data, key=lambda x: x['Timestamp'])
        print(f"Retrieved {len(data)} datapoints for {instance.name}")

    # Créer le graphique uniquement s'il y a des données
    if any(len(data) > 0 for data in cpu_data.values()):
        plt.figure(figsize=(12, 6))
        for instance_name, data in cpu_data.items():
            if data:  # Vérifier si nous avons des données pour cette instance
                times = [d['Timestamp'] for d in data]
                cpu = [d['Average'] for d in data]
                plt.plot(times, cpu, label=instance_name)
        
        plt.title(f'CPU Utilization - {mode} Mode')
        plt.xlabel('Time')
        plt.ylabel('CPU Utilization (%)')
        plt.grid(True)
        plt.legend()
        plt.savefig(f'cpu_utilization_{mode}.png')
        plt.close()

    return results

def test_all_modes(gatekeeper_ip, sql_instances):
   modes = ["RANDOM","CUSTOMIZED", "DIRECT_HIT"]
   results = {}
   
   for mode in modes:
       print(f"\nTesting {mode} mode...")
       # Set mode
       requests.post(f"http://{gatekeeper_ip}:5000/mode", json={"mode": mode})
       
       # Run benchmark
       results[mode] = run_benchmark_with_monitoring(gatekeeper_ip, sql_instances, mode)
       print(f"Read requests: {results[mode]['read']}")
       print(f"Write requests: {results[mode]['write']}")
       
   
   return results

if __name__ == "__main__":
   with open("public_ips.json", "r") as f:
       ips = json.load(f)
   
   with open("instance_info.json", "r") as f:
       instance_info = json.load(f)
   
   from collections import namedtuple
   Instance = namedtuple('Instance', ['name', 'instance'])
   InstanceData = namedtuple('InstanceData', ['id'])
   
   sql_instances = []
   for name in ['manager', 'worker1', 'worker2']:
       instance_data = InstanceData(id=instance_info[name]['instance_id'])
       sql_instances.append(Instance(name=name, instance=instance_data))
   
   results = test_all_modes(ips["gatekeeper"], sql_instances)
   
   with open("benchmark_results.json", "w") as f:
       json.dump(results, f, indent=4)