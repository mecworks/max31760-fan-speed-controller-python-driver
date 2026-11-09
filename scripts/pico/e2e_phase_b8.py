"""Phase B8 hardware E2E: 3-wire assists (PSEN/TACHFULL) + spin-up.

Runs ON the Pico (MicroPython). Exercises:
  - SPIN-UP OBSERVABLE EFFECT: with TACH2 enabled (dead port 2 => the
    "2 pulses at each enabled input" end-condition can never fire), a
    0->nonzero duty change under SPEN must hold the output at 100 % for
    the 2 s timeout, then revert to the selected manual duty
  - PSEN ONE-SHOT CONTRACT: measure_tach_once() returns a valid count,
    clears PSEN, and raises ValueError at non-33 Hz PWM (real HW)
  - TACHFULL FUNCTIONAL EFFECT: below 100 % duty it suspends TACH
    measurement (TC1 frozen); clearing it + accelerating the fan resumes
    updates
Prints PHASE-B8 DEVICE E2E: PASS on success.
"""
import time
import machine
from max31760.mp import MAX31760
from max31760._core import REG_TC1H, REG_TC1L, RAMP_IMMEDIATE

i2c = machine.I2C(0, scl=machine.Pin(1), sda=machine.Pin(0))
dev = MAX31760(i2c, addr=0x50)
assert dev.verify(), "verify() failed"

# Idempotent factory start
dev.write_reg(0x00, bytes([0x01]))
dev.write_reg(0x01, bytes([0x10]))
dev.write_reg(0x02, bytes([0x03]))
cr3_0 = dev.read_reg(0x02, 1)[0]
assert cr3_0 == 0x03, "not factory state"


def tc1():
    raw = dev.read_reg(REG_TC1H, 2)
    return (raw[0] << 8) | raw[1]


# --- spin-up observable effect --------------------------------------------------
# Kill any persistent fan-fail force first (D11): TACH2 off + CLRFAIL.
dev.tach2_enable(False)
dev.clear_fan_fail()
dev.set_ramp_rate(RAMP_IMMEDIATE)
dev.manual_enable(True)
dev.set_duty_pct(0.0)
deadline = 0
while dev.get_actual_duty_raw() != 0 and deadline < 40:
    time.sleep_ms(50)
    deadline += 1
assert dev.get_actual_duty_raw() == 0, "manual 0%% not reached"
print("baseline: manual 0%%, PWMV=0")

# Re-enable TACH2 so the spin-up end-condition (2 pulses at EACH enabled
# input) cannot fire on the dead port 2 => the 2 s timeout governs.
dev.tach2_enable(True)
dev.spin_up_enable(True)
dev.set_duty_pct(50.0)                     # 0 -> nonzero triggers spin-up

saw_full = False
settled_at = None
t0 = time.ticks_ms()
for i in range(120):                       # up to 6 s
    pwmv = dev.get_actual_duty_raw()
    if pwmv == 255:
        saw_full = True
    elif pwmv == 128:
        settled_at = time.ticks_diff(time.ticks_ms(), t0)
        break
    time.sleep_ms(50)
print("spin-up: saw 100%%=%s, settled at %s ms" % (saw_full, settled_at))
assert saw_full, "output never held at 100 %% during spin-up"
assert settled_at is not None, "output never reverted to 50 %%"
assert 1000 <= settled_at <= 3500, "spin-up duration out of band: %d ms" % settled_at
dev.spin_up_enable(False)
print("spin-up: OK (held 100%% ~%.1f s, then reverted to 50%%)" % (settled_at / 1000.0))

# --- PSEN one-shot contract + TACHFULL functional effect -------------------------
# Isolate from any persistent port-2 fan-fail force (manual duty must govern).
dev.tach2_enable(False)
dev.clear_fan_fail()
# NOTE (measured): at 5 % duty / 33 Hz TC1 still updates on this silicon
# (0x05B4 -> 0x0826 while coasting), so "low duty freezes TC" is NOT a valid
# precondition here. The stretched-pulse waveform itself is not visible via
# I2C either (PWMV holds the commanded duty during stretching, probed with
# e2e_probe_psen.py). Instead: PSEN gets a contract check (valid return,
# cleanup, precondition ValueError on real HW) and TACHFULL gets the
# DETERMINISTIC functional test: below 100 % duty it suspends TACH
# measurement entirely.
dev.set_duty_pct(50.0)
time.sleep_ms(1000)                      # let the fan settle at 50 %
cnt = dev.measure_tach_once(port=1, timeout_ms=3000)
rpm = dev.rpm(1)
print("measure_tach_once: %04X, rpm=%.1f" % (cnt, rpm))
assert not dev.pulse_stretch_enabled(), "PSEN left enabled"
assert cnt >= 0
if rpm > 0.0:
    assert 500.0 < rpm < 4000.0, "implausible RPM %.1f" % rpm
print("psen one-shot contract: OK")

# Precondition enforcement on real hardware
dev.set_pwm_freq_hz(150)
try:
    dev.measure_tach_once(port=1, timeout_ms=50)
    raise AssertionError("ValueError not raised at 150 Hz")
except ValueError:
    print("psen precondition (150 Hz rejected): OK")
dev.set_pwm_freq_hz(33)

dev.tacho_full_enable(True)
time.sleep_ms(1000)
t1 = tc1()
time.sleep_ms(1000)
t2 = tc1()
print("TC1 under TACHFULL @50%%: %04X -> %04X" % (t1, t2))
assert t1 == t2, "TACHFULL did not suspend TACH measurement below 100 %%"
dev.tacho_full_enable(False)
dev.set_duty_pct(100.0)                  # fan accelerates => TC1 must move
time.sleep_ms(1500)
t3 = tc1()
print("TC1 after TACHFULL off + accel: %04X (was %04X)" % (t3, t1))
assert t3 != t1, "TACH measurement did not resume after TACHFULL off"
assert not dev.tacho_full_enabled()
print("tachfull functional: OK")

# --- restore ------------------------------------------------------------------------
dev.manual_enable(False)
dev.write_reg(0x02, bytes([cr3_0]))        # factory CR3 (slow ramp, tach on)
assert dev.read_reg(0x02, 1)[0] == cr3_0
dev.clear_fan_fail()
print("restored factory CR3")

print("PHASE-B8 DEVICE E2E: PASS")
