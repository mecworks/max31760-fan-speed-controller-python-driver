# PLANS_0.1.1.md — MAX31760 Driver v0.1.1 Refactor (Effective-Python Review Remediation)

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`,
`Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.
The repository root `PLANS.md` (the v0.1.0 plan) is checked in; this document must be
maintained in accordance with it, and it inherits PLANS.md's standing orders: keep
PLANS.md + SUMMARY.md current at all times, check off milestones/tasks as confirmed, and
exercise ALL public APIs end-to-end on the real Pico bench — EXCEPTION: fan port 2 /
TACH2 functional tests (no second fan on bench; those stay unit-tested against mocks
only and are marked EXCLUDED-HW). Planning format follows the OpenAI Cookbook article
"Using PLANS.md for multi-hour problem solving" (codex_exec_plans), referenced by
PLANS.md §10.

## Purpose / Big Picture

After this change, the MAX31760 driver ships as v0.1.1: the same hardware behavior and
byte-identical wire protocol as the frozen, hardware-verified v0.1.0, wrapped in a
cleaner, single-source-of-truth code base. Concretely, a developer who picks up v0.1.1
gets: one canonical register-map module (`max31760/_regs.py`) instead of two drifting
constant blocks in `_core.py`; a uniform public API where every piece of device state is
a property and every verb is an action (`dev.ramp_rate = RAMP_IMMEDIATE`,
`dev.manual = True`, `dev.service_alert()`); `with MAX31760(...) as dev:` resource
handling; a `measure_tach_once()` that raises `TimeoutError` instead of smuggling a
stale count back; an honest package facade whose documented exports actually exist; and
modern, MicroPython-safe idioms (f-strings, zero-arg `super()`, unpacking helpers,
conservative type annotations). Nothing about what the chip sees on the bus changes —
the existing constant-pinning tests prove that — so the v0.1.0 hardware verification
remains valid, and the E2E matrix is re-run as confirmation rather than as discovery.

How to see it working: from the repo root, `python -m unittest discover tests` reports
more than the 134-test v0.1.0 baseline passing (new coverage for every changed
behavior); `python tools/api_coverage.py` prints `RESULT: PASS`;
`python tests/lint_subset.py` prints `RESULT: PASS` for eight shared files (seven plus
the new `_regs.py`); `python -m compileall max31760` exits clean; and on the Pico W
bench, `hw_smoke_test.py` and `e2e_hardware_test.py` reproduce the 12/12 E2E matrix
result from v0.1.0.

## Progress

- [x] (2026-11-21 11:41Z) Plan authored: every claim in CODE_REVIEW_FOR_0.1.1.md verified against the code base (verdicts in Surprises & Discoveries); baseline gates captured (134 tests OK, 124 public members PASS, lint PASS, compileall clean).
- [x] (2026-11-21) User review complete: D-04 (primary property/verb variant) and D-10 APPROVED; branch name fixed to `v0.1.1-refactor` (no `chatbox/` prefix); D-15 adopted (no backwards compatibility, no deprecation warnings — pre-1.0 release); hardware strategy set: Pico W performs ALL initial on-hardware testing, ESP32-S3 and RPi 3A+ legs deferred until Pico work + testing is complete.
- [x] (2026-11-21) Go-ahead received; execution started (M0). Execution directives: no co-author trailers; merge after all platforms validated; RPi 3A+ at `marc@192.168.1.225` (SSH keys); single MAX31760 chip relocated between benches (sequential validation).
- [x] (2026-11-21) M0 COMPLETE: branch `v0.1.1-refactor` created from `main` @ 09f2db5; plan doc committed (ef8e4c9, incl. `.gitignore` pattern fix); all four host gates re-confirmed green ON THE BRANCH (transcript in Artifacts and Notes); RPi 3A+ key-auth probe OK (hostname `fanspeedcontroller`, Python 3.13.5, `~/max31760-test/` pre-populated with the v0.1.0 deployment).
- [x] (2026-11-21) M1 COMPLETE (commit a186994): `max31760/_regs.py` created as leaf module (zero package imports); `_core.py` shrunk by ~270 lines (constants region + six helpers moved out; NOTE comment and mid-file `from ._faults import FaultMixin` deleted, import moved to top); `_faults.py`/`_lut.py` now import from `_regs`; lint gate covers 8 files; new `TestRegsModule` (4 tests). Gates green: **138 tests OK** (134 baseline UNMODIFIED + 4 new — proves zero value drift), api-coverage PASS (124 members), lint PASS ×8, compileall clean; import-order independence verified (`import max31760._faults` and `import max31760._lut` directly now succeed without importing `_core` first).
- [x] (2026-11-21) M2 COMPLETE (commit 5490987): `__enter__`/`__exit__` (never suppresses) + no-op core `close()` (facades override); `__repr__` → `<MAX31760 addr=0xNN>`; zero-arg `super()` in cp/mp; `(object)` dropped from all four classes; `_SmbusCompat.read_i2c_block_data` raises OSError on short legacy payloads; `soft_por` uses named `POR_SETTLE_MS`. New tests: `TestContextManager` (4), `TestRepr` (1), `TestSmbusCompatContract` (2); `POR_SETTLE_MS` pinned in `TestConstants`. Gates green: **145 tests OK**, api-coverage PASS (**125** public members — `close` added to core surface, covered), lint PASS ×8, compileall clean.
- [x] (2026-11-21) M3 COMPLETE: `measure_tach_once` raises TimeoutError when the count never changes (PSEN still cleared via finally); `get_pwm_freq_hz` raises ValueError on unknown DRV combo instead of guessing 33 Hz; keyword-only fences (`*, timeout_ms=` / `*, settle_ms=`) on wait_for_duty, measure_tach_once, save_config, load_config, recover_from_corruption, soft_por; internal call site fixed (`recover_from_corruption → save_config(..., timeout_ms=timeout_ms)`). Red→green demonstrated (transcript in Artifacts and Notes). Gates green: **148 tests OK**, api-coverage PASS (125), lint PASS ×8, compileall clean.
- [x] (2026-11-21) M4 COMPLETE: root `__init__.py` now declares explicit `__all__ = ["__version__"]` with an honest docstring (no eager submodule imports); mp.py/cp.py re-export the full public surface (113 names from `_regs` + MAX31760 + 2 LUT helpers = 116 per facade) with byte-identical `__all__` lists (generated cp.py from mp.py; parity test enforces identity); the lying class-body comment in `_core.py` fixed to state what is actually true. New `TestFacadeExports` (3 tests). Gates green: **151 tests OK**, api-coverage PASS (125), lint PASS ×8, compileall clean.
- [ ] M5: accessor unification (properties for state, verbs for actions) per approved D-04; update tests, examples, scripts, docs.
- [ ] M6: idiom sweep — f-string migration (with lint-gate update), `_u16_get`/`_u16_set` helpers, `zip`/`bisect` in `build_lut_curve`.
- [ ] M7: conservative built-in-type annotations on public signatures (with lint-gate relaxation); board-verified on Pico W.
- [ ] M8: docstring surgery — per-method `Raises:` lines, bulleted caveats, bench narrative carved into `NOTES/`, legend pointer for F#/D# IDs, ALL-CAPS demotion, constructor docstrings.
- [ ] M9: release — version bump 0.1.0 → 0.1.1, CHANGELOG entry, full host gates, hardware E2E Phase H1 (Pico W only), deferred Phase H2 (ESP32-S3 + RPi 3A+), merge to `main`, tag `v0.1.1`.

## Surprises & Discoveries

Documented during validation of the review report (2026-11-21) and to be appended as
implementation proceeds.

