# max31760 — Driver Documentation

Production-quality dual-platform Python driver for the Maxim **MAX31760**
precision fan-speed controller (the chip on the MikroElektronika *Fan 2 Click*).
One package, one shared core, identical public API on both platforms:

| Platform | Entry point | Transport |
|----------|-------------|-----------|
| MicroPython (RPi Pico RP2040/RP2350, ESP32-class) | `max31760.mp` | `machine.I2C` (`readfrom_mem`/`writeto_mem`) |
| CPython / Linux SBC (Raspberry Pi all models, BeagleBone, clones) | `max31760.cp` | `smbus2` (fallback: system `python3-smbus`) |

Verified live on: RPi Pico W (first edition, RP2040 — MicroPython v1.19.1 and
v1.29.0), ESP32 (MicroPython v1.29.0), and RPi 3A+ (Debian 13, Python 3.13,
smbus2); MAX31760 @ 0x50, one 4-wire fan on port 1, 2N3906 remote diode on
DXP/DXN. Expected to work equally well on a Pico 2 W (RP2350) — same `rp2`
port family — but that board has not been
tested.

---

## 1. Wiring

### Bare MAX31760 (or Fan 2 Click)

| MAX31760 pin | Function | Connect to |
|--------------|----------|------------|
| VDD (pin 1) | Supply | 3.3–5 V (Click: 3V3) |
| GND (pin 8) | Ground | GND |
| SDA (pin 2) | I²C data | I²C SDA (bench: GP0) |
| SCL (pin 3) | I²C clock | I²C SCL (bench: GP1) |
| ALERT (pin 4) | Alert output | MCU GPIO (optional; open-drain, pull up) |
| PWM (pin 5) | PWM out | Fan PWM input (4-wire fans) or fan supply (3-wire, see §7.2) |
| TACH1 (pin 6) | Tachometer 1 | Fan tach signal (port 1) |
| TACH2 (pin 7) | Tachometer 2 | Fan tach signal (port 2) |
| DXP / DXN | Remote sense | Remote NPN/PNP transistor base-emitter (see below) |

I²C address is fixed at **0x50**. Pull-ups on SDA/SCL are required (the Click
carries them; bare boards need 4.7 kΩ to 3.3 V).

Remote temperature sensing uses an external transistor whose B-E junction acts
as the sensor. Wire DXP to the collector side and DXN to the emitter side of a
small NPN (e.g. 2N3904) or PNP (e.g. 2N3906) mounted near the heat source. The
driver's ideality-factor API (§5.7) calibrates this reading.

### Bench configuration used for verification

- RPi Pico W (first edition), I²C0: SDA = GP0 (board pin 1), SCL = GP1 (board pin 2)
- MAX31760 @ 0x50; one 4-wire fan on TACH1/port 1; port 2 unconnected
- 2N3906 (PNP) remote diode on DXP/DXN

---

## 2. Installation

### MicroPython

Deploy the package into **`/lib`** (included in `sys.path` on all ports — the
standard location for third-party libraries):

```bash
mpremote fs mkdir :/lib          # some images ship without /lib; harmless if it exists
mpremote fs mkdir :/lib/max31760
mpremote cp max31760/__init__.py        :/lib/max31760/
mpremote cp max31760/_core.py          :/lib/max31760/
mpremote cp max31760/_tables.py        :/lib/max31760/
mpremote cp max31760/_lut.py           :/lib/max31760/
mpremote cp max31760/_faults.py        :/lib/max31760/
mpremote cp max31760/_transport_mp.py  :/lib/max31760/
mpremote cp max31760/mp.py             :/lib/max31760/
```

(`_transport_cp.py` and `cp.py` are not needed on-device.) Copy individual
files — device filesystems cannot copy whole directories. Alternative: boards
with `mip` (≥ v1.19) can install straight from a served directory.
Verify after deploying: `import max31760; print(max31760.__version__)` →
`0.1.0`. Note: if `/lib` does not exist yet, create it before the package
directory (`fs mkdir :/lib/max31760` fails with “No such file or directory”
when its parent is missing — observed on an ESP32 v1.29.0 image, 2026-11-08).

### CPython / Linux SBC

```bash
pip install .            # installs the package; pulls smbus2 from PyPI
# or without installing:
pip install smbus2       # then add the project root to sys.path
```

Enable I²C per platform first:

- **Raspberry Pi** (all models incl. Zero / Zero 2 W): `sudo raspi-config` →
  Interface Options → I2C → Enable (older images: uncomment `dtparam=i2c_arm=on`
  in `/boot/config.txt`). Bus `/dev/i2c-1` (GPIO pins 3/5) is the default;
  verify with `sudo i2cdetect -y 1` (expect `50`). The Zero family exposes the
  same 40-pin header, so nothing differs beyond physical wiring.
