"""MicroPython entry point.

Usage (RPi Pico / ESP32):
    import machine
    from max31760.mp import MAX31760
    i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
    dev = MAX31760(i2c, addr=0x50)

Every name in ``__all__`` is importable from this module; the list mirrors
``max31760.cp.__all__`` exactly (enforced by TestApiParity).
"""

from ._core import MAX31760 as _Core
from ._lut import build_lut_curve, lut_index_for_temp
from ._transport_mp import TransportMP
from ._regs import (
    REG_CR1, REG_CR2, REG_CR3, REG_FFDC, REG_MASK, REG_IFR,
    REG_RHSH, REG_RHSL, REG_LOTSH, REG_LOTSL, REG_ROTSH, REG_ROTSL,
    REG_LHSH, REG_LHSL, REG_TCTH, REG_TCTL,
    REG_USER_BASE, REG_USER_END, REG_LUT_BASE, REG_LUT_END,
    REG_PWMR, REG_PWMV, REG_TC1H, REG_TC1L, REG_TC2H, REG_TC2L,
    REG_RTH, REG_RTL, REG_LTH, REG_LTL, REG_SR, REG_EEX,
    ADDR_MIN, ADDR_MAX, PAGE_SIZE, LUT_LEN, USER_LEN,
    RETRY_DELAYS_MS, EEPROM_WAIT_MS, POR_SETTLE_MS,
    CR1_ALTMSK, CR1_SW_POR, CR1_HYST, CR1_DRV_MASK,
    CR1_DRV_33HZ, CR1_DRV_150HZ, CR1_DRV_1P5KHZ, CR1_DRV_25KHZ,
    CR1_PPS_NEGATIVE, CR1_MTI, CR1_TIS,
    INDEX_LOCAL, INDEX_REMOTE, INDEX_MAX,
    CR2_STBY, CR2_ALERTS, CR2_SPEN, CR2_FFMODE, CR2_FSENABLE,
    CR2_RDPS, CR2_FSST, CR2_DFC,
    CR3_CLRFAIL, CR3_FF_0, CR3_RAMP_MASK,
    RAMP_SLOW, RAMP_MED_SLOW, RAMP_MED_FAST, RAMP_IMMEDIATE,
    CR3_TACHFULL, CR3_PSEN, CR3_TACH2E, CR3_TACH1E,
    SR_TACH1A, SR_TACH2A, SR_ROTA, SR_RHA, SR_LOTA, SR_LHA,
    SR_RDFA, SR_PC, SR_ALARM_MASK,
    MASK_ALARM_FIELD, MASK_RESERVED_HI,
    EEX_BLOCK_00_0F, EEX_BLOCK_10_1F, EEX_BLOCK_20_2F,
    EEX_BLOCK_30_3F, EEX_BLOCK_40_4F, EEX_ALL_BLOCKS,
    EEX_LOAD_BIT, EEX_SAVE_ALL, EEX_LOAD_ALL,
    FF_MODE_INTERRUPT, FF_MODE_COMPARATOR,
    ALERT_MODE_INTERRUPT, ALERT_MODE_FAULT_INDICATOR,
    IFR_INDEX_MASK,
    TEMP_LSB_C, TACH_REF_HZ, TACH_AVG_PULSES,
    PWM_FREQ_33HZ, PWM_FREQ_150HZ, PWM_FREQ_1P5KHZ, PWM_FREQ_25KHZ,
    temp_to_raw16, raw16_to_temp, duty_to_pct, pct_to_duty,
    rpm_from_count, count_from_rpm,
)

__all__ = [
    "MAX31760",
    "build_lut_curve", "lut_index_for_temp",
    "REG_CR1", "REG_CR2", "REG_CR3", "REG_FFDC", "REG_MASK", "REG_IFR",
    "REG_RHSH", "REG_RHSL", "REG_LOTSH", "REG_LOTSL",
    "REG_ROTSH", "REG_ROTSL", "REG_LHSH", "REG_LHSL",
    "REG_TCTH", "REG_TCTL",
    "REG_USER_BASE", "REG_USER_END", "REG_LUT_BASE", "REG_LUT_END",
    "REG_PWMR", "REG_PWMV", "REG_TC1H", "REG_TC1L",
    "REG_TC2H", "REG_TC2L", "REG_RTH", "REG_RTL", "REG_LTH", "REG_LTL",
    "REG_SR", "REG_EEX",
    "ADDR_MIN", "ADDR_MAX", "PAGE_SIZE", "LUT_LEN", "USER_LEN",
    "RETRY_DELAYS_MS", "EEPROM_WAIT_MS", "POR_SETTLE_MS",
    "CR1_ALTMSK", "CR1_SW_POR", "CR1_HYST", "CR1_DRV_MASK",
    "CR1_DRV_33HZ", "CR1_DRV_150HZ", "CR1_DRV_1P5KHZ", "CR1_DRV_25KHZ",
    "CR1_PPS_NEGATIVE", "CR1_MTI", "CR1_TIS",
    "INDEX_LOCAL", "INDEX_REMOTE", "INDEX_MAX",
    "CR2_STBY", "CR2_ALERTS", "CR2_SPEN", "CR2_FFMODE", "CR2_FSENABLE",
    "CR2_RDPS", "CR2_FSST", "CR2_DFC",
    "CR3_CLRFAIL", "CR3_FF_0", "CR3_RAMP_MASK",
    "RAMP_SLOW", "RAMP_MED_SLOW", "RAMP_MED_FAST", "RAMP_IMMEDIATE",
    "CR3_TACHFULL", "CR3_PSEN", "CR3_TACH2E", "CR3_TACH1E",
    "SR_TACH1A", "SR_TACH2A", "SR_ROTA", "SR_RHA", "SR_LOTA", "SR_LHA",
    "SR_RDFA", "SR_PC", "SR_ALARM_MASK",
    "MASK_ALARM_FIELD", "MASK_RESERVED_HI",
    "EEX_BLOCK_00_0F", "EEX_BLOCK_10_1F", "EEX_BLOCK_20_2F",
    "EEX_BLOCK_30_3F", "EEX_BLOCK_40_4F", "EEX_ALL_BLOCKS",
    "EEX_LOAD_BIT", "EEX_SAVE_ALL", "EEX_LOAD_ALL",
    "FF_MODE_INTERRUPT", "FF_MODE_COMPARATOR",
    "ALERT_MODE_INTERRUPT", "ALERT_MODE_FAULT_INDICATOR",
    "IFR_INDEX_MASK",
    "TEMP_LSB_C", "TACH_REF_HZ", "TACH_AVG_PULSES",
    "PWM_FREQ_33HZ", "PWM_FREQ_150HZ", "PWM_FREQ_1P5KHZ", "PWM_FREQ_25KHZ",
    "temp_to_raw16", "raw16_to_temp", "duty_to_pct", "pct_to_duty",
    "rpm_from_count", "count_from_rpm",
]


class MAX31760(_Core):
    """MAX31760 driver bound to a MicroPython machine.I2C instance."""

    def __init__(self, i2c, addr=0x50):
        super().__init__(TransportMP(i2c, addr), addr)

    def close(self):
        """No-op on MicroPython (the garbage collector owns the bus);
        provided so portable code can call close() on both platforms."""
        pass
