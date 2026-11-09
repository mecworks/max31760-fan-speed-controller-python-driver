"""Diagnostic: dump tach-related state on the bench."""
import time
import machine
from max31760.mp import MAX31760
from max31760._core import REG_SR

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify()

def dump(tag):
    cr3 = dev.read_reg(0x02, 1)[0]
    tc1 = dev.read_reg(0x52, 2)
    tc2 = dev.read_reg(0x54, 2)
    sr = dev.read_reg(REG_SR, 1)[0]
    tct = dev.read_reg(0x0E, 2)
    print("%s: CR3=%02X TC1=%04X TC2=%04X SR=%02X TCT=%04X" % (
        tag, cr3, (tc1[0] << 8) | tc1[1], (tc2[0] << 8) | tc2[1],
        sr, (tct[0] << 8) | tct[1]))

dump("t0")
time.sleep_ms(1500)
dump("t+1.5s")
time.sleep_ms(1500)
dump("t+3s")
print("DIAG DONE")
