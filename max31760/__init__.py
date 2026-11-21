"""MAX31760 precision fan-speed controller driver.

Dual-platform package:
  - MicroPython boards (RPi Pico RP2040/RP2350, ESP32-class):  ``max31760.mp``
  - CPython / Linux SBC (Raspberry Pi, BeagleBone, clones):     ``max31760.cp``

Both entry points expose an identical public API: the device class plus the
full register-map / encoding / helper surface at module level (each entry
module's ``__all__`` lists exactly what it advertises). This package root
re-exports nothing beyond ``__version__`` - import the platform entry point
you need.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
