# Changelog

All notable changes to the `max31760` driver are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.1] - 2026-11-21

Accessor unification and fail-loud hardening. **Pre-1.0 release: the
breaking renames below have NO compatibility shims or deprecation warnings**
(D-15); this table is the migration notice.

### BREAKING: accessor renames (state is now properties)

Register-backed state moved from `get_x()`/`set_x(v)` method pairs to
PROPERTIES: reading or assigning performs the I2C transaction. Verbs remain
for actions (`save_config()`, `configure_4wire_fan()`, ...) and for
destructive-read primitives (`status_raw()`, `active_alarms()`, ...).

| Old (0.1.0) | New (0.1.1) |
|---|---|
| `get_local_high()` / `set_local_high(v)` | `local_high_c` property |
| `get_remote_high()` / `set_remote_high(v)` | `remote_high_c` property |
| `get_local_overtemp()` / `set_local_overtemp(v)` | `local_overtemp_c` property |
| `get_remote_overtemp()` / `set_remote_overtemp(v)` | `remote_overtemp_c` property |
| `lut_get()` / `lut_set(seq)` | `lut` property (list of 48 duty raws) |
| `manual_enable(on)` / `manual_enabled()` | `manual` property |
| `set_duty_raw(raw)` / `get_duty_cmd_raw()` | `duty_cmd_raw` read/write property |
| `get_actual_duty_raw()` | `actual_duty_raw` (read-only) |
| `get_actual_duty_pct()` | `actual_duty_pct` (read-only) |
| `set_index_source(v)` / `get_index_source()` | `index_source` property |
| `set_hysteresis_c(v)` / `get_hysteresis_c()` | `hysteresis_c` property |
| `set_pwm_freq_hz(v)` / `get_pwm_freq_hz()` | `pwm_freq_hz` property |
| `set_pwm_polarity(v)` / `get_pwm_polarity()` | `pwm_polarity` property |
| `set_ramp_rate(v)` / `get_ramp_rate()` | `ramp_rate` property |
| `set_tach_threshold(v)` / `get_tach_threshold()` | `tach_threshold` property |
| `spin_up_enable(on)` / `spin_up_enabled()` | `spin_up_enabled` property |
| `pulse_stretch_enable(on)` / `pulse_stretch_enabled()` | `pulse_stretch_enabled` property |
| `tacho_full_enable(on)` / `tacho_full_enabled()` | `tacho_full_enabled` property |
| `enter_standby()` / `exit_standby()` / `standby_active()` | `standby` property (True enters, False exits) |
| `set_alert_mode(v)` / `get_alert_mode()` | `alert_mode` property |
| `set_ideality_factor_index(v)` / `get_ideality_factor_index()` | `ideality_factor_index` property |
| `get_ideality_factor()` | `ideality_factor` (read-only) |
| `set_ffdc_raw(v)` / `get_ffdc_raw()` | `ff_dc_raw` property |
| `set_ff_zero_detection(on)` / `ff_zero_detection()` | `ff_zero_detection` property |
| `set_ff_mode(v)` / `get_ff_mode()` | `ff_mode` property |
| `set_rd_mode(on)` / `rd_mode_enabled()` | `rd_mode` property |
| `set_rd_polarity(v)` / `get_rd_polarity()` | `rd_polarity` property |
| `set_alert_mask(v)` / `get_alert_mask()` | `alert_mask` property |

Migration pattern: `dev.set_ramp_rate(MAX31760.RAMP_IMMEDIATE)` becomes
`dev.ramp_rate = MAX31760.RAMP_IMMEDIATE`; `dev.manual_enable(True)` becomes
`dev.manual = True`. Percent-convenience writers (`set_duty_pct()`,
`set_ffdc_pct()`) and all surviving verbs keep their names.

### BREAKING: behavior changes

- `measure_tach_once()` now RAISES `TimeoutError` when the TC count does not
  change within `timeout_ms` (previously returned the pre-stretch count).
  A stopped fan (count legitimately unchanged) now times out instead of
  returning 0; PSEN is still cleared on timeout.
- Reading `pwm_freq_hz` raises `ValueError` on an unrecognized CR1 DRV bit
  combo instead of silently falling back to 33 Hz (unreachable today; the
  field is exactly 2 bits with four encodings).
- Keyword-only fences: `timeout_ms` on `wait_for_duty()`,
  `measure_tach_once()`, `save_config()`, `load_config()`,
  `recover_from_corruption()` and `settle_ms` on `soft_por()` must now be
  passed by keyword; positional calls break.
- Legacy-smbus fallback (`_SmbusCompat.read_i2c_block_data`) raises
  `OSError` on short payloads instead of silently truncating.

### Added

