"""Wire-level behavioral model of the MAX31760 for host unit tests.

Emulates the semantics that matter to the driver:
  - pointer-incrementing writes with 8-byte PAGE WRAP (crossing a page
    boundary without STOP wraps within the page -> data lands at wrong
    addresses; this is how the real chip misbehaves on unchunked writes)
  - burst reads spanning pages freely (legal per datasheet)
  - SR alarm bits clear on read; PC (bit 7) PERSISTS across reads and only
    clears on POR/soft-POR after a successful EEPROM write
  - EEX: L/W + block-select decoded; RAM<->EEPROM copy applied when the
    tW window elapses (the mock applies it at the end of the EEX write;
    probe() still NACKs for a few calls to model the tW window)
  - CR1.SW_POR: resets sr_latch and reloads RAM from EEPROM (all blocks);
    the chip is unresponsive for a few probe() calls afterwards (models
    the live-silicon behavior where the reset completes mid-transaction
    and the master sees errno 121 even though the POR happened)
  - NACK injection (OSError) for retry tests
  - protocol-violation log: any burst_write > 8 bytes or ending off the
    page-row alignment it started on is recorded (a correct driver never
    produces one)
"""

from max31760._core import FACTORY_DEFAULTS, LUT_FACTORY_VALUE, \
    USER_FACTORY_VALUE, REG_SR, REG_EEX, REG_CR1, CR1_SW_POR

NUM_REGS = 0x5C          # registers 0x00..0x5B inclusive
PAGE_SIZE = 8


class MockChip(object):
    def __init__(self, addrs=(0x50,)):
        self.addrs = set(int(a) for a in addrs)  # which slave addresses ACK
        self.regs = bytearray(NUM_REGS)
        for r, v in FACTORY_DEFAULTS.items():
            self.regs[r] = v
        for i in range(8):
            self.regs[0x10 + i] = USER_FACTORY_VALUE
        for i in range(48):
            self.regs[0x20 + i] = LUT_FACTORY_VALUE
        self.nack = False              # when True, every transaction raises OSError
        self.txns = []                 # (kind, reg, length) log
        self.violations = []           # (reg, length) of illegal write chunks
        self.sr_latch = 0x00           # persistent alarm state (SR clears on read)
        self.eeprom_ops = []           # EEX values written (phase B/C use)
        # EEPROM model: mirrors registers 0x00..0x4F (the nonvolatile range)
        self.eeprom = bytearray(self.regs[:0x50])
        self.busy_polls = 0            # remaining tW NACK probes after an EEX op
        self.boot_polls = 0            # remaining unresponsive probes after POR
        self._pending_eex = None       # (load, blocks) awaiting the tW window end

    # -- EEPROM / POR helpers ---------------------------------------------------

    @staticmethod
    def _block_ranges(blocks):
        ranges = []
        for bit, base in ((0x01, 0x00), (0x02, 0x10), (0x04, 0x20),
                          (0x08, 0x30), (0x10, 0x40)):
            if blocks & bit:
                ranges.append((base, base + 0x10))
        return ranges

    def _apply_eex(self):
        load, blocks = self._pending_eex
        self._pending_eex = None
        for start, end in self._block_ranges(blocks):
            if load:
                self.regs[start:end] = self.eeprom[start:end]
            else:
                self.eeprom[start:end] = self.regs[start:end]

    def _por(self):
        """Simulate POR/soft-POR: reload RAM from EEPROM, clear latches,
        go briefly unresponsive (chip re-initializes). A POR also cancels
        any outstanding EEPROM busy window - all internal state resets."""
        self.regs[:0x50] = self.eeprom[:0x50]
        self.sr_latch = 0x00
        self.busy_polls = 0
        self.boot_polls = 3

    # -- wire-level operations ----------------------------------------------

    def require_ack(self, addr):
        """Raise OSError (NACK) if no device listens at addr."""
        if int(addr) not in self.addrs:
            raise OSError(5, "NACK (no device at 0x%02X)" % int(addr))

    def burst_write(self, reg, data, addr=0x50):
        self.require_ack(addr)
        if self.nack:
            raise OSError(5, "NACK")
        if self.boot_polls > 0:
            self.boot_polls -= 1      # each bus contact ticks boot forward
            raise OSError(5, "NACK (re-initializing)")
        data = bytes(bytearray(data))
        self.txns.append(("w", reg, len(data)))
        if (reg + len(data) - 1) // PAGE_SIZE != reg // PAGE_SIZE:
            # chunk crosses a page-row boundary => chip will wrap mid-write
            self.violations.append((reg, len(data)))
        ptr = reg
        for b in data:
            self.regs[ptr] = b
            ptr += 1
            if ptr % PAGE_SIZE == 0:
                ptr -= PAGE_SIZE      # wrap within page (chip behavior)
        if reg == REG_EEX:
            self.eeprom_ops.append(data[-1])
            v = data[-1]
            self._pending_eex = (bool(v & 0x80), v & 0x1F)
            self.busy_polls = 3       # simulate the tW NACK window
            self._apply_eex()         # copy completes within tW; the mock
                                       # models it as done-at-write-end
        if reg == REG_CR1 and data and (data[0] & CR1_SW_POR):
            self._por()

    def burst_read(self, reg, n, addr=0x50):
        self.require_ack(addr)
        if self.nack:
            raise OSError(5, "NACK")
        if self.boot_polls > 0:
            self.boot_polls -= 1      # each bus contact ticks boot forward
            raise OSError(5, "NACK (re-initializing)")
        if reg < 0 or reg + n > NUM_REGS:
            raise OSError(6, "out of range")
        self.txns.append(("r", reg, n))
        out = bytearray(self.regs[reg:reg + n])
        if reg <= REG_SR <= reg + n - 1:
            out[REG_SR - reg] = self.sr_latch
            self.sr_latch &= 0x80     # alarm bits clear on read; PC persists
        return bytes(out)

    def set_sr(self, value):
        """Test helper: latch alarm bits into SR."""
        self.sr_latch = value & 0xFF

    def probe_ok(self, addr=0x50):
        if int(addr) not in self.addrs or self.nack:
            return False
        if self.boot_polls > 0:
            self.boot_polls -= 1
            return False              # chip still re-initializing
        if self.busy_polls > 0:
            self.busy_polls -= 1
            if self.busy_polls == 0 and self._pending_eex is not None:
                self._apply_eex()
            return False              # device NACKs during tW
        return True


class MockTransport(object):
    """Transport-contract wrapper over MockChip (for _core tests)."""

    def __init__(self, chip, addr=0x50):
        self.chip = chip
        self.addr = addr
        self.delays = []

    def burst_read(self, reg, n):
        return self.chip.burst_read(reg, n, addr=self.addr)

    def burst_write(self, reg, data):
        self.chip.burst_write(reg, data, addr=self.addr)

    def probe(self):
        return self.chip.probe_ok(self.addr)

    def scan(self):
        return tuple(sorted(self.chip.addrs))

    def delay_ms(self, ms):
        self.delays.append(ms)


class FlakyTransport(MockTransport):
    """Fails its first `fails` transactions with OSError, then succeeds."""

    def __init__(self, chip, fails=1, addr=0x50):
        super(FlakyTransport, self).__init__(chip, addr)
        self.fails = fails

    def _maybe_fail(self):
        if self.fails > 0:
            self.fails -= 1
            raise OSError(5, "injected NACK")

    def burst_read(self, reg, n):
        self._maybe_fail()
        return self.chip.burst_read(reg, n)

    def burst_write(self, reg, data):
        self._maybe_fail()
        self.chip.burst_write(reg, data)