- **BeagleBone**: enable the I²C pinmux via Device Tree overlays, e.g.
  `sudo dtboe i2c0` (P9.17/P9.18) or `i2c1`; bus numbers follow
  `/dev/i2c-*`. Verify with `i2cdetect -y <bus>`.
- **Generic SBC**: enable the kernel I²C adapter for your chosen pins (vendor
  pinmux tooling varies), then use the matching `/dev/i2c-N` bus number.
  Discover buses with `ls /dev/i2c-*` and confirm the chip with
  `i2cdetect -y N`.

Root access to the i2c-dev nodes may require adding the user to the `i2c`
group or running as root.

---

## 3. Quick start

### MicroPython

```python
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)

assert dev.verify(), "chip not responding"
print("local  %.1f C" % dev.local_temp_c)
print("remote %.1f C" % dev.remote_temp_c)

# Drive the fan directly (manual mode):
dev.manual_enable(True)
dev.set_ramp_rate(MAX31760.RAMP_IMMEDIATE)
dev.set_duty_pct(50.0)
dev.wait_for_duty(50.0)
print("actual duty: %d/255" % dev.get_actual_duty_raw())
print("fan speed:   %.1f rpm" % dev.rpm(1))
```

### CPython / SBC

```python
from max31760.cp import MAX31760

dev = MAX31760(bus=1, addr=0x50)     # /dev/i2c-1
assert dev.verify()
dev.configure_4wire_fan(port=1)      # recommended 25 kHz preset
dev.manual_enable(True)
dev.set_duty_pct(75.0)
print(dev.rpm(1))
dev.close()                          # releases the bus if this object opened it
```

---

## 4. Core concepts you must know

1. **Control mode (CR2.DFC).** The factory default is *automatic LUT mode*:
   the output follows the temperature-indexed lookup table, and writes to the
   manual duty register (PWMR) are IGNORED. With the factory all-FF LUT the
   fan runs at 100 %. Call `manual_enable(True)` before using
   `set_duty_pct()`/`set_duty_raw()`. Conversely, in LUT mode program the LUT
   (`lut_set`/`lut_set_index`) and leave DFC cleared.
2. **Single-fan hygiene (mandatory).** If only one fan is connected, disable
   the unused tachometer and clear any latched fan-fail alarm:
   `tach2_enable(False)` + `clear_fan_fail()`. A dead/disabled-but-monitored
   port latches TACH2A after ~3 detection cycles (~8 s measured), which forces
   the PWM output to the FFDC value (factory 100 %) and overrides even manual
   duty. The presets in §5.10 do this for you.
3. **SR is read-clear.** Reading status (0x5A) clears most alarm bits; the
   PC (EEPROM-corrupt) bit persists until a successful EEPROM write + POR.
4. **Ramp rate.** Duty changes slew at the configured ramp rate; the factory
   setting is slow (measured ~15 s for 255→128). Use `wait_for_duty()` to
   block until the output actually reaches the target.
5. **EEPROM endurance.** Configuration RAM mirrors into EEPROM only when you
   call `save_config()`. Typical EEPROM life is ~1 million erase/write cycles
   per byte — save deliberately, not on every boot.

---

## 5. API reference

All methods exist identically on both facades (enforced by the parity gate,
§8). Signatures below are the shared-core ones.

### 5.1 Identity & raw access

| Method | Description |
|--------|-------------|
| `probe()` | True if the chip ACKs its address. |
| `scan()` | List of responding addresses on the bus. |
| `verify()` | Probe + sanity check of known RO registers; raises `OSError` on NACK. |
| `read_reg(reg, n=1)` | Read `n` bytes starting at `reg` (bounds-checked, page-safe chunking). |
| `write_reg(reg, buf)` | Write `buf` to `reg` (page-safe chunking; RO registers rejected). |

### 5.2 Temperature

| Member | Description |
|--------|-------------|
| `local_temp_c` (property) | Local die temperature, °C float. |
| `remote_temp_c` (property) | Remote diode temperature, °C float. |
| `set_local_high(celsius)` / `get_local_high()` | Local high-threshold setpoint (LTH/LTL). |
| `set_local_overtemp(celsius)` / `get_local_overtemp()` | Local over-temp shutdown threshold. |
| `set_remote_high(celsius)` / `get_remote_high()` | Remote high-threshold setpoint. |
| `set_remote_overtemp(celsius)` / `get_remote_overtemp()` | Remote over-temp threshold. |
| `set_hysteresis_c(celsius)` / `get_hysteresis_c()` | Threshold hysteresis (CR1.HYST). |
| `set_index_source(source)` / `get_index_source()` | Which sensor indexes the LUT: `INDEX_LOCAL`, `INDEX_REMOTE`, `INDEX_MAX`. |

