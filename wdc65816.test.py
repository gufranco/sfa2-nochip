import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cpu = load_module("wdc65816")


def decode(data, m=True, x=True):
    return cpu.decode(bytes(data), 0, 0x008000, m=m, x=x)


class TableTest(unittest.TestCase):
    def test_every_opcode_is_defined(self):
        self.assertEqual(len(cpu.OPCODES), 256)

    def test_every_opcode_names_a_known_addressing_mode(self):
        for mnemonic, mode in cpu.OPCODES:
            self.assertIn(mode, cpu.MODE_SIZE)
            self.assertTrue(mnemonic.isalpha())

    def test_the_flag_dependent_modes_are_the_two_immediates(self):
        self.assertEqual(set(cpu.FLAG_DEPENDENT), {"immediateA", "immediateX"})


class LengthTest(unittest.TestCase):
    def test_known_instruction_lengths(self):
        cases = [
            ([0xEA], 1, "nop"),
            ([0x60], 1, "rts"),
            ([0x6B], 1, "rtl"),
            ([0xE2, 0x20], 2, "sep #$20"),
            ([0xC2, 0x30], 2, "rep #$30"),
            ([0x8D, 0x01, 0x48], 3, "sta $4801"),
            ([0x8F, 0x1C, 0xF0, 0xC8], 4, "sta $c8f01c"),
            ([0xBF, 0x1C, 0xF0, 0xC8], 4, "lda $c8f01c,x"),
            ([0xBD, 0x03, 0x03], 3, "lda $0303,x"),
            ([0xA5, 0x12], 2, "lda $12"),
            ([0xA7, 0x12], 2, "lda [$12]"),
            ([0xB7, 0x12], 2, "lda [$12],y"),
            ([0x80, 0x10], 2, "bra $8012"),
            ([0x82, 0x00, 0x10], 3, "brl $9003"),
        ]

        for data, size, text in cases:
            instruction = decode(data)

            self.assertEqual(instruction.size, size, text)
            self.assertEqual(instruction.text, text)

    def test_an_immediate_follows_the_accumulator_width(self):
        wide = decode([0xA9, 0x01, 0x00], m=False)
        narrow = decode([0xA9, 0x01], m=True)

        self.assertEqual((wide.size, wide.text), (3, "lda #$0001"))
        self.assertEqual((narrow.size, narrow.text), (2, "lda #$01"))

    def test_an_index_immediate_follows_the_index_width(self):
        wide = decode([0xA2, 0x34, 0x12], x=False)
        narrow = decode([0xA2, 0x34], x=True)

        self.assertEqual((wide.size, wide.text), (3, "ldx #$1234"))
        self.assertEqual((narrow.size, narrow.text), (2, "ldx #$34"))

    def test_a_block_move_shows_its_operand_bytes_in_stored_order(self):
        instruction = decode([0x54, 0x7F, 0x7E])

        self.assertEqual(instruction.size, 3)
        self.assertEqual(instruction.text, "mvn $7f,$7e")
        self.assertEqual(instruction.operand, 0x7E7F)

    def test_a_truncated_instruction_is_reported(self):
        with self.assertRaises(cpu.Truncated):
            cpu.decode(b"\x8d\x01", 0, 0x008000)


class FlagTrackingTest(unittest.TestCase):
    def test_sep_narrows_and_rep_widens_the_accumulator(self):
        code = bytes([0xC2, 0x20, 0xA9, 0x34, 0x12, 0xE2, 0x20, 0xA9, 0x56])

        listing = cpu.disassemble(code, 0, 0x008000, m=True, x=True)

        self.assertEqual([i.text for i in listing[1::2]], ["lda #$1234", "lda #$56"])

    def test_sep_30_narrows_both_registers(self):
        code = bytes([0xE2, 0x30, 0xA9, 0x01, 0xA2, 0x02])

        listing = cpu.disassemble(code, 0, 0x008000, m=False, x=False)

        self.assertEqual(listing[1].text, "lda #$01")
        self.assertEqual(listing[2].text, "ldx #$02")

    def test_addresses_advance_by_the_instruction_size(self):
        code = bytes([0xEA, 0x8D, 0x01, 0x48, 0x60])

        listing = cpu.disassemble(code, 0, 0x008000)

        self.assertEqual([i.address for i in listing], [0x008000, 0x008001, 0x008004])

    def test_the_program_counter_wraps_inside_its_bank(self):
        code = bytes([0xEA, 0xEA])

        listing = cpu.disassemble(code, 0, 0x00FFFF)

        self.assertEqual([i.address for i in listing], [0x00FFFF, 0x000000])


class BranchTest(unittest.TestCase):
    def test_a_backward_branch_resolves_to_its_target(self):
        instruction = cpu.decode(bytes([0x80, 0xFE]), 0, 0x008010)

        self.assertEqual(instruction.text, "bra $8010")

    def test_a_forward_branch_resolves_to_its_target(self):
        instruction = cpu.decode(bytes([0x10, 0x05]), 0, 0x008000)

        self.assertEqual(instruction.text, "bpl $8007")


if __name__ == "__main__":
    unittest.main(verbosity=2)
