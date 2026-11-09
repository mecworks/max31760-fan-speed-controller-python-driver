"""smbus2-compatible facade over MockChip for CPython-adapter unit tests.

Models REAL smbus2 wire semantics (verified against live MAX31760 @ RPi 3A+
on 2026-11-08):
  - read_i2c_block_data(addr, reg, qty) returns exactly qty clean payload
    bytes - NO count byte, NO register-byte prefix (the kernel/smbus2
    consume the count internally)
  - block reads are limited to 32 bytes (raises ValueError beyond)
  - reads AND writes stay live during the EEPROM busy window (live silicon
    verified: only address probes/stray traffic see the tW NACK behavior,
    and even that is unreliable) - so no per-transaction busy gating here
Raises OSError on NACK, like smbus2/smbus do.
"""

from mock_i2c import MockChip

_BLOCK_LIMIT = 32


class FakeSMBus(object):
    def __init__(self, bus_num, chip=None):
        self.bus = int(bus_num)
        self.chip = chip if chip is not None else MockChip()
        self.closed = False
        self.block_reads = []   # qty of each block read (assert <= 32)

    def read_i2c_block_data(self, addr, reg, qty):
        if self.chip.nack:
            raise OSError(5, "NACK")
        if qty > _BLOCK_LIMIT:
            raise ValueError("quantity too large for block read")
        self.block_reads.append(qty)
        data = self.chip.burst_read(reg, qty, addr=addr)
        return list(data)          # clean payload, smbus2 contract

    def write_i2c_block_data(self, addr, reg, data):
        if self.chip.nack:
            raise OSError(5, "NACK")
        self.chip.burst_write(reg, bytes(bytearray(data)), addr=addr)

    def read_byte_data(self, addr, reg):
        if self.chip.nack:
            raise OSError(5, "NACK")
        return self.chip.burst_read(reg, 1, addr=addr)[0]

    def close(self):
        self.closed = True
