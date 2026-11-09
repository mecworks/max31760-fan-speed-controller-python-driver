"""LUT geometry and curve-building utilities for the MAX31760 driver.

Window layout (datasheet Table 7): window 0 covers temperatures below
18 C; each further window spans 2 C; window 47 saturates >= 110 C.
Kept separate from _core.py to hold the protocol core under the size
budget; depends only on _core fixed-point helpers.
"""

from ._core import LUT_LEN, pct_to_duty

# Window geometry (Table 7).
LUT_FIRST_BOUND_C = 18.0
LUT_WINDOW_STEP_C = 2.0


def lut_index_for_temp(celsius):
    """Map a temperature in C to its LUT window index (0..47)."""
    t = float(celsius)
    if t < LUT_FIRST_BOUND_C:
        return 0
    idx = int((t - (LUT_FIRST_BOUND_C - LUT_WINDOW_STEP_C)) // LUT_WINDOW_STEP_C)
    if idx > LUT_LEN - 1:
        return LUT_LEN - 1
    return idx


def build_lut_curve(points):
    """Build a 48-entry LUT (list of duty raws) from (temp_c, pct) breakpoints.

    Breakpoints must be sorted by strictly increasing temperature; the duty
    is linearly interpolated between consecutive points and clamped at both
    ends. Window i is evaluated at its midpoint (17 + 2*i C).
    Raises ValueError on unsorted/insufficient points or pct outside 0..100.
    """
    pts = [(float(t), float(p)) for t, p in points]
    if len(pts) < 2:
        raise ValueError("need at least 2 breakpoints")
    for t, p in pts:
        if p < 0.0 or p > 100.0:
            raise ValueError("percent %.3f out of range 0..100" % p)
    for i in range(1, len(pts)):
        if pts[i][0] <= pts[i - 1][0]:
            raise ValueError("breakpoints must increase in temperature")
    out = []
    for i in range(LUT_LEN):
        t = 17.0 + LUT_WINDOW_STEP_C * i
        if t <= pts[0][0]:
            p = pts[0][1]
        elif t >= pts[-1][0]:
            p = pts[-1][1]
        else:
            j = 0
            while pts[j + 1][0] < t:
                j += 1
            t0, p0 = pts[j]
            t1, p1 = pts[j + 1]
            p = p0 + (p1 - p0) * (t - t0) / (t1 - t0)
        out.append(pct_to_duty(p))
    return out
