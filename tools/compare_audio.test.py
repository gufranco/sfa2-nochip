import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare_audio = load_module("compare_audio", ROOT / "tools" / "compare_audio.py")


class RunTest(unittest.TestCase):
    def test_two_identical_dumps_differ_nowhere(self):
        self.assertEqual(compare_audio.runs_of_difference(bytes(64), bytes(64)), [])

    def test_one_differing_byte_is_one_run_of_one(self):
        second = bytearray(64)
        second[10] = 0xFF

        self.assertEqual(compare_audio.runs_of_difference(bytes(64), bytes(second)), [(10, 1)])

    def test_adjacent_differences_are_one_run(self):
        second = bytearray(64)
        second[10] = second[11] = second[12] = 0xFF

        self.assertEqual(compare_audio.runs_of_difference(bytes(64), bytes(second)), [(10, 3)])

    def test_separated_differences_are_separate_runs(self):
        second = bytearray(64)
        second[10] = second[20] = 0xFF

        self.assertEqual(
            compare_audio.runs_of_difference(bytes(64), bytes(second)), [(10, 1), (20, 1)]
        )

    def test_a_run_reaching_the_end_is_closed(self):
        second = bytearray(64)
        second[62] = second[63] = 0xFF

        self.assertEqual(compare_audio.runs_of_difference(bytes(64), bytes(second)), [(62, 2)])

    def test_a_run_starting_at_zero_is_found(self):
        second = bytearray(64)
        second[0] = 0xFF

        self.assertEqual(compare_audio.runs_of_difference(bytes(64), bytes(second)), [(0, 1)])


class VolatileTest(unittest.TestCase):
    def test_the_handshake_ports_are_volatile(self):
        for at in (0xF4, 0xF5, 0xF6, 0xF7):
            self.assertTrue(compare_audio.volatile(at), hex(at))

    def test_the_timer_registers_are_volatile(self):
        for at in range(0xFA, 0x100):
            self.assertTrue(compare_audio.volatile(at), hex(at))

    def test_sample_data_is_not(self):
        self.assertFalse(compare_audio.volatile(0x4000))

    def test_the_byte_between_the_ports_and_the_timers_is_not(self):
        self.assertFalse(compare_audio.volatile(0xF8))

    def test_a_difference_only_in_the_ports_is_not_meaningful(self):
        self.assertEqual(compare_audio.meaningful([(0xF4, 4)]), [])

    def test_a_difference_in_sample_data_is(self):
        self.assertEqual(compare_audio.meaningful([(0x4000, 16)]), [(0x4000, 16)])

    def test_a_run_that_straddles_the_ports_still_counts(self):
        self.assertEqual(compare_audio.meaningful([(0xF2, 8)]), [(0xF2, 8)])


class WhereTest(unittest.TestCase):
    def test_low_memory_is_the_drivers_own_variables(self):
        self.assertEqual(compare_audio.where(0x0010), "driver variables")

    def test_the_second_page_is_the_stack(self):
        self.assertEqual(compare_audio.where(0x0180), "stack")

    def test_the_ports_are_named_as_ports(self):
        self.assertEqual(compare_audio.where(0xF5), "ports and timers")

    def test_everything_else_is_what_was_uploaded(self):
        self.assertEqual(compare_audio.where(0x4000), "driver code or sample data")


class CompareTest(unittest.TestCase):
    def _dumps(self, folder, first, second):
        left = Path(folder) / "left.bin"
        right = Path(folder) / "right.bin"
        left.write_bytes(first)
        right.write_bytes(second)
        return left, right

    def test_two_identical_dumps_compare_clean(self):
        with tempfile.TemporaryDirectory() as folder:
            left, right = self._dumps(folder, bytes(0x10000), bytes(0x10000))

            found = compare_audio.compare(left, right)

            self.assertEqual(found["meaningful"], [])
            self.assertEqual(found["bytes"], 0)

    def test_a_difference_only_in_the_ports_compares_clean(self):
        with tempfile.TemporaryDirectory() as folder:
            second = bytearray(0x10000)
            second[0xF4] = 0xFF
            left, right = self._dumps(folder, bytes(0x10000), bytes(second))

            found = compare_audio.compare(left, right)

            self.assertEqual(found["meaningful"], [])
            self.assertEqual(found["bytes"], 1)

    def test_a_difference_in_uploaded_data_is_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            second = bytearray(0x10000)
            second[0x4000:0x4010] = b"\xff" * 16
            left, right = self._dumps(folder, bytes(0x10000), bytes(second))

            found = compare_audio.compare(left, right)

            self.assertEqual(found["meaningful"], [(0x4000, 16)])

    def test_the_sizes_of_both_dumps_are_reported(self):
        with tempfile.TemporaryDirectory() as folder:
            left, right = self._dumps(folder, bytes(0x10000), bytes(0x8000))

            self.assertEqual(compare_audio.compare(left, right)["sizes"], (0x10000, 0x8000))


class MainTest(unittest.TestCase):
    def test_it_refuses_a_call_with_the_wrong_number_of_arguments(self):
        self.assertEqual(compare_audio.main(["compare_audio.py"]), 2)


if __name__ == "__main__":
    unittest.main()
