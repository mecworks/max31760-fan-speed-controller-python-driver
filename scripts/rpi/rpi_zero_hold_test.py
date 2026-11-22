"""RPi bench 0%-hold test: adjudicate the frozen-tach anomaly.

The duty curve showed a flat 2302.4 rpm report during the 0 % duty window
while the chip's own PWMV readback said 0 %. Given the tach architecture
(period-of-averaged-pulse-group latched in TC1H/L, see _regs.py constants),
a fan that STOPS abruptly leaves its last period latched forever - the
reported RPM then describes the past, not the present.

This test makes the stop observable:
  1. 100 % duty, settle, record baseline (pwmv + reported rpm)
  2. command 0 %, then log pwmv + reported rpm every 2 s for 30 s
     *** WATCH/LISTEN TO THE FAN DURING THIS PHASE ***
  3. command 100 % again (restart from standstill), record recovery

Adjudication:
  fan audibly cuts out within ~1 s of the 0 % command
      -> abrupt stop confirmed; the flat 2302.4 was a STALE PERIOD LATCH.
         Chip, driver stage, and wiring are healthy; rpm() reports a stale
         value after a stop (document as a known limitation).
  fan keeps running at full speed through the 0 % window
      -> physical power-path anomaly (output not actually gated);
         inspect fan connector seating / probe the FOUT pin.

Fully reversible: snapshots 0x00..0x4F, restores byte-for-byte.
Run on the Pi from the deployment dir:  python3 rpi_zero_hold_test.py
Runtime ~50 s.
"""
import sys
import time

sys.path.insert(0, ".")
from max31760.cp import MAX31760

dev = MAX31760(bus=1, addr=0x50)
assert dev.verify(), "chip not responding"
SNAP = dev.read_reg(0x00, 0x50)
dev.manual = True
dev.ramp_rate = MAX31760.RAMP_IMMEDIATE

dev.set_duty_pct(100.0)
assert dev.wait_for_duty(100.0, timeout_ms=1500)
time.sleep(8)
print("baseline @100%%: pwmv=%d  rpm_reported=%.1f" %
      (dev.actual_duty_raw, dev.rpm(1)))

dev.set_duty_pct(0.0)
assert dev.wait_for_duty(0.0, timeout_ms=1500)
print("== 0 %% hold: WATCH THE FAN NOW ==")
for i in range(15):
    time.sleep(2.0)
    print("t=%2ds  pwmv=%3d  rpm_reported=%8.1f" %
          ((i + 1) * 2, dev.actual_duty_raw, dev.rpm(1)), flush=True)

dev.set_duty_pct(100.0)
assert dev.wait_for_duty(100.0, timeout_ms=1500)
time.sleep(8)
print("recovered @100%%: pwmv=%d  rpm_reported=%.1f" %
      (dev.actual_duty_raw, dev.rpm(1)))

dev.write_reg(0x00, SNAP)
ok = True
for off in range(0, 0x50, 8):
    if bytes(dev.read_reg(off, 8)) != SNAP[off:off + 8]:
        ok = False
        break
assert ok, "RESTORE VERIFICATION FAILED"
print("configuration restored (RAM verified byte-for-byte)")
