import importlib.util
import os
import random
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "sdd1.py"


def load_module():
    spec = importlib.util.spec_from_file_location("sdd1", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sdd1 = load_module()


def reverse7(value):
    out = 0
    for i in range(7):
        out |= ((value >> i) & 1) << (6 - i)
    return out


def synthetic(header, size=4096, seed=1):
    rng = random.Random(seed)
    return bytes([header]) + bytes(rng.randrange(256) for _ in range(size))


READ_AHEAD_PADDING = 64


class TableTest(unittest.TestCase):
    def test_the_run_table_is_a_permutation_of_one_to_128(self):
        self.assertEqual(sorted(sdd1.RUN_TABLE), list(range(1, 129)))

    def test_the_run_table_is_the_reversed_index_complement(self):
        expected = tuple(128 - reverse7(i) for i in range(128))

        self.assertEqual(sdd1.RUN_TABLE, expected)

    def test_every_evolution_row_names_reachable_states(self):
        for code_size, mps_next, lps_next in sdd1.EVOLUTION:
            self.assertIn(code_size, range(8))
            self.assertLess(mps_next, len(sdd1.EVOLUTION))
            self.assertLess(lps_next, len(sdd1.EVOLUTION))

    def test_the_evolution_table_has_33_states(self):
        self.assertEqual(len(sdd1.EVOLUTION), 33)


class HeaderTest(unittest.TestCase):
    def test_the_header_selects_the_bitplane_count(self):
        self.assertEqual(sdd1.bitplane_count(0), 2)
        self.assertEqual(sdd1.bitplane_count(1), 4)
        self.assertEqual(sdd1.bitplane_count(2), 4)
        self.assertEqual(sdd1.bitplane_count(3), 8)

    def test_the_header_is_reported_back_on_the_stream(self):
        for bitplane_type in range(4):
            for context_type in range(4):
                header = (bitplane_type << 6) | (context_type << 4)

                stream = sdd1.decompress(synthetic(header), 0, 64)

                self.assertEqual(stream.bitplanes, sdd1.bitplane_count(bitplane_type))
                self.assertEqual(stream.context, context_type)


class OutputTest(unittest.TestCase):
    def test_every_bitplane_mode_emits_exactly_the_requested_length(self):
        for bitplane_type in range(4):
            rom = synthetic(bitplane_type << 6)

            for length in (1, 2, 15, 16, 17, 512):
                self.assertEqual(len(sdd1.decompress(rom, 0, length).data), length)

    def test_a_zero_length_request_means_a_full_64k_block(self):
        rom = synthetic(0xC0, size=65536, seed=7)

        self.assertEqual(len(sdd1.decompress(rom, 0, 0).data), sdd1.MAX_LENGTH)

    def test_a_short_read_is_a_prefix_of_a_long_read(self):
        rom = synthetic(0x40, seed=3)

        short = sdd1.decompress(rom, 0, 64).data
        long = sdd1.decompress(rom, 0, 512).data

        self.assertEqual(long[:64], short)

    def test_decoder_state_does_not_leak_between_calls(self):
        rom = synthetic(0x00, seed=5)
        first = sdd1.decompress(rom, 0, 256).data

        sdd1.decompress(rom, 37, 256)
        sdd1.decompress(rom, 91, 1)

        self.assertEqual(sdd1.decompress(rom, 0, 256).data, first)

    def test_the_consumed_end_advances_past_the_two_byte_prologue(self):
        rom = synthetic(0x00, seed=11)

        stream = sdd1.decompress(rom, 0, 256)

        self.assertGreater(stream.end, 2)
        self.assertLessEqual(stream.end, len(rom))


class VendorStreamTest(unittest.TestCase):
    def pairs(self):
        named = os.environ.get("SFA2_VENDOR_STREAMS")
        if not named:
            raise unittest.SkipTest("set SFA2_VENDOR_STREAMS to a folder of .sdd1 and .raw pairs")
        folder = Path(named)
        if not folder.is_dir():
            raise unittest.SkipTest(f"{folder} is not a folder")
        found = [
            (packed, packed.with_suffix(".raw"))
            for packed in sorted(folder.rglob("*.sdd1"))
            if packed.with_suffix(".raw").exists()
        ]
        if not found:
            raise unittest.SkipTest(f"no .sdd1 and .raw pairs under {folder}")
        return found

    def test_every_vendor_pair_decompresses_to_its_own_raw_file(self):
        for packed, raw in self.pairs():
            want = raw.read_bytes()
            padded = packed.read_bytes() + bytes(READ_AHEAD_PADDING)

            got = sdd1.decompress(padded, 0, len(want)).data

            self.assertEqual(got, want, packed.name)

    def test_the_pairs_cover_more_than_one_stream(self):
        self.assertGreater(len(self.pairs()), 1)


class BoundsTest(unittest.TestCase):
    def test_running_off_the_end_of_the_rom_is_reported(self):
        rom = synthetic(0x00, size=8)

        with self.assertRaises(sdd1.TruncatedStream):
            sdd1.decompress(rom, 0, 4096)

    def test_an_offset_past_the_end_is_reported(self):
        rom = synthetic(0x00, size=8)

        with self.assertRaises(sdd1.TruncatedStream):
            sdd1.decompress(rom, len(rom), 16)

    def test_a_negative_offset_is_reported(self):
        rom = synthetic(0x00, size=64)

        with self.assertRaises(sdd1.TruncatedStream):
            sdd1.decompress(rom, -1, 16)


if __name__ == "__main__":
    unittest.main(verbosity=2)
