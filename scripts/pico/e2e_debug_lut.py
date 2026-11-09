"""Debug the LUT matrix section step by step."""
import machine
from max31760.mp import MAX31760, build_lut_curve, lut_index_for_temp

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)

curve = [min(255, int(i * 255 / 47.0)) for i in range(48)]
print("curve[0..3]=%r ... [%d]=%d" % (curve[:4], 47, curve[47]))
dev.lut_set(curve)
got = list(dev.lut_get())
print("bulk match:", got == curve)
if got != curve:
    for i in range(48):
        if got[i] != curve[i]:
            print("first diff at %d: got %d want %d" % (i, got[i], curve[i]))
            break
dev.lut_set_index(25, 0x5A)
print("index round trip:", dev.lut_get_index(25), "(want 90)")
idx = lut_index_for_temp(30.0)
print("index_for_temp(30) =", idx)
c2 = build_lut_curve([(0.0, 0.0), (47.0, 100.0)])
print("curve2 len=%d c2[0]=%d c2[47]=%d" % (len(c2), c2[0], c2[47]))
