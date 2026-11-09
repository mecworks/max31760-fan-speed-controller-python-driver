"""Phase B6 hardware E2E: tach enable, live RPM read, threshold vs real chip.

Runs ON the Pico (MicroPython). Exercises:
  - live RPM of the bench fan on port 1 (real tach pulses)
  - TACH1/TACH2 enable toggles (CR3 bits, other bits preserved)
  - TACH2 alarm observable effect: enabling TACH2 with no fan present must
    set TACH2A in SR (no second fan on bench => EXCLUDED-HW for functional
    RPM-on-port-2; the alarm path IS exercised)
  - 16-bit threshold get/set round-trip + factory restore
Prints PHASE-B6 DEVICE E2E: PASS on success.
"""
import time
import machine
from max31760.mp import MAX31760
from max31760._core import REG_SR

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify(), "verify() failed"

# Idempotent factory start
dev.write_reg(0x00, bytes([0x01]))
dev.write_reg(0x01, bytes([0x10]))
dev.write_reg(0x02, bytes([0x03]))
cr3_0 = dev.read_reg(0x02, 1)[0]
assert cr3_0 == 0x03, "not factory state"

# --- live RPM on port 1 -------------------------------------------------------
time.sleep_ms(500)                            # let counters settle
speed = dev.rpm(1, 2)
print("port1 rpm(ppr=2)=%.1f" % speed)
assert speed > 0.0, "fan not spinning?"
assert 100.0 < speed < 30000.0, "implausible fan speed %.1f" % speed
# Cross-check with a different assumed pulse count scales inversely
speed4 = dev.rpm(1, 4)
assert abs(speed4 * 2.0 - speed) / speed < 0.05, "ppr scaling inconsistent"
print("port1 rpm(ppr=4)=%.1f (half of ppr=2 as expected)" % speed4)

# --- tach enable toggles ------------------------------------------------------
assert dev.tach1_enabled() and dev.tach2_enabled()
dev.tach1_enable(False)
assert not dev.tach1_enabled() and dev.tach2_enabled()
dev.tach1_enable(True)
assert dev.tach1_enabled() and dev.tach2_enabled()
print("tach1 toggle: OK")

# --- TACH2 alarm observable effect (no fan on port 2) -------------------------
# NOTE: SR lives at 0x5A (0x04 is the ALERT MASK register, factory C0h).
sr_before = dev.read_reg(REG_SR, 1)[0]
dev.tach2_enable(True)                        # already on; force fresh detection
dev.write_reg(0x02, bytes([(cr3_0 & ~0x02) | 0x80]))  # CLRFAIL w/ TACH2 off
dev.tach2_enable(True)
# Datasheet: fan-error detection is DISABLED during the first 2 s after
# (re)start; MEASURED on this bench (e2e_diag_latency.py): TACH2A re-latches
# ~8 s after CLRFAIL + TACH2 re-enable (grace period + fault-queue cadence).
time.sleep_ms(10000)
sr_after = dev.read_reg(REG_SR, 1)[0]
print("SR before=%02X after=%02X (TACH2A=bit1)" % (sr_before, sr_after))
assert sr_after & 0x02, "TACH2A did not assert with no fan on port 2"
print("tach2 alarm: OK")

# --- 16-bit threshold round-trip ----------------------------------------------
th_0 = dev.get_tach_threshold()
assert th_0 == 0xFFFE, "factory threshold unexpected: %d" % th_0
for val in (0, 40000, 65535):
    dev.set_tach_threshold(val)
    got = dev.get_tach_threshold()
    assert got == val, "threshold mismatch: wrote %d read %d" % (val, got)
dev.set_tach_threshold(th_0)
assert dev.get_tach_threshold() == th_0
print("threshold round-trip: OK (factory %d restored)" % th_0)

# Restore factory control state
dev.write_reg(0x02, bytes([cr3_0]))
assert dev.read_reg(0x02, 1)[0] == cr3_0
print("restored factory CR3")

print("PHASE-B6 DEVICE E2E: PASS")
