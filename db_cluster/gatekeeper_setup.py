# gatekeeper_setup.py
def get_gatekeeper_setup_script():
    return """#!/bin/bash
apt-get update
apt-get install -y python3-pip
pip3 install flask requests cors

cat > /home/ubuntu/gatekeeper.py << 'EOL'
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re

app = Flask(__name__)
CORS(app)

TRUSTED_HOST = "TRUSTED_HOST_IP:5000"

def validate_query(query):
    # Basic SQL injection prevention
    dangerous_patterns = [
        r'--',
        r';.*$',
        r'/\*.*\*/',
        r'DROP.*TABLE',
        r'DELETE.*FROM'
    ]
    
    query = query.upper()
    for pattern in dangerous_patterns:
        if re.search(pattern, query, re.IGNORECASE):
            return False
    return True

@app.route('/query', methods=['POST', 'OPTIONS'])
def handle_query():
    if request.method == 'OPTIONS':
        return '', 204
    
    if not request.is_json:
        return jsonify({'success': False, 'error': 'Expected JSON'}), 400
        
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
            json={'query': query, 'strategy': strategy},
            timeout=30
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
echo "y" | ufw enable

python3 /home/ubuntu/gatekeeper.py &
"""