### 5.3 Manual (direct) control & duty

| Method | Description |
|--------|-------------|
| `manual_enable(on)` / `manual_enabled()` | CR2.DFC — direct fan control vs automatic LUT mode. |
| `set_duty_pct(pct)` | Command duty 0..100 % (writes PWMR). |
| `set_duty_raw(raw)` | Command duty 0..255. |
| `get_duty_cmd_raw()` | Last commanded duty (PWMR). |
| `get_actual_duty_raw()` / `get_actual_duty_pct()` | Actual output duty (PWMV, RO). |
| `set_ramp_rate(rate)` / `get_ramp_rate()` | `RAMP_SLOW` / `RAMP_MED_SLOW` / `RAMP_MED_FAST` / `RAMP_IMMEDIATE`. |
| `wait_for_duty(target_pct, timeout_ms=2000)` | Block until actual duty reaches target ±1 LSB; `TimeoutError` on overrun. |
| `set_pwm_freq_hz(hz)` / `get_pwm_freq_hz()` | One of `PWM_FREQ_33HZ`, `PWM_FREQ_150HZ`, `PWM_FREQ_1P5KHZ`, `PWM_FREQ_25KHZ`. |
| `set_pwm_polarity(polarity)` / `get_pwm_polarity()` | `POLARITY_POSITIVE` / `POLARITY_NEGATIVE`. |

### 5.4 Lookup table (automatic mode)

| Method | Description |
|--------|-------------|
| `lut_get()` | All 48 LUT entries as a tuple of raw duties. Window geometry (datasheet Table 7): window 0 covers < 18 °C, each further window spans 2 °C, window 47 saturates ≥ 110 °C. |
| `lut_set(duties)` | Program all 48 entries (sequence of 0..255). |
| `lut_get_index(index)` / `lut_set_index(index, duty)` | Single-entry access (index 0..47). |
| `build_lut_curve(points)` / `lut_index_for_temp(temp)` | Module-level helpers exported by both facades: build a 48-entry LUT from `(temp_c, pct)` breakpoints; map a temperature to its LUT window index. |

### 5.5 Tachometers & RPM

| Method | Description |
|--------|-------------|
| `tach1_enable(on)` / `tach1_enabled()` | Arm/disarm port-1 tachometer (CR3.TACH1E). |
| `tach2_enable(on)` / `tach2_enabled()` | Same for port 2 (CR3.TACH2E). |
| `rpm(port, pulses_per_rev=2)` | Instantaneous RPM from the TC counter pair; 0.0 when no count. |
| `measure_tach_once(port=1, timeout_ms=3000)` | One-shot pulse-stretched measurement (sets PSEN, polls TC, always clears PSEN). Requires 33 Hz + TACHFULL off. |
| `set_tach_threshold(count)` / `get_tach_threshold()` | Fan-fail tach threshold (TCTH:TCTL, 0..65535). |

### 5.6 Fault handling

| Method | Description |
|--------|-------------|
| `status_raw()` | Raw SR byte (RO, clear-on-read). |
| `active_alarms()` | Compact six-alarm bitmask (SR & SR_ALARM_MASK, PC excluded). Consumes the latch like `status_raw()` — call one or the other per service cycle. |
| `remote_diode_fault()` | True if SR.RDFA (remote diode fault). |
| `clear_fan_fail()` | Pulse CR3.CLRFAIL (self-clearing). |
| `set_ffdc_raw(raw)` / `set_ffdc_pct(pct)` / `get_ffdc_raw()` | Forced duty applied while a fan-fail condition holds. |
| `set_ff_zero_detection(on)` / `ff_zero_detection()` | CR3.FF_0 — treat zero tach count as failure. |
| `set_ff_mode(mode)` / `get_ff_mode()` | `FF_MODE_INTERRUPT` (latched) or `FF_MODE_COMPARATOR` (live). |
| `set_rd_mode(enabled)` / `rd_mode_enabled()` | CR3.FSST — locked-rotor (RD) sensing instead of tach counting. |
| `set_rd_polarity(high_means_spinning)` / `get_rd_polarity()` | CR3.RDPS — RD signal polarity. |

