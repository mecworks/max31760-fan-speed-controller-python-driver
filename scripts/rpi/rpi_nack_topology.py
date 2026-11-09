"""Map the write-NACK topology around the full EEPROM save/load sequence.

Phases (raw smbus2, 1 ms hammer cadence, no-op CR1 writes + SR reads):
  0: baseline 1 s, no EEX ops            -> expect zero NACKs
  1: CR1=sentinel, SAVE EEX, hammer 1 s  -> save busy window shape
  2: CR1=factory,   LOAD EEX, hammer 1 s -> commit stall shape/duration
Reports NACK runs (start-end ms) per phase plus read-alive stats.
Restores factory CR1 to RAM+EEPROM at the end.
"""
import sys
import time

sys.path.insert(0, ".")
import smbus2

b = smbus2.SMBus(1)
CR1_FAC = 0x19


def wr(v):
    try:
        b.write_i2c_block_data(0x50, 0x00, [v])
        return True
    except OSError:
        return False


def rd():
    try:
        b.read_byte_data(0x50, 0x58)
        return True
    except OSError:
        return False


def hammer(label, dur_s, val):
    t0 = time.monotonic()
    runs = []
    in_run = False
    start = 0
    n_wr_fail = 0
    n_rd_fail = 0
    while time.monotonic() - t0 < dur_s:
        t = int((time.monotonic() - t0) * 1000)
        okw = wr(val)
        okr = rd()
        if not okw:
            n_wr_fail += 1
            if not in_run:
                in_run = True
                start = t
        elif in_run:
            in_run = False
            runs.append((start, t - 1))
        if not okr:
            n_rd_fail += 1
    if in_run:
        runs.append((start, int(dur_s * 1000)))
    print("[%s] write NACK runs (ms): %s | wr_fail=%d rd_fail=%d"
          % (label, runs if runs else "NONE", n_wr_fail, n_rd_fail))
    return runs


print("baseline CR1:", hex(b.read_byte_data(0x50, 0x00)))
hammer("phase0 baseline ", 1.0, CR1_FAC)

# phase 1: save
b.write_i2c_block_data(0x50, 0x00, [CR1_FAC ^ 0x04])
b.write_i2c_block_data(0x50, 0x5B, [0x01])
hammer("phase1 SAVE     ", 1.0, CR1_FAC ^ 0x04)

# phase 2: load (commits sentinel into RAM -> changing load)
# hammer the POST-commit value so hammer writes are no-ops once committed
b.write_i2c_block_data(0x50, 0x00, [CR1_FAC])
b.write_i2c_block_data(0x50, 0x5B, [0x81])
hammer("phase2 LOAD     ", 1.0, CR1_FAC ^ 0x04)

# cleanup: ensure factory state in RAM+EEPROM
time.sleep(0.5)
wr(CR1_FAC)
b.write_i2c_block_data(0x50, 0x5B, [0x01])
time.sleep(0.7)
print("final CR1:", hex(b.read_byte_data(0x50, 0x00)))
print("DONE")
