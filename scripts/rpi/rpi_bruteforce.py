"""Brute-force the exact smoke-test EEPROM+POR sequence through the driver
to measure the failure rate and characterize the stall when it hits."""
import sys
import time

sys.path.insert(0, ".")
from max31760.cp import MAX31760

N_RUNS = 10
results = []

for i in range(N_RUNS):
    t_start = time.monotonic()
    try:
        dev = MAX31760(bus=1, addr=0x50)
        assert dev.verify()
        cr1_0 = dev.read_reg(0x00, 1)[0]
        sentinel = cr1_0 ^ 0x04
        dev.write_reg(0x00, bytes([sentinel]))
        dev.save_config(MAX31760.EEX_BLOCK_00_0F)
        dev.write_reg(0x00, bytes([cr1_0]))
        dev.load_config(MAX31760.EEX_BLOCK_00_0F)
        got = dev.read_reg(0x00, 1)[0]
        assert got == sentinel, "round trip mismatch %02X" % got
        dev.soft_por()
        # restore factory state
        dev.write_reg(0x00, bytes([cr1_0]))
        dev.save_config(MAX31760.EEX_BLOCK_00_0F)
        results.append("PASS %.2fs" % (time.monotonic() - t_start))
    except Exception as e:
        results.append("FAIL %s (%.2fs)" % (e.__class__.__name__,
                                            time.monotonic() - t_start))
    print("run %2d: %s" % (i + 1, results[-1]), flush=True)
    time.sleep(1.0)

print("--- summary: %d/%d pass ---" %
      (sum(1 for r in results if r.startswith("PASS")), N_RUNS))
