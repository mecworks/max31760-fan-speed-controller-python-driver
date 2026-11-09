"""MicroPython entry point.

Usage (RPi Pico / ESP32):
    import machine
    from max31760.mp import MAX31760
    i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
    dev = MAX31760(i2c, addr=0x50)
"""

from ._core import MAX31760 as _Core
from ._lut import build_lut_curve, lut_index_for_temp
from ._transport_mp import TransportMP

__all__ = ["MAX31760", "build_lut_curve", "lut_index_for_temp"]


class MAX31760(_Core):
    """MAX31760 driver bound to a MicroPython machine.I2C instance."""

    def __init__(self, i2c, addr=0x50):
        super(MAX31760, self).__init__(TransportMP(i2c, addr), addr)

    def close(self):
        """No-op on MicroPython (the garbage collector owns the bus);
        provided so portable code can call close() on both platforms."""
        pass
