"""Phase B3 hardware E2E: LUT get/set + curve builder against the real chip.

Runs ON the Pico (MicroPython). Exercises:
  - lut_get() factory state (48 x 0xFF)
  - build_lut_curve() on-device (float math sanity on MicroPython)
  - lut_set()/lut_get() 48-byte bulk round-trip (page-chunked writes)
  - lut_set_index()/lut_get_index() single-entry access
  - restore of the factory LUT
Prints PHASE-B3 DEVICE E2E: PASS on success.
"""
import machine
from max31760.mp import MAX31760, build_lut_curve, lut_index_for_temp

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify(), "verify() failed"

# Factory state
factory = dev.lut_get()
assert len(factory) == 48 and all(v == 0xFF for v in factory), "LUT not factory"
print("factory LUT: 48 x FF")

# Curve builder on-device: 50 % @20 C -> 100 % @40 C
# (keeps the bench fan healthy at ~ambient while proving non-flat output)
curve = build_lut_curve([(20.0, 50.0), (40.0, 100.0)])
assert len(curve) == 48
idx = lut_index_for_temp(27.0)
exp = curve[idx]
print("curve[%d] (t~%.0fC) = %d (%.1f%%)"
      % (idx, 17.0 + 2.0 * idx, exp, exp * 100.0 / 256.0))
assert 0 < exp < 255, "curve degenerate"

# Bulk round-trip (48 bytes => six page-aligned wire writes)
dev.lut_set(curve)
got = dev.lut_get()
assert got == list(curve), "bulk LUT round-trip mismatch"
print("bulk round-trip: OK")

# Single-entry access
dev.lut_set_index(20, 0x5A)
assert dev.lut_get_index(20) == 0x5A, "single-entry write lost"
assert dev.lut_get_index(21) == curve[21], "neighbour disturbed"
print("single-entry: OK")

# Restore factory LUT
dev.lut_set([0xFF] * 48)
assert all(v == 0xFF for v in dev.lut_get()), "restore failed"
print("restored factory LUT")

print("PHASE-B3 DEVICE E2E: PASS")
