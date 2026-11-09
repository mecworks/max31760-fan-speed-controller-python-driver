"""MicroPython transport adapter (machine.I2C).

Uses the canonical, universal I2C API: readfrom_mem / writeto_mem.
NOTE: mem_read/mem_write are NOT part of the standard MicroPython API
(absent on v1.19.1 RP2040; zero mentions in official docs) - do not use.
"""

import time


class TransportMP(object):
    """Adapts a caller-constructed machine.I2C object to the transport contract.

    Contract consumed by _core.MAX31760:
        burst_read(reg, n) -> bytes
        burst_write(reg, data) -> None      (1..8 bytes)
        probe() -> bool
        scan() -> tuple of 7-bit addresses
        delay_ms(ms) -> None
    """

    def __init__(self, i2c, addr=0x50):
        self._i2c = i2c
        self._addr = int(addr)

    def burst_read(self, reg, n):
        return self._i2c.readfrom_mem(self._addr, reg, n)

    def burst_write(self, reg, data):
        self._i2c.writeto_mem(self._addr, reg, bytearray(data))

    def probe(self):
        """Minimal single-transaction address probe.

        Reads the RO local-temperature MSB (0x58): harmless, no side
        effects. During the EEPROM write time (tW) the device NACKs its
        own address, which surfaces as OSError -> False, which is exactly
        the ack-poll semantics the driver relies on. (A full bus scan here
        would be far too slow for 10 ms polling.)
        """
        try:
            self._i2c.readfrom_mem(self._addr, 0x58, 1)
            return True
        except OSError:
            return False

    def scan(self):
        return self._i2c.scan()

    def delay_ms(self, ms):
        time.sleep_ms(ms)
