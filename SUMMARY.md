# SUMMARY.md — MAX31760 Dual-Platform Driver: Research, Decisions & Handoff

**Purpose:** Companion to `PLANS.md`. Together these two documents let you (or another
agent) cold-resume this project at any point: all research findings, every decision with
rationale, the live hardware verification results, and explicit resume instructions.
**Last updated:** 2026-11-07 (after live connectivity verification on the bench).
**State:** Research COMPLETE · Connectivity VERIFIED · Awaiting user review of
PLANS.md + SUMMARY.md → then Phase A coding begins.

---

## 1. Status Snapshot

- ✅ **CURRENT STATE (2026-11-08): v0.1.0 FROZEN; ALL THREE PLATFORMS VALIDATED** —
  Pico W RP2040 (COM16, MicroPython v1.29.0), ESP32 (COM7, v1.29.0), RPi 3A+
  CPython (Debian 13 / Python 3.13.5 / smbus2). The long-standing RPi
  `soft_por()` errno-121 blocker was ROOT-CAUSED and FIXED this session (D33):
  the chip resets mid-transaction on SW_POR latch, so the write must be issued
  exactly once with its expected error swallowed — retries re-fire the POR.
  RPi smoke + E2E matrix now 12/12 PASS; reliability check 10/10. The Pico
  was then redeployed with the D33 core and revalidated (smoke + E2E 12/12).
  Only remaining follow-up is user-driven: ESP32 re-validation when
  reconnected.
- ✅ Requirements & protocol research done (datasheet fully analyzed; upstream driver reviewed).
- ✅ Architecture decided (Option C: shared core + thin per-platform transports).
- ✅ All planning questions resolved; PLANS.md v3 has no open design questions.
- ✅ Real hardware connected and verified: MAX31760 answers at 0x50 on the Pico W (first edition, RP2040);
  both temperature channels read correctly (§6).
- ⚠️ One plan correction from live testing: MicroPython transport must use
  `readfrom_mem`/`writeto_mem`, not `mem_read`/`mem_write` (absent on v1.19.1 RP2040).
  Clarified post-Q&A (2026-11-07): those names are NON-STANDARD (zero mentions in official
  latest docs) ⇒ absent on ALL MicroPython ports incl. ESP32-S3; unrelated to the CPython
  SBC path (smbus2, never touches machine.I2C). No per-platform branching needed.
- ⏸️ ~~Coding NOT started~~ **▶️ BUILDING** — user go-ahead given 2026-11-07; Phase A
  (foundations) in progress. Docs kept current continuously as the resume source of truth;
  milestones checked off in PLANS.md as confirmed.
- 📌 Session checkpoint (pre-context-compression, 2026-11-07): all planning docs final;
  connectivity test PASSED (both temp sensors read); user asked one clarifying question
  (answered above); next event = user says "proceed" → Phase A task A1.
- ✅ **Phase A COMPLETE (2026-11-07)** — package scaffolded; constants verified vs datasheet;
  transport + retry + page-safe writes + fixed-point helpers implemented; 32 host unit tests
  green; MicroPython-subset lint gate green; LIVE E2E on Pico passed (probe, both temps,
  writeto_mem round-trips). See §12 Build Log.
- ▶️ **Phase B IN PROGRESS (2026-11-07)** — B1 (init/self-test), B2 (temps + setpoints),
  B3 (LUT get/set/index + curve builder) done & hardware-verified; 56 host unit tests green;
  size-budget policy amended (D15/D16): pure data/geometry extracted to `_tables.py` /
  `_lut.py`, `_core.py` back under its soft 16 KB target.

## 2. Project Goal

Production-quality **dual-platform Python driver** for the Maxim **MAX31760** precision
fan-speed controller (as used on the MikroElektronika Fan 2 Click):

- **MicroPython target:** RPi Pico (RP2040/RP2350), ESP32-class boards, MicroPython ≥ 1.17.
- **CPython target:** any Linux SBC with I²C — primary docs for Raspberry Pi (all models
  incl. Zero/Zero 2), BeagleBone, common RPi clones; generic guidance otherwise.

One `max31760` package, **identical public API** on both platforms (parity enforced by
construction via a shared core, plus an automated parity test). Full feature surface:
temperature sensing (local + remote diode), 48-step LUT auto fan control, manual duty,
tach/RPM, fan-fault handling, thermal thresholds/alerts, EEPROM persistence, lifecycle.

Success criteria (PLANS.md §1/§9): every datasheet feature reachable through a clean,
documented, integer-centric API; host unit tests green against a behavioral mock; shared
core runs unmodified on Pico and ESP32 ports; no CPython-only constructs in shared code;
parity gate passes.

## 3. Environments

| Role | Detail |
|------|--------|
| Dev host | Windows desktop, Python 3.14, pyserial 3.5. mpremote NOT yet installed (candidate dev dep). |
| Primary bench (connected) | RPi Pico W (**first edition, RP2040** — misidentified as Pico 2 W until the 2026-11-08 reflash), MicroPython v1.29.0 (reflashed 2026-11-08; originally v1.19.1), USB-serial **COM16** @ 115200 8N1 |
| Bench wiring | I2C0: SDA = GP0 (board pin 1), SCL = GP1 (board pin 2); MAX31760 @ 0x50 (A2:A0=GND) |
| Bench peripherals | 1 fan on TACH1/port 1 (port 2 empty); 2N3906 PNP thermal diode on DXP/DXN |
| Later cross-checks (user-run) | Raspberry Pi (exercises CPython path), ESP32-S3 (exercises MicroPython path) |

Agreed workflow: develop locally, iterate/test on the connected Pico throughout Phases A–B;
user later repeats key tests on RPi and ESP32-S3.

## 4. Research Findings

### 4.1 MAX31760 datasheet (Maxim DS 19-7395 Rev 0)

Datasheet online: primary https://download.mikroe.com/documents/datasheets/MAX31760.pdf ;
backup https://www.analog.com/media/en/technical-documentation/data-sheets/max31760.pdf
(local copy `reference/MAX31760.pdf`, gitignored — vendor copyright).
Full analysis: `NOTES/01-datasheet-analysis.md`. Essentials that drive the design:

- **Addressing:** 7-bit slave addr 0x50–0x57 (A2:A0 pins); Fast mode OK. Our device = 0x50.
- **Write model:** pointer-incrementing; **8-byte pages wrap within page** ⇒ bulk writes
  must be chunked per 8-byte row (STOP between rows). Reads may span pages freely.
- **Temperature format:** 16-bit two's complement, left-aligned; LSB = bit5 = 0.125 °C;
  range ≈ −128…+127.875 °C. Encode `raw16 = round(c*8)<<5`; decode `(sign_ext(raw)>>5)/8`.
- **LUT:** 48 bytes @ 0x20–0x4F; window i covers `<18 °C` (i=0), `18+2i ≤ T < 20+2i`
  (i≥1), `≥110 °C` (i=47); duty = value/256; hysteresis 2 or 4 °C.
- **Tach:** internal 100 kHz counter averaged over 4 pulses; `RPM = 6e6/(count·n_pulses)`;
  fail when count > threshold OR overflow; 3-strike queue; FFDC forced duty on failure.
- **EEPROM:** EEX reg 0x5B (bit7 load/save + 16-byte block select); after save the chip
  NACKs itself up to **550 ms** ⇒ ack-poll or timed wait mandatory.
- **SR (0x5A):** alarm bits **clear on read**; interrupt-mode ALERT service =
  read SR → … → clear ALTMSK.
- **Key regs:** CR1 0x00 (PWM freq/polarity, index source, hysteresis, SW-POR),
  CR2 0x01 (DFC, SPEN, FFMode, STBY…), CR3 0x02 (CLRFAIL, RAMP, PSEN, TACH1E/TACH2E),
  setpoints 0x06–0x0D, USER mem 0x10–0x17, PWMR/PWMV 0x50/0x51, TC1/TC2 0x52–0x55,
  RTH/RTL 0x56/0x57, LTH/LTL 0x58/0x59, SR 0x5A, EEX 0x5B.
- Factory defaults confirmed live: CR1=`01`, CR2=`10`, CR3=`03`, FFDC=`FF` (see §6).

### 4.2 Reference driver review (rudybrian/MAX31760-Python)

Cloned to `reference/` (research only — never modify). Verdict: **rewrite from scratch**,
do not port. Details: `NOTES/02-reference-driver-review.md`. Fatal bugs found:

- **B1:** `self.self.` typo crashes `writeControlRegister1("PWM_frequency", …)`.
- **B2:** spin-up uses wrong bit (ALERT 0x40 instead of SPEN 0x20).
- **B3:** tach threshold computes 16-bit but writes one un-clamped byte to the high reg.
- **B4:** RPM read divides by zero when fan stopped; can't detect count overflow.
- **B5:** fire-and-forget EEPROM save ignores the 550 ms busy window.
- Structural: Python 2 syntax, smbus-only (Linux), string-keyed APIs, dict allocation per
  status read, 48 separate transactions for a LUT read.

### 4.3 MicroPython transport (incl. LIVE finding)

Baseline API (decision, 2026-11-07): **`readfrom_mem(addr, reg, n)` /
`writeto_mem(addr, reg, buf)`** — long-standing, present on all supported ports, handles
dummy-write + repeated-start internally. `scan()` for discovery/probe.

⚠️ **Live finding (2026-11-07):** `I2C.mem_read`/`mem_write` raised AttributeError on the
actual target (v1.19.1, RP2040 port). Follow-up check of the official latest MicroPython
docs shows these names are **not part of the standard API at all** (zero mentions) — so
this is neither a Pico-port quirk nor a firmware-version gap; expect them equally absent
on ESP32-S3 and every other port. (The original "since v1.17" note in NOTES/03 was wrong.)
Consequence:
no capability probing needed — just use the classic names everywhere. (`writeto_mem`
presence to be confirmed at the first Phase-A write; expected.)

