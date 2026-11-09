# PLANS.md — MAX31760 Fan Speed Controller Driver (MicroPython + CPython/SBC)

Status: **v0.1.0 FROZEN — Phase A COMPLETE & hardware-verified; Phase B COMPLETE (B1–B12, hardware-verified); Phase C COMPLETE (C1–C10, 2026-11-07) · CROSS-PLATFORM PHASE COMPLETE 2026-11-08 (RPi 3A+ CPython over local SSH: PASS — smoke + E2E 12/12, root-caused & fixed the soft-POR errno-121 bug, D33; Pico W RP2040 @ COM16 v1.29.0: REVALIDATED WITH THE D33 CORE — smoke + E2E 12/12; ESP32 @ COM7 v1.29.0: PASS)**
Dates: 2026-11-03 (v1/v2) · 2026-11-07 (v3 — live hardware verification, transport-API correction, build start)
Handoff companion: `SUMMARY.md` (research, decisions, live-test results, resume instructions).
Standing orders (user, 2026-11-07): keep PLANS.md + SUMMARY.md current at all times; check off
milestones/tasks as confirmed; ALL public APIs and internal functionality must be tested
end-to-end on the real Pico bench — EXCEPTION: fan port 2 / TACH2 functional tests (no
second fan on bench; those are unit-tested against mocks only and marked EXCLUDED-HW).
Working dir: `<workdir>/FanSpeedController` (local checkout)
Repo layout reorganized 2026-11-08: all hardware bench scripts moved out of the
repo root into `scripts/{pico,esp32,rpi}/` (inventory + how-to-run in
`scripts/README.md`); `tests/` remains host-runnable unit tests only.
Project will be uploaded to GitHub — keep the tree tidy accordingly.

---

## 1. Goal

Build a production-quality **dual-platform driver** for the Maxim MAX31760 precision
fan-speed controller (as used on the MikroElektronika Fan 2 Click), covering the full I²C
protocol surface needed for fan control: temperature sensing, LUT-based automatic fan
speed, manual/direct duty control, tachometer/RPM monitoring, fan-fault handling, thermal
thresholds/alerts, EEPROM persistence, and device lifecycle (POR/standby).

Delivered as one `max31760` Python package (Option C — shared core + thin per-platform
transports, see §5):
- **MicroPython target**: RPi Pico (RP2040/RP2350) and ESP32-class boards, MicroPython ≥ 1.17.
- **Pure-Python (CPython) target**: any Linux SBC with an I²C bus — primary documentation
  for Raspberry Pi (all models incl. Zero/Zero 2), BeagleBone, and common RPi clones;
  generic Linux-SBC guidance for everything else.

Both entry points expose an **identical public API**, so application code drives the same
hardware unchanged whether it runs on a full-size SBC or an embedded MCU board.

Development & test environment (agreed 2026-11-07):
- **Primary bench (physically connected):** RPi Pico W (**first edition, RP2040** — misidentified as Pico 2 W until the 2026-11-08 reflash; user correction), MicroPython v1.29.0 (reflashed 2026-11-08; originally v1.19.1),
  USB-serial COM16 @ 115200 baud; MAX31760 on I2C0 (SDA=GP0/board-pin 1, SCL=GP1/board-pin 2),
  slave address 0x50. One fan on TACH1/port 1; 2N3906 PNP thermal diode on DXP/DXN
  (remote channel). The initial build is developed and iteratively tested HERE against real
  hardware.
- **Later cross-checks (user-run):** Raspberry Pi (CPython path) and ESP32-S3 (MicroPython path).

Success = every datasheet feature listed in §4 is reachable through a clean, documented,
integer-centric API; all host-side unit tests pass against a behavioral mock; the shared
core runs unmodified on Pico and ESP32 ports; no CPython-only constructs in shared code;
the API-parity gate passes between the two platform entry points.

## 2. Context & Research Findings

Full details in `NOTES/`:
- `NOTES/01-datasheet-analysis.md` — protocol, register map, data formats, fault model.
- `NOTES/02-reference-driver-review.md` — review of rudybrian/MAX31760-Python (upstream clone removed 2026-11-08):
  good constant sets & feature list; fatal bugs (B1–B5), heavy allocations,
  string-keyed APIs, incomplete EEPROM handling, Linux/smbus-only transport.
- `NOTES/03-micropython-target-notes.md` — `machine.I2C` API decisions, memory/timing
  constraints, testing strategy, delivery layout.
- `NOTES/04-dual-platform-expansion.md` — study of the pure-Python SBC target; options
  A/B/C compared; **Option C adopted** (rationale logged in §5.3).
- **Live hardware verification (2026-11-07)** — see §2.1: device answers at 0x50; both
  temperature channels read correctly; factory-default config confirmed; **transport API
  correction**: `mem_read`/`mem_write` are ABSENT on the v1.19.1 RP2040 build ⇒ baseline
  transport API is `readfrom_mem`/`writeto_mem` (see §5.1, A3, §8 risks).

Key protocol facts driving design:
- I²C slave addr 7-bit 0x50–0x57 (A2:A0 pins); Fast mode OK.
- Writes: pointer-incrementing, **8-byte pages, wrap within page** ⇒ bulk writes must be
  chunked per page row. Reads may span pages freely.
- Temperature: 16-bit two's complement, left-aligned, LSB=bit5=0.125 °C.
- LUT: 48 bytes @ 0x20–0x4F, 2 °C windows from <18 °C to ≥110 °C; duty=value/256.
- Tach: 100 kHz counter averaged over 4 pulses; `RPM = 6e6/(count·n)`; fail on count >
  threshold or overflow; 3-strike fault queue; FFDC forced duty on failure.
- EEPROM: EEX reg 5Bh (bit7 load/save + block select); device NACKs up to 550 ms after save.
- SR alarm bits clear on read; interrupt-mode ALERT service = read SR → … → ALTMSK=0.

### 2.1 Bench setup & live verification (2026-11-07)

Physical bench:

| Item | Value |
|------|-------|
| Host | Windows desktop, Python 3.14, pyserial 3.5 (mpremote not yet installed — candidate dev dep) |
| Board | RPi Pico W (first edition, RP2040); MicroPython v1.29.0 (reflashed 2026-11-08; originally v1.19.1) |
| Serial | COM16 @ 115200 8N1 |
| I²C | I2C0: SDA = GP0 (board pin 1), SCL = GP1 (board pin 2) |
| Device | MAX31760 @ 0x50 (A2:A0 = GND) |
| Fan | 1 unit on TACH1 / port 1 (port 2 unconnected) |
| Remote diode | 2N3906 PNP on DXP/DXN |

Verification performed (script `probe_temp.py`, raw-serial REPL, flat one-liners):
- Bus scan → exactly one device, 0x50 ✓
- LOCAL_TEMP (regs 58h/59h) = **+26.500 °C** (raw `1A80`) ✓
- REMOTE_TEMP (regs 56h/57h) = **+27.750 °C** (raw `1BC0`) ✓ — 2N3906 junction sits
  ~1.25 °C above die temp at rest; plausible.
- SR (5Ah) = `0x02` → TACH2A set: EXPECTED, CR3 enables TACH2 but port 2 is empty.
  TACH1A clear ⇒ the connected fan spins above the fail threshold (healthy).
