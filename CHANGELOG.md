# Changelog

All notable changes to the `max31760` driver are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-11-08

Initial release (frozen). Dual-platform Python driver for the Maxim MAX31760
precision fan-speed controller (MikroElektronika Fan 2 Click), with an
identical public API on both targets.

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
