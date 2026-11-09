"""Diagnose block-read vs byte-read behavior on the RPi bus."""
import smbus2

b = smbus2.SMBus(1)
print("byte 0x58:", hex(b.read_byte_data(0x50, 0x58)))
print("byte 0x59:", hex(b.read_byte_data(0x50, 0x59)))
try:
    d = b.read_i2c_block_data(0x50, 0x58, 2)
    print("block(2):", [hex(x) for x in d])
except Exception as e:
    print("block(2) FAILED:", type(e).__name__, e)
try:
    d = b.read_i2c_block_data(0x50, 0x00, 4)
    print("block(4) @0x00:", [hex(x) for x in d])
except Exception as e:
    print("block(4) FAILED:", type(e).__name__, e)
