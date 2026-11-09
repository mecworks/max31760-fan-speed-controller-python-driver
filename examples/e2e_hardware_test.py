"""C6 E2E hardware matrix: systematically exercise EVERY public API method on
the connected bench with observable-effect verification.

Self-restoring: snapshots the full nonvolatile range (0x00..0x4F) at start and
restores it (RAM + EEPROM block 00-0F) at the end. Port-2/TACH2 FUNCTIONAL
items are EXCLUDED-HW (no second fan on the bench) — only API contracts and
register effects are asserted there.
Platform selected automatically (sys.platform):
  rp2     -> MicroPython, I2C0 SDA=GP0  SCL=GP1   (RPi Pico bench)
  esp32   -> MicroPython, I2C0 SDA=GPIO41 SCL=GPIO42 (ESP32 bench)
  linux   -> CPython, SMBus/I2C bus 1 (RPi 3A+ bench, pins 3/5)
Run via:
  pico/esp32:  python -m mpremote connect port:<PORT> run examples/e2e_hardware_test.py
  rpi:         python3 examples/e2e_hardware_test.py   (needs /dev/i2c-1 access)
Prints one PASS/FAIL line per section and E2E HARDWARE MATRIX: PASS overall.
"""
import sys
import time

if sys.platform in ("rp2", "esp32"):
    import machine
    from max31760.mp import MAX31760, build_lut_curve, lut_index_for_temp
    if sys.platform == "rp2":                       # RPi Pico (RP2040/RP2350)
        SDA_PIN, SCL_PIN = 0, 1
    else:                                           # ESP32 bench
        SDA_PIN, SCL_PIN = 41, 42
    i2c = machine.I2C(0, scl=machine.Pin(SCL_PIN), sda=machine.Pin(SDA_PIN))
    dev = MAX31760(i2c, addr=0x50)
elif sys.platform.startswith("linux"):              # CPython SBC bench
    from max31760.cp import MAX31760, build_lut_curve, lut_index_for_temp
    dev = MAX31760(bus=1, addr=0x50)
else:
    raise SystemExit("unsupported platform: %s" % sys.platform)

assert dev.verify(), "chip not responding"


def _ticks_ms():
    if hasattr(time, "ticks_ms"):                   # MicroPython
        return time.ticks_ms()
    return int(time.monotonic() * 1000)


def _ticks_diff(a, b):
    if hasattr(time, "ticks_diff"):
        return time.ticks_diff(a, b)
    return a - b


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

SNAP = dev.read_reg(0x00, 0x50)          # full nonvolatile range
results = []


def section(name, fn):
    t0 = _ticks_ms()
    try:
        fn()
        results.append((name, "PASS", ""))
    except AssertionError as e:
        results.append((name, "FAIL", str(e)))
    except Exception as e:                       # noqa: broad by design
        results.append((name, "ERROR", "%s: %s" % (type(e).__name__, e)))
    print("[%s] %s (%d ms)%s" %
          (results[-1][1], name, _ticks_diff(_ticks_ms(), t0),
           (" - " + results[-1][2]) if results[-1][2] else ""))


# ---------------------------------------------------------------- identity ----
def s_identity():
    assert dev.probe()
    assert 0x50 in dev.scan()
    dev.user_memory_set(0, 0xA5)
    assert dev.user_memory_get(0) == 0xA5
    dev.user_memory_write_all(b"\x11\x22\x33\x44\x55\x66\x77\x88")
    got = dev.user_memory_read_all()
    assert len(got) == 8 and got[3] == 0x44 and got[7] == 0x88
section("identity/probe/scan/user-memory", s_identity)

# --------------------------------------------------------------- temperature --
def s_temperature():
    lt = dev.local_temp_c
    rt = dev.remote_temp_c
    assert -40.0 < lt < 125.0, "local %.1f implausible" % lt
    assert -40.0 < rt < 150.0, "remote %.1f implausible" % rt
    for setter, getter, val in ((dev.set_local_high, dev.get_local_high, 55.0),
                                (dev.set_local_overtemp, dev.get_local_overtemp, 90.0),
                                (dev.set_remote_high, dev.get_remote_high, 60.0),
                                (dev.set_remote_overtemp, dev.get_remote_overtemp, 95.0)):
        setter(val)
        assert abs(getter() - val) < 0.2, "setpoint round trip failed"
    dev.set_hysteresis_c(2.0)                  # CR1.HYST: 2 or 4 C only
    assert abs(dev.get_hysteresis_c() - 2.0) < 0.2
    dev.set_index_source(MAX31760.INDEX_REMOTE)
    assert dev.get_index_source() == MAX31760.INDEX_REMOTE
    dev.set_index_source(MAX31760.INDEX_LOCAL)
    assert dev.get_index_source() == MAX31760.INDEX_LOCAL
section("temperature/setpoints/index-source", s_temperature)

