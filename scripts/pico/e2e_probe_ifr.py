"""Probe: IFR restore timing on real silicon."""
import time
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify()

ifr_0 = dev.get_ideality_factor_index()
t0 = dev.remote_temp_c
print("start: IFR=%d remote=%.3f" % (ifr_0, t0))

dev.set_ideality_factor(0.9844)
for i in range(8):
    time.sleep_ms(500)
    print("+%d ms: IFR=%d remote=%.3f" % ((i + 1) * 500,
                                          dev.get_ideality_factor_index(),
                                          dev.remote_temp_c))

dev.set_ideality_factor_index(ifr_0)
print("restored IFR=%d" % dev.get_ideality_factor_index())
for i in range(8):
    time.sleep_ms(500)
    print("+%d ms: IFR=%d remote=%.3f" % ((i + 1) * 500,
                                          dev.get_ideality_factor_index(),
                                          dev.remote_temp_c))
print("PROBE DONE")