- Observation: every one of the 15 prioritized backlog items in CODE_REVIEW_FOR_0.1.1.md was verified TRUE against the code base; none was false or materially overstated.
Evidence: duplicate CR2/SR/EEX constant blocks at `_core.py` lines ~87–94 vs ~121–126, ~110–118 vs ~159–167, ~144–149 vs ~173–181; `CR2_FS_ENABLE` (line 91) and `CR2_FSENABLE` (line 124) both define bit 0x08 and neither is referenced anywhere (grep: definitions only); mid-file `from ._faults import FaultMixin` with the ordering NOTE at ~line 289; four coexisting accessor conventions confirmed by reading `_core.py`/`_faults.py` and the test suite; no `__enter__`/`__exit__`/`__repr__` anywhere (grep); the class-body comment "Public constants (usable as MAX31760.XXX; also exported by mp/cp)" contradicted by both entry modules' `__all__ = ["MAX31760", "build_lut_curve", "lut_index_for_temp"]`; `measure_tach_once` returns the pre-stretch count on timeout (lines ~786–801) and the existing test pins that stale behavior; `get_pwm_freq_hz` falls back to 33 Hz silently; `%`-formatting throughout; two-arg `super(MAX31760, self)` in `cp.py:20` and `mp.py:21`; `(object)` bases in four places (the review cited three); seven occurrences of `(raw[0] << 8) | raw[1]` (lines 442, 448, 486, 706, 725, 788, 797); `range(len(pts))` index loop in `_lut.py`; `self._wait_eeprom_ready(2000)` magic number in `soft_por`; `_SmbusCompat.read_i2c_block_data` silently truncates short payloads; constructors lack docstrings; ALL-CAPS emphasis inflation and dated bench narrative spliced into behavioral prose confirmed verbatim.
- Observation: the review's line-number citations are approximate but substantively correct (e.g., the second SR block spans ~159–167, not "~159–160"; the second CR2 block is a PARTIAL duplicate — it omits `CR2_FFMODE` and `CR2_DFC` — so "verbatim re-definition" applies to the five bits listed in the report's table, not the whole block). Values are identical today, so this is a maintainability hazard, not a live bug.
- Observation: `tests/lint_subset.py` ACTIVELY BANS f-strings (JoinedStr nodes) and ALL type annotations in the seven shared modules. Backlog items #8 (f-string sweep) and #11 (annotations) therefore cannot land without amending this gate; the review did not mention the interaction. The gate's own header notes `@property` IS allowed on MicroPython, which independently supports the property end-game in D-04.
- Observation: `tools/api_coverage.py` (CI gate) asserts every public member of the core class is referenced by name in `tests/test_max31760.py`. This is a free safety net for the M5 rename: any new or renamed public member that lacks test coverage fails CI. Baseline: 124 public members, PASS.
- Observation: `TestApiParity.test_module_exports_match` asserts `mp.__all__ == cp.__all__` and object identity of the shared exports. Any facade-export change (M4) must extend BOTH lists identically or the parity gate breaks.
- Observation: making `timeout_ms` keyword-only (M3) breaks existing positional call sites: `tests/test_max31760.py` calls `dev.wait_for_duty(50.0, 30)` and `dev.wait_for_duty(50.0, -1)` positionally; `examples/` already uses the `timeout_ms=` keyword form. Internal call sites `soft_por → self._wait_eeprom_ready(2000)` and `recover_from_corruption → self.save_config(EEX_ALL_BLOCKS, timeout_ms)` also pass optionals positionally.
  - CORRECTION (M3, 2026-11-21): the positional test call sites live inside `assertRaises` argument lists (`self.assertRaises(TimeoutError, dev.wait_for_duty, 50.0, 30)`), which a naive regex for direct calls misses — three total in `TestRampRate` (incl. `101.0, 100`). All converted to keyword form; no other hidden positional callers exist repo-wide (verified by targeted grep).
- Observation: platform claims verified against internet references: MicroPython added f-string support (PEP 498) in v1.17 (SourceForge v1.17 release notes: "adds support for f-strings (PEP-498), with a few limitations"); the project's stated baseline is v1.19.1 RP2040, so f-strings are safe. Zero-arg `super()`, `@property`, and simple built-in-name annotations are standard MicroPython features; container-generic annotations (`list[int]`) and `from __future__ import annotations` are NOT supported and remain banned.
- Observation: `get_pwm_freq_hz`'s silent-33-Hz fallback is UNREACHABLE today: the DRV field is exactly 2 bits and all four encodings exist, so the masked value always matches. The fix (raise instead) is defensive — it converts a latent silent assumption into a loud failure if the field is ever widened or a constant typos. Characterized as such in D-06.

- Observation (2026-11-21, user directives incorporated as Revision 3): (a) NO co-author trailers on any commit; (b) merge + tag only after all three platforms validated (option a elected); (c) RPi 3A+ reachable at `marc@192.168.1.225` via SSH key auth; (d) exactly ONE MAX31760 module exists — it is physically relocated between benches, so hardware validation is strictly sequential (Pico W → ESP32-S3 → RPi 3A+), never concurrent.

## Decision Log

Recorded as made while authoring/executing this plan. Entries marked PROPOSED await
user sign-off during plan review; everything else is binding for execution.

- Decision: D-01 — Adopt all 15 prioritized backlog items from CODE_REVIEW_FOR_0.1.1.md; each was validated as a real problem (see Surprises & Discoveries).
Rationale: all fifteen correspond to verified defects or hazards; none is speculative.
Date/Author: 2026-11-21, Chatbox agent (validation pass).

- Decision: D-02 — Canonical constant naming in the new `_regs.py`: keep the FIRST CR2 block (it is the complete one, including `CR2_FFMODE` and `CR2_DFC`) and DELETE the second "CR2 remaining control bits" block; the full-speed force bit keeps the name `CR2_FSENABLE` (house style favors compact abbreviations: STBY, ALERTS, SPEN, FFMODE, RDPS, FSST, DFC) and `CR2_FS_ENABLE` is deleted. Keep the FIRST SR block (richer comments) and delete the second. Keep `EEX_BLOCK_*`, `EEX_ALL_BLOCKS`, `EEX_LOAD_BIT`, `EEX_SAVE_ALL`, `EEX_LOAD_ALL`; delete the unused `EEX_BLK_*` aliases. Keep `MASK_ALARM_FIELD` and `MASK_RESERVED_HI`; delete the six individual `MASK_TACH1A`…`MASK_LHA` bits (referenced nowhere; callers can compose masks from the `SR_*` constants, whose bit positions match the MASK register one-to-one).
Rationale: single source of truth with one name per bit; every survivor is consumed by driver code or pinned by tests (`EEX_SAVE_ALL`/`EEX_LOAD_ALL`/`MASK_RESERVED_HI` are pinned by `TestConstants.test_eex_constants` and must survive).
Date/Author: 2026-11-21, Chatbox agent.

- Decision: D-03 — Extract `max31760/_regs.py` as a LEAF module (imports nothing from the package) holding: the register map, all bit-field constants, mode/index/frequency encodings, physical constants (`TEMP_LSB_C`, `TACH_REF_HZ`, `TACH_AVG_PULSES`, `PAGE_SIZE`, `LUT_LEN`, `USER_LEN`, `ADDR_MIN/MAX`, `RETRY_DELAYS_MS`, `EEPROM_WAIT_MS`, new `POR_SETTLE_MS`), and the six fixed-point helpers (`temp_to_raw16`, `raw16_to_temp`, `duty_to_pct`, `pct_to_duty`, `rpm_from_count`, `count_from_rpm`). `_core.py` imports every name it needs from `_regs` at the TOP of the file (explicit import list, no star imports), which means every existing `from max31760._core import ...` statement in tests keeps working unchanged. `_faults.py` and `_lut.py` switch their imports to `_regs`. The mid-file NOTE comment and the ordering-dependent `from ._faults import FaultMixin` disappear; that import moves to the top of `_core.py`. Resulting dependency graph: `_tables ← _regs ← {_faults, _lut} ← _core ← {cp, mp}` — acyclic by construction. `_regs.py` is added to the `SHARED` list in `tests/lint_subset.py`.
Rationale: Effective Python Item 88's structural cure (shared constants in a leaf module) eliminates the circular import permanently instead of relying on ordering luck; re-exporting through `_core` minimizes churn in the 134-test suite.
Date/Author: 2026-11-21, Chatbox agent.

