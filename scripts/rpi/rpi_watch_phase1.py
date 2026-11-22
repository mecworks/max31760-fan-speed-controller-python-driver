"""RPi bench watched-stop test, PHASE 1: put the fan at a KNOWN speed.

Snapshots the full nonvolatile range (0x00..0x4F) to /tmp/watch_snap.bin
(phase 2 restores from it), enters manual mode, drives 100 % duty, lets it
settle, prints the live state, and LEAVES THE FAN RUNNING at full speed.

Purpose: give the operator a visible, audible baseline to confirm BEFORE
the 0 % drop (phase 2). Expected: fan spinning hard (~2300 rpm).

Run on the Pi from the deployment dir:  python3 rpi_watch_phase1.py
Runtime ~10 s. Leaves the fan running; phase 2 completes the experiment.
"""
import sys
import time

sys.path.insert(0, ".")
from max31760.cp import MAX31760

SNAP_FILE = "/tmp/watch_snap.bin"

dev = MAX31760(bus=1, addr=0x50)
assert dev.verify(), "chip not responding"
snap = bytes(dev.read_reg(0x00, 0x50))
with open(SNAP_FILE, "wb") as f:
    f.write(snap)

dev.manual = True
dev.ramp_rate = MAX31760.RAMP_IMMEDIATE
dev.set_duty_pct(100.0)
assert dev.wait_for_duty(100.0, timeout_ms=1500)
time.sleep(8)                                   # settle at full speed

print("manual=%s  commanded=%d/255  actual=%d/255  rpm=%.1f  local=%.1f C" %
      (dev.manual, dev.duty_cmd_raw, dev.actual_duty_raw,
       dev.rpm(1), dev.local_temp_c))
print("PHASE 1: fan HELD at 100 %% - LOOK AT IT NOW (should spin hard)")
