"""ESP32-S3 demo: MAX31760 fan controller (MicroPython).

NOTE: ESP8266-class boards are OUT OF SCOPE for this driver (D16). This demo
targets ESP32-S3-class parts; adjust the I2C bus number and pins to your board
(e.g. DevKitC-1: SDA=GP8, SCL=GP9 on I2C0). Chip address is fixed at 0x50.
"""
import machine
from max31760.mp import MAX31760

# --- adapt these two lines to your board -------------------------------------
SDA_PIN = 8
SCL_PIN = 9
I2C_BUS = 0
# -----------------------------------------------------------------------------

i2c = machine.I2C(I2C_BUS, sda=machine.Pin(SDA_PIN), scl=machine.Pin(SCL_PIN))
dev = MAX31760(i2c, addr=0x50)

if not dev.verify():
    raise SystemExit("MAX31760 not responding at 0x50")

print("=== max31760 esp32-s3 demo ===")
print("local  temp: %.1f C" % dev.local_temp_c)
print("remote temp: %.1f C" % dev.remote_temp_c)

dev.configure_4wire_fan(port=1)
dev.manual_enable(True)
dev.set_ramp_rate(MAX31760.RAMP_IMMEDIATE)
dev.set_duty_pct(50.0)
dev.wait_for_duty(50.0)
print("duty 50%% -> actual %d/255, fan %.0f rpm" %
      (dev.get_actual_duty_raw(), dev.rpm(1)))
print("demo complete")
