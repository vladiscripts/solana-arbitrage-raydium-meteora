#!/bin/bash

# Update and install required packages
sudo apt-get update -y
sudo apt-get install -y unzip npm tmux redis-server postgresql postgresql-contrib wget

# Setup directories
mkdir -p ~/solana
mv meteora_arbitrage.zip ~/solana/
cd ~/solana || exit

# Unzip project
unzip meteora_arbitrage.zip
rm -rf meteora_arbitrage.zip

# Install Miniconda
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -O ~/Miniconda3.sh
bash ~/Miniconda3.sh -b -p $HOME/miniconda
source ~/miniconda/bin/activate

# Start and enable Redis
sudo systemctl start redis
sudo systemctl enable redis

# Test Redis
sudo systemctl status redis --no-pager
redis-cli ping

# Start and enable PostgreSQL
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Setup PostgreSQL database and user
sudo -i -u postgres psql <<EOF
CREATE USER topswellc WITH PASSWORD 'admin';
CREATE DATABASE arbitrage OWNER topswellc;
GRANT ALL PRIVILEGES ON DATABASE arbitrage TO topswellc;
GRANT USAGE ON SCHEMA public TO topswellc;
GRANT CREATE ON SCHEMA public TO topswellc;
GRANT ALL PRIVILEGES ON SCHEMA public TO topswellc;
\q
EOF

# Configure PostgreSQL to allow local connections
sudo sed -i "s/^host    all.*127.0.0.1\/32.*/host    all             all             127.0.0.1\/32            md5/" /etc/postgresql/16/main/pg_hba.conf
sudo systemctl restart postgresql

# Setup .pgpass file for passwordless authentication
echo "localhost:5432:arbitrage:topswellc:admin" > ~/.pgpass
chmod 600 ~/.pgpass

# Test PostgreSQL connection
psql -U topswellc -d arbitrage -h localhost -p 5432 -c "SELECT 'Connected to PostgreSQL' AS status;"

# Set environment variables
echo 'export SSL_CERT_FILE=$(python3 -c "import certifi; print(certifi.where())")' >> ~/.bashrc
echo 'export REQUESTS_CA_BUNDLE=$(python3 -c "import certifi; print(certifi.where())")' >> ~/.bashrc
source ~/.bashrc

echo 'source ~/miniconda/bin/activate' >> ~/.bashrc && source ~/.bashrc
conda activate /home/ubuntu/solana/arbitrage/core/env/topswell

echo "Setup complete!"