# ------------------------------------------------------------ manual control --
def s_manual_control():
    dev.manual_enable(True)
    assert dev.manual_enabled()
    dev.set_ramp_rate(MAX31760.RAMP_IMMEDIATE)
    assert dev.get_ramp_rate() == MAX31760.RAMP_IMMEDIATE
    dev.set_duty_raw(200)
    assert dev.get_duty_cmd_raw() == 200
    dev.set_duty_pct(50.0)
    assert dev.wait_for_duty(50.0, timeout_ms=1500)
    assert dev.get_actual_duty_raw() == 128
    assert abs(dev.get_actual_duty_pct() - 50.0) < 0.5
    dev.set_pwm_freq_hz(MAX31760.PWM_FREQ_150HZ)
    assert dev.get_pwm_freq_hz() == MAX31760.PWM_FREQ_150HZ
    dev.set_pwm_polarity(MAX31760.POLARITY_NEGATIVE)
    assert dev.get_pwm_polarity() == MAX31760.POLARITY_NEGATIVE
    dev.set_pwm_polarity(MAX31760.POLARITY_POSITIVE)
    assert dev.get_pwm_polarity() == MAX31760.POLARITY_POSITIVE
section("manual-mode/duty/ramp/freq/polarity", s_manual_control)

# ----------------------------------------------------------------------- LUT --
def s_lut():
    curve = [min(255, int(i * 255 / 47.0)) for i in range(48)]
    dev.lut_set(curve)
    got = list(dev.lut_get())
    assert got == curve, "LUT bulk round trip failed"
    dev.lut_set_index(25, 0x5A)
    assert dev.lut_get_index(25) == 0x5A
    idx = lut_index_for_temp(30.0)
    assert 0 <= idx <= 47
    # Breakpoints placed at the first/last window midpoints (17 C / 111 C)
    # so the endpoint entries are exact.
    c2 = build_lut_curve([(17.0, 0.0), (111.0, 100.0)])   # (temp_c, pct)
    assert len(c2) == 48 and c2[0] == 0 and c2[47] == 255
    assert all(a <= b for a, b in zip(c2, c2[1:])), "curve not monotonic"
section("lut/bulk+index/helpers", s_lut)

# -------------------------------------------------------------------- tach/RPM -
def s_tach():
    dev.tach1_enable(True)
    assert dev.tach1_enabled()
    dev.set_duty_pct(100.0)
    assert dev.wait_for_duty(100.0, timeout_ms=1500)
    rpm = _wait_rpm_settled(dev)      # converge before measuring (spin-up)
    assert rpm > 500.0, "fan not spinning (rpm=%.1f)" % rpm
    dev.set_tach_threshold(1000)
    assert dev.get_tach_threshold() == 1000
    # port 2: EXCLUDED-HW functionally (no fan); contract checks only
    dev.tach2_enable(False)
    assert not dev.tach2_enabled()
    assert dev.rpm(2) >= 0.0                    # no exception, sane value
section("tach1/rpm/threshold (+port2 EXCLUDED-HW)", s_tach)

# -------------------------------------------------------- 3-wire one-shot ------
def s_one_shot():
    dev.configure_3wire_supply_modulation(port=1)
    assert dev.pulse_stretch_enabled()
    cnt = dev.measure_tach_once(port=1, timeout_ms=3000)
    assert cnt > 0, "one-shot returned no count"
    dev.pulse_stretch_enable(False)
    assert not dev.pulse_stretch_enabled()
section("3-wire one-shot measure_tach_once", s_one_shot)

# --------------------------------------------------------------------- faults --
def s_faults():
    sr = dev.status_raw()
    assert isinstance(sr, int) and 0 <= sr <= 255
    assert not dev.remote_diode_fault()         # diode connected on bench
    dev.clear_fan_fail()
    al = dev.active_alarms()                    # F16 compact bitmask
    assert al == 0, "unexpected alarms %02X after CLRFAIL" % al
    dev.set_ffdc_raw(128)
    assert dev.get_ffdc_raw() == 128
    dev.set_ffdc_pct(25.0)
    assert dev.get_ffdc_raw() == 64
    dev.set_ff_zero_detection(True)
    assert dev.ff_zero_detection()
    dev.set_ff_mode(MAX31760.FF_MODE_COMPARATOR)
    assert dev.get_ff_mode() == MAX31760.FF_MODE_COMPARATOR
    dev.set_rd_mode(True)
    assert dev.rd_mode_enabled()
    dev.set_rd_mode(False)
    assert not dev.rd_mode_enabled()
    dev.set_rd_polarity(False)
    assert dev.get_rd_polarity() is False
    mask = MAX31760.SR_ALARM_MASK & ~MAX31760.SR_RDFA
    dev.set_alert_mask(mask)
    assert dev.get_alert_mask() == mask
section("fault-domain round trips", s_faults)

