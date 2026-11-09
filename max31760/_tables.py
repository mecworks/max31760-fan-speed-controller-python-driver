"""Data tables for the MAX31760 driver (pure data, no logic).

Factory defaults verified against datasheet Table 13 and live bench reads
(2026-11-07). Ideality-factor table per datasheet Table 4.
"""

# Factory defaults (Table 13; live-verified on bench 2026-11-07).
FACTORY_DEFAULTS = {
    0x00: 0x01, 0x01: 0x10, 0x02: 0x03, 0x03: 0xFF,   # CR1..FFDC
    0x04: 0xC0, 0x05: 0x18,                           # MASK, IFR
    0x06: 0x55, 0x07: 0x00,     # RHS  +85.0 C
    0x08: 0x55, 0x09: 0x00,     # LOTS +85.0 C
    0x0A: 0x6E, 0x0B: 0x00,     # ROTS +110.0 C
    0x0C: 0x46, 0x0D: 0x00,     # LHS  +70.0 C
    0x0E: 0xFF, 0x0F: 0xFE,     # TCTH/TCTL 65534
}
LUT_FACTORY_VALUE = 0xFF
USER_FACTORY_VALUE = 0x00

# Ideality factor table (Table 4): index 0x00..0x3F; >= 0x40 invalid.
IDEALITY_TABLE = (
    0.9844, 0.9853, 0.9863, 0.9873, 0.9882, 0.9892, 0.9902, 0.9911,
    0.9921, 0.9931, 0.9941, 0.9950, 0.9960, 0.9970, 0.9980, 0.9990,
    1.0000, 1.0010, 1.0020, 1.0030, 1.0040, 1.0050, 1.0060, 1.0070,
    1.0080, 1.0090, 1.0100, 1.0110, 1.0120, 1.0130, 1.0141, 1.0151,
    1.0161, 1.0171, 1.0182, 1.0192, 1.0202, 1.0213, 1.0223, 1.0233,
    1.0244, 1.0254, 1.0265, 1.0275, 1.0286, 1.0296, 1.0307, 1.0317,
    1.0328, 1.0338, 1.0349, 1.0360, 1.0370, 1.0381, 1.0392, 1.0402,
    1.0413, 1.0424, 1.0435, 1.0445, 1.0456, 1.0467, 1.0478, 1.0489,
)