Note: this is confined to the MicroPython side. The CPython/SBC path (full-Python RPi,
BeagleBone, etc.) never uses `machine.I2C` — it goes through `smbus2` on `/dev/i2c-N`
in `_transport_cp.py`. No cross-environment differentiation is required.

Raw-serial REPL delivery gotchas (hit during the connectivity test):
- Indented blocks need a terminating blank line to execute.
- A single-line compound statement (`if c: s`) swallows subsequent lines into its suite.
- Reliable patterns: flat one-liners per statement (worked for the probe), or ship scripts
  to flash (`mpremote cp x.py` then `exec(open('x.py').read())`). Candidate dev tooling:
  `pip install mpremote` (pure Python, works on Windows).

### 4.4 CPython transport

- Library: **smbus2** (pure Python, maintained, no compilation), with a 5-line
  `import smbus` fallback for stock `apt install python3-smbus` images.
- Quirk: `read_i2c_block_data(addr, reg, size)` returns a list whose `[0]` is the register
  byte (prepend quirk) — adapter strips it.
- Bus number is a constructor parameter (default 1 = `/dev/i2c-1` on RPi); enablement
  differs per distro/board ⇒ per-family docs (raspi-config, DT overlays) + generic
  `i2cdetect` fallback.

## 5. Decisions Log

| # | Date | Decision | Rationale |
|---|------|----------|-----------|
| D1 | 11-03 | **Architecture = Option C**: shared `_core.py` + thin per-platform transports (`_transport_mp.py`, `_transport_cp.py`), proper `max31760/` package | Identical API by construction (logic exists once); ~10% platform-specific code isolated & swappable; best testability. Option A (two independent files) rejected (~90% duplication drift); Option B (one adaptive file) kept as fallback only |
| D2 | 11-03 | CPython dep: **require `smbus2`**, 5-line `import smbus` fallback | Maintained, pure Python, no toolchain; fallback covers pre-installed system packages at near-zero cost |
| D3 | 11-03 | Distribution: **hybrid** — drop-in package + `requirements.txt` AND minimal `pyproject.toml` (`pip install .` works today) | Hobbyist fast path + machine-readable metadata; wheel CI & PyPI publishing deferred until a real second consumer appears |
| D4 | 11-03 | CPython scope: any Linux SBC with I²C; primary docs **RPi (all models)**, **BeagleBone**, RPi clones; generic guidance otherwise | User explicitly stated RPi is not the only target; bus number is a ctor param |
| D5 | 11-03 | Parity enforcement: shared core **+ automated parity test** comparing façades' exposed surface | Belt-and-braces against future façade divergence |
| D6 | 11-03 | Rewrite upstream driver from scratch (no porting) | Upstream bugs B1–B5 + structural issues (§4.2) make porting more costly than rewriting |
| D7 | 11-07 | Preset ramp rate default: **immediate** (not datasheet default 3.125 %/s) | Predictable behavior; user can override |
| D8 | 11-07 | `save_config()` default: **all-blocks** (full EEPROM range) unless explicit block mask passed | Convenience; user can restrict |
| D9 | 11-07 | Develop & test initially on the **connected Pico bench**; user later cross-checks on RPi + ESP32-S3 | Real-hardware verification available now; catches protocol assumptions early |
| D10 | 11-07 | MP transport baseline = **`readfrom_mem`/`writeto_mem`** (drop `mem_read`/`mem_write` and the pre-1.17 shim idea) | `mem_read` empirically absent on v1.19.1 RP2040; classic names are universal — simpler, no capability probe |
| D11 | 11-07 | Single-fan configs MUST disable TACH2E (and clear fan-fail via CLRFAIL) — promoted from "consider" to **mandatory** after live finding 2026-11-07 (B4): with no fan on port 2, the persistent TACH2A latches fan-fail after 3 detections and FORCES the PWM output to FFDC (factory 100%), overriding even manual duty commands | Bench has one fan on port 1; keeps SR clean AND prevents the output being pinned at full speed by a phantom fault |
| D12 | 11-07 | HW smoke test runs **incrementally** during Phases A–B on the bench, not only at the end | Connected hardware makes continuous real-world verification cheap |
| D13 | 11-07 | **E2E mandate**: every public API + internal function tested end-to-end on the real Pico bench (observable-effect verification: read-back, sensor sanity, audible fan response); EXCEPTION: fan port 2 / TACH2 functional tests (no second fan) → unit-tested only, marked EXCLUDED-HW | User directive; catches protocol assumptions against silicon, not just mocks |
| D14 | 11-07 | PLANS.md + SUMMARY.md are the authoritative resume artifacts; updated on every completed task, checkboxes ticked as confirmed | Survives session death / agent swap |
| D15 | 11-07 | **Size budget = soft guide**: ~16 KB per shared module is a target, not a ceiling; when a module grows past it, DECOMPOSE into small single-purpose modules (`_tables.py`, `_lut.py`) — NEVER trim functionality or documentation to fit size | User ruling 2026-11-07: "keeping the size small does help but should not come at the cost of functionality nor properly documented code". Decomposition keeps parity auditability while honoring the footprint theme |
| D16 | 11-07 | **ESP8266-class boards explicitly OUT OF SCOPE** for MicroPython targets (Pico RP2040/RP2350 + ESP32-class remain in scope) | User ruling 2026-11-07; removes design pressure toward ultra-tight-RAM compromises that would hurt in-scope targets |
| D17 | 11-07 | Data → `_tables.py`; LUT geometry/curve → `_lut.py`; protocol core stays in `_core.py` | Auditable decomposition (size-budget policy, D15) |
| D18 | 11-07 | B7 fault-handling domain extracted to `_faults.py` mixin (`FaultMixin`) | Keeps `_core.py` focused; ordering-safe circular import |
| D19 | 11-07 | PSEN functional proof requires external instrumentation (oscilloscope); E2E asserts API contract only | Stretched pulse invisible via PWMV or TC1 at bench fan speed (~2300 RPM) |
| D20 | 11-07 | TACHFULL used as the primary B8 functional observable | Freezes TC1 below 100% duty — deterministic, measurable via I²C |
| D21 | 11-07 | MP transport `probe()` switched from full-bus scan to single RO-register read (0x58) | Full scan too slow for 10 ms ack-poll cadence |
| D22 | 11-07 | Mock chip models EEX busy-window (NACK for 3 probe calls), PC persistence, SW_POR reset semantics | Required for meaningful EEPROM/POR unit tests |
| D23 | 11-07 | Presets are MODE-NEUTRAL: they do NOT set CR2.DFC | Factory default is LUT mode (DFC=0); forcing manual would surprise users wanting temperature-proportional control. Docstrings instruct calling `manual_enable(True)` separately |
| D24 | 11-07 | `close()` must exist on BOTH facades (no-op on MP) | C9 parity gate caught the asymmetry; portable code should be able to call `close()` unconditionally |
| D25 | 11-07 | FakeSMBus models EEPROM tW NACK at wire level (every transaction NACKs while `busy_polls > 0`) | Without this, TransportCP's `probe()` (a real register read) saw no busy state and EEX copies never applied on the CP path |
| D26 | 11-08 | **MicroPython deployment location = `/lib/max31760/`** (not filesystem root) | `/lib` is included in `sys.path` on all ports — standard location for third-party libraries (user correction 2026-11-08, confirmed by community guidance incl. mip auto-detection). Docs §2 updated; Pico redeployed same day. Side finding: the earlier root deploy had left `:/max31760/__init__.py` as a DIRECTORY containing the init file — package imported as a bare directory and `__init__` never executed; fixed during the move (real file now deployed, junk removed) |
| D27 | 11-08 | **Bench board ID corrected: first-edition Pico W (RP2040), not Pico 2 W (RP2350)** | User noticed while reflashing (2026-11-08). All "RP2350" references in PLANS/SUMMARY/docs corrected to RP2040. Validation claim now reads: proven on RP2040 (v1.19.1 + v1.29.0) and ESP32 (v1.29.0); Pico 2 W (RP2350) expected to work (same `rp2` port family) but UNTESTED — user does not have that board. Positive framing per user: passing on the OLDER hardware is the stronger compatibility proof |
| D28 | 11-08 | CP transport must NOT strip bytes from smbus2 block reads | Live verification on RPi 3A+: smbus2 returns clean payloads (no count/register prefix); stripping corrupted every read. Legacy system-smbus handled via the `_SmbusCompat` shim instead |
| D29 | 11-08 | EEPROM busy-window wait: conservative floor + no-op write-oracle proof (superseded by D32/D33) | Pure ack-polling proved unreliable on live silicon (spurious ACKs before the EEX command latches); a floor plus a write-proof was the interim design |
| D30 | 11-08 | Datasheet tW facts adopted as ground truth: 550 ms max full range; ~110 ms per 16-byte block; writes begin after STOP | From datasheet Note 4 AC table; basis for all busy-window sizing |
| D31 | 11-08 | Retry ladder: `RETRY_DELAYS_MS = (10, 30, 60, 100, 200, 400)` — cumulative span 800 ms > tW max 550 ms | Absorbs transient NACK bursts on every `_tx` call; kept as safety net even after D33 (harmless for normal ops) |
| D32 | 11-08 | `_wait_eeprom_ready` = fixed 700 ms pure delay (`EEPROM_WAIT_MS`), zero bus traffic, `TimeoutError` if budget < 700 ms | Above the datasheet worst case (550 ms); probes/oracles demonstrably interact badly with the silicon during commit windows |
| D33 | 11-08 | **ROOT CAUSE of the RPi soft-POR errno-121 failures: the chip executes SW_POR on latch and resets so fast that the in-flight transaction reports errno 121 even though the reset HAPPENED.** Fix: `soft_por()` issues the SW_POR write exactly once via the raw transport (bypassing the retry ladder — a retry re-fires the POR into a still-booting chip), swallows its OSError, polls until the device re-acknowledges (settle default raised 100 → 1000 ms), verifies responsiveness, then waits out the POR-triggered EEPROM-reload commit window | Proven live with a volatile-marker experiment (user memory reloads from EEPROM despite the error, 5/5 runs). Explains ALL prior observations: variable 6 ms–1.5 s "stalls" were boot times after repeated POR re-fires; only SW_POR-bearing writes failed; Pico/ESP32 tolerated the mid-transaction reset differently. Brute-force sequence went 0/10 → 10/10 after the fix |