- Decision: D-04 (APPROVED 2026-11-21 by user — primary property/verb variant) — Accessor end-game: PROPERTIES FOR ALL REGISTER-BACKED STATE, VERBS RESERVED FOR ACTIONS. Every getter that performs I/O becomes a read side of a property (I/O inside a property is legitimate for hardware drivers, cf. `serial.Serial.in_waiting`; the class docstring states this once). Setters become the write side. The toggle zoo collapses to boolean properties assigned directly. `enter_standby`/`exit_standby`/`standby_active` collapse into one read/write `standby` property (they manipulate a single bit; the asymmetry was nominal). Percent-convenience writers `set_duty_pct` and `set_ffdc_pct` REMAIN verbs (they convert units; the property holds the raw value). Destructive-read primitives (`status_raw`, `active_alarms`, `remote_diode_fault`, `eeprom_corrupt`) KEEP their verb forms — the verb shape advertises the latch-consuming side effect. Old → new mapping (left = removed in 0.1.1, right = added):

    local_high_c            <- get_local_high / set_local_high
    remote_high_c           <- get_remote_high / set_remote_high
    local_overtemp_c        <- get_local_overtemp / set_local_overtemp
    remote_overtemp_c       <- get_remote_overtemp / set_remote_overtemp
    index_source            <- get_index_source / set_index_source
    hysteresis_c            <- get_hysteresis_c / set_hysteresis_c
    pwm_freq_hz             <- get_pwm_freq_hz / set_pwm_freq_hz
    pwm_polarity            <- get_pwm_polarity / set_pwm_polarity
    ramp_rate               <- get_ramp_rate / set_ramp_rate
    tach_threshold          <- get_tach_threshold / set_tach_threshold
    ff_dc_raw               <- get_ffdc_raw / set_ffdc_raw
    duty_cmd_raw            <- get_duty_cmd_raw / set_duty_raw
    actual_duty_raw         <- get_actual_duty_raw            (RO)
    actual_duty_pct         <- get_actual_duty_pct            (RO)
    ideality_factor_index   <- get_ideality_factor_index / set_ideality_factor_index
    ideality_factor         <- get_ideality_factor            (RO)
    alert_mask              <- get_alert_mask / set_alert_mask
    ff_mode                 <- get_ff_mode / set_ff_mode
    manual                  <- manual_enabled / manual_enable(on)
    tach1_enabled           <- tach1_enabled() / tach1_enable(on)
    tach2_enabled           <- tach2_enabled() / tach2_enable(on)
    spin_up_enabled         <- spin_up_enabled() / spin_up_enable(on)
    pulse_stretch_enabled   <- pulse_stretch_enabled() / pulse_stretch_enable(on)
    tacho_full_enabled      <- tacho_full_enabled() / tacho_full_enable(on)
    rd_mode                 <- rd_mode_enabled / set_rd_mode(enabled)
    rd_polarity             <- get_rd_polarity / set_rd_polarity(high_means_spinning)
    ff_zero_detection       <- ff_zero_detection / set_ff_zero_detection(on)
    standby                 <- standby_active / enter_standby / exit_standby
    lut                     <- lut_get / lut_set              (list of 48 duty raws)

  Surviving verbs (unchanged names): `service_alert`, `clear_fan_fail`, `set_ffdc_pct`,
  `set_duty_pct`, `set_ideality_factor`, `measure_tach_once`, `wait_for_duty`, `rpm`,
  `save_config`, `load_config`, `recover_from_corruption`, `soft_por`,
  `user_memory_get/set/read_all/write_all`, `configure_4wire_fan`,
  `configure_3wire_supply_modulation`, `configure_two_fans`, `status_raw`,
  `active_alarms`, `remote_diode_fault`, `eeprom_corrupt`, `alert_masked`,
  `clear_alert_mask`, `verify`, `scan`, `probe`, `read_reg`, `write_reg`,
  `lut_get_index`, `lut_set_index`, `close`.
Rationale: the review's recommended end-state; at 0.1.x the rename is nearly free (post-1.0 it would owe the Item 89 deprecation dance); one convention for state removes the per-setting recall cost; the api-coverage gate enforces that every new name gets test coverage. FALLBACK (if the user prefers conservatism): uniform `get_`/`set_` methods, retire the two temperature properties to `get_local_temp_c()`/`get_remote_temp_c()`, normalize the two irregular toggles to `x_enable(x)`/`x_enabled()` — smaller blast radius, weaker consistency. M5 implements the approved primary variant; the documented FALLBACK is retired.
Date/Author: proposed 2026-11-21 by Chatbox agent; approved by user 2026-11-21.

- Decision: D-05 — `status_raw()` and `active_alarms()` KEEP their names (no `drain_status` rename); their docstrings are sharpened in M8 to lead with the destructive-read warning.
Rationale: the review rated the mutual exclusion "acceptable as-is given the hardware constraint"; renaming buys little against the churn, and the latch semantics are hardware-imposed, not API sloppiness.
Date/Author: 2026-11-21, Chatbox agent.

- Decision: D-06 — `get_pwm_freq_hz` RAISES `ValueError` on an unrecognized DRV bit combo instead of silently returning 33 Hz.
Rationale: cross-cutting fail-loud principle; unreachable today (2-bit field, four encodings) but converts a latent silent assumption into a loud failure against future drift.
Date/Author: 2026-11-21, Chatbox agent.

- Decision: D-07 — `measure_tach_once` RAISES `TimeoutError` when the TC count does not change within `timeout_ms`, instead of returning the pre-stretch count. The `finally` clause still clears PSEN.
Rationale: Item 20 — exceptional conditions are raised, not smuggled through the payload band; a stale count indistinguishable from a fresh measurement is worse than an exception. Documented consequence: a stopped fan (count legitimately unchanged) now times out rather than returning 0.
Date/Author: 2026-11-21, Chatbox agent.

- Decision: D-08 — Exception model STAYS on built-ins (`ValueError`/`OSError`/`TimeoutError`); no custom `MAX31760Error` family yet. Per-method `Raises:` documentation is added in M8 to the six timeout/exception-heavy methods.
Rationale: the review's own scoping advice — the built-in mapping is defensible for a hardware driver until this goes to PyPI for third parties, at which point a thin root family inheriting the built-ins can be added without breaking `except OSError` clauses.
Date/Author: 2026-11-21, Chatbox agent.

- Decision: D-09 — Honest facade: `max31760/__init__.py` gains a curated `__all__` exposing the platform-neutral public constants (re-bound from `_core`, which re-exports `_regs`) plus `build_lut_curve`/`lut_index_for_temp` (re-exported once from the package root). Both `cp.py` and `mp.py` gain the SAME extended `__all__` (constants + the two LUT utilities + `MAX31760`), keeping the parity gate green. The lying class-body comment in `_core.py` is corrected to state the real access paths (`MAX31760.RAMP_SLOW` via the class attribute; `max31760.cp.MAX31760` / `max31760.mp.MAX31760` for devices; package-root constants for platform-neutral code).
Rationale: importing `_core` at the package root is platform-neutral (it imports no transport), so `import max31760` costs nothing extra on boards that will import the core transitively anyway; the duplicated LUT re-export promise becomes honest in one place.
Date/Author: 2026-11-21, Chatbox agent.

- Decision: D-10 (APPROVED 2026-11-21 by user) — Branch workflow: create branch `v0.1.1-refactor` from `main` (branch name per user directive; no `chatbox/` prefix); execute M1–M8 entirely on that branch with one commit per milestone (plain commit messages — NO co-author trailers, per user directive 2026-11-21); `main` stays at v0.1.0 throughout; MERGE SCOPE ELECTED BY USER (option a): the merge into `main` and the `v0.1.1` tag happen only AFTER ALL THREE HARDWARE PLATFORMS ARE VALIDATED (Phase H1 Pico W + Phase H2 ESP32-S3 and RPi 3A+).
Rationale: isolates a breaking-API refactor from the frozen release; the merge/tag boundary is the only point at which 0.1.1 becomes visible.
Date/Author: proposed 2026-11-21 by Chatbox agent; approved by user 2026-11-21 (branch name corrected to `v0.1.1-refactor`).

