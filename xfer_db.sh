#!/bin/bash

# Dump database & copy to ipaq
echo '.dump' | sqlite3 $HOME/.freeflight/free.db | gzip -c > free.gz
scp free.gz ipaq:

# On ipaq remake database and move to correct location
ssh ipaq 'zcat free.gz | sqlite3 free.db; rm free.gz'
ssh ipaq 'mv free.db .freeflight'

# Clean up
rm free.gz
