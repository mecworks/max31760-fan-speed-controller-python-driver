"""Shared protocol core for the Maxim MAX31760 precision fan-speed controller.

Platform-neutral: runs unmodified on MicroPython (RP2040/RP2350, ESP32) and
CPython. No third-party imports, no type hints, no CPython-only syntax.

The core owns ALL protocol knowledge: register map, page-safe writes,
fixed-point math, error model. Transports are duck-typed objects providing:
    burst_read(reg, n) -> bytes      pointer read of n bytes starting at reg
    burst_write(reg, data) -> None   raw write of 1..8 bytes starting at reg
    probe() -> bool                  address ACK check
    scan() -> iterable               7-bit addresses present on the bus
    delay_ms(ms) -> None             short backoff between retries
Optional: close()

Error model (F23): ValueError for bad arguments/bounds; OSError for bus/NACK
failures (after escalating-backoff retries); TimeoutError for EEPROM-busy
overruns. Never silent failures.
"""

from ._tables import FACTORY_DEFAULTS, IDEALITY_TABLE, LUT_FACTORY_VALUE, \
    USER_FACTORY_VALUE

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

# --- CR2 (01h) bits ---------------------------------------------------------
CR2_STBY = 0x80      # standby
CR2_ALERTS = 0x40    # ALERT pin mode: 0=interrupt, 1=comparator
CR2_SPEN = 0x20      # spin-up enable
CR2_FFMODE = 0x10    # FF/FS mode: 0=interrupt(latched), 1=comparator
CR2_FS_ENABLE = 0x08 # external full-speed force enable
CR2_RDPS = 0x04      # RD signal polarity
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

# SR flags (register 0x5A; alarm bits clear on read)
SR_TACH1A = 0x01         # TACH1 fan-fail / overflow latched
SR_TACH2A = 0x02         # TACH2 fan-fail / overflow latched
SR_ROTA   = 0x04         # remote overtemperature
SR_RHA    = 0x08         # remote high temperature
SR_LOTA   = 0x10         # local overtemperature
SR_LHA    = 0x20         # local high temperature
SR_RDFA   = 0x40         # remote diode fault (does not drive ALERT)
SR_PC     = 0x80         # EEPROM program-corrupt (needs POR/soft-POR to clear)
SR_ALARM_MASK = 0x7F     # all alarm bits except PC

# CR2 remaining control bits
CR2_STBY = 0x80          # standby mode
CR2_ALERTS = 0x40        # ALERT function selection (0=interrupt, 1=SHDN-like)
CR2_SPEN = 0x20          # spin-up enable
CR2_FSENABLE = 0x08      # full-speed input enable
CR2_RDPS = 0x04          # RD polarity: 1 = RD high means spinning
CR2_FSST = 0x02          # fan-sense signal type: 1 = RD/locked-rotor input

# FF-mode encodings (CR2.FFMODE)
FF_MODE_INTERRUPT = 0    # latched until CLRFAIL
FF_MODE_COMPARATOR = 1   # follows the live fault condition

# ALERT-mode encodings (CR2.ALERTS)
ALERT_MODE_INTERRUPT = 0       # latched; needs the service routine (factory)
ALERT_MODE_FAULT_INDICATOR = 1 # tracks the live LHA/RHA condition

# IFR index field (bits [5:0]; reserved upper bits should stay 0)
IFR_INDEX_MASK = 0x3F

# EEX block-select bits (register 0x5B; L/W = bit 7)
EEX_BLOCK_00_0F = 0x01   # control registers CR1..TCTL
EEX_BLOCK_10_1F = 0x02   # user memory (10h..17h) + padding
EEX_BLOCK_20_2F = 0x04   # LUT lower third
EEX_BLOCK_30_3F = 0x08   # LUT middle third
EEX_BLOCK_40_4F = 0x10   # LUT upper third
EEX_ALL_BLOCKS = 0x1F    # every nonvolatile block
EEX_LOAD_BIT = 0x80      # 1 = load EEPROM->RAM, 0 = write RAM->EEPROM

# Alert-mask alarm field (MASK register bits [5:0]; positions match SR flags)
MASK_ALARM_FIELD = 0x3F

# --- SR (5Ah) alarm bits (clear on read) ------------------------------------
SR_PC = 0x80         # program corrupt (EEPROM)
SR_RDFA = 0x40       # remote diode fault
SR_LHA = 0x20        # local high alarm
SR_LOTA = 0x10       # local overtemp alarm
SR_RHA = 0x08        # remote high alarm
SR_ROTA = 0x04       # remote overtemp alarm
SR_TACH2A = 0x02     # TACH2 alarm
SR_TACH1A = 0x01     # TACH1 alarm
SR_ALARM_MASK = 0x7F

# --- MASK (04h): mirrors SR alarm bits; bits 7:6 reserved (hold 1) ----------
MASK_RESERVED_HI = 0xC0
MASK_LHA = 0x20
MASK_LOTA = 0x10
MASK_RHA = 0x08
MASK_ROTA = 0x04
MASK_TACH2A = 0x02
MASK_TACH1A = 0x01