- Decision: D-11 — Type annotations: CONSERVATIVE built-in names only (`int`, `float`, `bytes`, `str`, `bool`) on public method signatures (the boundary, per Item 90's timing strategy). NO `typing` imports, NO container generics (`list[int]`), NO `Optional[...]`, NO `from __future__ import annotations` (unsupported on MicroPython). `tests/lint_subset.py` is amended to ACCEPT `ast.Name` annotations whose id is in that five-name whitelist and to CONTINUE rejecting subscripted annotations, `AnnAssign`, and typing-module imports. Board verification on the Pico W (v1.29.0) precedes promotion: import the package, construct a device, and call annotated methods on-device.
Rationale: simple built-in annotations parse and evaluate harmlessly on MicroPython; the narrower-than-claimed constraint in the review is honored precisely; the lint gate keeps the guarantee machine-checked.
Date/Author: 2026-11-21, Chatbox agent.

- Decision: D-12 — f-string sweep: migrate the ~30 `%`-formatted error messages in shared modules to f-strings; amend `tests/lint_subset.py` to ACCEPT `ast.JoinedStr` nodes. Format specs used are limited to `:d`, `:.3f`, `:.4f`, `:02X` — all supported by MicroPython ≥1.17. Board verification on the Pico W includes triggering one ValueError path on-device to confirm rendering.
Rationale: f-strings are fully supported on the v1.19.1 baseline (verified against the v1.17 release notes); the prior ban was habit codified in the lint gate, not a platform constraint.
Date/Author: 2026-11-21, Chatbox agent.

- Decision: D-13 — Release mechanics: bump `__version__` in `max31760/__init__.py` and `version` in `pyproject.toml` from 0.1.0 to 0.1.1; add a CHANGELOG.md entry that leads with the BREAKING API CHANGES (the D-04 rename table) followed by additions and behavior changes (D-06, D-07, keyword fences).
Rationale: consumers upgrading must see the rename table first; the changelog is the de-facto deprecation notice for a pre-1.0 package.
Date/Author: 2026-11-21, Chatbox agent.

- Decision: D-14 — Keyword fences: `timeout_ms` becomes KEYWORD-ONLY (`*, timeout_ms=...`) on `wait_for_duty`, `measure_tach_once`, `save_config`, `load_config`, and `recover_from_corruption`; `settle_ms` on `soft_por` likewise. All internal call sites pass optionals by keyword. Known positional call sites to fix: two in `tests/test_max31760.py` (`wait_for_duty(50.0, 30)`, `wait_for_duty(50.0, -1)`), `soft_por → self._wait_eeprom_ready(2000)`, `recover_from_corruption → self.save_config(EEX_ALL_BLOCKS, timeout_ms)`.
Rationale: Items 23/25 — locks the interface against a future positional parameter being prepended; cheap insurance on the timeout-heavy methods.
Date/Author: 2026-11-21, Chatbox agent.

- Decision: D-15 — NO backwards compatibility, NO deprecation machinery: this is a pre-1.0 release. Old accessor names simply cease to exist in 0.1.1 — no alias modules, no `DeprecationWarning`s, no transitional dual-API window. The CHANGELOG breaking-changes table (D-13) is the sole migration notice.
Rationale: user directive 2026-11-21. Effective Python Item 89's deprecation dance applies at 1.0+; carrying both conventions through 0.1.1 would double the surface this refactor exists to shrink.
Date/Author: 2026-11-21, user directive recorded by Chatbox agent.

## Outcomes & Retrospective

(Pending — written at completion of M9: what was achieved against the Purpose, what
remains, lessons learned, and the exact final gate transcripts.)

## Context and Orientation

The repository is a dual-platform Python driver for the Maxim MAX31760 precision
fan-speed controller (I2C, 7-bit addresses 0x50–0x57). It runs unmodified on
MicroPython boards (RPi Pico RP2040/RP2350, ESP32-class) and on CPython/Linux SBCs
(Raspberry Pi, BeagleBone). Terms used in this plan, defined plainly:

- FACADE: the two thin platform entry points `max31760/cp.py` (wraps an SMBus/I2C bus
  via smbus2) and `max31760/mp.py` (wraps a caller-built `machine.I2C`). Each subclasses
  the shared core class and differs only in its constructor.
- CORE: `max31760/_core.py` — owns all protocol knowledge: register map, page-safe
  writes (writes chunked so they never cross an 8-byte page row, because the chip wraps
  the pointer WITHIN the page otherwise), fixed-point math, retry ladder, error model.
- TRANSPORT CONTRACT: duck-typed object providing `burst_read(reg, n) -> bytes`,
  `burst_write(reg, data)`, `probe() -> bool`, `scan() -> iterable`, `delay_ms(ms)`,
  optional `close()`. Injected in tests via mocks — this seam is why the whole suite
  runs on a laptop with no hardware.
- ERROR MODEL (F23): `ValueError` for bad arguments/bounds; `OSError` for bus/NACK
  failures after the escalating retry ladder; `TimeoutError` for EEPROM-busy overruns.
  Never silent failures.
- LATCH: the status register SR (0x5A) CLEARS its alarm bits when read; a persisting
  fault re-latches at the next detection. Two public methods consume it mutually
  exclusively.
- ACK-POLL: probing the device address to learn whether it is busy; proven unreliable
  on live silicon in both directions, hence the fixed-delay EEPROM waits.
- PARITY GATE: `TestApiParity` in the test suite — asserts both facades expose an
  IDENTICAL public surface (methods, signatures, constants, properties).
- API-COVERAGE GATE: `tools/api_coverage.py` — asserts every public member of the core
  class is referenced by name somewhere in `tests/test_max31760.py`.
- LINT GATE: `tests/lint_subset.py` — AST check that shared modules contain no
  CPython-only constructs (currently: no bad imports, no annotations, no f-strings,
  no async/yield-from/walrus; `@property` allowed).
- EXCLUDED-HW: bench tests impossible on the single-fan bench (TACH2/port-2
  functional); covered by mock unit tests only, per PLANS.md standing orders.
- E2E MATRIX: the 12-section end-to-end hardware test encoded in
  `examples/e2e_hardware_test.py` (plus `examples/hw_smoke_test.py`), historically
  12/12 PASS on Pico W, ESP32, and RPi 3A+.

Current state (v0.1.0 FROZEN, 2026-11-08): Phase A/B/C complete and hardware-verified;
cross-platform phase complete (RPi 3A+ CPython over SSH: smoke + E2E 12/12; Pico W
RP2040 @ COM16 v1.29.0: revalidated; ESP32 @ COM7 v1.29.0: PASS). Host suite: 134
unit tests green. Benches: Pico W on USB-serial COM16 (mpremote), ESP32-S3 on COM7
(mpremote), RPi 3A+ at `marc@192.168.1.225` (SSH key auth, CPython + smbus2;
`clk_tout_ms=700` must be re-set after reboot). HARDWARE CONSTRAINT (user directive
2026-11-21): exactly ONE MAX31760 module exists — it is physically relocated between
benches, so hardware validation is strictly sequential (Pico W first, then ESP32-S3,
then RPi 3A+), never concurrent. Hardware scripts live in `scripts/{pico,esp32,rpi}/` (inventory
and how-to-run in `scripts/README.md`); `tests/` remains host-runnable unit tests only.
CI (`.github/workflows/ci.yml`) runs on push to `main` and on PRs, across Python
3.11–3.15: unittest discover, api-coverage gate, lint gate, compileall.

File map relevant to this plan: `max31760/_core.py` (1085 lines; constants region
lines ~17–190, fixed-point helpers ~201–270, mid-file faults import ~285–290, device
class ~292 onward), `max31760/_faults.py` (FaultMixin; imports 13 names from `_core`),
`max31760/_lut.py` (LUT geometry + `build_lut_curve`; imports `LUT_LEN`, `pct_to_duty`
from `_core`), `max31760/_tables.py` (pure data), `max31760/_transport_cp.py`
(CPython adapter + `_SmbusCompat`), `max31760/_transport_mp.py` (MicroPython adapter),
`max31760/cp.py`, `max31760/mp.py`, `max31760/__init__.py` (version only, no `__all__`),
`tests/test_max31760.py` (1398 lines, 134 tests), `tests/mock_i2c.py` (MockChip,
MockTransport, FlakyTransport), `tests/fake_smbus.py` (FakeSMBus),
`tests/lint_subset.py`, `tools/api_coverage.py`, `examples/*.py` (six demo/E2E files
that exercise the public API), `scripts/**` (bench scripts, several of which call the
public API), `PLANS.md` (v0.1.0 plan: feature IDs F1–F26, decisions D1–D33, test
coverage per feature), `SUMMARY.md` (handoff companion), `CHANGELOG.md`,
`CODE_REVIEW_FOR_0.1.1.md` (the report this plan remediates).

Existing test coverage inherited from PLANS.md (feature ID → test class in
`tests/test_max31760.py`): F1 init/self-test → `TestInitSelfTest`; F2 temperatures →
`TestTemperatures`; F3 setpoints → `TestSetpoints`; F4/F5 LUT → `TestLutAccess`,
`TestLutIndexForTemp`, `TestBuildLutCurve`; F6–F8 manual/auto/PWM → `TestManualMode`,
`TestAutoConfig`, `TestPwmConfig`; F9 ramp/wait → `TestRampRate`; F10/F15 3-wire
assists → `TestThreeWireAssist`; F11/F12 tach → `TestTachometer`; F13/F14/F16/F17
faults → `TestFaultHandling`; F18/F19 ALERT/ideality → `TestAlertAndIdeality`;
F20/F21 EEPROM lifecycle → `TestEepromLifecycle`; F22 raw access/page-safety/retries →
`TestPageSafeWrite`, `TestRetryAndProbe`; F24 presets → `TestPresets`; F25 CP stack →
`TestCPAdapter`, `TestCPIntegration`; F26 parity → `TestApiParity`; math/constants →
`TestTempMath`, `TestDutyMath`, `TestRpmMath`, `TestConstants`,
`TestConstructorBounds`. This plan ADDS coverage where behavior changes (M2–M4, M6)
and MIGRATES existing coverage wholesale where names change (M5) — the migrated tests
carry the same assertions, so no PLANS.md coverage is lost.

## Plan of Work

Nine milestones, executed strictly in order on the branch from D-10. M1 comes first
because it reshapes the constant region that M3, M5, and M8 all touch (doing it first
avoids editing the same lines twice, per the review's sequencing note). M2–M4 are
independent quick wins batched by risk. M5 is the large breaking change and is gated
on D-04 sign-off. M6–M8 are polish layers that ride on the stabilized surface. M9 is
the release gate. Every milestone ends with a commit and a green host gate run
(unittest + api-coverage + lint + compileall); a red gate stops the milestone.

### M0 — Branch and baseline freeze

Goal: isolate the work and capture the exact green baseline. Work: create branch
`v0.1.1-refactor` from `main`; re-run the four host gates on the branch and
record the transcripts in Artifacts and Notes. Result: a branch whose starting state
is provably green. Proof: `git checkout -b v0.1.1-refactor` succeeds; the four
gate commands print the baseline outputs (134 tests OK; 124 public members PASS; lint
PASS for 7 files; compileall clean). Commit: `docs: adopt PLANS_0.1.1 with approved decisions (D-04 primary, D-10, D-15)` — the plan document travels with the branch, mirroring how PLANS.md is checked in; the dangling `.gitignore` comment ("Local review artifacts") gets its missing pattern line (`CODE_REVIEW_FOR_0.1.1.md`) in the same commit.

### M1 — Single source of truth: `_regs.py` extraction (backlog #1)

Goal: one canonical constant region, one name per bit, acyclic import graph. At the
end of this milestone the file `max31760/_regs.py` EXISTS and is the only place any
register/bit/encoding constant or fixed-point helper is DEFINED; `_core.py` no longer
defines any of them and no longer contains the mid-file NOTE/import; `_faults.py` and
`_lut.py` import from `_regs`. Work: (1) create `_regs.py` with the canonical regions
per D-02/D-03 — register map, CR1/CR2/CR3 bit fields (single CR2 block, `CR2_FSENABLE`
spelling), SR flags (single block), MASK field constants, EEX block selects (no
`EEX_BLK_*`), IFR/FF/ALERT mode encodings, index encodings, physical constants,
`POR_SETTLE_MS = 2000`, PWM frequency table, polarity privates, and the six fixed-point
helpers moved verbatim from `_core.py`. (2) Rewrite the `_core.py` header: explicit
top-of-file import list from `_regs` covering every name `_core` uses OR that tests
import from `_core` (this keeps all existing test imports working); move
`from ._faults import FaultMixin` to the top; delete the NOTE comment and the entire
duplicate constant/helper region. (3) Point `_faults.py` and `_lut.py` imports at
`_regs`. (4) Add `max31760/_regs.py` to `SHARED` in `tests/lint_subset.py`. (5) Add
`TestRegsModule` to the suite: asserts `_regs` imports nothing from the package (AST
walk of its imports), asserts every canonical name is bound identically in `_core`
(re-export integrity), asserts the dead names are GONE (`CR2_FS_ENABLE`,
`EEX_BLK_00_0F`…`EEX_BLK_40_4F`, `MASK_TACH1A`…`MASK_LHA`) and the survivors remain
(`CR2_FSENABLE`, `EEX_SAVE_ALL`, `EEX_LOAD_ALL`, `MASK_RESERVED_HI`,
`MASK_ALARM_FIELD`). Result: drift between two constant blocks becomes impossible; the
ordering-luck import is structurally eliminated. Proof: the ENTIRE existing suite passes
UNMODIFIED except the new test class — `TestConstants` pins every register value, SR
flag position, EEX encoding, and factory default, so any accidental value change fails
loudly; `python -c "import max31760.cp"` and `import max31760.mp` both succeed
(import-order independence); grep shows zero duplicate assignments of any constant
name; lint gate PASS for 8 files. Commit: "Extract register map and fixed-point helpers
into leaf module _regs; remove duplicate constant blocks and mid-file import".

### M2 — Quick structural wins (backlog #3, #6, #9, #15)

Goal: the five-minute-and-an-hour tier of fixes, batched because each is tiny and
independent. Work: (1) add `__enter__`/`__exit__` to the core class — `__enter__`
returns `self`; `__exit__` calls `self.close()` and returns `False` (never suppress);
both facades inherit, and the MicroPython no-op `close()` stays harmless. (2) add
`__repr__` to the core class returning `<MAX31760 addr=0xNN>` formatted from
`self._addr`. (3) zero-arg `super().__init__(...)` in `cp.py` and `mp.py`. (4) drop the
`(object)` tokens from `FaultMixin`, `TransportCP`, `_SmbusCompat`, `TransportMP`.
(5) in `_SmbusCompat.read_i2c_block_data`, ASSERT the legacy contract: if
`len(data) < qty + 1`, raise `OSError` naming the shortfall (fail loudly instead of
silently truncating). (6) replace the magic `2000` in `soft_por` with
`POR_SETTLE_MS` (defined in `_regs` next to `EEPROM_WAIT_MS`). Test updates: NEW
`TestContextManager` (owned FakeSMBus closed after the `with` block; borrowed handle
untouched; an exception inside the block still triggers close and still propagates;
mp-facade `with` works with the no-op close); NEW `TestRepr` (exact string for 0x50 and
0x57); NEW `TestSmbusCompatContract` (legacy stub returning a short payload raises
OSError; the existing normalization test still passes); EXTEND
`TestConstants.test_eex_constants` with `POR_SETTLE_MS == 2000`. Result: resources can
no longer be leaked by forgetting `close()`; `print(dev)` is diagnostic; the legacy
adapter fails loudly. Proof: suite green with the new classes; `repr` output visible in
any REPL session. Commit: "Add context manager, __repr__, zero-arg super, drop (object)
bases, assert legacy smbus payload length, name POR settle constant".

### M3 — Behavior fixes (backlog #4, #13, plus D-06)

Goal: close the three footguns. Work: (1) `measure_tach_once`: after the poll loop, if
`cnt == base` raise `TimeoutError("TACH count did not update within %d ms" %
timeout_ms)` (f-string per D-12); the `finally` still clears PSEN; docstring updated to
state the new contract (a stopped fan times out). (2) `get_pwm_freq_hz`: replace the
fallback `return PWM_FREQ_33HZ` with `raise ValueError` naming the unknown combo (D-06).
(3) keyword-only fences per D-14 on the five timeout-taking public methods plus
`soft_por(settle_ms)`; convert internal call sites to keyword passing; fix the two
positional test call sites. Test updates: FLIP
`test_measure_tach_once_returns_count_and_clears_psen` →
`test_measure_tach_once_times_out_on_static_count` (static mock now expects
`TimeoutError`; assert PSEN cleared afterward); NEW
`test_measure_tach_once_success_path` (inline stub transport whose TC read returns a
changing value after N polls — mirrors the existing `Stub` pattern in
`test_wait_is_pure_delay_without_bus_traffic`); NEW
`test_get_pwm_freq_hz_unknown_combo_raises` (temporarily shadow
`_PWM_FREQ_TO_BITS` with a shortened table, seed the matching CR1 bits, expect
ValueError, restore); NEW `test_keyword_only_timeouts` (inspect.signature asserts
KEYWORD_ONLY kind for `timeout_ms` on the five methods and `settle_ms` on `soft_por`);
UPDATE the two positional `wait_for_duty` calls to keyword form. Result: stale tach
counts and silent frequency assumptions become exceptions; the timeout interface is
locked against positional drift. Proof: flipped/new tests pass; the pre-change code
fails them (run the new tests against the pre-M3 tree to demonstrate red→green); suite
otherwise green. Commit: "Raise TimeoutError on unchanged tach count, raise on unknown
PWM DRV combo, make timeout parameters keyword-only".

### M4 — Honest package facade (backlog #5)

Goal: the documented exports exist. Work: (1) `max31760/__init__.py`: import the
platform-neutral public constants from `_core` (which re-exports `_regs`) plus
`build_lut_curve`/`lut_index_for_temp` from `_lut`; define `__all__` listing them;
keep `__version__`. (2) `cp.py` and `mp.py`: extend `__all__` IDENTICALLY (MAX31760 +
the two LUT utilities + the same constant list) so the parity gate stays green. (3)
Fix the lying class-body comment in `_core.py` to state the real access paths (D-09).
Test updates: NEW `TestPackageFacade` (`import max31760` exposes `__version__`,
`__all__`, and every name in `__all__` resolves; spot-check `max31760.RAMP_SLOW`,
`max31760.SR_ALARM_MASK`, `max31760.EEX_BLOCK_00_0F`, `max31760.build_lut_curve`);
EXTEND `TestApiParity.test_module_exports_match` to assert both entry `__all__` lists
contain the full constant set and remain equal. Result: `max31760.RAMP_SLOW` works
without choosing a platform; the comment tells the truth. Proof: new/extended tests
pass; `python -c "import max31760; print(max31760.RAMP_SLOW)"` prints 0. Commit:
"Honest package facade: root __all__, extended entry-module __all__, corrected export
comment".

### M5 — Accessor unification (backlog #2; gated on D-04 sign-off)

Goal: one convention — properties for state, verbs for actions. Work: implement the
approved D-04 mapping in `_core.py` and `_faults.py`: each mapped setting becomes a
`@property` whose getter is the former getter body and whose setter is the former
setter body (validation included); toggles become plain boolean properties; the
standby trio collapses to one read/write property; `lut` becomes a bulk property
(list of 48) beside the surviving `lut_get_index`/`lut_set_index` verbs. The class
docstring gains the one-line note that property access performs I/O. Then propagate
the rename to EVERY consumer: `tests/test_max31760.py` (mechanical rewrite of all
`get_x`/`set_x`/toggle calls — assertions unchanged), `examples/*.py` (six files),
`scripts/{pico,esp32,rpi}/*.py` (bench scripts calling renamed members), `docs/`,
`README.md`, `SUMMARY.md` (API references). Add a meta-test locking the convention:
NEW `TestAccessorConvention` asserting no public member name starts with `get_` and
no public member is both a property and callable. Result: readers no longer pay the
per-setting recall cost; the api-coverage gate verifies every new name is exercised.
Proof: suite green; `tools/api_coverage.py` PASS (member count drops from 124 to the
new surface, every name covered); parity gate PASS (both facades identical);
`grep -rn "get_" examples scripts docs README.md` finds no stale references; the
examples' observable behavior is unchanged (their printed values come from the same
registers). Commit: "Unify accessor convention: properties for state, verbs for
actions (breaking; see CHANGELOG)".

### M6 — Idiom sweep (backlog #8, #10, #12)

Goal: modern, MicroPython-safe idioms. Work: (1) f-string sweep of the ~30 error
messages in shared modules (D-12); amend `lint_subset.py` to accept `JoinedStr`.
(2) add `_u16_get(hi_reg)` / `_u16_set(hi_reg, value16)` helpers to the core (unpacking
form, byte-order contract in one docstring) and refactor the seven read sites
(local/remote temp, `_setpoint_get`, `rpm`, `measure_tach_once` ×2, `get_tach_threshold`
— or their M5-renamed equivalents) and the two write sites (`_setpoint_set`,
`set_tach_threshold`). (3) `build_lut_curve`: replace the `range(len(pts))` sort check
with `zip(pts, pts[1:])` parallelism and the per-window linear scan with
`bisect.bisect_right` over the breakpoint temperatures (polish; behavior identical).
Test updates: NO assertion changes required — wire-level tests
(`test_wire_level_single_aligned_write`, threshold round-trips, temperature vectors,
`TestBuildLutCurve` vectors) already pin the observable behavior; add ONE new test
`test_u16_helpers_roundtrip` exercising `_u16_get`/`_u16_set` directly against the
mock. Result: the byte-order contract lives in one docstring; the sort check reads as
intent. Proof: suite green; lint gate green with the relaxed rule; grep shows zero
remaining `%`-formatted strings in shared modules. Commit: "f-string sweep, _u16
helpers, zip/bisect in build_lut_curve".

### M7 — Conservative type annotations (backlog #11; board-gated)

Goal: boundary annotations that survive MicroPython. Work: annotate PUBLIC method
signatures with built-in names only (D-11): e.g. `def rpm(self, port: int = 1,
pulses_per_rev: int = 2) -> float`, `def lut_get(self) -> list` is NOT allowed —
container generics are banned; use `-> bytes`/`-> int`/`-> float`/`-> bool` and leave
list-returning methods unannotated or annotated with a comment. Amend
`lint_subset.py` per D-11 (whitelist `Name` annotations ∈ {int, float, bytes, str,
bool}; reject Subscript annotations, AnnAssign, typing imports, future-annotations).
BOARD GATE before promotion: deploy the package to the Pico W (v1.29.0) via mpremote,
run a micro-probe that imports the package, constructs a device, and calls three
annotated methods on-device; record the transcript. Result: the public boundary is
self-documenting for IDEs and checkers without endangering the interpreter. Proof:
lint gate green under the new rules; Pico W probe transcript shows clean import and
correct results; CPython suite green. Commit: "Conservative built-in-type annotations
on public signatures; relax lint gate to whitelisted Name annotations".

### M8 — Docstring surgery (backlog #7, #14)

Goal: documentation that earns its place. Work: (1) add formal `Args:`/`Returns:`/
`Raises:` sections to `save_config`, `load_config`, `measure_tach_once`,
`wait_for_duty`, `verify`, `soft_por`, `recover_from_corruption` (the six-plus-one
obligation-bearing methods; D-08). (2) Bulleted treatment of the long caveats in
`_tx`, `_wait_eeprom_ready`, `soft_por`, `measure_tach_once`, and
`TransportMP.probe` (one-line summary first, specifics as bullets). (3) Carve the
dated bench narratives (2026-11-07/08 observations) OUT of docstrings INTO a new
`NOTES/eeprom-timing.md` consolidating the evidence trail; docstrings keep a one-line
pointer ("waits a fixed 700 ms — bench rationale in NOTES/eeprom-timing.md"). (4) Add
the legend pointer to the `_core.py` module docstring: "Feature/decision IDs (F#, D#,
A#, B#) refer to PLANS.md sections." (5) Demote ALL-CAPS emphasis: reserve caps for
the two genuinely dangerous facts (destructive SR read; POR-swallowed write); the rest
become normal-weight prose. (6) Write the MISSING constructor docstrings (core
`MAX31760.__init__`, `cp.MAX31760.__init__` including the `handle` contract
"use as-is, not closed", `mp.MAX31760.__init__`). (7) Fix the summaries that restate
the name (`get_actual_duty_raw` et al. — or their M5 successors) so each states
something the name doesn't (when the value lags the command, that the read is
destructive, which grid/unit the value sits on). Result: a newcomer can learn each
method's obligations from its docstring alone. Proof: no behavior change — suite green
unchanged; a manual diff review confirms only docstrings/comments changed
(`git diff --stat` shows only `.py` docstring hunks plus the new NOTES file). Commit:
"Docstring surgery: Raises sections, bulleted caveats, bench notes to NOTES/, legend
pointer, ALL-CAPS demotion, constructor docstrings".

