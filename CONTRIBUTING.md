# Contributing

Thanks for helping improve the MAX31760 driver. This project targets two
platforms with one shared core, so contributions must keep both sides green.

## Prerequisites

- Python ≥ 3.7 (host side; CPython 3.13 recommended for development).
- For CPython transport work on Linux: `pip install smbus2`.
- For MicroPython device work: `pip install mpremote` (one command per
  invocation: `python -m mpremote connect port:COM<N> <single_cmd>`).
- Hardware (optional but encouraged for behavioural changes): MikroElektronika
  Fan 2 Click on a Pico (GP0/GP1), ESP32 (GPIO41/42), or RPi (I²C bus 1).

## Running the quality gates

Every change must pass all four host-side gates (no hardware needed):

```bash
python -m unittest discover tests    # 134 mock-backed unit/integration tests
python tools/api_coverage.py         # every public member referenced by the suite
python tests/lint_subset.py          # MicroPython-subset compliance (shared modules)
python -m compileall max31760        # syntax gate
```

CI runs the same gates on every push/PR (see `.github/workflows/ci.yml`).

## Ground rules

- **Shared-core purity:** `max31760/_core.py`, `_tables.py`, `_lut.py`,
  `_faults.py` must stay free of CPython-only imports/constructs (enforced
  by the lint-subset gate). Platform differences belong in
  `_transport_mp.py` / `_transport_cp.py` and the `mp`/`cp` facades.
- **Integer-centric API:** no string keys, no per-call dict allocations in
  hot paths — MicroPython memory budget matters.
- **Error model:** `ValueError` (bad argument / RO write / out-of-map),
  `OSError` (bus NACK / missing chip), `TimeoutError` (duty settle, EEPROM
  window). Never fail silently; never swallow a bus error except where the
  silicon semantics demand it (see `soft_por()`, decision D33).
- **Transport calls:** use `readfrom_mem`/`writeto_mem` only — never
  `mem_read`/`mem_write` (absent on some MicroPython builds).
- **New public API ⇒ tests:** every new public member needs a mock unit
  test AND an on-device E2E slice (or an explicit EXCLUDED-HW justification
  if the bench can't express it). The parity gate requires identical
  surfaces on `mp` and `cp`.
- **Docs:** update `docs/README.md` (API tables), `README.md` (if layout or
  quick-start changes), and `CHANGELOG.md` (unreleased section) in the same
  PR.

## Hardware testing conventions

- Bench scripts live in `scripts/{pico,esp32,rpi}/` — they import
  `machine` / need real hardware and are deliberately NOT collected by the
  unit-test suite.
- E2E matrices are self-restoring: snapshot registers 0x00..0x4F, exercise
  everything, restore byte-for-byte, re-save EEPROM block 00-0F. Keep new
  slices self-restoring too.
- RPM assertions must use bounded convergence waits (fan spin-up transient,
  decision D34) — never fixed sleeps.
- Device filesystem constraints (MicroPython): cannot `rm` directories or
  `cp` whole directories — copy individual `.py` files. Deploy location:
  `:/lib/max31760/`.

## Licensing

The project is licensed under the **GNU Lesser General Public License v2.1 or
later (LGPL-2.1-or-later)** — see `LICENSE`. By submitting a change you agree
that your contribution may be distributed under those terms. Note that the
LGPL permits linking against this library from proprietary code; if you add
code of your own to the library itself, it must remain LGPL-compatible.
