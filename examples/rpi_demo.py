"""Raspberry Pi demo: MAX31760 fan controller (CPython, full Python).

Works on any RPi model with I2C enabled (raspi-config -> Interface Options ->
I2C). Verify the chip first:  sudo i2cdetect -y 1   (expect 50)
Requires: pip install smbus2   (or: sudo apt install python3-smbus)
"""
from max31760.cp import MAX31760

BUS = 1          # /dev/i2c-1 (GPIO pins 3/5); use 0 for the alt header pins
ADDR = 0x50

dev = MAX31760(bus=BUS, addr=ADDR)

if not dev.verify():
    raise SystemExit("MAX31760 not responding at 0x%02X" % ADDR)

print("=== max31760 raspberry pi demo ===")
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

dev.set_duty_pct(50.0)
dev.wait_for_duty(50.0)
dev.close()
print("demo complete")
