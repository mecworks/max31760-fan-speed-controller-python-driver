"""Raspberry Pi (CPython) MAX31760 connectivity probe.

Runs on the SBC itself (full Python + smbus2). Bus 1 = GPIO pins 3/5
(SDA=GPIO2, SCL=GPIO3). Read-only: scan, verify, temps, actual duty.
Run:  python3 rpi_probe.py   (needs access to /dev/i2c-1; use sudo if not in i2c group)
"""
import sys

sys.path.insert(0, ".")
from max31760.cp import MAX31760

BUS = 1
ADDR = 0x50

dev = MAX31760(bus=BUS, addr=ADDR)

print("python:", sys.version.split()[0])
found = dev.scan()
print("bus %d scan:" % BUS, [hex(a) for a in found])
if ADDR not in found:
    print("PROBE: FAIL - no device at 0x%02X" % ADDR)
    raise SystemExit(1)

assert dev.verify(), "verify failed"
lt = dev.local_temp_c
rt = dev.remote_temp_c
cr1 = dev.read_reg(0x00, 1)[0]
pwmv = dev.get_actual_duty_raw()
print("CR1          = 0x%02X" % cr1)
print("local  temp  = %.1f C" % lt)
print("remote temp  = %.1f C" % rt)
print("actual duty  = %d/255" % pwmv)

assert -40.0 < lt < 125.0, "local temp implausible (%.1f)" % lt
assert -40.0 < rt < 150.0, "remote temp implausible (%.1f)" % rt
print("PROBE: PASS - MAX31760 reachable at 0x%02X, temps sane" % ADDR)