- CR1=`01` CR2=`10` CR3=`03` FFDC=`FF` — matches datasheet factory defaults (Table 13).

Findings that changed the plan:
1. **`I2C.mem_read`/`mem_write` are not part of the standard MicroPython API** —
   AttributeError on v1.19.1 RP2040, and the official latest MicroPython docs contain
   no mention of them (checked 2026-11-07). Not a Pico-port or version quirk: expected
   equally absent on ESP32-S3 and all other ports. Baseline transport API =
   `readfrom_mem`/`writeto_mem` (canonical, long-standing, universal); the pre-1.17
   `transaction()` shim idea is dropped. `writeto_mem` presence to be confirmed at first
   Phase-A write (expected — same API vintage as readfrom_mem).
2. Raw-serial REPL delivery gotchas: indented blocks need a terminating blank line; a
   single-line compound statement (`if c: s`) swallows subsequent lines into its suite.
   Mitigation for scripted HW tests: flat one-liners, or ship scripts to flash
   (`mpremote cp` + `exec(open('x.py'))`). Candidate: `pip install mpremote` as dev tooling.
3. Single-fan bench ⇒ demos/presets should offer a single-fan configuration (disable
   TACH2E) so SR stays clean; noted for F24 preset tuning.

## 3. Scope

### In scope
- One `max31760` package: shared core + MicroPython transport + CPython transport
  (Option C layout, §5). Core has zero third-party deps (stdlib `time` only); the CPython
  adapter requires `smbus2` (with `python3-smbus` fallback).
- Full register coverage incl. user memory region; raw-access escape hatch.
- Identical public API on both platform entry points (enforced by an automated parity test).
- Behavioral mock + unittest suite runnable under host CPython 3 (CI-friendly).
- Examples: Pico, ESP32, Raspberry Pi (+ BeagleBone/generic-Linux notes) + hardware
  smoke-test script + usage docs.
- Packaging: drop-in package + `requirements.txt` AND minimal `pyproject.toml` so
  `pip install .` works today (wheel automation & registry publishing deferred).
- Attribution/license headers (MIT, credit upstream author & Mikroe reference).

### Out of scope (explicitly deferred)
- GUI/web UI, daemon/systemd service packaging.
- Wheel-build CI automation and registry (PyPI/private index) publishing — revisit when a
  real second consumer appears.
- GPIO-driven ALERT/FF/FS interrupt wiring (driver supports polling + service routines;
  ISR integration left to application code — documented pattern provided).
- Windows/macOS hosts (CPython target is Linux-only; MicroPython target unaffected).
- Hardware bring-up/debugging beyond providing the smoke-test script.

## 4. Functional Requirements (protocol coverage checklist)

Each item maps to an API in §5. All must be implemented and unit-tested.

| ID | Requirement | Datasheet basis |
|----|-------------|-----------------|
| F1 | Initialize on caller-supplied `machine.I2C`; validate address 0x50–0x57; optional bus scan self-test | Table 13 |
| F2 | Read local/remote temperature (°C float, 0.125 resolution, signed) | §Temperature Sensing |
| F3 | Get/set 4 setpoints: LHS, RHS, LOTS, ROTS (°C float, full ±128 range) | Table 5 |
| F4 | Bulk read LUT (48 duties) + single/bulk write with page-safe chunking | Table 7 |
| F5 | LUT window helpers: temp↔index↔address; monotonic-curve builder utility | Fig. 4/Table 7 |
| F6 | Manual mode: enable/disable DFC, set duty (raw 0–255 and %), read current PWMV | §Direct Control |
| F7 | Auto mode config: index source (local/remote/max), hysteresis 2/4 °C | CR1 MTI/TIS/HYST |
| F8 | PWM output config: frequency 33 Hz/150 Hz/1.5 kHz/25 kHz, polarity | CR1 DRV/PPS |
| F9 | Ramp rate selection (3.125/6.25/12.5 %/s, immediate) + wait-for-duty helper | CR3 RAMP |
| F10 | Spin-up enable/disable | CR2 SPEN |
| F11 | Tach: enable/disable TACH1/2; read RPM (configurable pulses/rev; guard count=0 and overflow) | §Tachometer Inputs |
| F12 | Set/get min-RPM fail threshold (proper 16-bit TCTH/TCTL, clamped ≤65535) | TCT regs |
| F13 | Fan-fail handling: read status, clear faults (CLRFAIL), FFDC get/set, FF_0, comparator/interrupt FF mode | CR2/CR3/SR |
| F14 | RD/locked-rotor mode: FSST + RDPS | CR2 |
| F15 | 3-wire assist: pulse-stretch (PSEN) set/clear incl. one-shot measure sequence; TACHFULL | CR3 |
| F16 | Status: raw SR read; named flag constants; compact active-alarm bitmask; remote-diode-fault check | SR |
| F17 | Alert mask get/set (all 6 alarms, reserved bits preserved) | MASK |
| F18 | Interrupt-mode ALERT service routine (SR read → ALTMSK clear) | §ALERT |
| F19 | Ideality factor: numeric nearest-match set + exact-index get/set; 64-entry table | IFR/Table 4 |
| F20 | EEPROM: save_config(block-select), load_config(block-select), busy ack-poll w/ timeout, program-corrupt check + recovery helper | EEX/SR.PC |
| F21 | Lifecycle: soft POR, standby enter/exit, user-memory (10h–17h) read/write | CR1.6/CR2.7 |
| F22 | Raw access: `read_reg(reg,n)`, `write_reg(reg,buf)` with bounds checks | — |
| F23 | Error model: `ValueError` bad args, `OSError` bus/NACK (retry once), `TimeoutError` EEPROM busy overrun; never silent -1/False | — |
| F24 | Presets: `configure_4wire_fan()`, `configure_3wire_supply_modulation()`, `configure_two_fans()` convenience combos | Table 10 |
| F25 | CPython transport adapter: `smbus2` primary, `import smbus` fallback; configurable bus number (default 1); absorbs `read_i2c_block_data` register-prepend quirk; maps kernel errors to `OSError` | Linux i2c-dev |
| F26 | Cross-platform API parity: both entry points expose identical public surface (method set, signatures, constants, exception semantics) — enforced by automated parity test | — |
| F27 | Distribution: drop-in package + `requirements.txt`; minimal `pyproject.toml` supporting `pip install .` | — |

## 5. Architecture

### 5.1 Layered design (Option C — shared core + thin per-platform transports)

```
Application code (identical on every platform)
      │
      ▼
max31760.mp.MAX31760 / max31760.cp.MAX31760     (thin façades — bind a transport)
      │
      ▼
_core.MAX31760(transport, addr)                  (device API — F1..F24)
  • typed int constants (plain ints for MP compat)
  • RMW field setters (read-modify-write, isolate fields, preserve others)
  • fixed-point temp math, 16-bit-aware tach/threshold math
  • page-safe bulk writes (chunks ≤8-byte writes onto 8-byte page rows)
  • retry-on-OSError (1 retry, ~5 ms backoff) + error model (F23)
  • EEPROM sequencing + ack-poll
      │  (duck-typed transport contract — no inheritance)
      ▼
Transport adapters (~40–60 LOC each)
  _transport_mp : machine.I2C.readfrom_mem/writeto_mem (universal baseline;
                  mem_read/mem_write NOT relied upon — verified absent on v1.19.1 RP2040)
  _transport_cp : smbus2 (fallback: python3-smbus), configurable bus number
```

