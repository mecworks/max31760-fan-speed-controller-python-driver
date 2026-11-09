# TODO

Living list of roadmap items and known issues for the MAX31760 dual-platform
driver. Completed items move to the `SUMMARY.md` build log; deliberate
deferrals live under **Deferred**.

Status at v0.1.0 freeze (2026-11-08): no known functional driver bugs —
134 mock-backed unit/integration tests GREEN, all quality gates PASS, E2E
hardware matrix 12/12 PASS on all three benches (Pico W RP2040, ESP32,
RPi 3A+ CPython). The items below are roadmap work, environment caveats,
and tech debt.

## Roadmap

- [x] **R1 — Push to GitHub** as `max31760-fan-speed-controller-python-driver`.
      **DONE 2026-11-09:** root commit `c31228c` (81 files) pushed to
      <https://github.com/mecworks/max31760-fan-speed-controller-python-driver>
      (public). Datasheet PDF stayed local only (vendor copyright; canonical
      URLs documented in README References).
- [ ] **R2 — ESP32 re-validation with the D33 core** *(blocked: board
      disconnected).* Redeploy `_core.py` to `:/lib/max31760/_core.py`,
      re-run `hw_smoke_test.py` + `e2e_hardware_test.py`, confirm 12/12.
      The deployed copy predates D33; the change is strictly additive
      robustness (`soft_por()` error handling), so risk is low.
- [ ] **R3 — Pico 2 W / RP2350 validation** *(blocked: hardware not owned).*
      Expected to work unchanged (same `rp2` port family); untested.
- [ ] **R4 — BeagleBone / generic SBC live validation.** Docs claim support
      (CPython/smbus2 path); only Raspberry Pi silicon has been exercised.
      Validate bus numbering, pin mapping, and the errno-121 behaviour of
      non-bcm2835 I²C controllers (design assumption from D33).
- [ ] **R5 — Expand the Examples page** (Wiki.js `-Examples` +
      `examples/README.md`). Flagged for future sessions: more worked
      examples (dual-fan config, ALERT ISR on both platforms, LUT curve
      fitting, EEPROM persistence workflows).
- [ ] **R6 — Wheel CI / PyPI publishing** *(deferred per D3).* Trigger: a
      real second consumer appears. See Deferred.

## Known issues & tech debt

- [ ] **K1 — RPi `clk_tout_ms` tuning is non-persistent.** The bcm2835
      timeout was raised 35 → 700 ms via sysfs during the D32/D33
      investigation; it resets on reboot. Candidate fix: a small
      systemd/udev drop-in for bench reproducibility. Not required for
      driver correctness (D33 removed the dependence on it) — ops comfort
      only.
- [x] **K2 — Home-LAN identifiers redacted (2026-11-09).** `SUMMARY.md`,
      `PLANS.md`, and `scripts/README.md` previously contained the RPi SSH
      host (`user@192.168.x.x`) and a Windows username in a path. All removed;
      replaced with "local RPi over SSH" / generic paths. No credentials were
      ever present.
- [ ] **K3 — `examples/esp32_demo.py` carries placeholders** (pin/bus
      values to adapt per board). Fine as a template; document adaptation
      steps when R2 lands.
- [ ] **K4 — mpremote dev-dependency decision open.** Recommended: document
      `pip install mpremote` in CONTRIBUTING (done) and optionally add a
      `requirements-dev.txt`. Low priority.
- [ ] **K5 — ESP32 deployed `_core.py` predates D33.** Superseded by R2;
      tracked here so the stale copy isn't forgotten if the board sits
      disconnected for a while.
- [ ] **K6 — Align `requires-python` with CI coverage.** `pyproject.toml`
      claims `>=3.7`; CI now tests 3.11–3.13 (3.9 dropped 2026-11-09: EOL,
      no Ubuntu 26.04 runner build). Decide whether to tighten
      `requires-python` to `>=3.11` or keep the broad claim (MicroPython
      parity makes the CPython floor mostly theoretical).

## Fixed this session (2026-11-09)

- `docs/README.md` §7: duplicated item number (two "6." entries) — renumbered.
- `docs/README.md` §8: stale test count (127 → 134).
- Removed cloned upstream repo `reference/MAX31760-Python/` (findings
  preserved in `NOTES/02-reference-driver-review.md`).
- Datasheet decoupled from the repo: gitignored + canonical primary/backup
  URLs added to README, docs/README, NOTES/01, PLANS, SUMMARY.
- License finalized as **LGPL-2.1-or-later** (was an MIT placeholder):
  `LICENSE` rewritten (canonical GNU text, © Marc Christensen),
  `pyproject.toml` license/classifier/authors updated, `CONTRIBUTING.md`
  licensing section updated.
- Home-LAN details (SSH user/IP, Windows username) redacted from PLANS.md,
  SUMMARY.md, scripts/README.md (K2 closed).

## Deferred (deliberate)

- **PyPI/wheel publishing (D3)** — revisit when a second consumer exists;
  until then `pip install .` from the repo is the distribution story.
- **ESP8266-class boards (D16)** — out of scope; feature set exceeds their
  RAM. rp2/esp32 ports cover the need.
- **Licensing** — released under **LGPL-2.1-or-later** (final decision
  2026-11-09; supersedes the earlier MIT placeholder). No further relicensing
  anticipated.
