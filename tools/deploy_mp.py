"""Deploy the max31760 package to a MicroPython board over mpremote exec.

Workaround for mpremote 1.29.0, whose `cp`/`fs cp` file transfer fails with
"No such file or directory" / "Permission denied" while the `exec` channel
works fine. Transfers each file as base64 chunks written through exec, then
verifies with the device-side sha256sum.

Usage:
    python tools/deploy_mp.py --port COM16 [--dest /lib/max31760]

Deploys the shared modules plus mp.py (the MicroPython surface); cp.py and
_transport_cp.py are CPython-only and skipped.
"""
import argparse
import base64
import hashlib
import subprocess
import sys
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent.parent / "max31760"
FILES = [
    "__init__.py", "_core.py", "_faults.py", "_lut.py", "_regs.py",
    "_tables.py", "_transport_mp.py", "mp.py",
]
CHUNK_CHARS = 4000  # base64 chars per exec call (~3 KB payload)


def mpremote(port, args):
    cmd = [sys.executable, "-m", "mpremote", "connect", f"port:{port}"]
    cmd += args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def deploy_file(port, dest_dir, name):
    src = PKG_DIR / name
    data = src.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    dst = f"{dest_dir}/{name}"
    rc, _, err = mpremote(port, ["exec", f'open("{dst}", "w").close()'])
    if rc != 0:
        raise RuntimeError(f"cannot create {dst}: {err}")
    for off in range(0, len(b64), CHUNK_CHARS):
        chunk = b64[off:off + CHUNK_CHARS]
        mode = "w" if off == 0 else "a"
        code = (f'import binascii;'
                f'f=open("{dst}", "{mode}");'
                f'f.write(binascii.a2b_base64(b"{chunk}"));'
                f'f.close()')
        rc, _, err = mpremote(port, ["exec", code])
        if rc != 0:
            raise RuntimeError(f"chunk {off // CHUNK_CHARS} of {dst} failed: {err}")
    want = hashlib.sha256(data).hexdigest()
    rc, out, err = mpremote(port, ["fs", "sha256sum", dst])
    got = out.split()[-1] if out and out.split() else ""
    if rc != 0 or got != want:
        raise RuntimeError(f"sha mismatch for {dst}: want {want} got {got} ({err})")
    print(f"  {name}: {len(data)} bytes OK")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", required=True, help="serial port, e.g. COM16")
    ap.add_argument("--dest", default="/lib/max31760",
                    help="destination dir on the board (default /lib/max31760)")
    args = ap.parse_args()

    rc, _, err = mpremote(args.port, ["fs", "mkdir", args.dest])
    if rc != 0 and "exists" not in err.lower():
        raise RuntimeError(f"mkdir {args.dest} failed: {err}")
    print(f"deploying {len(FILES)} files to {args.dest} via {args.port}")
    for name in FILES:
        deploy_file(args.port, args.dest, name)
    print("DEPLOY OK")


if __name__ == "__main__":
    main()