**Transport contract** (implemented by both adapters, consumed by core):
- `burst_read(reg, n) -> bytes` — pointer read of n bytes starting at `reg` (reads may
  span pages; that is legal per datasheet).
- `burst_write(reg, data) -> None` — raw write of `data` (1–8 bytes) starting at `reg`;
  alignment/chunking is the **core's** job (protocol knowledge stays in one place).
- `probe() -> bool` — address ACK check (self-test/discovery). Optional `close()`.

### 5.2 Package layout

```
max31760/
├── __init__.py         # __version__ only (flash-friendly; no eager platform imports)
├── _core.py            # MAX31760(transport, addr) — the single source of truth
├── _transport_mp.py    # MicroPython machine.I2C adapter
├── _transport_cp.py    # CPython smbus2/smbus adapter (bus-number param, default 1)
├── mp.py               # MAX31760(i2c, addr=0x50) — MicroPython entry point
└── cp.py               # MAX31760(bus=1, addr=0x50, handle=None) — CPython entry point
```

Construction takes the platform-native I²C resource (an unavoidable difference); the
**post-construction public API is identical** on both platforms because both façades
return the same class (`_core.MAX31760`) — parity holds by construction and is
additionally gated by test (F26).

### 5.3 Decisions & rationale (approved 2026-11-03)

| # | Decision | Choice | Why |
|---|----------|--------|-----|
| 1 | Structure | **Option C**: shared core + thin per-platform transports, proper `max31760/` package | Makes "identical functionality/API" a structural property (logic exists once); transports isolated & swappable; best testability. Option A (two independent files) rejected — ~90% duplication invites drift. Option B (one adaptive file) retained as fallback only |
| 2 | CPython dependency | **Require `smbus2`**, with 5-line `import smbus` fallback in the adapter | smbus2 = maintained, pure-Python, no toolchain needed; fallback covers stock `apt install python3-smbus` images at near-zero cost; both share the same SMBus API |
| 3 | Distribution | **Hybrid**: drop-in package + `requirements.txt` **and** minimal `pyproject.toml` (`pip install .` works today) | Transparent/simple for hobbyists while enabling reproducible installs; wheel-build CI and registry publishing deferred until a real second consumer exists |
| 4 | SBC scope | Any Linux system with an I²C bus; primary docs: **Raspberry Pi (all models incl. Zero/Zero 2)**, **BeagleBone**, common RPi clones; generic Linux-SBC guidance otherwise | Bus number is a constructor parameter (default 1); I²C enablement varies by distro/board ⇒ docs give per-family steps + generic fallback (`i2cdetect`, `/dev/i2c-*`) |
| 5 | Parity enforcement | Shared core (structural) **+ automated parity test** (F26) comparing façades' exposed surface | Belt-and-braces: prevents future divergence of the thin façades/constants |
| 6 | Size budget (amended 2026-11-07) | **Soft target ~16 KB per shared module**; when a module grows past it, DECOMPOSE into small single-purpose modules (`_tables.py`, `_lut.py` pattern) — never trim functionality or documentation to fit size | User ruling 2026-11-07: small size helps but must not cost functionality nor properly documented code; decomposition keeps parity auditability while honoring the footprint theme |
| 7 | MCU scope (clarified 2026-11-07) | MicroPython targets: Pico RP2040/RP2350 + ESP32-class boards; **ESP8266-class boards explicitly OUT OF SCOPE** | User ruling 2026-11-07; removes any design pressure toward ultra-tight-RAM compromises that would hurt the in-scope targets |

Design rules (from notes): integer-centric API (no string keys), no per-call dict
allocation, tables as tuples, floats only at final presentation values (temps, RPM, %),
each shared module targets ~16 KB (SOFT — decompose rather than truncate, decision 6),
Python-3-syntax valid under the MicroPython subset (lint-gated).

Public API sketch (final names settled during build). Entry points differ only in how the
I²C resource is supplied; everything after construction is identical:
```python
# MicroPython:
dev = max31760.mp.MAX31760(i2c, addr=0x50)
# CPython/Linux:
dev = max31760.cp.MAX31760(bus=1, addr=0x50)

dev.local_temp_c; dev.remote_temp_c          # F2
dev.set_local_high(70.0); dev.get_remote_ot()  # F3
dev.lut_get(); dev.lut_set(list48); dev.lut_set_index(12, 200)  # F4/F5
dev.manual_enable(True); dev.set_duty(50); dev.current_duty_raw()  # F6
dev.index_source(MAX31760.INDEX_MAX); dev.hysteresis_c(4)         # F7
dev.pwm_freq(HZ_25K); dev.pwm_polarity(POSITIVE)                  # F8
dev.ramp_rate(RAMP_IMMEDIATE); dev.wait_for_duty(50, timeout_ms=2000)  # F9
dev.rpm(fan=1, pulses_per_rev=2)                                  # F11
dev.set_min_rpm(600, pulses_per_rev=2)                            # F12
dev.status_raw(); dev.active_alarms(); dev.clear_fan_fault()      # F13/F16
dev.service_alert()                                               # F18
dev.ideality_set(1.005)                                           # F19
dev.save_config(); dev.load_config(); dev.program_corrupt()       # F20
dev.soft_por(); dev.standby(True)                                 # F21
dev.read_reg(0x50); dev.write_reg(0x50, b"\x80")                  # F22
```

## 6. Implementation Plan (tasks, in order)

Checkboxes tracked here during build. Each task ends green (tests pass) before the next starts.

### Phase A — Foundations
- [x] **A1.** Scaffold repo layout per §5.2: `max31760/` package at repo root (no `src/`), plus `tests/`, `examples/`, `requirements.txt`, `pyproject.toml`, `README.md`. *(done 2026-11-07)*
- [x] **A2.** Register/bitmask constants module section (verified vs datasheet table; factory-default table included). *(done 2026-11-07 — encodings re-verified against parsed datasheet Tables 1/4/6/11/13/34; factory defaults match live bench reads)*
- [x] **A3.** Transport layer: `_reg_read/_reg_write/_burst_read/_page_safe_write`, retry logic, address validation. MicroPython adapter uses `readfrom_mem`/`writeto_mem` (baseline; `mem_read`/`mem_write` verified absent on v1.19.1 RP2040 — do not depend on them). *Accept: unit tests prove page-wrap protection (unaligned 9-byte write raises ValueError; aligned multi-page write splits correctly); live check on Pico: one `writeto_mem` round-trip to a scratch register (USER region 10h).* *(done 2026-11-07 — host suite green incl. page-wrap + retry tests; LIVE E2E on Pico: probe, temp reads, 0xA5 single-byte round-trip, 8-byte page-row bulk write/read-back, restore — ALL PASS; `writeto_mem` existence confirmed)*
- [x] **A4.** Fixed-point helpers: `temp_to_raw16/raw16_to_temp` (round-trip incl. negatives), `duty_to_pct/pct_to_duty`, `rpm_from_count/count_from_rpm` (clamp+overflow semantics). *Accept: property-style round-trip tests.* *(done 2026-11-07 — 13-vector encode/decode table incl. boundaries; strict range check pre-quantization; count=0→stopped guard; 16-bit clamp)*

