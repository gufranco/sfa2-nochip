from collections import namedtuple

MAX_LENGTH = 0x10000
CONTEXT_COUNT = 32
PLANE_COUNT = 8
PREV_BITS_MASK = 0x3FF

EVOLUTION = (
    (0, 25, 25),
    (0, 2, 1),
    (0, 3, 1),
    (0, 4, 2),
    (0, 5, 3),
    (1, 6, 4),
    (1, 7, 5),
    (1, 8, 6),
    (1, 9, 7),
    (2, 10, 8),
    (2, 11, 9),
    (2, 12, 10),
    (2, 13, 11),
    (3, 14, 12),
    (3, 15, 13),
    (3, 16, 14),
    (3, 17, 15),
    (4, 18, 16),
    (4, 19, 17),
    (5, 20, 18),
    (5, 21, 19),
    (6, 22, 20),
    (6, 23, 21),
    (7, 24, 22),
    (7, 24, 23),
    (0, 26, 1),
    (1, 27, 2),
    (2, 28, 4),
    (3, 29, 8),
    (4, 30, 12),
    (5, 31, 16),
    (6, 32, 18),
    (7, 24, 22),
)

RUN_TABLE = (
    128,
    64,
    96,
    32,
    112,
    48,
    80,
    16,
    120,
    56,
    88,
    24,
    104,
    40,
    72,
    8,
    124,
    60,
    92,
    28,
    108,
    44,
    76,
    12,
    116,
    52,
    84,
    20,
    100,
    36,
    68,
    4,
    126,
    62,
    94,
    30,
    110,
    46,
    78,
    14,
    118,
    54,
    86,
    22,
    102,
    38,
    70,
    6,
    122,
    58,
    90,
    26,
    106,
    42,
    74,
    10,
    114,
    50,
    82,
    18,
    98,
    34,
    66,
    2,
    127,
    63,
    95,
    31,
    111,
    47,
    79,
    15,
    119,
    55,
    87,
    23,
    103,
    39,
    71,
    7,
    123,
    59,
    91,
    27,
    107,
    43,
    75,
    11,
    115,
    51,
    83,
    19,
    99,
    35,
    67,
    3,
    125,
    61,
    93,
    29,
    109,
    45,
    77,
    13,
    117,
    53,
    85,
    21,
    101,
    37,
    69,
    5,
    121,
    57,
    89,
    25,
    105,
    41,
    73,
    9,
    113,
    49,
    81,
    17,
    97,
    33,
    65,
    1,
)

CONTEXT_MASKS = (
    (0x01C0, 0x0001),
    (0x0180, 0x0001),
    (0x00C0, 0x0001),
    (0x0180, 0x0003),
)

Stream = namedtuple("Stream", "data end bitplanes context")


class TruncatedStream(Exception):
    pass


def bitplane_count(bitplane_type):
    if bitplane_type == 3:
        return 8
    return 2 if bitplane_type == 0 else 4


def decompress(rom, offset, length):
    if length == 0:
        length = MAX_LENGTH
    if offset < 0 or offset + 2 > len(rom):
        raise TruncatedStream(offset)

    header = rom[offset]
    bitplane_type = header >> 6
    context_type = (header >> 4) & 3
    high_mask, low_mask = CONTEXT_MASKS[context_type]

    stream = ((header << 11) | (rom[offset + 1] << 3)) & 0xFFFF
    valid = 5
    pos = offset + 2
    counters = [0] * PLANE_COUNT
    states = [0] * CONTEXT_COUNT
    mps = [0] * CONTEXT_COUNT
    prev = [0] * PLANE_COUNT
    out = bytearray()

    def get_bit(plane):
        nonlocal stream, valid, pos
        history = prev[plane]
        context = ((plane & 1) << 4) | ((history & high_mask) >> 5) | (history & low_mask)
        state = states[context]
        code_size, mps_next, lps_next = EVOLUTION[state]

        counter = counters[code_size]
        if counter == 0:
            if valid == 0:
                stream |= rom[pos]
                pos += 1
                valid = 8
            stream = ((stream << 1) & 0xFFFF) ^ 0x8000
            valid -= 1
            if stream & 0x8000:
                counter = (0x80 + (1 << code_size)) & 0xFF
            else:
                counter = RUN_TABLE[(stream >> 8) | (0x7F >> code_size)]
                stream = (stream << code_size) & 0xFFFF
                valid -= code_size
                if valid < 0:
                    stream |= rom[pos] << (-valid)
                    pos += 1
                    valid += 8

        counter = (counter - 1) & 0xFF
        if counter == 0x80:
            counters[code_size] = 0
            states[context] = mps_next
            bit = mps[context]
        elif counter == 0:
            counters[code_size] = 0
            states[context] = lps_next
            if state < 2:
                mps[context] ^= 1
                bit = mps[context]
            else:
                bit = mps[context] ^ 1
        else:
            counters[code_size] = counter
            bit = mps[context]

        prev[plane] = ((history << 1) | bit) & PREV_BITS_MASK
        return bit

    try:
        if bitplane_type == 3:
            while True:
                byte = 0
                for plane in range(PLANE_COUNT):
                    if get_bit(plane):
                        byte |= 1 << plane
                out.append(byte)
                length -= 1
                if length == 0:
                    break
        else:
            plane = 0
            step = 0
            while True:
                first = second = 0
                for shift in (7, 6, 5, 4, 3, 2, 1, 0):
                    if get_bit(plane):
                        first |= 1 << shift
                    if get_bit(plane + 1):
                        second |= 1 << shift
                out.append(first)
                length -= 1
                if length == 0:
                    break
                out.append(second)
                length -= 1
                if length == 0:
                    break
                step = (step + 32) & 0xFF
                if step == 0:
                    if bitplane_type == 1:
                        plane = (plane + 2) & 7
                    elif bitplane_type == 2:
                        plane ^= 2
    except IndexError:
        raise TruncatedStream(offset) from None

    return Stream(bytes(out), pos, bitplane_count(bitplane_type), context_type)
