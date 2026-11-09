# MAX31760 Datasheet Analysis (Discovery Notes)

Source: Maxim Integrated DS 19-7395 Rev 0 (4/14).
Online: primary https://download.mikroe.com/documents/datasheets/MAX31760.pdf ;
backup https://www.analog.com/media/en/technical-documentation/data-sheets/max31760.pdf .
Local copy: `reference/MAX31760.pdf` (gitignored — vendor copyright, not redistributed).
Device: Precision fan-speed controller with nonvolatile 48-step temperature→PWM lookup table.

## 1. Device Overview

- Measures **local die temperature** and **remote diode temperature** (e.g., 2N3906, CPU/GPU thermal diode).
- Maps measured temperature → PWM duty cycle via a **48-byte nonvolatile LUT** (2 °C windows).
- **Two independent tachometer inputs** (TACH1/TACH2) for two-fan monitoring + fan-fault detection.
- Open-drain outputs: **PWM**, **ALERT**, **FF/FS** (fan-fail out / full-speed in multiplexed), **SHDN** (system shutdown on overtemp).
- Config stored in **on-chip EEPROM**; loads to RAM at power-on automatically.
- VDD 3.0–3.6 V, −40…+125 °C, QSOP-16. I²C interface, Fast-mode capable.

## 2. Communication Protocol (I²C)

| Item | Value |
|---|---|
| Slave address | 7-bit `101 A2 A1 A0` → **0x50 … 0x57** (pins tied GND/VDD). Wire write byte = addr<<1 \| 0 (e.g., 0xA0 for 0x50). |
| Speed | Standard & Fast mode (≤400 kHz). |
| Bus reset | Device times out after holding SDA low 25–45 ms (does not reset other bus masters). |
| Write model | START → dev-addr(W) → **memory-address byte** → 1–8 data bytes → STOP. Internal pointer increments; **page size = 8 bytes**. Crossing a page boundary without STOP wraps within the page (data lands at wrong address!). Master must STOP between pages. |
| Read model | Pointer-based. To read a specific location: dummy-write the address (START, addr-W, reg, repeated-START, addr-R) then read N bytes, NACK last. Multi-page reads are fine (no page-wrap constraint on reads). |
| EEPROM busy | After any EEPROM byte write the device **NACKs its own address for up to tW = 550 ms** (~110 ms per 16-byte block). Host must either wait or **acknowledge-poll** (probe address until ACK). |
| EEPROM ops | Via **EEX register (5Bh)**: bit7 = L/W (1 = load EEPROM→RAM, 0 = write RAM→EEPROM), bits 4:0 select 16-byte blocks (00h–0Fh, 10h–1Fh, 20h–2Fh, 30h–3Fh, 40h–4Fh). Bits auto-clear. Full-range load = 0x9F, full-range save = 0x1F. |
| Corruption recovery | SR.PC bit flags EEPROM corruption; fix = rewrite EEPROM from good RAM, then power-cycle or soft-POR (CR1.6). |

### Transaction recipes needed from the driver
1. Single-register read (dummy-write + repeated-start read).
2. Multi-register burst read (up to 48 bytes across pages — OK for reads).
3. Single/multi-register write ≤ 8 bytes, aligned to 8-byte page rows (LUT writes must be chunked per page).
4. Post-save delay or ack-poll (550 ms worst case).

## 3. Register Map (00h–5Bh)

