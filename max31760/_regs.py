"""Canonical register map, bit fields, encodings and fixed-point math.

Leaf module: imports NOTHING from the package (dependency-graph root).
Single source of truth for every register address, bit-field constant,
mode/index/frequency encoding, physical constant and fixed-point helper
(v0.1.1 decision D-03: extracted from _core.py to eliminate the duplicate
constant blocks and the ordering-dependent circular import).

Register map per Maxim DS 19-7395 Rev 0, Table 13. One name per bit;
values pinned by tests/test_max31760.py (TestConstants, TestRegsModule).
"""

# ---------------------------------------------------------------------------
# Register map (datasheet DS 19-7395 Rev 0, Table 13)
# ---------------------------------------------------------------------------
REG_CR1 = 0x00       # Control Register 1
REG_CR2 = 0x01       # Control Register 2
REG_CR3 = 0x02       # Control Register 3
REG_FFDC = 0x03      # Fan-Fail Forced Duty Cycle
REG_MASK = 0x04      # Alarm Mask
REG_IFR = 0x05       # Ideality Factor
REG_RHSH = 0x06      # Remote High Set Point (MSB)
REG_RHSL = 0x07      # Remote High Set Point (LSB)
REG_LOTSH = 0x08     # Local Overtemp Set Point (MSB)
REG_LOTSL = 0x09     # Local Overtemp Set Point (LSB)
REG_ROTSH = 0x0A     # Remote Overtemp Set Point (MSB)
REG_ROTSL = 0x0B     # Remote Overtemp Set Point (LSB)
REG_LHSH = 0x0C      # Local High Set Point (MSB)
REG_LHSL = 0x0D      # Local High Set Point (LSB)
REG_TCTH = 0x0E      # Tach Count Threshold (MSB)
REG_TCTL = 0x0F      # Tach Count Threshold (LSB)
REG_USER_BASE = 0x10 # User memory (8 bytes, 10h..17h)
REG_USER_END = 0x17
REG_LUT_BASE = 0x20  # LUT[0..47] (20h..4Fh)
REG_LUT_END = 0x4F
REG_PWMR = 0x50      # Direct (manual) duty command
REG_PWMV = 0x51      # Current actual duty (RO)
REG_TC1H = 0x52      # TACH1 count (RO)
REG_TC1L = 0x53
REG_TC2H = 0x54      # TACH2 count (RO)
REG_TC2L = 0x55
REG_RTH = 0x56       # Remote temperature reading (RO)
REG_RTL = 0x57
REG_LTH = 0x58       # Local temperature reading (RO)
REG_LTL = 0x59
REG_SR = 0x5A        # Status / alarm flags (RO, clear-on-read)
REG_EEX = 0x5B       # EEPROM load/write control (WO, auto-clears)

ADDR_MIN = 0x50
ADDR_MAX = 0x57
PAGE_SIZE = 8        # write pages wrap within 8-byte rows
LUT_LEN = 48
USER_LEN = 8
RETRY_DELAYS_MS = (10, 30, 60, 100, 200, 400)  # escalating retry backoffs
EEPROM_WAIT_MS = 700   # fixed post-EEX wait: above datasheet tW max (550 ms)
POR_SETTLE_MS = 2000   # default settle window after a software POR


# --- CR1 (00h) bits ---------------------------------------------------------
CR1_ALTMSK = 0x80    # interrupt-mode alert latch mask
CR1_SW_POR = 0x40    # software POR (self-clearing)
CR1_HYST = 0x20      # LUT hysteresis: 0 = 2 C, 1 = 4 C
CR1_DRV_MASK = 0x18  # PWM frequency select [1:0] << 3 (bits 4:3)
CR1_DRV_33HZ = 0x00
CR1_DRV_150HZ = 0x08
CR1_DRV_1P5KHZ = 0x10
CR1_DRV_25KHZ = 0x18
CR1_PPS_NEGATIVE = 0x04  # polarity: 0 = positive, 1 = negative
CR1_MTI = 0x02     # maximum temperature as index
CR1_TIS = 0x01     # temperature index source

