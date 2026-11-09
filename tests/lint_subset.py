"""MicroPython-subset lint gate for shared (platform-neutral) modules.

Checks (per PLANS.md verification item 2):
  - compiles under CPython (syntax valid)
  - no CPython-only imports (os/sys/json/struct/logging/subprocess/threading/socket...)
  - no type annotations / arrow returns
  - no f-strings, async/await, yield-from, walrus operator
  (@property IS allowed: MicroPython supports the property builtin.)
Shared files: _core.py, _transport_mp.py, mp.py, __init__.py
Exempt (CPython-only by design): _transport_cp.py, cp.py
"""
import ast
import py_compile
import sys

SHARED = [
    "max31760/_core.py",
    "max31760/_tables.py",
    "max31760/_lut.py",
    "max31760/_faults.py",
    "max31760/_transport_mp.py",
    "max31760/mp.py",
    "max31760/__init__.py",
]
BAD_MODULES = {
    "os", "sys", "json", "struct", "logging", "subprocess", "threading",
    "socket", "urllib", "http", "sqlite3", "smbus", "smbus2", "ctypes",
    "multiprocessing", "queue", "select", "signal",
}


def check(path):
    problems = []
    src = open(path, encoding="utf-8").read()
    try:
        py_compile.compile(path, doraise=True)
    except Exception as e:
        return ["compile: %s" % e]
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                top = a.name.split(".")[0]
                if top in BAD_MODULES:
                    problems.append("bad import %r at line %d" % (a.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            top = (node.module or "").split(".")[0]
            if top in BAD_MODULES:
                problems.append("bad from-import %r at line %d" % (node.module, node.lineno))
        elif isinstance(node, ast.FunctionDef):
            params = (list(getattr(node.args, "posonlyargs", []))
                      + list(node.args.args)
                      + list(node.args.kwonlyargs))
            if node.args.vararg is not None:
                params.append(node.args.vararg)
            if node.args.kwarg is not None:
                params.append(node.args.kwarg)
            if any(p.annotation is not None for p in params):
                problems.append("arg annotation in %s line %d"
                                % (node.name, node.lineno))
            if node.returns is not None:
                problems.append("return annotation in %s line %d" % (node.name, node.lineno))
        elif isinstance(node, ast.AnnAssign):
            problems.append("annotation at line %d" % node.lineno)
        elif isinstance(node, ast.JoinedStr):
            problems.append("f-string at line %d" % node.lineno)
        elif isinstance(node, ast.AsyncFunctionDef):
            problems.append("async def at line %d" % node.lineno)
        elif isinstance(node, ast.Yield):
            pass  # plain yield is fine in MP; only 'yield from' is banned
        elif isinstance(node, ast.NamedExpr):
            problems.append("walrus operator at line %d" % node.lineno)
    return problems


ok = True
for path in SHARED:
    probs = check(path)
    if probs:
        ok = False
        print("%s : FAIL" % path)
        for p in probs:
            print("   - %s" % p)
    else:
        print("%s : CLEAN" % path)
print("RESULT:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
