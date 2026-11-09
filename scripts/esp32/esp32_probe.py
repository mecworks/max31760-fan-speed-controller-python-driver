"""Standalone MAX31760 connectivity probe for the ESP32 bench (COM7).

Pure machine.I2C — no driver dependency. SDA=GPIO41, SCL=GPIO42.
Reads only RO/control registers; changes nothing.
Run via:  python -m mpremote connect port:COM7 run esp32_probe.py
"""
import sys
import machine

print("fw:", sys.implementation.name, sys.version)

SDA = 41
SCL = 42
ADDR = 0x50

i2c = machine.I2C(0, sda=machine.Pin(SDA), scl=machine.Pin(SCL), freq=400000)
found = [hex(a) for a in i2c.scan()]
print("bus scan:", found)

if ADDR not in i2c.scan():
    print("PROBE: FAIL - no device at 0x%02X" % ADDR)
    raise SystemExit(1)


def temp_c(hi, lo):
    v = ((hi << 8) | lo) & 0xFFFF
    if v & 0x8000:
        v -= 0x10000
    return (v >> 5) / 8.0


cr1 = i2c.readfrom_mem(ADDR, 0x00, 1)[0]
lt = temp_c(*i2c.readfrom_mem(ADDR, 0x58, 2))
rt = temp_c(*i2c.readfrom_mem(ADDR, 0x56, 2))
pwmv = i2c.readfrom_mem(ADDR, 0x51, 1)[0]
print("CR1   = 0x%02X" % cr1)
print("local  temp = %.1f C" % lt)
print("remote temp = %.1f C" % rt)
print("PWMV (actual duty) = %d/255" % pwmv)

assert -40.0 < lt < 125.0, "local temp implausible (%.1f)" % lt
assert -40.0 < rt < 150.0, "remote temp implausible (%.1f)" % rt
print("PROBE: PASS - MAX31760 reachable at 0x%02X, temps sane" % ADDR)
