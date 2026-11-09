"""Restore factory control-register state after an interrupted E2E run."""
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify()
dev.write_reg(0x00, bytes([0x01]))   # CR1 factory
dev.write_reg(0x01, bytes([0x10]))   # CR2 factory
dev.write_reg(0x02, bytes([0x03]))   # CR3 factory
dev.write_reg(0x02, bytes([0x83]))   # CLRFAIL (self-clearing)
print("CR1=%02X CR2=%02X CR3=%02X" % (
    dev.read_reg(0x00, 1)[0], dev.read_reg(0x01, 1)[0], dev.read_reg(0x02, 1)[0]))
print("RESTORE OK")
