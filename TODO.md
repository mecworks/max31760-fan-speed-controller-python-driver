# TODO

Living list of roadmap items and known issues for the MAX31760 dual-platform
driver. Completed items move to the `SUMMARY.md` build log; deliberate
deferrals live under **Deferred**.

Status at v0.1.1 (2026-11-21): the PLANS_0.1.1.md refactor is COMPLETE —
all 15 CODE_REVIEW_FOR_0.1.1.md items remediated, merged to `main` and
tagged `v0.1.1`. 153 mock-backed unit/integration tests GREEN, all quality
gates PASS, E2E hardware matrix 12/12 PASS on all three benches (Pico W
RP2040, ESP32-S3, RPi 3A+ CPython) re-run against the refactored package.
The items below are roadmap work, environment caveats, and tech debt.

## Roadmap

- [x] **R1 — Push to GitHub** as `max31760-fan-speed-controller-python-driver`.
      **DONE 2026-11-09:** root commit `c31228c` (81 files) pushed to
      <https://github.com/mecworks/max31760-fan-speed-controller-python-driver>
      (public). Datasheet PDF stayed local only (vendor copyright; canonical
      URLs documented in README References).
- [x] **R2 — ESP32 re-validation with the D33 core.** **DONE 2026-11-21:**
      fulfilled by the v0.1.1 Phase H2 leg 1 run — the full v0.1.1 package
      (D33-era `_core.py` included) deployed to `/lib/max31760/` on the
      ESP32-S3 (COM7, MicroPython v1.29.0); `hw_smoke_test.py` PASS and
      `e2e_hardware_test.py` 12/12 PASS, configuration restored
      byte-for-byte.
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
- [ ] **R7 — `rpm()` staleness guard** *(future release; carried out of
      0.1.1 scope per PLANS_0.1.1.md Revision 4).* The MAX31760 tachometer
      latches pulse PERIODS (TC1H/L in 100 kHz ticks, averaged over 4
      pulses), not counts: once the fan stops producing pulses (fan stopped,
      or exactly 0 % commanded duty on a fan that idles at its minimum
      speed), no new period is ever measured and the register keeps its last
      value indefinitely, so `rpm()` reports a stale frozen speed
      indistinguishable from a live one. Bench evidence: `actual_duty_raw`
      held 0 for 30 s while `rpm(1)` stayed at 2331.0; at 0 % duty the chip
      reported 2320.2 rpm while the optical meter read ~650. Candidate
      designs: cross-check the SR tach-alarm bits, or flag an unchanging
      non-zero reading over a time window. Companion doc debts from the same
      discovery: document the 0 %-duty-means-minimum-speed Intel 4-wire
      convention in docs/examples, and note the effective LUT control range
      (~22–100 % duty) for the bench fan (Cooler Master SickleFlow 92; hard
      min-speed floor ~656 rpm below ~22 %). Data:
      `NOTES/bench-data/duty_curve_1pct.csv` / `fan_curve_1pct.png`;
      diagnosis trail in PLANS_0.1.1.md (Surprises, H2 leg 2).

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
- [x] **K5 — ESP32 deployed `_core.py` predates D33.** RESOLVED 2026-11-21:
      the v0.1.1 deployment (Phase H2 leg 1) replaced the stale copy; see R2.
- [x] **K6 — Align `requires-python` with CI coverage.** RESOLVED
      2026-11-09: user set the supported floor to "greater than 3.9" →
      `requires-python = ">=3.10"` (encoded as `>=3.10`, not `>3.9`, because
      PEP 440 lets `>3.9` still match 3.9.x patches). 3.10 is EOL (Oct
      2026) and below the CI matrix (3.11–3.15); declared support
      intentionally one minor wider than tested.
- [ ] **K7 — RPi bench local-temp channel reads ~54 °C vs ~23.5 °C room
      ambient.** Found during the v0.1.1 H2 leg 2 (2026-11-21). The heat is
      STATIC — independent of drive state (standby endpoint test: 54.2 °C
      pre-standby → 54.2 °C post-standby after ~3 min quiescent) — and the
      PWM driver stage is exonerated across the full duty range (modulation
      checks + the 1 % curve mapping track command smoothly). Live suspect:
      the LOCAL sensor path itself, possibly damaged in the earlier SDA/SCL
      miswiring incident. NON-BLOCKING for the release (production use case
      indexes REMOTE). Arbitration test staged but never run:
      `scripts/rpi/rpi_dual_temp_check.py` (external PNP transistor in
      direct thermal contact with the chip; remote ≈50+ °C ⇒ genuinely hot
      die ⇒ swap the power source, then replace the click; remote
      ≈28–30 °C ⇒ local sensor path damaged). The same chip read ~24–26 °C
      local on the Pico W and ESP32-S3 benches.

## Completed this session (2026-11-21)

- **PLANS_0.1.1.md executed end-to-end (M0–M9)** — all 15 items from
  `CODE_REVIEW_FOR_0.1.1.md` remediated on branch `v0.1.1-refactor`:
  `_regs.py` leaf-module extraction (circular import eliminated), context
  manager / `__repr__` / legacy-smbus payload contract, fail-loud tach and
  PWM guards + keyword-only timeout/settle fences, honest facade exports,
  accessor unification (properties for state, verbs for actions — ~30
  breaking renames, no shims per D-15), f-string sweep, conservative
  built-in-type annotations, docstring surgery, version bump + CHANGELOG.
- **All three hardware platforms re-validated on v0.1.1** (sequential,
  single relocated chip): Pico W (COM16), ESP32-S3 (COM7), RPi 3A+ (over
  SSH) — `hw_smoke_test.py` PASS + `e2e_hardware_test.py` 12/12 PASS on
  each; benches left in factory state. Host gates: 153 tests OK,
  api-coverage 97 members PASS, lint ×8 PASS, compileall clean.
- **Merged to `main` + tagged `v0.1.1`** (fast-forward; `main` is 14
  commits ahead of `origin/main` — NOT pushed, standing default).
- **New tooling**: `tools/api_audit.py` (3-stage AST audit of
  examples/scripts for pre-0.1.1 API usage — 46 files, PASS) and
  `tools/deploy_mp.py` (hash-verified chunked-base64 MicroPython deployment;
  mpremote 1.29.0 `cp`/`fs cp` are broken on this setup).
- **Fan characterized** (Cooler Master SickleFlow 92): 1 % duty sweep,
  101 points × 15 s settle — min-speed floor ~656 rpm below ~22 % duty,
  smooth near-linear rise to 2311 rpm @99 %; CSV + chart archived under
  `NOTES/bench-data/`.
- **Tachometer architecture established**: period-of-pulse-group latching
  (not windowed counting) — root cause of the `rpm()` staleness at fan stop
  / 0 % duty; carried as R7.
- **RPi thermal anomaly investigated**: heat proven static and
  drive-independent; driver stage exonerated; carried as K7 (arbitration
  test staged, not run).
- **R2 and K5 closed** (the ESP32 redeployment happened as part of H2 leg 1).

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