### M9 — Hardening, E2E, release (backlog remainder + D-10, D-13)

Goal: prove the refactored driver on real silicon and ship 0.1.1. Work: (1) version
bump in `max31760/__init__.py` and `pyproject.toml` to 0.1.1; CHANGELOG.md entry led by
the breaking-rename table (D-13). (2) FULL host gate run: unittest, api-coverage,
lint, compileall — record transcripts. (3) HARDWARE E2E in two phases (user directive 2026-11-21). PHASE H1 — NOW, Pico W
ONLY (COM16, v1.29.0): `python -m mpremote connect port:COM16 run
examples/hw_smoke_test.py` then `... run examples/e2e_hardware_test.py`; the M6
f-string error-rendering probe and the M7 annotated-signature probe also run here
(they are Pico-gated by construction). Before each run: snapshot the full register
range (read 0x00–0x5B); after: restore RAM byte-for-byte and re-save EEPROM so the
bench ends in its pre-test state (standing lesson). TACH2/port-2 functional items
remain EXCLUDED-HW (unit-tested only). Remember the convergence-wait lesson: sample
RPM only after the fan has settled (several seconds from rest), or a mid-acceleration
reading (~710 rpm at 25 % duty) looks like a fault. PHASE H2 — DEFERRED, starts only
after H1 is complete AND the user gives the go-ahead: RPi 3A+ at `marc@192.168.1.225`
(SSH key auth, CPython + smbus2; SCP the package + examples to `~/max31760-test/`, re-set `clk_tout_ms=700`,
run the same two suites with `python3` — this leg re-validates the `_SmbusCompat`
contract change and the f-string/annotation deployment on the CPython side) and
ESP32-S3 (COM7, mpremote; `esp32_probe.py` + smoke). (4) MERGE + TAG (user-elected option a): only after ALL THREE HARDWARE PLATFORMS ARE
VALIDATED — Phase H1 (Pico W) plus both Phase H2 legs (ESP32-S3, RPi 3A+) — then
merge and tag `v0.1.1`. Only one MAX31760 exists; it is physically moved between
benches, so the H2 legs run sequentially. Merge is a merge commit preserving
branch history; tag `v0.1.1`. Result: a tagged, hardware-confirmed 0.1.1 with a clean, uniform API.
Proof: E2E matrix 12/12 PASS on Pico W in Phase H1 — the same sections that passed
on v0.1.0; host gates green; Phase H2 benches (RPi 3A+, ESP32-S3) appended when that
leg runs; `git tag -l` shows `v0.1.1`; CHANGELOG documents the breakage. Commit: the merge commit; tag `v0.1.1`.

