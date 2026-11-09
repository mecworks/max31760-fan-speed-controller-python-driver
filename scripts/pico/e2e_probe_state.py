"""Quick live-state probe: CR2/DFC, PWMR/PWMV, LUT around ambient."""
import machine
i = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
def hx(b):
    return " ".join("%02X" % x for x in b)

print("CR2=%02X (DFC=%d)" % (i.readfrom_mem(0x50, 0x01, 1)[0],
                             i.readfrom_mem(0x50, 0x01, 1)[0] & 0x01))
print("PWMR=%02X PWMV=%02X" % (i.readfrom_mem(0x50, 0x50, 1)[0],
                               i.readfrom_mem(0x50, 0x51, 1)[0]))
print("LUT[24..31]=", hx(i.readfrom_mem(0x50, 0x38, 8)))
print("local temp raw:", hx(i.readfrom_mem(0x50, 0x58, 2)))
