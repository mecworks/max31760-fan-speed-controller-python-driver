"""Confirm: SW_POR write 'fails' with errno 121 but the chip DID reset.

1. Set user-mem marker 0xA5 (volatile).
2. Issue SW_POR write; record errno + elapsed.
3. Poll SR reads every 10 ms until the chip answers again.
4. Read user_mem + CR1: if user_mem != 0xA5 (reloaded from EEPROM), the
   reset really happened despite the errno. Repeat 5x for boot-time spread.
Restores factory state at the end.
"""
import sys
import time

sys.path.insert(0, ".")
import smbus2

b = smbus2.SMBus(1)
CR1_FAC = 0x19


def wr(reg, v):
    b.write_i2c_block_data(0x50, reg, [v])


def rd(reg):
    return b.read_byte_data(0x50, reg)


for i in range(5):
    wr(0x10, 0xA5)                       # volatile marker
    t0 = time.monotonic()
    err = None
    try:
        wr(0x00, rd(0x00) | 0x40)        # SW_POR
    except OSError as e:
        err = e
    t_write = int((time.monotonic() - t0) * 1000)
    # poll for re-ack
    t1 = time.monotonic()
    alive = False
    while True:
        try:
            rd(0x5A)
            alive = True
            break
        except OSError:
            pass
        if time.monotonic() - t1 > 5.0:
            print("run %d: CHIP NEVER CAME BACK" % (i + 1))
            break
    if not alive:
        continue
    t_boot = int((time.monotonic() - t1) * 1000)
    um = rd(0x10)
    cr1 = rd(0x00)
    print("run %d: write_err=%s (%d ms) boot=%d ms | user_mem=%02X (marker was A5) cr1=%02X"
          % (i + 1, ("errno %d" % err.errno) if err else "None",
             t_write, t_boot, um, cr1))
    time.sleep(0.5)

# restore
time.sleep(0.3)
wr(0x00, CR1_FAC)
b.write_i2c_block_data(0x50, 0x5B, [0x01])
time.sleep(0.7)
print("final cr1=%02X" % rd(0x00))
print("DONE")
