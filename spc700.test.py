import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


spc700 = load_module("spc700")


IPL_ROM = bytes(
    [
        0xCD,
        0xEF,
        0xBD,
        0xE8,
        0x00,
        0xC6,
        0x1D,
        0xD0,
        0xFC,
        0x8F,
        0xAA,
        0xF4,
        0x8F,
        0xBB,
        0xF5,
        0x78,
        0xCC,
        0xF4,
        0xD0,
        0xFB,
        0x2F,
        0x19,
        0xEB,
        0xF4,
        0xD0,
        0xFC,
        0x7E,
        0xF4,
        0xD0,
        0x0B,
        0xE4,
        0xF5,
        0xCB,
        0xF4,
        0xD7,
        0x00,
        0xFC,
        0xD0,
        0xF3,
        0xAB,
        0x01,
        0x10,
        0xEF,
        0x7E,
        0xF4,
        0x10,
        0xEB,
        0xBA,
        0xF6,
        0xDA,
        0x00,
        0xBA,
        0xF4,
        0xC4,
        0xF4,
        0xDD,
        0x5D,
        0xD0,
        0xDB,
        0x1F,
        0x00,
        0x00,
        0xC0,
        0xFF,
    ]
)

IPL_EXPECTED = [
    (0xFFC0, "mov x,#$ef"),
    (0xFFC2, "mov sp,x"),
    (0xFFC3, "mov a,#$00"),
    (0xFFC5, "mov (x),a"),
    (0xFFC6, "dec x"),
    (0xFFC7, "bne $ffc5"),
    (0xFFC9, "mov $0f4,#$aa"),
    (0xFFCC, "mov $0f5,#$bb"),
    (0xFFCF, "cmp $0f4,#$cc"),
    (0xFFD2, "bne $ffcf"),
    (0xFFD4, "bra $ffef"),
    (0xFFD6, "mov y,$0f4"),
    (0xFFD8, "bne $ffd6"),
    (0xFFDA, "cmp y,$0f4"),
    (0xFFDC, "bne $ffe9"),
    (0xFFDE, "mov a,$0f5"),
    (0xFFE0, "mov $0f4,y"),
    (0xFFE2, "mov ($000)+y,a"),
    (0xFFE4, "inc y"),
    (0xFFE5, "bne $ffda"),
    (0xFFE7, "inc $001"),
    (0xFFE9, "bpl $ffda"),
    (0xFFEB, "cmp y,$0f4"),
    (0xFFED, "bpl $ffda"),
    (0xFFEF, "movw ya,$0f6"),
    (0xFFF1, "movw $000,ya"),
    (0xFFF3, "movw ya,$0f4"),
    (0xFFF5, "mov $0f4,a"),
    (0xFFF7, "mov a,y"),
    (0xFFF8, "mov x,a"),
    (0xFFF9, "bne $ffd6"),
    (0xFFFB, "jmp ($0000+x)"),
]


class TableTest(unittest.TestCase):
    def test_every_opcode_is_defined(self):
        self.assertEqual(len(spc700.OPCODES), 256)

    def test_no_opcode_is_longer_than_three_bytes(self):
        for opcode, (_, size) in enumerate(spc700.OPCODES):
            self.assertIn(size, (1, 2, 3), f"opcode {opcode:02X}")

    def test_implied_opcodes_are_one_byte(self):
        for opcode in (0x00, 0x1C, 0x1D, 0xBD, 0xC6, 0xDD, 0x5D, 0xFC):
            self.assertEqual(spc700.OPCODES[opcode][1], 1, f"opcode {opcode:02X}")

    def test_absolute_opcodes_are_three_bytes(self):
        for opcode in (0x05, 0x0C, 0x1E, 0x1F, 0x8F, 0x03):
            self.assertEqual(spc700.OPCODES[opcode][1], 3, f"opcode {opcode:02X}")


class DecodeTest(unittest.TestCase):
    def test_a_one_byte_opcode_decodes(self):
        instruction = spc700.decode(bytes([0x00]), 0, 0x0200)

        self.assertEqual(instruction.text, "nop")
        self.assertEqual(instruction.size, 1)
        self.assertEqual(instruction.address, 0x0200)

    def test_an_immediate_operand_renders(self):
        instruction = spc700.decode(bytes([0xE8, 0x7F]), 0, 0x0200)

        self.assertEqual(instruction.text, "mov a,#$7f")
        self.assertEqual(instruction.size, 2)

    def test_a_direct_page_operand_uses_the_page_flag(self):
        low = spc700.decode(bytes([0xE4, 0x10]), 0, 0x0200, p=0)
        high = spc700.decode(bytes([0xE4, 0x10]), 0, 0x0200, p=1)

        self.assertEqual(low.text, "mov a,$010")
        self.assertEqual(high.text, "mov a,$110")

    def test_a_relative_branch_targets_the_next_instruction_plus_offset(self):
        instruction = spc700.decode(bytes([0xD0, 0xFC]), 0, 0xFFC7)

        self.assertEqual(instruction.text, "bne $ffc5")

    def test_reading_past_the_end_of_the_data_is_rejected(self):
        with self.assertRaises(ValueError):
            spc700.decode(bytes([0xE8]), 0, 0x0200)


class IplRomTest(unittest.TestCase):
    def test_the_ipl_rom_disassembles_to_its_documented_listing(self):
        produced = [
            (instruction.address, instruction.text)
            for instruction in spc700.disassemble(
                IPL_ROM, 0, 0xFFC0, count=len(IPL_EXPECTED)
            )
        ]

        self.assertEqual(produced, IPL_EXPECTED)

    def test_the_listing_covers_every_byte_but_the_reset_vector(self):
        total = sum(
            instruction.size
            for instruction in spc700.disassemble(
                IPL_ROM, 0, 0xFFC0, count=len(IPL_EXPECTED)
            )
        )

        self.assertEqual(total, len(IPL_ROM) - 2)


class DisassembleTest(unittest.TestCase):
    def test_a_count_limits_the_listing(self):
        listing = list(spc700.disassemble(IPL_ROM, 0, 0xFFC0, count=3))

        self.assertEqual(len(listing), 3)

    def test_addresses_advance_by_each_instruction_size(self):
        listing = list(spc700.disassemble(IPL_ROM, 0, 0xFFC0, count=6))

        for previous, following in zip(listing, listing[1:]):
            self.assertEqual(following.address, previous.address + previous.size)

    def test_the_listing_stops_at_the_end_of_the_data(self):
        listing = list(spc700.disassemble(bytes([0x00, 0x00]), 0, 0x0200))

        self.assertEqual(len(listing), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
