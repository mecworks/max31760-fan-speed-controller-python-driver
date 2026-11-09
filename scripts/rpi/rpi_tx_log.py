"""Log every I2C transaction of the driver's EEPROM section to find exactly
which transaction NACKs and when, relative to the EEX operations."""
import sys
import time

sys.path.insert(0, ".")
import smbus2
from max31760.cp import MAX31760


class LoggedBus(object):
    def __init__(self, bus):
        self._b = bus
        self.t0 = time.monotonic()

    def ts(self):
        return "%7.3f" % (time.monotonic() - self.t0)

    def read_byte_data(self, addr, reg):
        try:
            v = self._b.read_byte_data(addr, reg)
            print("%s RBYTE  reg=%02X -> %02X" % (self.ts(), reg, v))
            return v
        except OSError:
            print("%s RBYTE  reg=%02X -> NACK" % (self.ts(), reg))
            raise

    def read_i2c_block_data(self, addr, reg, qty):
        try:
            d = self._b.read_i2c_block_data(addr, reg, qty)
            print("%s RBLOCK reg=%02X n=%d -> %s" %
                  (self.ts(), reg, qty, bytes(bytearray(d)).hex()))
            return d
        except OSError:
            print("%s RBLOCK reg=%02X n=%d -> NACK" % (self.ts(), reg, qty))
            raise

    def write_i2c_block_data(self, addr, reg, data):
        hx = bytes(bytearray(data)).hex()
        try:
            self._b.write_i2c_block_data(addr, reg, data)
            print("%s WBLOCK reg=%02X -> %s" % (self.ts(), reg, hx))
        except OSError:
            print("%s WBLOCK reg=%02X -> NACK (%s)" % (self.ts(), reg, hx))
            raise

    def close(self):
        self._b.close()


lb = LoggedBus(smbus2.SMBus(1))
dev = MAX31760(bus=1, addr=0x50, handle=lb)
assert dev.verify()

cr1_0 = dev.read_reg(0x00, 1)[0]
sentinel = cr1_0 ^ 0x04
print("== cr1_0=%02X sentinel=%02X ==" % (cr1_0, sentinel))
dev.write_reg(0x00, bytes([sentinel]))
dev.save_config(MAX31760.EEX_BLOCK_00_0F)
dev.write_reg(0x00, bytes([cr1_0]))
dev.load_config(MAX31760.EEX_BLOCK_00_0F)
got = dev.read_reg(0x00, 1)[0]
print("== got=%02X expect=%02X ==" % (got, sentinel))
try:
    dev.soft_por()
    print("== soft_por OK ==")
except OSError as e:
    print("== soft_por FAILED: %s ==" % e)
# cleanup: restore original CR1 to RAM+EEPROM
dev.write_reg(0x00, bytes([cr1_0]))
dev.save_config(MAX31760.EEX_BLOCK_00_0F)
print("cleanup done, CR1=%02X" % dev.read_reg(0x00, 1)[0])
