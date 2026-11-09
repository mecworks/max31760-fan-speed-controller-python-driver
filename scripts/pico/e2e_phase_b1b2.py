"""Phase B1/B2 hardware E2E: init/self-test + temperatures + setpoints.

Runs ON the Pico (MicroPython). Exercises:
  - verify() self-test (address ACK, F1)
  - scan() bus discovery (F1; expect 0x50 present)
  - local_temp_c / remote_temp_c properties (F2; plausible ambient values)
  - all four setpoint get/set pairs (F3): write distinctive value,
    read back through the API, restore factory default, verify restore
Prints PHASE-B1B2 DEVICE E2E: PASS on success.
"""
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)

# B1: self-test + discovery
assert dev.verify(), "verify() failed"
print("verify: True")
found = dev.scan()
print("scan: " + ", ".join(["0x%02X" % a for a in found]))
assert 0x50 in found, "device missing from scan"

# B2: temperatures
local_c = dev.local_temp_c
remote_c = dev.remote_temp_c
print("local=%.3fC remote=%.3fC" % (local_c, remote_c))
assert -40.0 < local_c < 125.0, "local temp implausible"
assert -40.0 < remote_c < 125.0, "remote temp implausible"

# B2: setpoint round-trips (distinctive test values, then restore factory)
CASES = [
    ("local_high", 60.5, 70.0),
    ("remote_high", 90.0, 85.0),
    ("local_overtemp", 95.25, 85.0),
    ("remote_overtemp", 105.0, 110.0),
]
for name, test_val, factory in CASES:
    g = getattr(dev, "get_" + name)
    s = getattr(dev, "set_" + name)
    assert abs(g() - factory) < 0.01, name + " not at factory default"
    s(test_val)
    got = g()
    print(name + ": set %.3f -> read %.3f" % (test_val, got))
    assert abs(got - test_val) < 0.01, name + " round-trip failed"
    s(factory)
    assert abs(g() - factory) < 0.01, name + " restore failed"

print("PHASE-B1B2 DEVICE E2E: PASS")
