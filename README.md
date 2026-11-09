# max31760 — Dual-Platform Driver for the Maxim MAX31760 Fan-Speed Controller

Licensed under **LGPL-2.1-or-later** (see [LICENSE](LICENSE)).

Production-quality Python driver for the Maxim **MAX31760** precision fan-speed
controller (as used on the MikroElektronika Fan 2 Click). One package, identical
public API on both platforms:

| Platform | Entry point | Transport |
|----------|-------------|-----------|
| MicroPython (RPi Pico RP2040/RP2350, ESP32-class) | `max31760.mp` | `machine.I2C` (`readfrom_mem`/`writeto_mem`) |
| CPython / Linux SBC (Raspberry Pi all models, BeagleBone, clones) | `max31760.cp` | `smbus2` (fallback: system `python3-smbus`) |

**Full documentation:** [`docs/README.md`](docs/README.md) — wiring, per-platform
installation, quick starts, complete API reference, error model, operational
notes, ALERT ISR pattern.

Validated live on: RPi Pico W (first edition, RP2040 — MicroPython v1.19.1 and
v1.29.0), ESP32 (MicroPython v1.29.0), and Raspberry Pi 3A+ (CPython/smbus2);
E2E hardware matrix 12/12 PASS on all three. See `PLANS.md` §7 for results
tables.

## Quick start

### MicroPython (RPi Pico / ESP32)

Deploy the package into `/lib` first (see docs §2), then:

```python
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))   # Pico GP1/GP0
dev = MAX31760(i2c, addr=0x50)

assert dev.verify()
print(dev.local_temp_c, dev.remote_temp_c)

dev.configure_4wire_fan(port=1)      # recommended preset
dev.manual_enable(True)              # presets are mode-neutral (DFC untouched)
dev.set_duty_pct(50.0)
dev.wait_for_duty(50.0)
print(dev.rpm(1))
```

### CPython / Linux SBC

```bash
pip install .          # pulls smbus2 on Linux; or: pip install smbus2
```

```python
from max31760.cp import MAX31760

dev = MAX31760(bus=1, addr=0x50)     # bus 1 = /dev/i2c-1 on Raspberry Pi
assert dev.verify()
dev.close()                          # releases the bus if this object opened it
```

Enable I²C per platform first (per-family steps in docs §2; verify with
`i2cdetect -y <bus>` — expect `50`).

## Examples

| Script | Purpose |
|--------|---------|
| `examples/pico_demo.py` | Pico demo: probe → temps → duty sweep → RPM → save config |
| `examples/esp32_demo.py` | ESP32-S3 variant (pin/bus placeholders to adapt) |
| `examples/rpi_demo.py` | Raspberry Pi (CPython) demo |
| `examples/hw_smoke_test.py` | Core-behaviour smoke test, self-restoring (board-aware pins) |
| `examples/e2e_hardware_test.py` | Full 12-section E2E matrix over every public API domain (board-aware pins) |

Both test scripts auto-select I²C pins via `sys.platform` (`rp2` → GP0/GP1,
`esp32` → GPIO41/42) and restore all configuration when done.

## Repository layout

| Path | Contents |
|------|----------|
| `max31760/` | The driver package (shared core + `mp`/`cp` facades) |
| `examples/` | Polished demos + the canonical tri-platform smoke/E2E suites |
| `tests/` | Host-runnable, CI-collectable unit/integration suite (mock-backed) |
| `tools/` | Dev quality gates (API coverage, lint subset) |
| `scripts/` | Hardware bench validation & diagnostics, grouped by bench (`pico/`, `esp32/`, `rpi/`) — see `scripts/README.md` |
| `docs/` | Full API reference, wiring, installation |
| `NOTES/` | Research notes (datasheet analysis, reference review, MP constraints) |
| `reference/` | Local copy of the datasheet PDF (kept out of git — see References) |

## Development

Host-side gates (all green at v0.1.0 freeze):

```bash
python -m unittest discover tests    # 134 mock-backed unit/integration tests
python tools/api_coverage.py         # every public member exercised by the suite
python tests/lint_subset.py          # MicroPython-subset compliance gate
python -m compileall max31760        # syntax gate
```

Planning & history: `PLANS.md` (checklists, F-requirements, E2E results) and
`SUMMARY.md` (decisions log D1–D34, build log, handoff context).

Hardware bench scripts (validation/diagnostics per bench) are in `scripts/`
— they need real hardware and are not part of the test suite.

## References

- **MAX31760 datasheet** — Maxim Integrated DS 19-7395 Rev 0 (4/14):
  - Primary: <https://download.mikroe.com/documents/datasheets/MAX31760.pdf>
  - Backup: <https://www.analog.com/media/en/technical-documentation/data-sheets/max31760.pdf>

  A local copy is kept at `reference/MAX31760.pdf` for offline work; it is
  gitignored because we don't own the copyright and won't redistribute it.
- MikroElektronika Fan 2 Click (target board): <https://www.mikroe.com/fan-2-click>
