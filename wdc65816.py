from collections import namedtuple

MODE_SIZE = {
    "absolute": 2,
    "absoluteLong": 3,
    "absoluteLongX": 3,
    "absolutePC": 2,
    "absoluteX": 2,
    "absoluteY": 2,
    "direct": 1,
    "directX": 1,
    "directY": 1,
    "immediate": 1,
    "immediateA": 2,
    "immediateX": 2,
    "implied": 0,
    "indexedIndirectX": 1,
    "indirect": 1,
    "indirectIndexedY": 1,
    "indirectLong": 1,
    "indirectLongPC": 2,
    "indirectLongY": 1,
    "indirectPC": 2,
    "indirectX": 2,
    "move": 2,
    "relative": 1,
    "relativeWord": 2,
    "stack": 1,
    "stackIndirect": 1,
}

OPCODES = (
    ("brk", "immediate"),
    ("ora", "indexedIndirectX"),
    ("cop", "immediate"),
    ("ora", "stack"),
    ("tsb", "direct"),
    ("ora", "direct"),
    ("asl", "direct"),
    ("ora", "indirectLong"),
    ("php", "implied"),
    ("ora", "immediateA"),
    ("asl", "implied"),
    ("phd", "implied"),
    ("tsb", "absolute"),
    ("ora", "absolute"),
    ("asl", "absolute"),
    ("ora", "absoluteLong"),
    ("bpl", "relative"),
    ("ora", "indirectIndexedY"),
    ("ora", "indirect"),
    ("ora", "stackIndirect"),
    ("trb", "direct"),
    ("ora", "directX"),
    ("asl", "directX"),
    ("ora", "indirectLongY"),
    ("clc", "implied"),
    ("ora", "absoluteY"),
    ("inc", "implied"),
    ("tas", "implied"),
    ("trb", "absolute"),
    ("ora", "absoluteX"),
    ("asl", "absoluteX"),
    ("ora", "absoluteLongX"),
    ("jsr", "absolutePC"),
    ("and", "indexedIndirectX"),
    ("jsl", "absoluteLong"),
    ("and", "stack"),
    ("bit", "direct"),
    ("and", "direct"),
    ("rol", "direct"),
    ("and", "indirectLong"),
    ("plp", "implied"),
    ("and", "immediateA"),
    ("rol", "implied"),
    ("pld", "implied"),
    ("bit", "absolute"),
    ("and", "absolute"),
    ("rol", "absolute"),
    ("and", "absoluteLong"),
    ("bmi", "relative"),
    ("and", "indirectIndexedY"),
    ("and", "indirect"),
    ("and", "stackIndirect"),
    ("bit", "directX"),
    ("and", "directX"),
    ("rol", "directX"),
    ("and", "indirectLongY"),
    ("sec", "implied"),
    ("and", "absoluteY"),
    ("dec", "implied"),
    ("tsa", "implied"),
    ("bit", "absoluteX"),
    ("and", "absoluteX"),
    ("rol", "absoluteX"),
    ("and", "absoluteLongX"),
    ("rti", "implied"),
    ("eor", "indexedIndirectX"),
    ("wdm", "immediate"),
    ("eor", "stack"),
    ("mvp", "move"),
    ("eor", "direct"),
    ("lsr", "direct"),
    ("eor", "indirectLong"),
    ("pha", "implied"),
    ("eor", "immediateA"),
    ("lsr", "implied"),
    ("phk", "implied"),
    ("jmp", "absolutePC"),
    ("eor", "absolute"),
    ("lsr", "absolute"),
    ("eor", "absoluteLong"),
    ("bvc", "relative"),
    ("eor", "indirectIndexedY"),
    ("eor", "indirect"),
    ("eor", "stackIndirect"),
    ("mvn", "move"),
    ("eor", "directX"),
    ("lsr", "directX"),
    ("eor", "indirectLongY"),
    ("cli", "implied"),
    ("eor", "absoluteY"),
    ("phy", "implied"),
    ("tad", "implied"),
    ("jml", "absoluteLong"),
    ("eor", "absoluteX"),
    ("lsr", "absoluteX"),
    ("eor", "absoluteLongX"),
    ("rts", "implied"),
    ("adc", "indexedIndirectX"),
    ("per", "absolute"),
    ("adc", "stack"),
    ("stz", "direct"),
    ("adc", "direct"),
    ("ror", "direct"),
    ("adc", "indirectLong"),
    ("pla", "implied"),
    ("adc", "immediateA"),
    ("ror", "implied"),
    ("rtl", "implied"),
    ("jmp", "indirectPC"),
    ("adc", "absolute"),
    ("ror", "absolute"),
    ("adc", "absoluteLong"),
    ("bvs", "relative"),
    ("adc", "indirectIndexedY"),
    ("adc", "indirect"),
    ("adc", "stackIndirect"),
    ("stz", "directX"),
    ("adc", "directX"),
    ("ror", "directX"),
    ("adc", "indirectLongY"),
    ("sei", "implied"),
    ("adc", "absoluteY"),
    ("ply", "implied"),
    ("tda", "implied"),
    ("jmp", "indirectX"),
    ("adc", "absoluteX"),
    ("ror", "absoluteX"),
    ("adc", "absoluteLongX"),
    ("bra", "relative"),
    ("sta", "indexedIndirectX"),
    ("brl", "relativeWord"),
    ("sta", "stack"),
    ("sty", "direct"),
    ("sta", "direct"),
    ("stx", "direct"),
    ("sta", "indirectLong"),
    ("dey", "implied"),
    ("bit", "immediateA"),
    ("txa", "implied"),
    ("phb", "implied"),
    ("sty", "absolute"),
    ("sta", "absolute"),
    ("stx", "absolute"),
    ("sta", "absoluteLong"),
    ("bcc", "relative"),
    ("sta", "indirectIndexedY"),
    ("sta", "indirect"),
    ("sta", "stackIndirect"),
    ("sty", "directX"),
    ("sta", "directX"),
    ("stx", "directY"),
    ("sta", "indirectLongY"),
    ("tya", "implied"),
    ("sta", "absoluteY"),
    ("txs", "implied"),
    ("txy", "implied"),
    ("stz", "absolute"),
    ("sta", "absoluteX"),
    ("stz", "absoluteX"),
    ("sta", "absoluteLongX"),
    ("ldy", "immediateX"),
    ("lda", "indexedIndirectX"),
    ("ldx", "immediateX"),
    ("lda", "stack"),
    ("ldy", "direct"),
    ("lda", "direct"),
    ("ldx", "direct"),
    ("lda", "indirectLong"),
    ("tay", "implied"),
    ("lda", "immediateA"),
    ("tax", "implied"),
    ("plb", "implied"),
    ("ldy", "absolute"),
    ("lda", "absolute"),
    ("ldx", "absolute"),
    ("lda", "absoluteLong"),
    ("bcs", "relative"),
    ("lda", "indirectIndexedY"),
    ("lda", "indirect"),
    ("lda", "stackIndirect"),
    ("ldy", "directX"),
    ("lda", "directX"),
    ("ldx", "directY"),
    ("lda", "indirectLongY"),
    ("clv", "implied"),
    ("lda", "absoluteY"),
    ("tsx", "implied"),
    ("tyx", "implied"),
    ("ldy", "absoluteX"),
    ("lda", "absoluteX"),
    ("ldx", "absoluteY"),
    ("lda", "absoluteLongX"),
    ("cpy", "immediateX"),
    ("cmp", "indexedIndirectX"),
    ("rep", "immediate"),
    ("cmp", "stack"),
    ("cpy", "direct"),
    ("cmp", "direct"),
    ("dec", "direct"),
    ("cmp", "indirectLong"),
    ("iny", "implied"),
    ("cmp", "immediateA"),
    ("dex", "implied"),
    ("wai", "implied"),
    ("cpy", "absolute"),
    ("cmp", "absolute"),
    ("dec", "absolute"),
    ("cmp", "absoluteLong"),
    ("bne", "relative"),
    ("cmp", "indirectIndexedY"),
    ("cmp", "indirect"),
    ("cmp", "stackIndirect"),
    ("pei", "indirect"),
    ("cmp", "directX"),
    ("dec", "directX"),
    ("cmp", "indirectLongY"),
    ("cld", "implied"),
    ("cmp", "absoluteY"),
    ("phx", "implied"),
    ("stp", "implied"),
    ("jmp", "indirectLongPC"),
    ("cmp", "absoluteX"),
    ("dec", "absoluteX"),
    ("cmp", "absoluteLongX"),
    ("cpx", "immediateX"),
    ("sbc", "indexedIndirectX"),
    ("sep", "immediate"),
    ("sbc", "stack"),
    ("cpx", "direct"),
    ("sbc", "direct"),
    ("inc", "direct"),
    ("sbc", "indirectLong"),
    ("inx", "implied"),
    ("sbc", "immediateA"),
    ("nop", "implied"),
    ("xba", "implied"),
    ("cpx", "absolute"),
    ("sbc", "absolute"),
    ("inc", "absolute"),
    ("sbc", "absoluteLong"),
    ("beq", "relative"),
    ("sbc", "indirectIndexedY"),
    ("sbc", "indirect"),
    ("sbc", "stackIndirect"),
    ("pea", "absolute"),
    ("sbc", "directX"),
    ("inc", "directX"),
    ("sbc", "indirectLongY"),
    ("sed", "implied"),
    ("sbc", "absoluteY"),
    ("plx", "implied"),
    ("xce", "implied"),
    ("jsr", "indirectX"),
    ("sbc", "absoluteX"),
    ("inc", "absoluteX"),
    ("sbc", "absoluteLongX"),
)

