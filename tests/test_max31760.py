"""Host unit tests for the max31760 package (Phase A scope).

Run from the repo root:  python -m unittest discover tests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mock_i2c import MockChip, MockTransport, FlakyTransport
from fake_smbus import FakeSMBus

from max31760._core import (
    MAX31760,
    temp_to_raw16, raw16_to_temp, duty_to_pct, pct_to_duty,
    rpm_from_count, count_from_rpm,
    REG_CR1, REG_CR2, REG_CR3, REG_FFDC, REG_MASK, REG_IFR,
    REG_RHSH, REG_RHSL, REG_LOTSH, REG_LOTSL, REG_ROTSH, REG_ROTSL,
    REG_LHSH, REG_LHSL, REG_TCTH, REG_TCTL,
    REG_USER_BASE, REG_USER_END, REG_LUT_BASE, REG_LUT_END,
    REG_PWMR, REG_PWMV, REG_SR, REG_EEX, REG_LTH, REG_LTL,
    REG_RTH, REG_RTL,
    ADDR_MIN, ADDR_MAX, PAGE_SIZE, LUT_LEN, USER_LEN, RETRY_DELAYS_MS,
    EEPROM_WAIT_MS,
    CR1_MTI, CR1_TIS, CR1_HYST, CR1_PPS_NEGATIVE, CR1_SW_POR,
    CR1_DRV_MASK, CR1_DRV_33HZ, CR1_DRV_150HZ, CR1_DRV_1P5KHZ, CR1_DRV_25KHZ,
    REG_CR3, CR3_RAMP_MASK,
    REG_TCTH, REG_TCTL, REG_TC1H, REG_TC1L, REG_TC2H, REG_TC2L,
    REG_MASK, REG_FFDC, MASK_ALARM_FIELD,
    SR_TACH1A, SR_TACH2A, SR_ROTA, SR_RHA, SR_LOTA, SR_LHA, SR_RDFA, SR_PC,
    SR_ALARM_MASK, FF_MODE_INTERRUPT, FF_MODE_COMPARATOR,
    ALERT_MODE_INTERRUPT, ALERT_MODE_FAULT_INDICATOR, IFR_INDEX_MASK,
    IDEALITY_TABLE,
    EEX_BLOCK_00_0F, EEX_BLOCK_10_1F, EEX_BLOCK_20_2F,
    EEX_BLOCK_30_3F, EEX_BLOCK_40_4F, EEX_ALL_BLOCKS,
    USER_FACTORY_VALUE,
    CR3_TACH1E, CR3_TACH2E, CR3_PSEN,
    INDEX_LOCAL, INDEX_REMOTE, INDEX_MAX,
    RAMP_SLOW, RAMP_MED_SLOW, RAMP_MED_FAST, RAMP_IMMEDIATE,
    PWM_FREQ_33HZ, PWM_FREQ_150HZ, PWM_FREQ_1P5KHZ, PWM_FREQ_25KHZ,
    SR_ALARM_MASK, MASK_RESERVED_HI,
    EEX_SAVE_ALL, EEX_LOAD_ALL, EEX_ALL_BLOCKS,
    FACTORY_DEFAULTS, IDEALITY_TABLE, TACH_REF_HZ,
)
from max31760._transport_cp import TransportCP
from max31760._lut import lut_index_for_temp, build_lut_curve


class TestConstants(unittest.TestCase):
    def test_address_range(self):
        self.assertEqual(ADDR_MIN, 0x50)
        self.assertEqual(ADDR_MAX, 0x57)

    def test_register_layout(self):
        self.assertEqual(REG_LUT_BASE, 0x20)
        self.assertEqual(REG_LUT_END, 0x4F)
        self.assertEqual(REG_LUT_END - REG_LUT_BASE + 1, LUT_LEN)
        self.assertEqual(LUT_LEN, 48)
        self.assertEqual(REG_USER_END - REG_USER_BASE + 1, USER_LEN)
        self.assertEqual(USER_LEN, 8)
        self.assertEqual(REG_SR, 0x5A)
        self.assertEqual(REG_EEX, 0x5B)

    def test_factory_defaults_decode(self):
        d = FACTORY_DEFAULTS
        self.assertEqual(raw16_to_temp((d[REG_RHSH] << 8) | d[REG_RHSL]), 85.0)
        self.assertEqual(raw16_to_temp((d[REG_LOTSH] << 8) | d[REG_LOTSL]), 85.0)
        self.assertEqual(raw16_to_temp((d[REG_ROTSH] << 8) | d[REG_ROTSL]), 110.0)
        self.assertEqual(raw16_to_temp((d[REG_LHSH] << 8) | d[REG_LHSL]), 70.0)
        self.assertEqual((d[REG_TCTH] << 8) | d[REG_TCTL], 0xFFFE)
        self.assertEqual(d[REG_CR1], 0x01)   # live-verified on bench
        self.assertEqual(d[REG_CR2], 0x10)
        self.assertEqual(d[REG_CR3], 0x03)
        self.assertEqual(d[REG_FFDC], 0xFF)
        self.assertEqual(d[REG_MASK], 0xC0)
        self.assertEqual(d[REG_IFR], 0x18)

    def test_ideality_table(self):
        self.assertEqual(len(IDEALITY_TABLE), 64)
        self.assertAlmostEqual(IDEALITY_TABLE[0x00], 0.9844)
        self.assertAlmostEqual(IDEALITY_TABLE[0x18], 1.0080)  # factory default
        self.assertAlmostEqual(IDEALITY_TABLE[0x3F], 1.0489)
        for i in range(1, 64):
            self.assertGreater(IDEALITY_TABLE[i], IDEALITY_TABLE[i - 1])

    def test_ramp_ordering(self):
        self.assertEqual(RAMP_SLOW, 0x00)
        self.assertEqual(RAMP_MED_SLOW, 0x10)
        self.assertEqual(RAMP_MED_FAST, 0x20)
        self.assertEqual(RAMP_IMMEDIATE, 0x30)

    def test_drv_bit_positions(self):
        # Regression: datasheet reg 00h places DRV on bits [4:3].
        self.assertEqual(CR1_DRV_MASK, 0x18)
        self.assertEqual(CR1_DRV_33HZ, 0x00)
        self.assertEqual(CR1_DRV_150HZ, 0x08)
        self.assertEqual(CR1_DRV_1P5KHZ, 0x10)
        self.assertEqual(CR1_DRV_25KHZ, 0x18)
        for v in (CR1_DRV_33HZ, CR1_DRV_150HZ, CR1_DRV_1P5KHZ, CR1_DRV_25KHZ):
            self.assertEqual(v & ~CR1_DRV_MASK, 0)

    def test_index_encodings(self):
        self.assertEqual(INDEX_LOCAL & (CR1_MTI | CR1_TIS), 0x00)
        self.assertEqual(INDEX_REMOTE & (CR1_MTI | CR1_TIS), CR1_TIS)
        self.assertTrue(INDEX_MAX & CR1_MTI)

    def test_eex_constants(self):
        self.assertEqual(EEX_ALL_BLOCKS, 0x1F)
        self.assertEqual(EEX_SAVE_ALL, 0x1F)
        self.assertEqual(EEX_LOAD_ALL, 0x9F)
        self.assertEqual(SR_ALARM_MASK, 0x7F)
        self.assertEqual(MASK_RESERVED_HI, 0xC0)


class TestTempMath(unittest.TestCase):
    VECTORS = [(-128.0, 0x8000), (-55.0, 0xC900), (-25.0, 0xE700),
               (-1.0, 0xFF00), (-0.125, 0xFFE0), (0.0, 0x0000),
               (0.125, 0x0020), (1.0, 0x0100), (25.0, 0x1900),
               (85.0, 0x5500), (110.0, 0x6E00), (125.0, 0x7D00),
               (127.875, 0x7FE0)]

    def test_encode_vectors(self):
        for celsius, raw in self.VECTORS:
            self.assertEqual(temp_to_raw16(celsius), raw,
                             msg="encode %.3f" % celsius)

    def test_round_trip(self):
        for celsius, _ in self.VECTORS:
            self.assertEqual(raw16_to_temp(temp_to_raw16(celsius)), celsius)

    def test_decode_vectors(self):
        for celsius, raw in self.VECTORS:
            self.assertEqual(raw16_to_temp(raw), celsius,
                             msg="decode %04X" % raw)
        # Largest possible raw decodes to the max temperature (bits 4:0 unused).
        self.assertEqual(raw16_to_temp(0x7FFF), 127.875)

    def test_out_of_range_raises(self):
        self.assertRaises(ValueError, temp_to_raw16, -128.0625)
        self.assertRaises(ValueError, temp_to_raw16, 127.9375)
        self.assertRaises(ValueError, temp_to_raw16, 200.0)
        self.assertRaises(ValueError, temp_to_raw16, -200.0)


class TestDutyMath(unittest.TestCase):
    def test_duty_to_pct(self):
        self.assertEqual(duty_to_pct(0), 0.0)
        self.assertEqual(duty_to_pct(128), 50.0)
        self.assertAlmostEqual(duty_to_pct(255), 99.609375)
        self.assertRaises(ValueError, duty_to_pct, -1)
        self.assertRaises(ValueError, duty_to_pct, 256)

    def test_pct_to_duty(self):
        self.assertEqual(pct_to_duty(0.0), 0)
        self.assertEqual(pct_to_duty(50.0), 128)
        self.assertEqual(pct_to_duty(100.0), 255)
        self.assertEqual(pct_to_duty(25.0), 64)
        self.assertRaises(ValueError, pct_to_duty, -0.1)
        self.assertRaises(ValueError, pct_to_duty, 100.1)


class TestRpmMath(unittest.TestCase):
    def test_known_value(self):
        # 100 kHz / 1000 ticks-per-pulse = 100 pulses/s; /2 per rev * 60 = 3000 RPM
        self.assertEqual(rpm_from_count(1000, 2), 3000.0)

    def test_zero_count_is_stopped(self):
        self.assertEqual(rpm_from_count(0, 2), 0.0)
        self.assertEqual(rpm_from_count(-5, 2), 0.0)

    def test_inverse(self):
        self.assertEqual(count_from_rpm(3000.0, 2), 1000)
        self.assertEqual(count_from_rpm(6000.0, 2), 500)

    def test_clamp_and_errors(self):
        self.assertEqual(count_from_rpm(1.0, 2), 0xFFFF)
        self.assertRaises(ValueError, count_from_rpm, 0.0, 2)
        self.assertRaises(ValueError, count_from_rpm, -1.0, 2)
        self.assertRaises(ValueError, rpm_from_count, 100, 0)
        self.assertRaises(ValueError, count_from_rpm, 100.0, 0)
        self.assertEqual(TACH_REF_HZ, 100000)


def make_dev(chip=None, transport=None, addr=0x50):
    chip = chip if chip is not None else MockChip()
    transport = transport if transport is not None else MockTransport(chip)
    return MAX31760(transport, addr), chip, transport


class TestConstructorBounds(unittest.TestCase):
    def test_valid_addresses(self):
        dev, _, _ = make_dev(addr=0x50)
        self.assertEqual(dev._addr, 0x50)
        dev, _, _ = make_dev(addr=0x57)
        self.assertEqual(dev._addr, 0x57)

    def test_invalid_addresses_raise(self):
        self.assertRaises(ValueError, make_dev, addr=0x4F)
        self.assertRaises(ValueError, make_dev, addr=0x58)
        self.assertRaises(ValueError, make_dev, addr=0x00)


class TestPageSafeWrite(unittest.TestCase):
    def test_nine_byte_unaligned_split(self):
        dev, chip, tr = make_dev()
        data = bytes(range(0xA0, 0xA9))          # 9 bytes @ 0x10
        dev.write_reg(0x10, data)
        writes = [t for t in chip.txns if t[0] == "w"]
        self.assertEqual(writes, [("w", 0x10, 8), ("w", 0x18, 1)])
        self.assertEqual(bytes(chip.regs[0x10:0x19]), data)
        self.assertEqual(chip.violations, [])

    def test_full_lut_write(self):
        dev, chip, _ = make_dev()
        lut = bytes((i * 5) & 0xFF for i in range(48))
        dev.write_reg(REG_LUT_BASE, lut)
        writes = [t for t in chip.txns if t[0] == "w"]
        self.assertEqual(len(writes), 6)
        for w in writes:
            self.assertEqual(w[2], 8)
            self.assertEqual(w[1] % PAGE_SIZE, 0)
        self.assertEqual(bytes(chip.regs[0x20:0x50]), lut)
        self.assertEqual(chip.violations, [])

    def test_mid_page_multi_row(self):
        dev, chip, _ = make_dev()
        data = bytes(range(0x10, 0x1C))          # 12 bytes @ 0x12
        dev.write_reg(0x12, data)
        writes = [t for t in chip.txns if t[0] == "w"]
        self.assertEqual(writes, [("w", 0x12, 6), ("w", 0x18, 6)])
        self.assertEqual(bytes(chip.regs[0x12:0x1E]), data)
        self.assertEqual(chip.violations, [])

    def test_mock_wraps_on_illegal_chunk(self):
        # Prove the mock faithfully emulates the chip hazard: a 9-byte
        # unchunked write wraps within the page and scatters data.
        chip = MockChip()
        before = bytes(chip.regs[0x10:0x19])
        chip.burst_write(0x10, bytes(range(9)))
        self.assertNotEqual(bytes(chip.regs[0x10:0x19]), before)
        self.assertEqual(len(chip.violations), 1)

    def test_bounds_checks(self):
        dev, chip, _ = make_dev()
        # read past SR (0x5A)
        self.assertRaises(ValueError, dev.read_reg, 0x5A, 2)
        self.assertRaises(ValueError, dev.read_reg, 0x5B, 1)
        self.assertRaises(ValueError, dev.read_reg, 0x00, 0)
        # write past EEX (0x5B)
        self.assertRaises(ValueError, dev.write_reg, 0x5A, b"\x00\x00")
        self.assertRaises(ValueError, dev.write_reg, 0x5C, b"\x00")
        self.assertRaises(ValueError, dev.write_reg, 0x00, b"")
        # legal edges
        self.assertEqual(len(dev.read_reg(0x00, 0x5B)), 0x5B)
        dev.write_reg(0x5B, b"\x1F")             # EEX alone is writable
        self.assertEqual(chip.regs[0x5B], 0x1F)
        # writes may never touch the RO status register
        self.assertRaises(ValueError, dev.write_reg, 0x5A, b"\x00")


class TestRetryAndProbe(unittest.TestCase):
    def test_transient_nack_then_success(self):
        chip = MockChip()
        tr = FlakyTransport(chip, fails=1)
        dev = MAX31760(tr, 0x50)
        val = dev.read_reg(REG_LTH, 2)
        self.assertEqual(len(val), 2)
        self.assertEqual(tr.delays, [RETRY_DELAYS_MS[0]])

    def test_transient_burst_absorbed_by_escalating_backoff(self):
        # Regression (2026-11-08, RPi 3A+): an EEPROM load committing new
        # register values NACKs bus traffic for up to ~45 ms, and the stall
        # can begin immediately after a successful write - so readiness
        # pre-waits alone cannot prevent hitting it; the escalating
        # backoffs must absorb it.
        chip = MockChip()
        tr = FlakyTransport(chip, fails=2)
        dev = MAX31760(tr, 0x50)
        val = dev.read_reg(REG_LTH, 2)
        self.assertEqual(len(val), 2)
        self.assertEqual(tr.delays, list(RETRY_DELAYS_MS[:2]))

    def test_long_commit_stall_absorbed(self):
        # Same regression, worst observed case (~41 ms stall): three
        # consecutive NACKed attempts need the third backoff (60 ms) to
        # land clear of the window.
        chip = MockChip()
        tr = FlakyTransport(chip, fails=3)
        dev = MAX31760(tr, 0x50)
        val = dev.read_reg(REG_LTH, 2)
        self.assertEqual(len(val), 2)
        self.assertEqual(tr.delays, list(RETRY_DELAYS_MS[:3]))

    def test_full_tw_worst_case_stall_absorbed(self):
        # Datasheet worst case: a commit stall lasting up to tW max
        # (550 ms) must be ridden out by the full backoff ladder
        # (cumulative span 600 ms > 550 ms).
        chip = MockChip()
        tr = FlakyTransport(chip, fails=len(RETRY_DELAYS_MS))
        dev = MAX31760(tr, 0x50)
        val = dev.read_reg(REG_LTH, 2)
        self.assertEqual(len(val), 2)
        self.assertEqual(tr.delays, list(RETRY_DELAYS_MS))

    def test_persistent_failure_propagates(self):
        chip = MockChip()
        tr = FlakyTransport(chip, fails=99)
        dev = MAX31760(tr, 0x50)
        self.assertRaises(OSError, dev.read_reg, REG_LTH, 2)
        self.assertEqual(tr.delays, list(RETRY_DELAYS_MS))  # all retries used

    def test_probe(self):
        chip = MockChip()
        dev, _, _ = make_dev(chip=chip)
        self.assertTrue(dev.probe())
        chip.nack = True
        self.assertFalse(dev.probe())


class TestInitSelfTest(unittest.TestCase):
    """B1: constructor + init/self-test (F1)."""

    def test_scan_lists_present_devices(self):
        chip = MockChip(addrs=[0x50, 0x62])
        dev, _, _ = make_dev(chip=chip)
        self.assertEqual(dev.scan(), [0x50, 0x62])

    def test_verify_passes_when_present(self):
        dev, _, _ = make_dev()
        self.assertTrue(dev.verify())

    def test_verify_raises_when_absent(self):
        chip = MockChip()                       # nothing at 0x51
        tr = MockTransport(chip, addr=0x51)
        dev = MAX31760(tr, 0x51)
        self.assertRaises(OSError, dev.verify)

    def test_probe_false_when_absent(self):
        chip = MockChip()
        tr = MockTransport(chip, addr=0x51)
        dev = MAX31760(tr, 0x51)
        self.assertFalse(dev.probe())


class TestTemperatures(unittest.TestCase):
    """B2: temperature getters (F2)."""

    def test_local_temp_live_bench_vector(self):
        dev, chip, _ = make_dev()
        chip.regs[REG_LTH] = 0x1A
        chip.regs[REG_LTL] = 0x80               # raw 1A80 = +26.5 C (bench)
        self.assertEqual(dev.local_temp_c, 26.5)

    def test_remote_temp_negative(self):
        dev, chip, _ = make_dev()
        chip.regs[REG_RTH] = 0xFF
        chip.regs[REG_RTL] = 0xE0               # raw FFE0 = -0.125 C
        self.assertEqual(dev.remote_temp_c, -0.125)

    def test_temps_are_fresh_each_access(self):
        dev, chip, _ = make_dev()
        chip.regs[REG_LTH] = 0x19
        chip.regs[REG_LTL] = 0x00
        self.assertEqual(dev.local_temp_c, 25.0)
        chip.regs[REG_LTH] = 0x1A                # no LSB change -> 26.0 C
        self.assertEqual(dev.local_temp_c, 26.0)


class TestSetpoints(unittest.TestCase):
    """B2: four setpoint get/set pairs (F3)."""

    PAIRS = [
        ("local_high", REG_LHSH, REG_LHSL),
        ("remote_high", REG_RHSH, REG_RHSL),
        ("local_overtemp", REG_LOTSH, REG_LOTSL),
        ("remote_overtemp", REG_ROTSH, REG_ROTSL),
    ]

    def test_factory_defaults_decode(self):
        dev, _, _ = make_dev()
        self.assertEqual(dev.get_local_high(), 70.0)
        self.assertEqual(dev.get_remote_high(), 85.0)
        self.assertEqual(dev.get_local_overtemp(), 85.0)
        self.assertEqual(dev.get_remote_overtemp(), 110.0)

    def test_set_get_roundtrip_all_four(self):
        dev, chip, _ = make_dev()
        vals = {"local_high": 60.5, "remote_high": 90.0,
                "local_overtemp": 95.25, "remote_overtemp": 105.0}
        for name, hi, lo in self.PAIRS:
            getattr(dev, "set_" + name)(vals[name])
            self.assertEqual(getattr(dev, "get_" + name)(), vals[name],
                             msg=name)
            raw = (chip.regs[hi] << 8) | chip.regs[lo]
            self.assertEqual(raw, temp_to_raw16(vals[name]), msg=name)

    def test_negative_setpoint_encoding(self):
        dev, chip, _ = make_dev()
        dev.set_local_high(-10.0)
        self.assertEqual(dev.get_local_high(), -10.0)
        raw = (chip.regs[REG_LHSH] << 8) | chip.regs[REG_LHSL]
        self.assertEqual(raw, 0xF600)            # q=-80 -> (-80<<5)&0xFFFF

    def test_wire_level_single_aligned_write(self):
        dev, chip, _ = make_dev()
        dev.set_remote_overtemp(110.0)
        writes = [t for t in chip.txns if t[0] == "w"]
        self.assertEqual(writes, [("w", REG_ROTSH, 2)])
        self.assertEqual(chip.violations, [])

    def test_out_of_range_raises(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.set_local_high, 128.0)
        self.assertRaises(ValueError, dev.set_remote_high, -128.125)
        self.assertRaises(ValueError, dev.set_local_overtemp, 200.0)
        self.assertRaises(ValueError, dev.set_remote_overtemp, -200.0)


class TestLutIndexForTemp(unittest.TestCase):
    """B3: temperature -> LUT window mapping (F5)."""

    VECTORS = [(-50.0, 0), (0.0, 0), (17.9, 0), (18.0, 1), (19.9, 1),
               (20.0, 2), (26.6, 5), (100.0, 42), (109.9, 46),
               (110.0, 47), (115.0, 47), (200.0, 47)]

    def test_vectors(self):
        for t, idx in self.VECTORS:
            self.assertEqual(lut_index_for_temp(t), idx, msg=str(t))


class TestBuildLutCurve(unittest.TestCase):
    """B3: monotonic curve builder utility (F5)."""

    def test_flat_half(self):
        lut = build_lut_curve([(0.0, 50.0), (120.0, 50.0)])
        self.assertEqual(len(lut), 48)
        self.assertTrue(all(v == 128 for v in lut))

    def test_linear_ramp_values(self):
        # 0 % at 20 C -> 100 % at 60 C; window midpoints are 17 + 2*i.
        lut = build_lut_curve([(20.0, 0.0), (60.0, 100.0)])
        self.assertEqual(lut[lut_index_for_temp(19.0)], 0)     # below start
        self.assertEqual(lut[2], 6)                            # t=21 -> 2.5 %
        self.assertEqual(lut[11], 122)                         # t=39 -> 47.5 %
        self.assertEqual(lut[21], 250)                         # t=59 -> 97.5 %
        self.assertEqual(lut[22], 255)                         # t=61 -> clamped
        self.assertEqual(lut[47], 255)

    def test_monotonic_non_decreasing(self):
        lut = build_lut_curve([(10.0, 5.0), (40.0, 60.0), (90.0, 100.0)])
        for i in range(1, 48):
            self.assertGreaterEqual(lut[i], lut[i - 1])

    def test_bad_inputs_raise(self):
        self.assertRaises(ValueError, build_lut_curve, [(20.0, 50.0)])
        self.assertRaises(ValueError, build_lut_curve, [])
        self.assertRaises(ValueError, build_lut_curve,
                          [(40.0, 50.0), (20.0, 60.0)])
        self.assertRaises(ValueError, build_lut_curve,
                          [(20.0, 50.0), (20.0, 60.0)])
        self.assertRaises(ValueError, build_lut_curve,
                          [(20.0, -1.0), (40.0, 50.0)])
        self.assertRaises(ValueError, build_lut_curve,
                          [(20.0, 50.0), (40.0, 101.0)])


class TestLutAccess(unittest.TestCase):
    """B3: LUT bulk/single get/set (F4)."""

    def test_factory_default_is_all_ff(self):
        dev, _, _ = make_dev()
        lut = dev.lut_get()
        self.assertEqual(len(lut), 48)
        self.assertTrue(all(v == 0xFF for v in lut))

    def test_bulk_set_wire_level(self):
        dev, chip, _ = make_dev()
        lut = bytes((i * 5) & 0xFF for i in range(48))
        dev.lut_set(lut)
        writes = [t for t in chip.txns if t[0] == "w"]
        self.assertEqual(len(writes), 6)
        for w in writes:
            self.assertEqual(w[2], 8)
            self.assertEqual(w[1] % PAGE_SIZE, 0)
        self.assertEqual(dev.lut_get(), list(lut))
        self.assertEqual(chip.violations, [])

    def test_bulk_set_rejects_bad_length_and_values(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.lut_set, [0] * 47)
        self.assertRaises(ValueError, dev.lut_set, [0] * 49)
        self.assertRaises(ValueError, dev.lut_set, [0] * 47 + [-1])
        self.assertRaises(ValueError, dev.lut_set, [0] * 47 + [256])

    def test_single_entry_roundtrip(self):
        dev, chip, _ = make_dev()
        dev.lut_set_index(12, 200)
        self.assertEqual(dev.lut_get_index(12), 200)
        self.assertEqual(chip.regs[REG_LUT_BASE + 12], 200)
        self.assertEqual(dev.lut_get_index(11), 0xFF)   # neighbours untouched

    def test_single_entry_bounds(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.lut_get_index, -1)
        self.assertRaises(ValueError, dev.lut_get_index, 48)
        self.assertRaises(ValueError, dev.lut_set_index, -1, 100)
        self.assertRaises(ValueError, dev.lut_set_index, 48, 100)
        self.assertRaises(ValueError, dev.lut_set_index, 0, -1)
        self.assertRaises(ValueError, dev.lut_set_index, 0, 256)


class TestManualMode(unittest.TestCase):
    """B4: manual/auto mode + direct duty (F6)."""

    def test_manual_enable_roundtrip_preserves_other_bits(self):
        dev, chip, _ = make_dev()
        self.assertFalse(dev.manual_enabled())
        dev.manual_enable(True)
        self.assertTrue(dev.manual_enabled())
        self.assertEqual(chip.regs[REG_CR2], 0x11)   # factory 0x10 | DFC
        dev.manual_enable(False)
        self.assertFalse(dev.manual_enabled())
        self.assertEqual(chip.regs[REG_CR2], 0x10)   # restored exactly

    def test_set_duty_pct_and_raw(self):
        dev, chip, _ = make_dev()
        dev.set_duty_pct(50.0)
        self.assertEqual(chip.regs[REG_PWMR], 128)
        self.assertEqual(dev.get_duty_cmd_raw(), 128)
        dev.set_duty_raw(200)
        self.assertEqual(chip.regs[REG_PWMR], 200)
        dev.set_duty_pct(100.0)
        self.assertEqual(chip.regs[REG_PWMR], 255)
        dev.set_duty_pct(0.0)
        self.assertEqual(chip.regs[REG_PWMR], 0)

    def test_set_duty_validation(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.set_duty_pct, -0.1)
        self.assertRaises(ValueError, dev.set_duty_pct, 100.1)
        self.assertRaises(ValueError, dev.set_duty_raw, -1)
        self.assertRaises(ValueError, dev.set_duty_raw, 256)

    def test_actual_duty_readback(self):
        dev, chip, _ = make_dev()
        chip.regs[REG_PWMV] = 0x80                   # RO register, mock-seeded
        self.assertEqual(dev.get_actual_duty_raw(), 128)
        self.assertEqual(dev.get_actual_duty_pct(), 50.0)


class TestAutoConfig(unittest.TestCase):
    """B4: index source + hysteresis (F7)."""

    def test_index_source_all_three(self):
        dev, chip, _ = make_dev()
        for src in (INDEX_LOCAL, INDEX_REMOTE, INDEX_MAX):
            dev.set_index_source(src)
            self.assertEqual(dev.get_index_source(), src)
            self.assertEqual(chip.regs[REG_CR1] & 0x03, src)
        # factory default is remote-index (CR1 = 0x01)
        dev.write_reg(REG_CR1, bytes([0x01]))
        self.assertEqual(dev.get_index_source(), INDEX_REMOTE)

    def test_index_source_rejects_reserved(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.set_index_source, 0x02)  # reserved
        self.assertRaises(ValueError, dev.set_index_source, 0x04)

    def test_index_source_preserves_other_cr1_bits(self):
        dev, chip, _ = make_dev()
        dev.write_reg(REG_CR1, bytes([0x20]))         # HYST set, others clear
        dev.set_index_source(INDEX_MAX)
        self.assertEqual(chip.regs[REG_CR1], 0x23)    # HYST kept, bits[1:0]=03

    def test_hysteresis_roundtrip(self):
        dev, chip, _ = make_dev()
        self.assertEqual(dev.get_hysteresis_c(), 2)   # factory default
        dev.set_hysteresis_c(4)
        self.assertEqual(dev.get_hysteresis_c(), 4)
        self.assertEqual(chip.regs[REG_CR1] & CR1_HYST, CR1_HYST)
        dev.set_hysteresis_c(2)
        self.assertEqual(dev.get_hysteresis_c(), 2)
        self.assertEqual(chip.regs[REG_CR1] & CR1_HYST, 0)

    def test_hysteresis_rejects_others(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.set_hysteresis_c, 3)
        self.assertRaises(ValueError, dev.set_hysteresis_c, 1)


class TestPwmConfig(unittest.TestCase):
    """B4: PWM frequency + polarity (F8)."""

    def test_freq_all_four(self):
        dev, _, _ = make_dev()
        for hz in (PWM_FREQ_33HZ, PWM_FREQ_150HZ, PWM_FREQ_1P5KHZ, PWM_FREQ_25KHZ):
            dev.set_pwm_freq_hz(hz)
            self.assertEqual(dev.get_pwm_freq_hz(), hz)

    def test_freq_bit_values(self):
        dev, chip, _ = make_dev()
        dev.set_pwm_freq_hz(PWM_FREQ_33HZ)
        self.assertEqual(chip.regs[REG_CR1] & CR1_DRV_MASK, CR1_DRV_33HZ)
        dev.set_pwm_freq_hz(PWM_FREQ_150HZ)
        self.assertEqual(chip.regs[REG_CR1] & CR1_DRV_MASK, CR1_DRV_150HZ)
        dev.set_pwm_freq_hz(PWM_FREQ_1P5KHZ)
        self.assertEqual(chip.regs[REG_CR1] & CR1_DRV_MASK, CR1_DRV_1P5KHZ)
        dev.set_pwm_freq_hz(PWM_FREQ_25KHZ)
        self.assertEqual(chip.regs[REG_CR1] & CR1_DRV_MASK, CR1_DRV_25KHZ)

    def test_freq_rejects_unsupported(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.set_pwm_freq_hz, 1000)
        self.assertRaises(ValueError, dev.set_pwm_freq_hz, 0)

    def test_polarity_roundtrip(self):
        dev, chip, _ = make_dev()
        self.assertEqual(dev.get_pwm_polarity(), MAX31760.POLARITY_POSITIVE)
        dev.set_pwm_polarity(MAX31760.POLARITY_NEGATIVE)
        self.assertEqual(dev.get_pwm_polarity(), MAX31760.POLARITY_NEGATIVE)
        self.assertEqual(chip.regs[REG_CR1] & CR1_PPS_NEGATIVE, CR1_PPS_NEGATIVE)
        dev.set_pwm_polarity(MAX31760.POLARITY_POSITIVE)
        self.assertEqual(dev.get_pwm_polarity(), MAX31760.POLARITY_POSITIVE)
        self.assertEqual(chip.regs[REG_CR1] & CR1_PPS_NEGATIVE, 0)

    def test_polarity_rejects_bad_value(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.set_pwm_polarity, 2)

    def test_class_constants_match_module(self):
        self.assertEqual(MAX31760.INDEX_MAX, INDEX_MAX)
        self.assertEqual(MAX31760.RAMP_IMMEDIATE, RAMP_IMMEDIATE)
        self.assertEqual(MAX31760.PWM_FREQ_25KHZ, PWM_FREQ_25KHZ)
        self.assertEqual(MAX31760.POLARITY_NEGATIVE, 1)


class TestRampRate(unittest.TestCase):
    """B5: ramp rate + wait_for_duty (F9)."""

    def test_ramp_rate_all_four_preserve_other_bits(self):
        dev, chip, _ = make_dev()
        self.assertEqual(dev.get_ramp_rate(), RAMP_SLOW)   # factory CR3=0x03
        for r in (RAMP_MED_SLOW, RAMP_MED_FAST, RAMP_IMMEDIATE, RAMP_SLOW):
            dev.set_ramp_rate(r)
            self.assertEqual(dev.get_ramp_rate(), r)
            self.assertEqual(chip.regs[REG_CR3], 0x03 | r)  # TACH bits kept

    def test_ramp_rate_rejects_unknown(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.set_ramp_rate, 0x40)
        self.assertRaises(ValueError, dev.set_ramp_rate, 0x08)

    def test_wait_for_duty_immediate_hit(self):
        dev, chip, tr = make_dev()
        chip.regs[REG_PWMV] = 128
        self.assertTrue(dev.wait_for_duty(50.0, timeout_ms=100))
        self.assertEqual(tr.delays, [])          # hit on first poll

    def test_wait_for_duty_timeout(self):
        dev, chip, tr = make_dev()
        chip.regs[REG_PWMV] = 255                # mock never slews
        self.assertRaises(TimeoutError, dev.wait_for_duty, 50.0, 30)
        self.assertGreater(len(tr.delays), 0)    # actually polled

    def test_wait_for_duty_bad_args(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.wait_for_duty, 50.0, -1)
        self.assertRaises(ValueError, dev.wait_for_duty, 101.0, 100)


class TestTachometer(unittest.TestCase):
    """B6: tach enable + RPM reads + threshold (F11,F12)."""

    def test_tach_enable_roundtrips_preserve_other_bits(self):
        dev, chip, _ = make_dev()
        self.assertTrue(dev.tach1_enabled())      # factory CR3=0x03
        self.assertTrue(dev.tach2_enabled())
        dev.tach1_enable(False)
        self.assertFalse(dev.tach1_enabled())
        self.assertTrue(dev.tach2_enabled())      # untouched
        self.assertEqual(chip.regs[REG_CR3], 0x02)
        dev.tach2_enable(False)
        self.assertEqual(chip.regs[REG_CR3], 0x00)
        dev.tach1_enable(True)
        dev.tach2_enable(True)
        self.assertEqual(chip.regs[REG_CR3], 0x03)  # restored exactly

    def test_rpm_port1_math(self):
        dev, chip, _ = make_dev()
        chip.regs[REG_TC1H] = 0x01
        chip.regs[REG_TC1L] = 0xF4            # count = 500
        self.assertAlmostEqual(dev.rpm(1, 2), 6000000.0 / (500 * 2))
        self.assertAlmostEqual(dev.rpm(1, 4), 6000000.0 / (500 * 4))

    def test_rpm_zero_count_returns_zero(self):
        dev, chip, _ = make_dev()
        chip.regs[REG_TC1H] = 0x00
        chip.regs[REG_TC1L] = 0x00
        self.assertEqual(dev.rpm(1, 2), 0.0)   # no div-by-zero (upstream B4)

    def test_rpm_port2_uses_tc2_regs(self):
        dev, chip, _ = make_dev()
        chip.regs[REG_TC2H] = 0x02
        chip.regs[REG_TC2L] = 0xE8            # count = 744
        self.assertAlmostEqual(dev.rpm(2, 2), 6000000.0 / (744 * 2))
        # port-1 registers must not leak into the port-2 read
        chip.regs[REG_TC1H] = 0xAB
        chip.regs[REG_TC1L] = 0xCD
        self.assertAlmostEqual(dev.rpm(2, 2), 6000000.0 / (744 * 2))

    def test_rpm_bad_args(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.rpm, 3, 2)
        self.assertRaises(ValueError, dev.rpm, 1, 0)

    def test_threshold_roundtrip_and_wire_bytes(self):
        dev, chip, _ = make_dev()
        self.assertEqual(dev.get_tach_threshold(), 0xFFFE)  # factory
        for val in (0, 1, 40000, 65535):
            dev.set_tach_threshold(val)
            self.assertEqual(dev.get_tach_threshold(), val)
            self.assertEqual(chip.regs[REG_TCTH], (val >> 8) & 0xFF)
            self.assertEqual(chip.regs[REG_TCTL], val & 0xFF)

    def test_threshold_rejects_out_of_range(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.set_tach_threshold, -1)
        self.assertRaises(ValueError, dev.set_tach_threshold, 65536)


class TestFaultHandling(unittest.TestCase):
    """B7: status, CLRFAIL, FFDC, FF_0, FF mode, RD mode, alert mask."""

    def test_status_raw_clears_on_read(self):
        dev, chip, _ = make_dev()
        chip.sr_latch = 0x03
        self.assertEqual(dev.status_raw(), 0x03)
        self.assertEqual(dev.status_raw(), 0x00)   # cleared by the read

    def test_remote_diode_fault(self):
        dev, chip, _ = make_dev()
        chip.sr_latch = SR_RDFA
        self.assertTrue(dev.remote_diode_fault())
        chip.sr_latch = 0x00
        self.assertFalse(dev.remote_diode_fault())

    def test_active_alarms_compact_bitmask(self):
        # F16: compact six-alarm bitmask, PC excluded, latch consumed.
        dev, chip, _ = make_dev()
        chip.sr_latch = SR_TACH1A | SR_LHA | SR_PC
        self.assertEqual(dev.active_alarms(), SR_TACH1A | SR_LHA)
        # Second read: alarm bits consumed; only PC persists (silicon behaviour)
        self.assertEqual(dev.status_raw(), SR_PC)

    def test_sr_flag_positions(self):
        # SR flag positions must match the datasheet register 5Ah layout
        self.assertEqual(SR_TACH1A, 0x01)
        self.assertEqual(SR_TACH2A, 0x02)
        self.assertEqual(SR_ROTA, 0x04)
        self.assertEqual(SR_RHA, 0x08)
        self.assertEqual(SR_LOTA, 0x10)
        self.assertEqual(SR_LHA, 0x20)
        self.assertEqual(SR_RDFA, 0x40)
        self.assertEqual(SR_PC, 0x80)
        self.assertEqual(SR_ALARM_MASK, 0x7F)

    def test_clear_fan_fail_preserves_other_bits(self):
        dev, chip, _ = make_dev()
        self.assertEqual(chip.regs[REG_CR3], 0x03)
        dev.clear_fan_fail()
        self.assertEqual(chip.regs[REG_CR3], 0x83)   # CLRFAIL | factory

    def test_ffdc_roundtrip_and_validation(self):
        dev, chip, _ = make_dev()
        self.assertEqual(dev.get_ffdc_raw(), 0xFF)   # factory
        dev.set_ffdc_raw(0x80)
        self.assertEqual(dev.get_ffdc_raw(), 0x80)
        self.assertEqual(chip.regs[REG_FFDC], 0x80)
        dev.set_ffdc_pct(50.0)
        self.assertEqual(dev.get_ffdc_raw(), 128)
        self.assertRaises(ValueError, dev.set_ffdc_raw, 256)
        self.assertRaises(ValueError, dev.set_ffdc_raw, -1)
        self.assertRaises(ValueError, dev.set_ffdc_pct, 101.0)

    def test_ff_zero_detection_toggle(self):
        dev, chip, _ = make_dev()
        self.assertFalse(dev.ff_zero_detection())    # factory CR3=0x03
        dev.set_ff_zero_detection(True)
        self.assertTrue(dev.ff_zero_detection())
        self.assertEqual(chip.regs[REG_CR3], 0x43)   # other bits kept
        dev.set_ff_zero_detection(False)
        self.assertEqual(chip.regs[REG_CR3], 0x03)

    def test_ff_mode_roundtrip(self):
        dev, chip, _ = make_dev()
        self.assertEqual(dev.get_ff_mode(), FF_MODE_COMPARATOR)  # factory
        dev.set_ff_mode(FF_MODE_INTERRUPT)
        self.assertEqual(dev.get_ff_mode(), FF_MODE_INTERRUPT)
        self.assertEqual(chip.regs[REG_CR2], 0x00)
        dev.set_ff_mode(FF_MODE_COMPARATOR)
        self.assertEqual(chip.regs[REG_CR2], 0x10)
        self.assertRaises(ValueError, dev.set_ff_mode, 2)

    def test_rd_mode_and_polarity(self):
        dev, chip, _ = make_dev()
        self.assertFalse(dev.rd_mode_enabled())
        self.assertFalse(dev.get_rd_polarity())
        dev.set_rd_mode(True)
        dev.set_rd_polarity(True)
        self.assertTrue(dev.rd_mode_enabled())
        self.assertTrue(dev.get_rd_polarity())
        self.assertEqual(chip.regs[REG_CR2], 0x16)   # 0x10 | FSST | RDPS
        dev.set_rd_mode(False)
        dev.set_rd_polarity(False)
        self.assertEqual(chip.regs[REG_CR2], 0x10)   # restored exactly

    def test_alert_mask_roundtrip_preserves_reserved(self):
        dev, chip, _ = make_dev()
        self.assertEqual(chip.regs[REG_MASK], 0xC0)  # factory
        self.assertEqual(dev.get_alert_mask(), 0x00)
        dev.set_alert_mask(SR_TACH1A | SR_TACH2A)
        self.assertEqual(dev.get_alert_mask(), 0x03)
        self.assertEqual(chip.regs[REG_MASK], 0xC3)  # reserved bits kept
        dev.set_alert_mask(MASK_ALARM_FIELD)
        self.assertEqual(chip.regs[REG_MASK], 0xFF)
        dev.set_alert_mask(0)
        self.assertEqual(chip.regs[REG_MASK], 0xC0)  # back to factory

    def test_alert_mask_rejects_reserved_bits(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.set_alert_mask, 0x40)
        self.assertRaises(ValueError, dev.set_alert_mask, 0xFF)
        # RDFA has no mask bit (it never drives ALERT): 0x7F must be rejected
        self.assertRaises(ValueError, dev.set_alert_mask, SR_ALARM_MASK)
        self.assertRaises(ValueError, dev.set_alert_mask, -1)


class TestThreeWireAssist(unittest.TestCase):
    """B8: spin-up (SPEN), pulse stretch (PSEN), TACHFULL, one-shot measure."""

    def test_spin_up_toggle_preserves_cr2(self):
        dev, chip, _ = make_dev()
        self.assertFalse(dev.spin_up_enabled())          # factory CR2=0x10
        dev.spin_up_enable(True)
        self.assertTrue(dev.spin_up_enabled())
        self.assertEqual(chip.regs[REG_CR2], 0x30)       # FFMODE kept
        dev.spin_up_enable(False)
        self.assertEqual(chip.regs[REG_CR2], 0x10)

    def test_pulse_stretch_toggle_preserves_cr3(self):
        dev, chip, _ = make_dev()
        self.assertFalse(dev.pulse_stretch_enabled())    # factory CR3=0x03
        dev.pulse_stretch_enable(True)
        self.assertTrue(dev.pulse_stretch_enabled())
        self.assertEqual(chip.regs[REG_CR3], 0x07)       # tach enables kept
        dev.pulse_stretch_enable(False)
        self.assertEqual(chip.regs[REG_CR3], 0x03)

    def test_tacho_full_toggle_preserves_cr3(self):
        dev, chip, _ = make_dev()
        self.assertFalse(dev.tacho_full_enabled())
        dev.tacho_full_enable(True)
        self.assertTrue(dev.tacho_full_enabled())
        self.assertEqual(chip.regs[REG_CR3], 0x0B)
        dev.tacho_full_enable(False)
        self.assertEqual(chip.regs[REG_CR3], 0x03)

    def test_measure_tach_once_returns_count_and_clears_psen(self):
        dev, chip, _ = make_dev()
        chip.regs[REG_TC1H] = 0x05
        chip.regs[REG_TC1L] = 0x0D                       # static mock: no change
        cnt = dev.measure_tach_once(port=1, timeout_ms=150)
        self.assertEqual(cnt, 0x050D)
        self.assertFalse(dev.pulse_stretch_enabled())    # cleared in finally

    def test_measure_tach_once_port2_reads_tc2(self):
        dev, chip, _ = make_dev()
        chip.regs[REG_TC2H] = 0xAB
        chip.regs[REG_TC2L] = 0xCD
        self.assertEqual(dev.measure_tach_once(port=2, timeout_ms=150), 0xABCD)

    def test_measure_tach_once_preconditions(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.measure_tach_once, port=3)
        dev.set_pwm_freq_hz(PWM_FREQ_150HZ)
        self.assertRaises(ValueError, dev.measure_tach_once, port=1,
                          timeout_ms=50)
        dev.set_pwm_freq_hz(PWM_FREQ_33HZ)
        dev.tacho_full_enable(True)
        self.assertRaises(ValueError, dev.measure_tach_once, port=1,
                          timeout_ms=50)


class TestAlertAndIdeality(unittest.TestCase):
    """B9: ALERT service routine (F18) + ideality factor (F19)."""

    def test_alert_mode_roundtrip(self):
        dev, chip, _ = make_dev()
        self.assertEqual(dev.get_alert_mode(), ALERT_MODE_INTERRUPT)  # factory
        dev.set_alert_mode(ALERT_MODE_FAULT_INDICATOR)
        self.assertEqual(dev.get_alert_mode(), ALERT_MODE_FAULT_INDICATOR)
        self.assertEqual(chip.regs[REG_CR2], 0x50)   # 0x10 | ALERTS
        dev.set_alert_mode(ALERT_MODE_INTERRUPT)
        self.assertEqual(chip.regs[REG_CR2], 0x10)
        self.assertRaises(ValueError, dev.set_alert_mode, 2)

    def test_service_alert_reads_and_clears_sr(self):
        dev, chip, _ = make_dev()
        chip.sr_latch = SR_LHA | SR_RHA
        sr = dev.service_alert()
        self.assertEqual(sr, SR_LHA | SR_RHA)
        self.assertEqual(chip.sr_latch, 0x00)       # cleared by the read

    def test_alt_mask_get_clear(self):
        dev, chip, _ = make_dev()
        self.assertFalse(dev.alert_masked())        # factory CR1=0x01
        chip.regs[REG_CR1] = 0x81                   # simulate device latch
        self.assertTrue(dev.alert_masked())
        dev.clear_alert_mask()
        self.assertFalse(dev.alert_masked())
        self.assertEqual(chip.regs[REG_CR1], 0x01)  # other bits preserved

    def test_ideality_index_roundtrip_and_validation(self):
        dev, chip, _ = make_dev()
        self.assertEqual(dev.get_ideality_factor_index(), 0x18)  # factory
        self.assertEqual(dev.get_ideality_factor(), 1.0080)
        dev.set_ideality_factor_index(0)
        self.assertEqual(chip.regs[REG_IFR], 0x00)
        dev.set_ideality_factor_index(63)
        self.assertEqual(chip.regs[REG_IFR], 0x3F)
        self.assertRaises(ValueError, dev.set_ideality_factor_index, 64)
        self.assertRaises(ValueError, dev.set_ideality_factor_index, -1)

    def test_ideality_nearest_match(self):
        dev, _, _ = make_dev()
        i = dev.set_ideality_factor(1.0)
        self.assertEqual(i, 16)                     # table[16] = 1.0000
        self.assertEqual(dev.get_ideality_factor(), 1.0000)
        i = dev.set_ideality_factor(0.985)
        self.assertEqual(i, 1)                      # 0.9853 closer than 0.9844
        # Exact midpoint between 1.0000 and 1.0010 -> lower index wins
        i = dev.set_ideality_factor(1.0005)
        self.assertEqual(i, 16)
        # Round-trip consistency for an arbitrary value
        i = dev.set_ideality_factor(1.02)
        self.assertEqual(dev.get_ideality_factor(), IDEALITY_TABLE[i])

    def test_ideality_range_rejection(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.set_ideality_factor, 0.98)
        self.assertRaises(ValueError, dev.set_ideality_factor, 1.05)
        self.assertRaises(ValueError, dev.set_ideality_factor, 1.04891)


class TestEepromLifecycle(unittest.TestCase):
    """B10: EEPROM save/load + ack-poll + corruption recovery (F20),
    soft POR / standby / user memory (F21)."""

    def test_save_config_writes_eeprom(self):
        dev, chip, tr = make_dev()
        chip.regs[REG_CR1] = 0x02                       # mutate RAM
        dev.save_config(EEX_BLOCK_00_0F)
        self.assertEqual(chip.eeprom_ops[-1], EEX_BLOCK_00_0F)  # L/W=0
        self.assertEqual(chip.eeprom[REG_CR1], 0x02)   # RAM -> EEPROM
        self.assertIn(EEPROM_WAIT_MS, tr.delays)       # fixed tW wait

    def test_load_config_reads_eeprom(self):
        dev, chip, _ = make_dev()
        chip.eeprom[REG_CR1] = 0x05                     # seed EEPROM
        dev.load_config(EEX_BLOCK_00_0F)
        self.assertEqual(chip.eeprom_ops[-1], 0x80 | EEX_BLOCK_00_0F)
        self.assertEqual(chip.regs[REG_CR1], 0x05)      # EEPROM -> RAM

    def test_each_block_select_constant_encodes_correctly(self):
        # C2 coverage: every EEX block-select constant must round-trip into
        # the exact EEX byte for both write and load directions.
        cases = [(EEX_BLOCK_00_0F, REG_CR1),
                 (EEX_BLOCK_10_1F, 0x10),
                 (EEX_BLOCK_20_2F, 0x20),
                 (EEX_BLOCK_30_3F, 0x30),
                 (EEX_BLOCK_40_4F, 0x40)]
        for blk, reg in cases:
            dev, chip, _ = make_dev()
            chip.regs[reg] = 0x5A
            dev.save_config(blk)
            self.assertEqual(chip.eeprom_ops[-1], blk)
            self.assertEqual(chip.eeprom[reg], 0x5A)
            chip.eeprom[reg] = 0x6B
            dev.load_config(blk)
            self.assertEqual(chip.eeprom_ops[-1], 0x80 | blk)
            self.assertEqual(chip.regs[reg], 0x6B)

    def test_block_select_scoping(self):
        dev, chip, _ = make_dev()
        chip.regs[REG_CR1] = 0x02
        chip.regs[0x20] = 0x40
        dev.save_config(EEX_BLOCK_00_0F)               # only block 0
        self.assertEqual(chip.eeprom[REG_CR1], 0x02)
        self.assertNotEqual(chip.eeprom[0x20], 0x40)   # LUT untouched

    def test_invalid_block_select_rejected(self):
        dev, _, _ = make_dev()
        self.assertRaises(ValueError, dev.save_config, 0)
        self.assertRaises(ValueError, dev.save_config, 0x20)
        self.assertRaises(ValueError, dev.load_config, 0x3F)

    def test_busy_timeout_raises(self):
        dev, chip, _ = make_dev()
        chip.busy_polls = 10**9                        # never becomes ready
        self.assertRaises(TimeoutError, dev.save_config, timeout_ms=0)

    def test_wait_is_pure_delay_without_bus_traffic(self):
        # Regression (2026-11-08, RPi 3A+): ack-polling is unreliable in
        # BOTH directions on live silicon - the device ACKs stray probes
        # before the EEX command latches, and genuinely NACKs its own
        # address while a LOAD commits new register values (observed up to
        # ~600 ms, later than nominal tW). Probes and oracle writes
        # demonstrably interact badly with the commit, so the busy-window
        # wait must be a PURE DELAY of EEPROM_WAIT_MS with ZERO bus traffic.
        dev, _, tr = make_dev()

        class Stub(object):
            def __init__(self):
                self.probes = 0
                self.reads = 0
                self.non_eex_writes = 0

            def probe(self):
                self.probes += 1
                return True

            def burst_read(self, reg, n):
                self.reads += 1
                return b"\x19"

            def burst_write(self, reg, data):
                if reg != REG_EEX:
                    self.non_eex_writes += 1

            def delay_ms(self, ms):
                pass

        stub = Stub()
        tr.probe = stub.probe
        tr.burst_read = stub.burst_read
        tr.burst_write = stub.burst_write
        dev.save_config(EEX_BLOCK_00_0F)
        self.assertEqual(stub.probes, 0)
        self.assertEqual(stub.reads, 0)
        self.assertEqual(stub.non_eex_writes, 0)
        self.assertIn(EEPROM_WAIT_MS, tr.delays)

    def test_soft_por_resets_and_reloads(self):
        dev, chip, _ = make_dev()
        chip.set_sr(SR_LHA)
        chip.regs[REG_CR1] = 0x02
        chip.eeprom[REG_CR1] = 0x07                    # EEPROM holds other value
        dev.soft_por()
        self.assertEqual(chip.sr_latch, 0x00)          # latches cleared
        self.assertEqual(chip.regs[REG_CR1], 0x07)     # RAM reloaded from EEPROM

    def test_soft_por_survives_mid_transaction_reset_error(self):
        # Regression (2026-11-08, RPi 3A+): SW_POR executes on latch; the
        # chip resets so fast that the in-flight write reports errno 121
        # even though the reset HAPPENED (verified live: volatile user
        # memory reloads from EEPROM despite the error). The driver must
        # issue the POR write exactly ONCE - a retry re-fires the POR into
        # a still-booting chip - swallow its OSError, and settle via probe
        # polling.
        dev, chip, tr = make_dev()
        chip.eeprom[REG_CR1] = 0x07
        por_writes = []
        orig_write = tr.burst_write

        def spy_write(reg, data):
            if reg == REG_CR1 and data and (data[0] & CR1_SW_POR):
                por_writes.append(1)
                orig_write(reg, data)      # latch: POR fires, boot_polls set
                raise OSError(121, "Remote I/O error")
            return orig_write(reg, data)

        tr.burst_write = spy_write
        dev.soft_por()                       # must NOT raise
        self.assertEqual(len(por_writes), 1)  # single attempt, no retries
        self.assertEqual(chip.regs[REG_CR1], 0x07)   # reload applied
        self.assertIn(EEPROM_WAIT_MS, tr.delays)     # commit window waited

    def test_standby_roundtrip(self):
        dev, chip, _ = make_dev()
        self.assertFalse(dev.standby_active())
        dev.enter_standby()
        self.assertTrue(dev.standby_active())
        self.assertEqual(chip.regs[REG_CR2], 0x90)     # 0x10 | STBY
        dev.exit_standby()
        self.assertFalse(dev.standby_active())
        self.assertEqual(chip.regs[REG_CR2], 0x10)

    def test_user_memory_single(self):
        dev, chip, _ = make_dev()
        self.assertEqual(dev.user_memory_get(0), USER_FACTORY_VALUE)
        dev.user_memory_set(3, 0xA5)
        self.assertEqual(chip.regs[0x13], 0xA5)
        self.assertEqual(dev.user_memory_get(3), 0xA5)
        self.assertRaises(ValueError, dev.user_memory_get, 8)
        self.assertRaises(ValueError, dev.user_memory_set, -1, 1)
        self.assertRaises(ValueError, dev.user_memory_set, 0, 256)

    def test_user_memory_bulk(self):
        dev, chip, _ = make_dev()
        data = bytes(range(8))
        dev.user_memory_write_all(data)
        self.assertEqual(bytes(chip.regs[0x10:0x18]), data)
        self.assertEqual(dev.user_memory_read_all(), data)
        self.assertRaises(ValueError, dev.user_memory_write_all, b'\x00' * 7)

    def test_pc_persists_across_reads(self):
        dev, chip, _ = make_dev()
        chip.set_sr(SR_PC | SR_TACH1A)
        self.assertTrue(dev.eeprom_corrupt())
        self.assertTrue(dev.eeprom_corrupt())         # PC survives reads...
        self.assertEqual(dev.status_raw() & SR_TACH1A, 0)  # ...others clear

    def test_recover_from_corruption(self):
        dev, chip, _ = make_dev()
        chip.set_sr(SR_PC)
        chip.regs[REG_CR1] = 0x02                      # desired RAM state
        ok = dev.recover_from_corruption()
        self.assertTrue(ok)
        self.assertEqual(chip.eeprom[REG_CR1], 0x02)   # rewritten to EEPROM
        self.assertEqual(chip.regs[REG_CR1], 0x02)     # reloaded after POR
        self.assertFalse(dev.eeprom_corrupt())


class TestPresets(unittest.TestCase):
    """B11: convenience configuration presets (F24)."""

    def test_configure_4wire_fan_port1(self):
        dev, chip, _ = make_dev()
        dev.configure_4wire_fan(port=1)
        self.assertEqual(chip.regs[REG_CR1] & 0x18, CR1_DRV_25KHZ)
        self.assertTrue(chip.regs[REG_CR3] & CR3_TACH1E)
        self.assertFalse(chip.regs[REG_CR3] & CR3_TACH2E)
        # Presets are mode-neutral: DFC (CR2 bit 0) must stay at factory
        self.assertFalse(chip.regs[REG_CR2] & 0x01)

    def test_configure_4wire_fan_port2(self):
        dev, chip, _ = make_dev()
        dev.configure_4wire_fan(port=2)
        self.assertTrue(chip.regs[REG_CR3] & CR3_TACH2E)
        self.assertFalse(chip.regs[REG_CR3] & CR3_TACH1E)
        self.assertRaises(ValueError, dev.configure_4wire_fan, port=3)

    def test_configure_3wire_supply_modulation(self):
        dev, chip, _ = make_dev()
        dev.configure_3wire_supply_modulation(port=1)
        self.assertEqual(chip.regs[REG_CR1] & 0x18, CR1_DRV_33HZ)
        self.assertTrue(chip.regs[REG_CR3] & CR3_PSEN)
        self.assertTrue(chip.regs[REG_CR3] & CR3_TACH1E)
        self.assertFalse(chip.regs[REG_CR3] & CR3_TACH2E)

    def test_configure_two_fans(self):
        dev, chip, _ = make_dev()
        dev.configure_two_fans()
        self.assertEqual(chip.regs[REG_CR1] & 0x18, CR1_DRV_25KHZ)
        self.assertTrue(chip.regs[REG_CR3] & (CR3_TACH1E | CR3_TACH2E))

    def test_presets_leave_chip_protocol_clean(self):
        dev, chip, _ = make_dev()
        for preset in (lambda: dev.configure_4wire_fan(),
                       lambda: dev.configure_3wire_supply_modulation(),
                       lambda: dev.configure_two_fans()):
            preset()
            self.assertEqual(chip.violations, [])


class TestCPAdapter(unittest.TestCase):
    def setUp(self):
        self.chip = MockChip()
        self.fake = FakeSMBus(1, chip=self.chip)
        self.tr = TransportCP(bus=1, addr=0x50, handle=self.fake)
        self.dev = MAX31760(self.tr, 0x50)

    def test_block_read_payload_passthrough(self):
        # Regression (2026-11-08): transport must NOT strip a byte from
        # smbus2 block reads - smbus2 returns clean payloads (live-verified
        # on RPi 3A+). Stripping one byte truncated 2-byte reads to 1.
        self.chip.regs[0x58] = 0x1A
        self.chip.regs[0x59] = 0x80
        data = self.dev.read_reg(0x58, 2)
        self.assertEqual(data, b"\x1a\x80")      # full payload, unmodified

    def test_long_read_chunked_under_limit(self):
        lut = bytes((i * 7) & 0xFF for i in range(48))
        for i in range(48):
            self.chip.regs[0x20 + i] = lut[i]
        got = self.dev.read_reg(REG_LUT_BASE, 48)
        self.assertEqual(got, lut)
        self.assertTrue(all(q <= 32 for q in self.fake.block_reads))
        self.assertEqual(sum(self.fake.block_reads), 48)

    def test_write_via_adapter(self):
        self.dev.write_reg(0x10, b"\xde\xad")
        self.assertEqual(bytes(self.chip.regs[0x10:0x12]), b"\xde\xad")
        self.assertEqual(self.chip.violations, [])

    def test_probe_maps_oserror(self):
        self.assertTrue(self.dev.probe())
        self.chip.nack = True
        self.assertFalse(self.dev.probe())

    def test_close_semantics(self):
        # Borrowed handle: close() must not touch it.
        self.assertFalse(self.tr._owns_bus)
        self.tr.close()
        self.assertFalse(self.fake.closed)
        # Owned handle: close() releases it (ownership flag simulated,
        # since a real bus cannot be opened on a non-Linux host).
        owned_fake = FakeSMBus(1, chip=MockChip())
        tr2 = TransportCP(bus=1, addr=0x50, handle=owned_fake)
        tr2._owns_bus = True
        tr2.close()
        self.assertTrue(owned_fake.closed)

    def test_scan_probes_candidate_addresses(self):
        chip = MockChip(addrs=[0x50, 0x62])
        fake = FakeSMBus(1, chip=chip)
        tr = TransportCP(bus=1, addr=0x50, handle=fake)
        dev = MAX31760(tr, 0x50)
        self.assertEqual(dev.scan(), [0x50, 0x62])

    def test_verify_via_cp_adapter(self):
        self.assertTrue(self.dev.verify())
        self.chip.nack = True
        self.assertRaises(OSError, self.dev.verify)

    def test_legacy_smbus_compat_normalizes_count_byte(self):
        # _SmbusCompat adapts legacy system-smbus semantics (no length arg,
        # count byte prepended) to the smbus2 clean-payload contract.
        from max31760._transport_cp import _SmbusCompat

        chip = MockChip()
        chip.regs[0x58] = 0x1A
        chip.regs[0x59] = 0x80

        class LegacyStub(object):
            def read_i2c_block_data(self, addr, reg):      # 2-arg, old API
                qty = 4
                return [qty] + list(chip.burst_read(reg, qty, addr=addr))

            def write_i2c_block_data(self, addr, reg, data):
                chip.burst_write(reg, bytes(bytearray(data)), addr=addr)

            def read_byte_data(self, addr, reg):
                return chip.burst_read(reg, 1, addr=addr)[0]

            def write_byte_data(self, addr, reg, val):
                pass

            def close(self):
                pass

        wrapped = _SmbusCompat(LegacyStub())
        self.assertEqual(wrapped.read_i2c_block_data(0x50, 0x58, 2),
                         [0x1A, 0x80])


class TestCPIntegration(unittest.TestCase):
    """B12 (F25): full driver stack (cp facade + TransportCP + core) over the
    fake SMBus handle — proves the CPython path exercises every API domain
    identically to the MicroPython path."""

    def setUp(self):
        from max31760.cp import MAX31760 as CPDev
        self.chip = MockChip()
        self.fake = FakeSMBus(1, chip=self.chip)
        self.dev = CPDev(bus=1, addr=0x50, handle=self.fake)

    def test_full_stack_smoke_matrix(self):
        dev = self.dev
        # identity / raw access
        self.assertTrue(dev.verify())
        self.assertIn(0x50, dev.scan())
        self.assertEqual(dev.read_reg(REG_CR1, 1)[0], FACTORY_DEFAULTS[REG_CR1])
        # manual mode + duty + ramp
        dev.manual_enable(True)
        self.assertTrue(dev.manual_enabled())
        dev.set_ramp_rate(RAMP_IMMEDIATE)
        dev.set_duty_pct(50.0)
        self.chip.regs[REG_PWMV] = 128          # emulate a settled ramp
        self.assertTrue(dev.wait_for_duty(50.0))
        self.assertEqual(dev.get_actual_duty_raw(), 128)
        # LUT
        dev.lut_set_index(25, 128)              # raw duty 0..255
        self.assertEqual(dev.lut_get_index(25), 128)
        # temperature + setpoints
        self.assertIsInstance(dev.local_temp_c, float)
        dev.set_local_high(60.0)
        self.assertAlmostEqual(dev.get_local_high(), 60.0, places=2)
        # tach
        dev.tach1_enable(True)
        self.assertEqual(dev.rpm(1), 0.0)          # no pulses in the mock
        dev.set_tach_threshold(1000)
        self.assertEqual(dev.get_tach_threshold(), 1000)
        # fault domain
        self.assertEqual(dev.status_raw(), 0x00)
        dev.set_ffdc_pct(50.0)
        self.assertEqual(dev.get_ffdc_raw(), 128)
        mask = MASK_ALARM_FIELD & ~SR_TACH1A
        dev.set_alert_mask(mask)
        self.assertEqual(dev.get_alert_mask(), mask)
        # 3-wire assists + alert/ideality
        dev.spin_up_enable(True)
        self.assertTrue(dev.spin_up_enabled())
        dev.pulse_stretch_enable(True)
        self.assertTrue(dev.pulse_stretch_enabled())
        self.assertFalse(dev.tacho_full_enabled())
        self.assertEqual(dev.get_alert_mode(), ALERT_MODE_INTERRUPT)
        self.assertEqual(dev.get_ideality_factor_index(), 0x18)
        self.assertEqual(dev.set_ideality_factor(1.0), 16)
        # EEPROM lifecycle through the chunked CP read/write path
        self.chip.regs[REG_CR1] = 0x02
        dev.save_config(EEX_BLOCK_00_0F)
        self.assertEqual(self.chip.eeprom[REG_CR1], 0x02)
        self.chip.eeprom[REG_CR1] = 0x07
        dev.load_config(EEX_BLOCK_00_0F)
        self.assertEqual(self.chip.regs[REG_CR1], 0x07)
        self.assertFalse(dev.eeprom_corrupt())
        # lifecycle: POR reloads RAM from EEPROM (which holds 0x07 from the
        # load step above); standby; user memory
        dev.soft_por()
        self.assertEqual(self.chip.regs[REG_CR1], 0x07)
        dev.enter_standby()
        self.assertTrue(dev.standby_active())
        dev.exit_standby()
        self.assertFalse(dev.standby_active())
        dev.user_memory_set(0, 0xA5)
        self.assertEqual(dev.user_memory_get(0), 0xA5)
        # presets
        dev.configure_4wire_fan(port=1)
        self.assertEqual(self.chip.regs[REG_CR1] & 0x18, CR1_DRV_25KHZ)
        self.assertEqual(self.chip.violations, [])
        # teardown releases the borrowed-handle flag correctly
        dev.close()
        self.assertFalse(self.fake.closed)   # injected handle not owned


class TestApiParity(unittest.TestCase):
    """C9 (F26): both entry points must expose an IDENTICAL public surface
    (methods, signatures, constants, properties); only the platform-specific
    constructor differs by design."""

    def setUp(self):
        import inspect
        self.inspect = inspect
        from max31760.mp import MAX31760 as MPDev
        from max31760.cp import MAX31760 as CPDev
        self.MPDev = MPDev
        self.CPDev = CPDev

    def test_shared_core_identity(self):
        # Both facades subclass the SAME shared core class.
        self.assertIs(self.MPDev.__mro__[1], self.CPDev.__mro__[1])

    def test_module_exports_match(self):
        import max31760.mp as mp_mod
        import max31760.cp as cp_mod
        self.assertEqual(mp_mod.__all__, cp_mod.__all__)
        for name in mp_mod.__all__:
            if name == "MAX31760":
                continue                      # distinct thin facades by design
            self.assertIs(getattr(mp_mod, name), getattr(cp_mod, name))

    def test_public_surface_identical(self):
        mp_pub = {n for n in dir(self.MPDev) if not n.startswith("_")}
        cp_pub = {n for n in dir(self.CPDev) if not n.startswith("_")}
        self.assertEqual(mp_pub, cp_pub,
                         "surface diff: %r vs %r" %
                         (sorted(mp_pub - cp_pub), sorted(cp_pub - mp_pub)))
        for name in sorted(mp_pub):
            m = getattr(self.MPDev, name)
            c = getattr(self.CPDev, name)
            if isinstance(m, property):
                self.assertIsInstance(c, property,
                                       "%s not a property on cp facade" % name)
            elif callable(m):
                sig_m = self.inspect.signature(m)
                sig_c = self.inspect.signature(c)
                self.assertEqual(sig_m, sig_c,
                                 "signature mismatch: %s" % name)
            else:
                self.assertEqual(m, c, "constant mismatch: %s" % name)


if __name__ == "__main__":
    unittest.main()
