"""Phase B4 hardware E2E: manual/auto modes, duty, PWM config vs real chip.

Runs ON the Pico (MicroPython). Exercises:
  - manual_enable()/manual_enabled() (CR2.DFC)
  - set_duty_pct/get_duty_cmd_raw/get_actual_duty_* with OBSERVABLE EFFECT:
    actual output duty (PWMV) must slew from 255 to 128 (fan slows audibly)
  - index source / hysteresis / PWM frequency / polarity round-trips
  - full restore of factory CR1/CR2/CR3 state
Prints PHASE-B4 DEVICE E2E: PASS on success.
"""
import time
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify(), "verify() failed"

# Idempotent start: force factory control-register state in case a previous
# run was interrupted mid-test (then verify the restore took).
dev.write_reg(0x00, bytes([0x01]))
dev.write_reg(0x01, bytes([0x10]))
dev.write_reg(0x02, bytes([0x03]))
cr1_0 = dev.read_reg(0x00, 1)[0]
cr2_0 = dev.read_reg(0x01, 1)[0]
cr3_0 = dev.read_reg(0x02, 1)[0]
print("baseline CR1=%02X CR2=%02X CR3=%02X" % (cr1_0, cr2_0, cr3_0))
assert cr1_0 == 0x01 and cr2_0 == 0x10 and cr3_0 == 0x03, "not factory state"

# Ramp to immediate so the duty slewing is observable within the test window.
# SINGLE-FAN BENCH PREP (D11): with no fan on port 2, the persistent TACH2A
# latches fan-fail after 3 detections and FORCES the output to FFDC (100%),
# overriding even manual duty. Disable TACH2E and clear the fan-fail latch.
cr3_prep = (cr3_0 & ~0x02) | 0x30
dev.write_reg(0x02, bytes([cr3_prep]))
dev.write_reg(0x02, bytes([cr3_prep | 0x80]))   # CLRFAIL (self-clearing)
print("prep: TACH2 disabled, fan-fail cleared")

assert not dev.manual, "DFC unexpectedly set"
start_pwmv = dev.actual_duty_raw
print("auto-mode PWMV start=%d" % start_pwmv)
assert start_pwmv == 255, "expected 100%% in auto mode (LUT all FF)"

# Manual mode: command 50 %, watch the ACTUAL output follow
dev.manual = True
assert dev.manual
dev.set_duty_pct(50.0)
assert dev.duty_cmd_raw == 128, "PWMR command lost"
deadline = 0
while dev.actual_duty_raw != 128 and deadline < 60:
    time.sleep_ms(50)
    deadline += 1
end_pwmv = dev.actual_duty_raw
print("manual 50%%: cmd=128 actual=%d (was %d)" % (end_pwmv, start_pwmv))
assert end_pwmv == 128, "actual duty did not reach commanded value"
assert abs(dev.actual_duty_pct - 50.0) < 0.01

# Auto-mode configuration round-trips (restore factory each time)
src = dev.index_source
dev.index_source = MAX31760.INDEX_MAX
assert dev.index_source == MAX31760.INDEX_MAX
dev.index_source = src
assert dev.index_source == src
print("index_source: OK")

hys = dev.hysteresis_c
dev.hysteresis_c = 4
assert dev.hysteresis_c == 4
dev.hysteresis_c = hys
assert dev.hysteresis_c == hys
print("hysteresis: OK")

freq = dev.pwm_freq_hz
dev.pwm_freq_hz = MAX31760.PWM_FREQ_25KHZ
assert dev.pwm_freq_hz == MAX31760.PWM_FREQ_25KHZ
dev.pwm_freq_hz = freq
assert dev.pwm_freq_hz == freq
print("pwm_freq: OK")

pol = dev.pwm_polarity
dev.pwm_polarity = MAX31760.POLARITY_NEGATIVE
assert dev.pwm_polarity == MAX31760.POLARITY_NEGATIVE
dev.pwm_polarity = pol
assert dev.pwm_polarity == pol
print("polarity: OK")

# Back to automatic mode; verify full factory-state restore
dev.manual = False
assert not dev.manual
dev.write_reg(0x02, bytes([cr3_0]))
assert dev.read_reg(0x00, 1)[0] == cr1_0, "CR1 not restored"
assert dev.read_reg(0x01, 1)[0] == cr2_0, "CR2 not restored"
assert dev.read_reg(0x02, 1)[0] == cr3_0, "CR3 not restored"
print("restored factory control registers")

print("PHASE-B4 DEVICE E2E: PASS")
