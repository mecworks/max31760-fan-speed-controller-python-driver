"""Does bus traffic during the post-LOAD window disturb the commit?

Variant X: LOAD EEX -> PURE SLEEP 300 ms (zero bus traffic) -> hammer 1 s
Variant Z: LOAD EEX -> write-back oracle every 10 ms for 300 ms -> hammer 1 s
Each variant starts from factory CR1 in RAM, sentinel in EEPROM, so the
load is a CHANGING load in both cases. Reports write-NACK runs per variant.
Restores factory state at the end.
"""
import sys
import time

sys.path.insert(0, ".")
import smbus2

b = smbus2.SMBus(1)
CR1_FAC = 0x19
SENT = CR1_FAC ^ 0x04


def wr(v):
    try:
        b.write_i2c_block_data(0x50, 0x00, [v])
        return True
    except OSError:
        return False


def rd_cr1():
    try:
        return b.read_byte_data(0x50, 0x00)
    except OSError:
        return None


def hammer(label, dur_s, val):
    t0 = time.monotonic()
    runs = []
    in_run = False
    start = 0
    n_fail = 0
    while time.monotonic() - t0 < dur_s:
        t = int((time.monotonic() - t0) * 1000)
        if wr(val):
            if in_run:
                in_run = False
                runs.append((start, t - 1))
        else:
            n_fail += 1
            if not in_run:
                in_run = True
                start = t
    if in_run:
        runs.append((start, int(dur_s * 1000)))
    print("[%s] hammer NACK runs (ms): %s | fails=%d"
          % (label, runs if runs else "NONE", n_fail))


def setup():
    """RAM=factory, EEPROM=sentinel => next load is changing."""
    time.sleep(0.3)
    b.write_i2c_block_data(0x50, 0x00, [CR1_FAC])
    b.write_i2c_block_data(0x50, 0x5B, [0x01])   # save factory->EEPROM
    time.sleep(0.7)
    b.write_i2c_block_data(0x50, 0x00, [SENT])   # RAM sentinel
    b.write_i2c_block_data(0x50, 0x5B, [0x01])   # save sentinel->EEPROM
    time.sleep(0.7)
    b.write_i2c_block_data(0x50, 0x00, [CR1_FAC])  # RAM back to factory
    assert rd_cr1() == CR1_FAC


# ---- Variant X: pure sleep ---------------------------------------------
setup()
print("== VARIANT X: pure sleep ==")
b.write_i2c_block_data(0x50, 0x5B, [0x81])   # LOAD (changing)
time.sleep(0.30)
hammer("X hammer ", 1.0, SENT)
print("X post CR1:", hex(rd_cr1()))

time.sleep(0.5)

# ---- Variant Z: oracle write-back during window -------------------------
setup()
print("== VARIANT Z: oracle write-backs ==")
b.write_i2c_block_data(0x50, 0x5B, [0x81])   # LOAD (changing)
t0 = time.monotonic()
while time.monotonic() - t0 < 0.30:
    v = rd_cr1()                             # read current
    if v is not None:
        wr(v)                                # write it back (oracle style)
    time.sleep(0.010)
hammer("Z hammer ", 1.0, SENT)
print("Z post CR1:", hex(rd_cr1()))

# cleanup: factory everywhere
time.sleep(0.3)
wr(CR1_FAC)
b.write_i2c_block_data(0x50, 0x5B, [0x01])
time.sleep(0.7)
print("final CR1:", hex(rd_cr1()))
print("DONE")
