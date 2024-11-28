# main.py
import sys
import signal
import os
from infrastructure import CloudInfrastructure
from mysql_setup import get_mysql_setup_script
from proxy_setup import get_proxy_setup_script
from gatekeeper_setup import get_gatekeeper_setup_script
from trusted_host_setup import get_trusted_host_setup_script
from benchmark import run_benchmark
from config import AWSConfig

def signal_handler(signum, frame):
    print("\nInterruption détectée. Nettoyage des ressources...")
    if 'infra' in globals():
        infra.cleanup()
    sys.exit(0)

def main():
    global infra
    try:
        # Configure signal handlers
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Create keys directory in user's home directory
        home_dir = os.path.expanduser(".")
        keys_dir = os.path.join(home_dir, "aws_keys")
        os.makedirs(keys_dir, exist_ok=True)
        
        # Update key path in AWSConfig
        AWSConfig.key_path = os.path.join(keys_dir, "db-cluster-key.pem")

        infra = CloudInfrastructure()
        
        # Test AWS connection first
        try:
            infra.ec2.describe_regions()
        except Exception as e:
            print("Erreur de connexion AWS. Vérifiez vos credentials.")
            print(f"Erreur: {str(e)}")
            return

        # Create security groups
        print("Creating security groups...")
        mysql_sg = infra.create_security_group("mysql-sg-2", "MySQL security group", [
            {
                'IpProtocol': 'tcp',
                'FromPort': 3306,
                'ToPort': 3306,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
            }
        ])
        if not mysql_sg:
            print("Failed to create MySQL security group")
            return

        proxy_sg = infra.create_security_group("proxy-sg-2", "Proxy security group", [
            {
                'IpProtocol': 'tcp',
                'FromPort': 5000,
                'ToPort': 5000,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
            }
        ])
        if not proxy_sg:
            print("Failed to create Proxy security group")
            return

        gatekeeper_sg = infra.create_security_group("gatekeeper-sg-2", "Gatekeeper security group", [
            {
                'IpProtocol': 'tcp',
                'FromPort': 5000,
                'ToPort': 5000,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
            }
        ])
        if not gatekeeper_sg:
            print("Failed to create Gatekeeper security group")
            return

        trusted_host_sg = infra.create_security_group("trusted-host-sg-2", "Trusted host security group", [
            {
                'IpProtocol': 'tcp',
                'FromPort': 5000,
                'ToPort': 5000,
                'IpRanges': [{'CidrIp': '0.0.0.0/0'}]
            }
        ])
        if not trusted_host_sg:
            print("Failed to create Trusted Host security group")
            return

        # Create MySQL instances
        print("Creating MySQL manager instance...")
        mysql_manager = infra.create_instance(
            "mysql-manager",
            AWSConfig.instance_types['mysql'],
            [mysql_sg],
            get_mysql_setup_script(is_manager=True)
        )
        if not mysql_manager:
            print("Failed to create MySQL manager instance")
            return
    
        print("Creating MySQL worker instances...")
        mysql_worker1 = infra.create_instance(
            "mysql-worker1",
            AWSConfig.instance_types['mysql'],
            [mysql_sg],
            get_mysql_setup_script()
        )
        if not mysql_worker1:
            print("Failed to create MySQL worker1 instance")
            return
    
        mysql_worker2 = infra.create_instance(
            "mysql-worker2",
            AWSConfig.instance_types['mysql'],
            [mysql_sg],
            get_mysql_setup_script()
        )
        if not mysql_worker2:
            print("Failed to create MySQL worker2 instance")
            return
    
        # Get MySQL IPs
        print("Getting MySQL instances IPs...")
        manager_ip = infra.get_instance_ip(mysql_manager)
        worker1_ip = infra.get_instance_ip(mysql_worker1)
        worker2_ip = infra.get_instance_ip(mysql_worker2)
        
        if not all([manager_ip, worker1_ip, worker2_ip]):
            print("Failed to get MySQL instances IPs")
            return
    
        print("Creating Proxy instance...")
        # Create Proxy instance
        proxy_script = get_proxy_setup_script().replace('MANAGER_IP', manager_ip)\
                                             .replace('WORKER1_IP', worker1_ip)\
                                             .replace('WORKER2_IP', worker2_ip)
    
        proxy = infra.create_instance(
            "proxy",
            AWSConfig.instance_types['proxy'],
            [proxy_sg],
            proxy_script
        )
        if not proxy:
            print("Failed to create Proxy instance")
            return
    
        print("Getting Proxy instance IP...")
        proxy_ip = infra.get_instance_ip(proxy)
        if not proxy_ip:
            print("Failed to get Proxy instance IP")
            return
    
        print("Creating Trusted Host instance...")
        # Create Trusted Host instance
        trusted_host_script = get_trusted_host_setup_script().replace('PROXY_IP', proxy_ip)
    
        trusted_host = infra.create_instance(
            "trusted-host",
            AWSConfig.instance_types['trusted_host'],
            [trusted_host_sg],
            trusted_host_script
        )
        if not trusted_host:
            print("Failed to create Trusted Host instance")
            return
    
        print("Getting Trusted Host instance IP...")
        trusted_host_ip = infra.get_instance_ip(trusted_host)
        if not trusted_host_ip:
            print("Failed to get Trusted Host instance IP")
            return
    
        print("Creating Gatekeeper instance...")
        # Create Gatekeeper instance
        gatekeeper_script = get_gatekeeper_setup_script().replace('TRUSTED_HOST_IP', trusted_host_ip)
    
        gatekeeper = infra.create_instance(
            "gatekeeper",
            AWSConfig.instance_types['gatekeeper'],
            [gatekeeper_sg],
            gatekeeper_script
        )
        if not gatekeeper:
            print("Failed to create Gatekeeper instance")
            return
    
        print("Getting Gatekeeper instance IP...")
        gatekeeper_ip = infra.get_instance_ip(gatekeeper)
        if not gatekeeper_ip:
            print("Failed to get Gatekeeper instance IP")
            return
    
        print("\nInfrastructure setup complete!")
        print(f"Gatekeeper IP: {gatekeeper_ip}")
        print(f"Trusted Host IP: {trusted_host_ip}")
        print(f"Proxy IP: {proxy_ip}")
        print(f"MySQL Manager IP: {manager_ip}")
        print(f"MySQL Worker 1 IP: {worker1_ip}")
        print(f"MySQL Worker 2 IP: {worker2_ip}")
        
        # Save IPs to a file for future reference
        with open(os.path.join(home_dir, "db_cluster_ips.txt"), "w") as f:
            f.write(f"Gatekeeper IP: {gatekeeper_ip}\n")
            f.write(f"Trusted Host IP: {trusted_host_ip}\n")
            f.write(f"Proxy IP: {proxy_ip}\n")
            f.write(f"MySQL Manager IP: {manager_ip}\n")
            f.write(f"MySQL Worker 1 IP: {worker1_ip}\n")
            f.write(f"MySQL Worker 2 IP: {worker2_ip}\n")
            f.write(f"\nSSH Key path: {AWSConfig.key_path}\n")
        print("\nStarting benchmarks...")
        benchmark_results = run_benchmark(gatekeeper_ip)
    
        print("\nBenchmark Results:")
        for strategy, results in benchmark_results.items():
            print(f"\nStrategy: {strategy}")
            print("Read Operations:")
            print(f"  Average: {results['read']['avg']:.3f}s")
            print(f"  Median: {results['read']['median']:.3f}s")
            print(f"  Min: {results['read']['min']:.3f}s")
            print(f"  Max: {results['read']['max']:.3f}s")
        
            print("Write Operations:")
            print(f"  Average: {results['write']['avg']:.3f}s")
            print(f"  Median: {results['write']['median']:.3f}s")
            print(f"  Min: {results['write']['min']:.3f}s")
            print(f"  Max: {results['write']['max']:.3f}s")
    except Exception as e:
        print(f"Une erreur s'est produite: {str(e)}")
        #infra.cleanup()
        raise

if __name__ == "__main__":
    main()