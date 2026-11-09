"""Phase B9 hardware E2E: ALERT service routine (F18) + ideality factor (F19).

Runs ON the Pico (MicroPython). Exercises:
  - IDEALITY FACTOR OBSERVABLE EFFECT: changing IFR away from the factory
    value must shift the remote diode temperature reading measurably
    (the diode junction math scales with the programmed n)
  - FULL ALERT INTERRUPT SERVICE SEQUENCE on real silicon: lower LHS below
    ambient so LHA latches, then walk the datasheet steps:
      2) service_alert() reads SR (identifies cause; device sets ALTMSK)
         4) attend to the condition (raise LHS back above ambient)
         5) clear_alert_mask() unmasks new alerts
Prints PHASE-B9 DEVICE E2E: PASS on success.
"""
import time
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify(), "verify() failed"

# Idempotent factory start
dev.write_reg(0x00, bytes([0x01]))
dev.write_reg(0x01, bytes([0x10]))
dev.write_reg(0x02, bytes([0x03]))
cr3_0 = dev.read_reg(0x02, 1)[0]
assert cr3_0 == 0x03, "not factory state"

# --- ideality factor observable effect ------------------------------------------
ifr_idx_0 = dev.get_ideality_factor_index()
t0 = dev.remote_temp_c
print("factory IFR idx=%d (n=%.4f), remote=%.3f C" %
      (ifr_idx_0, dev.get_ideality_factor(), t0))
idx = dev.set_ideality_factor(0.9844)      # farthest table entry => max shift
time.sleep_ms(500)                         # allow a fresh conversion
t1 = dev.remote_temp_c
print("IFR idx=%d (n=%.4f), remote=%.3f C" % (idx, dev.get_ideality_factor(), t1))
assert idx == 0
shift = t1 - t0
assert shift > 0.25, "remote temp did not shift enough: %+0.3f C" % shift
dev.set_ideality_factor_index(ifr_idx_0)   # restore factory
# NOTE (measured): the bench diode reading settles slowly (~4 s) around an
# IFR change (fixture thermal/electrical coupling); poll until it returns.
t2 = dev.remote_temp_c
for i in range(12):
    if abs(t2 - t0) < 0.5:
        break
    time.sleep_ms(500)
    t2 = dev.remote_temp_c
assert abs(t2 - t0) < 0.5, "factory IFR restore lost (%.3f vs %.3f)" % (t2, t0)
print("ideality factor: OK (shift %+0.3f C, restored)" % shift)

# --- alert mode round-trip --------------------------------------------------------
assert dev.get_alert_mode() == MAX31760.ALERT_MODE_INTERRUPT   # factory
dev.set_alert_mode(MAX31760.ALERT_MODE_FAULT_INDICATOR)
assert dev.get_alert_mode() == MAX31760.ALERT_MODE_FAULT_INDICATOR
dev.set_alert_mode(MAX31760.ALERT_MODE_INTERRUPT)
assert dev.get_alert_mode() == MAX31760.ALERT_MODE_INTERRUPT
print("alert mode: OK")

# --- full ALERT interrupt service sequence (datasheet steps 2/4/5) ----------------
lhs_0 = dev.get_local_high()
ambient = dev.local_temp_c
print("LHS=%.1f C, local die=%.1f C" % (lhs_0, ambient))
assert ambient < lhs_0, "bench hotter than LHS already?"
dev.set_local_high(ambient - 10.0)         # force LHA well below ambient

sr = 0
for i in range(40):                        # up to 20 s for LHA to latch
    time.sleep_ms(500)
    sr = dev.service_alert()               # step 2: read SR (clears it)
    if sr & MAX31760.SR_LHA:
        break
print("service_alert SR=%02X (LHA=bit5 expected)" % sr)
assert sr & MAX31760.SR_LHA, "LHA never latched with LHS below ambient"
assert dev.alert_masked(), "device did not set ALTMSK after the SR read"
print("ALTMSK latched by silicon: OK")

# Step 4: attend to the condition
dev.set_local_high(lhs_0)
time.sleep_ms(1000)                        # let the alarm release

# Step 5: unmask
dev.clear_alert_mask()
assert not dev.alert_masked(), "ALTMSK stuck after clear"
assert dev.get_local_high() == lhs_0
print("alert isr sequence: OK (steps 2/4/5 walked on real silicon)")

# Final sanity: no residual alarms after restore
time.sleep_ms(1000)
sr_final = dev.status_raw()
assert not (sr_final & (MAX31760.SR_LHA | MAX31760.SR_RHA)), \
    "residual high-temp alarm after restore: %02X" % sr_final
print("final SR=%02X clean" % sr_final)

print("PHASE-B9 DEVICE E2E: PASS")
