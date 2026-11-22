"""RPi bench precise duty-vs-RPM curve: 0..100 % in 1 % steps.

Each step: command duty, confirm via chip readback (wait_for_duty), then
sample rpm(1) once per second for 15 s (settled value = final sample).
Rows are appended to the CSV incrementally (crash-safe); progress lines go
to stdout. Fully reversible: snapshots nonvolatile range 0x00..0x4F and
restores it byte-for-byte at the end.

Known bench fact (Cooler Master SickleFlow 92, 650-2300 rpm): 0 % duty
does NOT stop the fan - it runs at its ~650 rpm minimum (Intel 4-wire
convention). Expect a flat floor from 0 % up to the crossover point.

Run on the Pi from the deployment dir:  python3 rpi_duty_curve_1pct.py
Output: /tmp/duty_curve_1pct.csv   (columns: pct,rpm_settled,rpm_min,rpm_max)
Runtime ~28 min.
"""
import sys
import time

sys.path.insert(0, ".")
from max31760.cp import MAX31760

SETTLE_S = 15          # user-specified settle window per level
SAMPLE_S = 1.0         # sampling cadence inside the window
CSV_PATH = "/tmp/duty_curve_1pct.csv"

dev = MAX31760(bus=1, addr=0x50)
assert dev.verify(), "chip not responding"
SNAP = dev.read_reg(0x00, 0x50)
dev.manual = True
dev.ramp_rate = MAX31760.RAMP_IMMEDIATE

csvf = open(CSV_PATH, "w")
csvf.write("pct,rpm_settled,rpm_min,rpm_max\n")
csvf.flush()

print("== 1 %% duty sweep (%d s settle each) ==" % SETTLE_S, flush=True)
rows = []
for pct in range(0, 101):
    dev.set_duty_pct(float(pct))
    assert dev.wait_for_duty(float(pct), timeout_ms=1500), \
        "PWM engine did not reach %d %% duty" % pct
    vals = []
    for _ in range(SETTLE_S // int(SAMPLE_S)):
        time.sleep(SAMPLE_S)
        vals.append(dev.rpm(1))
    settled = vals[-1]
    rows.append((pct, settled))
    csvf.write("%d,%.1f,%.1f,%.1f\n" % (pct, settled, min(vals), max(vals)))
    csvf.flush()
    print("[%3d/101] %3d%%  rpm=%.1f  (band %.1f-%.1f)" %
          (pct + 1, pct, settled, min(vals), max(vals)), flush=True)
csvf.close()

# ------------------------------------------------------------- restore ------
dev.write_reg(0x00, SNAP)
ok = True
for off in range(0, 0x50, 8):
    if bytes(dev.read_reg(off, 8)) != SNAP[off:off + 8]:
        ok = False
        break
assert ok, "RESTORE VERIFICATION FAILED"
print("configuration restored (RAM verified byte-for-byte)")

lo_p, lo_r = min(rows, key=lambda r: r[1])
hi_p, hi_r = max(rows, key=lambda r: r[1])
mono = all(a <= b for (_, a), (_, b) in zip(rows, rows[1:]))
print("summary: min %.1f rpm @%d %%   max %.1f rpm @%d %%   monotonic=%s" %
      (lo_r, lo_p, hi_r, hi_p, mono))
print("SWEEP COMPLETE - csv at %s" % CSV_PATH)
