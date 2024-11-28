# gatekeeper_setup.py
def get_gatekeeper_setup_script():
    return """#!/bin/bash
apt-get update
apt-get install -y python3-pip
pip3 install flask requests

cat > /home/ubuntu/gatekeeper.py << 'EOL'
from flask import Flask, request, jsonify
import requests
import re

app = Flask(__name__)

TRUSTED_HOST = "TRUSTED_HOST_IP:5000"

def validate_query(query):
    # Basic SQL injection prevention
    dangerous_patterns = [
        r'--',
        r';.*$',
        r'/\*.*\*/',
        r'UNION.*SELECT',
        r'DROP.*TABLE',
        r'DELETE.*FROM',
        r'INSERT.*INTO',
        r'UPDATE.*SET'
    ]
    
    query = query.upper()
    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return False
    return True

@app.route('/query', methods=['POST'])
def handle_query():
    query = request.json.get('query', '')
    strategy = request.json.get('strategy', 'direct')
    
    if not validate_query(query):
        return jsonify({
            'success': False,
            'error': 'Invalid query detected'
        }), 400
        
    try:
        response = requests.post(
            f'http://{TRUSTED_HOST}/query',
            json={'query': query, 'strategy': strategy}
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
ufw allow 5000/tcp
ufw allow 22/tcp
ufw enable

python3 /home/ubuntu/gatekeeper.py &
"""