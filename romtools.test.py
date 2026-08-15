import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "romtools.py"


def load_module():
    spec = importlib.util.spec_from_file_location("romtools", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rt = load_module()


class HeaderTest(unittest.TestCase):
    def test_a_copier_header_is_detected_and_stripped(self):
        data = b"\x00" * 512 + b"x" * 1048576

        self.assertTrue(rt.has_copier_header(data))
        self.assertEqual(len(rt.strip_header(data)), 1048576)

    def test_a_headerless_rom_is_left_alone(self):
        data = b"x" * 1048576

        self.assertFalse(rt.has_copier_header(data))
        self.assertEqual(len(rt.strip_header(data)), 1048576)


class GameDoctorTest(unittest.TestCase):
    def test_parts_join_in_letter_order_with_one_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "SF96soB.078").write_bytes(b"B" * 32768)
            (folder / "SF96soA.078").write_bytes(b"\x00" * 512 + b"A" * 32768)

            blob = rt.join_game_doctor(folder)

            self.assertEqual(blob, b"A" * 32768 + b"B" * 32768)

    def test_mixed_case_part_names_still_order_by_letter(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "SF32008D.078").write_bytes(b"D" * 32768)
            (folder / "sf32008a.078").write_bytes(b"\x00" * 512 + b"A" * 32768)

            self.assertEqual(rt.join_game_doctor(folder), b"A" * 32768 + b"D" * 32768)


class EntropyTest(unittest.TestCase):
    def test_random_data_reads_as_incompressible(self):
        import os

        block = os.urandom(65536)

        self.assertGreater(rt.deflate_ratio(block), 0.95)

    def test_repetitive_data_reads_as_compressible(self):
        self.assertLess(rt.deflate_ratio(b"\x00" * 65536), 0.1)

    def test_the_profile_returns_one_ratio_per_block(self):
        data = b"\x00" * (65536 * 3)

        ratios = rt.block_ratios(data, 65536)

        self.assertEqual(len(ratios), 3)


class ChunkIndexTest(unittest.TestCase):
    def test_a_chunk_present_in_both_is_found(self):
        a = b"HELLO" * 300
        index = rt.chunk_index(a, chunk=64, stride=64)

        self.assertIn(a[:64], index)

    def test_reuse_is_measured_as_a_fraction(self):
        a = b"A" * 4096
        b = b"A" * 4096

        found, total = rt.measure_reuse(a, b, chunk=1024)

        self.assertEqual(found, total)

    def test_unrelated_data_shares_nothing(self):
        found, total = rt.measure_reuse(b"A" * 4096, b"B" * 4096, chunk=1024)

        self.assertEqual(found, 0)
        self.assertEqual(total, 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
