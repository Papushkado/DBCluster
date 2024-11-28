# proxy_setup.py
def get_proxy_setup_script():
    return """#!/bin/bash
apt-get update
apt-get install -y python3-pip
pip3 install flask mysql-connector-python requests

cat > /home/ubuntu/proxy.py << 'EOL'
from flask import Flask, request, jsonify
import mysql.connector
import random
import subprocess
import json

app = Flask(__name__)

MYSQL_NODES = {
    "manager": "MANAGER_IP",
    "workers": ["WORKER1_IP", "WORKER2_IP"]
}

def get_connection(host):
    return mysql.connector.connect(
        host=host,
        user="admin",
        password="your-secure-password",
        database="sakila"
    )

def measure_ping(host):
    result = subprocess.run(['ping', '-c', '1', host], capture_output=True, text=True)
    if result.returncode == 0:
        return float(result.stdout.split('time=')[1].split()[0])
    return float('inf')

@app.route('/query', methods=['POST'])
def handle_query():
    query = request.json.get('query', '').upper()
    strategy = request.json.get('strategy', 'direct')
    
    if any(word in query for word in ['SELECT', 'SHOW', 'DESCRIBE']):
        if strategy == 'direct':
            host = MYSQL_NODES['manager']
        elif strategy == 'random':
            host = random.choice(MYSQL_NODES['workers'])
        else:  # customized - ping-based
            ping_times = {
                host: measure_ping(host) 
                for host in MYSQL_NODES['workers']
            }
            host = min(ping_times.items(), key=lambda x: x[1])[0]
    else:
        # Write operations always go to manager
        host = MYSQL_NODES['manager']
    
    try:
        conn = get_connection(host)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query)
        
        if query.startswith(('INSERT', 'UPDATE', 'DELETE')):
            conn.commit()
            # Replicate to workers
            for worker in MYSQL_NODES['workers']:
                worker_conn = get_connection(worker)
                worker_cursor = worker_conn.cursor()
                worker_cursor.execute(query)
                worker_conn.commit()
                worker_cursor.close()
                worker_conn.close()
        
        results = cursor.fetchall() if not query.startswith(('INSERT', 'UPDATE', 'DELETE')) else None
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'results': results,
            'host': host
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'host': host
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOL

python3 /home/ubuntu/proxy.py &
"""