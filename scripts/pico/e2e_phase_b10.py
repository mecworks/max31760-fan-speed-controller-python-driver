"""Phase B10 hardware E2E: EEPROM lifecycle (F20) + soft POR/standby/user mem (F21).

Runs ON the Pico (MicroPython). Exercises REAL nonvolatile storage:
  - user memory round-trip (public API)
  - save_config(): RAM -> EEPROM with ack-poll (measures the tW window)
  - soft POR: proves the saved values survive a full device reset
  - load_config(): EEPROM -> RAM overwrite (observable via CR1)
  - full restore of the pre-test configuration + final POR verification
  - standby enter/exit with I2C staying responsive
Prints PHASE-B10 DEVICE E2E: PASS on success.
NOTE: performs two full EEPROM program cycles (~1 s each). If this script
ever dies between mutation and restore, use e2e_restore.py.
"""
import time
import machine
from max31760.mp import MAX31760

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify(), "verify() failed"

BLOCKS = (0x00, 0x10, 0x20, 0x30, 0x40)

# --- snapshot the current RAM configuration ------------------------------------
snap = {}
for base in BLOCKS:
    snap[base] = bytes(dev.read_reg(base, 16))
cr1_0 = snap[0x00][0]
print("snapshot taken (CR1=%02X)" % cr1_0)
assert not dev.eeprom_corrupt(), "PC set before test"

# --- user memory round-trip ------------------------------------------------------
dev.user_memory_write_all(b"\xA5\x5A\x11\x22\x33\x44\x55\x66")
u1 = dev.user_memory_read_all()
assert u1 == b"\xA5\x5A\x11\x22\x33\x44\x55\x66", "bulk user mem mismatch"
dev.user_memory_set(7, 0x77)
assert dev.user_memory_get(7) == 0x77
print("user memory: OK")

# --- save_config: RAM -> EEPROM, ack-polled ---------------------------------------
dev.set_pwm_freq_hz(150)                     # mutate CR1.DRV
dev.write_reg(0x20, bytes([0x80]))           # mutate LUT[0]
t0 = time.ticks_ms()
dev.save_config()                            # all blocks
dt = time.ticks_diff(time.ticks_ms(), t0)
print("save_config: %d ms (tW window ack-polled)" % dt)
assert dt >= 100, "ack-poll returned suspiciously fast (%d ms)" % dt

# --- soft POR: saved values must survive a full reset ----------------------------
dev.soft_por()
time.sleep_ms(100)
cr1_p = dev.read_reg(0x00, 1)[0]
lut0_p = dev.read_reg(0x20, 1)[0]
u_p = dev.user_memory_get(0)
print("post-POR: CR1=%02X (pre-save %02X), LUT[0]=%02X, user[0]=%02X"
      % (cr1_p, cr1_0, lut0_p, u_p))
assert cr1_p & 0x18 == 0x08, "PWM freq did not persist through POR"
assert lut0_p == 0x80, "LUT[0] did not persist through POR"
assert u_p == 0xA5, "user memory did not persist through POR"
assert not dev.eeprom_corrupt(), "PC set after save+POR"
print("eeprom save + POR persistence: OK")

# --- restore original RAM, save, then prove load_config overwrites RAM -----------
for base in BLOCKS:
    dev.write_reg(base, snap[base])          # page-aligned 16-byte chunks
dev.save_config()
dev.set_pwm_freq_hz(25000)                   # RAM diverges from EEPROM again
assert dev.read_reg(0x00, 1)[0] & 0x18 == 0x18
dev.load_config(MAX31760.EEX_BLOCK_00_0F)    # pull control block back from EEPROM
cr1_l = dev.read_reg(0x00, 1)[0]
print("load_config: CR1=%02X (back to snapshot %02X)" % (cr1_l, cr1_0))
assert cr1_l == cr1_0, "load_config did not restore CR1 from EEPROM"
print("load_config overwrite: OK")

# --- standby enter/exit ------------------------------------------------------------
assert not dev.standby_active()
dev.enter_standby()
assert dev.standby_active()
cr2_s = dev.read_reg(0x01, 1)[0]             # I2C must stay responsive
assert cr2_s & 0x80, "STBY bit not visible while in standby"
dev.exit_standby()
assert not dev.standby_active()
print("standby: OK (I2C responsive while in standby)")

# --- final POR: verify the whole configuration matches the pre-test snapshot ------
dev.soft_por()
time.sleep_ms(100)
ok = True
for base in BLOCKS:
    cur = bytes(dev.read_reg(base, 16))
    if cur != snap[base]:
        ok = False
        print("MISMATCH at block %02X: %s vs %s" %
              (base, cur.hex(), snap[base].hex()))
assert ok, "configuration not restored to pre-test snapshot"
assert not dev.eeprom_corrupt(), "PC set at end"
print("final POR: configuration matches pre-test snapshot")

print("PHASE-B10 DEVICE E2E: PASS")