FLAG_DEPENDENT = {"immediateA": "m", "immediateX": "x"}

DIRECT_MODES = {
    "direct": "${:02x}",
    "directX": "${:02x},x",
    "directY": "${:02x},y",
    "indirect": "(${:02x})",
    "indexedIndirectX": "(${:02x},x)",
    "indirectIndexedY": "(${:02x}),y",
    "indirectLong": "[${:02x}]",
    "indirectLongY": "[${:02x}],y",
    "stack": "${:02x},s",
    "stackIndirect": "(${:02x},s),y",
    "immediate": "#${:02x}",
}

ABSOLUTE_MODES = {
    "absolute": "${:04x}",
    "absolutePC": "${:04x}",
    "absoluteX": "${:04x},x",
    "absoluteY": "${:04x},y",
    "indirectPC": "(${:04x})",
    "indirectX": "(${:04x},x)",
    "indirectLongPC": "[${:04x}]",
}

LONG_MODES = {
    "absoluteLong": "${:06x}",
    "absoluteLongX": "${:06x},x",
}

RELATIVE_MODES = {"relative", "relativeWord"}

Instruction = namedtuple("Instruction", "address offset opcode mnemonic mode operand size text")


class Truncated(Exception):
    pass


def operand_size(mode, m, x):
    flag = FLAG_DEPENDENT.get(mode)
    if flag is None:
        return MODE_SIZE[mode]
    return 1 if (m if flag == "m" else x) else 2


