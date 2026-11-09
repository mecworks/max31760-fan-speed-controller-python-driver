"""Measure TACH2A re-arm latency after CLRFAIL + TACH2 re-enable."""
import time
import machine
from max31760.mp import MAX31760
from max31760._core import REG_SR

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify()

# Ensure factory-ish CR3 (both tach enabled, slow ramp)
cr3_0 = dev.read_reg(0x02, 1)[0]
print("CR3 start=%02X" % cr3_0)
print("SR start=%02X" % dev.read_reg(REG_SR, 1)[0])   # clears any latch

# Restart TACH2 monitoring with a clean slate
dev.write_reg(0x02, bytes([(cr3_0 & ~0x02) | 0x80]))   # TACH2 off + CLRFAIL
t0 = time.ticks_ms()
dev.tach2_enable(True)
print("TACH2 re-enabled at t=0")

seen = False
for i in range(30):                                    # 30 x 500 ms = 15 s
    time.sleep_ms(500)
    sr = dev.read_reg(REG_SR, 1)[0]                    # clear-on-read each poll
    tc2 = dev.read_reg(0x54, 2)
    el = time.ticks_diff(time.ticks_ms(), t0)
    print("t=%4d ms SR=%02X TC2=%04X" % (el, sr, (tc2[0] << 8) | tc2[1]))
    if sr & 0x02:
        seen = True
        break
if not seen:
    print("TACH2A never asserted in 15 s")
else:
    print("TACH2A re-armed after ~%d ms" % el)
print("LATENCY DIAG DONE")
