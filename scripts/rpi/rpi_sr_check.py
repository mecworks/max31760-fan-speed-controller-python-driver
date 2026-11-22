"""RPi bench status-register snapshot: read SR (clear-on-read) once and
decode every alarm bit. Consumes the latches (harmless here; the E2E suite
drains them routinely). Run:  python3 rpi_sr_check.py
"""
import sys

sys.path.insert(0, ".")
from max31760.cp import MAX31760
from max31760._regs import (REG_SR, SR_TACH1A, SR_TACH2A, SR_ROTA, SR_RHA,
                            SR_LOTA, SR_LHA, SR_RDFA, SR_PC)

dev = MAX31760(bus=1, addr=0x50)
assert dev.verify(), "chip not responding"
sr = dev.read_reg(REG_SR, 1)[0]
bits = (("TACH1A", SR_TACH1A), ("TACH2A", SR_TACH2A), ("ROTA", SR_ROTA),
        ("RHA", SR_RHA), ("LOTA", SR_LOTA), ("LHA", SR_LHA),
        ("RDFA", SR_RDFA), ("PC", SR_PC))
print("SR raw = 0x%02X" % sr)
for name, mask in bits:
    print("  %-8s %s" % (name, "SET" if sr & mask else "-"))
print("local=%.1f C  remote=%.1f C  pwmv=%d/255  rpm_reported=%.1f" %
      (dev.local_temp_c, dev.remote_temp_c, dev.actual_duty_raw,
       dev.rpm(1)))
