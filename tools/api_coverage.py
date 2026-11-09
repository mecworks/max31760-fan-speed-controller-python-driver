"""Coverage gate (C2): assert every public API member of the shared core is
exercised somewhere in the unit-test suite. Run: python tools/api_coverage.py
Exits non-zero listing any uncovered names."""
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from max31760._core import MAX31760  # noqa: E402


def public_names(cls):
    names = []
    for name in dir(cls):
        if name.startswith("_"):
            continue
        val = getattr(cls, name, None)
        if callable(val) or isinstance(val, (int, float)) \
                or isinstance(val, property):
            names.append(name)
    return sorted(names)


def main():
    test_src = open(os.path.join(ROOT, "tests", "test_max31760.py"),
                    encoding="utf-8").read()
    missing = []
    total = 0
    for name in public_names(MAX31760):
        total += 1
        pat = re.compile(r"\b" + re.escape(name) + r"\b")
        if not pat.search(test_src):
            missing.append(name)
    print("public members: %d" % total)
    if missing:
        print("NOT EXERCISED IN TEST SUITE:")
        for m in missing:
            print("  - %s" % m)
        return 1
    print("RESULT: PASS (all public members referenced by the suite)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