Status flag constants: `SR_TACH1A`, `SR_TACH2A`, `SR_ROTA`, `SR_RHA`,
`SR_LOTA`, `SR_LHA`, `SR_RDFA`, `SR_PC`, plus `SR_ALARM_MASK` (all six
alarm bits) and `SR_ALARM_MASK`-based helpers.

### 5.7 Alerts & ideality factor

| Method | Description |
|--------|-------------|
| `set_alert_mask(alarms)` / `get_alert_mask()` | MASK register (0x04): which alarms drive ALERT. |
| `alert_masked()` | True if CR1.ALTMSK is latched (post-service masking active). |
| `service_alert()` | Read SR (datasheet step 2) and return it. |
| `clear_alert_mask()` | Clear ALTMSK (datasheet step 5). |
| `set_alert_mode(mode)` / `get_alert_mode()` | `ALERT_MODE_INTERRUPT` (latched, factory) or `ALERT_MODE_FAULT_INDICATOR` (tracks live condition). |
| `set_ideality_factor_index(idx)` / `get_ideality_factor_index()` | IFR index 0..63 (CR2 bits [5:0]). |
| `get_ideality_factor()` | Float n for the current index (from `IDEALITY_TABLE`). |
| `set_ideality_factor(n)` | Nearest-table match; returns the chosen index; rejects out-of-range. |

`IDEALITY_TABLE` (64 floats, 0.9844..1.0489) is exposed as a class attribute.

### 5.8 EEPROM, lifecycle & user memory

| Method | Description |
|--------|-------------|
| `save_config(blocks=EEX_ALL_BLOCKS, timeout_ms=2000)` | RAM → EEPROM; waits out the tW busy window with a fixed 700 ms delay (above the datasheet worst case); `TimeoutError` if the budget is under 700 ms. |
| `load_config(blocks=EEX_ALL_BLOCKS, timeout_ms=2000)` | EEPROM → RAM (same fixed wait). |
| `eeprom_corrupt()` | True if SR.PC (persists across SR reads). |
| `recover_from_corruption(timeout_ms=2000)` | Rewrite all blocks → soft POR → verify PC cleared. |
| `soft_por(settle_ms=1000)` | CR1.SW_POR self-clearing reset; RAM reloads from EEPROM. The chip resets mid-transaction, so the SW_POR write is issued exactly once (no retries) and its expected bus error is swallowed; the method then polls until the device re-acknowledges (up to `settle_ms`) and waits out the POR-triggered EEPROM-reload window. Raises `OSError` only if the device never comes back. |
| `enter_standby()` / `exit_standby()` / `standby_active()` | CR2.STBY (I²C stays alive in standby). |
| `user_memory_get(index=0)` / `user_memory_set(index, value)` | User memory bytes 0x10..0x17 (index 0..7). |
| `user_memory_read_all()` / `user_memory_write_all(data)` | Bulk variants (8 bytes). |

Block-select constants: `EEX_BLOCK_00_0F` … `EEX_BLOCK_40_4F`,
`EEX_ALL_BLOCKS` (= 0x1F).

### 5.9 Spin-up & 3-wire assists

| Method | Description |
|--------|-------------|
| `spin_up_enable(on)` / `spin_up_enabled()` | CR2.SPEN — hold ~100 % briefly to help the fan start. |
| `pulse_stretch_enable(on)` / `pulse_stretch_enabled()` | CR3.PSEN — stretch tach pulses so they survive 33 Hz supply chopping. |
| `tacho_full_enable(on)` / `tacho_full_enabled()` | CR3.TACHFULL — suspend tach measurement below 100 % duty. |

### 5.10 Presets

| Method | Description |
|--------|-------------|
| `configure_4wire_fan(port=1, pwm_freq_hz=PWM_FREQ_25KHZ)` | Datasheet Fig. 2a topology: 25 kHz, port armed, single-fan hygiene applied. |
| `configure_3wire_supply_modulation(port=1)` | Datasheet Fig. 2b topology: 33 Hz + PSEN so the tach survives supply chopping. |
| `configure_two_fans(pwm_freq_hz=PWM_FREQ_25KHZ)` | Both tachometers armed for dual-fan operation. |

Presets are **mode-neutral**: they never touch CR2.DFC. If you intend to drive
the output with `set_duty_pct()`, call `manual_enable(True)` yourself (in
automatic mode the LUT governs — see §4.1).

### 5.11 Lifecycle

| Method | Description |
|--------|-------------|
| `close()` | Releases the bus on CPython (only if this object opened it); documented no-op on MicroPython. Portable code may call it on both platforms. |

---

## 6. Error model

