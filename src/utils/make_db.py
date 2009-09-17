#!/usr/bin/env python

import math
import freenav.freedb

PARALLEL1 = math.radians(49)
PARALLEL2 = math.radians(55)
REF_LAT = math.radians(52)
REF_LON = math.radians(0)

def main():
    db = freenav.freedb.Freedb()
    db.create(PARALLEL1, PARALLEL2, REF_LAT, REF_LON)

if __name__ == '__main__':
    main()
