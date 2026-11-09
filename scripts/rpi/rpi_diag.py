"""Raw I2C diagnostics on the RPi (CPython + smbus2). Read-mostly: the only
write is a scratch round trip to USER memory 0x10 (saved/restored).
Run:  python3 rpi_diag.py
"""
import sys
import time

import smbus2

BUS = 1
ADDR = 0x50

bus = smbus2.SMBus(BUS)

print("== single-byte reads (read_byte_data) ==")
for reg in (0x00, 0x58, 0x59, 0x56, 0x57, 0x5A):
    for attempt in range(3):
        try:
            v = bus.read_byte_data(ADDR, reg)
            print("reg 0x%02X try%d -> 0x%02X" % (reg, attempt, v))
        except OSError as e:
            print("reg 0x%02X try%d -> OSError: %s" % (reg, attempt, e))
            break

print("== word read (read_word_data) ==")
try:
    w = bus.read_word_data(ADDR, 0x58)
    print("LTH:LTL word = 0x%04X" % w)
except OSError as e:
    print("word read OSError:", e)

print("== block reads of varying length (read_i2c_block_data) ==")
for n in (1, 2, 4, 8):
    try:
        data = bus.read_i2c_block_data(ADDR, 0x58, n)
        print("n=%d -> len=%d data=%s" % (n, len(data), " ".join("%02X" % b for b in data)))
    except OSError as e:
        print("n=%d -> OSError: %s" % (n, e))

print("== write/read round trip to USER mem 0x10 ==")
orig = bus.read_byte_data(ADDR, 0x10)
print("original 0x10 = 0x%02X" % orig)
bus.write_byte_data(ADDR, 0x10, 0xA5)
time.sleep(0.05)
back = bus.read_byte_data(ADDR, 0x10)
print("after write 0xA5, read back = 0x%02X" % back)
bus.write_byte_data(ADDR, 0x10, orig)
time.sleep(0.05)
restored = bus.read_byte_data(ADDR, 0x10)
print("restored 0x10 = 0x%02X" % restored)