| Condition | Behaviour |
|-----------|-----------|
| Bad argument (range, type, unknown constant) | `ValueError` raised immediately, nothing written. |
| Bus NACK / missing chip | `OSError` (the transport retries once, then propagates). |
| Timeout (duty settle, EEPROM tW window) | `TimeoutError` with a descriptive message. |
| Write to a read-only register (e.g. SR) | `ValueError`. |
| Out-of-bounds register access | `ValueError` (map spans 0x00–0x5B). |

The driver never silently ignores failures: every mutating call either
succeeds or raises.

---

## 7. Operational notes (measured on real silicon)

1. **Factory state is LUT mode at 100 %.** After power-on (or `soft_por()`
   with factory EEPROM) the output follows the all-FF LUT → 100 % duty. This
   is normal; enable manual mode or program the LUT.
2. **Fan-fail re-arm latency ≈ 8 s** after `clear_fan_fail()` with a dead
   monitored port (2 s startup grace + detection cadence). Expect TACHxA to
   re-latch within that window.
3. **EEPROM tW** is ~110 ms per 16-byte block, max 550 ms (full range). The
   driver waits out the busy window with a fixed 700 ms delay after every
   `save_config`/`load_config`; do not hammer the bus during that window.
4. **`soft_por()` can take up to ~1 s** in pathological cases: the chip
   resets mid-transaction (the SW_POR write may report a bus error even
   though the reset happened), then re-initializes and reloads EEPROM into
   RAM. The method absorbs all of this internally; only a device that never
   comes back raises `OSError`.
5. **IFR changes settle slowly (~4 s)** in the bench fixture (thermal
   coupling of the remote diode); the API itself is instant.
6. **Stretched pulses are not observable via I²C** at typical bench speeds:
   PWMV reports the commanded duty and TC updates continuously. Verify PSEN
   behaviour externally (scope) or rely on `measure_tach_once()` returning a
   valid count.
7. **Standby keeps I²C alive** — the chip answers reads while STBY=1.

---

## 8. Testing

```bash
python -m unittest discover tests    # 134 mock-backed unit/integration tests
python tools/api_coverage.py         # gate: every public member exercised
python tests/lint_subset.py          # gate: MicroPython-subset compliance
python -m compileall max31760        # syntax gate
```

Gates:

- **Parity gate (F26):** `TestApiParity` asserts the mp and cp facades expose
  an identical public surface (names, signatures, constants, properties).
- **Coverage gate:** `tools/api_coverage.py` fails if any public member is
  unreferenced by the suite.
- **Wire-legality mock:** the mock chip asserts page-aligned ≤8-byte writes,
  the SMBus 32-byte block-read limit, the prepend-register quirk, EEPROM tW
  NACK windows, and SR clear-on-read semantics.

On-device E2E slices (`e2e_phase_*.py`) were run incrementally on the Pico
bench during the build (now archived under `scripts/pico/`); results are
logged in `SUMMARY.md`.

---

## 9. Example: ALERT interrupt service routine

With `set_alert_mode(ALERT_MODE_INTERRUPT)` (factory) the ALERT pin goes low
when a masked alarm latches. Service it like this:

```python
import time
from max31760.mp import MAX31760

def isr(pin):                       # wired to the ALERT pin (IRQ_FALLING)
    sr = dev.service_alert()        # step 2: read SR (clears non-PC bits)
    if sr & MAX31760.SR_TACH1A:
        print("fan 1 stalled!")
    if sr & MAX31760.SR_LHA:
        print("local temp above LHS")
    # attend the condition, then release the mask:
    dev.clear_alert_mask()          # step 5

dev.set_alert_mask(MAX31760.SR_ALARM_MASK & ~MAX31760.SR_RDFA)
irq_pin.irq(handler=isr, trigger=machine.Pin.IRQ_FALLING)
```

In `ALERT_MODE_FAULT_INDICATOR` the pin tracks the live condition instead of
latching, so no service routine is needed (poll `status_raw()` for details).

---

## 10. References

- **MAX31760 datasheet** — Maxim Integrated DS 19-7395 Rev 0 (4/14):
  - Primary: <https://download.mikroe.com/documents/datasheets/MAX31760.pdf>
  - Backup: <https://www.analog.com/media/en/technical-documentation/data-sheets/max31760.pdf>

  All register-map and timing citations in this document refer to that
  datasheet (e.g. Table 13 register map, Table 7 LUT window geometry,
  Fig. 2a/2b fan topologies, alert-service procedure steps). A local copy is
  kept at `reference/MAX31760.pdf` (gitignored — vendor copyright, not
  redistributed with this repo).
