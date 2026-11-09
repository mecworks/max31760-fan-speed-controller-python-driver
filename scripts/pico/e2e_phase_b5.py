"""Phase B5 hardware E2E: ramp rate + wait_for_duty vs real chip.

Runs ON the Pico (MicroPython). Demonstrates on silicon:
  - set_ramp_rate/get_ramp_rate round-trips (CR3 bits [5:4])
  - IMMEDIATE ramp: wait_for_duty settles fast after a manual duty command
  - SLOW ramp (3.125 %/s): output slews gradually (measured mid-slew), then
    switching back to IMMEDIATE lets wait_for_duty finish quickly
Prints PHASE-B5 DEVICE E2E: PASS on success.
"""
import time
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify(), "verify() failed"

# Idempotent factory start (interrupted-run safety)
dev.write_reg(0x00, bytes([0x01]))
dev.write_reg(0x01, bytes([0x10]))
dev.write_reg(0x02, bytes([0x03]))
cr3_0 = dev.read_reg(0x02, 1)[0]
assert cr3_0 == 0x03, "not factory state"

# Single-fan bench prep (D11): TACH2 off + fan-fail cleared so manual duty works
cr3_prep = (cr3_0 & ~0x02) | 0x30
dev.write_reg(0x02, bytes([cr3_prep]))
dev.write_reg(0x02, bytes([cr3_prep | 0x80]))   # CLRFAIL

# Ramp-rate API round-trip (prep above left ramp at immediate)
assert dev.get_ramp_rate() == MAX31760.RAMP_IMMEDIATE
for r in (MAX31760.RAMP_MED_SLOW, MAX31760.RAMP_MED_FAST,
          MAX31760.RAMP_IMMEDIATE, MAX31760.RAMP_SLOW):
    dev.set_ramp_rate(r)
    assert dev.get_ramp_rate() == r, "ramp rate lost"
print("ramp_rate round-trips: OK")

dev.manual_enable(True)

# --- IMMEDIATE ramp: settle must be fast -------------------------------------
dev.set_ramp_rate(MAX31760.RAMP_IMMEDIATE)
dev.set_duty_pct(25.0)
t0 = time.ticks_ms()
ok = dev.wait_for_duty(25.0, timeout_ms=2000)
dt_imm = time.ticks_diff(time.ticks_ms(), t0)
assert ok and dt_imm < 500, "immediate ramp too slow (%d ms)" % dt_imm
print("immediate: settled at 25%% in %d ms" % dt_imm)

# --- SLOW ramp (3.125 %/s): verify gradual slew ------------------------------
dev.set_ramp_rate(MAX31760.RAMP_SLOW)
dev.set_duty_pct(75.0)                       # 25 -> 75 needs 16 s at full rate
time.sleep_ms(1000)                          # expect ~3.1 percentage points
mid = dev.get_actual_duty_raw()
lo, hi = 64, 192                             # 25% .. 75% raw bounds
assert lo < mid < hi, "slow ramp not slewing (mid=%d)" % mid
print("slow ramp: after 1 s actual=%d (between %d and %d)" % (mid, lo, hi))

# Switch back to immediate; wait_for_duty must now finish promptly
dev.set_ramp_rate(MAX31760.RAMP_IMMEDIATE)
t1 = time.ticks_ms()
ok = dev.wait_for_duty(75.0, timeout_ms=2000)
dt_fin = time.ticks_diff(time.ticks_ms(), t1)
assert ok and dt_fin < 500, "finish too slow (%d ms)" % dt_fin
print("switched to immediate: finished at 75%% in %d ms" % dt_fin)

# Restore factory control state
dev.manual_enable(False)
dev.write_reg(0x02, bytes([cr3_0]))
assert dev.read_reg(0x02, 1)[0] == cr3_0
print("restored factory CR3")

print("PHASE-B5 DEVICE E2E: PASS")
