"""I2C bus recovery for the RPi bench (run as ROOT, i2c driver UNLOADED).

Sequence (Philips spec):
  1. Read SDA statically (input) - is it held low?
  2. Generate up to 9 SCL pulses; after each, sample SDA.
  3. Once SDA reads HIGH, issue a STOP (SDA rises while SCL high).
  4. Report final state.
Shell wrapper: sudo modprobe -r i2c_bcm2835; sudo python3 rpi_bus_recovery.py;
              sudo modprobe i2c_bcm2835
"""
import os
import time

SDA, SCL = 2, 3


def export(n):
    with open("/sys/class/gpio/export", "w") as f:
        f.write(str(n))
    time.sleep(0.15)


def unexport(n):
    try:
        with open("/sys/class/gpio/unexport", "w") as f:
            f.write(str(n))
    except OSError:
        pass


def set_dir(n, d):
    with open("/sys/class/gpio/gpio%d/direction" % n, "w") as f:
        f.write(d)


def set_val(n, v):
    with open("/sys/class/gpio/gpio%d/value" % n, "w") as f:
        f.write(str(v))


def get_val(n):
    with open("/sys/class/gpio/gpio%d/value" % n) as f:
        return int(f.read().strip())


try:
    export(SCL)
    export(SDA)
    set_dir(SCL, "out")
    set_dir(SDA, "in")

    print("static SDA (input, no driver): %d" % get_val(SDA))

    released = False
    for i in range(9):
        set_val(SCL, 1)
        time.sleep(0.002)
        set_val(SCL, 0)
        time.sleep(0.002)
        sda = get_val(SDA)
        print("pulse %d -> SDA=%d" % (i + 1, sda))
        if sda == 1:
            released = True
            break

    if released:
        # STOP: SDA low -> high while SCL high
        set_dir(SDA, "out")
        set_val(SDA, 0)
        time.sleep(0.001)
        set_val(SCL, 1)
        time.sleep(0.001)
        set_val(SDA, 1)
        time.sleep(0.001)
        set_val(SCL, 0)
        print("STOP issued; SDA released cleanly")
    else:
        print("SDA STILL HELD LOW after 9 pulses - device likely latched;"
              " power-cycle the MAX31760 module")
finally:
    unexport(SCL)
    unexport(SDA)
