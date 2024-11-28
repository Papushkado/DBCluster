# trusted_host_setup.py
def get_trusted_host_setup_script():
    return """#!/bin/bash
apt-get update
apt-get install -y python3-pip
pip3 install flask requests

cat > /home/ubuntu/trusted_host.py << 'EOL'
from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

PROXY_HOST = "PROXY_IP:5000"

@app.route('/query', methods=['POST'])
def handle_query():
    try:
        response = requests.post(
            f'http://{PROXY_HOST}/query',
            json=request.json
        )
        return response.json()
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
EOL

# Configure firewall
ufw default deny incoming
ufw allow from GATEKEEPER_IP to any port 5000
ufw allow 22/tcp
ufw enable

python3 /home/ubuntu/trusted_host.py &
"""