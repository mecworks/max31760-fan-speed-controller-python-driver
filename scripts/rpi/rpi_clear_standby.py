"""One-off recovery: clear a stale STANDBY latch left by a killed diagnostic
run, then soft-POR back to the EEPROM-persisted (factory) configuration and
verify against the known factory CR bytes (CR1=0x19 CR2=0x11 CR3=0x31).

Run on the Pi from the deployment dir:  python3 rpi_clear_standby.py
"""
import sys
import time

sys.path.insert(0, ".")
from max31760.cp import MAX31760

dev = MAX31760(bus=1, addr=0x50)
assert dev.verify(), "chip not responding"
print("standby =", dev.standby)
if dev.standby:
    dev.standby = False
    time.sleep(0.5)
    assert not dev.standby

# Reset RAM to the EEPROM-persisted (factory) configuration.
dev.soft_por(settle_ms=2000)
cr1 = dev.read_reg(0x00, 1)[0]
cr2 = dev.read_reg(0x01, 1)[0]
cr3 = dev.read_reg(0x02, 1)[0]
print("CR1=0x%02X CR2=0x%02X CR3=0x%02X" % (cr1, cr2, cr3))
assert cr1 == 0x19 and cr2 == 0x11 and cr3 == 0x31, "factory CR mismatch"
lt = dev.local_temp_c
rt = dev.remote_temp_c
print("local=%.1f C  remote=%.1f C  duty=%d/255" %
      (lt, rt, dev.actual_duty_raw))
assert lt > 0.0, "local temp still unreadable after POR"
print("RECOVERY: PASS - factory state restored, chip active")