# --- EEX (5Bh): bit7 = L/W (1 = load EEPROM->RAM, 0 = save RAM->EEPROM); ----
# --- bits 4:0 = one bit per 16-byte block; auto-clears ----------------------
EEX_LOAD_BIT = 0x80
EEX_BLK_00_0F = 0x01
EEX_BLK_10_1F = 0x02
EEX_BLK_20_2F = 0x04
EEX_BLK_30_3F = 0x08
EEX_BLK_40_4F = 0x10
EEX_ALL_BLOCKS = 0x1F
EEX_SAVE_ALL = 0x1F
EEX_LOAD_ALL = 0x9F

# Data tables (factory defaults, ideality factors) live in _tables.py.

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
            "temperature %.3f C out of range -128.0..+127.875" % c)
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
        raise ValueError("duty %d out of range 0..255" % d)
    return d * 100.0 / 256.0


def pct_to_duty(pct):
    """Percent (0..100) to duty raw (0..255), rounded."""
    p = float(pct)
    if p < 0.0 or p > 100.0:
        raise ValueError("percent %.3f out of range 0..100" % p)
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


# ---------------------------------------------------------------------------
# Device class
# ---------------------------------------------------------------------------

# NOTE: _faults imports constants from this module, so this import MUST stay
# below every constant/helper definition above (ordering-safe circular import;
# entry points mp/cp always import _core first).
from ._faults import FaultMixin