## Concrete Steps

Working directory for ALL host commands: the repository root
(`<workdir>/FanSpeedController`). Expected transcripts below were captured 2026-11-21
on the v0.1.0 baseline (M0 re-confirms them on the branch).

    # M0 — branch + baseline
    git checkout main && git checkout -b v0.1.1-refactor
    python -m unittest discover tests
    # Ran 134 tests in ~2.1s / OK
    python tools/api_coverage.py
    # public members: 124 / RESULT: PASS (all public members referenced by the suite)
    python tests/lint_subset.py
    # max31760/_core.py : CLEAN ... (7 files) / RESULT: PASS
    python -m compileall max31760
    # (no output, exit 0)

    # After EACH milestone (M1..M8), the same four gates must be green, then:
    git add -A && git commit -m "<milestone message>"   # plain message, no trailers (user directive)

    # M7 board gate (Pico W, from the repo root, mpremote installed):
    python -m mpremote connect port:COM16 fs cp max31760 /lib/max31760
    python -m mpremote connect port:COM16 run scripts/pico/refactor_probe.py
    # expected: import ok, device constructed, annotated methods return sane values

    # M9 Phase H1 hardware E2E (Pico W only):
    python -m mpremote connect port:COM16 run examples/hw_smoke_test.py
    python -m mpremote connect port:COM16 run examples/e2e_hardware_test.py
    # expected: all sections print PASS; final line 12/12 (TACH2 functional EXCLUDED-HW)

    # M9 Phase H2 (DEFERRED: only after H1 complete + user go-ahead):
    #   RPi 3A+ (marc@192.168.1.225, ssh keys): scp package + examples to ~/max31760-test/, re-set clk_tout_ms=700,
    #   python3 hw_smoke_test.py && python3 e2e_hardware_test.py
    #   ESP32-S3: python -m mpremote connect port:COM7 run scripts/esp32/esp32_probe.py (+ smoke)

    # M9 merge + tag (only after the agreed release-scope gates are green):
    git checkout main && git merge v0.1.1-refactor
    git tag v0.1.1