Design rules carried into the build: integer-centric API (no string keys), no per-call
dict allocation, tables as tuples, floats only at final presentation values (temps, RPM,
%), each shared module targets ~16 KB (SOFT — decompose rather than truncate, D15),
Python-3-syntax valid under the MicroPython subset (lint-gated),
error model: `ValueError` bad args / `OSError` bus+NACK (retry once) / `TimeoutError`
EEPROM-busy overrun — never silent failures.

## 6. Live Hardware Verification (2026-11-07)

Procedure: raw-serial script `probe_temp.py` (repo root) drives the MicroPython REPL on
COM16 with flat one-liners: scan bus, read LOCAL_TEMP (0x58–0x59), REMOTE_TEMP
(0x56–0x57), SR (0x5A), CR1..FFDC (0x00–0x03). Decode uses the arithmetic sign-extension
trick `(((hi<<8)|lo)^0x8000)-0x8000` (avoids multi-line `def`/`if` in the REPL).

Results (chip freshly power-reset by user beforehand):

| Item | Result | Interpretation |
|------|--------|----------------|
| Bus scan | exactly one device: **0x50** | Clean bus, correct address |
| LOCAL_TEMP | **+26.500 °C** (raw `1A80`) | Onboard die sensor working |
| REMOTE_TEMP | **+27.750 °C** (raw `1BC0`) | 2N3906 on DXP/DXN working; +1.25 °C vs die at rest is plausible |
| SR | `0x02` (TACH2A) | Expected: CR3 enables TACH2 but port 2 is empty. TACH1A clear ⇒ fan on port 1 healthy |
| CR1/CR2/CR3/FFDC | `01`/`10`/`03`/`FF` | Matches datasheet factory defaults (Table 13) |

Both temp sensors confirmed readable — answering the user's question directly: yes, local
(onboard) and remote (external 2N3906 diode) both respond correctly.

Artifacts: `probe_temp.py` (kept in repo root as a reference probe; will be superseded by
`examples/hw_smoke_test.py`).

## 7. Operational Lessons (for whoever resumes)

1. **Never assume documented MicroPython API availability** — verify on the actual target
   firmware before designing around it (cost us one iteration; caught pre-build).
2. **Serial REPL scripting:** keep statements flat/single-line; terminate indented blocks
   with a blank line; avoid single-line `if c: s` (swallows following lines). For anything
   non-trivial, upload a `.py` to flash and `exec(open(...))`.
3. **Power-reset behavior:** after the user's power reset the chip came up cleanly with
   factory defaults — safe assumption for bring-up.
4. **Expected noise on this bench:** SR.TACH2A will be set while TACH2E=1 with port 2
   empty. Don't mistake it for a fault.
5. Temperature sanity check for future tests: local ≈ room ambient; remote ≈ local + 1–2 °C
   with the 2N3906 at rest.

## 8. Internet Resources

