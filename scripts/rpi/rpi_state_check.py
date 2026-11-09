"""Verify/restore factory CR1 on the RPi bench chip."""
import sys

sys.path.insert(0, ".")
from max31760.cp import MAX31760

d = MAX31760(bus=1, addr=0x50)
assert d.verify()
cr1, cr2, cr3 = [d.read_reg(r, 1)[0] for r in (0, 1, 2)]
print("CR1=%02X CR2=%02X CR3=%02X" % (cr1, cr2, cr3))
if cr1 != 0x19:
    d.write_reg(0x00, bytes([0x19]))
    d.save_config(MAX31760.EEX_BLOCK_00_0F)
    print("restored CR1 -> %02X" % d.read_reg(0x00, 1)[0])
else:
    print("chip already at factory CR1")
