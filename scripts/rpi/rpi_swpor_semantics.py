"""Does the 'rejected' SW_POR write actually reset the chip?

Marker test: user memory 0x10 holds 0xA5 (volatile RAM). A real POR reloads
it from EEPROM (factory value). After each SW_POR write attempt, read back
user memory + CR1 + SR to determine whether the reset happened.

Part 1: SW_POR write with NO prior EEX activity (fresh state).
Part 2: full smoke sequence (save/load) then SW_POR write.
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


def swpor_attempt(label):
    t0 = time.monotonic()
    try:
        wr(0x00, rd(0x00) | 0x40)
        ok = True
    except OSError as e:
        ok = False
    dt = int((time.monotonic() - t0) * 1000)
    um = rd(0x10)
    cr1 = rd(0x00)
    sr = rd(0x5A)
    print("%s: write=%s (%d ms) | user_mem=%02X cr1=%02X sr=%02X"
          % (label, "OK" if ok else "NACK", dt, um, cr1, sr))
    return ok


print("== PART 1: SW_POR with no EEX history ==")
wr(0x10, 0xA5)                       # marker in user memory
swpor_attempt("P1a first ")
time.sleep(0.3)
wr(0x10, 0xA5)
swpor_attempt("P1b second")
# restore user memory to factory-ish (whatever EEPROM holds)
b.write_i2c_block_data(0x50, 0x5B, [0x81])     # load block 10-1F? no: block0
time.sleep(0.7)
# NOTE: EEX block select: bit1 = 10h..1F. Reload block 1 properly:
b.write_i2c_block_data(0x50, 0x5B, [0x82])
time.sleep(0.7)
um_now = rd(0x10)
print("P1 user mem after reload: %02X" % um_now)

print("")
print("== PART 2: SW_POR after save/load sequence ==")
cr1_0 = rd(0x00)
sentinel = cr1_0 ^ 0x04
wr(0x10, 0xA5)                       # marker again
wr(0x00, sentinel)
b.write_i2c_block_data(0x50, 0x5B, [0x01])     # SAVE block 0
time.sleep(0.7)
wr(0x00, cr1_0)
b.write_i2c_block_data(0x50, 0x5B, [0x81])     # LOAD block 0
time.sleep(0.7)
print("P2 pre-POR: cr1=%02X user_mem=%02X" % (rd(0x00), rd(0x10)))
swpor_attempt("P2a after seq")
time.sleep(0.3)
wr(0x10, 0xA5)
swpor_attempt("P2b retry   ")

# cleanup: factory CR1 everywhere, user mem from EEPROM
time.sleep(0.3)
wr(0x00, CR1_FAC)
b.write_i2c_block_data(0x50, 0x5B, [0x01])
time.sleep(0.7)
b.write_i2c_block_data(0x50, 0x5B, [0x82])     # reload user mem block
time.sleep(0.7)
print("final: cr1=%02X user_mem=%02X" % (rd(0x00), rd(0x10)))
print("DONE")