| Resource | Used for |
|----------|----------|
| Maxim DS 19-7395 Rev 0 — MAX31760 datasheet ([primary](https://download.mikroe.com/documents/datasheets/MAX31760.pdf) / [backup](https://www.analog.com/media/en/technical-documentation/data-sheets/max31760.pdf); local copy gitignored) | Protocol, registers, formats, fault model (NOTES/01) |
| https://www.mikroe.com/fan-2-click | Target board (Fan 2 Click) |
| https://github.com/rudybrian/MAX31760-Python | Baseline study (bugs B1–B5); local clone removed 2026-11-08 |
| https://docs.micropython.org/en/latest/library/machine.I2C.html | MicroPython transport API |
| https://pypi.org/project/smbus2/ , https://github.com/kplindegaard/smbus2 | CPython transport library |
| https://www.raspberrypi.com/documentation/computers/os.html#i2c-bus | RPi I²C enablement docs |
| https://beagleboard.org/ | BeagleBone I²C pins/bus reference |
| https://docs.micropython.org/en/latest/reference/pyboard.html#mpremote | mpremote serial tooling (candidate dev dep) |
| OpenAI Cookbook — Codex exec plans article | Planning-document format |

## 9. Repository Inventory

(Updated 2026-11-08 after the repo reorganization — see Build Log.)

```
FanSpeedController/
├── PLANS.md                     # Master build plan (read this first)
├── SUMMARY.md                   # This file (research/decisions/build log/handoff)
├── README.md                    # Root entry point (quick start, dev gates, layout)
├── pyproject.toml               # Packaging metadata (name=max31760, v0.1.0, MIT)
├── requirements.txt             # smbus2>=0.4.2 (Linux only)
├── .gitignore                   # pycache/egg-info/build artifacts (added 2026-11-08)
├── max31760/                    # THE DRIVER PACKAGE (shared core + mp/cp facades)
│   ├── __init__.py _core.py _tables.py _lut.py _faults.py
│   ├── _transport_mp.py _transport_cp.py
│   └── mp.py cp.py              # MicroPython / CPython entry points
├── tests/                       # Host-runnable unit/integration suite (134 tests)
│   ├── test_max31760.py         # Mock-backed unit + integration tests
│   ├── mock_i2c.py              # Behavioral mock chip
│   ├── fake_smbus.py            # Wire-level fake SMBus
│   └── lint_subset.py           # MicroPython-subset compliance gate
├── tools/                       # Dev quality gates & early probes
│   ├── api_coverage.py          # Public-API coverage gate
│   └── pico_probe.py pico_diag.py
├── examples/                    # Polished demos + canonical bench suites
│   ├── pico_demo.py esp32_demo.py rpi_demo.py
│   ├── hw_smoke_test.py         # Tri-platform smoke (board-aware pins)
│   └── e2e_hardware_test.py     # Tri-platform 12-section E2E matrix
├── scripts/                     # Hardware bench validation & diagnostics (2026-11-08)
│   ├── README.md                # Inventory + how-to-run per bench
│   ├── pico/                    # Pico W bench: e2e phase slices + deploy/RPM probes
│   ├── esp32/                   # ESP32 bench: connectivity probe
│   └── rpi/                     # RPi 3A+ bench: CPython I²C diagnostics
├── docs/README.md               # Full API reference / wiring / installation
├── NOTES/                       # Research notes 01–05
└── reference/                   # Datasheet PDF + upstream Adafruit driver (RESEARCH ONLY)
```

## 10. Resume Instructions (for any agent)

**Read order:** this file → `PLANS.md` (especially §2.1, §4, §5, §6) → skim `NOTES/01`
(register map & formats) → `NOTES/03` (MP constraints, header-corrected).

**Current position:** PLANS.md §6, **Phase B** (core device API) — starting at task B1.
Phase A (A1–A4) complete and hardware-verified 2026-11-07. See PLANS.md checkboxes for
live status.

**Hard rules:**
1. **Do NOT start coding until the user confirms** they've reviewed PLANS.md + SUMMARY.md
   and given the go-ahead (their standing instruction).
2. Follow PLANS.md §6 task order; each task ends green (tests pass) before the next starts.
3. Shared code (`_core.py`, `_transport_mp.py`, `mp.py`) must stay MicroPython-subset
   compatible: no type hints, no CPython-only imports, no f-string edge cases.
4. Transport contract: `burst_read(reg,n)`, `burst_write(reg,data)` (1–8 bytes),
   `probe()`. MP adapter uses `readfrom_mem`/`writeto_mem` ONLY (D10).
5. Page-safe writes: chunk ≤8-byte writes onto 8-byte page rows; reads may span pages.
6. Never modify `reference/`.
7. Keep the API identical across `max31760.mp` and `max31760.cp` (parity gate F26).
8. Iterate on the connected Pico (COM16) whenever a task touches transport/device I/O;
   remember the REPL lessons in §7.

**Immediate next actions after go-ahead:**
1. A1 — scaffold package layout per PLANS.md §5.2.
2. A2 — register/bitmask constants + factory-default table (verify vs NOTES/01).
3. A3 — transport layer + retry logic; acceptance includes a live `writeto_mem` round-trip
   to USER region (0x10h) on the Pico (also confirms `writeto_mem` existence).
4. A4 — fixed-point helpers (temp/duty/RPM encode-decode) + round-trip tests.

**Encoding details verified against parsed datasheet (2026-11-07, for A2):**
- Table 6 index source: MTI=0,TIS=0 → local; MTI=0,TIS=1 → remote (default); MTI=1 (TIS
  don't-care) → max(local,remote). Driver uses INDEX_MAX = MTI|TIS = 0x03.
- Table 11 ramp: 00=3.125 %/s (default), 01=6.25, 10=12.5, 11=immediate ⇒ RAMP_IMMEDIATE=0x30.
- Table 4 ideality: 64 entries 0x00=0.9844 … 0x3F=1.0489 (exact values captured in
  _core.IDEALITY_TABLE); 0x18=1.0080 (factory default); ≥0x40 invalid.
- EEX (reg 5Bh): bit7 L/W (1=load EEPROM→RAM, 0=save RAM→EEPROM); bits 4:0 = one bit per
  16-byte block (bit0=00h–0Fh … bit4=40h–4Fh); all-blocks mask 0x1F; save-all=0x1F,
  load-all=0x9F; EEX clears to 00h when read.
- Temp format re-confirmed (Tables 1/2): bit5=0.125 °C, bits 4:0 unused; +25→19h00h,
  −0.125→FFhE0h, +125→7Dh00h.

## 12. Build Log

### 2026-11-07 — Phase A complete (A1–A4)

Built:
- `max31760/` package: `__init__.py` (v0.1.0), `_core.py` (register map, bitmasks,
  factory defaults, 64-entry ideality table, fixed-point helpers, MAX31760 class with
  bounds-checked raw access, single-retry-on-OSError, page-safe chunked writes, RO-SR
  write guard), `_transport_mp.py` (readfrom_mem/writeto_mem), `_transport_cp.py`
  (smbus2/smbus lazy import, prepend-quirk strip, ≤32-byte read chunking, bus ownership
  semantics), `mp.py` / `cp.py` façades (subclass of shared core ⇒ parity by construction).
- `tests/`: `mock_i2c.py` (wire-level chip model: page-wrap emulation, SR clear-on-read,
  NACK injection, protocol-violation log), `fake_smbus.py` (prepend quirk + 32-byte limit),
  `test_max31760.py` (**32 tests, all green**), `lint_subset.py` (MicroPython-subset AST
  gate: bad imports / annotations / f-strings / async / walrus — PASS on all shared files).
- Packaging: `requirements.txt`, `pyproject.toml` (smbus2 dep Linux-markered), `README.md`.

Live hardware E2E (`e2e_phase_a.py` via mpremote on COM16):
```
probe: True
local=26.625C remote=27.750C
user0 orig=00 read_back=A5
user_bulk=B0B1B2B3B4B5B6B7
restored user0=00
PHASE-A TRANSPORT E2E: PASS
```
Confirms: `writeto_mem` exists & works on v1.19.1 RP2040; page-safe write path correct on
silicon; temps sane.

Operational notes learned this session:
- mpremote (1.29.0, installed via pip; NOT on PATH → invoke as `python -m mpremote`):
  options come AFTER the subcommand; connect syntax is `connect port:COM16`; chained
  commands do NOT split reliably → use ONE invocation per command:
  `python -m mpremote connect port:COM16 cp <src> :/<dst>` / `... run <script.py>`.
- smbus2/smbus are Linux-only ⇒ `_transport_cp.py` imports them lazily so the whole suite
  runs on the Windows dev host with injected fake handles.
- Python 3.14 host: ast-based lint must handle `posonlyargs` etc.; keep gates defensive.

Known open items carried into Phase B: EEPROM busy-window modeling in mock (C1 hardening);
TACH2 functional tests remain EXCLUDED-HW (no second fan).

### 2026-11-07 — Phase B started: B1 + B2 complete (host green + live E2E PASS)

Built:
- **B1 (F1):** `MAX31760.scan()` (sorted list of 7-bit addresses on bus) and
  `MAX31760.verify()` (self-test; raises OSError naming the address when absent,
  returns True on success). Transport contract extended with `scan()`: MP adapter uses
  native `i2c.scan()`; CP adapter probes candidates 0x03..0x77 via RO LTH read
  (smbus has no native scan; diagnostic-only ~114 txns).
- **B2 (F2,F3):** `local_temp_c` / `remote_temp_c` properties (fresh 2-byte burst read
  each access); setpoint get/set pairs `get/set_local_high`, `get/set_remote_high`,
  `get/set_local_overtemp`, `get/set_remote_overtemp` — all share the temperature
  encoding (datasheet Table 5 → Table 1 format), validated -128.0..+127.875 C.
  Each setter is one aligned 2-byte wire write (H/L pairs never cross page rows).
- Mock upgrade: `MockChip(addrs=(0x50,))` multi-address bus model + `require_ack()`;
  FakeSMBus passes real addresses through (CP-path scan/verify now testable).
- Tests: 32 → **46, all green** (+TestInitSelfTest, TestTemperatures incl. live-bench
  vector raw 1A80 = 26.5 °C, TestSetpoints incl. negative-encoding 0xF600 and
  wire-level single-write assertions). Lint gate docstring corrected: @property IS
  MicroPython-supported (gate implementation never banned it; API sketch promises it).

Live hardware E2E (`e2e_phase_b1b2.py` via mpremote on COM16):
```
verify: True
scan: 0x50
local=26.625C remote=27.875C
local_high: set 60.500 -> read 60.500
remote_high: set 90.000 -> read 90.000
local_overtemp: set 95.250 -> read 95.250
remote_overtemp: set 105.000 -> read 105.000
PHASE-B1B2 DEVICE E2E: PASS
```
All four setpoints also verified at factory defaults before mutation and restored
afterward (assertions in-script).

Operational notes learned this session:
- mpremote `cp <dir> :/` onto an EXISTING device dir fails (Permission denied), and
  `rm :/dir` on a non-empty dir fails (OSError 39) ⇒ ship package files INDIVIDUALLY:
  `python -m mpremote connect port:COM16 cp max31760/_core.py :/max31760/_core.py` etc.
  (Unchanged files report "Up to date" and are skipped.)

### 2026-11-07 — B3 complete + size-budget amendment (D15/D16)

Built:
- **B3 (F4,F5):** `lut_get()` / `lut_set(list48)` bulk access (six page-aligned wire
  writes, verified violation-free at mock level); `lut_get_index(i)` / `lut_set_index(i,duty)`
  single-entry access; pure utilities `lut_index_for_temp(c)` (window mapping, Table 7
  geometry: window 0 = <18 °C, 2 °C steps, ≥110 °C saturates at index 47) and
  `build_lut_curve(points)` (monotonic-breakpoint linear interpolation sampled at window
  midpoints 17+2i °C, clamped ends; ValueError on unsorted/duplicate points or pct∉0..100).
- **Size-budget amendment (user ruling):** ~16 KB/module is a SOFT target; decompose,
  never truncate functionality/docs. Executed immediately: pure data moved to
  `max31760/_tables.py` (FACTORY_DEFAULTS, IDEALITY_TABLE, factory LUT/USER values) and
  LUT geometry/curve builder to `max31760/_lut.py`. Result: `_core.py` 18.1 → **15.4 KB**
  (under budget again); dependency graph acyclic (`_tables ← _core ← _lut ← {mp,cp}`);
  both façades re-export `build_lut_curve`/`lut_index_for_temp` (parity preserved);
  lint gate extended to cover the two new shared modules.
- Tests: 46 → **56, all green** (+TestLutIndexForTemp vectors incl. boundaries,
  TestBuildLutCurve flat/ramp/monotonic/error cases, TestLutAccess bulk wire-level +
  single-entry isolation + bounds).

Live hardware E2E (`e2e_phase_b3.py` via mpremote on COM16):
```
factory LUT: 48 x FF
curve[5] (t~27C) = 173 (67.6%)
bulk round-trip: OK
single-entry: OK
restored factory LUT
PHASE-B3 DEVICE E2E: PASS
```
Confirms float math + curve builder run cleanly on-device (MicroPython v1.19.1 RP2040),
48-byte page-chunked writes correct on silicon, factory LUT state intact before/after.

### 2026-11-07 — B4 complete (manual/auto modes, duty, PWM config)

Built:
- **B4 (F6,F7,F8):** `manual_enable(on)`/`manual_enabled()` (CR2.DFC); `set_duty_pct(pct)` /
  `set_duty_raw(raw)` (PWMR) / `get_duty_cmd_raw()`; `get_actual_duty_raw()` /
  `get_actual_duty_pct()` (PWMV, RO); `set/get_index_source` (INDEX_LOCAL/REMOTE/MAX;
  reserved encoding 0x02 rejected); `set/get_hysteresis_c` (2 or 4 only);
  `set/get_pwm_freq_hz` (33/150/1500/25000 Hz); `set/get_pwm_polarity`
  (POLARITY_POSITIVE/NEGATIVE). All CR1/CR2 mutations go through read-modify-write helpers
  that preserve unrelated bits. Public constants (INDEX_*, RAMP_*, PWM_FREQ_*, POLARITY_*)
  exposed as class attributes so `MAX31760.INDEX_MAX` works per the API sketch.
- **Latent Phase-A bug caught & fixed:** CR1 DRV bit values were off by one position
  (were 0x04/0x08/0x0C; datasheet reg 00h places DRV on bits **[4:3]** ⇒ 0x00/0x08/0x10/0x18).
  Mask 0x18 was already correct; only the individual values were wrong. Caught by new unit
  tests BEFORE any hardware exposure; regression test `test_drv_bit_positions` added.
- Tests: 56 → **72, all green** (+TestManualMode, TestAutoConfig, TestPwmConfig,
  +DRV regression pin).

Live hardware E2E (`e2e_phase_b4.py` via mpremote on COM16):
```
baseline CR1=01 CR2=10 CR3=03
prep: TACH2 disabled, fan-fail cleared
auto-mode PWMV start=255
manual 50%: cmd=128 actual=128 (was 255)
index_source: OK
hysteresis: OK
pwm_freq: OK
polarity: OK
restored factory control registers
PHASE-B4 DEVICE E2E: PASS
```
Observable effect verified: actual output duty (PWMV) slewed 255→128 when 50 % commanded
in manual mode (fan slowed audibly).

**Protocol finding (important for presets/docs):** on the single-fan bench, the first B4
run FAILED (PWMV stuck at 255 despite DFC+PWMR=128). Root cause: factory-default TACH2E=1
with no fan on port 2 ⇒ persistent TACH2A ⇒ fan-fail latches after 3 consecutive
detections ⇒ chip forces PWM output to FFDC (0xFF = 100 %) immediately, overriding manual
duty. Fix in-script: disable TACH2E + write CLRFAIL before duty tests. Consequences:
1. D11 promoted to MANDATORY: every single-fan preset/config must clear TACH2E (+CLRFAIL).
2. The E2E script is now idempotent (forces factory CR1/CR2/CR3 at start) so an interrupted
   run cannot wedge subsequent runs; `e2e_restore.py` kept as emergency restore tool.

### 2026-11-07 — B5 complete (ramp rate + wait_for_duty)

Built:
- **B5 (F9):** `set_ramp_rate(rate)` / `get_ramp_rate()` (RAMP_SLOW/MED_SLOW/MED_FAST/
  IMMEDIATE on CR3 bits [5:4], RMW-preserving, unknown rates rejected);
  `wait_for_duty(target_pct, timeout_ms=2000)` — polls PWMV every 10 ms via the transport's
  delay hook, returns True when the quantized target is reached, raises TimeoutError on
  overrun (error model consistent with EEPROM-busy); ValueError on negative timeout or bad pct.
- Tests: 72 → **77, all green** (+TestRampRate: round-trips preserving TACH bits,
  rejection, immediate-hit, timeout-with-polling-evidence, bad args).

Live hardware E2E (`e2e_phase_b5.py` via mpremote on COM16):
```
ramp_rate round-trips: OK
immediate: settled at 25% in 1 ms
slow ramp: after 1 s actual=68 (between 64 and 192)
switched to immediate: finished at 75% in 1 ms
restored factory CR3
PHASE-B5 DEVICE E2E: PASS
```
Quantitative confirmation: from 25 % under RAMP_SLOW, after exactly 1 s the output sat at
68/255 = 26.6 % — i.e. ~3.1 percentage points of slew, matching the datasheet 3.125 %/s
specification on silicon. Immediate-ramp settle measured at 1 ms (single poll).

### 2026-11-07 — B6 complete (tach enable, RPM reads, threshold)

Built:
- **B6 (F11,F12):** `tach1_enable/tach1_enabled`, `tach2_enable/tach2_enabled` (CR3 RMW);
  `rpm(port, pulses_per_rev=2)` — single aligned 2-byte read of the RO TC pair,
  `RPM = 6,000,000 / (count × ppr)`, returns 0.0 on count=0 (fixes upstream bug B4
  div-by-zero); a very slow fan whose count overflows surfaces as the TACHxA alarm bit
  (datasheet), never a bogus number; `set_tach_threshold(count)` / `get_tach_threshold()`
  — proper 16-bit big-endian TCTH:TCTL write (fixes upstream bug B3 single un-clamped byte),
  ValueError outside 0..65535.
- Tests: 77 → **84, all green** (+TestTachometer: enable round-trips preserving other CR3
  bits, RPM math both ports + ppr scaling, zero-count guard, port isolation, threshold
  round-trip incl. wire-byte split, range rejection).

Live hardware E2E (`e2e_phase_b6.py` via mpremote on COM16):
```
port1 rpm(ppr=2)=2322.0
port1 rpm(ppr=4)=1161.0 (half of ppr=2 as expected)
tach1 toggle: OK
SR before=02 after=02 (TACH2A=bit1)
tach2 alarm: OK
threshold round-trip: OK (factory 65534 restored)
restored factory CR3
PHASE-B6 DEVICE E2E: PASS
```
The bench fan measures ~2322 RPM live; ppr scaling is exactly inverse as the formula
predicts. Functional RPM-on-port-2 remains EXCLUDED-HW (no second fan), but the TACH2
alarm path IS exercised: with no fan present, TC2 saturates at 0xFFFF (> threshold 0xFFFE)
and TACH2A latches in SR.

Findings & lessons:
1. **SR address mix-up caught:** an early draft of the E2E read 0x04 believing it was SR;
   0x04 is the ALERT MASK register (factory C0h — hence the confusing "SR=C0" readings).
   Real SR = **0x5A**, EEX = 0x5B (register map, datasheet p.20). Core constants were
   already correct; only the ad-hoc script was wrong. Scripts now import REG_SR.
2. **Fan-fail re-arm latency MEASURED ≈ 8 s** after CLRFAIL + TACH2 re-enable
   (`e2e_diag_latency.py`: TC2=FFFF throughout, TACH2A latched at t≈8027 ms). Datasheet
   guarantees only a 2 s startup grace + "three consecutive detections"; the observed
   cadence implies fault sampling well slower than the PWM period. Any test/preset that
   clears fan-fail must budget ≥ ~10 s before expecting the alarm to re-latch.
3. Diagnostic artifacts kept: `e2e_diag.py` (state dump), `e2e_diag_latency.py`
   (re-arm latency probe).

### 2026-11-07 — B7 complete (fault handling, status, FFDC, modes, alert mask)

Built:
- **B7 (F13,F14,F16,F17):** `status_raw()` (SR @ 0x5A; clear-on-read loudly
documented), SR_* flag constants (TACH1A/TACH2A/ROTA/RHA/LOTA/LHA/RDFA/PC +
SR_ALARM_MASK), `remote_diode_fault()`, `clear_fan_fail()` (CR3.CLRFAIL),
`set_ffdc_raw/set_ffdc_pct/get_ffdc_raw` (FFDC 0x03),
`set_ff_zero_detection/ff_zero_detection` (CR3.FF_0), `set_ff_mode/get_ff_mode`
(FF_MODE_INTERRUPT latched vs FF_MODE_COMPARATOR live), `set_rd_mode/
rd_mode_enabled` (CR2.FSST RD/locked-rotor input select), `set_rd_polarity/
get_rd_polarity` (CR2.RDPS), `set_alert_mask/get_alert_mask` (MASK 0x04: six
alarm bits RMW'd one-to-one with SR positions, reserved upper bits preserved,
RDFA has no mask bit so 0x40+ rejected).
- Tests: 84 → **94, all green** (+TestFaultHandling: clear-on-read semantics,
flag-position pins, CLRFAIL preservation, FFDC round-trip/validation, FF_0,
FF mode, RD mode+polarity exact-byte restore, alert-mask reserved-bit
preservation + range rejection).
- **Decomposition:** fault domain extracted from `_core.py` into new
  `max31760/_faults.py` (`FaultMixin` mixed into MAX31760). Ordering-safe
circular import (constants defined before the mixin import line) documented
in `_core.py`; lint gate extended to cover `_faults.py`. Sizes after split:
_core 26.1 KB, _faults 5.2 KB.

Live hardware E2E (`e2e_phase_b7.py` via mpremote on COM16):
```
status_raw=02 (TACH2A expected from boot)
status + remote diode check: OK
PWMV with FFDC=FF: 255
PWMV with FFDC=50%: 128
ffdc force path: OK (output followed FFDC 255->128->255)
TACH2A re-armed after 7508 ms
clear_fan_fail + re-arm: OK
ff_zero: OK
ff_mode: OK
rd_mode+polarity: OK
alert_mask: OK
restored factory CR3
PHASE-B7 DEVICE E2E: PASS
```
Findings:
1. **FFDC force path proven on silicon:** with the persistent TACH2 fan-fail
   active (no port-2 fan) and LUT still commanding 100 %, lowering FFDC dragged
   the ACTUAL output (PWMV) 255→128 immediately, and restoring FFDC brought it
   back to 255 — the fan-fail override is real and independent of LUT/manual duty.
2. Re-arm latency via the public API measured at 7.5 s, consistent with the
   ~8 s figure from B6's diagnostic probe.
3. The `_faults.py` mixin + circular-import wiring verified working on
   MicroPython v1.19.1 (device imported and ran the full suite cleanly).

### 2026-11-07 — B8 complete (3-wire assists: PSEN/TACHFULL + spin-up)

Built:
- **B8 (F10,F15):** `spin_up_enable/spin_up_enabled` (CR2.SPEN),
  `pulse_stretch_enable/pulse_stretch_enabled` (CR3.PSEN),
  `tacho_full_enable/tacho_full_enabled` (CR3.TACHFULL), and
  `measure_tach_once(port=1, timeout_ms=3000)` — one-shot PSEN sequence
  (set PSEN, poll TC until change or timeout, clear PSEN in `finally`; enforces
  33 Hz PWM + TACHFULL-off preconditions with ValueError).
- Tests: 94 → **100, all green** (+TestThreeWireAssist: CR2/CR3 bit
  preservation, one-shot return/cleanup, port-2 routing, precondition
  rejection).

Live hardware E2E (`e2e_phase_b8.py` via mpremote on COM16):
```
baseline: manual 0%, PWMV=0
spin-up: saw 100%=True, settled at 2171 ms
spin-up: OK (held 100% ~2.2 s, then reverted to 50%)
measure_tach_once: 077C, rpm=1565.8
psen one-shot contract: OK
psen precondition (150 Hz rejected): OK
TC1 under TACHFULL @50%: 077C -> 077C
TC1 after TACHFULL off + accel: 0579 (was 077C)
tachfull functional: OK
restored factory CR3
PHASE-B8 DEVICE E2E: PASS
```
Findings:
1. **Spin-up proven on silicon:** with TACH2 enabled (dead port 2 makes the
   "2 pulses at each enabled input" end-condition unreachable), a 0→50 % duty
   change under SPEN held the output at 100 % for 2.17 s (the 2 s timeout) and
   then reverted to the selected 50 % duty — exactly per datasheet.
2. **TACHFULL proven functionally:** below 100 % duty it suspends TACH
   measurement entirely (TC1 frozen at 0x077C across 1 s); clearing it and
   accelerating the fan resumed updates (0x0579). Cross-consistency: TC1=0x077C
   ⇒ rpm() = 1565.8 RPM matches the live reading exactly.
3. **PSEN waveform is not observable via I²C:** PWMV holds the commanded duty
   during stretching (probed with `e2e_probe_psen.py`: flat 13 over 3 s with
   PSEN on at 5 %). And contrary to expectation, TC1 still updates at 5 % duty /
   33 Hz on this silicon (0x05B4→0x0826 while coasting), so "low duty freezes
   TC" is NOT a valid test precondition here. PSEN therefore gets a contract
   check (valid return, cleanup, real-HW ValueError at 150 Hz) plus mock unit
   tests; the stretch mechanism itself rests on the datasheet + unit tests.

### 2026-11-07 — B9 complete (ALERT service routine + ideality factor)

Built:
- **B9 (F18,F19):** `set/get_alert_mode` (ALERT_MODE_INTERRUPT latched /
  ALERT_MODE_FAULT_INDICATOR live, CR2.ALERTS), `service_alert()` (datasheet
  step 2 — SR read; documents that the device then holds ALTMSK=1),
  `alert_masked()` / `clear_alert_mask()` (CR1.ALTMSK, steps 3/5);
  `set_ideality_factor_index(idx)` (IFR bits [5:0], reserved upper bits
  preserved, 0..63 validated), `get_ideality_factor_index()`,
  `get_ideality_factor()` (table lookup), `set_ideality_factor(n)` nearest-
  match with range rejection (0.9844..1.0489) and lower-index tie-break;
  IDEALITY_TABLE exposed as class attribute.
- Tests: 100 → **106, all green** (+TestAlertAndIdeality: mode round-trip,
  service-alert clear-on-read, ALTMSK get/clear preserving other CR1 bits,
  index round-trip/validation, nearest-match incl. midpoint tie, range
  rejection).

Live hardware E2E (`e2e_phase_b9.py` via mpremote on COM16):
```
factory IFR idx=24 (n=1.0080), remote=27.625 C
IFR idx=0 (n=0.9844), remote=29.625 C
ideality factor: OK (shift +2.000 C, restored)
alert mode: OK
LHS=70.0 C, local die=25.9 C
service_alert SR=22 (LHA=bit5 expected)
ALTMSK latched by silicon: OK
alert isr sequence: OK (steps 2/4/5 walked on real silicon)
final SR=02 clean
PHASE-B9 DEVICE E2E: PASS
```
Findings:
1. **Full ALERT interrupt-service sequence executed on real silicon:** lowering
   LHS below ambient forced the LHA latch; `service_alert()` returned SR=0x22
   (LHA | TACH2A — the dead port-2 alarm was also latched, correctly ignored by
   the assertion); **the silicon itself set ALTMSK after the SR read**
   (`alert_masked()` True without any driver write) — the datasheet's step-3
   device behaviour verified, not emulated; attending (raising LHS back to 70 °C)
   and `clear_alert_mask()` completed the sequence; final SR clean.
2. **Ideality factor proven observably:** IFR 0x18→0x00 shifted the remote
   diode reading +2.0 °C immediately (direction and magnitude consistent with
   the n-scaling of the junction math); restoring the factory index brought the
   reading back within tolerance.
3. **MEASURED: slow settle around IFR changes** — the bench diode reading takes
   ~4 s to settle after an IFR change (probe `e2e_probe_ifr.py`: monotonic
   approach in both directions). Attributed to fixture thermal/electrical
   coupling, not the chip; the E2E polls up to 6 s for the restore.

### 2026-11-07 — B10 complete (EEPROM lifecycle + soft POR/standby/user memory)

Built:
- **B10 (F20,F21):** `save_config(blocks=EEX_ALL_BLOCKS, timeout_ms=2000)` /
  `load_config(...)` — EEX L/W + block-select bits (`EEX_BLOCK_00_0F` ..
  `EEX_BLOCK_40_4F`, `EEX_ALL_BLOCKS`); ack-polls `transport.probe()` every
  10 ms until the device acknowledges again, `TimeoutError` on overrun;
  `eeprom_corrupt()` (SR.PC — persists across SR reads, clears only after a
  successful write + POR); `recover_from_corruption(timeout_ms)` (rewrite all
  blocks → soft POR → verify PC cleared);
  `soft_por(settle_ms=100)` (CR1.SW_POR self-clearing + bus-settle wait);
  `enter_standby()/exit_standby()/standby_active()` (CR2.STBY);
  `user_memory_get/set/read_all/write_all` (10h..17h).
- Transport MP `probe()` switched from a full-bus scan to a single RO-register
  transaction (OSError on NACK = exact ack-poll semantics; a scan per poll
  would be far too slow at 10 ms cadence).
- Mock fidelity upgrades: PC now persists across SR reads (only alarm bits
  [6:0] clear); EEX writes open a tW NACK window during which `probe()` fails,
  then apply the deferred RAM↔EEPROM copy for the selected block ranges;
  CR1.SW_POR reloads RAM from EEPROM and clears latches.
- Tests: 106 → **117, all green** (+TestEepromLifecycle: save/load with block
  scoping, invalid-mask rejection, busy-timeout, POR reset+reload, standby
  round-trip, user-memory single/bulk + validation, PC persistence, full
  corruption-recovery flow).

Live hardware E2E (`e2e_phase_b10.py` via mpremote on COM16) — REAL EEPROM
program cycles on the bench chip:
```
snapshot taken (CR1=01)
user memory: OK
save_config: 279 ms (tW window ack-polled)
post-POR: CR1=09 (pre-save 01), LUT[0]=80, user[0]=A5
eeprom save + POR persistence: OK
load_config: CR1=01 (back to snapshot 01)
load_config overwrite: OK
standby: OK (I2C responsive while in standby)
final POR: configuration matches pre-test snapshot
PHASE-B10 DEVICE E2E: PASS
```
Findings:
1. **Full nonvolatile chain proven on silicon:** RAM mutation (CR1.DRV→150 Hz,
   LUT[0]→80h, user mem pattern) → `save_config()` (ack-polled, 279 ms live tW
   window) → `soft_por()` → all three values survived the full device reset —
   RAM→EEPROM→POR→RAM verified end-to-end.
2. **load_config observable:** after re-diverging RAM (DRV→25 kHz), loading the
   control block pulled CR1 back to the saved value (0x01) — EEPROM→RAM
   overwrite confirmed.
3. **Standby safe to use:** I²C stayed fully responsive while STBY was set
   (per datasheet, the interface remains active); exit restored normal mode.
4. Final soft POR verified the entire 80-byte nonvolatile configuration equals
   the pre-test snapshot byte-for-byte; SR.PC clean throughout (no corruption
   events).

### 2026-11-07 — B11 complete (presets; raw access/error model already in place)

Built:
- **B11 (F24):** presets on top of the existing Phase-A raw access (F22) and
  error model (F23): `configure_4wire_fan(port=1, pwm_freq_hz=PWM_FREQ_25KHZ)`
  (datasheet Fig. 2a), `configure_3wire_supply_modulation(port=1)` (Fig. 2b:
  33 Hz + PSEN pulse-stretch assist), `configure_two_fans()` (both tachometers
  armed). All apply the mandatory single-fan hygiene (D11: unused port
  disabled + CLRFAIL) via a shared `_single_port_hygiene(port)` helper and are
  MODE-NEUTRAL: they deliberately do not touch CR2.DFC, with docstrings telling
  users to call manual_enable(True) if they intend set_duty_pct() control.
- Tests: 122 → **122 green** (+TestPresets: per-preset register effects for
  both ports, invalid-port rejection, DFC left untouched, protocol-clean
  writes).

Live hardware E2E (`e2e_phase_b11.py` via mpremote on COM16):
```
factory CR1=19 CR2=11 CR3=31
4wire preset: CR1=19 CR3=31
4wire @50%: PWMV=128, rpm=1277.7 (after 1 x 200 ms settle)
4wire @100%: rpm=2250.6 (was 1277.7 at 50%)
configure_4wire_fan: OK
3wire preset: CR1=01 CR3=35
3wire one-shot: TC=0528, rpm=2272.7
configure_3wire_supply_modulation: OK
twofans preset: CR3=33
two-fans: SR=02 after 16 x 500 ms (TACH2A expected)
configure_two_fans: OK (port-2 fault detector armed)
restored factory CR1/CR2/CR3
PHASE-B11 DEVICE E2E: PASS
```
Findings:
1. **KEY DISCOVERY — factory default is LUT mode:** CR2.DFC (bit 0) selects
   direct/manual fan control; factory CR2=0x10 has DFC=0, so the output follows
   the temperature-indexed LUT, NOT the PWMR manual duty. With the factory
   all-FF LUT the output sits at 100 %. Earlier phases ran implicitly in
   manual mode because an ad-hoc script had set DFC=1; the B10 soft-PORs
   silently reverted the bench to LUT mode, which initially masqueraded as a
   "stuck fan-fail force" (PWMV=255 with SR=00, FFDC=FF). Diagnosis path:
   probe CR2/PWMR/PWMV/LUT (`e2e_probe_state.py`) -> DFC=0 + LUT[ambient]=FF
   explained everything. The driver already exposed manual_enable()/manual_
   enabled() (F6); presets now document the interaction explicitly.
2. **Duty->speed causality proven at 25 kHz:** 50 % duty gave 1277.7 RPM,
   100 % gave 2250.6 RPM (1.76x) — the 4-wire preset genuinely drives the
   physical fan through its PWM input.
3. **Factory ramp rate is slow:** with the factory RAMP bits, 255->128 took
   ~15 s; the E2E forces RAMP_IMMEDIATE as test setup (restored via the final
   CR3 write). Users scripting fast transitions should know this.
4. Two-fans preset arming verified functionally: with TACH2 enabled on the
   dead port, TACH2A latched after 8 s (16 x 500 ms polls) — the fault
   detector is genuinely armed by the preset.
5. Bench left in true factory state (CR2 reset to 0x10 after the run; a failed
   earlier attempt had left DFC=1 behind).

### 2026-11-07 — B12 complete (CPython transport integration tests)

Built:
- **B12 (F25):** `TestCPIntegration` — full driver stack (cp facade +
  TransportCP + core) exercised over an injected FakeSMBus handle across every
  API domain: raw access/verify/scan, manual mode + duty + ramp +
  wait_for_duty, LUT get/set, temperature setpoints, tach enable/threshold,
  fault domain (status_raw/FFDC/alert mask), 3-wire assists (spin-up/PSEN/
  TACHFULL), alert mode + ideality factor, EEPROM save/load through the
  chunked CP read/write path, soft POR reload-from-EEPROM, standby enter/exit,
  user memory, presets, and close semantics on a borrowed handle.
- **Fake fixture upgrade (important):** FakeSMBus now models the EEPROM tW
  window at wire level — while MockChip.busy_polls > 0 EVERY transaction
  (read or write) raises OSError(NACK) and each attempt consumes one poll,
  mirroring MockChip.probe_ok. Previously only probe_ok knew about the busy
  window, so TransportCP.probe() (implemented as a real RO-register read)
  always succeeded and _wait_eeprom_ready exited immediately, leaving EEX
  copies unapplied on the CP path. The MP path was unaffected because its
  mock transport routes probe() straight to probe_ok.
- Suite: 122 -> **123, all GREEN**; lint PASS.

Scope note: live verification of the cp facade on a Raspberry Pi (full Python,
real smbus2) is deferred to the user-driven cross-platform phase — this bench
is MicroPython-only with no i2c-dev/smbus available.

### 2026-11-07 — Phase C progress (C1–C9 done; C10 pending)

Quality gates & delivery artifacts landed today:

- **C1 (mock hardening):** closed — page-wrap violation tracking, EEPROM tW
  window (now enforced at wire level in BOTH fixtures), SR clear-on-read incl.
  PC persistence, NACK injection all present. 3-strike fault queue deliberately
  not emulated (driver treats SR as an opaque latch; ~8 s re-arm measured on
  bench instead).
- **C2 (suite completeness):** **127 tests green**; new automated coverage gate
  `tools/api_coverage.py` proves all 123 public members are exercised (caught
  3 untested EEX block-select constants → now covered).
- **C3 (static sanity):** compileall PASS; MicroPython-subset lint gate PASS;
  AST parse of MP files PASS.
- **C4 (docs):** `docs/README.md` written — wiring tables, per-platform install
  (incl. I²C enablement for RPi all models / BeagleBone DT overlays / generic
  SBC), quick starts, full API reference (11 domains, 90 methods + 31
  constants), error-model table, measured operational notes, ALERT ISR example.
  Doc corrections made while writing: LUT window geometry is Table-7 style
  (window 0 < 18 °C, 2 °C windows, ≥110 °C saturates) — NOT index==°C;
  build_lut_curve takes (temp_c, pct) breakpoints evaluated at window
  midpoints; hysteresis is a 2-or-4 °C field.
- **C5 (examples):** pico_demo.py, esp32_demo.py (ESP8266 out of scope noted),
  rpi_demo.py, hw_smoke_test.py. Smoke test RUN LIVE: temps 26.4/27.9 °C, duty
  sweep exact (0/64/128/192/255), rpm 2298.9 @100 %, EEPROM round trip + POR
  survival with discriminating sentinel (XOR-flipped CR1 bit), RAM+EEPROM left
  pre-test state. PASS.
- **C6 (E2E hardware matrix):** `examples/e2e_hardware_test.py` — 12-section
  self-restoring matrix over every public API domain. LIVE RUN: **12/12 PASS**
  (~1.2 s total). Iteration findings: hysteresis 2/4 °C constraint; LUT helpers
  are module-level exports; build_lut_curve endpoint breakpoints must sit at
  window midpoints (17/111 °C) for exact endpoints. Results table committed to
  PLANS.md §7.
- **C7 (packaging):** pyproject.toml + requirements.txt verified via fresh-venv
  `pip install .` + import of both facades (smbus2 correctly skipped on Windows
  via platform marker). Full Linux-venv check deferred with cross-platform phase.
- **C8 (SBC docs/examples):** rpi_demo.py + expanded per-family I²C enablement
  docs (see C4).
- **C9 (parity gate, F26):** TestApiParity added — shared-core MRO identity,
  __all__ match, full surface diff (names/signatures/constants/properties).
  Immediately caught a real asymmetry: close() existed only on the cp facade →
  fixed with a documented no-op close() on mp.py. Suite now 127 green.

### 2026-11-07 — C10 final review & v0.1.0 freeze (Phase C COMPLETE)

Row-by-row audit of F1–F27 against the implemented API + test suite found ONE
gap: **F16's "compact active-alarm bitmask" was never implemented** (the risk
table had promised `active_alarms()`). Fixed in the same pass:

- `max31760/_faults.py`: new `active_alarms()` — reads SR, returns
  `SR & SR_ALARM_MASK` (six alarm bits, PC excluded); docstring warns it
  consumes the latch like `status_raw()` (call one or the other per service
cycle).
- Unit test `test_active_alarms_compact_bitmask`: asserts masking, and that a
  second read sees only PC persisting (matches real silicon + mock semantics).
- Live matrix: fault section now asserts `active_alarms() == 0` after
  CLRFAIL; re-deployed `_faults.py` + matrix to the Pico → **12/12 PASS**.
- Docs: §5.6 row added; PLANS.md §7 results table updated.

Final gate state at freeze: **128 unit tests green · coverage gate PASS (124
public members) · MicroPython-subset lint PASS · compileall PASS · parity
gate green · E2E hardware matrix 12/12 PASS.** Known deferrals (user-driven):
Linux-venv pip verification, RPi full-Python live run, ESP32-S3 live run,
port-2/TACH2 functional bench testing (EXCLUDED-HW), oscilloscope proof of
PSEN pulse stretching.

### 2026-11-08 — Deployment location fix (/lib) + ESP32 cross-platform phase start

User correction: third-party MicroPython packages belong in **`/lib`** (always on
`sys.path`; mip auto-detects it), not the filesystem root. Actions taken:

- **Pico redeploy:** `os.rename('/max31760', '/lib/max31760')` via device exec
  (`mpremote fs mv` does not move directories); verified import from `/lib`
  (`max31760.__version__ == 0.1.0`, 125 public members).
- **Latent deploy bug found & fixed:** the original root deploy had left
  `:/max31760/__init__.py` as a DIRECTORY containing the init file, so the
  package imported as a bare directory and `__init__` never executed. Renamed
  the junk aside, deployed the real `__init__.py` file, removed the junk tree.
- **Docs:** README §2 MicroPython install now targets `:/lib/max31760/` with a
  post-deploy verification one-liner; decision logged as D26 (D17–D25 also
  back-filled into this decisions log — they existed only in handoff briefs).
- **ESP32 bench brought online (COM7):** MicroPython v1.29.0; MAX31760 moved
  physically to this MCU by user (SDA=GPIO41, SCL=GPIO42). Standalone probe
  (`esp32_probe.py`, pure machine.I2C): bus scan finds exactly 0x50, CR1=0x19
  (factory), local 24.8 °C / remote 25.9 °C sane, PWMV=255 (factory LUT-mode
  100 % state). **Connectivity confirmed.** Pico bench consequently NACKs at
  0x50 (chip no longer connected there) — expected.

Next: deploy driver to ESP32 `/lib` and run the full E2E hardware matrix on
the new MCU (awaiting user go-ahead).

### 2026-11-08 — ESP32 cross-platform validation: FULL PASS

Executed the go-ahead: deployed + validated the complete driver stack on the
ESP32 bench (COM7, MicroPython v1.29.0, I2C0 SDA=GPIO41/SCL=GPIO42).

- **Board-aware test scripts:** `examples/hw_smoke_test.py` and
  `examples/e2e_hardware_test.py` now auto-select pins via `sys.platform`
  (`rp2` → GP0/GP1, `esp32` → GPIO41/42) — single source of truth, no
  per-board forks.
- **Deploy:** package → `:/lib/max31760/` (D26). Finding: this ESP32 image
  shipped WITHOUT `/lib`; `fs mkdir :/lib/max31760` failed until `/lib` was
  created first (device-side `os.mkdir`). Docs §2 updated with the caveat.
- **API-surface diff between boards:** initially 125 (Pico) vs 126 (ESP32)
  public members — traced to a STALE pre-D24 `mp.py` on the Pico (missing
  `close()`); all other files were "Up to date". Resynced; both boards now
  report 126 members incl. `close`. Lesson: the version one-liner check does
  not catch per-file staleness — member-count diff is the stronger gate.
- **Smoke test (ESP32): PASS** — temps 24.9/26.0 °C; exact duty sweep
  0/64/128/192/255; rpm @100 % = 2284.8 (Pico bench: 2298.9 — same fan,
  within noise); EEPROM round trip + soft-POR survival OK; registers restored.
- **E2E hardware matrix (ESP32): 12/12 PASS** (~1.5 s total), identical
  section set to the Pico run; self-restoring (RAM verified byte-for-byte +
  EEPROM re-saved). Results table committed to PLANS.md §7.

Cross-platform status: **ESP32 leg COMPLETE** (second MicroPython port,
v1.29.0, different pin mapping — transport baseline confirmed portable).
RPi full-Python (smbus2) leg remains outstanding.

### 2026-11-08 — Pico reflash + re-validation: PASS

User reflashed the Pico and moved the MAX31760 back to this bench. Probed
with `pico_reflash_probe.py` (kept in repo root with the other diagnostics):

- Firmware now **v1.29.0** (was v1.19.1) — same image generation as the
  ESP32 bench; `sys.platform == "rp2"` unchanged.
- Flash filesystem SURVIVED the reflash: all prior scripts at root and
  `/lib/max31760/` intact (import OK, version 0.1.0, 126 members incl.
  `close()`). No redeploy needed; board-aware test scripts refreshed from
  the current sources anyway.
- Bus scan: exactly one device at 0x50.
- Smoke test: **PASS** (temps 25.3/26.1 °C; exact duty sweep; rpm @100 % =
  2316.6; EEPROM round trip + POR survival; registers restored).
- E2E hardware matrix: **12/12 PASS** (~1.3 s), self-restoring.

Driver now validated on: RP2040 @ v1.19.1 (original build), RP2040 @ v1.29.0
(post-reflash), ESP32 @ v1.29.0. Transport baseline (`readfrom_mem`/
`writeto_mem`) confirmed stable across firmware generations.

**Board-ID correction (user, 2026-11-08):** the bench board is a first-edition
**Pico W (RP2040)**, not a Pico 2 W (RP2350) as previously assumed — noticed
while reflashing. All "RP2350" references above corrected to RP2040. Pico 2 W
(RP2350) expected to work (same `rp2` port family) but UNTESTED — user does
not have that board. Logged as D27.

### 2026-11-08 — RPi CPython leg: root cause found, fixed, FULL PASS

The RPi 3A+ leg (local RPi over SSH; Debian 13, Python 3.13.5, smbus2,
i2c-bcm2835 bus 1) was blocked for five successive fix iterations by
`soft_por()` failing with `OSError [Errno 121]` after `load_config`. This
session closed it out.

**Investigation arc (diagnostic scripts kept in repo root):**

1. `rpi_tw_timeline.py` — raw NACK/ACK timelines after EEX ops: SAVE shows a
   clean ~53 ms NACK window; LOAD shows no sustained window at 1 ms cadence.
2. `rpi_tx_log.py` — driver-level transaction trace: the NACKed writes were
   ALWAYS the SW_POR-bearing write (0x5D); same-value/no-POR writes succeeded
   in the SAME MILLISECOND as the NACKs ⇒ killed the time-window theory.
3. `rpi_nack_topology.py`, `rpi_interference_test.py`,
   `rpi_traffic_vs_silence.py` — controlled experiments: baseline hammering
   never NACKs; post-EEX windows are variable and hard to reproduce in
   isolation.
4. `rpi_bruteforce.py` / `rpi_bruteforce_raw.py` — the exact smoke sequence
   through the driver AND through raw smbus2: **0/10 pass**, deterministic.
5. `rpi_swpor_semantics.py` + `rpi_boot_time.py` — DECISIVE: a volatile
   marker in user memory (0xA5) is GONE after a "failed" SW_POR write
   (reloaded from EEPROM), 5/5 runs ⇒ **the POR executes despite errno 121**.
   The chip resets so fast that bcm2835 reports the in-flight transaction as
   failed. Every retry of the SW_POR write re-fired another POR into a
   still-booting chip — the cascading NACKs had masqueraded as an "EEPROM
   busy window" all along (variable 6 ms–1.5 s = boot-time variance).

**Fix (D33, in `_core.py`):** `soft_por()` now reads CR1, issues the SW_POR
write exactly once via the RAW transport (`self._t.burst_write`, bypassing
the `_tx` retry ladder), swallows its OSError (expected), polls `probe()`
until the device re-acknowledges (settle default raised 100 → 1000 ms),
raises only if the device never returns, then waits out the POR-triggered
EEPROM-reload commit window via `_wait_eeprom_ready` (fixed 700 ms pure
delay, D32). Also this session: `_wait_eeprom_ready` rewritten as a pure
delay (probes/oracles interact badly with the silicon during commit);
mock fixtures updated to match verified silicon semantics (EEX copy applied
at write-end; data transactions stay live during tW; post-POR boot
unresponsiveness modeled via `boot_polls`).

**Validation on the RPi:**

- Smoke test: **PASS** (temps 26.2/27.4 °C; exact duty sweep 0/64/128/192/255;
  rpm @100 % = 709.9; EEPROM round trip + post-POR CR1 survival OK;
  registers restored).
- E2E hardware matrix: **12/12 PASS** (section 9 eeprom/por/standby/recovery
  3519 ms — slower than MicroPython benches due to the full tW waits).
- Reliability: brute-force save/load/POR sequence ×10 through the driver:
  **10/10 PASS** (was 0/10 pre-fix).
- Host suite: **134 tests GREEN** (+1 new regression test pinning the
  single-attempt/swallow/settle contract), lint PASS, coverage gate PASS
  (124 public members referenced).

**Cross-platform phase COMPLETE.** Note: the Pico's deployed `_core.py`
predates D31–D33 and must be redeployed when the Pico is reconnected (the
new `soft_por` semantics benefit the MicroPython path too — it now survives
mid-transaction reset errors there as well).

### 2026-11-08 — Pico redeploy of the D33 core: PASS

User moved the Click from the RPi back to the Pico bench. Executed the
pending redeploy:

- Deployed the fixed `_core.py` to `:/lib/max31760/_core.py` via mpremote
  (44033 bytes on-device = local size; only package file changed since the
  previous Pico deploy) + refreshed both board-aware test scripts.
- Post-deploy sanity (`pico_deploy_check.py`, kept in repo root): version
  0.1.0, 126 public members, chip verifies at 0x50, temps read.
- Smoke test: **PASS** (temps 26.5/27.5 °C; exact duty sweep 0/64/128/192/255;
  EEPROM round trip + post-POR CR1 survival OK; registers restored).
- E2E hardware matrix: **12/12 PASS**, self-restoring. Section 9 took 3532 ms
  — essentially identical to the RPi figure (3519 ms), both dominated by the
  fixed 700 ms tW waits + post-POR settle rather than ack-polling.
- The D33 `soft_por()` rewrite is confirmed regression-free on the
  MicroPython path and adds mid-transaction-reset resilience there too.

### 2026-11-08 — RPM re-test: spin-up transient explained, scripts hardened

User asked for a fan-speed re-test ("nothing changed on the power supply").
It did not need explaining as a power issue — the ~710 rpm figures from
today's first Pico/RPi smoke runs were a SPIN-UP TRANSIENT ARTIFACT of the
measurement, not a real speed change.

- Dedicated measurement (`pico_rpm_check.py`, kept in repo root) with proper
  settling + independent raw-counter verification. Key semantics confirmed
  against the datasheet (reg 52h/53h): TC1 holds INTERNAL CLOCK TICKS BETWEEN
  PULSES at 100 kHz (a period timer, NOT an accumulating pulse counter);
  Fan_RPM = 60·100,000/(TC1H·256+TC1L)/n. Measured: 25 % → ~736–748 rpm,
  50 % → ~1245–1271, 75 % → ~1800, **100 % → 2311–2327 rpm** — squarely in
  the historical band (2284.8–2316.6 across all prior benches). Fan and PSU
  are healthy; the driver's `rpm()` matches the datasheet formula exactly.
- Mechanism: the old scripts sampled 500–800 ms after applying 100 % duty.
  When the fan starts from rest it is still accelerating then (~710 rpm ≈ its
  25 %-duty speed); earlier runs caught the fan coasting from full speed (the
  chip sat at factory 100 % LUT between tests) and read ~2300. Both outcomes
  were "correct" for what they measured — just different moments in spin-up.
- Fix: `hw_smoke_test.py` and `e2e_hardware_test.py` now poll `rpm(1)` until
  two consecutive samples agree within 2 % (bounded 10 s) before asserting.
  Re-run confirmed: smoke reports **2316.6 rpm**, E2E 12/12 (tach section
  4013 ms — the convergence wait genuinely earned its keep). Scripts synced
  to the Pico and the RPi deploy dir.

Driver now validated on ALL THREE platforms with the FINAL core: RP2040
@ v1.29.0 (D33 core), ESP32 @ v1.29.0 (pre-D33 core — the change only
alters `soft_por` error handling, which already behaved benignly on ESP32),
RPi 3A+ CPython (D33 core).

### 2026-11-08 — Repo reorganization: bench scripts → `scripts/`

User request: tidy the repo root ahead of the planned GitHub upload. Moved all
40 loose hardware-bench scripts out of the root into `scripts/`, grouped by
bench:

- `scripts/pico/` (22 files): the 17 `e2e_*.py` Phase A/B slices plus
  `pico_deploy_check.py`, `pico_reflash_probe.py`, `pico_rpm_check.py`, and
  `probe_temp.py` (host-side serial REPL probe).
- `scripts/esp32/`: `esp32_probe.py`.
- `scripts/rpi/` (18 files): the `rpi_*.py` CPython diagnostics from the
  D32/D33 investigation.

Rationale: `tests/` stays reserved for host-runnable, CI-collectable unit
tests (the bench scripts import `machine` / need real hardware and would break
test collection); a dedicated top-level `scripts/` matches typical GitHub
layout. All scripts are self-contained (no cross-imports), so nothing broke.
Added `scripts/README.md` (inventory + how-to-run per bench) and a root
`.gitignore` (`__pycache__/`, `*.egg-info/`, build/dist artifacts). Historical
entries above still cite the old root locations — intentional as-of-time
references. Docs updated: root README (layout table, validated-on line,
134-test count), examples/README.md, docs/README.md, PLANS.md header note.

### 2026-11-08 — Cleanup: removed cloned upstream repo from `reference/`

User request: delete `reference/MAX31760-Python/` (clone of rudybrian/MAX31760-Python,
used only for the NOTES/02 baseline study). Nothing was copied into our code —
everything was rewritten from scratch — so the driver is unaffected; all findings
(bugs B1–B5, constant sets, architecture notes) remain in
`NOTES/02-reference-driver-review.md`. Removed 6 files (~70 KB). `reference/` now
contains only the datasheet PDF. Doc references updated: PLANS.md (§2, §10),
SUMMARY.md (§8 table), NOTES/02 header, NOTES/03 delivery-layout tree.

### 2026-11-08 — Datasheet decoupled from the repo (gitignored + canonical URLs)

User request: keep `reference/MAX31760.pdf` locally but never check it in
(vendor copyright — we don't own it and can't upload it to GitHub). Added to
`.gitignore`; documented the canonical online sources in README.md (new
References section), docs/README.md (new §10), NOTES/01 header, PLANS.md §10,
and this file (§4.1, §8 table): primary
https://download.mikroe.com/documents/datasheets/MAX31760.pdf , backup
https://www.analog.com/media/en/technical-documentation/data-sheets/max31760.pdf .
Also fixed the stale `reference/` row in the README layout table (it still
listed the upstream clone removed earlier today).

## 11. Open Items (non-blocking)

- Confirm `writeto_mem` presence at first Phase-A write (expected fine).
- Finalize F24 preset set incl. the single-fan variant (D11) during B11.
- Decide whether to `pip install mpremote` for dev convenience (recommended).
- ~~User's later RPi + ESP32-S3 cross-checks happen post-v0.1.0~~ → **COMPLETE
  2026-11-08**: ESP32 leg PASS (earlier that day); RPi leg PASS after the D33
  root-cause fix (smoke + E2E 12/12 + reliability 10/10).
- ~~**Redeploy fixed `_core.py` to the Pico** (`:/lib/max31760/_core.py`) when
  the Pico is reconnected — its copy predates D31–D33; re-run smoke + E2E to
  confirm no MicroPython regression.~~ → DONE 2026-11-08 (smoke + E2E 12/12
  PASS with the D33 core; see Build Log).
- ESP32 re-validation when the board is reconnected (optional; last validated
  2026-11-08 with the pre-D33 core — the D33 change only alters `soft_por`
  error handling, which already behaved benignly on ESP32).
- Wheel CI / PyPI publishing intentionally deferred (D3).
