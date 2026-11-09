"""Post-reflash Pico health probe (COM16). Read-only: firmware, filesystem,
I2C bus scan. Run via: python -m mpremote connect port:COM16 run pico_reflash_probe.py
"""
import sys
import os
import machine

print("fw:", sys.implementation.name, sys.version)
print("platform:", sys.platform)

try:
    print("/lib:", sorted(os.listdir("/lib")))
except OSError as e:
    print("/lib missing:", e)

try:
    pkg = "/lib/max31760"
    files = sorted(os.listdir(pkg))
    print("pkg files:", files)
    import max31760
    from max31760.mp import MAX31760
    n = len([x for x in dir(MAX31760) if not x.startswith("_")])
    print("import OK, version:", max31760.__version__, ", members:", n)
except Exception as e:
    print("package check failed:", type(e).__name__, e)

i2c = machine.I2C(0, sda=machine.Pin(0), scl=machine.Pin(1))
print("i2c scan:", [hex(a) for a in i2c.scan()])
