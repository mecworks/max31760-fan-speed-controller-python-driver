"""Hardware smoke test for the MAX31760 bench.

Exercises the core observable behaviours end-to-end and restores the control
registers when done:
  - chip identity (verify)
  - temperatures (local ~ ambient; remote within a sane band)
  - manual duty sweep 0 -> 100 % with actual-duty confirmation
  - RPM on TACH1 (plausible while spinning)
  - EEPROM save/load round trip of the control block
  - soft POR survival of a saved value
Prints HW SMOKE TEST: PASS on success.
Platform selected automatically (sys.platform):
  rp2     -> MicroPython, I2C0 SDA=GP0  SCL=GP1   (RPi Pico bench)
  esp32   -> MicroPython, I2C0 SDA=GPIO41 SCL=GPIO42 (ESP32 bench)
  linux   -> CPython, SMBus/I2C bus 1 (RPi 3A+ bench, pins 3/5)
Run via:
  pico/esp32:  python -m mpremote connect port:<PORT> run examples/hw_smoke_test.py
  rpi:         python3 examples/hw_smoke_test.py   (needs /dev/i2c-1 access)
"""
import sys
import time

if sys.platform in ("rp2", "esp32"):
    import machine
    from max31760.mp import MAX31760
    if sys.platform == "rp2":                       # RPi Pico (RP2040/RP2350)
        SDA_PIN, SCL_PIN = 0, 1
    else:                                           # ESP32 bench
        SDA_PIN, SCL_PIN = 41, 42
    i2c = machine.I2C(0, scl=machine.Pin(SCL_PIN), sda=machine.Pin(SDA_PIN))
    dev = MAX31760(i2c, addr=0x50)
elif sys.platform.startswith("linux"):              # CPython SBC bench
    from max31760.cp import MAX31760
    dev = MAX31760(bus=1, addr=0x50)
else:
    raise SystemExit("unsupported platform: %s" % sys.platform)

assert dev.verify(), "chip not responding"


def _sleep_ms(ms):
    if hasattr(time, "sleep_ms"):
        time.sleep_ms(ms)
    else:
        time.sleep(ms / 1000.0)


def _wait_rpm_settled(dev, timeout_ms=10000, tol=0.02):
    """Poll rpm(1) until it converges (two samples within tol) or timeout.

    The fan takes several seconds to reach steady-state speed (momentum +
    aerodynamic load); a fixed short settle can catch it mid-spin-up and
    report a misleadingly low value. Returns the settled reading.
    """
    prev = None
    stable = 0
    waited = 0
    while True:
        r = dev.rpm(1)
        if prev is not None and abs(r - prev) <= tol * max(prev, 1.0):
            stable += 1
        else:
            stable = 0
        if stable >= 2 or waited >= timeout_ms:
            return r
        prev = r
        _sleep_ms(500)
        waited += 500

cr1_0 = dev.read_reg(0x00, 1)[0]
cr2_0 = dev.read_reg(0x01, 1)[0]
cr3_0 = dev.read_reg(0x02, 1)[0]

# --- identity / temperature ---------------------------------------------------
lt = dev.local_temp_c
rt = dev.remote_temp_c
print("temps: local %.1f C, remote %.1f C" % (lt, rt))
assert -40.0 < lt < 125.0, "local temp implausible (%.1f)" % lt
assert -40.0 < rt < 150.0, "remote temp implausible (%.1f)" % rt

# --- manual duty sweep ---------------------------------------------------------
dev.manual_enable(True)
dev.set_ramp_rate(MAX31760.RAMP_IMMEDIATE)
for pct in (0.0, 25.0, 50.0, 75.0, 100.0):
    dev.set_duty_pct(pct)
    assert dev.wait_for_duty(pct, timeout_ms=1500), \
        "duty did not reach %.0f%%" % pct
    print("duty %3.0f%% ok (actual %d)" % (pct, dev.get_actual_duty_raw()))

# --- RPM -----------------------------------------------------------------------
rpm = _wait_rpm_settled(dev)          # converge before measuring (spin-up)
print("rpm @100%%: %.1f" % rpm)
assert rpm > 500.0, "fan not spinning (rpm=%.1f)" % rpm

# --- EEPROM round trip -----------------------------------------------------------
sentinel = cr1_0 ^ 0x04                 # flip one CR1 bit as a marker
assert sentinel != cr1_0
dev.write_reg(0x00, bytes([sentinel]))
dev.save_config(MAX31760.EEX_BLOCK_00_0F)
dev.write_reg(0x00, bytes([cr1_0]))     # clobber RAM back
dev.load_config(MAX31760.EEX_BLOCK_00_0F)
got = dev.read_reg(0x00, 1)[0]
print("eeprom round trip: CR1=%02X (expected %02X)" % (got, sentinel))
assert got == sentinel, "EEPROM round trip failed"

# --- soft POR survival ------------------------------------------------------------
dev.soft_por()
got = dev.read_reg(0x00, 1)[0]
print("post-POR CR1=%02X (expected %02X)" % (got, sentinel))
assert got == sentinel, "value did not survive soft POR"

# --- restore ----------------------------------------------------------------------
dev.write_reg(0x00, bytes([cr1_0]))
dev.write_reg(0x01, bytes([cr2_0]))
dev.write_reg(0x02, bytes([cr3_0]))
dev.clear_fan_fail()
assert dev.read_reg(0x00, 1)[0] == cr1_0
assert dev.read_reg(0x01, 1)[0] == cr2_0
assert dev.read_reg(0x02, 1)[0] == cr3_0
print("control registers restored")
# Leave the EEPROM in the restored (pre-test) state too:
dev.save_config(MAX31760.EEX_BLOCK_00_0F)

print("HW SMOKE TEST: PASS")
