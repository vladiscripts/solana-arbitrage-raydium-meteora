#!/bin/bash

# Variables
EC2_HOST="YOUR_EC2_HOST"
EC2_USER="YOUR_EC2_USER"
LOCAL_USER="YOUR_LOCAL_USER"
LOCAL_DB="YOUR_LOCAL_DB_NAME"
LOCAL_IP="localhost"
LOCAL_PORT=5432
EC2_DB="YOUR_EC2_DB_NAME"
EC2_KEY="YOUR_SSH_KEY_FILE"
DUMP_FILE="data.sql"

# Dump the database (data only)
pg_dump -U $LOCAL_USER -h $LOCAL_IP -p $LOCAL_PORT -d $LOCAL_DB --data-only -f $DUMP_FILE

# Copy to EC2
scp -i $EC2_KEY $DUMP_FILE $EC2_USER@$EC2_HOST:/home/$EC2_USER/

# SSH and restore on EC2
ssh -i $EC2_KEY $EC2_USER@$EC2_HOST << EOF
    psql -U $LOCAL_USER -d $EC2_DB -h $LOCAL_IP -p $LOCAL_PORT -c "TRUNCATE TABLE luts, meteora_pools, tokens, pools, two_arbitrage_routes RESTART IDENTITY CASCADE;"
    psql -U $LOCAL_USER -d $EC2_DB -h $LOCAL_IP -p $LOCAL_PORT -f /home/$EC2_USER/$DUMP_FILE
EOF

echo "✅ Database cloned successfully!"
