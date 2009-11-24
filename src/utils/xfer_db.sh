#!/bin/bash

# Dump database & copy to ipaq
echo "Dumping local database..."
echo '.dump' | sqlite3 $HOME/.freeflight/free.db | gzip -c > free.gz
echo "Copying to "$1
scp free.gz $1:

# On ipaq remake database and move to correct location
echo "Re-generating remote database..."
ssh $1 'zcat free.gz | sqlite3 free.db; rm free.gz'
ssh $1 'mv free.db .freeflight'

# Clean up
rm free.gz
