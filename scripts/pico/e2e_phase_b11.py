"""Phase B11 hardware E2E: configuration presets (F24).

Runs ON the Pico (MicroPython). Exercises each preset on real silicon with
observable effects:
  - configure_4wire_fan(): 25 kHz selected, manual 50 % duty reaches the
    output (PWMV ~128) and the live fan reads a plausible RPM at 25 kHz
  - configure_3wire_supply_modulation(): 33 Hz + PSEN; measure_tach_once()
    returns a valid count through the pulse-stretch path
  - configure_two_fans(): both tachometers armed; the dead port-2 fault
    detector latches TACH2A within its ~8 s re-arm window (proof that
    enabling TACH2 monitoring actually arms the detector)
Restores factory CR1/CR3 at the end.
Prints PHASE-B11 DEVICE E2E: PASS on success.
"""
import time
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify(), "verify() failed"

cr1_0 = dev.read_reg(0x00, 1)[0]
cr2_0 = dev.read_reg(0x01, 1)[0]
cr3_0 = dev.read_reg(0x02, 1)[0]
print("factory CR1=%02X CR2=%02X CR3=%02X" % (cr1_0, cr2_0, cr3_0))
# NOTE: factory CR2 has DFC=0 => automatic LUT mode governs the output.
# Manual-duty assertions below require manual_enable(True).
# Also force the immediate ramp so duty transitions are prompt (restored
# at the end); the presets themselves do not touch the ramp rate.
dev.set_ramp_rate(MAX31760.RAMP_IMMEDIATE)

# --- preset 1: 4-wire fan -------------------------------------------------------
dev.configure_4wire_fan(port=1)
dev.manual_enable(True)
cr1 = dev.read_reg(0x00, 1)[0]
cr3 = dev.read_reg(0x02, 1)[0]
print("4wire preset: CR1=%02X CR3=%02X" % (cr1, cr3))
assert cr1 & 0x18 == 0x18, "25 kHz not selected"
assert cr3 & 0x01 and not (cr3 & 0x02), "TACH1/TACH2 bits wrong"
time.sleep_ms(200)
dev.set_duty_pct(50.0)
pv = dev.get_actual_duty_raw()
for i in range(10):
    if 120 <= pv <= 136:
        break
    time.sleep_ms(200)
    pv = dev.get_actual_duty_raw()
rpm_half = dev.rpm(1)
print("4wire @50%%: PWMV=%d, rpm=%.1f (after %d x 200 ms settle)" %
      (pv, rpm_half, i + 1))
if not (120 <= pv <= 136):
    print("DIAG: SR=%02X CR2=%02X CR3=%02X FFDC=%02X" %
          (dev.status_raw(), dev.read_reg(0x01, 1)[0],
           dev.read_reg(0x02, 1)[0], dev.get_ffdc_raw()))
assert 120 <= pv <= 136, "PWMV off target at 50 %% (%d)" % pv
# Causality check: raising the duty must raise the fan speed
# (a real 4-wire fan at 50 % duty spins well below its full speed).
dev.set_duty_pct(100.0)
time.sleep_ms(2000)                       # let the fan accelerate
rpm_full = dev.rpm(1)
print("4wire @100%%: rpm=%.1f (was %.1f at 50%%)" % (rpm_full, rpm_half))
assert rpm_full > rpm_half * 1.3, \
    "fan did not speed up with duty (%.1f -> %.1f)" % (rpm_half, rpm_full)
print("configure_4wire_fan: OK")

# --- preset 2: 3-wire supply modulation ------------------------------------------
dev.configure_3wire_supply_modulation(port=1)
dev.manual_enable(True)
cr1 = dev.read_reg(0x00, 1)[0]
cr3 = dev.read_reg(0x02, 1)[0]
print("3wire preset: CR1=%02X CR3=%02X" % (cr1, cr3))
assert cr1 & 0x18 == 0x00, "33 Hz not selected"
assert cr3 & 0x04, "PSEN not set"
dev.set_duty_pct(50.0)
time.sleep_ms(300)
cnt = dev.measure_tach_once(port=1, timeout_ms=3000)
rpm = dev.rpm(1)
print("3wire one-shot: TC=%04X, rpm=%.1f" % (cnt, rpm))
assert cnt > 0, "measure_tach_once returned no count"
assert 1000.0 < rpm < 3500.0, "implausible RPM (%.1f)" % rpm
print("configure_3wire_supply_modulation: OK")

# --- preset 3: two fans ------------------------------------------------------------
dev.configure_two_fans()
cr3 = dev.read_reg(0x02, 1)[0]
print("twofans preset: CR3=%02X" % cr3)
assert cr3 & 0x03 == 0x03, "both TACH enables missing"
# Dead port 2 must now latch TACH2A within its ~8 s re-arm window
sr = 0
for i in range(24):                        # up to 12 s
    time.sleep_ms(500)
    sr = dev.status_raw()
    if sr & MAX31760.SR_TACH2A:
        break
print("two-fans: SR=%02X after %d x 500 ms (TACH2A expected)" %
      (sr, i + 1))
assert sr & MAX31760.SR_TACH2A, "TACH2 alarm never latched with TACH2 enabled"
print("configure_two_fans: OK (port-2 fault detector armed)")

# --- restore ------------------------------------------------------------------------
dev.write_reg(0x00, bytes([cr1_0]))
dev.write_reg(0x01, bytes([cr2_0]))
dev.write_reg(0x02, bytes([cr3_0]))
dev.clear_fan_fail()
assert dev.read_reg(0x00, 1)[0] == cr1_0
assert dev.read_reg(0x01, 1)[0] == cr2_0
assert dev.read_reg(0x02, 1)[0] == cr3_0
print("restored factory CR1/CR2/CR3")
print("PHASE-B11 DEVICE E2E: PASS")