class MAX31760(FaultMixin):
    """MAX31760 device API bound to a transport (see module docstring)."""

    # Public constants (usable as MAX31760.XXX; also exported by mp/cp).
    INDEX_LOCAL = INDEX_LOCAL
    INDEX_REMOTE = INDEX_REMOTE
    INDEX_MAX = INDEX_MAX
    RAMP_SLOW = RAMP_SLOW
    RAMP_MED_SLOW = RAMP_MED_SLOW
    RAMP_MED_FAST = RAMP_MED_FAST
    RAMP_IMMEDIATE = RAMP_IMMEDIATE
    PWM_FREQ_33HZ = PWM_FREQ_33HZ
    PWM_FREQ_150HZ = PWM_FREQ_150HZ
    PWM_FREQ_1P5KHZ = PWM_FREQ_1P5KHZ
    PWM_FREQ_25KHZ = PWM_FREQ_25KHZ
    POLARITY_POSITIVE = _POLARITY_POSITIVE
    POLARITY_NEGATIVE = _POLARITY_NEGATIVE
    SR_TACH1A = SR_TACH1A
    SR_TACH2A = SR_TACH2A
    SR_ROTA = SR_ROTA
    SR_RHA = SR_RHA
    SR_LOTA = SR_LOTA
    SR_LHA = SR_LHA
    SR_RDFA = SR_RDFA
    SR_PC = SR_PC
    SR_ALARM_MASK = SR_ALARM_MASK
    FF_MODE_INTERRUPT = FF_MODE_INTERRUPT
    FF_MODE_COMPARATOR = FF_MODE_COMPARATOR
    ALERT_MODE_INTERRUPT = ALERT_MODE_INTERRUPT
    ALERT_MODE_FAULT_INDICATOR = ALERT_MODE_FAULT_INDICATOR
    IDEALITY_TABLE = IDEALITY_TABLE
    EEX_BLOCK_00_0F = EEX_BLOCK_00_0F
    EEX_BLOCK_10_1F = EEX_BLOCK_10_1F
    EEX_BLOCK_20_2F = EEX_BLOCK_20_2F
    EEX_BLOCK_30_3F = EEX_BLOCK_30_3F
    EEX_BLOCK_40_4F = EEX_BLOCK_40_4F
    EEX_ALL_BLOCKS = EEX_ALL_BLOCKS

    def __init__(self, transport, addr=0x50):
        a = int(addr)
        if a < ADDR_MIN or a > ADDR_MAX:
            raise ValueError("address 0x%02X outside 0x%02X..0x%02X"
                             % (a, ADDR_MIN, ADDR_MAX))
        self._t = transport
        self._addr = a

    # -- low-level plumbing (internal) -------------------------------------

    def _tx(self, fn):
        """Run a transport transaction, retrying through transient NACKs.

        Live silicon (RPi 3A+, 2026-11-08) shows the MAX31760 genuinely
        NACKs its own address (reads stay live) while an EEPROM load
        commits new register values - a stall whose duration is variable
        (observed 6 ms to >200 ms; bounded by tW max 550 ms) and which can
        begin immediately AFTER a successful write, so no pre-wait alone
        can prevent hitting it. The escalating backoff ladder spans the
        full datasheet worst case and absorbs such finite transients
        transparently on every API call; a persistent fault still raises
        OSError after the final attempt.
        """
        last = None
        for i in range(len(RETRY_DELAYS_MS) + 1):
            try:
                return fn()
            except OSError as e:
                last = e
                if i < len(RETRY_DELAYS_MS):
                    self._t.delay_ms(RETRY_DELAYS_MS[i])
        raise last

    def _burst_read(self, reg, n):
        r = int(reg)
        nn = int(n)
        if nn < 1:
            raise ValueError("read length must be >= 1")
        if r < 0 or r + nn - 1 > REG_SR:
            raise ValueError("read 0x%02X+%d out of range 0x00..0x5A"
                             % (r, nn - 1))
        return self._tx(lambda: self._t.burst_read(r, nn))

    def _page_safe_write(self, reg, data):
        """Split data into chunks that never cross an 8-byte page row.

        The chip wraps the pointer WITHIN the page when a write crosses a
        boundary without STOP, so every chunk must start aligned to its page
        row and span at most PAGE_SIZE bytes.
        """
        pos = 0
        cur = reg
        total = len(data)
        while pos < total:
            room = PAGE_SIZE - (cur % PAGE_SIZE)
            chunk = data[pos:pos + room]
            self._tx(lambda: self._t.burst_write(cur, chunk))
            pos += len(chunk)
            cur += len(chunk)

    def _burst_write(self, reg, data):
        r = int(reg)
        b = bytes(bytearray(data))
        if len(b) < 1:
            raise ValueError("empty write buffer")
        end = r + len(b) - 1
        if r < 0 or end > REG_EEX:
            raise ValueError("write 0x%02X+%d out of range 0x00..0x5B"
                             % (r, len(b) - 1))
        if r <= REG_SR <= end:
            raise ValueError("write 0x%02X+%d overlaps read-only status "
                             "register 0x5A" % (r, len(b) - 1))
        self._page_safe_write(r, b)

    # -- public raw access (F22) --------------------------------------------

    def read_reg(self, reg, n=1):
        """Raw burst read of n bytes starting at reg (0x00..0x5A). -> bytes"""
        return self._burst_read(reg, n)

    def write_reg(self, reg, buf):
        """Raw page-safe write of buf (1..N bytes) starting at reg (0x00..0x5B)."""
        self._burst_write(reg, buf)

    def probe(self):
        """Address ACK check. -> bool"""
        return self._t.probe()

    # -- init / self-test (F1) -----------------------------------------------

    def scan(self):
        """Return the 7-bit slave addresses present on the bus (sorted ints).

        Discovery aid; use verify() for a pass/fail self-test.
        """
        return [int(a) for a in self._t.scan()]

    def verify(self):
        """Self-test: confirm the device acknowledges at the bound address.

        Raises OSError if the device does not answer. Returns True on success.
        """
        if not self.probe():
            raise OSError("MAX31760 not responding at 0x%02X" % self._addr)
        return True

    # -- temperatures & setpoints (F2, F3) -----------------------------------

    @property
    def local_temp_c(self):
        """Local (IC die) temperature in degrees C (float, 0.125 resolution)."""
        raw = self._burst_read(REG_LTH, 2)
        return raw16_to_temp((raw[0] << 8) | raw[1])

    @property
    def remote_temp_c(self):
        """Remote diode-junction temperature in degrees C (float, 0.125 res.)."""
        raw = self._burst_read(REG_RTH, 2)
        return raw16_to_temp((raw[0] << 8) | raw[1])

    def get_local_high(self):
        """Local high set point (LHS) in degrees C."""
        return self._setpoint_get(REG_LHSH)

    def set_local_high(self, celsius):
        """Set the local high set point (LHS), degrees C (-128..+127.875)."""
        self._setpoint_set(REG_LHSH, celsius)

    def get_remote_high(self):
        """Remote high set point (RHS) in degrees C."""
        return self._setpoint_get(REG_RHSH)

    def set_remote_high(self, celsius):
        """Set the remote high set point (RHS), degrees C (-128..+127.875)."""
        self._setpoint_set(REG_RHSH, celsius)

    def get_local_overtemp(self):
        """Local overtemperature set point (LOTS) in degrees C."""
        return self._setpoint_get(REG_LOTSH)

    def set_local_overtemp(self, celsius):
        """Set the local overtemperature set point (LOTS), degrees C."""
        self._setpoint_set(REG_LOTSH, celsius)

    def get_remote_overtemp(self):
        """Remote overtemperature set point (ROTS) in degrees C."""
        return self._setpoint_get(REG_ROTSH)

    def set_remote_overtemp(self, celsius):
        """Set the remote overtemperature set point (ROTS), degrees C."""
        self._setpoint_set(REG_ROTSH, celsius)

    # -- setpoint plumbing (internal) ----------------------------------------

    def _setpoint_get(self, hi_reg):
        raw = self._burst_read(hi_reg, 2)
        return raw16_to_temp((raw[0] << 8) | raw[1])

    def _setpoint_set(self, hi_reg, celsius):
        v = temp_to_raw16(celsius)
        self._burst_write(hi_reg, (v >> 8, v & 0xFF))

    # -- LUT (F4, F5) ---------------------------------------------------------

    def lut_get(self):
        """Read all 48 LUT entries. -> list of duty raws (0..255)."""
        data = self._burst_read(REG_LUT_BASE, LUT_LEN)
        return list(bytearray(data))

    def lut_set(self, duties):
        """Write all 48 LUT entries from an iterable of 48 ints (0..255)."""
        vals = bytearray()
        for d in duties:
            v = int(d)
            if v < 0 or v > 255:
                raise ValueError("duty %d out of range 0..255" % v)
            vals.append(v)
        if len(vals) != LUT_LEN:
            raise ValueError("LUT needs %d entries, got %d" % (LUT_LEN, len(vals)))
        self._burst_write(REG_LUT_BASE, vals)

    def lut_get_index(self, index):
        """Read one LUT entry (index 0..47). -> duty raw."""
        return self._burst_read(REG_LUT_BASE + self._lut_idx(index), 1)[0]

    def lut_set_index(self, index, duty):
        """Write one LUT entry (index 0..47) with a duty raw (0..255)."""
        v = int(duty)
        if v < 0 or v > 255:
            raise ValueError("duty %d out of range 0..255" % v)
        self._burst_write(REG_LUT_BASE + self._lut_idx(index), (v,))

    @staticmethod
    def _lut_idx(index):
        i = int(index)
        if i < 0 or i >= LUT_LEN:
            raise ValueError("LUT index %d out of range 0..%d" % (i, LUT_LEN - 1))
        return i

    # -- manual/auto modes & PWM output config (F6-F8) ------------------------

    def _cr1_rmw(self, mask, bits):
        """Read-modify-write of CR1 bit fields (other bits preserved)."""
        v = self._burst_read(REG_CR1, 1)[0]
        self._burst_write(REG_CR1, (((v & ~mask) | (bits & mask)) & 0xFF,))

    def _cr2_rmw(self, mask, bits):
        """Read-modify-write of CR2 bit fields (other bits preserved)."""
        v = self._burst_read(REG_CR2, 1)[0]
        self._burst_write(REG_CR2, (((v & ~mask) | (bits & mask)) & 0xFF,))

    def _cr3_rmw(self, mask, bits):
        """Read-modify-write of CR3 bit fields (other bits preserved)."""
        v = self._burst_read(REG_CR3, 1)[0]
        self._burst_write(REG_CR3, (((v & ~mask) | (bits & mask)) & 0xFF,))

    # F6: manual (direct) mode

    def manual_enable(self, on):
        """Enable (truthy) or disable (falsy) direct/manual fan control (CR2.DFC).

        Enabled: PWMR commands the output. Disabled: automatic LUT mode governs.
        """
        self._cr2_rmw(CR2_DFC, CR2_DFC if on else 0)

    def manual_enabled(self):
        """True if direct/manual fan control is currently enabled."""
        return bool(self._burst_read(REG_CR2, 1)[0] & CR2_DFC)

    def set_duty_pct(self, pct):
        """Set the commanded fan duty, percent 0..100 (written to PWMR)."""
        self._burst_write(REG_PWMR, (pct_to_duty(pct),))

    def set_duty_raw(self, raw):
        """Set the commanded fan duty, raw 0..255 (written to PWMR)."""
        d = int(raw)
        if d < 0 or d > 255:
            raise ValueError("duty %d out of range 0..255" % d)
        self._burst_write(REG_PWMR, (d,))

    def get_duty_cmd_raw(self):
        """Read back the commanded duty (PWMR), raw 0..255."""
        return self._burst_read(REG_PWMR, 1)[0]

    def get_actual_duty_raw(self):
        """Read the actual output duty (PWMV, RO), raw 0..255."""
        return self._burst_read(REG_PWMV, 1)[0]

    def get_actual_duty_pct(self):
        """Actual output duty (PWMV, RO) as a percent float."""
        return duty_to_pct(self.get_actual_duty_raw())

    # F7: automatic-mode configuration

    def set_index_source(self, source):
        """Select the LUT index source: INDEX_LOCAL / INDEX_REMOTE / INDEX_MAX."""
        if source not in (INDEX_LOCAL, INDEX_REMOTE, INDEX_MAX):
            raise ValueError("unknown index source 0x%02X" % int(source))
        self._cr1_rmw(CR1_MTI | CR1_TIS, source)

    def get_index_source(self):
        """Current LUT index source (one of the INDEX_* constants)."""
        return self._burst_read(REG_CR1, 1)[0] & (CR1_MTI | CR1_TIS)

    def set_hysteresis_c(self, celsius):
        """Set the LUT hysteresis: 2 or 4 degrees C."""
        c = int(celsius)
        if c not in (2, 4):
            raise ValueError("hysteresis must be 2 or 4 C")
        self._cr1_rmw(CR1_HYST, CR1_HYST if c == 4 else 0)

    def get_hysteresis_c(self):
        """Current LUT hysteresis in degrees C (2 or 4)."""
        return 4 if self._burst_read(REG_CR1, 1)[0] & CR1_HYST else 2

    # F8: PWM output configuration

    def set_pwm_freq_hz(self, hz):
        """Set the PWM frequency: 33, 150, 1500 or 25000 Hz."""
        h = int(hz)
        for f, b in _PWM_FREQ_TO_BITS:
            if h == f:
                self._cr1_rmw(CR1_DRV_MASK, b)
                return
        raise ValueError("PWM frequency %d Hz unsupported (use 33/150/1500/25000)"
                         % h)

    def get_pwm_freq_hz(self):
        """Current PWM frequency in Hz (33, 150, 1500 or 25000)."""
        v = self._burst_read(REG_CR1, 1)[0] & CR1_DRV_MASK
        for f, b in _PWM_FREQ_TO_BITS:
            if v == b:
                return f
        return PWM_FREQ_33HZ

    def set_pwm_polarity(self, polarity):
        """Set PWM polarity: POLARITY_POSITIVE (default) or POLARITY_NEGATIVE."""
        p = int(polarity)
        if p not in (_POLARITY_POSITIVE, _POLARITY_NEGATIVE):
            raise ValueError("polarity must be POLARITY_POSITIVE or POLARITY_NEGATIVE")
        self._cr1_rmw(CR1_PPS_NEGATIVE, CR1_PPS_NEGATIVE if p else 0)

    def get_pwm_polarity(self):
        """Current PWM polarity (POLARITY_POSITIVE or POLARITY_NEGATIVE)."""
        if self._burst_read(REG_CR1, 1)[0] & CR1_PPS_NEGATIVE:
            return _POLARITY_NEGATIVE
        return _POLARITY_POSITIVE

    # -- ramp rate & duty settling (F9) ---------------------------------------

    def set_ramp_rate(self, rate):
        """Set the duty ramp rate: RAMP_SLOW / RAMP_MED_SLOW / RAMP_MED_FAST /
        RAMP_IMMEDIATE (CR3 bits [5:4])."""
        if rate not in (RAMP_SLOW, RAMP_MED_SLOW, RAMP_MED_FAST, RAMP_IMMEDIATE):
            raise ValueError("unknown ramp rate 0x%02X" % int(rate))
        v = self._burst_read(REG_CR3, 1)[0]
        self._burst_write(REG_CR3, (((v & ~CR3_RAMP_MASK) | rate) & 0xFF,))

    def get_ramp_rate(self):
        """Current ramp rate (one of the RAMP_* constants)."""
        return self._burst_read(REG_CR3, 1)[0] & CR3_RAMP_MASK

    def wait_for_duty(self, target_pct, timeout_ms=2000):
        """Wait until the actual output duty (PWMV) reaches target_pct.

        Returns True when reached; raises TimeoutError after timeout_ms.
        Polls every 10 ms; the target is quantized to the 0..255 duty grid.
        """
        target = pct_to_duty(target_pct)
        deadline = int(timeout_ms)
        if deadline < 0:
            raise ValueError("timeout_ms must be >= 0")
        while True:
            if self.get_actual_duty_raw() == target:
                return True
            if deadline <= 0:
                raise TimeoutError(
                    "duty did not reach %.1f%% within %d ms"
                    % (float(target_pct), int(timeout_ms)))
            self._t.delay_ms(10)
            deadline -= 10

    # -- tachometer inputs (F11, F12) ------------------------------------------

    def tach1_enable(self, on):
        """Enable (truthy) or disable (falsy) TACH1 counting (CR3.TACH1E)."""
        self._cr3_rmw(CR3_TACH1E, CR3_TACH1E if on else 0)

    def tach1_enabled(self):
        """True if TACH1 counting is enabled."""
        return bool(self._burst_read(REG_CR3, 1)[0] & CR3_TACH1E)

    def tach2_enable(self, on):
        """Enable (truthy) or disable (falsy) TACH2 counting (CR3.TACH2E)."""
        self._cr3_rmw(CR3_TACH2E, CR3_TACH2E if on else 0)

    def tach2_enabled(self):
        """True if TACH2 counting is enabled."""
        return bool(self._burst_read(REG_CR3, 1)[0] & CR3_TACH2E)

    def rpm(self, port=1, pulses_per_rev=2):
        """Read the fan speed on port 1 or 2 in RPM.

        pulses_per_rev is the fan's tach output frequency per revolution
        (commonly 2). Returns 0.0 when the counter reads zero (fan stopped
        or no pulses). A very slow fan whose count overflows surfaces as the
        corresponding TACHxA alarm bit (see status()), not a bogus number.
        """
        p = int(port)
        if p not in (1, 2):
            raise ValueError("port must be 1 or 2")
        n = int(pulses_per_rev)
        if n < 1:
            raise ValueError("pulses_per_rev must be >= 1")
        hi, lo = (REG_TC1H, REG_TC1L) if p == 1 else (REG_TC2H, REG_TC2L)
        raw = self._burst_read(hi, 2)
        count = (raw[0] << 8) | raw[1]
        if count == 0:
            return 0.0
        return (60.0 * TACH_REF_HZ) / (count * n)

    def set_tach_threshold(self, count):
        """Set the minimum-RPM fail threshold (TCTH:TCTL), 0..65535.

        The fan is considered failed when its measured count exceeds this
        value (or overflows). Factory default is 65534 (effectively off).
        """
        c = int(count)
        if c < 0 or c > 0xFFFF:
            raise ValueError("threshold %d out of range 0..65535" % c)
        self._burst_write(REG_TCTH, ((c >> 8) & 0xFF, c & 0xFF))

    def get_tach_threshold(self):
        """Current minimum-RPM fail threshold (TCTH:TCTL), 0..65535."""
        raw = self._burst_read(REG_TCTH, 2)
        return (raw[0] << 8) | raw[1]

    # -- 3-wire assist & spin-up (F10, F15) ------------------------------------

    def spin_up_enable(self, on):
        """Enable/disable fan spin-up (CR2.SPEN).

        When enabled, any change of the selected duty from zero to nonzero
        drives the PWM to 100 % until either a 2 s timeout expires or two
        tach pulses are seen at each enabled TACH input; afterwards the
        output reverts to LUT/manual duty.
        """
        self._cr2_rmw(CR2_SPEN, CR2_SPEN if on else 0)

    def spin_up_enabled(self):
        """True if fan spin-up is enabled (CR2.SPEN)."""
        return bool(self._burst_read(REG_CR2, 1)[0] & CR2_SPEN)

    def pulse_stretch_enable(self, on):
        """Enable/disable periodic pulse stretching (CR3.PSEN).

        While enabled — and only when PWM freq = 33 Hz and TACHFULL = 0 — a
        stretched PWM pulse is inserted ~every 12 s so the TACH counters can
        update even at low duty. For a single on-demand update use
        measure_tach_once() instead of leaving this on.
        """
        self._cr3_rmw(CR3_PSEN, CR3_PSEN if on else 0)

    def pulse_stretch_enabled(self):
        """True if periodic pulse stretching is enabled (CR3.PSEN)."""
        return bool(self._burst_read(REG_CR3, 1)[0] & CR3_PSEN)

    def tacho_full_enable(self, on):
        """Enable/disable TACHFULL (CR3.TACHFULL).

        When set, TACH measurements are valid only at 100 % duty and fan-fail
        detection is disabled below 100 %. Pulse stretching is ignored while
        TACHFULL is set.
        """
        self._cr3_rmw(CR3_TACHFULL, CR3_TACHFULL if on else 0)

    def tacho_full_enabled(self):
        """True if TACHFULL mode is enabled (CR3.TACHFULL)."""
        return bool(self._burst_read(REG_CR3, 1)[0] & CR3_TACHFULL)

    def measure_tach_once(self, port=1, timeout_ms=3000):
        """One-shot TACH counter update via pulse stretching (PSEN).

        Sets PSEN, waits up to timeout_ms for the TC register to update
        (a stretched pulse lasts up to ~2.6 s worst case), clears PSEN and
        returns the new count. The fan will visibly speed up during the
        stretched pulse. Requires 33 Hz PWM with TACHFULL disabled (the
        silicon ignores PSEN otherwise); ValueError raised if violated.
        """
        p = int(port)
        if p not in (1, 2):
            raise ValueError("port must be 1 or 2")
        if self.get_pwm_freq_hz() != PWM_FREQ_33HZ:
            raise ValueError("pulse stretching requires 33 Hz PWM")
        if self.tacho_full_enabled():
            raise ValueError("pulse stretching requires TACHFULL disabled")
        reg = REG_TC1H if p == 1 else REG_TC2H
        raw = self._burst_read(reg, 2)
        base = (raw[0] << 8) | raw[1]
        cnt = base
        self.pulse_stretch_enable(True)
        try:
            waited = 0
            while waited < int(timeout_ms):
                self._t.delay_ms(50)
                waited += 50
                raw = self._burst_read(reg, 2)
                cnt = (raw[0] << 8) | raw[1]
                if cnt != base:
                    break
            return cnt
        finally:
            self.pulse_stretch_enable(False)

    # -- ALERT service & ideality factor (F18, F19) -----------------------------

    def set_alert_mode(self, mode):
        """Select ALERT output behaviour (CR2.ALERTS):
        ALERT_MODE_INTERRUPT (latched, serviced via service_alert(); factory
        default) or ALERT_MODE_FAULT_INDICATOR (tracks the live LHA/RHA
        condition and deasserts when it clears)."""
        m = int(mode)
        if m not in (ALERT_MODE_INTERRUPT, ALERT_MODE_FAULT_INDICATOR):
            raise ValueError("unknown alert mode %d" % m)
        self._cr2_rmw(CR2_ALERTS,
                      CR2_ALERTS if m == ALERT_MODE_FAULT_INDICATOR else 0)

    def get_alert_mode(self):
        """Current ALERT mode (ALERT_MODE_INTERRUPT or
        ALERT_MODE_FAULT_INDICATOR)."""
        if self._burst_read(REG_CR2, 1)[0] & CR2_ALERTS:
            return ALERT_MODE_FAULT_INDICATOR
        return ALERT_MODE_INTERRUPT

    def service_alert(self):
        """Step 2 of the datasheet ALERT interrupt-service sequence: read SR.

        Reading SR identifies the cause and clears LHA/RHA/LOTA/ROTA; the
        device resets the ALERT pin to high impedance and holds ALTMSK=1,
        masking new alerts, until clear_alert_mask() is called AFTER the
        triggering condition has been attended to (step 5). Returns the
        latched SR value (test against the SR_* flag constants).
        """
        return self.status_raw()

    def alert_masked(self):
        """True while ALTMSK (CR1.7) masks new ALERT assertions."""
        return bool(self._burst_read(REG_CR1, 1)[0] & CR1_ALTMSK)

    def clear_alert_mask(self):
        """Step 5 of the ALERT ISR sequence: write 0 to CR1.ALTMSK so new
        temperature alerts can assert ALERT again. Call only after the
        triggering condition has been attended to."""
        self._cr1_rmw(CR1_ALTMSK, 0)

    def set_ideality_factor_index(self, idx):
        """Set the ideality-factor table index (IFR bits [5:0]), 0..63.
        Reserved upper bits (which should stay 0) are preserved."""
        i = int(idx)
        if i < 0 or i >= len(IDEALITY_TABLE):
            raise ValueError("ideality index %d out of range 0..%d"
                             % (i, len(IDEALITY_TABLE) - 1))
        v = self._burst_read(REG_IFR, 1)[0]
        self._burst_write(REG_IFR, (((v & ~IFR_INDEX_MASK) | i) & 0xFF,))

    def get_ideality_factor_index(self):
        """Current ideality-factor table index (IFR bits [5:0]), 0..63."""
        return self._burst_read(REG_IFR, 1)[0] & IFR_INDEX_MASK

    def get_ideality_factor(self):
        """The ideality factor currently programmed (table lookup), float."""
        return IDEALITY_TABLE[self.get_ideality_factor_index()]

    def set_ideality_factor(self, n):
        """Program the ideality factor closest to n (nearest-match table
        lookup) and return the index used. Raises ValueError if n lies
        outside the table range (0.9844 .. 1.0489); ties resolve to the
        lower index."""
        f = float(n)
        lo, hi = IDEALITY_TABLE[0], IDEALITY_TABLE[-1]
        if f < lo or f > hi:
            raise ValueError("ideality factor %.4f outside table range "
                             "%.4f..%.4f" % (f, lo, hi))
        best_i, best_d = 0, abs(IDEALITY_TABLE[0] - f)
        for i in range(1, len(IDEALITY_TABLE)):
            d = abs(IDEALITY_TABLE[i] - f)
            if d < best_d:
                best_i, best_d = i, d
        self.set_ideality_factor_index(best_i)
        return best_i

    # -- EEPROM lifecycle (F20) --------------------------------------------------

    def save_config(self, blocks=EEX_ALL_BLOCKS, timeout_ms=2000):
        """Write RAM to EEPROM for the selected blocks (EEX, L/W=0).

        blocks is a bitmask of EEX_BLOCK_* constants (default: all). Per the
        datasheet the EEPROM write begins at the STOP of the EEX transaction;
        this method waits out the busy window (see _wait_eeprom_ready) and
        raises TimeoutError on overrun. Power must remain stable for the
        duration of the write.
        """
        b = int(blocks)
        if b == 0 or b > EEX_ALL_BLOCKS:
            raise ValueError("block select 0x%02X invalid" % b)
        self._burst_write(REG_EEX, ((b & EEX_ALL_BLOCKS),))
        self._wait_eeprom_ready(timeout_ms)

    def load_config(self, blocks=EEX_ALL_BLOCKS, timeout_ms=2000):
        """Load EEPROM into RAM for the selected blocks (EEX, L/W=1).

        Same block-select semantics and busy-window wait as save_config().
        """
        b = int(blocks)
        if b == 0 or b > EEX_ALL_BLOCKS:
            raise ValueError("block select 0x%02X invalid" % b)
        self._burst_write(REG_EEX, (EEX_LOAD_BIT | (b & EEX_ALL_BLOCKS),))
        self._wait_eeprom_ready(timeout_ms)

    def _wait_eeprom_ready(self, timeout_ms):
        """Wait out the EEPROM busy window with a pure delay.

        Datasheet: tW is typically 110 ms per 16-byte block, MAX 550 ms for
        the full 80-byte range, and the recommended alternative to
        ack-polling is simply to wait out the maximum tW before accessing
        the device. Live silicon (RPi 3A+, 2026-11-08) shows ack-polling is
        unreliable in BOTH directions - the device ACKs stray probes before
        it latches the EEX command, and while a LOAD commits new register
        values it genuinely NACKs its own address (reads stay live) for a
        variable time observed up to ~600 ms - so this waits a fixed 700 ms
        (above the datasheet worst case) with ZERO bus traffic: probes and
        oracle writes demonstrably interact badly with the silicon. The _tx
        retry ladder remains as a safety net beyond the guarantee.
        Raises TimeoutError if timeout_ms < 700 (readiness cannot be
        guaranteed within the given budget).
        """
        limit = int(timeout_ms)
        if limit < 0:
            raise ValueError("timeout_ms must be >= 0")
        if limit < EEPROM_WAIT_MS:
            raise TimeoutError(
                "EEPROM busy after %d ms (need >= %d)" % (limit, EEPROM_WAIT_MS))
        self._t.delay_ms(EEPROM_WAIT_MS)

    def eeprom_corrupt(self):
        """True if SR.PC indicates an EEPROM program-corruption event.

        PC persists across SR reads (unlike the other alarm bits) and only
        clears after a successful EEPROM write followed by POR/soft-POR.
        Note: the underlying SR read still clears the OTHER alarm bits.
        """
        return bool(self.status_raw() & SR_PC)

    def recover_from_corruption(self, timeout_ms=2000):
        """Recover from a program-corrupt condition (SR.PC set).

        Re-writes ALL blocks from the current RAM (which must hold the
        desired values), issues a soft POR so the chip reloads from EEPROM,
        and verifies PC cleared. Returns True on success, False otherwise.
        """
        self.save_config(EEX_ALL_BLOCKS, timeout_ms)
        self.soft_por()
        return not self.eeprom_corrupt()

    # -- lifecycle: soft POR, standby, user memory (F21) ------------------------

    def soft_por(self, settle_ms=1000):
        """Issue a software power-on reset (CR1.SW_POR, self-clearing).

        The device resets and reloads RAM from EEPROM; latched alarms and
        volatile state are lost.

        IMPORTANT (live silicon, RPi 3A+, 2026-11-08): the POR executes as
        soon as the SW_POR bit is latched, and the chip resets so fast that
        the in-flight I2C transaction commonly reports an error (errno 121
        on Linux bcm2835) even though the reset HAPPENED. Retrying the
        write would re-trigger another POR, so the write is issued exactly
        once, outside the normal retry ladder, and any OSError from it is
        expected and swallowed. Afterward the method polls until the device
        acknowledges again (up to settle_ms; the default of 1000 ms covers
        pathological boot times), verifies responsiveness, then waits out
        the EEPROM-reload busy window (the POR performs an implicit load -
        see _wait_eeprom_ready). Raises OSError only if the device never
        comes back within settle_ms.
        """
        cur = self._burst_read(REG_CR1, 1)[0]
        try:
            # Raw transport call, deliberately bypassing _tx: NO retries
            # here (a retry re-fires the POR into a still-booting chip).
            self._t.burst_write(REG_CR1, ((cur | CR1_SW_POR) & 0xFF,))
        except OSError:
            pass  # expected: chip resets mid-transaction
        waited = 0
        while not self._t.probe() and waited < settle_ms:
            self._t.delay_ms(10)
            waited += 10
        if not self._t.probe():
            raise OSError("device not responding after soft POR")
        self._wait_eeprom_ready(2000)

    def enter_standby(self):
        """Enter standby mode (CR2.STBY): sensing/PWM off, I2C stays active."""
        self._cr2_rmw(CR2_STBY, CR2_STBY)

    def exit_standby(self):
        """Exit standby mode (CR2.STBY)."""
        self._cr2_rmw(CR2_STBY, 0)

    def standby_active(self):
        """True if the device is in standby mode (CR2.STBY)."""
        return bool(self._burst_read(REG_CR2, 1)[0] & CR2_STBY)

    def user_memory_get(self, index=0):
        """Read one byte of general-purpose user memory (10h..17h), 0..7."""
        i = int(index)
        if i < 0 or i > 7:
            raise ValueError("user memory index %d out of range 0..7" % i)
        return self._burst_read(REG_USER_BASE + i, 1)[0]

    def user_memory_set(self, index, value):
        """Write one byte of general-purpose user memory (10h..17h), 0..7."""
        i = int(index)
        v = int(value)
        if i < 0 or i > 7:
            raise ValueError("user memory index %d out of range 0..7" % i)
        if v < 0 or v > 255:
            raise ValueError("user memory value %d out of range 0..255" % v)
        self._burst_write(REG_USER_BASE + i, (v,))

    def user_memory_read_all(self):
        """All 8 bytes of user memory as a bytes object."""
        return self._burst_read(REG_USER_BASE, 8)

    def user_memory_write_all(self, data):
        """Write all 8 bytes of user memory (len(data) must be 8)."""
        d = bytes(bytearray(data))
        if len(d) != 8:
            raise ValueError("expected 8 bytes, got %d" % len(d))
        self._burst_write(REG_USER_BASE, d)

    # -- presets (F24) -----------------------------------------------------------

    def _single_port_hygiene(self, port):
        """Enable the selected port's tach, disable the other, clear any
        latched fan-fail (mandatory single-fan config, see D11)."""
        p = int(port)
        if p == 1:
            self.tach1_enable(True)
            self.tach2_enable(False)
        elif p == 2:
            self.tach2_enable(True)
            self.tach1_enable(False)
        else:
            raise ValueError("port must be 1 or 2")
        self.clear_fan_fail()

    def configure_4wire_fan(self, port=1, pwm_freq_hz=PWM_FREQ_25KHZ):
        """Standard 4-wire fan on the given port (datasheet Figure 2a).

        Sets the recommended 25 kHz PWM frequency, enables the port's
        tachometer, and applies single-fan hygiene (unused port disabled,
        fan-fail cleared). The fan's PWM input wires to the device PWM out.
        Does not change the control mode: call manual_enable(True) if you
        intend to drive the output with set_duty_pct(); otherwise the LUT
        governs (factory default).
        """
        self.set_pwm_freq_hz(pwm_freq_hz)
        self._single_port_hygiene(port)

    def configure_3wire_supply_modulation(self, port=1):
        """3-wire fan driven by PWM supply modulation (Figure 2b).

        The fan supply rail is chopped by the PWM output, so the typical
        33 Hz frequency is used and pulse stretching (PSEN) is enabled so
        the tachometer remains measurable while the supply is modulated.
        Applies single-fan hygiene for the selected port. As with the other
        presets, this does not change the control mode: enable manual mode
        (manual_enable(True)) to drive the duty with set_duty_pct().
        """
        self.set_pwm_freq_hz(PWM_FREQ_33HZ)
        self.pulse_stretch_enable(True)
        self._single_port_hygiene(port)

    def configure_two_fans(self, pwm_freq_hz=PWM_FREQ_25KHZ):
        """Two fans, one per port (both monitored).

        Enables both tachometers and clears any latched fan-fail. Note the
        single PWM output drives both fans simultaneously, and fan-fail
        force (FFDC) applies to the shared output.
        """
        self.set_pwm_freq_hz(pwm_freq_hz)
        self.tach1_enable(True)
        self.tach2_enable(True)
        self.clear_fan_fail()

