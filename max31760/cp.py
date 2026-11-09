"""CPython / Linux SBC entry point.

Usage (Raspberry Pi, BeagleBone, any Linux box with I2C enabled):
    from max31760.cp import MAX31760
    dev = MAX31760(bus=1, addr=0x50)
Requires smbus2 (pip install smbus2) or the system python3-smbus package.
"""

from ._core import MAX31760 as _Core
from ._lut import build_lut_curve, lut_index_for_temp
from ._transport_cp import TransportCP

__all__ = ["MAX31760", "build_lut_curve", "lut_index_for_temp"]


class MAX31760(_Core):
    """MAX31760 driver bound to a Linux SMBus/I2C bus."""

    def __init__(self, bus=1, addr=0x50, handle=None):
        super(MAX31760, self).__init__(TransportCP(bus, addr, handle), addr)

    def close(self):
        """Release the underlying bus (only if this object opened it)."""
        self._t.close()
