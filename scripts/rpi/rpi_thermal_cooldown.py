"""RPi bench thermal diagnostic: duty-modulation check + standby cooldown.

Investigates the elevated local die temperature (~55 C vs ~27 C ambient air;
the remote channel is an OFF-BOARD external PNP transistor, so it reads
ambient, not board temperature). Distinguishes three candidates in one
reversible run:

  A. driver-stage fault (e.g. stuck-on low-side FET from prior miswiring)
     -> phase 1 shows NO duty modulation
  B. fan-motor heat conducted into the click PCB (bench geometry)
     -> phase 1 tracks, phase 2 cools strongly in standby
  C. static/internal dissipation (latent defect / leakage)
     -> phase 1 tracks, phase 2 stays hot in standby

Procedure (fully reversible):
  1. snapshot nonvolatile range 0x00..0x4F
  2. phase 1: manual mode, settled RPM at 50% vs 100% duty
  3. phase 2: enter standby (drive off, fan coasts down), sample
     local/remote/Pi-SoC every 15 s for 3 min
  4. exit standby, restore snapshot byte-for-byte, verify

Run on the Pi from the deployment dir:  python3 rpi_thermal_cooldown.py
(needs access to /dev/i2c-1; use sudo if not in i2c group)
Total runtime ~4 min.
"""
import os
import sys
import time

sys.path.insert(0, ".")
from max31760.cp import MAX31760

BUS = 1
ADDR = 0x50


def pi_soc_c():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except OSError:
        return float("nan")


def settled_rpm(dev, timeout_s=8.0, tol=0.03):
    """Poll rpm(1) until two consecutive samples agree within tol."""
    prev = None
    stable = 0
    waited = 0.0
    while True:
        r = dev.rpm(1)
        if prev is not None and abs(r - prev) <= tol * max(prev, 1.0):
            stable += 1
        else:
            stable = 0
        if stable >= 2 or waited >= timeout_s:
            return r
        prev = r
        time.sleep(0.5)
        waited += 0.5


dev = MAX31760(bus=BUS, addr=ADDR)
assert dev.verify(), "chip not responding"
if dev.standby:                                  # defensive: killed prior run
    print("stale STANDBY detected - clearing")
    dev.standby = False
    time.sleep(0.5)
lt_pre = dev.local_temp_c
assert lt_pre > 0.0, (
    "local temp unreadable (%.1f C) - chip not active?" % lt_pre)
SNAP = dev.read_reg(0x00, 0x50)

print("== phase 1: duty-modulation spot check ==")
print("pre-test local temp = %.1f C" % lt_pre)
dev.manual = True
dev.ramp_rate = MAX31760.RAMP_IMMEDIATE
dev.set_duty_pct(50.0)
assert dev.wait_for_duty(50.0, timeout_ms=1500)
rpm50 = settled_rpm(dev)
dev.set_duty_pct(100.0)
assert dev.wait_for_duty(100.0, timeout_ms=1500)
rpm100 = settled_rpm(dev)
print("rpm @50%%  = %8.1f" % rpm50)
print("rpm @100%% = %8.1f" % rpm100)
if rpm100 > rpm50 * 1.25:
    print("phase 1 verdict: PWM stage TRACKS duty (modulation healthy)")
else:
    print("phase 1 verdict: WARNING - weak/absent duty modulation, "
          "driver stage suspect")

print("")
print("== phase 2: standby cooldown (12 x 15 s) ==")
print("%-6s %-10s %-10s %-10s" % ("t_s", "local_C", "remote_C", "pisoc_C"))
dev.standby = True
assert dev.standby
t0 = time.time()
trend = []
for _ in range(12):
    time.sleep(15)
    lt = dev.local_temp_c
    rt = dev.remote_temp_c
    st = pi_soc_c()
    trend.append(lt)
    print("%-6d %-10.1f %-10.1f %-10.1f" %
          (int(time.time() - t0), lt, rt, st))

dev.standby = False
assert not dev.standby
time.sleep(5)
lt = dev.local_temp_c
rt = dev.remote_temp_c
print("post-standby: local=%.1f C  remote=%.1f C" % (lt, rt))

# ------------------------------------------------------------- restore ------
dev.write_reg(0x00, SNAP)
ok = True
for off in range(0, 0x50, 8):
    if bytes(dev.read_reg(off, 8)) != SNAP[off:off + 8]:
        ok = False
        break
assert ok, "RESTORE VERIFICATION FAILED"
print("configuration restored (RAM verified byte-for-byte)")

first, last = trend[0], trend[-1]
drop = first - last
print("")
print("cooldown: %.1f -> %.1f C over %d s (delta %+.1f C)" %
      (first, last, 15 * 12, drop))
if drop >= 10.0:
    print("VERDICT: strong cooling in standby -> heat tied to ACTIVE DRIVE.")
    print("         Next: repeat with fan DISCONNECTED at 100% duty:")
    print("         heats -> driver-stage loss; stays cool -> motor conduction.")
elif drop <= 3.0:
    print("VERDICT: little/no cooling in standby -> STATIC/internal "
          "dissipation.")
    print("         Consistent with latent defect (prior miswiring).")
    print("         Next: swap power source; consider replacing the click.")
else:
    print("VERDICT: intermediate (%+.1f C) -> rerun with a longer window," % drop)
    print("         or repeat with the fan disconnected to isolate the motor.")
