# 06 — EEPROM timing & live-silicon quirks (bench record)

Date: 2026-11-08. Bench: RPi 3A+ (`fanspeedcontroller`), Linux bcm2835 I2C
driver, MAX31760 rev A at 0x50. This note collects the dated bench
observations that shaped the driver's EEPROM/POR handling. It was carved
out of the `_core.py` docstrings during the 0.1.1 refactor (M8) so the
behavioral docs can state WHAT the code does and WHY in one line, with the
evidence kept here.

## 1. Address NACK stalls while an EEPROM commit lands

While an EEPROM load commits new register values, the MAX31760 genuinely
NACKs its own address — reads of live registers stay working, but ordinary
transactions fail. Observed characteristics:

- Duration is variable: observed from 6 ms to >200 ms; the datasheet bound
  is tW max 550 ms (worst case over the full 80-byte range).
- The stall can begin IMMEDIATELY after a successful write returns, so no
  fixed pre-wait can prevent hitting it.

Design consequence: every public transaction runs through the escalating
retry/backoff ladder (`RETRY_DELAYS_MS`), which spans the datasheet worst
case and absorbs such finite transients transparently; a persistent fault
still raises `OSError` after the final attempt.

## 2. Ack-polling around EEX is unreliable in both directions

The datasheet recommends waiting out tW rather than polling, and the bench
confirmed polling is unsafe:

- Before the EEX command latches, the device ACKs stray probes (a probe can
  race ahead of the command it intends to confirm).
- While a LOAD commits new register values, the device NACKs its own
  address for a variable time — observed up to ~600 ms.

Design consequence: `_wait_eeprom_ready()` waits a FIXED 700 ms
(`EEPROM_WAIT_MS`, above the datasheet worst case) with ZERO bus traffic.
Probes and oracle writes demonstrably interact badly with the silicon
during the commit window. The `_tx` retry ladder remains as a safety net
beyond the guarantee.

## 3. Software POR resets mid-transaction

The POR executes as soon as the CR1.SW_POR bit is latched. The chip resets
so fast that the in-flight I2C write commonly reports an error (errno 121
on Linux bcm2835) even though the reset DID happen. Retrying the write
would fire another POR into a still-booting chip.

Design consequence: `soft_por()` issues the SW_POR write exactly once,
OUTSIDE the normal retry ladder, and swallows any `OSError` from it. It
then polls (10 ms cadence) until the device acknowledges again (bounded by
`settle_ms`; the default 1000 ms covers pathological boot times), verifies
responsiveness, and finally waits out the EEPROM-reload busy window — the
POR performs an implicit EEPROM load, so the same 700 ms fixed wait applies.
`OSError` is raised only if the device never comes back within `settle_ms`.