# Temperature index source (Table 6): MTI:TIS combinations.
INDEX_LOCAL = 0x00   # MTI=0 TIS=0
INDEX_REMOTE = 0x01  # MTI=0 TIS=1 (factory default)
INDEX_MAX = 0x03     # MTI=1 (TIS don't-care; set both for determinism)

# --- CR2 (01h) bits (canonical single block) --------------------------------
CR2_STBY = 0x80      # standby mode
CR2_ALERTS = 0x40    # ALERT pin mode: 0=interrupt, 1=comparator
CR2_SPEN = 0x20      # spin-up enable
CR2_FFMODE = 0x10    # FF/FS mode: 0=interrupt(latched), 1=comparator
CR2_FSENABLE = 0x08  # full-speed input enable
CR2_RDPS = 0x04      # RD signal polarity: 1 = RD high means spinning
CR2_FSST = 0x02      # fan-sense type: 0=tach, 1=RD
CR2_DFC = 0x01       # direct fan control (manual duty)

# --- CR3 (02h) bits ---------------------------------------------------------
CR3_CLRFAIL = 0x80   # clear fan-fail status (self-clearing)
CR3_FF_0 = 0x40      # fan-fail detection while duty = 0
CR3_RAMP_MASK = 0x30 # ramp rate select [1:0] << 4
RAMP_SLOW = 0x00         # 3.125 %/s (datasheet default)
RAMP_MED_SLOW = 0x10     # 6.25 %/s
RAMP_MED_FAST = 0x20     # 12.5 %/s
RAMP_IMMEDIATE = 0x30    # immediate (driver preset default, D7)
CR3_TACHFULL = 0x08      # tach input is a supply-modulation signal
CR3_PSEN = 0x04          # pulse-stretch enable (3-wire assist)
CR3_TACH2E = 0x02        # TACH2 enable
CR3_TACH1E = 0x01        # TACH1 enable

# --- SR (5Ah) alarm bits (clear on read) ------------------------------------
SR_TACH1A = 0x01         # TACH1 fan-fail / overflow latched
SR_TACH2A = 0x02         # TACH2 fan-fail / overflow latched
SR_ROTA   = 0x04         # remote overtemperature
SR_RHA    = 0x08         # remote high temperature
SR_LOTA   = 0x10         # local overtemperature
SR_LHA    = 0x20         # local high temperature
SR_RDFA   = 0x40         # remote diode fault (does not drive ALERT)
SR_PC     = 0x80         # EEPROM program-corrupt (needs POR/soft-POR to clear)
SR_ALARM_MASK = 0x7F     # all alarm bits except PC

# --- MASK (04h): mirrors SR alarm bits; bits 7:6 reserved (hold 1) ----------
MASK_ALARM_FIELD = 0x3F  # alarm-mask field (positions match SR flags)
MASK_RESERVED_HI = 0xC0

# --- EEX (5Bh): bit7 = L/W (1 = load EEPROM->RAM, 0 = save RAM->EEPROM); ----
# --- bits 4:0 = one bit per 16-byte block; auto-clears ----------------------
EEX_BLOCK_00_0F = 0x01   # control registers CR1..TCTL
EEX_BLOCK_10_1F = 0x02   # user memory (10h..17h) + padding
EEX_BLOCK_20_2F = 0x04   # LUT lower third
EEX_BLOCK_30_3F = 0x08   # LUT middle third
EEX_BLOCK_40_4F = 0x10   # LUT upper third
EEX_ALL_BLOCKS = 0x1F    # every nonvolatile block
EEX_LOAD_BIT = 0x80      # 1 = load EEPROM->RAM, 0 = write RAM->EEPROM
EEX_SAVE_ALL = 0x1F      # save all blocks (L/W = 0)
EEX_LOAD_ALL = 0x9F      # load all blocks (L/W = 1)

# FF-mode encodings (CR2.FFMODE)
FF_MODE_INTERRUPT = 0    # latched until CLRFAIL
FF_MODE_COMPARATOR = 1   # follows the live fault condition