| Addr | Name | R/W | EEPROM-backed | Factory default | Purpose |
|---|---|---|---|---|---|
| 00h | CR1 | RW | yes | 01h | ALTMSK(7), SW-POR(6), HYST(5), DRV[1:0](4:3), PPS(2), MTI(1), TIS(0) |
| 01h | CR2 | RW | yes | 10h | STBY(7), ALERTS(6), SPEN(5), FFMode(4), FSEnable(3), RDPS(2), FSST(1), DFC(0) |
| 02h | CR3 | RW | yes | 03h | CLRFAIL(7, self-clear), FF_0(6), RAMP[1:0](5:4), TACHFULL(3), PSEN(2), TACH2E(1), TACH1E(0) |
| 03h | FFDC | RW | yes | FFh | Duty forced on fan failure |
| 04h | MASK | RW | yes | C0h | Alarm masks; bits 7:6 reserved = 1 |
| 05h | IFR | RW | yes | 18h | Remote-diode ideality factor (64-entry table, 0.9844–1.0489) |
| 06h/07h | RHSH/RHSL | RW | yes | 55h/00h | Remote High Set-point (+85 °C) |
| 08h/09h | LOTSH/LOTSL | RW | yes | 55h/00h | Local Overtemp Set-point (+85 °C) |
| 0Ah/0Bh | ROTSH/ROTSL | RW | yes | 6Eh/00h | Remote Overtemp Set-point (+110 °C) |
| 0Ch/0Dh | LHSH/LHSL | RW | yes | 46h/00h | Local High Set-point (+70 °C) |
| 0Eh/0Fh | TCTH/TCTL | RW | yes | FFh/FEh | Tach fail threshold (unsigned 16-bit) |
| 10h–17h | USER | RW | yes | 00h | 8 bytes general-purpose user memory |
| 20h–4Fh | LUT[0..47] | RW | yes | FFh | 48-byte temp→duty table |
| 50h | PWMR | RW | no | 00h | Direct (manual) duty command |
| 51h | PWMV | RO | no | 00h | Current actual duty (incl. during ramp/fault) |
| 52h/53h | TC1H/TC1L | RO | no | 00h | TACH1 count (avg clock ticks/pulse @100 kHz ref) |
| 54h/55h | TC2H/TC2L | RO | no | 00h | TACH2 count |
| 56h/57h | RTH/RTL | RO | no | 00h | Remote temp reading |
| 58h/59h | LTH/LTL | RO | no | 00h | Local temp reading |
| 5Ah | SR | RO | no | 00h | Status: PC(7), RDFA(6), LHA(5), LOTA(4), RHA(3), ROTA(2), TACH2A(1), TACH1A(0). **Alarm bits clear on read.** |
| 5Bh | EEX | WO | no | 00h | EEPROM load/write control (auto-clears) |

## 4. Key Data Formats

### Temperature (setpoints + readings)
- 16-bit two's complement, **left-aligned**: sign = bit15, magnitude bits 14:5, **LSB (bit5) = 0.125 °C**. Range ≈ −128…+127.875 °C.
- Encode: `raw16 = round(celsius * 8) << 5`; decode: `celsius = (sign_extend(raw16) >> 5) / 8.0`.
- Examples: +25 °C → 19h 00h; −0.125 °C → FFh E0h; +125 °C → 7Dh 00h.
- ADC conversion time 150 ms (both channels); resolution 0.125 °C; accuracy ±2 °C (0…85 °C local).

### PWM duty
- 8-bit value, resolution 1/256: `duty% = value/256*100`; 0xFF ≡ 100 %.
- LUT window i (i=0): T < 18 °C; i≥1: `18+2i ≤ T < 20+2i`; i=47: T ≥ 110 °C. Address = 0x20+i.
- Hysteresis on LUT stepping: 2 °C (HYST=0) or 4 °C (HYST=1).

### Tachometer / RPM
- Internal 100 kHz counter; counts clock periods over **4 tach pulses** → average ticks/pulse in 16-bit unsigned TC registers.
- `RPM = 60 × 100,000 / (count) / n` where n = pulses/rev (typically 2).
- Fail condition: count **greater than** TCT threshold **or overflow** (wrap ⇒ very slow/stopped fan). Three consecutive detections ⇒ FF/FS asserts + duty forced to FFDC.
- Detection disabled for first 2 s after startup; disabled while duty = 0 or ramping to 0 (unless FF_0=1; always disabled at 33 Hz supply-modulation mode).
- RD/locked-rotor mode: FSST=1, polarity via RDPS.

## 5. Control Semantics Needed for Fan Control

### CR1 (00h)
- **DRV[1:0]** PWM frequency: 00=33 Hz, 01=150 Hz, 10=1.5 kHz, 11=25 kHz (default 00). 4-wire fans want 25 kHz.
- **PPS** polarity: 0 = positive (100 % = high), 1 = negative.
- **MTI/TIS** LUT index source: local / remote / max(local,remote). Default: remote.
- **HYST** 2/4 °C LUT hysteresis.
- **SW-POR** (bit6): reloads EEPROM-backed regs from EEPROM, resets volatile regs; self-clears; other bits ignored when set.
- **ALTMSK** (bit7): interrupt-mode alert latch mask; set automatically when SR is read while LHA/RHA active; cleared by writing 0.

