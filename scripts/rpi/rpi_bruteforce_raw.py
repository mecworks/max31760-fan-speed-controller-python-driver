"""Same 10x brute force as rpi_bruteforce.py but with RAW smbus2 (no driver):
identical value sequence and 700 ms silences. Isolates driver-specific
behavior from pure bus-sequence behavior."""
import sys
import time

sys.path.insert(0, ".")
import smbus2

N_RUNS = 10
CR1_FAC = 0x19


def wr(b, v):
    b.write_i2c_block_data(0x50, 0x00, [v])


def rd_cr1(b):
    return b.read_byte_data(0x50, 0x00)


results = []
for i in range(N_RUNS):
    t0 = time.monotonic()
    try:
        b = smbus2.SMBus(1)
        assert b.read_byte_data(0x50, 0x58) is not None   # verify (probe)
        cr1_0 = rd_cr1(b)
        sentinel = cr1_0 ^ 0x04
        wr(b, sentinel)                                   # RAM = sentinel
        b.write_i2c_block_data(0x50, 0x5B, [0x01])        # SAVE
        time.sleep(0.700)                                 # fixed wait
        wr(b, cr1_0)                                       # RAM = factory
        b.write_i2c_block_data(0x50, 0x5B, [0x81])        # LOAD
        time.sleep(0.700)                                 # fixed wait
        got = rd_cr1(b)
        assert got == sentinel, "round trip mismatch %02X" % got
        # soft_por equivalent: RMW CR1 |= 0x40
        v = rd_cr1(b)
        wr(b, (v | 0x40) & 0xFF)                          # <- the failing op
        # restore factory state
        wr(b, cr1_0)
        b.write_i2c_block_data(0x50, 0x5B, [0x01])        # SAVE
        time.sleep(0.700)
        b.close()
        results.append("PASS %.2fs" % (time.monotonic() - t0))
    except Exception as e:
        results.append("FAIL %s:%s (%.2fs)" % (e.__class__.__name__, e,
                                               time.monotonic() - t0))
    print("run %2d: %s" % (i + 1, results[-1]), flush=True)
    time.sleep(1.0)

print("--- summary: %d/%d pass ---" %
      (sum(1 for r in results if r.startswith("PASS")), N_RUNS))
