"""Sample local + remote temp channels every 30 s for 5 min.

Arbitrates the local-channel suspect: with the external PNP transistor
(remote channel) placed in direct thermal contact with the MAX31760
package, remote_temp_c tracks the TRUE package temperature independently
of the local sensor path. Read-only; no configuration changes.

Run on the Pi from the deployment dir:  python3 rpi_dual_temp_check.py
"""
import sys
import time

sys.path.insert(0, ".")
from max31760.cp import MAX31760

dev = MAX31760(bus=1, addr=0x50)
assert dev.verify(), "chip not responding"
print("%-6s %-10s %-10s" % ("t_s", "local_C", "remote_C"))
t0 = time.time()
for i in range(10):
    lt = dev.local_temp_c
    rt = dev.remote_temp_c
    print("%-6d %-10.1f %-10.1f" % (int(time.time() - t0), lt, rt))
    if i < 9:
        time.sleep(30)
print("done")
