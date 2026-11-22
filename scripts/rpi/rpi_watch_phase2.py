"""RPi bench watched-stop test, PHASE 2: the 0 % drop, observed.

Starts from phase 1's 100 % hold. Timeline (~50 s total):
  t=0   baseline print (fan at full speed)
  t=8   *** 0 % COMMAND ISSUED - THE MOMENT: does the fan cut out
        within ~1-2 s, or keep spinning at full speed? ***
  t=8..38   pwmv + reported rpm logged every 2 s during the 0 % hold
  t=38  back to 100 %, settle
  end   configuration restored byte-for-byte from /tmp/watch_snap.bin

Operator watches the WHOLE run and reports what the fan physically did
during the 0 % window. Fully reversible.

Run on the Pi from the deployment dir:  python3 rpi_watch_phase2.py
Requires phase 1 to have run (snapshot file present).
"""
import sys
import time

sys.path.insert(0, ".")
from max31760.cp import MAX31760

SNAP_FILE = "/tmp/watch_snap.bin"

dev = MAX31760(bus=1, addr=0x50)
assert dev.verify(), "chip not responding"
with open(SNAP_FILE, "rb") as f:
    SNAP = f.read()
assert len(SNAP) == 0x50, "bad snapshot file"

print("baseline @100%%: pwmv=%d  rpm_reported=%.1f" %
      (dev.actual_duty_raw, dev.rpm(1)))
time.sleep(8)

print("*** COMMANDING 0 %% NOW - WATCH THE FAN ***")
dev.set_duty_pct(0.0)
assert dev.wait_for_duty(0.0, timeout_ms=1500)
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
print("PHASE 2 COMPLETE - report what the fan did during the 0 %% window")
