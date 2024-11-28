# mysql_setup.py
from config import MySQLConfig

def get_mysql_setup_script(is_manager=False):
    return f"""#!/bin/bash
apt-get update
apt-get install -y mysql-server sysbench
systemctl start mysql
systemctl enable mysql

# Configure MySQL
mysql -e "CREATE USER '{MySQLConfig.user}'@'%' IDENTIFIED BY '{MySQLConfig.password}'"
mysql -e "GRANT ALL PRIVILEGES ON *.* TO '{MySQLConfig.user}'@'%'"
mysql -e "FLUSH PRIVILEGES"

# Download and install Sakila
wget https://downloads.mysql.com/docs/sakila-db.tar.gz
tar xvf sakila-db.tar.gz
mysql -e "SOURCE sakila-db/sakila-schema.sql"
mysql -e "SOURCE sakila-db/sakila-data.sql"

# Configure MySQL for replication if manager
{"" if not is_manager else '''
echo "
server-id=1
log_bin=/var/log/mysql/mysql-bin.log
binlog_format=ROW
" >> /etc/mysql/my.cnf
systemctl restart mysql
'''}
"""