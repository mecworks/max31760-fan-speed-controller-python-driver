# Dual-Platform Expansion Study: Adding a Pure-Python (SBC) Driver

Date: 2026-11-03 · Status: **DECIDED** — Option C adopted (proper package); folded into PLANS.md v2

## Question
Extend the goal to ship a **second driver** targeting **pure Python (CPython)** on small SBCs
(Raspberry Pi et al.), with **functionality and API identical** to the MicroPython driver, so the
same application code drives the Fan 2 Click whether it runs on a full-size RPi or an embedded
board (Pico / ESP32). User's initial instinct: two separate files, one per platform. Evaluate
whether that's the right approach.

## The decisive architectural fact

The MAX31760 driver decomposes cleanly into two layers:

| Layer | Share of code | Platform-dependent? |
|---|---|---|
| **Core / protocol** — register map, temp encode/decode, LUT math, RPM math, EEPROM sequencing, fault logic, RMW field setters, presets | ~90% | **No** — depends only on an abstract "reg_read / reg_write / burst_read" primitive |
| **Transport** — how bytes actually go over I²C | ~10% | **Yes** — this is the ONLY difference |

- MicroPython transport: `machine.I2C.mem_read(addr, reg, n)` / `mem_write(addr, reg, buf)` (+ `writeto`/`readfrom` fallback).
- CPython/Linux transport: `smbus2.SMBus(bus).read_byte_data / write_byte_data / read_i2c_block_data / write_i2c_block_data` (or legacy `smbus`, or `i2c-bus`).

**Consequence:** "identical functionality and API" is trivially satisfied *if and only if the core
logic lives in exactly one place.* The entire decision reduces to **packaging**, not to whether we
can meet the requirement.

## CPython transport notes (grounding)
- Preferred lib: **`smbus2`** — pure-Python, actively maintained, drop-in for `python-smbus`,
  wraps `/dev/i2c-*`. Install: `pip install smbus2` (or `apt install python3-smbus` for the C ext).
- Bus number: RPi default I²C bus = **1** (`/dev/i2c-1`); must be selectable (some hats/boards use 0).
- Quirks the adapter must absorb:
  - `read_i2c_block_data(addr, reg, n)` returns a list **with the register byte prepended** → strip `[0]`.
  - Block-write length limits exist; our ≤8-byte page-aligned writes fit comfortably.
  - Errors raise `OSError` (errno 5/6) — same family as MicroPython, so the core's retry/error model carries over unchanged.
- Enabling I²C on RPi: `raspi-config` → Interface Options → I2C → Enable; confirm with `i2cdetect -y -r 1` expecting `0x50`.

## Three candidate architectures

### Option A — Two fully independent files (user's current idea)
`max31760_mp.py` (self-contained) + `max31760_cp.py` (self-contained), each carrying its own
transport **and its own copy of all core logic**.

**Pros**
- Fully standalone per platform; zero cross-imports; "this file is for that board."
- No chance a CPython-only import leaks into the MP build (or vice-versa).
- Dead-simple deployment story.

**Cons**
- ~90% code duplication → every fix/feature applied **twice**.
- Drift is near-certain over time; "identical API" becomes a *manually-enforced promise*, not a structural guarantee. (The reference driver's copy-paste bugs are exactly the failure mode duplicated logic invites.)
- Doubled test surface; proving equivalence is extra work forever.
- Highest long-term maintenance cost.

**Fit for the stated goal: weakest.** Identity is promised, not guaranteed.

### Option B — One combined file with adaptive transport
Single `max31760.py`. Core written once. Transport selected by **duck-typing the object the caller
passes in** (lazy/guarded imports): pass a `machine.I2C` → MP path; pass an `smbus2`/`smbus` handle
→ CPython path.

**Pros**
- Single source of truth → identical logic guaranteed structurally.
- One file to maintain; smallest total footprint; copy-one-file-everywhere deployment.

**Cons**
- Both `machine` and `smbus` referenced in one module (mitigated by lazy/guarded imports).
- Runtime sniffing + conditional branches concentrated in the transport section.
- A broken CPython branch isn't caught until someone actually runs it on Linux (static checks can't fully cover it).
- Less explicit; some devs dislike auto-detection magic. Extending to a 3rd backend bloats the file.

**Fit: strong, pragmatic, minimal.** Best when "one file, works everywhere" is the top priority.

### Option C — Shared core module + thin per-platform adapters (RECOMMENDED)
```
max31760/
├── __init__.py          # convenience re-exports
├── _core.py             # ALL protocol logic; consumes a transport object (duck-typed)
├── _transport_mp.py     # MicroPython machine.I2C adapter  (~40 LOC)
└── _transport_cp.py     # CPython smbus2/smbus adapter      (~40 LOC)
```
(Flatter variant if a package feels heavy: `max31760_core.py` + `max31760_mp.py` + `max31760_cp.py`,
where the two platform files are tiny wrappers exposing the same `MAX31760` class.)