If a milestone leaves a gate red: fix forward on the branch (do NOT merge); if the
milestone itself is unsound, `git reset --hard <previous-milestone-commit>` restores
the last green state — every milestone commit is a checkpoint by construction.

## Validation and Acceptance

Acceptance is phrased as observable behavior. ALL of the following must hold before
M9's merge:

Host gates (repo root): `python -m unittest discover tests` reports MORE than 134
tests, all OK (baseline 134 minus zero removals plus the additions below; the exact
final count is recorded in Artifacts and Notes). `python tools/api_coverage.py` prints
`RESULT: PASS` with the new (smaller) public-member count, proving every renamed/new
member is exercised. `python tests/lint_subset.py` prints CLEAN for EIGHT files
(seven plus `_regs.py`) and `RESULT: PASS` under the relaxed rules (JoinedStr allowed;
whitelisted Name annotations allowed). `python -m compileall max31760` exits clean.

New/updated test inventory (the coverage this plan owes): M1 — `TestRegsModule`
(leaf-import purity, re-export integrity, dead-name absence, survivor presence).
M2 — `TestContextManager` (owned-close, borrowed-untouched, exception-propagation,
mp no-op), `TestRepr` (exact strings), `TestSmbusCompatContract` (short payload →
OSError), `POR_SETTLE_MS` pin in `TestConstants`. M3 — flipped
`test_measure_tach_once_times_out_on_static_count` (red before M3, green after),
`test_measure_tach_once_success_path`, `test_get_pwm_freq_hz_unknown_combo_raises`,
`test_keyword_only_timeouts`, keyword-form updates to the two `wait_for_duty` calls.
M4 — `TestPackageFacade`, extended `TestApiParity.test_module_exports_match`.
M5 — wholesale migration of ~40 existing test methods to property form (same
assertions), `TestAccessorConvention` meta-lock. M6 — `test_u16_helpers_roundtrip`.
M7 — lint-gate rule tests (whitelisted annotation accepted, subscript annotation
rejected, typing import rejected). M8 — no new tests (doc-only; diff-stat proof).
The red→green demonstration is mandatory for M3's flipped test: run it against the
pre-M3 tree first and record both transcripts.

Hardware E2E (acceptance per PLANS.md Definition of Done, phased per user
directive): PHASE H1 — on the Pico W bench, `hw_smoke_test.py` completes with every
assert passing and `e2e_hardware_test.py` reports 12/12 sections PASS (TACH2
functional EXCLUDED-HW, unit-covered); this is the acceptance bar for
development-complete. PHASE H2 (deferred until H1 complete + user go-ahead) — same
result on the RPi 3A+ bench (CPython path; re-validates the `_SmbusCompat` contract
change and the f-string/annotation deployment on the CPython side) and ESP32-S3
(`esp32_probe.py` + smoke). Bench state restored byte-for-byte after each run.
Board-syntax acceptance for M6/M7: the Pico W probes demonstrate f-string error
rendering and annotated-signature import/call on v1.29.0 MicroPython.

Release acceptance: `max31760.__version__ == "0.1.1"`; `pyproject.toml` version 0.1.1;
CHANGELOG.md contains the breaking-rename table; `git tag -l` includes `v0.1.1`;
`main` HEAD is the merge commit.

## Idempotence and Recovery

Every host-side step is repeatable: the gates are pure reads of the tree; commits are
additive checkpoints; the branch never touches `main` until M9. Re-running a milestone
after a partial failure is safe because each milestone's edits are self-contained
files (M1: `_regs.py` + `_core.py` header + two import lines; M5: the rename is a
whole-tree mechanical transform that can be reapplied from the mapping). Rollback:
`git reset --hard` to the previous milestone commit on the branch; `main` remains at
v0.1.0 throughout, so the worst case is throwing away the branch. Hardware recovery:
`scripts/pico/e2e_restore.py` restores factory control-register state after an
interrupted E2E run; the driver's own `recover_from_corruption()` handles the
EEPROM-program-corrupt condition; a bricked-board scenario is covered by reflashing
via mpremote followed by `scripts/pico/pico_reflash_probe.py`. The M9 merge is the only
irreversible step; it happens only after every gate is green, and the tag can be
deleted/moved if a post-merge defect is found (fix-forward on a hotfix branch, re-tag).

## Artifacts and Notes

Baseline transcripts (captured 2026-11-21, v0.1.0, repo root):

    $ python -m unittest discover tests
    Ran 134 tests in 2.145s
    OK
    $ python tools/api_coverage.py
    public members: 124
    RESULT: PASS (all public members referenced by the suite)
    $ python tests/lint_subset.py
    max31760/_core.py : CLEAN
    max31760/_tables.py : CLEAN
    max31760/_lut.py : CLEAN
    max31760/_faults.py : CLEAN
    max31760/_transport_mp.py : CLEAN
    max31760/mp.py : CLEAN
    max31760/__init__.py : CLEAN
    RESULT: PASS

