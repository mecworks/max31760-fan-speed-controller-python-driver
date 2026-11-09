"""Fault handling, status & fan-sense configuration (B7: F13,F14,F16,F17).

Mixed into MAX31760 (see _core.py). Methods here touch SR (0x5A), MASK
(0x04), FFDC (0x03) and the fault-related bit fields of CR2/CR3. Kept in a
separate module so the protocol core stays focused on transport, math and
the primary control path (size-budget policy, PLANS.md decision 6).
"""
from ._core import (
    REG_SR, REG_MASK, REG_FFDC, REG_CR2, REG_CR3,
    SR_RDFA, SR_ALARM_MASK, MASK_ALARM_FIELD,
    CR3_CLRFAIL, CR3_FF_0,
    CR2_FFMODE, CR2_FSST, CR2_RDPS,
    FF_MODE_INTERRUPT, FF_MODE_COMPARATOR,
    pct_to_duty,
)


class FaultMixin(object):
    """Fault/status/alert-mask/fan-sense methods mixed into MAX31760."""

    # -- status (F16) ----------------------------------------------------------

    def status_raw(self):
        """Read the raw status register (SR, 0x5A).

        WARNING: reading SR CLEARS the latched alarm bits (datasheet); a
        persisting fault re-latches at the next detection. Test the result
        against the SR_* flag constants.
        """
        return self._burst_read(REG_SR, 1)[0]

    def remote_diode_fault(self):
        """True if the remote-diode-fault alarm (RDFA) is latched."""
        return bool(self.status_raw() & SR_RDFA)

    def active_alarms(self):
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

    def set_ffdc_raw(self, raw):
        """Set the fan-fail forced duty cycle (FFDC), raw 0..255."""
        d = int(raw)
        if d < 0 or d > 255:
            raise ValueError("FFDC %d out of range 0..255" % d)
        self._burst_write(REG_FFDC, (d,))

    def set_ffdc_pct(self, pct):
        """Set the fan-fail forced duty cycle (FFDC), percent 0..100."""
        self._burst_write(REG_FFDC, (pct_to_duty(pct),))

    def get_ffdc_raw(self):
        """Current fan-fail forced duty cycle (FFDC), raw 0..255."""
        return self._burst_read(REG_FFDC, 1)[0]

    def set_ff_zero_detection(self, on):
        """Enable/disable fan-fail detection while PWM duty is zero (CR3.FF_0).

        Disable for fans that stop spinning at 0 % duty so an intentional stop
        is not reported as a failure.
        """
        self._cr3_rmw(CR3_FF_0, CR3_FF_0 if on else 0)

    def ff_zero_detection(self):
        """True if fan-fail detection is active at zero duty (CR3.FF_0)."""
        return bool(self._burst_read(REG_CR3, 1)[0] & CR3_FF_0)

    def set_ff_mode(self, mode):
        """Select fan-fail output behaviour (CR2.FFMODE):
        FF_MODE_INTERRUPT (latched until CLRFAIL) or FF_MODE_COMPARATOR
        (follows the live fault condition)."""
        m = int(mode)
        if m not in (FF_MODE_INTERRUPT, FF_MODE_COMPARATOR):
            raise ValueError("unknown FF mode %d" % m)
        self._cr2_rmw(CR2_FFMODE, CR2_FFMODE if m else 0)

    def get_ff_mode(self):
        """Current fan-fail mode (FF_MODE_INTERRUPT or FF_MODE_COMPARATOR)."""
        if self._burst_read(REG_CR2, 1)[0] & CR2_FFMODE:
            return FF_MODE_COMPARATOR
        return FF_MODE_INTERRUPT

    # -- RD / locked-rotor mode (F14) -------------------------------------------

    def set_rd_mode(self, enabled):
        """Select the fan-sense signal type (CR2.FSST): True = RD/
        locked-rotor input on both TACH pins, False = tachometer pulses."""
        self._cr2_rmw(CR2_FSST, CR2_FSST if enabled else 0)

    def rd_mode_enabled(self):
        """True if the TACH inputs expect RD/locked-rotor signals (CR2.FSST)."""
        return bool(self._burst_read(REG_CR2, 1)[0] & CR2_FSST)

    def set_rd_polarity(self, high_means_spinning):
        """Set RD signal polarity (CR2.RDPS): True = RD high means the fan
        is spinning, False = RD low means spinning."""
        self._cr2_rmw(CR2_RDPS, CR2_RDPS if high_means_spinning else 0)

    def get_rd_polarity(self):
        """True if RD high means spinning (CR2.RDPS)."""
        return bool(self._burst_read(REG_CR2, 1)[0] & CR2_RDPS)

    # -- alert mask (F17) --------------------------------------------------------

    def set_alert_mask(self, alarms):
        """Mask/unmask alarm outputs for the given alarms (MASK, 0x04).

        alarms is a bitmask of SR_* flag constants — bit positions match the
        MASK register one-to-one (except RDFA, which has no mask bit because
        it never drives ALERT). Only the six alarm bits are written; the
        reserved upper bits (which should stay 1) are preserved.
        """
        m = int(alarms)
        if m < 0 or m > MASK_ALARM_FIELD:
            raise ValueError("alert mask 0x%02X out of range" % m)
        v = self._burst_read(REG_MASK, 1)[0]
        self._burst_write(REG_MASK, (((v & ~MASK_ALARM_FIELD) | m) & 0xFF,))

    def get_alert_mask(self):
        """Currently masked alarms (bitmask of SR_* flag constants)."""
        return self._burst_read(REG_MASK, 1)[0] & MASK_ALARM_FIELD
