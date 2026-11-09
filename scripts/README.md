# Hardware Bench Scripts

Validation, diagnostic, and probe scripts written during development and
cross-platform verification. They are **not** part of the shipped `max31760`
package and are **not** collected by the unit-test suite in `tests/` (they
need real hardware and/or import `machine`). Every script here is
self-contained — none imports another script from this tree.

Scripts are grouped by the physical bench they target:

| Dir | Bench | Runtime | How to run |
|-----|-------|---------|------------|
| `pico/` | RPi Pico W (RP2040), USB-serial COM16 | MicroPython on-device (most) · CPython host-side (`probe_temp.py`) | `python -m mpremote connect port:COM16 run <script>.py` · host: `python probe_temp.py` |
| `esp32/` | ESP32, USB-serial COM7 | MicroPython on-device | `python -m mpremote connect port:COM7 run <script>.py` |
| `rpi/` | Raspberry Pi 3A+ (local RPi over SSH) | CPython on the Pi (smbus2) | SCP to `~/max31760-test/`, then `python3 <script>.py` (some need `sudo`; `clk_tout_ms=700` must be re-set after reboot) |

The canonical tri-platform suites (`hw_smoke_test.py`,
`e2e_hardware_test.py`) live in `examples/` — the `e2e_phase_*` scripts below
are the incremental per-feature slices that were run during Phases A/B.

## pico/

| Script | Purpose |
|--------|---------|
| `e2e_phase_a.py` | Phase A hardware E2E: transport layer against the real MAX31760 |
| `e2e_phase_b1b2.py` | Phase B1/B2 E2E: init/self-test + temperatures + setpoints |
| `e2e_phase_b3.py` | Phase B3 E2E: LUT get/set + curve builder vs real chip |
| `e2e_phase_b4.py` | Phase B4 E2E: manual/auto modes, duty, PWM config vs real chip |
| `e2e_phase_b5.py` | Phase B5 E2E: ramp rate + wait_for_duty vs real chip |
| `e2e_phase_b6.py` | Phase B6 E2E: tach enable, live RPM read, threshold vs real chip |
| `e2e_phase_b7.py` | Phase B7 E2E: fault handling, status, FFDC, modes, alert mask |
| `e2e_phase_b8.py` | Phase B8 E2E: 3-wire assists (PSEN/TACHFULL) + spin-up |
| `e2e_phase_b9.py` | Phase B9 E2E: ALERT service routine (F18) + ideality factor (F19) |
| `e2e_phase_b10.py` | Phase B10 E2E: EEPROM lifecycle (F20) + soft POR/standby/user mem (F21) |
| `e2e_phase_b11.py` | Phase B11 E2E: configuration presets (F24) |
| `e2e_debug_lut.py` | Debug the LUT matrix section step by step |
| `e2e_diag.py` | Diagnostic: dump tach-related state on the bench |
| `e2e_diag_latency.py` | Measure TACH2A re-arm latency after CLRFAIL + TACH2 re-enable |
| `e2e_fix_cr2.py` | Restore true factory CR2 (DFC=0) after B11 left DFC set |
| `e2e_probe_ifr.py` | Probe: IFR restore timing on real silicon |
| `e2e_probe_psen.py` | Probe: is the PSEN stretched pulse visible in PWMV at low manual duty? |
| `e2e_probe_state.py` | Quick live-state probe: CR2/DFC, PWMR/PWMV, LUT around ambient |
| `e2e_restore.py` | Restore factory control-register state after an interrupted E2E run |
| `pico_deploy_check.py` | Post-deploy sanity check for the Pico (via mpremote) |
| `pico_reflash_probe.py` | Post-reflash Pico health probe: firmware, filesystem, I²C scan |
| `pico_rpm_check.py` | Focused fan-speed measurement with independent raw-counter verification |
| `probe_temp.py` | Host-side raw-serial REPL probe (COM16) — drives the MicroPython REPL over pyserial |

## esp32/

| Script | Purpose |
|--------|---------|
| `esp32_probe.py` | Standalone MAX31760 connectivity probe for the ESP32 bench (pure `machine.I2C`) |

## rpi/

All CPython + smbus2, run on the Pi itself. Written during the RPi leg
investigation (D32/D33 — soft-POR errno-121 root cause).

| Script | Purpose |
|--------|---------|
| `rpi_probe.py` | Connectivity probe (scan, verify, temps) |
| `rpi_diag.py` | Raw I²C diagnostics (read-mostly) |
| `rpi_blocktest.py` | Block-read vs byte-read behavior on the RPi bus |
| `rpi_bus_recovery.py` | I²C bus recovery (run as root, i2c driver unloaded) |
| `rpi_state_check.py` | Verify/restore factory CR1 on the bench chip |
| `rpi_tw_timeline.py` | Measure the real busy-window shape after an EEX operation |
| `rpi_tx_log.py` | Log every driver I²C transaction in the EEPROM section |
| `rpi_nack_topology.py` | Map the write-NACK topology around save/load |
| `rpi_burst_measure.py` | Isolate the post-LOAD completion NACK burst |
| `rpi_interference_test.py` | Does bus traffic during the post-LOAD window disturb the commit? |
| `rpi_traffic_vs_silence.py` | Decisive test: traffic vs silence during the post-LOAD window |
| `rpi_silence_vs_probe.py` | Silence vs probe during the post-LOAD window, interleaved 5× each |
| `rpi_bruteforce.py` | 10× brute force of the exact smoke sequence through the driver |
| `rpi_bruteforce_raw.py` | Same 10× brute force with raw smbus2 (driver isolated) |
| `rpi_swpor_semantics.py` | Does the "rejected" SW_POR write actually reset the chip? (volatile marker) |
| `rpi_boot_time.py` | Confirm the SW_POR "failure" resets the chip; measure boot time |
| `rpi_lifecycle_diag.py` | Step-by-step repro of the E2E lifecycle section with per-call detail |
