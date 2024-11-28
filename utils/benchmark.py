import requests
import time
import json
import concurrent.futures
import pandas as pd

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

def run_benchmark(gatekeeper_ip, num_requests=1000):
    url = f"http://{gatekeeper_ip}:5000/query"
    
    read_query = "SELECT * FROM actor LIMIT 1;"
    write_query = "INSERT INTO actor (first_name, last_name) VALUES ('Test', 'User');"
    
    results = []
    
    # Run parallel requests
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        # Read requests
        read_futures = [
            executor.submit(send_request, url, read_query, False)
            for _ in range(num_requests)
        ]
        
        # Write requests
        write_futures = [
            executor.submit(send_request, url, write_query, True)
            for _ in range(num_requests)
        ]
        
        # Collect results
        for future in concurrent.futures.as_completed(read_futures + write_futures):
            results.append(future.result())
    
    # Analyze results
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

# Test each proxy mode
def test_all_modes(gatekeeper_ip):
    modes = ["DIRECT_HIT", "RANDOM", "CUSTOMIZED"]
    results = {}
    
    for mode in modes:
        # Set mode
        requests.post(f"http://{gatekeeper_ip}:5000/mode", json={"mode": mode})
        
        # Run benchmark
        results[mode] = run_benchmark(gatekeeper_ip)
        
        print(f"\nResults for {mode} mode:")
        print(f"Read requests: {results[mode]['read']}")
        print(f"Write requests: {results[mode]['write']}")
    
    return results

if __name__ == "__main__":
    with open("public_ips.json", "r") as f:
        ips = json.load(f)
    
    results = test_all_modes(ips["gatekeeper"])
    
    # Save results
    with open("benchmark_results.json", "w") as f:
        json.dump(results, f, indent=4)