# ---------------------------------------------------------- alerts/ideality ----
def s_alerts():
    dev.set_alert_mode(MAX31760.ALERT_MODE_FAULT_INDICATOR)
    assert dev.get_alert_mode() == MAX31760.ALERT_MODE_FAULT_INDICATOR
    dev.set_alert_mode(MAX31760.ALERT_MODE_INTERRUPT)
    assert dev.get_alert_mode() == MAX31760.ALERT_MODE_INTERRUPT
    sr = dev.service_alert()
    assert isinstance(sr, int)
    dev.clear_alert_mask()
    assert not dev.alert_masked()
    dev.set_ideality_factor_index(0x00)
    assert dev.get_ideality_factor_index() == 0x00
    n = dev.get_ideality_factor()
    assert abs(n - MAX31760.IDEALITY_TABLE[0]) < 1e-6
    idx = dev.set_ideality_factor(1.0)
    best = min(range(64), key=lambda i: abs(MAX31760.IDEALITY_TABLE[i] - 1.0))
    assert idx == best, "nearest-match index wrong"
    assert abs(dev.get_ideality_factor() - 1.0) < 0.005
section("alert-mode/service/ideality", s_alerts)

# ------------------------------------------------------------------- lifecycle -
def s_lifecycle():
    sentinel = SNAP[0] ^ 0x04
    dev.write_reg(0x00, bytes([sentinel]))
    dev.save_config(MAX31760.EEX_BLOCK_00_0F)
    dev.write_reg(0x00, bytes([SNAP[0]]))
    dev.load_config(MAX31760.EEX_BLOCK_00_0F)
    assert dev.read_reg(0x00, 1)[0] == sentinel, "EEPROM round trip failed"
    assert not dev.eeprom_corrupt()
    dev.soft_por()
    assert dev.read_reg(0x00, 1)[0] == sentinel, "POR survival failed"
    dev.enter_standby()
    assert dev.standby_active()
    assert dev.probe()                          # I2C alive in standby
    dev.exit_standby()
    assert not dev.standby_active()
    dev.recover_from_corruption(timeout_ms=2000)   # clean no-op path
    assert not dev.eeprom_corrupt()
section("eeprom/por/standby/recovery", s_lifecycle)

# -------------------------------------------------------------------- assists --
def s_assists():
    dev.spin_up_enable(True)
    assert dev.spin_up_enabled()
    dev.spin_up_enable(False)
    assert not dev.spin_up_enabled()
    dev.tacho_full_enable(True)
    assert dev.tacho_full_enabled()
    dev.tacho_full_enable(False)
    assert not dev.tacho_full_enabled()
section("spin-up/tacho-full bits", s_assists)

# -------------------------------------------------------------------- presets --
def s_presets():
    dev.configure_4wire_fan(port=1)
    cr1 = dev.read_reg(0x00, 1)[0]
    cr3 = dev.read_reg(0x02, 1)[0]
    assert cr1 & 0x18 == 0x18, "preset did not select 25 kHz"
    assert cr3 & 0x01 and not (cr3 & 0x02), "preset TACH bits wrong"
    dev.configure_two_fans()
    cr3 = dev.read_reg(0x02, 1)[0]
    assert cr3 & 0x03 == 0x03, "two-fans preset missing TACH enables"
section("presets register effects", s_presets)

# ---------------------------------------------------------------- error model --
def s_errors():
    def expect_value_error(fn):
        try:
            fn()
        except ValueError:
            return
        raise AssertionError("ValueError not raised")
    expect_value_error(lambda: dev.write_reg(0x5A, b"\x00"))     # RO SR
    expect_value_error(lambda: dev.read_reg(0x60, 1))            # out of map
    expect_value_error(lambda: dev.read_reg(0x00, 0x100))        # too long
    expect_value_error(lambda: dev.set_duty_pct(-1.0))
    expect_value_error(lambda: dev.set_duty_pct(101.0))
    expect_value_error(lambda: dev.set_tach_threshold(70000))
    expect_value_error(lambda: dev.set_ramp_rate(0x40))
    expect_value_error(lambda: dev.lut_set_index(48, 100))
    expect_value_error(lambda: dev.set_ideality_factor(1.5))
    expect_value_error(lambda: dev.configure_4wire_fan(port=3))
section("error model (ValueError paths)", s_errors)

# ------------------------------------------------------------------ restore ----
dev.write_reg(0x00, SNAP)
dev.clear_fan_fail()
ok = True
for reg_off in range(0, 0x50, 8):
    chunk = dev.read_reg(reg_off, 8)
    if bytes(chunk) != SNAP[reg_off:reg_off + 8]:
        ok = False
        break
assert ok, "restore verification failed"
dev.save_config(MAX31760.EEX_BLOCK_00_0F)      # leave EEPROM pre-test state
print("configuration restored (RAM verified byte-for-byte)")

fails = [r for r in results if r[1] != "PASS"]
print("")
print("sections: %d passed, %d failed" %
      (len(results) - len(fails), len(fails)))
if fails:
    for name, status, msg in fails:
        print("  FAILED: %s [%s] %s" % (name, status, msg))
    raise SystemExit("E2E HARDWARE MATRIX: FAIL")
print("E2E HARDWARE MATRIX: PASS")
