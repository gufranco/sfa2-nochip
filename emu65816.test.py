import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


emu = load_module("emu65816")


class FlatMemory:
    def __init__(self, data=None):
        self.cells = dict(data or {})

    def read8(self, address):
        return self.cells.get(address & 0xFFFFFF, 0x00)

    def write8(self, address, value):
        self.cells[address & 0xFFFFFF] = value & 0xFF


def run(code, base=0x008000, memory=None, **registers):
    memory = memory or FlatMemory()
    for offset, byte in enumerate(code):
        memory.cells[base + offset] = byte
    cpu = emu.Cpu(memory)
    for name, value in registers.items():
        setattr(cpu, name, value)
    cpu.call(base)
    return cpu


class WidthTest(unittest.TestCase):
    def test_sep_and_rep_move_the_accumulator_width(self):
        cpu = run([0xE2, 0x20, 0xC2, 0x20, 0x6B])

        self.assertFalse(cpu.m8)

    def test_an_eight_bit_immediate_loads_one_byte(self):
        cpu = run([0xE2, 0x20, 0xA9, 0x7F, 0x6B])

        self.assertEqual(cpu.a & 0xFF, 0x7F)

    def test_a_sixteen_bit_immediate_loads_two_bytes(self):
        cpu = run([0xC2, 0x20, 0xA9, 0x34, 0x12, 0x6B])

        self.assertEqual(cpu.a, 0x1234)


class StackTest(unittest.TestCase):
    def test_a_pushed_word_comes_back_unchanged(self):
        cpu = run([0xC2, 0x30, 0xA9, 0x34, 0x12, 0x48, 0xA9, 0x00, 0x00, 0x68, 0x6B])

        self.assertEqual(cpu.a, 0x1234)

    def test_pea_pushes_a_literal_that_plb_can_pull(self):
        cpu = run([0xF4, 0x60, 0x60, 0xAB, 0xAB, 0x6B])

        self.assertEqual(cpu.db, 0x60)

    def test_php_and_plp_restore_the_carry(self):
        cpu = run([0x38, 0x08, 0x18, 0x28, 0x6B])

        self.assertTrue(cpu.c)

    def test_the_stack_pointer_returns_to_where_it_started(self):
        cpu = run([0x08, 0x8B, 0xC2, 0x30, 0x48, 0x68, 0xAB, 0x28, 0x6B], s=0x01FF)

        self.assertEqual(cpu.s, 0x01FF)


class AddressingTest(unittest.TestCase):
    def test_a_long_read_reaches_another_bank(self):
        memory = FlatMemory({0x610042: 0x99})

        cpu = run([0xE2, 0x30, 0xA2, 0x42, 0xBF, 0x00, 0x00, 0x61, 0x6B], memory=memory)

        self.assertEqual(cpu.a & 0xFF, 0x99)

    def test_a_long_write_reaches_another_bank(self):
        memory = FlatMemory()

        run([0xE2, 0x20, 0xA9, 0x5A, 0x8F, 0x02, 0x43, 0x00, 0x6B], memory=memory)

        self.assertEqual(memory.read8(0x004302), 0x5A)

    def test_absolute_indexed_uses_the_data_bank(self):
        memory = FlatMemory({0x600005: 0x77})

        cpu = run(
            [
                0xF4,
                0x60,
                0x60,
                0xAB,
                0xAB,
                0xE2,
                0x20,
                0xA0,
                0x05,
                0x00,
                0xB9,
                0x00,
                0x00,
                0x6B,
            ],
            memory=memory,
        )

        self.assertEqual(cpu.a & 0xFF, 0x77)

    def test_an_absolute_index_load_uses_the_data_bank(self):
        memory = FlatMemory({0x004302: 0x34, 0x004303: 0x12})

        cpu = run([0xC2, 0x30, 0xAE, 0x02, 0x43, 0x6B], memory=memory)

        self.assertEqual(cpu.x, 0x1234)

    def test_stack_relative_reads_below_the_pointer(self):
        cpu = run([0xC2, 0x30, 0xA9, 0x21, 0x43, 0x48, 0xA5, 0x00, 0xA3, 0x01, 0x6B])

        self.assertEqual(cpu.a, 0x4321)


class LoopTest(unittest.TestCase):
    def test_a_scan_stops_on_the_matching_byte(self):
        memory = FlatMemory({0x600003: 0xCE})
        code = [
            0xE2,
            0x20,
            0xF4,
            0x60,
            0x60,
            0xAB,
            0xAB,
            0xA9,
            0xCE,
            0xD9,
            0x00,
            0x00,
            0xF0,
            0x03,
            0xC8,
            0x80,
            0xF8,
            0x6B,
        ]

        cpu = run(code, memory=memory, y=0x0000)

        self.assertEqual(cpu.y, 0x0003)

    def test_a_runaway_loop_is_stopped_rather_than_hanging(self):
        with self.assertRaises(emu.StepLimit):
            run([0x80, 0xFE, 0x6B])


if __name__ == "__main__":
    unittest.main(verbosity=2)