**Pros**
- DRY: logic in exactly one place → identical behavior **by construction**.
- Transports isolated & tiny → trivial to review, test, swap; add a 3rd backend without touching core.
- Best testability: a mock transport plugs into `_core`; the **same suite proves both platforms' logic**. Equivalence is structural.
- Idiomatic for CPython (modules/packages) and perfectly normal on MicroPython (multi-file/package deploy via `mpremote cp` is standard; RAM/import cost of a couple of small modules is negligible).
- Each platform still presents the user a single small entry point to import/copy.

**Cons**
- More than one file → slightly more to copy onto a MicroPython board (copy the package dir or 2–3 files). Minor.
- Must keep the core↔transport interface contract (a handful of methods) stable. Small discipline cost.
- Marginally more upfront structure.

**Fit: best engineering; most directly serves the "identical API" mandate.**

## Why the binary framing ("one file vs two files") misses the sweet spot
"One file" (B) and "two independent files" (A) are the two poles. The optimal point is **neither**:
**one shared brain + two thin skins** (C). It keeps the *deployment simplicity* people want from
"one file" while keeping the *identity guarantee* people want from a single source of truth — and
it isolates the only thing that legitimately differs (transport) into swappable ~40-line modules.

## Marginal cost of adding the SBC target (headline)
Because the core is shared, the genuinely new work is small:
- ~40–60 LOC CPython transport adapter (+ its quirks: block-read strip, bus-number select).
- Adapter unit tests (block-read quirk, bus selection, error mapping).
- CPython packaging bits: `requirements.txt` (smbus2), optional `pyproject.toml` for pip install.
- RPi example + docs (GPIO SDA/SCL pins, enabling I²C, `i2cdetect` verification).
- CI tweak: host suite now meaningfully exercises the CP adapter too.
Everything else (core logic, F1–F24, mock, most tests) is **reused unchanged**.

## Comparison matrix

| Criterion | A: 2 independent | B: 1 adaptive file | C: core + adapters |
|---|---|---|---|
| Identical API guaranteed | ✗ (drift risk) | ✓ | ✓✓ (structural) |
| Maintenance effort | High (×2) | Low | Low |
| Deployment simplicity (MP) | ★★★ | ★★★ | ★★ (copy pkg/dir) |
| Deployment simplicity (SBC) | ★★★ | ★★★ | ★★★ |
| Testability / proof of parity | Weak | Moderate | Strong |
| Add 3rd backend later | Painful | Messy | Trivial |
| Static-verifiability per path | Good | Poorer | Good |
| Upfront complexity | Low | Low | Moderate |
| Fits "identical functionality" mandate | Weakest | Strong | **Strongest** |

## Recommendation
Adopt **Option C** (shared core + thin adapters). It makes the "identical API/functionality"
requirement a structural property rather than a convention, minimizes long-term maintenance, and
costs only a small amount of new code. If the user prioritizes absolute minimum file count above
clean separation, **Option B** is the acceptable fallback (still guarantees identical logic).
Avoid **Option A** (full duplication) — it directly undermines the stated goal.

## If approved — exact deltas to PLANS.md
1. **§1 Goal**: add "…plus a pure-Python (CPython) driver for SBCs (Raspberry Pi), sharing the
   same core and exposing an identical API."
2. **§3 Scope (in)**: add CPython transport adapter (smbus2 primary, smbus fallback), CPython
   packaging (`requirements.txt`, optional `pyproject.toml`), RPi example + docs.
3. **§4 Requirements**: add rows —
   - F25: CPython transport adapter (smbus2/smbus) with block-read quirk handling + bus-number select.
   - F26: Cross-platform API-parity gate (same public method set/signatures on both entry points).
   - F27: CPython packaging/install path (pip-installable or drop-in module).
4. **§5 Architecture**: replace the single-transport sketch with the layered diagram
   (app → `MAX31760` façade → `_core` → pluggable transport {mp, cp}); define the transport
   interface contract (`reg_read(reg,n)`, `reg_write(reg,buf)`, `burst_read(reg,n)`, `scan()` opt.).
5. **§6 Tasks**: add Phase B task for the CP adapter; add Phase C tasks for CPython packaging,
   RPi example/docs, and a parity test that asserts both façades expose identical signatures.
6. **§7 Verification**: add "run host suite under CPython exercising the CP adapter" and a
   signature-parity check between the two entry points.
7. **§8 Risks**: add "smbus block-read prepend quirk" and "RPi I²C bus-not-enabled" mitigations.
8. **Layout (§7 of NOTES/03)**: update tree to the package layout.

## Resolved (2026-11-03, user-approved)
1. **Structure**: Option C, proper `max31760/` package. ✔
2. **Dependency**: require `smbus2`; include 5-line `import smbus` fallback in the adapter. ✔
3. **Distribution**: hybrid — drop-in modules + `requirements.txt` **and** minimal
   `pyproject.toml` (`pip install .` works today); wheel-build automation and registry
   publishing deferred until a real second consumer. ✔
4. **SBC scope**: any Linux system with an I²C bus. Primary docs: Raspberry Pi (all
   models, incl. Zero/Zero 2), BeagleBone, common RPi clones; generic references for
   other boards. Bus number is a parameter (default 1). ✔
5. Folded into PLANS.md v2 (new reqs F25–F27, §5.3 decisions log, tasks B12/C7–C10,
   verification items 5–6, added risks). ✔
