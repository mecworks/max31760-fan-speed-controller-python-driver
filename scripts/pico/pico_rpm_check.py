"""Focused fan-speed measurement on the Pico bench.

TC1 semantics (datasheet p.~38, reg 52h/53h): the TACH1 count register holds
the INTERNAL CLOCK TICKS BETWEEN PULSES at 100 kHz - a period timer, NOT an
accumulating pulse counter. Datasheet formula:
    Fan_RPM = 60 x 100,000 / (TC1H*256 + TC1L) / n   (n = pulses/rev)
This script prints the RAW register values plus the datasheet-formula RPM
computed here (independent of the driver code path) alongside dev.rpm().
Sanity anchors: 2300 rpm @ppr=2 -> ~2174 ticks; 717 rpm @ppr=2 -> ~6974 ticks.
Restores all control registers + EEPROM when done.
"""
import time
import machine
from max31760.mp import MAX31760
from max31760._core import REG_TC1H, REG_TC1L

PPR = 2          # bench fan: 2 pulses per revolution
REF_HZ = 100000  # internal tach counter clock (datasheet)

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
d = MAX31760(i2c)
assert d.verify()

cr1_0 = d.read_reg(0x00, 1)[0]
cr2_0 = d.read_reg(0x01, 1)[0]
cr3_0 = d.read_reg(0x02, 1)[0]
print("baseline SR=%02X (clear-on-read)" % d.status_raw())


def tc1_count():
    return (d.read_reg(REG_TC1H, 1)[0] << 8) | d.read_reg(REG_TC1L, 1)[0]


def ds_rpm(count):
    # datasheet formula, computed locally (not via the driver)
    return 60.0 * REF_HZ / float(count) / float(PPR) if count else 0.0


d.manual_enable(True)
d.set_ramp_rate(MAX31760.RAMP_IMMEDIATE)

for pct in (25.0, 50.0, 75.0, 100.0):
    d.set_duty_pct(pct)
    assert d.wait_for_duty(pct, timeout_ms=1500), "duty stuck at %.0f" % pct
    settle = 5000 if pct == 100.0 else 2500      # extra settle at top end
    time.sleep_ms(settle)
    pwmv = d.get_actual_duty_raw()
    samples = []
    for _ in range(5):                            # 5 period samples
        samples.append(tc1_count())
        time.sleep_ms(300)
    med = sorted(samples)[len(samples) // 2]
    print("duty %3.0f%%  pwmv=%3d  raw_ticks=%s" % (pct, pwmv, str(samples)))
    print("         median=%5d  datasheet_rpm=%8.1f  drv_rpm=%8.1f"
          % (med, ds_rpm(med), d.rpm(1)))

print("local temp %.1f C" % d.local_temp_c)
print("final SR=%02X" % d.status_raw())

# --- restore (same discipline as hw_smoke_test.py) ---------------------------
d.write_reg(0x00, bytes([cr1_0]))
d.write_reg(0x01, bytes([cr2_0]))
d.write_reg(0x02, bytes([cr3_0]))
d.clear_fan_fail()
assert d.read_reg(0x00, 1)[0] == cr1_0
assert d.read_reg(0x01, 1)[0] == cr2_0
assert d.read_reg(0x02, 1)[0] == cr3_0
d.save_config(MAX31760.EEX_BLOCK_00_0F)      # leave EEPROM pre-test-state
print("restored OK")
