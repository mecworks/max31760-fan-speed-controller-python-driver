"""CPython transport adapter (smbus2, fallback: system smbus).

Linux-only in practice. Wraps the kernel i2c-dev interface via /dev/i2c-N.
The smbus library is imported lazily (only when opening a real bus), so this
module can be imported - and tested with an injected fake handle - on any host.
Long reads are chunked at the 32-byte I2C block-read protocol limit; each
chunk re-addresses the continuing register, which is legal because reads may
span pages freely.

Handle contract: read_i2c_block_data(addr, reg, n) returns exactly n payload
bytes (smbus2 semantics - the count byte is consumed internally by the
kernel/smbus2). The legacy system smbus module instead prepends the count
byte and takes no length argument; _SmbusCompat normalizes it to the same
contract. Verified against live silicon (MAX31760 @ RPi 3A+, 2026-11-08):
smbus2 block reads return clean payloads.
"""

import time

_BLOCK_READ_LIMIT = 32  # I2C block-read protocol limit (kernel enforces this)
_SCAN_MIN = 0x03         # conventional i2cdetect candidate range
_SCAN_MAX = 0x77


class _SmbusCompat(object):
    """Normalizes legacy smbus to the smbus2 block-read contract.

    Legacy smbus read_i2c_block_data(addr, cmd) takes no length argument and
    returns [count_byte, data...]; smbus2 takes a length and returns the
    clean payload. All other methods match between the two libraries.
    """

    def __init__(self, bus):
        self._bus = bus

    def read_i2c_block_data(self, addr, reg, qty):
        data = self._bus.read_i2c_block_data(addr, reg)
        return list(data[1:qty + 1])  # drop count byte, keep payload

    def write_i2c_block_data(self, addr, reg, data):
        self._bus.write_i2c_block_data(addr, reg, data)

    def read_byte_data(self, addr, reg):
        return self._bus.read_byte_data(addr, reg)

    def write_byte_data(self, addr, reg, val):
        return self._bus.write_byte_data(addr, reg, val)

    def close(self):
        self._bus.close()


def _open_smbus(bus):
    """Open a real SMBus handle, preferring smbus2 over system smbus."""
    try:
        import smbus2 as _mod
        return _mod.SMBus(int(bus))
    except ImportError:
        import smbus as _mod
        return _SmbusCompat(_mod.SMBus(int(bus)))


class TransportCP(object):
    """Adapts an SMBus handle to the transport contract.

    Args:
        bus:    I2C bus number (RPi default 1 = /dev/i2c-1).
        addr:   7-bit slave address (0x50..0x57).
        handle: optional pre-opened smbus2/smbus object (used as-is, not closed).
    """

    def __init__(self, bus=1, addr=0x50, handle=None):
        self._addr = int(addr)
        if handle is None:
            self._bus = _open_smbus(bus)
            self._owns_bus = True
        else:
            self._bus = handle
            self._owns_bus = False

    def burst_read(self, reg, n):
        out = bytearray()
        off = 0
        while off < n:
            chunk = min(_BLOCK_READ_LIMIT, n - off)
            data = self._bus.read_i2c_block_data(self._addr, reg + off, chunk)
            out.extend(data[:chunk])  # clean payload per handle contract
            off += chunk
        return bytes(out)

    def burst_write(self, reg, data):
        self._bus.write_i2c_block_data(self._addr, reg, list(bytearray(data)))

    def probe(self):
        try:
            # Read LTH (RO temperature register): harmless, no side effects.
            self._bus.read_byte_data(self._addr, 0x58)
            return True
        except OSError:
            return False

    def scan(self):
        """Probe candidate 7-bit addresses; return sorted list of responders.

        smbus has no native bus scan, so each candidate in 0x03..0x77 is
        probed with a read of the RO LTH register (0x58); non-responders
        NACK (OSError) and are skipped. Diagnostic-only (~114 transactions).
        """
        found = []
        for a in range(_SCAN_MIN, _SCAN_MAX + 1):
            try:
                self._bus.read_byte_data(a, 0x58)
                found.append(a)
            except OSError:
                pass
        return found

    def delay_ms(self, ms):
        time.sleep(ms / 1000.0)

    def close(self):
        if self._owns_bus:
            self._bus.close()
