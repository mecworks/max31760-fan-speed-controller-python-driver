"""Pico demo: MAX31760 fan controller on an RPi Pico (MicroPython).

Bench wiring (Fan 2 Click / bare chip @ 0x50):
    I2C0: SDA = GP0 (pin 1), SCL = GP1 (pin 2)
    Fan on TACH1/port 1; remote diode on DXP/DXN.
Run directly on the board or via:  mpremote run examples/pico_demo.py
"""
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)

if not dev.verify():
    raise SystemExit("MAX31760 not responding at 0x50")

print("=== max31760 pico demo ===")
print("local  temp: %.1f C" % dev.local_temp_c)
print("remote temp: %.1f C" % dev.remote_temp_c)

# Recommended 4-wire topology preset, then manual control:
dev.configure_4wire_fan(port=1)
dev.manual_enable(True)
dev.set_ramp_rate(MAX31760.RAMP_IMMEDIATE)

for pct in (25.0, 50.0, 75.0, 100.0):
    dev.set_duty_pct(pct)
    dev.wait_for_duty(pct)
    print("duty %3.0f%% -> actual %3d/255, fan %.0f rpm" %
          (pct, dev.get_actual_duty_raw(), dev.rpm(1)))

# Persist the current configuration to EEPROM:
dev.save_config()
print("configuration saved to EEPROM")

# Back to a calm state:
dev.set_duty_pct(50.0)
dev.wait_for_duty(50.0)
print("demo complete")