M0 transcript (captured 2026-11-21 on branch `v0.1.1-refactor`, commit ef8e4c9):

    $ git checkout -b v0.1.1-refactor
    Switched to a new branch 'v0.1.1-refactor'
    $ python -m unittest discover tests
    Ran 134 tests in 2.137s
    OK
    $ python tools/api_coverage.py
    public members: 124
    RESULT: PASS (all public members referenced by the suite)
    $ python tests/lint_subset.py
    max31760/_core.py : CLEAN
    max31760/_tables.py : CLEAN
    max31760/_lut.py : CLEAN
    max31760/_faults.py : CLEAN
    max31760/_transport_mp.py : CLEAN
    max31760/mp.py : CLEAN
    max31760/__init__.py : CLEAN
    RESULT: PASS
    $ python -m compileall -q max31760
    (no output, exit 0)
    $ ssh marc@192.168.1.225 "hostname && python3 --version"
    fanspeedcontroller
    Python 3.13.5
    # ~/max31760-test/ already holds the v0.1.0 deployment (package + both E2E suites + rpi_* scripts)

M1 transcript (captured 2026-11-21, commit a186994):

    $ python -m unittest discover tests
    Ran 138 tests in 2.150s
    OK
    $ python tools/api_coverage.py
    public members: 124
    RESULT: PASS (all public members referenced by the suite)
    $ python tests/lint_subset.py
    max31760/_regs.py : CLEAN   (+ 7 more, all CLEAN)
    RESULT: PASS
    $ python -m compileall -q max31760
    (no output, exit 0)
    $ python -c "import max31760.mp; import max31760.cp"
    facade-import-ok
    $ python -c "import max31760._faults" ; python -c "import max31760._lut"
    faults-direct-ok / lut-direct-ok   (previously required _core imported first)

M2 transcript (captured 2026-11-21, commit 5490987):

    $ python -m unittest discover tests
    Ran 145 tests in 2.149s
    OK
    $ python tools/api_coverage.py
    public members: 125
    RESULT: PASS (all public members referenced by the suite)

M3 red→green transcript (captured 2026-11-21):

RED — new/flipped tests run against pre-M3 core (git show 5490987:_core.py),
     exactly the four designed failures, everything else green:

    FAIL: test_timeout_params_are_keyword_only (TestKeywordOnlyTimeouts)
        AssertionError: POSITIONAL_OR_KEYWORD is not KEYWORD_ONLY
    FAIL: test_unknown_drv_combo_raises (TestPwmFreqGuard)
        (old getter silently returned 33 Hz for an unmatched DRV combo)
    FAIL: test_measure_tach_once_port2_times_out_on_static_count (TestThreeWireAssist)
        AssertionError: TimeoutError not raised by measure_tach_once
    FAIL: test_measure_tach_once_times_out_on_static_count (TestThreeWireAssist)
        AssertionError: TimeoutError not raised by measure_tach_once
    Ran 148 tests ... FAILED (failures=4)

GREEN — same suite against the M3 core:

    Ran 148 tests in 2.146s
    OK
    $ python tools/api_coverage.py
    public members: 125
    RESULT: PASS (all public members referenced by the suite)

M4 transcript (captured 2026-11-21):

    $ python -m unittest discover tests
    Ran 151 tests in 2.153s
    OK
    $ python tools/api_coverage.py
    public members: 125
    RESULT: PASS (all public members referenced by the suite)

(Milestone transcripts — gate outputs, red→green demonstrations, Pico W probe and E2E
matrix results, merge/tag records — are appended here as each milestone lands.)

## Interfaces and Dependencies

Final-state contracts after M9 (prescriptive; anything not listed is unchanged from
v0.1.0):

In `max31760/_regs.py` (NEW leaf module, imports nothing from the package), define:
the full register map (`REG_CR1`…`REG_EEX`, `ADDR_MIN`, `ADDR_MAX`, `PAGE_SIZE`,
`LUT_LEN`, `USER_LEN`), all CR1/CR2/CR3 bit fields (single CR2 block; the full-speed
force bit named `CR2_FSENABLE = 0x08`), the single SR flag block (`SR_TACH1A`…`SR_PC`,
`SR_ALARM_MASK`), `MASK_ALARM_FIELD`, `MASK_RESERVED_HI`, the EEX block selects
(`EEX_BLOCK_00_0F`…`EEX_BLOCK_40_4F`, `EEX_ALL_BLOCKS`, `EEX_LOAD_BIT`,
`EEX_SAVE_ALL`, `EEX_LOAD_ALL`), mode/index/frequency encodings (`INDEX_*`,
`RAMP_*`, `FF_MODE_*`, `ALERT_MODE_*`, `IFR_INDEX_MASK`, `PWM_FREQ_*`,
`_PWM_FREQ_TO_BITS`, `_POLARITY_POSITIVE`, `_POLARITY_NEGATIVE`), physical constants
(`TEMP_LSB_C`, `TACH_REF_HZ`, `TACH_AVG_PULSES`, `RETRY_DELAYS_MS`,
`EEPROM_WAIT_MS`, `POR_SETTLE_MS = 2000`), and the helpers
`temp_to_raw16(celsius: float) -> int`, `raw16_to_temp(raw16: int) -> float`,
`duty_to_pct(duty: int) -> float`, `pct_to_duty(pct: float) -> int`,
`rpm_from_count(count: int, pulses_per_rev: int = 2) -> float`,
`count_from_rpm(rpm: float, pulses_per_rev: int = 2) -> int`.

In `max31760/_core.py`: the `MAX31760` class additionally defines
`__enter__(self) -> MAX31760`, `__exit__(self, exc_type, exc_value, traceback) ->
bool` (calls `close()`, returns False), and `__repr__(self) -> str`
(`<MAX31760 addr=0xNN>`). The public surface is the D-04 mapping: properties for all
mapped state (each getter performing a retried burst read; each setter validating then
writing), surviving verbs unchanged, `timeout_ms`/`settle_ms` keyword-only on
`wait_for_duty`, `measure_tach_once`, `save_config`, `load_config`,
`recover_from_corruption`, `soft_por`. `measure_tach_once` raises `TimeoutError` when
the count is unchanged at timeout. `get_pwm_freq_hz` (or its `pwm_freq_hz` property
under D-04-primary) raises `ValueError` on an unknown DRV combo. Private helpers
`_u16_get(hi_reg) -> int` and `_u16_set(hi_reg, value16) -> None` centralize the
big-endian 16-bit idiom. Public signatures carry built-in-name annotations only
(D-11 whitelist).

In `max31760/__init__.py`: `__version__ = "0.1.1"`, a curated `__all__` of the
platform-neutral public constants plus `build_lut_curve` and `lut_index_for_temp`
(re-exported from `_lut` once). In `max31760/cp.py` and `max31760/mp.py`: identical
extended `__all__` (parity gate enforced); zero-arg `super()`; inherited
context-manager methods.

In `tests/lint_subset.py`: `SHARED` includes `max31760/_regs.py`; `JoinedStr` nodes
are ACCEPTED; `ast.Name` annotations are accepted iff the id ∈ {int, float, bytes,
str, bool}; subscripted annotations, `AnnAssign`, `typing` imports, and
`from __future__ import annotations` remain REJECTED.

Error model (unchanged built-ins, extended obligations): `ValueError` — bad
arguments/bounds AND unknown PWM DRV combo; `OSError` — bus/NACK after retries AND
legacy-smbus short payload; `TimeoutError` — EEPROM-busy overrun AND unchanged tach
count in `measure_tach_once`. Every obligation-bearing method documents its `Raises:`
section (M8).

Dependencies: no new third-party dependencies (smbus2 remains the only Linux dep);
`bisect` is stdlib and available on MicroPython; no network access required at build
or test time.

---

Revision notes (bottom of plan, per ExecPlan rules):
Initial revision 2026-11-21 — plan authored from the validated CODE_REVIEW_FOR_0.1.1.md; all 15 backlog items accepted (D-01); D-04 (accessor end-game) and D-10 (branch workflow) proposed, awaiting user sign-off. No implementation began.
Revision 2 2026-11-21 — user approvals incorporated: D-04 primary property/verb variant APPROVED; D-10 APPROVED with branch renamed to `v0.1.1-refactor` (no `chatbox/` prefix); D-15 ADDED (no backwards compatibility, no deprecation warnings — pre-1.0); hardware E2E re-phased (Phase H1 Pico-W-only now; Phase H2 ESP32-S3 + RPi 3A+ deferred until H1 complete + user go-ahead); merge/tag scope pending user election (default: after H2).
Revision 3 2026-11-21 — execution directives folded in: co-author trailers removed from all commits; merge/tag gated on ALL THREE platforms validated (option a confirmed by user); RPi 3A+ connection recorded (`marc@192.168.1.225`, SSH key auth); single-MAX31760 relocation constraint documented (sequential H2 legs). User gave the go-ahead; M0 underway.
