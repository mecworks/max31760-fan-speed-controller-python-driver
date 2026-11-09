# 05 — Hardware Verification Log (RPi Pico W first edition + MAX31760)

Date: 2026-11-03 · Host: Windows · Link: USB serial COM16 @115200
Script: `tools/pico_probe.py` (REPL driven via pyserial; Ctrl-B to friendly REPL)

## Result: CONNECTIVITY VERIFIED ✅ (bidirectional)

| Check | Method | Result |
|-------|--------|--------|
| Firmware | `sys.version` | MicroPython v1.19.1, platform `rp2` |
| Bus scan | `i2c.scan()` | `[80]` = **0x50** present (MAX31760, A2:A0=000) |
| Local temp | `readfrom_mem(0x50,0x58,2)` | raw 0x1AC0 → **≈26.75 °C** (correct ÷256 scale) |
| Status SR | `readfrom_mem(0x50,0x5A,1)` | `0x2` → TACH2A set (fan-2 idle) |
| CR1 | `readfrom_mem(0x50,0x00,1)` | `0x1` → DRV=01 (150 Hz PWM) |
| Current duty PWMV | `readfrom_mem(0x50,0x51,1)` | `255` = 100 % |
| Tach TC1 | `readfrom_mem(0x50,0x52,2)` | `1295` → ≈2317 RPM @2 ppr |
| Tach TC2 | `readfrom_mem(0x50,0x54,2)` | `65535` = overflow (fan-2 stopped/unwired) |
| Write path | RMW no-op on CR1 | `rw_ok True` (round-trips) |

Remote-temp channel (0x56/0x57) returned no value on this run — consistent with
no remote diode populated; not a comms fault. All register addresses match
NOTES/01 §3 register map.

## ⚠️ KEY FINDING — non-standard I²C API on this firmware

This v1.19.1 rp2 build does **NOT** expose the canonical MicroPython I²C surface:

| Canonical (≥1.20 / most ports) | Present here? | Actual name on this build |
|-------------------------------|---------------|---------------------------|
| `mem_read(addr, reg, n)`      | ❌            | `readfrom_mem(addr, reg, n)` |
| `mem_write(addr, reg, data)`  | ❌            | `writeto_mem(addr, reg, data)` |
| `begin_transaction`/`end_…`   | ❌            | — (absent) |
| `transaction()` ctx mgr       | ❌            | — (absent) |
| `scan()`                      | ✅            | `scan()` |
| `writeto(addr, data)`         | ✅            | `writeto(addr, data)` |
| `readfrom(addr, n)`           | ✅            | `readfrom(addr, n)` *(takes addr+n)* |
| `readinto(buf)`               | ✅            | present but needs tx context |

Full `dir(i2c)`: `init, readfrom, readfrom_into, readfrom_mem, readfrom_mem_into,
readinto, scan, start, stop, write, writeto, writeto_mem, writevto`.

### Impact on `_transport_mp.py` (Phase A4)
The MP transport adapter must **capability-probe at init** and dispatch across
at least three dialects:
1. `mem_read`/`mem_write` (canonical ≥1.20) — preferred.
2. `readfrom_mem`/`writeto_mem` (this board's naming) — fallback.
3. `transaction()` + `writeto`+`readfrom` pointer-latch — last resort.

Do **not** hard-code any single method family. This is now a hard requirement,
not an assumption.

## Corrected temperature scale (for the record)
Decode: `celsius = sign_extend(raw16) / 256.0`  (equivalently `(raw16>>5)/8`).
Encode: `raw16 = round(celsius*256) & 0xFFFF`. Probe initially used ÷64 (wrong);
driver uses ÷256.
