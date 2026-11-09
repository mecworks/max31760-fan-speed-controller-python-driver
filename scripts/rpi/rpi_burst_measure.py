"""Isolate the post-LOAD completion NACK burst: trigger a LOAD, then hammer
a no-op CR1 write every 1 ms for 300 ms and report every NACK run."""
import sys
import time

sys.path.insert(0, ".")
import smbus2

b = smbus2.SMBus(1)


def wr():
    try:
        b.write_i2c_block_data(0x50, 0x00, [0x19])
        return True
    except OSError:
        return False


# ensure clean state first
assert wr()
print("pre-state CR1:", hex(b.read_byte_data(0x50, 0x00)))

b.write_i2c_block_data(0x50, 0x5B, [0x81])   # LOAD block 00-0F
t0 = time.monotonic()
runs = []
in_run = False
start = 0
while time.monotonic() - t0 < 0.30:
    t = int((time.monotonic() - t0) * 1000)
    ok = wr()
    if not ok and not in_run:
        in_run = True
        start = t
    elif ok and in_run:
        in_run = False
        runs.append((start, t - 1))
if in_run:
    runs.append((start, 299))
print("NACK runs (ms):", runs if runs else "NONE")
print("post CR1:", hex(b.read_byte_data(0x50, 0x00)))
# restore factory CR1 to EEPROM too
wr()
b.write_i2c_block_data(0x50, 0x5B, [0x01])
time.sleep(0.7)
print("final CR1:", hex(b.read_byte_data(0x50, 0x00)))
print("DONE")
