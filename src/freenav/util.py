import math
import re

def dmm(val, precision=3):
    """Splits a lat/lon value into degrees, minutes, decimal minutes and
    hemispheres.

    val - lat/lon, in radians
    precision - specifies number of decimal digits

    Returns a dictionary with the following fields -
    ns - sign of the value either N(+ve) or S(-ve)
    ew - sign of the value either E(+ve) or W(-ve)
    deg - Whole degrees, if a width (eg %3D) is given value is zero padded
    min - Whole minutes, if a width (eg %2M) is given value is zero padded
    dec - Decimal minutes, number of places given by the precision argument
    """

    # Make "sign" string
    ns, ew = ("N", "E") if (val >= 0) else ("S", "W")

    # Split into degrees/minutes/decimal minutes
    decimal_precision = 10 ** precision
    total_dec = int(round(abs(math.degrees(val)) * 60 * decimal_precision))
    minutes, decimal_minutes = divmod(total_dec, decimal_precision)
    degrees, minutes = divmod(minutes, 60)

    # Make string value
    return {'deg': degrees, 'min': minutes, 'dec': decimal_minutes,
            'ns': ns, 'ew': ew}

def dms(val, precision=0):
    """Splits a lat/lon value into degrees, minutes, seconds, decimal seconds
    and hemispheres

    val - lat/lon, in radians
    precision - specifies number of decimal digits

    Returns a dictional with the following fields -
    ns - sign of the value either N(+ve) or S(-ve)
    ew - sign of the value either E(+ve) or W(-ve)
    deg - Whole degrees, if a width (eg %3D) is given value is zero padded
    min - Whole minutes, if a width (eg %2M) is given value is zero padded
    sec - Whole seconds, if a width (eg %2M) is given value is zero padded
    dec - Decimal seconds, number of places given by the precision argument
    """

    # Make "sign" string
    ns, ew = ("N", "E") if (val >= 0) else ("S", "W")

    # Split into degrees/minutes/seconds/decimal seconds
    decimal_precision = 10 ** precision
    total_dec = int(round(abs(math.degrees(val)) * 3600 * decimal_precision))
    decimal_seconds, seconds = divmod(total_dec, decimal_precision)
    minutes, seconds = divmod(seconds, 60)
    degrees, minutes = divmod(minutes, 60)

    # Make string value
    return {'deg': degrees, 'min': minutes, 'sec': seconds,
            'dec': decimal_seconds, 'ns': ns, 'ew': ew}
