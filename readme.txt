BUILDING THE DATABASE
---------------------

1. Run freedb.py to create the database and add tables

2. Download tab separated file from Worldwide Soaring Turnpoint Exchange
   (Unfortunately the field names seem somewhat variable.)
3. Delete comment text from start of file leaving the header line
4. Run import_wp.py

5. Download Rory O'Connor's airspace files
6. Correct "errors" in airspace files (use vim :goto to move to byte location)
6a. Convert file to unix format
7. Run import_air.py

8. Copy to ipaq
     pc> echo '.dump' | sqlite3 ~/.freeflight/free.db | gzip -c > free.gz
     pc> scp free.gz ipaq:free.gz
     ipaq> rm .freeflight/free.gz
     ipaq> zcat free.gz | sqlite3 .freeflight/free.db
