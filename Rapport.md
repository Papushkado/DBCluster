# Cloud Design Patterns: Implementing a DB Cluster

Stephen Cohen - 2412336

---


---

# Implementing the infrastructure

## MySQL instances 

The results of the `Sysbench` benchmark on the MySQL instances is available in the appendix. (This the logs that we get)
To experimente this, you can run the code named `deployment_with_benchmark.py`


# Appendix

## MySQL Sysbench

Here are the logs : 

```
[Running] python -u "c:\Users\Stephen\Documents\1_Etudes\Montreal\LOG8145 - Cloud Computing\DBCluster\main.py"
Created key pair and saved to mysql-cluster-key.pem
Created VPC: vpc-0e2dbca33378a5037
Created Subnet: subnet-0ac2309f3e71b4512
Created Security Groups
Created EC2 Instances

Waiting for instances to initialize before running Sysbench tests...

Testing MySQL-Manager (34.206.52.162)

Executing: sudo apt-get update
Hit:1 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal InRelease
Hit:2 http://security.ubuntu.com/ubuntu focal-security InRelease
Hit:3 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-updates InRelease
Hit:4 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-backports InRelease
Reading package lists...



Executing: sudo apt-get install -y sysbench
Reading package lists...
Building dependency tree...
Reading state information...
The following additional packages will be installed:
  libluajit-5.1-2 libluajit-5.1-common libmysqlclient21 libpq5
The following NEW packages will be installed:
  libluajit-5.1-2 libluajit-5.1-common libmysqlclient21 libpq5 sysbench
0 upgraded, 5 newly installed, 0 to remove and 182 not upgraded.
Need to get 1800 kB of archives.
After this operation, 9051 kB of additional disk space will be used.
Get:1 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal/universe amd64 libluajit-5.1-common all 2.1.0~beta3+dfsg-5.1build1 [44.3 kB]
Get:2 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal/universe amd64 libluajit-5.1-2 amd64 2.1.0~beta3+dfsg-5.1build1 [228 kB]
Get:3 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-updates/main amd64 libmysqlclient21 amd64 8.0.40-0ubuntu0.20.04.1 [1304 kB]
Get:4 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-updates/main amd64 libpq5 amd64 12.20-0ubuntu0.20.04.1 [117 kB]
Get:5 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal/universe amd64 sysbench amd64 1.0.18+ds-1 [107 kB]
Fetched 1800 kB in 0s (37.5 MB/s)
Selecting previously unselected package libluajit-5.1-common.

(Reading database ... 
(Reading database ... 5%
(Reading database ... 10%
(Reading database ... 15%
(Reading database ... 20%
(Reading database ... 25%
(Reading database ... 30%
(Reading database ... 35%
(Reading database ... 40%
(Reading database ... 45%
(Reading database ... 50%
(Reading database ... 55%
(Reading database ... 60%
(Reading database ... 65%
(Reading database ... 70%
(Reading database ... 75%
(Reading database ... 80%
(Reading database ... 85%
(Reading database ... 90%
(Reading database ... 95%
(Reading database ... 100%
(Reading database ... 62513 files and directories currently installed.)

Preparing to unpack .../libluajit-5.1-common_2.1.0~beta3+dfsg-5.1build1_all.deb ...

Unpacking libluajit-5.1-common (2.1.0~beta3+dfsg-5.1build1) ...

Selecting previously unselected package libluajit-5.1-2:amd64.

Preparing to unpack .../libluajit-5.1-2_2.1.0~beta3+dfsg-5.1build1_amd64.deb ...

Unpacking libluajit-5.1-2:amd64 (2.1.0~beta3+dfsg-5.1build1) ...

Selecting previously unselected package libmysqlclient21:amd64.

Preparing to unpack .../libmysqlclient21_8.0.40-0ubuntu0.20.04.1_amd64.deb ...

Unpacking libmysqlclient21:amd64 (8.0.40-0ubuntu0.20.04.1) ...

Selecting previously unselected package libpq5:amd64.

Preparing to unpack .../libpq5_12.20-0ubuntu0.20.04.1_amd64.deb ...

Unpacking libpq5:amd64 (12.20-0ubuntu0.20.04.1) ...

Selecting previously unselected package sysbench.

Preparing to unpack .../sysbench_1.0.18+ds-1_amd64.deb ...

Unpacking sysbench (1.0.18+ds-1) ...

Setting up libmysqlclient21:amd64 (8.0.40-0ubuntu0.20.04.1) ...

Setting up libpq5:amd64 (12.20-0ubuntu0.20.04.1) ...

Setting up libluajit-5.1-common (2.1.0~beta3+dfsg-5.1build1) ...

Setting up libluajit-5.1-2:amd64 (2.1.0~beta3+dfsg-5.1build1) ...

Setting up sysbench (1.0.18+ds-1) ...

Processing triggers for man-db (2.9.1-1) ...

Processing triggers for libc-bin (2.31-0ubuntu9.9) ...


debconf: unable to initialize frontend: Dialog
debconf: (Dialog frontend will not work on a dumb terminal, an emacs shell buffer, or without a controlling terminal.)
debconf: falling back to frontend: Readline
debconf: unable to initialize frontend: Readline
debconf: (This frontend requires a controlling tty.)
debconf: falling back to frontend: Teletype
dpkg-preconfigure: unable to re-open stdin: 


Executing: mysql -uroot -proot_password -e 'CREATE DATABASE IF NOT EXISTS sbtest;'

mysql: [Warning] Using a password on the command line interface can be insecure.


Executing: sysbench --db-driver=mysql --mysql-user=root --mysql-password=root_password --mysql-db=sbtest --table-size=10000 --tables=3 /usr/share/sysbench/oltp_read_write.lua prepare
sysbench 1.0.18 (using system LuaJIT 2.1.0-beta3)

Creating table 'sbtest1'...
Inserting 10000 records into 'sbtest1'
Creating a secondary index on 'sbtest1'...
Creating table 'sbtest2'...
Inserting 10000 records into 'sbtest2'
Creating a secondary index on 'sbtest2'...
Creating table 'sbtest3'...
Inserting 10000 records into 'sbtest3'
Creating a secondary index on 'sbtest3'...



Executing: sysbench --db-driver=mysql --mysql-user=root --mysql-password=root_password --mysql-db=sbtest --table-size=10000 --tables=3 --threads=6 --time=60 --report-interval=10 /usr/share/sysbench/oltp_read_write.lua run
sysbench 1.0.18 (using system LuaJIT 2.1.0-beta3)

Running the test with following options:
Number of threads: 6
Report intermediate results every 10 second(s)
Initializing random number generator from current time


Initializing worker threads...

Threads started!

[ 10s ] thds: 6 tps: 313.01 qps: 6271.21 (r/w/o: 4390.55/1254.04/626.62) lat (ms,95%): 27.66 err/s: 0.00 reconn/s: 0.00
[ 20s ] thds: 6 tps: 319.42 qps: 6388.70 (r/w/o: 4471.81/1278.06/638.83) lat (ms,95%): 27.17 err/s: 0.00 reconn/s: 0.00
[ 30s ] thds: 6 tps: 318.51 qps: 6367.88 (r/w/o: 4457.63/1273.24/637.02) lat (ms,95%): 27.66 err/s: 0.00 reconn/s: 0.00
[ 40s ] thds: 6 tps: 318.00 qps: 6361.03 (r/w/o: 4453.32/1271.71/636.00) lat (ms,95%): 27.17 err/s: 0.00 reconn/s: 0.00
[ 50s ] thds: 6 tps: 331.00 qps: 6621.29 (r/w/o: 4634.19/1325.10/662.00) lat (ms,95%): 26.20 err/s: 0.00 reconn/s: 0.00
[ 60s ] thds: 6 tps: 327.00 qps: 6537.02 (r/w/o: 4576.92/1306.10/654.00) lat (ms,95%): 26.68 err/s: 0.00 reconn/s: 0.00
SQL statistics:
    queries performed:
        read:                            269864
        write:                           77104
        other:                           38552
        total:                           385520
    transactions:                        19276  (321.09 per sec.)
    queries:                             385520 (6421.85 per sec.)
    ignored errors:                      0      (0.00 per sec.)
    reconnects:                          0      (0.00 per sec.)

General statistics:
    total time:                          60.0304s
    total number of events:              19276

Latency (ms):
         min:                                    3.74
         avg:                                   18.68
         max:                                   73.45
         95th percentile:                       27.17
         sum:                               360035.04

Threads fairness:
    events (avg/stddev):           3212.6667/22.69
    execution time (avg/stddev):   60.0058/0.01




Executing: sysbench --db-driver=mysql --mysql-user=root --mysql-password=root_password --mysql-db=sbtest --table-size=10000 --tables=3 /usr/share/sysbench/oltp_read_write.lua cleanup
sysbench 1.0.18 (using system LuaJIT 2.1.0-beta3)

Dropping table 'sbtest1'...
Dropping table 'sbtest2'...
Dropping table 'sbtest3'...



Testing MySQL-Worker-1 (3.236.166.73)

Executing: sudo apt-get update
Hit:1 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal InRelease
Hit:2 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-updates InRelease
Hit:3 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-backports InRelease
Hit:4 http://security.ubuntu.com/ubuntu focal-security InRelease
Reading package lists...



Executing: sudo apt-get install -y sysbench
Reading package lists...
Building dependency tree...
Reading state information...
The following additional packages will be installed:
  libluajit-5.1-2 libluajit-5.1-common libmysqlclient21 libpq5
The following NEW packages will be installed:
  libluajit-5.1-2 libluajit-5.1-common libmysqlclient21 libpq5 sysbench
0 upgraded, 5 newly installed, 0 to remove and 182 not upgraded.
Need to get 1800 kB of archives.
After this operation, 9051 kB of additional disk space will be used.
Get:1 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal/universe amd64 libluajit-5.1-common all 2.1.0~beta3+dfsg-5.1build1 [44.3 kB]
Get:2 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal/universe amd64 libluajit-5.1-2 amd64 2.1.0~beta3+dfsg-5.1build1 [228 kB]
Get:3 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-updates/main amd64 libmysqlclient21 amd64 8.0.40-0ubuntu0.20.04.1 [1304 kB]
Get:4 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-updates/main amd64 libpq5 amd64 12.20-0ubuntu0.20.04.1 [117 kB]
Get:5 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal/universe amd64 sysbench amd64 1.0.18+ds-1 [107 kB]
Fetched 1800 kB in 0s (36.5 MB/s)
Selecting previously unselected package libluajit-5.1-common.

(Reading database ... 
(Reading database ... 5%
(Reading database ... 10%
(Reading database ... 15%
(Reading database ... 20%
(Reading database ... 25%
(Reading database ... 30%
(Reading database ... 35%
(Reading database ... 40%
(Reading database ... 45%
(Reading database ... 50%
(Reading database ... 55%
(Reading database ... 60%
(Reading database ... 65%
(Reading database ... 70%
(Reading database ... 75%
(Reading database ... 80%
(Reading database ... 85%
(Reading database ... 90%
(Reading database ... 95%
(Reading database ... 100%
(Reading database ... 62513 files and directories currently installed.)

Preparing to unpack .../libluajit-5.1-common_2.1.0~beta3+dfsg-5.1build1_all.deb ...

Unpacking libluajit-5.1-common (2.1.0~beta3+dfsg-5.1build1) ...

Selecting previously unselected package libluajit-5.1-2:amd64.

Preparing to unpack .../libluajit-5.1-2_2.1.0~beta3+dfsg-5.1build1_amd64.deb ...

Unpacking libluajit-5.1-2:amd64 (2.1.0~beta3+dfsg-5.1build1) ...

Selecting previously unselected package libmysqlclient21:amd64.

Preparing to unpack .../libmysqlclient21_8.0.40-0ubuntu0.20.04.1_amd64.deb ...

Unpacking libmysqlclient21:amd64 (8.0.40-0ubuntu0.20.04.1) ...

Selecting previously unselected package libpq5:amd64.

Preparing to unpack .../libpq5_12.20-0ubuntu0.20.04.1_amd64.deb ...

Unpacking libpq5:amd64 (12.20-0ubuntu0.20.04.1) ...

Selecting previously unselected package sysbench.

Preparing to unpack .../sysbench_1.0.18+ds-1_amd64.deb ...

Unpacking sysbench (1.0.18+ds-1) ...

Setting up libmysqlclient21:amd64 (8.0.40-0ubuntu0.20.04.1) ...

Setting up libpq5:amd64 (12.20-0ubuntu0.20.04.1) ...

Setting up libluajit-5.1-common (2.1.0~beta3+dfsg-5.1build1) ...

Setting up libluajit-5.1-2:amd64 (2.1.0~beta3+dfsg-5.1build1) ...

Setting up sysbench (1.0.18+ds-1) ...

Processing triggers for man-db (2.9.1-1) ...

Processing triggers for libc-bin (2.31-0ubuntu9.9) ...


debconf: unable to initialize frontend: Dialog
debconf: (Dialog frontend will not work on a dumb terminal, an emacs shell buffer, or without a controlling terminal.)
debconf: falling back to frontend: Readline
debconf: unable to initialize frontend: Readline
debconf: (This frontend requires a controlling tty.)
debconf: falling back to frontend: Teletype
dpkg-preconfigure: unable to re-open stdin: 


Executing: mysql -uroot -proot_password -e 'CREATE DATABASE IF NOT EXISTS sbtest;'

mysql: [Warning] Using a password on the command line interface can be insecure.


Executing: sysbench --db-driver=mysql --mysql-user=root --mysql-password=root_password --mysql-db=sbtest --table-size=10000 --tables=3 /usr/share/sysbench/oltp_read_write.lua prepare
sysbench 1.0.18 (using system LuaJIT 2.1.0-beta3)

Creating table 'sbtest1'...
Inserting 10000 records into 'sbtest1'
Creating a secondary index on 'sbtest1'...
Creating table 'sbtest2'...
Inserting 10000 records into 'sbtest2'
Creating a secondary index on 'sbtest2'...
Creating table 'sbtest3'...
Inserting 10000 records into 'sbtest3'
Creating a secondary index on 'sbtest3'...



Executing: sysbench --db-driver=mysql --mysql-user=root --mysql-password=root_password --mysql-db=sbtest --table-size=10000 --tables=3 --threads=6 --time=60 --report-interval=10 /usr/share/sysbench/oltp_read_write.lua run
sysbench 1.0.18 (using system LuaJIT 2.1.0-beta3)

Running the test with following options:
Number of threads: 6
Report intermediate results every 10 second(s)
Initializing random number generator from current time


Initializing worker threads...

Threads started!

[ 10s ] thds: 6 tps: 312.12 qps: 6253.89 (r/w/o: 4378.14/1250.90/624.85) lat (ms,95%): 28.16 err/s: 0.00 reconn/s: 0.00
[ 20s ] thds: 6 tps: 323.20 qps: 6463.98 (r/w/o: 4524.79/1292.80/646.40) lat (ms,95%): 26.68 err/s: 0.00 reconn/s: 0.00
[ 30s ] thds: 6 tps: 323.51 qps: 6467.57 (r/w/o: 4527.89/1292.65/647.03) lat (ms,95%): 27.17 err/s: 0.00 reconn/s: 0.00
[ 40s ] thds: 6 tps: 318.78 qps: 6377.91 (r/w/o: 4464.16/1276.20/637.55) lat (ms,95%): 28.67 err/s: 0.00 reconn/s: 0.00
[ 50s ] thds: 6 tps: 324.64 qps: 6489.75 (r/w/o: 4543.02/1297.45/649.27) lat (ms,95%): 26.68 err/s: 0.00 reconn/s: 0.00
[ 60s ] thds: 6 tps: 328.90 qps: 6578.51 (r/w/o: 4605.01/1315.80/657.70) lat (ms,95%): 26.20 err/s: 0.00 reconn/s: 0.00
SQL statistics:
    queries performed:
        read:                            270438
        write:                           77268
        other:                           38634
        total:                           386340
    transactions:                        19317  (321.84 per sec.)
    queries:                             386340 (6436.83 per sec.)
    ignored errors:                      0      (0.00 per sec.)
    reconnects:                          0      (0.00 per sec.)

General statistics:
    total time:                          60.0182s
    total number of events:              19317

Latency (ms):
         min:                                    6.93
         avg:                                   18.64
         max:                                   59.15
         95th percentile:                       27.17
         sum:                               359989.12

Threads fairness:
    events (avg/stddev):           3219.5000/7.14
    execution time (avg/stddev):   59.9982/0.01




Executing: sysbench --db-driver=mysql --mysql-user=root --mysql-password=root_password --mysql-db=sbtest --table-size=10000 --tables=3 /usr/share/sysbench/oltp_read_write.lua cleanup
sysbench 1.0.18 (using system LuaJIT 2.1.0-beta3)

Dropping table 'sbtest1'...
Dropping table 'sbtest2'...
Dropping table 'sbtest3'...



Testing MySQL-Worker-2 (3.223.127.57)

Executing: sudo apt-get update
Hit:1 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal InRelease
Hit:2 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-updates InRelease
Hit:3 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-backports InRelease
Hit:4 http://security.ubuntu.com/ubuntu focal-security InRelease
Reading package lists...



Executing: sudo apt-get install -y sysbench
Reading package lists...
Building dependency tree...
Reading state information...
The following additional packages will be installed:
  libluajit-5.1-2 libluajit-5.1-common libmysqlclient21 libpq5
The following NEW packages will be installed:
  libluajit-5.1-2 libluajit-5.1-common libmysqlclient21 libpq5 sysbench
0 upgraded, 5 newly installed, 0 to remove and 182 not upgraded.
Need to get 1800 kB of archives.
After this operation, 9051 kB of additional disk space will be used.
Get:1 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal/universe amd64 libluajit-5.1-common all 2.1.0~beta3+dfsg-5.1build1 [44.3 kB]
Get:2 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal/universe amd64 libluajit-5.1-2 amd64 2.1.0~beta3+dfsg-5.1build1 [228 kB]
Get:3 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-updates/main amd64 libmysqlclient21 amd64 8.0.40-0ubuntu0.20.04.1 [1304 kB]
Get:4 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal-updates/main amd64 libpq5 amd64 12.20-0ubuntu0.20.04.1 [117 kB]
Get:5 http://us-east-1.ec2.archive.ubuntu.com/ubuntu focal/universe amd64 sysbench amd64 1.0.18+ds-1 [107 kB]
Fetched 1800 kB in 0s (36.1 MB/s)
Selecting previously unselected package libluajit-5.1-common.

(Reading database ... 
(Reading database ... 5%
(Reading database ... 10%
(Reading database ... 15%
(Reading database ... 20%
(Reading database ... 25%
(Reading database ... 30%
(Reading database ... 35%
(Reading database ... 40%
(Reading database ... 45%
(Reading database ... 50%
(Reading database ... 55%
(Reading database ... 60%
(Reading database ... 65%
(Reading database ... 70%
(Reading database ... 75%
(Reading database ... 80%
(Reading database ... 85%
(Reading database ... 90%
(Reading database ... 95%
(Reading database ... 100%
(Reading database ... 62513 files and directories currently installed.)

Preparing to unpack .../libluajit-5.1-common_2.1.0~beta3+dfsg-5.1build1_all.deb ...

Unpacking libluajit-5.1-common (2.1.0~beta3+dfsg-5.1build1) ...

Selecting previously unselected package libluajit-5.1-2:amd64.

Preparing to unpack .../libluajit-5.1-2_2.1.0~beta3+dfsg-5.1build1_amd64.deb ...

Unpacking libluajit-5.1-2:amd64 (2.1.0~beta3+dfsg-5.1build1) ...

Selecting previously unselected package libmysqlclient21:amd64.

Preparing to unpack .../libmysqlclient21_8.0.40-0ubuntu0.20.04.1_amd64.deb ...

Unpacking libmysqlclient21:amd64 (8.0.40-0ubuntu0.20.04.1) ...

Selecting previously unselected package libpq5:amd64.

Preparing to unpack .../libpq5_12.20-0ubuntu0.20.04.1_amd64.deb ...

Unpacking libpq5:amd64 (12.20-0ubuntu0.20.04.1) ...

Selecting previously unselected package sysbench.

Preparing to unpack .../sysbench_1.0.18+ds-1_amd64.deb ...

Unpacking sysbench (1.0.18+ds-1) ...

Setting up libmysqlclient21:amd64 (8.0.40-0ubuntu0.20.04.1) ...

Setting up libpq5:amd64 (12.20-0ubuntu0.20.04.1) ...

Setting up libluajit-5.1-common (2.1.0~beta3+dfsg-5.1build1) ...

Setting up libluajit-5.1-2:amd64 (2.1.0~beta3+dfsg-5.1build1) ...

Setting up sysbench (1.0.18+ds-1) ...

Processing triggers for man-db (2.9.1-1) ...

Processing triggers for libc-bin (2.31-0ubuntu9.9) ...


debconf: unable to initialize frontend: Dialog
debconf: (Dialog frontend will not work on a dumb terminal, an emacs shell buffer, or without a controlling terminal.)
debconf: falling back to frontend: Readline
debconf: unable to initialize frontend: Readline
debconf: (This frontend requires a controlling tty.)
debconf: falling back to frontend: Teletype
dpkg-preconfigure: unable to re-open stdin: 


Executing: mysql -uroot -proot_password -e 'CREATE DATABASE IF NOT EXISTS sbtest;'

mysql: [Warning] Using a password on the command line interface can be insecure.


Executing: sysbench --db-driver=mysql --mysql-user=root --mysql-password=root_password --mysql-db=sbtest --table-size=10000 --tables=3 /usr/share/sysbench/oltp_read_write.lua prepare
sysbench 1.0.18 (using system LuaJIT 2.1.0-beta3)

Creating table 'sbtest1'...
Inserting 10000 records into 'sbtest1'
Creating a secondary index on 'sbtest1'...
Creating table 'sbtest2'...
Inserting 10000 records into 'sbtest2'
Creating a secondary index on 'sbtest2'...
Creating table 'sbtest3'...
Inserting 10000 records into 'sbtest3'
Creating a secondary index on 'sbtest3'...



Executing: sysbench --db-driver=mysql --mysql-user=root --mysql-password=root_password --mysql-db=sbtest --table-size=10000 --tables=3 --threads=6 --time=60 --report-interval=10 /usr/share/sysbench/oltp_read_write.lua run
sysbench 1.0.18 (using system LuaJIT 2.1.0-beta3)

Running the test with following options:
Number of threads: 6
Report intermediate results every 10 second(s)
Initializing random number generator from current time


Initializing worker threads...

Threads started!

[ 10s ] thds: 6 tps: 313.24 qps: 6276.26 (r/w/o: 4393.80/1255.37/627.09) lat (ms,95%): 28.16 err/s: 0.00 reconn/s: 0.00
[ 20s ] thds: 6 tps: 231.51 qps: 4629.91 (r/w/o: 3241.08/925.82/463.01) lat (ms,95%): 52.89 err/s: 0.00 reconn/s: 0.00
[ 30s ] thds: 6 tps: 287.00 qps: 5737.89 (r/w/o: 4016.89/1147.00/574.00) lat (ms,95%): 37.56 err/s: 0.00 reconn/s: 0.00
[ 40s ] thds: 6 tps: 324.20 qps: 6486.27 (r/w/o: 4539.88/1297.99/648.40) lat (ms,95%): 26.68 err/s: 0.00 reconn/s: 0.00
[ 50s ] thds: 6 tps: 125.10 qps: 2498.71 (r/w/o: 1749.71/498.80/250.20) lat (ms,95%): 189.93 err/s: 0.00 reconn/s: 0.00
[ 60s ] thds: 6 tps: 308.69 qps: 6177.14 (r/w/o: 4323.39/1236.37/617.38) lat (ms,95%): 31.94 err/s: 0.00 reconn/s: 0.00
SQL statistics:
    queries performed:
        read:                            222656
        write:                           63616
        other:                           31808
        total:                           318080
    transactions:                        15904  (264.98 per sec.)
    queries:                             318080 (5299.56 per sec.)
    ignored errors:                      0      (0.00 per sec.)
    reconnects:                          0      (0.00 per sec.)

General statistics:
    total time:                          60.0187s
    total number of events:              15904

Latency (ms):
         min:                                    4.59
         avg:                                   22.64
         max:                                  705.30
         95th percentile:                       38.25
         sum:                               360023.32

Threads fairness:
    events (avg/stddev):           2650.6667/12.94
    execution time (avg/stddev):   60.0039/0.00




Executing: sysbench --db-driver=mysql --mysql-user=root --mysql-password=root_password --mysql-db=sbtest --table-size=10000 --tables=3 /usr/share/sysbench/oltp_read_write.lua cleanup
sysbench 1.0.18 (using system LuaJIT 2.1.0-beta3)

Dropping table 'sbtest1'...
Dropping table 'sbtest2'...
Dropping table 'sbtest3'...
```