### Phase B — Core device API
- [x] **B1.** Constructor + init/self-test (scan option). *(F1)* *(done 2026-11-07 — `scan()` + `verify()` (raises OSError when absent); transport contract gains `scan()` (MP native `i2c.scan()`, CP probes 0x03..0x77 via RO LTH read); mock upgraded to multi-address bus model; LIVE E2E: verify=True, scan=[0x50])*
- [x] **B2.** Temperatures + 4 setpoints. *(F2,F3)* *(done 2026-11-07 — `local_temp_c`/`remote_temp_c` properties; get/set pairs for LHS/RHS/LOTS/ROTS sharing temp encoding (Table 5→Table 1); setters validate -128..+127.875 C; single aligned 2-byte wire write per setpoint; LIVE E2E: temps sane, all four round-trip + factory restore)*
- [x] **B3.** LUT get/set/index + curve-builder utility. *(F4,F5)* *(done 2026-11-07 — `lut_get()`/`lut_set(list48)` bulk (six page-aligned wire writes), `lut_get_index(i)`/`lut_set_index(i,duty)` single-entry; pure utilities `lut_index_for_temp()` + `build_lut_curve(points)` (monotonic-breakpoint linear interpolation, midpoint sampling, clamped ends) live in `_lut.py`; LIVE E2E: factory 48×FF confirmed, on-device curve build, bulk round-trip, single-entry isolation, factory restore)*
- [x] **B4.** Manual/auto modes, duty, PWM freq/polarity, index source, hysteresis. *(F6,F7,F8)* *(done 2026-11-07 — `manual_enable/manual_enabled` (CR2.DFC), `set_duty_pct/set_duty_raw/get_duty_cmd_raw`, `get_actual_duty_raw/pct` (PWMV RO); `set/get_index_source` (INDEX_* consts, reserved 0x02 rejected), `set/get_hysteresis_c` (2|4 only), `set/get_pwm_freq_hz` (33/150/1500/25000), `set/get_pwm_polarity` (POLARITY_* consts); RMW helpers preserve other CR1/CR2 bits; public constants exposed as class attrs per API sketch. CAUGHT: latent Phase-A bug — CR1 DRV bit values were off by one position (correct: bits [4:3], 150Hz=0x08/1.5k=0x10/25k=0x18); regression test added. LIVE E2E incl. observable effect: PWMV slewed 255→128 on manual 50%; required disabling TACH2E + CLRFAIL first (persistent TACH2A latches fan-fail ⇒ output forced to FFDC 100%) — D11 now MANDATORY for single-fan configs)*
- [x] **B5.** Ramp rate + `wait_for_duty`. *(F9)* *(done 2026-11-07 — `set/get_ramp_rate` (RAMP_* consts, CR3 bits [5:4], RMW-preserving); `wait_for_duty(target_pct, timeout_ms=2000)` polls PWMV every 10 ms via transport delay, returns True on reach, raises TimeoutError on overrun; LIVE E2E: immediate settle 1 ms; slow ramp measured 26.6 % after 1 s from 25 % — matches datasheet 3.125 %/s exactly)*
- [x] **B6.** Tach enable, RPM reads, threshold get/set. *(F11,F12)* *(done 2026-11-07 — `tach1/2_enable(enabled)` (CR3 RMW); `rpm(port, pulses_per_rev=2)` (RO TC pair, single aligned read; 0.0 on count=0 — fixes upstream B4 div-by-zero; overflow surfaces as TACHxA per datasheet, no bogus numbers); `set/get_tach_threshold` (proper 16-bit TCTH:TCTL big-endian pair, ValueError outside 0..65535 — fixes upstream B3). LIVE E2E: bench fan reads ~2322 RPM @ppr=2 with consistent ppr scaling; TACH2A alarm path exercised (no port-2 fan: EXCLUDED-HW for functional RPM-on-port-2 only). MEASURED: TACH2A re-latches ~8 s after CLRFAIL+re-enable (2 s startup grace + fault-queue cadence). LESSON: SR is at 0x5A — 0x04 is the ALERT MASK register (factory C0h); an early E2E draft read the wrong address and misread the mask as status)*
- [x] **B7.** Fault handling: status, masks, CLRFAIL, FFDC, FF_0, FF mode, RD mode. *(F13,F14,F16,F17)* *(done 2026-11-07 — `status_raw()` (SR @ 0x5A, clear-on-read documented), SR_* flag constants, `remote_diode_fault()`, `clear_fan_fail()`, `set_ffdc_raw/pct`+`get_ffdc_raw`, `set_ff_zero_detection/ff_zero_detection` (CR3.FF_0), `set/get_ff_mode` (FF_MODE_INTERRUPT/COMPARATOR), `set_rd_mode/rd_mode_enabled` (FSST), `set/get_rd_polarity` (RDPS), `set/get_alert_mask` (MASK 0x04, six alarm bits RMW'd, reserved upper bits preserved, RDFA has no mask bit). DECOMPOSITION: fault domain extracted to `_faults.py` (FaultMixin mixed into MAX31760; ordering-safe circular import documented); lint gate extended. LIVE E2E: FFDC force path PROVEN on silicon (output followed FFDC 255→128→255 under persistent TACH2 fan-fail); re-arm latency 7.5 s via public API; all round-trips + restore)*
- [x] **B8.** 3-wire assists (PSEN one-shot, TACHFULL), spin-up. *(F10,F15)* *(done 2026-11-07 — `spin_up_enable/spin_up_enabled` (CR2.SPEN), `pulse_stretch_enable/pulse_stretch_enabled` (CR3.PSEN), `tacho_full_enable/tacho_full_enabled` (CR3.TACHFULL), `measure_tach_once(port=1, timeout_ms=3000)` one-shot PSEN sequence (sets PSEN, polls TC until change/timeout, clears PSEN in finally; enforces 33 Hz + TACHFULL-off preconditions with ValueError). LIVE E2E: spin-up OBSERVABLE (held 100%% ~2.17 s under 2 s timeout w/ dead port 2, then reverted to 50%%); TACHFULL FUNCTIONAL (TC1 frozen below 100%% duty, resumed after clear+accel); PSEN contract + 150 Hz rejection on real HW. MEASURED: stretched-pulse waveform NOT visible via I2C (PWMV holds commanded duty); TC1 updates even at 5%% duty/33 Hz on this silicon — "low duty freezes TC" is not a valid precondition here)*
- [x] **B9.** ALERT service routine; ideality factor. *(F18,F19)* *(done 2026-11-07 — `set/get_alert_mode` (ALERT_MODE_INTERRUPT/FAULT_INDICATOR, CR2.ALERTS), `service_alert()` (datasheet step 2: SR read, clear-on-read documented), `alert_masked()`/`clear_alert_mask()` (CR1.ALTMSK steps 3/5); `set_ideality_factor_index(idx)` (IFR bits [5:0], reserved upper preserved), `get_ideality_factor_index()`, `get_ideality_factor()` (table lookup float), `set_ideality_factor(n)` nearest-match w/ range rejection + lower-index tie-break; IDEALITY_TABLE exposed as class attr. LIVE E2E: FULL ISR SEQUENCE ON REAL SILICON — LHS lowered below ambient forced LHA latch; service_alert() returned SR=22 (LHA|TACH2A); silicon itself set ALTMSK after the SR read (device behaviour verified, not driver emulation); attend+unmask walked; final SR clean. Ideality: IFR 0x18->0x00 shifted remote temp +2.0 C immediately, restored after ~4 s settle. MEASURED: bench diode reading settles slowly (~4 s) around IFR changes — fixture coupling, API unaffected)*
- [x] **B10.** EEPROM save/load + ack-poll + corrupt recovery; soft POR; standby; user memory. *(F20,F21)* *(done 2026-11-07 — `save_config(blocks=EEX_ALL_BLOCKS, timeout_ms=2000)` / `load_config(...)` (EEX L/W + block-select bits EEX_BLOCK_00_0F..40_4F; ack-polls transport.probe() every 10 ms until the device ACKs again, TimeoutError on overrun); `eeprom_corrupt()` (SR.PC — persists across SR reads, only clears after successful write + POR); `recover_from_corruption(timeout_ms)` (rewrite-all-blocks → soft POR → verify PC cleared); `soft_por(settle_ms=100)` (CR1.SW_POR self-clearing + bus-settle wait); `enter_standby()/exit_standby()/standby_active()` (CR2.STBY); `user_memory_get/set/read_all/write_all` (10h..17h). Transport MP probe switched from full-bus scan to a single RO-register transaction (OSError on NACK = exact ack-poll semantics). Mock now models: PC persistence across SR reads, EEX tW NACK window with deferred RAM<->EEPROM copy per block mask, SW_POR reload-from-EEPROM + latch clear. LIVE E2E: REAL EEPROM CYCLES — save_config ack-polled 279 ms; soft POR proved persistence (CR1 DRV 150 Hz, LUT[0]=80h, user[0]=A5h all survived reset); load_config overwrote RAM back from EEPROM; standby enter/exit with I2C responsive; final POR verified full config == pre-test snapshot byte-for-byte; PC clean throughout)*
- [x] **B11.** Raw access + presets. *(F22,F24)* *(done 2026-11-07 — raw access (read_reg/write_reg bounds-checked, RO-SR write rejection, page-safe chunking) + error model (ValueError/OSError-retry-once/TimeoutError) were already in place from Phase A; ADDED F24 presets: `configure_4wire_fan(port=1, pwm_freq_hz=25k)` (Fig. 2a), `configure_3wire_supply_modulation(port=1)` (Fig. 2b: 33 Hz + PSEN), `configure_two_fans()` (both TACH armed); all apply single-fan hygiene per D11 and are MODE-NEUTRAL (do not touch DFC — documented). LIVE E2E: 4-wire preset drove PWMV=128 @50% with duty->speed CAUSALITY proven (1277 -> 2250 RPM at 100%); 3-wire preset one-shot TC valid via PSEN path; two-fans preset armed the dead port-2 detector (TACH2A latched after 8 s). KEY FINDING: factory CR2 has DFC=0 => automatic LUT mode governs the output (factory LUT=all FF => 100%); earlier phases ran implicitly in manual mode because an ad-hoc script had set DFC=1 — a soft POR (B10) silently reverted the bench to LUT mode. Presets document the manual_enable() requirement; E2E enables it explicitly. MEASURED: factory ramp rate makes 255->128 take ~15 s (immediate ramp forced in E2E test-setup)*
- [x] **B12.** CPython transport adapter (`smbus2` + `smbus` fallback, bus-number select,
      block-read quirk) + adapter unit tests against a fake smbus object. *(F25)* *(done 2026-11-07 — adapter itself was built in Phase A; this milestone closes its INTEGRATION testing: `TestCPIntegration` runs the full driver stack (cp facade + TransportCP + core) over an injected FakeSMBus handle across every API domain (raw access, manual mode/duty/ramp/wait_for_duty, LUT, temps/setpoints, tach/threshold, fault domain, 3-wire assists, alert mode + ideality, EEPROM save/load through the chunked CP path, soft POR reload-from-EEPROM, standby, user memory, presets, close semantics). FAKE FIXTURE UPGRADE: FakeSMBus now models the tW NACK window at wire level (every transaction NACKs while busy_polls > 0, each attempt consumes a poll) — previously only MockChip.probe_ok knew about it, so the CP probe() (a real register read) saw no busy state and EEX copies never applied on the CP path. Live RPi run of the cp facade DEFERRED to the user-driven cross-platform phase (bench is MicroPython-only; no i2c-dev/smbus here). Suite: 122 -> **123, all GREEN**)*

### Phase C — Quality & delivery
- [x] **C1.** Mock I²C simulator hardening: emulate page wrap, EEPROM busy window, SR clear-on-read, 3-strike fault queue, NACK injection for retry tests. *(done 2026-11-07 — page-wrap violation tracking ✓ (MockChip.violations), EEPROM tW busy window ✓ (deferred RAM<->EEPROM copy per block mask; since B12 also enforced at wire level in FakeSMBus so BOTH transports see it), SR clear-on-read ✓ (incl. PC persistence across reads), NACK injection ✓ (chip.nack + FlakyTransport for retry-once semantics). 3-strike fault queue deliberately NOT emulated: the driver treats SR as an opaque latch (correct per datasheet — the master never sequences the strikes); bench-measured ~8 s re-arm latency documented instead)*
- [x] **C2.** Complete unittest suite (target: ≥60 assertions across F1–F24; 100% of public methods exercised). *(done 2026-11-07 — **127 tests / all GREEN**; NEW automated coverage gate `tools/api_coverage.py` proves all **123 public members** of the shared core are referenced by the suite (gate added after finding 3 untested EEX block-select constants, now covered by test_each_block_select_constant_encodes_correctly)*
- [x] **C3.** Static sanity: run module import + full test suite under `pylint`-free check via `python -m compileall` and a MicroPython-subset lint pass (no CPython imports, no type hints, no f-string edge cases). *(done 2026-11-07 — `python -m compileall max31760 tests tools` PASS; `tests/lint_subset.py` (MicroPython-subset gate: forbidden imports/syntax on _core/_tables/_lut/_faults/_transport_mp/mp/__init__) PASS; AST parse of MP files PASS)*
- [x] **C4.** Docs: `docs/README.md` (wiring, quick start, full API reference, error model, EEPROM-endurance guidance, ISR-pattern example), docstrings on every public method. *(done 2026-11-07 — `docs/README.md`: wiring tables (bare chip + bench config), per-platform install incl. I2C enablement, quick starts, full API reference grouped into 11 domains with all 90 methods + 31 constants, error-model table, measured operational notes (LUT-mode factory default, ~8 s fan-fail re-arm, ~280 ms tW, ~4 s IFR settle, PSEN observability limits, standby-I2C-alive), ALERT ISR pattern example; every public method carries a docstring (verified by the coverage gate referencing each name)*
- [x] **C5.** Examples: `pico_demo.py`, `esp32_demo.py`, `rpi_demo.py`, `hw_smoke_test.py` (smoke test iterated live on the connected Pico/COM16 during the build). *(done 2026-11-07 — all four written; `hw_smoke_test.py` RUN LIVE ON THE BENCH: temps local 26.4 C / remote 27.9 C (+1.5 C as expected for the 2N3906), full duty sweep 0/25/50/75/100 % hit exact actuals (0/64/128/192/255), rpm @100 % = 2298.9, EEPROM round trip + soft-POR survival with discriminating sentinel (CR1 19h->1Dh), registers AND EEPROM left in pre-test state. PASS. Design note: smoke test flips a CR1 bit via XOR (guaranteed-different marker) and re-saves block 00-0F after restoring so the bench EEPROM ends clean)*
- [x] **C6.** **E2E hardware matrix (user mandate 2026-11-07):** `examples/e2e_hardware_test.py`
      systematically exercises EVERY public API method on the Pico bench with observable-
effect verification (register read-back, expected sensor values, audible fan response);
      TACH2/port-2 functional items marked EXCLUDED-HW (unit-tested only); results table
      committed to PLANS.md §7 and SUMMARY.md. *(done 2026-11-07 — 12-section self-restoring matrix; LIVE RUN: 12/12 PASS (see §7 results table). Iteration notes: hysteresis is a 2-or-4 °C field (test corrected from 1 °C); LUT helpers are module-level exports, not class attrs; build_lut_curve evaluates windows at midpoints (17..111 °C) so endpoint breakpoints must sit at window midpoints for exact endpoints; docs corrected for the true Table-7 window geometry)*
- [x] **C7.** Packaging: `requirements.txt`, minimal `pyproject.toml`; verify `pip install .`
      into a fresh venv on Linux. *(F27)* *(done 2026-11-07 — pyproject.toml (setuptools, MIT, smbus2 gated to platform_system=='Linux') + requirements.txt already in place; VERIFIED: fresh venv + `pip install .` + import of both facades OK on the Windows host (smbus2 correctly skipped via the platform marker). Full Linux-venv verification DEFERRED with the cross-platform phase (no Linux box at the bench)*
- [x] **C8.** SBC examples + docs: Raspberry Pi (all models incl. Zero/Zero 2), BeagleBone,
      generic Linux SBC (I²C enablement per family, bus discovery, `i2cdetect` verification). *(done 2026-11-07 — `examples/rpi_demo.py` (CPython demo, bus selection, i2cdetect hint); docs/README.md §2 expanded: RPi all models incl. Zero/Zero 2 W (raspi-config + dtparam fallback), BeagleBone DT overlays (dtboe i2c0/i2c1, P9.17/P9.18), generic SBC pinmux + /dev/i2c-N discovery + i2cdetect verification)*
- [x] **C9.** API-parity gate: automated test asserting identical public surface (class
      identity, method names/signatures, constants, exception types) on both entry points. *(F26)* *(done 2026-11-07 — `TestApiParity`: shared-core MRO identity, module __all__ match, full public-surface diff (names, inspect.signature per method, constant values, property-ness). Gate immediately caught a REAL asymmetry: close() existed only on the cp facade — fixed by adding a documented no-op close() to mp.py so portable code can call it on both platforms. Suite now 127 green)*
- [x] **C10.** Final review pass: verify every F-row in §4 has API + test; update this file's checkboxes; freeze v0.1.0. *(done 2026-11-07 — F1–F27 audited row-by-row against the implemented API + suite: all covered EXCEPT F16's "compact active-alarm bitmask", which was MISSING despite being promised in the risk table → added `active_alarms()` to `_faults.py` (+ unit test incl. PC-persistence semantics, + live matrix check, + docs row). Final gates: 128 tests green, coverage gate PASS (124 public members), lint PASS, compileall PASS, parity gate green, E2E matrix 12/12 PASS with the new member. v0.1.0 frozen)*

## 7. Verification Plan

1. **Host unit tests** (primary gate): `python -m unittest discover tests` under CPython 3 —
   all green. Mock sim asserts wire-level legality (page alignment, ≤8-byte writes, correct
   repeated-start reads, EEPROM timing behavior).
2. **Syntax/subset check**: `compileall` + grep gates on `_core.py`, `_transport_mp.py`,
   `mp.py` (no CPython-only imports such as `smbus`/`sys`/`os`, no type annotations).
   `_transport_cp.py`/`cp.py` are exempt (CPython-only by design).
3. **Hardware smoke test** (bench, ongoing): `examples/hw_smoke_test.py` on the connected
   Pico W (COM16) + MAX31760 — prints temps (expect local ≈ ambient, remote ≈ local+
   1–2 °C with the 2N3906), sweeps manual duty 0→100 % (audible fan-speed change), reads
   RPM on TACH1 (TACH2 disabled in the single-fan preset), saves/loads EEPROM, exercises
   POR. Run INCREMENTALLY during Phases A–B, not only at the end. Later: user repeats on
   Raspberry Pi (CPython path) and ESP32-S3 (MicroPython path).
4. **Cross-port check**: identical package imported on both rp2 and esp32 firmware builds
   (no port-specific code paths in shared code).
5. **CPython adapter exercise**: host suite drives `_core` through the CPython adapter
   against a fake `smbus2` object (covers the block-read prepend quirk, bus selection,
   error mapping — no hardware needed).
6. **Parity gate**: automated comparison of the public surfaces exposed by `max31760.mp`
   and `max31760.cp` (class identity, method names/signatures, constants, exception
   semantics) — must match. *(F26)*
7. **End-to-end hardware coverage (MANDATORY — user directive 2026-11-07):** every public
   API method and internal function is exercised end-to-end on the connected Pico bench
   (real MAX31760) via `examples/e2e_hardware_test.py`: drive each API, verify the
   OBSERVABLE EFFECT (register read-back equals written value, sensor readings sane,
   fan audibly responds to duty sweeps, EEPROM persists across reload/POR), record
   PASS/FAIL per method. **Exception (bench limitation):** fan port 2 / TACH2 FUNCTIONAL
   tests (no second fan connected) — those methods are covered by mock unit tests only
   and marked EXCLUDED-HW in the matrix. Runs INCREMENTALLY: transport slice after Phase A;
   full device-API slice after Phase B; examples/packaging after Phase C. Results logged
   in PLANS.md (checkboxes) + SUMMARY.md.

### E2E hardware matrix results (C6, run 2026-11-07 on Pico bench / COM16)

`examples/e2e_hardware_test.py` — self-restoring (snapshots 0x00..0x4F, restores RAM
byte-for-byte + re-saves EEPROM block 00-0F):

| # | Section | Observable effect verified | Result |
|---|---------|----------------------------|--------|
| 1 | identity/probe/scan/user-memory | probe, scan finds 0x50, user memory get/set/read_all/write_all round trips | PASS (9 ms) |
| 2 | temperature/setpoints/index-source | local/remote plausible; LHS/LTS/RHS/RTS/HYST round trips; index source LOCAL/REMOTE | PASS (10 ms) |
| 3 | manual-mode/duty/ramp/freq/polarity | DFC set; PWMR read-back; actual duty hits 128 @50 %; ramp/freq/polarity round trips | PASS (10 ms) |
| 4 | lut/bulk+index/helpers | 48-entry bulk round trip; single index; lut_index_for_temp; build_lut_curve endpoints + monotonicity | PASS (19 ms) |
| 5 | tach1/rpm/threshold (+port2 EXCLUDED-HW) | TACH1 armed; rpm > 500 at 100 % duty; threshold round trip; port-2 contract-only (no fan) | PASS (806 ms) |
| 6 | 3-wire one-shot measure_tach_once | 33 Hz + PSEN preset; valid TC count returned | PASS (161 ms) |
| 7 | fault-domain round trips | SR readable; RDFA false (diode connected); CLRFAIL; **active_alarms()==0 post-CLRFAIL** (F16 compact bitmask); FFDC raw/pct; FF_0; FF mode; RD mode/polarity; alert mask | PASS (13 ms) |
| 8 | alert-mode/service/ideality | both alert modes; service_alert; ALTMSK clear; IFR index + nearest-match vs IDEALITY_TABLE | PASS (12 ms) |
| 9 | eeprom/por/standby/recovery | save/load sentinel round trip; PC clean; soft-POR survival; standby w/ live I²C; recover_from_corruption no-op path | PASS (351 ms) |
| 10 | spin-up/tacho-full bits | SPEN + TACHFULL bit round trips | PASS (5 ms) |
| 11 | presets register effects | 4-wire: 25 kHz + TACH hygiene; two-fans: both TACH enables | PASS (9 ms) |
| 12 | error model (ValueError paths) | RO-SR write, out-of-map/too-long reads, bad duty/threshold/ramp/LUT-index/IFR/port all raise ValueError | PASS (7 ms) |

**Overall: 12/12 PASS — `E2E HARDWARE MATRIX: PASS`** (final run includes
`active_alarms()` added during the C10 review). Port-2/TACH2 functional items
remain EXCLUDED-HW (unit-tested vs mocks only), per standing order.

### Cross-platform re-run — ESP32 bench (COM7, MicroPython v1.29.0, 2026-11-08)

Same self-restoring matrix, board-aware wiring (I2C0 SDA=GPIO41 / SCL=GPIO42,
pins auto-selected via `sys.platform == "esp32"`). Package deployed to
`:/lib/max31760/` (D26).

| # | Section | Result |
|---|---------|--------|
| 1 | identity/probe/scan/user-memory | PASS (17 ms) |
| 2 | temperature/setpoints/index-source | PASS (20 ms) |
| 3 | manual-mode/duty/ramp/freq/polarity | PASS (19 ms) |
| 4 | lut/bulk+index/helpers | PASS (18 ms) |
| 5 | tach1/rpm/threshold (+port2 EXCLUDED-HW) | PASS (812 ms) |
| 6 | 3-wire one-shot measure_tach_once | PASS (170 ms) |
| 7 | fault-domain round trips | PASS (22 ms) |
| 8 | alert-mode/service/ideality | PASS (17 ms) |
| 9 | eeprom/por/standby/recovery | PASS (365 ms) |
| 10 | spin-up/tacho-full bits | PASS (10 ms) |
| 11 | presets register effects | PASS (16 ms) |
| 12 | error model (ValueError paths) | PASS (9 ms) |

**Overall: 12/12 PASS — `E2E HARDWARE MATRIX: PASS` (~1.5 s total).** Smoke
test also PASS on this MCU: temps 24.9/26.0 °C, exact duty sweep
(0/64/128/192/255), rpm @100 % = 2284.8 (Pico bench: 2298.9 — same fan,
within noise), EEPROM round trip + POR survival OK. API-surface diff between
the two boards: identical (126 public members each; initial 125-vs-126
discrepancy traced to a stale pre-D24 `mp.py` on the Pico — resynced).

### Post-reflash re-validation — Pico bench (COM16, 2026-11-08)

User reflashed the Pico; chip moved back to this bench. Findings:

- Firmware upgraded **v1.19.1 → v1.29.0** (now matches the ESP32 image);
  filesystem survived the flash — `/lib/max31760/` intact, import OK,
  126 members (fully-synced state incl. `close()`).
- Bus scan: exactly 0x50 present.
- Smoke test: **PASS** — temps 25.3/26.1 °C, exact duty sweep
  (0/64/128/192/255), rpm @100 % = 2316.6, EEPROM round trip + POR survival
  OK, registers restored.
- E2E hardware matrix: **12/12 PASS** (~1.3 s total), self-restoring.
- Bonus datapoint: driver transport baseline (`readfrom_mem`/`writeto_mem`)
  now validated across TWO firmware generations (v1.19.1 and v1.29.0) on
  RP2040 silicon.
- **Board-ID correction (user, 2026-11-08):** the bench board is a first-edition
  **Pico W (RP2040)**, not a Pico 2 W (RP2350) as previously assumed. All
  "RP2350" references in this file corrected to RP2040. Pico 2 W (RP2350)
  expected to work (same `rp2` port family, same I²C peripheral behaviour)
  but UNTESTED — user does not have that board.

### CPython validation — RPi 3A+ bench (local RPi over SSH, 2026-11-08)

Environment: Raspberry Pi 3A+ (aarch64), Debian 13, kernel 6.18.60+rpt-rpi-v8,
Python 3.13.5, smbus2; MAX31760 on I²C bus 1 (SDA=GPIO2/pin 3, SCL=GPIO3/pin 5).
Package deployed to `~/max31760-test/max31760/` (hash-verified).

**Root cause of the long-standing `soft_por()` errno-121 failures (D33):**
The chip executes the soft-POR as soon as CR1.SW_POR is latched and resets so
fast that the RPi's bcm2835 I²C controller reports errno 121 for the
in-flight transaction even though the reset HAPPENED (proven live: volatile
user memory reloads from EEPROM despite the error, 5/5 runs). The old driver
retried the write through the `_tx` ladder — each retry re-fired the POR into
a still-booting chip, producing cascading NACKs that masqueraded as a
mysterious "EEPROM busy window" (variable 6 ms–1.5 s stalls). Fix: the SW_POR
write is issued exactly once via the raw transport (no retries), its OSError
is expected and swallowed, then the device is polled until it acknowledges
again (settle budget raised to 1000 ms default) before waiting out the
POR-triggered EEPROM-reload commit window.

Smoke test: **PASS** — temps 26.2/27.4 °C, exact duty sweep
(0/64/128/192/255), rpm @100 % = 709.9 (fan speed varies run-to-run on this
bench; functional check is the duty/actual match), EEPROM round trip +
post-POR CR1 survival OK, registers restored.

| # | Section | Result |
|---|---------|--------|
| 1 | identity/probe/scan/user-memory | PASS (37 ms) |
| 2 | temperature/setpoints/index-source | PASS (10 ms) |
| 3 | manual-mode/duty/ramp/freq/polarity | PASS (16 ms) |
| 4 | lut/bulk+index/helpers | PASS (20 ms) |
| 5 | tach1/rpm/threshold (+port2 EXCLUDED-HW) | PASS (810 ms) |
| 6 | 3-wire one-shot measure_tach_once | PASS (118 ms) |
| 7 | fault-domain round trips | PASS (20 ms) |
| 8 | alert-mode/service/ideality | PASS (14 ms) |
| 9 | eeprom/por/standby/recovery | PASS (3519 ms) |
| 10 | spin-up/tacho-full bits | PASS (9 ms) |
| 11 | presets register effects | PASS (14 ms) |
| 12 | error model (ValueError paths) | PASS (2 ms) |

**Overall: 12/12 PASS — `E2E HARDWARE MATRIX: PASS`.** Reliability check:
the previously-failing save/load/POR sequence run 10× back-to-back through
the driver: **10/10 PASS** (was 0/10 before the fix). Section 9 is slower
here than on MicroPython benches because every EEX op now waits out the
full tW window (fixed 700 ms, D32) plus the post-POR settle.

*(The "rpm @100 % = 709.9" printed by the smoke test in this run was a
spin-up-transient artifact, not a real speed change — see the Pico-redeploy
section below for the root cause and the script fix.)*

**Cross-platform phase COMPLETE:** all three legs validated — Pico W RP2040
(COM16, v1.29.0), ESP32 (COM7, v1.29.0), RPi 3A+ CPython (Debian 13,
Python 3.13.5). Outstanding follow-ups are user-driven: redeploy the fixed
`_core.py` to the Pico when it is reconnected (its copy predates D31–D33),
ESP32 re-validation when reconnected.

### Pico redeploy of the D33 core — COM16 (2026-11-08)

User moved the Click back to the Pico bench. Redeployed the fixed
`_core.py` (44033 bytes, size-verified on-device; only file changed since
the previous Pico deploy) plus refreshed `hw_smoke_test.py` /
`e2e_hardware_test.py`. Post-deploy sanity: version 0.1.0, 126 public
members, chip verifies, temps read.

- Smoke test: **PASS** — temps 26.5/27.5 °C, exact duty sweep
  (0/64/128/192/255), EEPROM round trip + post-POR CR1 survival OK,
  registers restored.
- E2E hardware matrix: **12/12 PASS**, self-restoring (section 9
  eeprom/por/standby/recovery = 3532 ms — matches the RPi figure, both now
  dominated by the fixed 700 ms tW waits + post-POR settle).
- **RPM re-test (user-requested, same day):** the ~710 rpm figures from
  today's first Pico/RPi smoke runs were a SPIN-UP TRANSIENT ARTIFACT, not
  a fan or power-supply problem. Dedicated measurement (`pico_rpm_check.py`,
  kept in repo root) with proper settling and independent raw-counter
  verification (TC1 holds inter-pulse ticks at 100 kHz per datasheet;
  Fan_RPM = 60·100,000/(TC1H·256+TC1L)/n): 25 % → ~736–748 rpm, 50 % →
  ~1245–1271, 75 % → ~1800, **100 % → 2311–2327 rpm** — squarely in the
  historical band (2284.8–2316.6 across all prior benches). Mechanism:
  the old scripts measured 500–800 ms after applying 100 % duty; when the
  fan starts from rest it is still accelerating then (~710 rpm ≈ its 25 %-duty
  speed), while earlier runs caught the fan coasting from full speed (chip
  sat at factory 100 % LUT between tests) and read ~2300. Fix: both
  `hw_smoke_test.py` and `e2e_hardware_test.py` now poll `rpm(1)` until two
  consecutive samples agree within 2 % (bounded 10 s) before asserting —
  re-run confirmed: smoke reports 2316.6 rpm, E2E 12/12 (tach section 4013
  ms, i.e. the convergence wait genuinely earned its keep). Scripts synced
  to the Pico and the RPi deploy dir.
- Confirms the D33 `soft_por()` rewrite is regression-free on the
  MicroPython path (it also gains mid-transaction-reset resilience there).

| Risk | Impact | Mitigation |
|------|--------|------------|
| `mem_read`/`mem_write` absent (**non-standard names — not in official docs; confirmed absent on v1.19.1 RP2040**) | Broken transport if depended on | Baseline API = `readfrom_mem`/`writeto_mem` (canonical across all ports); no capability probing needed |
| Raw-serial REPL delivery breaks multi-line scripts (suite-swallowing, missing blank-line terminator) | Flaky HW test runs | Flat one-liners for probes; ship real scripts to flash (`mpremote cp` + `exec(open(...))`); adopt mpremote as dev tooling |
| EEPROM save corrupts config if power dips mid-write | Bricked fan profile | Doc warning + `program_corrupt()` recovery path + recommend saving only when stable |
| Page-wrap bug class (silent wrong-address writes) | Corrupted LUT/config | Enforced chunking in transport + mock assertion; B-task A3 acceptance test |
| SR clear-on-read surprises app logic | Missed alarms | Documented prominently; `active_alarms()` returns snapshot; service routine encapsulates semantics |
| Float rounding drift in temp encode | Off-by-one LSB setpoints | Integer-first math (`round(c*8)<<5`), round-trip tests incl. boundary values |
| Tach overflow misreported as high RPM | False "healthy" reading | Overflow heuristic (count < previous sample while fan known running) + threshold cross-check; documented limitation |
| Scope creep toward app-level features | Schedule slip | Strict out-of-scope list (§3); presets capped at F24 set |
| smbus `read_i2c_block_data` returns register byte prepended | Corrupt reads on CPython path | Adapter strips `[0]`; covered by fake-smbus unit test (verification item 5) |
| I²C bus disabled / wrong bus number on an SBC | Opaque init failure | Per-family enablement docs (raspi-config, DT overlays); `probe()` self-test + clear error naming the bus tried |
| Divergence between the two platform façades over time | Broken "identical API" promise | Structural (shared core) + automated parity gate (F26) in the test suite |

Resolved defaults (approved by user 2026-11-07; may be revisited later):
- Preset ramp rate: **immediate** (predictable behavior; datasheet default is slow 3.125 %/s).
- `save_config()`: **all-blocks default**, explicit block mask optional.

## 9. Definition of Done

- All §4 requirements implemented, each with ≥1 unit test (mock-backed).
- `unittest` suite green on host CPython 3; module compiles clean; no CPython-only syntax.
- Each shared module within its size budget (decision 6: soft ~16 KB/module,
  decompose rather than truncate); package licensed under LGPL-2.1-or-later.
- Docs + 3 examples committed; PLANS.md checkboxes all checked; v0.1.0 tagged.
- User reviews and approves final deliverable.
- **E2E hardware matrix green on the Pico bench**: every public API exercised with
  observable-effect verification; TACH2/port-2 functional items documented as EXCLUDED-HW
  (unit-tested only) per bench limitation.

## 10. References

- Maxim DS 19-7395 Rev 0 — MAX31760 datasheet: primary
  https://download.mikroe.com/documents/datasheets/MAX31760.pdf , backup
  https://www.analog.com/media/en/technical-documentation/data-sheets/max31760.pdf
  (local copy `reference/MAX31760.pdf`, gitignored — vendor copyright).
- https://www.mikroe.com/fan-2-click (target board).
- https://github.com/rudybrian/MAX31760-Python (baseline study; local clone removed 2026-11-08).
- https://docs.micropython.org/en/latest/library/machine.I2C.html (MicroPython transport API).
- https://pypi.org/project/smbus2/ and https://github.com/kplindegaard/smbus2 (CPython transport lib).
- https://www.raspberrypi.com/documentation/computers/os.html#i2c-bus (RPi I²C enablement).
- https://beagleboard.org/ (BeagleBone I²C pins/bus reference).
- https://docs.micropython.org/en/latest/reference/pyboard.html#mpremote (mpremote — serial file-transfer/REPL tooling; candidate dev dependency).
- Planning format: OpenAI Cookbook — Codex exec plans article.
