"""Restore true factory CR2 (DFC=0) after B11 left DFC set."""
import machine
i = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
i.writeto_mem(0x50, 0x01, b"\x10")
print("CR2=%02X" % i.readfrom_mem(0x50, 0x01, 1)[0])
