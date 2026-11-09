"""Post-deploy sanity check for the Pico (run via mpremote)."""
import os
import machine
import max31760
import max31760.mp as m

print("version", max31760.__version__)
print("members", len([a for a in dir(m.MAX31760) if not a.startswith("_")]))
print("core size", os.stat("/lib/max31760/_core.py")[6])
i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
d = m.MAX31760(i2c)
print("verify", d.verify())
print("local temp C", round(d.local_temp_c, 2))
d.close()
print("OK")