- Context-manager support (`with MAX31760(...) as dev:`), `__repr__`
  (`<MAX31760 addr=0xNN>`), and a no-op core `close()` so portable code can
  close on both platforms.
- Honest facade exports: explicit `__all__` at the package root; `mp.py`/
  `cp.py` re-export the full public surface (~90 names each) with identity
  enforced by the parity gate.
- `max31760/_regs.py` leaf module (register map + fixed-point helpers);
  the circular import between `_core.py` and `_faults.py` is gone.
- Conservative built-in-type annotations on public signatures (whitelist:
  `int`, `float`, `bytes`, `str`, `bool`).
- Docstring surgery: per-method `Raises:` sections, destructive-read
  warnings leading `status_raw()`/`active_alarms()`, constructor docstrings,
  F#/D# legend pointers; bench evidence carved out to
  `NOTES/06-eeprom-timing.md`.

### Changed

- Error messages migrated from `%`-formatting to f-strings (MicroPython
  >= 1.17 supports PEP 498; project baseline v1.29.0).
- Duplicate big-endian 16-bit decodes consolidated into `_u16_get`/
  `_u16_set` helpers; `build_lut_curve()` rewritten with `zip`/`bisect`.
- Lint gate amended: f-strings accepted; type annotations restricted to the
  five-name built-in whitelist.
- Test suite grown 134 → 151 tests (facade-export, context-manager, repr,
  smbus-compat-contract, and regs-module coverage).

### Validated on

- Host gates: 151 unit tests OK, API-coverage PASS (97 public members),
  MicroPython-subset lint PASS ×8, compileall clean.
- Hardware E2E (Pico W, ESP32-S3, RPi 3A+): pending Phase H1/H2 runs;
  merge/tag gated on all three passing.

## [0.1.0] - 2026-11-08

Initial release (frozen). Dual-platform Python driver for the Maxim MAX31760
precision fan-speed controller (MikroElektronika Fan 2 Click), with an
identical public API on both targets.

### Changed

- CPython support floor raised from `>=3.7` to `>=3.10` (drops Python
  3.7–3.9, all EOL). Encoded as `>=3.10` rather than `>3.9`: under PEP 440
  version normalization, bare `>3.9` would still admit 3.9.x patch
  releases. Note that 3.10 itself is EOL (Oct 2026) and sits just below
  the CI test matrix (3.11–3.15); declared support is intentionally one
  minor wider than the tested range. (Shipped in 0.1.0; previously omitted
  from this section.)

### Added

- Shared protocol core (`max31760/_core.py`) plus thin per-platform
  transports and facades:
  - MicroPython: `from max31760.mp import MAX31760` (`machine.I2C`,
    `readfrom_mem`/`writeto_mem`)
  - CPython/Linux SBC: `from max31760.cp import MAX31760` (`smbus2`,
    fallback system `python3-smbus`)
- Full datasheet feature surface: local/remote temperature sensing, 48-step
  temperature→PWM LUT (automatic mode), manual/direct duty control with
  settle-wait, tachometer/RPM measurement (both ports), fan-fail detection
  & FFDC recovery, thermal thresholds/alerts with mask + service routine,
  EEPROM save/load with tW busy-window handling, soft POR, standby, user
  memory, spin-up/pulse-stretch/tacho-full assists, and one-shot presets
  (4-wire fan, 3-wire supply modulation, dual-fan).
- Exception-based error model: `ValueError` (bad argument / RO write /
  out-of-map), `OSError` (bus NACK / missing chip), `TimeoutError`
  (duty settle, EEPROM window). Nothing fails silently.
- Host-runnable test suite: 134 mock-backed unit/integration tests against a
  behavioral mock chip with wire-legality assertions, plus a fake SMBus for
  the CPython adapter.
- Quality gates: API coverage (every public member referenced by the suite),
  mp/cp API-parity gate, MicroPython-subset lint gate, `compileall` syntax
  gate.
- Polished examples (`examples/`) and the canonical tri-platform smoke/E2E
  suites; hardware bench scripts grouped by bench under `scripts/`.
- Documentation: full API reference (`docs/README.md`), research notes
  (`NOTES/`), master plan (`PLANS.md`), decisions log D1–D34 (`SUMMARY.md`).

### Validated on

- RPi Pico W (first edition, RP2040) — MicroPython v1.19.1 and v1.29.0:
  smoke PASS, E2E matrix 12/12 PASS.
- ESP32 — MicroPython v1.29.0: smoke PASS, E2E matrix 12/12 PASS.
- Raspberry Pi 3A+ (Debian 13, Python 3.13.5, smbus2) — CPython: smoke PASS,
  E2E matrix 12/12 PASS, soft-POR reliability brute force 10/10.

Port-2/TACH2 *functional* items are EXCLUDED-HW on the single-fan bench and
covered by mock unit tests only.
