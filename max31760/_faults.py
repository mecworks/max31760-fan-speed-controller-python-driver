"""Fault handling, status & fan-sense configuration (B7: F13,F14,F16,F17).

Mixed into MAX31760 (see _core.py). Methods here touch SR (0x5A), MASK
(0x04), FFDC (0x03) and the fault-related bit fields of CR2/CR3. Kept in a
separate module so the protocol core stays focused on transport, math and
the primary control path (size-budget policy, PLANS.md decision 6).
"""
from ._regs import (
    REG_SR, REG_MASK, REG_FFDC, REG_CR2, REG_CR3,
    SR_RDFA, SR_ALARM_MASK, MASK_ALARM_FIELD,
    CR3_CLRFAIL, CR3_FF_0,
    CR2_FFMODE, CR2_FSST, CR2_RDPS,
    FF_MODE_INTERRUPT, FF_MODE_COMPARATOR,
    pct_to_duty,
)


class FaultMixin:
    """Fault/status/alert-mask/fan-sense methods mixed into MAX31760."""

    # -- status (F16) ----------------------------------------------------------

    def status_raw(self) -> int:
        """Read the raw status register (SR, 0x5A).

        WARNING: reading SR CLEARS the latched alarm bits (datasheet); a
        persisting fault re-latches at the next detection. Test the result
        against the SR_* flag constants.
        """
        return self._burst_read(REG_SR, 1)[0]

    def remote_diode_fault(self) -> bool:
        """True if the remote-diode-fault alarm (RDFA) is latched."""
        return bool(self.status_raw() & SR_RDFA)

    def active_alarms(self) -> int:
        """Read SR and return a compact bitmask of the six alarm bits
        (PC excluded, i.e. SR & SR_ALARM_MASK).

        Consumes the latch exactly like status_raw(): call ONE or the other
        per service cycle, not both — the second read would see an already
        cleared register.
        """
        return self.status_raw() & SR_ALARM_MASK

    # -- fan-fail handling (F13) -----------------------------------------------

    def clear_fan_fail(self):
        """Clear the fan-fail status bits (CR3.CLRFAIL, self-clearing).

        Note: after clearing, a persisting fault takes up to ~8 s to
        re-latch on this silicon (2 s startup grace + fault-queue cadence).
        """
        self._cr3_rmw(CR3_CLRFAIL, CR3_CLRFAIL)

    @property
    def ff_dc_raw(self) -> int:
        """Fan-fail forced duty cycle (FFDC), raw 0..255; assign to set."""
        return self._burst_read(REG_FFDC, 1)[0]

    @ff_dc_raw.setter
    def ff_dc_raw(self, raw: int):
        d = int(raw)
        if d < 0 or d > 255:
            raise ValueError(f"FFDC {d:d} out of range 0..255")
        self._burst_write(REG_FFDC, (d,))

    def set_ffdc_pct(self, pct: float):
        """Set the fan-fail forced duty cycle (FFDC), percent 0..100."""
        self._burst_write(REG_FFDC, (pct_to_duty(pct),))

    @property
    def ff_zero_detection(self) -> bool:
        """Fan-fail detection while PWM duty is zero (CR3.FF_0);
        assign True/False to toggle.

        Disable for fans that stop spinning at 0 % duty so an intentional stop
        is not reported as a failure.
        """
        return bool(self._burst_read(REG_CR3, 1)[0] & CR3_FF_0)

    @ff_zero_detection.setter
    def ff_zero_detection(self, on: bool):
        self._cr3_rmw(CR3_FF_0, CR3_FF_0 if on else 0)

    @property
    def ff_mode(self) -> int:
        """Fan-fail output behaviour (CR2.FFMODE); assign to select:
        FF_MODE_INTERRUPT (latched until CLRFAIL) or FF_MODE_COMPARATOR
        (follows the live fault condition)."""
        if self._burst_read(REG_CR2, 1)[0] & CR2_FFMODE:
            return FF_MODE_COMPARATOR
        return FF_MODE_INTERRUPT

    @ff_mode.setter
    def ff_mode(self, mode: int):
        m = int(mode)
        if m not in (FF_MODE_INTERRUPT, FF_MODE_COMPARATOR):
            raise ValueError(f"unknown FF mode {m:d}")
        self._cr2_rmw(CR2_FFMODE, CR2_FFMODE if m else 0)

    # -- RD / locked-rotor mode (F14) -------------------------------------------

    @property
    def rd_mode(self) -> bool:
        """RD/locked-rotor input mode (CR2.FSST); assign True/False to
        select: True = RD/locked-rotor signal on both TACH pins,
        False = tachometer pulses."""
        return bool(self._burst_read(REG_CR2, 1)[0] & CR2_FSST)

    @rd_mode.setter
    def rd_mode(self, enabled: bool):
        self._cr2_rmw(CR2_FSST, CR2_FSST if enabled else 0)

    @property
    def rd_polarity(self) -> bool:
        """RD signal polarity (CR2.RDPS): True = RD high means the fan
        is spinning, False = RD low means spinning; assign to change."""
        return bool(self._burst_read(REG_CR2, 1)[0] & CR2_RDPS)

    @rd_polarity.setter
    def rd_polarity(self, high_means_spinning: bool):
        self._cr2_rmw(CR2_RDPS, CR2_RDPS if high_means_spinning else 0)

    # -- alert mask (F17) --------------------------------------------------------

    @property
    def alert_mask(self) -> int:
        """Masked alarm outputs (MASK, 0x04); assign a bitmask to change.

        Bit positions match the SR_* flag constants one-to-one (except RDFA,
        which has no mask bit because it never drives ALERT). Only the six
        alarm bits are written; the reserved upper bits (which should stay 1)
        are preserved.
        """
        return self._burst_read(REG_MASK, 1)[0] & MASK_ALARM_FIELD

    @alert_mask.setter
    def alert_mask(self, alarms: int):
        m = int(alarms)
        if m < 0 or m > MASK_ALARM_FIELD:
            raise ValueError(f"alert mask 0x{m:02X} out of range")
        v = self._burst_read(REG_MASK, 1)[0]
        self._burst_write(REG_MASK, (((v & ~MASK_ALARM_FIELD) | m) & 0xFF,))