def branch_target(address, size, operand, width):
    delta = operand - (1 << (width * 8)) if operand >= 1 << (width * 8 - 1) else operand
    return (address & 0xFF0000) | ((address + size + delta) & 0xFFFF)


def render(mode, operand, address, size, width):
    if mode == "implied":
        return ""
    if mode in FLAG_DEPENDENT:
        return f"#${operand:02x}" if width == 1 else f"#${operand:04x}"
    if mode in DIRECT_MODES:
        return DIRECT_MODES[mode].format(operand)
    if mode in ABSOLUTE_MODES:
        return ABSOLUTE_MODES[mode].format(operand)
    if mode in LONG_MODES:
        return LONG_MODES[mode].format(operand)
    if mode in RELATIVE_MODES:
        return f"${branch_target(address, size, operand, width) & 0xFFFF:04x}"
    if mode == "move":
        return f"${operand & 0xFF:02x},${operand >> 8:02x}"
    raise KeyError(mode)


def decode(data, offset, address, m=True, x=True):
    if not 0 <= offset < len(data):
        raise Truncated(offset)
    opcode = data[offset]
    mnemonic, mode = OPCODES[opcode]
    width = operand_size(mode, m, x)
    if offset + 1 + width > len(data):
        raise Truncated(offset)

    operand = int.from_bytes(data[offset + 1 : offset + 1 + width], "little") if width else None
    size = 1 + width
    text = render(mode, operand, address, size, width)
    return Instruction(
        address,
        offset,
        opcode,
        mnemonic,
        mode,
        operand,
        size,
        f"{mnemonic} {text}".strip(),
    )


def apply_flags(instruction, m, x):
    if instruction.mnemonic == "sep":
        return (m or bool(instruction.operand & 0x20), x or bool(instruction.operand & 0x10))
    if instruction.mnemonic == "rep":
        return (
            m and not instruction.operand & 0x20,
            x and not instruction.operand & 0x10,
        )
    return m, x


def disassemble(data, offset, address, count=None, m=True, x=True, stop_at_return=False):
    listing = []
    while count is None or len(listing) < count:
        try:
            instruction = decode(data, offset, address, m, x)
        except Truncated:
            break
        listing.append(instruction)
        m, x = apply_flags(instruction, m, x)
        offset += instruction.size
        address = (address & 0xFF0000) | ((address + instruction.size) & 0xFFFF)
        if stop_at_return and instruction.mnemonic in ("rts", "rtl", "rti"):
            break
    return listing
