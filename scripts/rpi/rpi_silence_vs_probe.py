"""Silence vs probe during the post-LOAD window, interleaved 5x each.

Sequence per iteration (raw smbus2):
  RAM=sentinel -> SAVE EEX -> [variant behavior for 700 ms] ->
  RAM=factory -> LOAD EEX -> [variant behavior for 700 ms] ->
  read CR1 -> SW_POR write (the historically failing op) -> restore.
Variant S: pure sleep. Variant P: probe (SR read) every 10 ms.
"""
import sys
import time

sys.path.insert(0, ".")
import smbus2

CR1_FAC = 0x19


def wr(b, v):
    b.write_i2c_block_data(0x50, 0x00, [v])


def rd_cr1(b):
    return b.read_byte_data(0x50, 0x00)


def wait_variant(b, mode):
    if mode == "S":
        time.sleep(0.700)
    else:  # P: probe every 10 ms
        t0 = time.monotonic()
        while time.monotonic() - t0 < 0.700:
            try:
                b.read_byte_data(0x50, 0x58)
            except OSError:
                pass
            time.sleep(0.010)


def one_run(mode):
    t0 = time.monotonic()
    b = smbus2.SMBus(1)
    try:
        assert b.read_byte_data(0x50, 0x58) is not None
        cr1_0 = rd_cr1(b)
        sentinel = cr1_0 ^ 0x04
        wr(b, sentinel)
        b.write_i2c_block_data(0x50, 0x5B, [0x01])     # SAVE
        wait_variant(b, mode)
        wr(b, cr1_0)
        b.write_i2c_block_data(0x50, 0x5B, [0x81])     # LOAD
        wait_variant(b, mode)
        got = rd_cr1(b)
        assert got == sentinel, "round trip mismatch %02X" % got
        v = rd_cr1(b)
        wr(b, (v | 0x40) & 0xFF)                       # SW_POR write
        wr(b, cr1_0)
        b.write_i2c_block_data(0x50, 0x5B, [0x01])     # SAVE restore
        wait_variant(b, mode)
        return True
    except Exception:
        return False
    finally:
        b.close()
        time.sleep(0.5)


for rnd in range(5):
    s = one_run("S")
    p = one_run("P")
    print("round %d: silence=%s probe=%s" %
          (rnd + 1, "PASS" if s else "FAIL", "PASS" if p else "FAIL"),
          flush=True)

print("DONE")