### CR2 (01h)
- **DFC** direct/manual fan control (overrides LUT; duty from PWMR).
- **FSST/RDPS** fan-sense type (tach square wave vs RD signal) + RD polarity.
- **FSEnable**: external FF/FS-low forces 100 % duty (two-controller daisy-chain feature).
- **FFMode**: FF/FS as interrupt (latched) vs comparator (live).
- **SPEN** spin-up: 100 % drive until 2 s elapsed or 2 tach pulses seen on each enabled input.
- **ALERTS**: ALERT pin as interrupt (0, latched until serviced) vs comparator/fault-indicator (1, live).
- **STBY** standby: stops sensing/tach/PWM; I²C stays alive.

### CR3 (02h)
- **TACH1E/TACH2E** enable inputs (disabling also clears that fan's fault status + FF/FS).
- **PSEN** pulse-stretch (33 Hz only, requires TACHFULL=0): periodic ~12 s stretched pulse lets tach be measured at low duty.
- **TACHFULL**: measure/fail-detect only at 100 % duty.
- **RAMP[1:0]** duty slew rate: 3.125 / 6.25 / 12.5 %/s, or immediate. Applies to LUT and manual modes.
- **FF_0**: keep fan-fail detection armed at 0 % duty (fans that coast at 0 %).
- **CLRFAIL** (self-clearing): clears TACH1A/TACH2A; deasserts FF/FS in interrupt mode.

### Fault/alert behavior
- **Fault queue**: any fault output (ALERT/FF/FS/SHDN) fires only after **3 consecutive** fault samples.
- **ALERT** (open-drain, pull-up): high-temp alarm (LHS/RHS exceeded). Comparator mode: live. Interrupt mode: latched; service sequence = sense ALERT low → read SR (clears LHA/RHA/LOTA/ROTA, sets ALTMSK) → handle → write ALTMSK=0. 1 °C hysteresis on high alarms.
- **SHDN** (open-drain, active-low): LOTS/ROTS exceeded; 10 °C hysteresis; unaffected by SR reads.
- **Remote diode fault** (SR.RDFA): open/short diode detected; does not trigger ALERT.
- **Standby** saves power; I²C still responsive.

## 6. Operating Modes Summary (driver must support all)

| Mode | Settings | Use |
|---|---|---|
| Auto (LUT) | DFC=0 | Normal closed-loop temp→fan |
| Manual | DFC=1 + PWMR | Host-driven duty |
| 4-wire fan | DRV=11 (25 kHz), PPS per fan, TACHFULL=0, PSEN=x | Standard PC/server fan |
| 3-wire, supply modulation | DRV=00 (33 Hz), PSEN=1 (stretch) or TACHFULL=1 | No PWM input on fan |
| 3-wire, variable DC | DRV=11, regulator FB ← filtered PWM | Silent 3-wire drive |
| Two fans | TACH1E=TACH2E=1, shared PWM | Dual-fan redundancy |
| RD/locked-rotor fans | FSST=1, RDPS per fan | Fans w/o tach pulses |
| Standby | STBY=1 | Power-down sensing |

## 7. Hardware Notes Relevant to Software

- All outputs open-drain ⇒ need external pull-ups (board-provided on the Mikroelektronika Fan 2 Click).
- ALERT/FF/FS/SHDN can be wired to MCU GPIOs for event-driven servicing (optional; driver should also support pure polling).
- EEPROM endurance 1000 cycles @85 °C ⇒ driver should batch config changes and save once (`save_config()`), not save on every setter.
- On POR the chip runs autonomously from EEPROM — software only needs to reconfigure on demand.

## 8. Reference Target Board

MikroElektronika **Fan 2 Click** (mikroe.com/fan-2-click): MAX31760 on mikroBUS; I²C 7-bit address **0x50** (wire 0xA0) per vendor C library and the reference Python driver default; routes PWM, ALERT, FF/FS, SHDN, TACH1/2, DXP/DXN to mikroBUS pins. Driver must treat address as a parameter (0x50–0x57) since A0–A2 are jumperable.
