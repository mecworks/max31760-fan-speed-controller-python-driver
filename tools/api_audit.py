"""Static audit of examples/ and scripts/ for pre-0.1.1 (v0.1.0) API usage.

Scans every .py file under examples/ and scripts/ with the AST and flags:
  - any attribute access to a PURE-OLD name (removed in 0.1.1 by the D-04
    accessor unification), and
  - CALLS on AMBIGUOUS names (methods in 0.1.0, properties in 0.1.1 -
    bare access is the correct new form, calling them raises TypeError).

Comments and docstrings cannot match (they are not AST nodes), so historical
prose mentions of old names are ignored by design. Stage 3 additionally
checks that every attribute accessed on a MAX31760(...) instance exists on
the current API (catches typos/stale names the D-04 list cannot know).
Exit code 0 = clean, 1 = findings. Part of the M9 pre-leg-2 audit step
(user directive 2026-11-21).
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET_DIRS = [ROOT / "examples", ROOT / "scripts"]

# Removed in 0.1.1; any attribute access to these is dead code.
PURE_OLD = {
    "get_local_high", "set_local_high",
    "get_remote_high", "set_remote_high",
    "get_local_overtemp", "set_local_overtemp",
    "get_remote_overtemp", "set_remote_overtemp",
    "lut_get", "lut_set",
    "manual_enable", "manual_enabled",
    "set_duty_raw", "get_duty_cmd_raw",
    "get_actual_duty_raw", "get_actual_duty_pct",
    "set_index_source", "get_index_source",
    "set_hysteresis_c", "get_hysteresis_c",
    "set_pwm_freq_hz", "get_pwm_freq_hz",
    "set_pwm_polarity", "get_pwm_polarity",
    "set_ramp_rate", "get_ramp_rate",
    "set_tach_threshold", "get_tach_threshold",
    "spin_up_enable", "pulse_stretch_enable", "tacho_full_enable",
    "enter_standby", "exit_standby", "standby_active",
    "set_alert_mode", "get_alert_mode",
    "set_ideality_factor_index", "get_ideality_factor_index",
    "get_ideality_factor",
    "set_ffdc_raw", "get_ffdc_raw",
    "set_ff_zero_detection",
    "set_ff_mode", "get_ff_mode",
    "set_rd_mode", "rd_mode_enabled",
    "set_rd_polarity", "get_rd_polarity",
    "set_alert_mask", "get_alert_mask",
}

# Methods in 0.1.0, PROPERTIES in 0.1.1: only a call is wrong.
AMBIGUOUS_NOW_PROPERTY = {
    "spin_up_enabled", "pulse_stretch_enabled",
    "tacho_full_enabled", "ff_zero_detection",
}


class Finder(ast.NodeVisitor):
    def __init__(self):
        self.findings = []
        self.string_mentions = []

    def visit_Attribute(self, node):
        if node.attr in PURE_OLD:
            self.findings.append((node.lineno, node.col_offset,
                                  f"{node.attr} (pure-old name)"))
        self.generic_visit(node)

    def visit_Call(self, node):
        if isinstance(node.func, ast.Attribute) \
                and node.func.attr in AMBIGUOUS_NOW_PROPERTY:
            self.findings.append((node.lineno, node.func.col_offset,
                                  f"{node.func.attr}() (now a property)"))
        self.generic_visit(node)

    def visit_Constant(self, node):
        # Stage 2: old names inside string literals (dynamic getattr/setattr
        # risk, or historical prose in docstrings). Informational only.
        if isinstance(node.value, str):
            for name in PURE_OLD:
                if name in node.value:
                    self.string_mentions.append(
                        (node.lineno, name, node.value.strip()))
                    break
        self.generic_visit(node)


def _call_name(v):
    """Name of a Call's func (bare name or trailing attribute), else None."""
    if not isinstance(v, ast.Call):
        return None
    f = v.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _dev_attr_names(tree):
    """Attribute names accessed on variables bound to MAX31760(...) calls."""
    devs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) \
                and _call_name(node.value) == "MAX31760":
            for t in node.targets:
                if isinstance(t, ast.Name):
                    devs.add(t.id)
    attrs = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value,
                                                          ast.Name) \
                and node.value.id in devs:
            attrs.add(node.attr)
    return attrs


def main():
    files = []
    for d in TARGET_DIRS:
        for p in sorted(d.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            files.append(p)
    total_findings = 0
    total_mentions = 0
    for p in files:
        tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        finder = Finder()
        finder.visit(tree)
        rel = p.relative_to(ROOT)
        if finder.findings:
            total_findings += len(finder.findings)
            print(f"{rel}: {len(finder.findings)} finding(s)")
            for lineno, col, what in sorted(finder.findings):
                line = p.read_text(encoding="utf-8").splitlines()[lineno - 1]
                print(f"  L{lineno}:{col + 1}  {what}")
                print(f"      | {line.strip()}")
        if finder.string_mentions:
            total_mentions += len(finder.string_mentions)
            print(f"{rel}: {len(finder.string_mentions)} string mention(s) "
                  f"(INFO - docstring/prose or dynamic reference, manual "
                  f"review)")
            for lineno, name, text in sorted(finder.string_mentions):
                shown = text if len(text) <= 90 else text[:87] + "..."
                print(f"  L{lineno}  '{name}' in: {shown}")
    print(f"\nscanned {len(files)} files under examples/ + scripts/")
    print(f"informational string mentions: {total_mentions}")
    # Stage 3: attribute-existence check against the current API.
    # Both facades expose an identical surface (parity gate), so the cp
    # facade (host-importable) stands in for both.
    missing_total = 0
    try:
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))
        import max31760.cp as _cp
        _cls = _cp.MAX31760
    except Exception as e:                     # noqa: broad - host tool
        print(f"stage 3 skipped (cannot import max31760.cp: {e})")
    else:
        for p in files:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
            attrs = _dev_attr_names(tree)
            missing = sorted(a for a in attrs
                             if not hasattr(_cls, a))
            if missing:
                missing_total += len(missing)
                rel = p.relative_to(ROOT)
                print(f"{rel}: MISSING ATTRIBUTES {missing}")
        if missing_total:
            print(f"RESULT: FAIL ({missing_total} unknown attributes)")
            return 1
        print("stage 3: all MAX31760 instance attributes exist on the "
              "current API")
    if total_findings:
        print(f"RESULT: FAIL ({total_findings} pre-0.1.1 API usages)")
        return 1
    print("RESULT: PASS (no live pre-0.1.1 API usage)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
