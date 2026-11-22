"""RPi bench duty-vs-RPM curve mapping: 0..100 % in 5 % steps.

Answers two questions:
  1. PRE-FLIGHT STATE DUMP: what is the chip actually commanding right now
     (manual vs LUT mode, commanded vs actual duty, live RPM) - resolves
     "is the fan running at 100 %?".
  2. FULL MODULATION CURVE: settled RPM at each 5 % duty increment, sampled
     every 1 s for 15 s after each step (final sample = settled value;
     min/max band reported). Also proves smoothness of the PWM stage across
     the entire range (thermal-anomaly investigation, candidate A).

Fully reversible: snapshots nonvolatile range 0x00..0x4F, restores it
byte-for-byte at the end (chip returns to whatever mode it was in, e.g.
factory LUT mode).

Run on the Pi from the deployment dir:  python3 rpi_duty_rpm_curve.py
Total runtime ~6 min.
"""
import sys
import time

sys.path.insert(0, ".")
from max31760.cp import MAX31760

SETTLE_S = 15          # user-specified settle window per level
SAMPLE_S = 1.0         # sampling cadence inside the window

dev = MAX31760(bus=1, addr=0x50)
assert dev.verify(), "chip not responding"

print("== pre-flight state ==")
print("manual mode      =", dev.manual)
print("index source     =", "REMOTE" if dev.index_source == MAX31760.INDEX_REMOTE else "LOCAL")
print("commanded duty   = %d/255 (%.1f %%)" %
      (dev.duty_cmd_raw, dev.duty_cmd_raw * 100.0 / 255.0))
print("actual duty      = %d/255 (%.1f %%)" %
      (dev.actual_duty_raw, dev.actual_duty_raw * 100.0 / 255.0))
print("live rpm         = %.1f" % dev.rpm(1))
print("local temp       = %.1f C" % dev.local_temp_c)
print("")

SNAP = dev.read_reg(0x00, 0x50)
dev.manual = True
dev.ramp_rate = MAX31760.RAMP_IMMEDIATE

print("== duty-vs-rpm curve (settled after %d s) ==" % SETTLE_S)
print("%-8s %-12s %-12s" % ("duty", "rpm_settled", "band(min-max)"))
curve = []
for pct in range(0, 101, 5):
    dev.set_duty_pct(float(pct))
    assert dev.wait_for_duty(float(pct), timeout_ms=1500), \
        "PWM engine did not reach %d %% duty" % pct
    vals = []
    for _ in range(SETTLE_S // int(SAMPLE_S)):
        time.sleep(SAMPLE_S)
        vals.append(dev.rpm(1))
    settled = vals[-1]
    curve.append((pct, settled))
    print("%-8s %-12.1f %-12.1f-%.1f" %
          ("%d%%" % pct, settled, min(vals), max(vals)), flush=True)

# ------------------------------------------------------------- restore ------
dev.write_reg(0x00, SNAP)
ok = True
for off in range(0, 0x50, 8):
    if bytes(dev.read_reg(off, 8)) != SNAP[off:off + 8]:
        ok = False
        break
assert ok, "RESTORE VERIFICATION FAILED"
print("configuration restored (RAM verified byte-for-byte)")

print("")
print("== summary ==")
nonzero = [(p, r) for p, r in curve if r > 10.0]
if nonzero:
    lo_p, lo_r = nonzero[0]
    hi_p, hi_r = nonzero[-1]
    print("lowest responsive duty : %d %% -> %.1f rpm" % (lo_p, lo_r))
    print("highest duty           : %d %% -> %.1f rpm" % (hi_p, hi_r))
mono = all(a <= b for (_, a), (_, b) in zip(curve, curve[1:]))
print("monotonic non-decreasing : %s" % mono)
