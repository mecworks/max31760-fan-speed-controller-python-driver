"""Phase A hardware E2E: transport layer against the real MAX31760.

Runs ON the Pico (MicroPython). Exercises:
  - probe (address ACK)
  - burst reads of both temperature channels (readfrom_mem)
  - single-byte write round-trip (writeto_mem) in USER region 0x10
  - full 8-byte page-row bulk write + read-back
  - restore of the original USER byte
Prints PHASE-A TRANSPORT E2E: PASS on success.
"""
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)

print("probe:", dev.probe())
assert dev.probe()

lt = dev.read_reg(0x58, 2)
rt = dev.read_reg(0x56, 2)


def dec(b):
    v = (b[0] << 8) | b[1]
    if v & 0x8000:
        v -= 0x10000
    return (v >> 5) / 8.0


local_c = dec(lt)
remote_c = dec(rt)
print("local=%.3fC remote=%.3fC" % (local_c, remote_c))
assert -40.0 < local_c < 125.0, "local temp implausible"
assert -40.0 < remote_c < 125.0, "remote temp implausible"

# Single-byte write round-trip (USER region 0x10)
orig = dev.read_reg(0x10, 1)[0]
dev.write_reg(0x10, b"\xa5")
back = dev.read_reg(0x10, 1)[0]
print("user0 orig=%02X read_back=%02X" % (orig, back))
assert back == 0xA5, "single-byte write did not stick"

# Full 8-byte page-row bulk write + read-back
bulk = bytes(range(0xB0, 0xB8))
dev.write_reg(0x10, bulk)
got = dev.read_reg(0x10, 8)
print("user_bulk=" + "".join(["%02X" % x for x in got]))
assert got == bulk, "bulk write mismatch"

# Restore original value
dev.write_reg(0x10, bytes([orig]))
restored = dev.read_reg(0x10, 1)[0]
assert restored == orig, "restore failed"
print("restored user0=%02X" % restored)

print("PHASE-A TRANSPORT E2E: PASS")
