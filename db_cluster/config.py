# config.py
from dataclasses import dataclass

@dataclass
class AWSConfig:
    region = "us-west-2"
    ami_id = "ami-0735c191cf914754d"  # Ubuntu 20.04 LTS
    instance_types = {
        "mysql": "t2.micro",
        "proxy": "t2.large",
        "gatekeeper": "t2.large",
        "trusted_host": "t2.large"
    }
    key_name = "db-cluster-key"
    key_path = None  # Will be set in main.py
    
@dataclass
class MySQLConfig:
    user = "admin"
    password = "your-secure-password"
    database = "sakila"
    port = 3306