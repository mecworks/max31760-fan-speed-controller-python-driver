# MicroPython Target Notes (Driver Constraints & Platform API)

> **CORRECTION (2026-11-07, live test on RPi Pico W first edition / MicroPython v1.19.1):**
> `I2C.mem_read`/`mem_write` are **ABSENT** on this build (AttributeError). The driver's
> baseline transport API is therefore `readfrom_mem(addr, reg, n)` /
> `writeto_mem(addr, reg, buf)` — long-standing and universal across ports. Do NOT depend
> on `mem_read`/`mem_write`; see PLANS.md §2.1 for details.

Targets: RP2040/RP2350 boards (RPi Pico/Pico W), ESP32 family — any port with `machine.I2C`.
Docs: https://docs.micropython.org/en/latest/library/machine.I2C.html

## 1. machine.I2C API surface we rely on

Constructor (port-dependent pin args; user constructs, driver receives instance):
```python
import machine
# RPi Pico (GP4=SCL, GP5=SDA), Fast mode:
i2c = machine.I2C(0, scl=machine.Pin(5), sda=machine.Pin(4), freq=400_000)
# ESP32 example:
i2c = machine.I2C(0, scl=machine.Pin(22), sda=machine.Pin(21), freq=400_000)
```

Methods:
| Method | Notes |
|---|---|
| `scan()` | Returns tuple of 7-bit addresses present. Use for discovery/self-test. |
| `writeto(addr, buf)` | Full transaction incl. STOP. Raises `OSError` (errno 5/6/…) on NACK. |
| `readfrom(n)` | Read n bytes from last addressed slave (needs prior writeto in same transaction). |
| `mem_read(addr, reg, nbytes)` | **Since v1.17**: register-prefixed burst read (dummy-write + repeated-start internally). Exactly our "read recipe". |
| `mem_write(addr, reg, buf)` | **Since v1.17**: register-prefixed burst write. |
| `transaction(fn)` / `with i2c.transaction():` | Group ops into one bus session (repeated starts between calls). Fallback path for pre-1.17 ports. |
| `deinit()` | Release peripheral. |

**Decision:** require MicroPython ≥ 1.17 (all current Pico/ESP32 releases are ≥1.19/1.2x).
Primary path uses `mem_read`/`mem_write`; include a small fallback shim using
`transaction() + writeto([reg]) + readfrom(n)` so the driver degrades gracefully on older ports.
The shim is ~15 lines and keeps the driver honest on both worlds.

Error semantics: NACK/bus errors raise `OSError`. Driver catches at the low-level layer,
retries once after a short delay, then re-raises as `OSError` with a descriptive message.
Argument problems raise `ValueError`. This fixes reference-driver deficiency D5.

## 2. Memory & performance constraints shaping the design

- RAM: Pico has 264 KB SRAM but MicroPython heap is modest; ESP32-S3 similar. Rule: **no per-call dict construction**, no string-keyed lookups in hot paths.
  - Tables (ideality factor, LUT windows) stored as module-level **tuples of ints**.
  - Status/alert-mask decoding returns raw int + bit constants; optional tiny helper returns a compact int bitmask of "active alarms" instead of a dict.
  - `get_lut()` allocates one 48-byte buffer per call (acceptable; caller can reuse pattern).
- Flash: single-module target < ~16 KB source. No dependencies beyond stdlib (`time`, optionally `machine`).
- CPU: avoid float math where int suffices (temp encode/decode via shift+round; RPM via integer division returning float only at final step).
- GC: long-running loops should not allocate each iteration ⇒ provide `poll_status(buf=None)` style where sensible; document that `get_*` helpers allocate.

## 3. Timing considerations

- ADC conversion 150 ms: temperature registers update continuously; no wait needed to read (value may be up to 150 ms stale — document).
- EEPROM save: tW ≤ 550 ms. Strategy: `save_config()` writes EEX then **acknowledge-polls** (probe a cheap register read every ~10–20 ms until success, hard cap ~700 ms → raise `TimeoutError` if exceeded). Ack-poll beats blind sleep (typical block write ≈110 ms). Polling must tolerate `OSError` (NACK = still busy).
- Tach counts update when the chip completes a 4-pulse average; reading anytime is safe (may lag).
- Ramp rates: duty changes slew at 3.125–12.5 %/s unless RAMP=fast — callers comparing PWMV vs target must account for this (document; expose `wait_for_duty(target, timeout_ms)` helper).

## 4. Portability rules

- Only `machine.I2C` + `time` imports. No `ustruct` (manual shifts), no `sys`, no CPython-only modules.
- Python 3 syntax compatible with MicroPython subset: f-strings OK on modern MP but keep `%`/concat for safety? → Decision: use f-strings sparingly (MP ≥1.17 supports them); prefer plain concatenation in error messages for max compat.
- Type hints: NOT used (MicroPython ignores most annotations but they cost flash; keep code clean without them).
- Provide board-ready examples: `examples/pico_demo.py`, `examples/esp32_demo.py` showing I²C init + full workflow.

## 5. Testing strategy (host-side, no hardware required)

- `tests/mock_i2c.py`: fake I²C object implementing `mem_read/mem_write/writeto/readfrom/scan/transaction` backed by a simulated MAX31760 register file (incl. page-wrap behavior, EEPROM busy window, SR clear-on-read, fault queue). Runs under host CPython 3.
- `tests/test_max31760.py`: unittest suite covering: temp encode/decode round-trips (incl. negatives), setpoint get/set, LUT bulk get/set page alignment, manual/auto modes, RPM math (zero-count, overflow, custom pulses/rev), threshold clamping, CR1/2/3 RMW field isolation, EEPROM save/load sequencing + busy polling, soft POR, alert service sequence, ideality nearest-match, address validation.
- Mock sim also verifies the driver never issues an unaligned >8-byte write (catches page-wrap class of bugs).
- Hardware smoke test script `examples/hw_smoke_test.py` for bench verification (manual run, not CI).

## 6. Delivery layout (updated 2026-11-03 for dual-platform Option C)

```
FanSpeedController/
├── PLANS.md
├── NOTES/                          # discovery + decision notes
├── max31760/                       # THE PACKAGE (drop-in copyable; pip-installable)
│   ├── __init__.py                 # __version__ only
│   ├── _core.py                    # shared protocol logic (single source of truth)
│   ├── _transport_mp.py            # machine.I2C adapter
│   ├── _transport_cp.py            # smbus2/smbus adapter
│   ├── mp.py                       # MicroPython entry point
│   └── cp.py                       # CPython/SBC entry point
├── requirements.txt                # smbus2 (CPython target)
├── pyproject.toml                  # minimal; enables `pip install .`
├── examples/
│   ├── pico_demo.py
│   ├── esp32_demo.py
│   ├── rpi_demo.py                 # Raspberry Pi (+ BeagleBone/generic Linux notes)
│   └── hw_smoke_test.py
├── tests/
│   ├── mock_i2c.py
│   ├── fake_smbus.py               # fake smbus2 for CP-adapter tests
│   └── test_max31760.py
└── docs/README.md                  # usage guide + wiring + API reference + SBC setup
```