# ALERT-mode encodings (CR2.ALERTS)
ALERT_MODE_INTERRUPT = 0       # latched; needs the service routine (factory)
ALERT_MODE_FAULT_INDICATOR = 1 # tracks the live LHA/RHA condition

# IFR index field (bits [5:0]; reserved upper bits should stay 0)
IFR_INDEX_MASK = 0x3F

# Physical constants
TEMP_LSB_C = 0.125       # temperature resolution (bit5)
TACH_REF_HZ = 100000     # internal tach counter clock
TACH_AVG_PULSES = 4      # pulses averaged into each TC sample

# PWM frequency options (CR1 DRV bits) and polarity encodings.
PWM_FREQ_33HZ = 33
PWM_FREQ_150HZ = 150
PWM_FREQ_1P5KHZ = 1500
PWM_FREQ_25KHZ = 25000
_POLARITY_POSITIVE = 0
_POLARITY_NEGATIVE = 1
_PWM_FREQ_TO_BITS = ((PWM_FREQ_33HZ, CR1_DRV_33HZ),
                     (PWM_FREQ_150HZ, CR1_DRV_150HZ),
                     (PWM_FREQ_1P5KHZ, CR1_DRV_1P5KHZ),
                     (PWM_FREQ_25KHZ, CR1_DRV_25KHZ))


# ---------------------------------------------------------------------------
# Fixed-point helpers (A4)
# ---------------------------------------------------------------------------

def temp_to_raw16(celsius):
    """Encode a Celsius float to the 16-bit left-aligned two's-complement raw.

    LSB = bit5 = 0.125 C. Input must lie within -128.0 .. +127.875 C and is
    then quantized to the 0.125 C grid (nearest step). Raises ValueError
    outside the range.
    """
    c = float(celsius)
    if c < -128.0 or c > 127.875:
        raise ValueError(
            f"temperature {c:.3f} C out of range -128.0..+127.875")
    q = int(round(c * 8.0))
    return (q << 5) & 0xFFFF


def raw16_to_temp(raw16):
    """Decode a 16-bit left-aligned two's-complement raw to Celsius float."""
    v = raw16 & 0xFFFF
    if v & 0x8000:
        v -= 0x10000
    return (v >> 5) / 8.0


def duty_to_pct(duty):
    """Duty raw (0..255) to percent float (0..99.609...)."""
    d = int(duty)
    if d < 0 or d > 255:
        raise ValueError(f"duty {d:d} out of range 0..255")
    return d * 100.0 / 256.0


def pct_to_duty(pct):
    """Percent (0..100) to duty raw (0..255), rounded."""
    p = float(pct)
    if p < 0.0 or p > 100.0:
        raise ValueError(f"percent {p:.3f} out of range 0..100")
    d = int(round(p * 256.0 / 100.0))
    if d > 255:
        d = 255
    return d


def rpm_from_count(count, pulses_per_rev=2):
    """Convert an average TC count (clock ticks/pulse @100 kHz) to RPM.

    Returns 0.0 for count <= 0 (fan stopped / no pulses). Overflow of the
    16-bit count cannot be detected from a single sample; callers comparing
    successive samples should treat a sudden drop while the fan is known to
    be running as a probable overflow.
    """
    c = int(count)
    n = int(pulses_per_rev)
    if n <= 0:
        raise ValueError("pulses_per_rev must be >= 1")
    if c <= 0:
        return 0.0
    return 60.0 * TACH_REF_HZ / float(c) / float(n)


def count_from_rpm(rpm, pulses_per_rev=2):
    """Inverse of rpm_from_count, clamped to the 16-bit unsigned range."""
    n = int(pulses_per_rev)
    if n <= 0:
        raise ValueError("pulses_per_rev must be >= 1")
    r = float(rpm)
    if r <= 0.0:
        raise ValueError("rpm must be > 0")
    c = int(round(60.0 * TACH_REF_HZ / r / float(n)))
    if c < 0:
        c = 0
    elif c > 0xFFFF:
        c = 0xFFFF
    return c
