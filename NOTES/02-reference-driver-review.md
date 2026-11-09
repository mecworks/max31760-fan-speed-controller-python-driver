# Reference Driver Review: rudybrian/MAX31760-Python (GPL-2.0/MIT dual header)

Repo cloned to `reference/MAX31760-Python/` (HEAD c2449cf; clone removed from this
repo 2026-11-08 — the findings below stand on their own). Files: `MAX31760.py` (~700 lines),
`Adafruit_I2C.py` (smbus transport), `test-MAX31760.py` (CPython 2 demo script), `README.md`.

License note: file headers say MIT-style text; repo metadata says GPL-2.0. Either way we are
free to borrow ideas/constants; we will **rewrite from scratch** for MicroPython and keep our
own license. We credit the author in docs.

## Architecture of the reference driver

- `MAX31760(Adafruit_I2C)` — device class inherits a Linux/smbus I²C wrapper.
- Transport (`Adafruit_I2C`): `readU8/readS8/readU16/write8/write16/writeList/readList` over
  `smbus.write_byte_data / read_byte_data / write_i2c_block_data / read_i2c_block_data`.
  Auto-detects Pi bus number via `/proc/cpuinfo`.
- Device layer: register constants + bitmask constants + string-keyed "LUT" dicts mapping
  friendly names → bit values; per-register read/write methods that return/accept dicts or
  `(param, value)` pairs; utility helpers (temps, tach, LUT, EEPROM, POR, defaults).

## Well-designed parts (worth carrying forward)

1. **Complete register-map constant set** (addresses + all CR1/CR2/CR3/MASK/SR bitmasks) — matches datasheet correctly.
2. **Separation of transport vs device logic** — right pattern; we replicate it with a MicroPython I²C adapter.
3. **Ideality-factor table** covering all 64 IFR entries (values 0.9844–1.0489) — reuse as compact tuple.
4. **LUT window model** (index ↔ temperature window ↔ address 0x20+i) — concept correct; we derive it arithmetically instead of storing 48 dicts.
5. **Convenience wrappers** for the four setpoints, local/remote temps, tach reads, FFDC, alert mask, status — good API surface shape.
6. `sendPOR()`, `clearFF()` one-shot helpers — sensible.
7. Test script exercises nearly every API call — useful checklist for our test suite.

## Deficiencies & bugs (why we rewrite rather than port)

### Fatal / correctness bugs
| # | Location | Problem |
|---|---|---|
| B1 | `writeControlRegister1("PWM_frequency", …)` | `self.self.MAX31760_CTRL1_PWM_FREQ_25_KHZ` — typo, raises `AttributeError` at runtime. Setting PWM frequency is impossible. |
| B2 | `readControlRegister2()` / `writeControlRegister2("spin_up_enable", …)` | Uses `CTRL2_ALERT_COMP` (0x40) instead of SPEN (0x20). Spin-up read reports the wrong bit; spin-up write corrupts ALERT mode. Copy-paste bug. |
| B3 | `writeTachThreshold(RPM)` | Computes 16-bit count but writes only the high byte via `write8(TCTH, tach)` with an un-clamped int (e.g., 10 RPM → 300000). TCTL never written; threshold garbage. |
| B4 | `readTach()` | No guard for `count == 0` → `ZeroDivisionError` when fan stopped/no signal. Also no overflow detection (wrapped count ⇒ absurdly high RPM reported). |
| B5 | `readTemp()` | Relies on CPython arbitrary-precision two's-complement accident (`(-1)<<8 \| 0xE0`); works but obscure, and `readS8`+shift is fragile if backported. Needs clean sign-extension. |

### Design weaknesses
| # | Issue |
|---|---|
| D1 | **Not MicroPython-compatible**: Python 2 syntax (`except IOError, err`, bare prints), `import smbus` (Linux-only), `/proc/cpuinfo` sniffing. Runs only on desktop Linux. |
| D2 | **Heavy allocations**: builds fresh dicts on every `readStatus()`, `readAlertMask()`, `readFanLUT()` (48 nested dicts!), calls `invertDict()` (full dict copy) on every control-register read. Hostile to RAM-constrained MCUs. |
| D3 | **String-keyed APIs everywhere** (`"medium-fast"`, `"1.0050"`): string interning/hashing overhead, brittle float→str matching (`str(1.005)` ≠ `"1.0050"` → KeyError), poor ergonomics. |
| D4 | **EEPROM handling incomplete**: `writeRAMToEEPROM()` fires EEX=0x1F and returns immediately — ignores the 550 ms tW during which the chip NACKs; any follow-up I²C op fails. No block-select support, no ack-polling, no corruption-recovery helper. |
| D5 | **No error propagation**: failures return `-1`/`False` silently; no exceptions, no retries, no distinction between "bad argument" and "bus NACK". |
| D6 | **Inefficient LUT access**: `readFanLUT()` = 48 separate single-byte I²C transactions (should be one 48-byte burst read); `writeFanLUT()` keyed on floating-point boundary match (`value['high'] == temp_high`) — awkward and imprecise. |
| D7 | **Hardcoded assumptions**: 2 pulses/rev baked into tach math (not configurable); temp range limited to −55…125 °C though format supports ±128; `setDefaults()` enables DFC (manual mode) by default, silently disabling the LUT. |
| D8 | **Missing features**: user memory region (10h–17h), generic raw reg access, pulse-stretch assist sequence (PSEN set→wait→clear), interrupt-mode ALERT service routine (SR read + ALTMSK clear), standby convenience, MTI/TIS combined setter, ideality nearest-match by numeric value, multi-page-safe bulk LUT write, RPM-threshold *read* uses the buggy tach path, no `pulses_per_rev` parameter anywhere. |
| D9 | **Coarse duty API**: `readCurrentDutyCycle()` rounds to integer percent (loses 1/256 resolution); no raw-duty accessor. |
| D10 | **API inconsistency**: some setters take booleans, some strings, some floats; `writeControlRegisterN(param, value)` is a giant if/elif chain duplicated 3× — unmaintainable. |

## Conclusions feeding the new architecture

1. Keep: register/bitmask constants (verified against datasheet), transport/device split, ideality table, setpoint/temp/tach/LUT/EEPROM/POR feature list.
2. Fix: all B1–B5 bugs by construction (typed enums-as-ints, 16-bit-aware writes, zero/overflow guards, clean sign extension).
3. Rebuild for MicroPython: integer-centric API (no string keys), minimal allocations (tuples, small lists, no per-call dicts), `machine.I2C` transport with retry + OSError semantics, page-safe bulk writes, EEPROM busy handling (sleep/ack-poll), full feature coverage incl. D8 gaps.
4. License: rewrite cleanly; retain attribution comment for rudybrian's work and the Mikroe click reference.
