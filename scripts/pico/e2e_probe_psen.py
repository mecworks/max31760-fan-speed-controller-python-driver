"""Probe: is the PSEN stretched pulse visible in PWMV at low manual duty?"""
import time
import machine
from max31760.mp import MAX31760
from max31760._core import RAMP_IMMEDIATE

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify()

dev.write_reg(0x00, bytes([0x01]))
dev.write_reg(0x01, bytes([0x10]))
dev.write_reg(0x02, bytes([0x03]))
dev.tach2_enabled = False          # isolate from port-2 fan-fail force
dev.clear_fan_fail()
dev.ramp_rate = RAMP_IMMEDIATE
dev.manual = True
dev.set_duty_pct(5.0)
time.sleep_ms(300)
print("baseline PWMV=%d (manual 5%%)" % dev.actual_duty_raw)

dev.pulse_stretch_enabled = True
traj = []
for i in range(30):             # 3 s @ 100 ms
    traj.append(dev.actual_duty_raw)
    time.sleep_ms(100)
dev.pulse_stretch_enabled = False
print("PWMV trajectory with PSEN on:", traj)

# restore
dev.manual = False
dev.write_reg(0x02, bytes([0x03]))
dev.clear_fan_fail()
print("PROBE DONE")
