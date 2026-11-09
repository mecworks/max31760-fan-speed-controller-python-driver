"""Phase B7 hardware E2E: fault handling, status, FFDC, modes, alert mask.

Runs ON the Pico (MicroPython). Exercises:
  - status_raw() (SR @ 0x5A, clear-on-read) + named flags
  - remote_diode_fault() (bench diode healthy => False)
  - FFDC OBSERVABLE EFFECT: with the persistent TACH2 fan-fail active
    (no fan on port 2), lowering FFDC must drag the ACTUAL output (PWMV)
    down with it, proving the force path independent of LUT/manual duty
  - clear_fan_fail() + measured ~8 s re-arm latency via the public API
  - FF_0, FF mode, RD mode/polarity, alert-mask round-trips + restores
Prints PHASE-B7 DEVICE E2E: PASS on success.
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

# --- status -------------------------------------------------------------------
sr = dev.status_raw()
print("status_raw=%02X (TACH2A expected from boot)" % sr)
assert sr & MAX31760.SR_TACH2A, "TACH2A not latched?"
assert not dev.remote_diode_fault(), "healthy diode flagged faulty"
print("status + remote diode check: OK")

# --- FFDC observable effect -----------------------------------------------------
# Persistent TACH2 fan-fail forces the output to FFDC (factory 0xFF = 100 %).
# Ensure the latch is actually active first (re-arm can take ~8 s).
# NB: status_raw() clears SR on read; use the captured value.
guard = 0
sr_guard = dev.status_raw()
while not (sr_guard & MAX31760.SR_TACH2A) and guard < 40:
    time.sleep_ms(500)
    sr_guard = dev.status_raw()
    guard += 1
assert sr_guard & MAX31760.SR_TACH2A, "TACH2A never latched"
pwmv_0 = dev.get_actual_duty_raw()
print("PWMV with FFDC=FF: %d" % pwmv_0)
assert pwmv_0 == 255, "expected full speed under fan-fail force"
dev.set_ffdc_pct(50.0)
deadline = 0
while dev.get_actual_duty_raw() != 128 and deadline < 40:
    time.sleep_ms(50)
    deadline += 1
pwmv_mid = dev.get_actual_duty_raw()
print("PWMV with FFDC=50%%: %d" % pwmv_mid)
assert pwmv_mid == 128, "output did not follow FFDC (force path dead?)"
dev.set_ffdc_raw(0xFF)
deadline = 0
while dev.get_actual_duty_raw() != 255 and deadline < 40:
    time.sleep_ms(50)
    deadline += 1
assert dev.get_actual_duty_raw() == 255, "FFDC restore lost"
assert dev.get_ffdc_raw() == 0xFF
print("ffdc force path: OK (output followed FFDC 255->128->255)")

# --- clear_fan_fail + re-arm latency -------------------------------------------
dev.clear_fan_fail()
t0 = time.ticks_ms()
armed = False
for _ in range(40):                                # up to 20 s
    time.sleep_ms(500)
    if dev.status_raw() & MAX31760.SR_TACH2A:
        armed = True
        break
el = time.ticks_diff(time.ticks_ms(), t0)
print("TACH2A re-armed after %d ms" % el)
assert armed, "TACH2A did not re-latch within 20 s"
assert el >= 5000, "re-arm suspiciously fast (%d ms)" % el
print("clear_fan_fail + re-arm: OK")

# --- FF_0 / FF mode / RD mode / polarity round-trips ----------------------------
assert not dev.ff_zero_detection()
dev.set_ff_zero_detection(True)
assert dev.ff_zero_detection()
dev.set_ff_zero_detection(False)
assert not dev.ff_zero_detection()
print("ff_zero: OK")

assert dev.get_ff_mode() == MAX31760.FF_MODE_COMPARATOR   # factory
dev.set_ff_mode(MAX31760.FF_MODE_INTERRUPT)
assert dev.get_ff_mode() == MAX31760.FF_MODE_INTERRUPT
dev.set_ff_mode(MAX31760.FF_MODE_COMPARATOR)
assert dev.get_ff_mode() == MAX31760.FF_MODE_COMPARATOR
print("ff_mode: OK")

assert not dev.rd_mode_enabled()
assert not dev.get_rd_polarity()
dev.set_rd_mode(True)
dev.set_rd_polarity(True)
assert dev.rd_mode_enabled() and dev.get_rd_polarity()
dev.set_rd_mode(False)
dev.set_rd_polarity(False)
assert not dev.rd_mode_enabled() and not dev.get_rd_polarity()
print("rd_mode+polarity: OK")

# --- alert mask ------------------------------------------------------------------
mask_0 = dev.get_alert_mask()
assert mask_0 == 0x00, "factory mask unexpected: 0x%02X" % mask_0
dev.set_alert_mask(MAX31760.SR_TACH1A | MAX31760.SR_TACH2A)
assert dev.get_alert_mask() == 0x03
dev.set_alert_mask(0)
assert dev.get_alert_mask() == 0x00
print("alert_mask: OK")

# Restore factory control state + clear any latched faults
dev.write_reg(0x02, bytes([cr3_0]))
assert dev.read_reg(0x02, 1)[0] == cr3_0
dev.clear_fan_fail()
print("restored factory CR3")

print("PHASE-B7 DEVICE E2E: PASS")
