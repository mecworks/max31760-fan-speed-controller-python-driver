"""RPi bench raw tach-counter peek: read TC1H/L (non-destructive) and
decode the implied speed of the LAST latched pulse period.

During a coast-down, the period latch keeps updating until the fan drops
below the overflow floor (~183 rpm at 2 PPR: 65535 ticks / 100 kHz clock /
2 revs per 4-pulse group); the frozen value then records the speed at the
crossing. Pure reads - no writes, no SR consumption.
Run:  python3 rpi_tc_raw.py
"""
import sys

sys.path.insert(0, ".")
from max31760.cp import MAX31760
from max31760._regs import REG_TC1H, TACH_REF_HZ

dev = MAX31760(bus=1, addr=0x50)
assert dev.verify(), "chip not responding"
raw = dev.read_reg(REG_TC1H, 2)
count = (raw[0] << 8) | raw[1]
if count == 0:
    print("TC1 raw = 0 (fresh/POR state)")
else:
    implied_rpm = 60.0 * TACH_REF_HZ / (count * 2.0)
    print("TC1 raw count = %d ticks" % count)
    print("implied speed of last latched period = %.1f rpm" % implied_rpm)
    print("(overflow floor ~= 183 rpm at 2 PPR; a value near 65535 means")
    print(" the fan coasted DOWN THROUGH the measurable range before freezing)")
print("rpm() reports: %.1f   pwmv=%d/255   local=%.1f C" %
      (dev.rpm(1), dev.actual_duty_raw, dev.local_temp_c))
