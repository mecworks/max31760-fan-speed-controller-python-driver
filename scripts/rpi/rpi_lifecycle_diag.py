"""Step-by-step reproduction of the E2E lifecycle section with per-call
timing, to locate exactly which transaction NACKs on the RPi."""
import sys
import time

sys.path.insert(0, ".")
from max31760.cp import MAX31760

dev = MAX31760(bus=1, addr=0x50)
assert dev.verify()

SNAP = dev.read_reg(0x00, 0x50)


def step(label, fn):
    t0 = time.monotonic()
    try:
        r = fn()
        dt = (time.monotonic() - t0) * 1000.0
        print("OK   %-38s %8.1f ms  %r" % (label, dt, r))
        return r
    except Exception as e:
        dt = (time.monotonic() - t0) * 1000.0
        print("ERR  %-38s %8.1f ms  %s: %s" %
              (label, dt, type(e).__name__, e))
        raise


step("write sentinel CR1", lambda: dev.write_reg(0x00, bytes([SNAP[0] ^ 0x04])))
step("save_config(00-0F)", lambda: dev.save_config(MAX31760.EEX_BLOCK_00_0F))
step("write CR1 back", lambda: dev.write_reg(0x00, bytes([SNAP[0]])))
step("load_config(00-0F)", lambda: dev.load_config(MAX31760.EEX_BLOCK_00_0F))
print("CR1 after load: 0x%02X (expect sentinel 0x%02X)" %
      (dev.read_reg(0x00, 1)[0], SNAP[0] ^ 0x04))
step("eeprom_corrupt", dev.eeprom_corrupt)
step("soft_por", lambda: dev.soft_por())
print("CR1 after POR: 0x%02X" % dev.read_reg(0x00, 1)[0])
step("enter_standby", lambda: dev.enter_standby())
step("standby_active", dev.standby_active)
step("probe in standby", dev.probe)
step("exit_standby", lambda: dev.exit_standby())
step("recover_from_corruption",
     lambda: dev.recover_from_corruption(timeout_ms=2000))
step("eeprom_corrupt final", dev.eeprom_corrupt)

# restore
dev.write_reg(0x00, SNAP)
dev.clear_fan_fail()
dev.save_config(MAX31760.EEX_BLOCK_00_0F)
print("restored")
