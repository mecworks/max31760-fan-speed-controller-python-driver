"""Decisive test: does bus traffic during the post-LOAD window prevent the
long write-NACK stalls seen with silence?

Four variants, each starting from RAM=factory / EEPROM=sentinel (changing
load), issuing LOAD EEX, then 1.5 s of the variant's behavior, then a 1 s
hammer of no-op writes. Reports NACK activity in both phases.
  A: pure silence
  B: probe (SR read) every 10 ms
  C: no-op write-back every 10 ms
  D: no-op write-back every 1 ms
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


def rd_sr():
    try:
        b.read_byte_data(0x50, 0x58)
        return True
    except OSError:
        return False


def setup():
    time.sleep(0.3)
    b.write_i2c_block_data(0x50, 0x00, [CR1_FAC])
    b.write_i2c_block_data(0x50, 0x5B, [0x01])
    time.sleep(0.7)
    b.write_i2c_block_data(0x50, 0x00, [SENT])
    b.write_i2c_block_data(0x50, 0x5B, [0x01])
    time.sleep(0.7)
    b.write_i2c_block_data(0x50, 0x00, [CR1_FAC])
    assert rd_cr1() == CR1_FAC


def run_variant(label, mode):
    setup()
    b.write_i2c_block_data(0x50, 0x5B, [0x81])   # LOAD (changing)
    t0 = time.monotonic()
    n_wr_fail = 0
    n_rd_fail = 0
    while time.monotonic() - t0 < 1.5:
        if mode == "A":
            time.sleep(0.05)
        elif mode == "B":
            if not rd_sr():
                n_rd_fail += 1
            time.sleep(0.010)
        elif mode == "C":
            v = rd_cr1()
            if v is None:
                n_rd_fail += 1
            elif not wr(v):
                n_wr_fail += 1
            time.sleep(0.010)
        elif mode == "D":
            v = rd_cr1()
            if v is None:
                n_rd_fail += 1
            elif not wr(v):
                n_wr_fail += 1
            time.sleep(0.001)
    # hammer phase
    th = time.monotonic()
    runs = []
    in_run = False
    start = 0
    h_fail = 0
    while time.monotonic() - th < 1.0:
        t = int((time.monotonic() - th) * 1000)
        if wr(SENT):
            if in_run:
                in_run = False
                runs.append((start, t - 1))
        else:
            h_fail += 1
            if not in_run:
                in_run = True
                start = t
    if in_run:
        runs.append((start, 1000))
    print("[%s] wait-phase fails wr=%d rd=%d | hammer runs=%s fails=%d"
          % (label, n_wr_fail, n_rd_fail, runs if runs else "NONE", h_fail))
    time.sleep(0.5)


run_variant("A silence      ", "A")
run_variant("B probe 10ms   ", "B")
run_variant("C writebk 10ms ", "C")
run_variant("D writebk 1ms  ", "D")

# cleanup
time.sleep(0.3)
wr(CR1_FAC)
b.write_i2c_block_data(0x50, 0x5B, [0x01])
time.sleep(0.7)
print("final CR1:", hex(rd_cr1()))
print("DONE")
