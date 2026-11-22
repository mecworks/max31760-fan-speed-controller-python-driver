"""RPi bench manual-watch helper: ONE change per invocation.

Usage:
  python3 rpi_watch_step.py zero     # command 0 % duty, hold 6 s, print state
                                     # LEAVES THE BENCH AT 0 % DUTY
  python3 rpi_watch_step.py restore  # restore byte-for-byte from
                                     # /tmp/watch_snap.bin (made by phase 1)

Protocol: operator looks at the fan AFTER each step and reports what the
blades are doing before the next step is issued.
"""
import sys
import time

sys.path.insert(0, ".")
from max31760.cp import MAX31760

SNAP_FILE = "/tmp/watch_snap.bin"
dev = MAX31760(bus=1, addr=0x50)
assert dev.verify(), "chip not responding"

if len(sys.argv) != 2 or sys.argv[1] not in ("zero", "restore"):
    raise SystemExit(__doc__)

if sys.argv[1] == "zero":
    dev.set_duty_pct(0.0)
    assert dev.wait_for_duty(0.0, timeout_ms=1500)
    time.sleep(6.0)
    print("commanded=%d/255  actual(pwmv)=%d/255  rpm_reported=%.1f  local=%.1f C" %
          (dev.duty_cmd_raw, dev.actual_duty_raw, dev.rpm(1),
           dev.local_temp_c))
    print("BENCH LEFT AT 0 %% DUTY - LOOK AT THE FAN NOW")
else:
    with open(SNAP_FILE, "rb") as f:
        snap = f.read()
    assert len(snap) == 0x50, "bad snapshot file"
    dev.write_reg(0x00, snap)
    ok = True
    for off in range(0, 0x50, 8):
        if bytes(dev.read_reg(off, 8)) != snap[off:off + 8]:
            ok = False
            break
    assert ok, "RESTORE VERIFICATION FAILED"
    print("configuration restored (RAM verified byte-for-byte)")
    print("post-restore: commanded=%d/255  actual=%d/255  rpm_reported=%.1f" %
          (dev.duty_cmd_raw, dev.actual_duty_raw, dev.rpm(1)))
