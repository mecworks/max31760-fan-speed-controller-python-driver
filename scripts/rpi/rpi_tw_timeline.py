"""Measure the real busy-window shape after an EEX operation.

Raw smbus2, 1 ms resolution. For each of LOAD and SAVE: trigger the EEX op,
then log (probe_ack, write_accepted) every millisecond for 1.5 s. Prints a
run-length summary so the NACK/ACK structure is visible at a glance.
Restores CR1=0x19 to RAM+EEPROM at the end.
"""
import sys
import time

sys.path.insert(0, ".")
import smbus2

b = smbus2.SMBus(1)


def probe():
    try:
        b.read_byte_data(0x50, 0x58)
        return True
    except OSError:
        return False


def wr():
    try:
        b.write_i2c_block_data(0x50, 0x00, [0x19])  # CR1 no-op (already 0x19)
        return True
    except OSError:
        return False


def summarize(log, label):
    print("--- %s timeline (ms: P=probe W=write, runs) ---" % label)
    if not log:
        return
    prev = log[0]
    start = log[0][0]
    for t, p, w in log[1:] + [(10**9, None, None)]:
        cur = (p, w)
        if cur != prev:
            print("%4d-%4d ms  probe=%s write=%s" %
                  (start, t - 1, prev[0], prev[1]))
            prev = cur
            start = t


def measure(eex_val, label):
    b.write_i2c_block_data(0x50, 0x5B, [eex_val])
    t0 = time.monotonic()
    log = []
    while time.monotonic() - t0 < 1.5:
        t = int((time.monotonic() - t0) * 1000)
        log.append((t, probe(), wr()))
        time.sleep(0.001)
    summarize(log, label)


print("initial: probe=%s write=%s" % (probe(), wr()))
measure(0x81, "LOAD block 00-0F (EEX=0x81)")
time.sleep(1.0)
measure(0x01, "SAVE block 00-0F (EEX=0x01)")

# ensure clean factory state afterwards
time.sleep(1.0)
b.write_i2c_block_data(0x50, 0x00, [0x19])
b.write_i2c_block_data(0x50, 0x5B, [0x01])
time.sleep(0.7)
print("final CR1:", hex(b.read_byte_data(0x50, 0x00)))
print("DONE")
