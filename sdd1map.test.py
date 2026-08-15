import importlib.util
import itertools
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sdd1map = load_module("sdd1map")
sdd1 = load_module("sdd1")
romtools = load_module("romtools")

TAGGED = ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc"
RETAIL = ROOT / "roms" / "sfa2-usa-final.sfc"
EXPECTED_STREAMS = 2815
EXPECTED_GFX_BYTES = 4947202
FIRST_SOURCE = 0x7890


def tagged_blob(markers, size=8192):
    blob = bytearray(size)
    for position, target in markers:
        blob[position : position + 4] = sdd1map.MARKER
        blob[position + 4 : position + 8] = target.to_bytes(4, "little")
    return bytes(blob)


class MarkerTest(unittest.TestCase):
    def test_markers_are_reported_in_rom_order(self):
        blob = tagged_blob([(100, 0), (300, 64), (700, 192)])

        markers = sdd1map.find_markers(blob)

        self.assertEqual(markers, [(100, 0), (300, 64), (700, 192)])

    def test_a_blob_without_markers_yields_nothing(self):
        self.assertEqual(sdd1map.find_markers(bytes(4096)), [])


class BuildMapTest(unittest.TestCase):
    def test_lengths_come_from_the_gap_between_consecutive_targets(self):
        blob = tagged_blob([(100, 0), (300, 64), (700, 192)])

        entries = sdd1map.build_map(blob)

        self.assertEqual([e.length for e in entries[:2]], [64, 128])

    def test_sources_are_the_marker_positions(self):
        blob = tagged_blob([(100, 0), (300, 64)])

        entries = sdd1map.build_map(blob)

        self.assertEqual([e.source for e in entries], [100, 300])

    def test_the_final_length_is_unknown_without_a_declared_total(self):
        blob = tagged_blob([(100, 0), (300, 64)])

        entries = sdd1map.build_map(blob)

        self.assertIsNone(entries[-1].length)

    def test_a_declared_total_resolves_the_final_length(self):
        blob = tagged_blob([(100, 0), (300, 64)])

        entries = sdd1map.build_map(blob, gfx_size=200)

        self.assertEqual(entries[-1].length, 136)

    def test_targets_that_move_backwards_are_rejected(self):
        blob = tagged_blob([(100, 64), (300, 0)])

        with self.assertRaises(ValueError):
            sdd1map.build_map(blob)

    def test_a_total_below_the_last_target_is_rejected(self):
        blob = tagged_blob([(100, 0), (300, 64)])

        with self.assertRaises(ValueError):
            sdd1map.build_map(blob, gfx_size=32)


@unittest.skipUnless(TAGGED.exists() and RETAIL.exists(), "roms are not present")
class RealMapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tagged = romtools.load(TAGGED)
        cls.retail = romtools.load(RETAIL)
        cls.entries = sdd1map.build_map(cls.tagged)

    def test_the_patched_rom_carries_one_marker_per_stream(self):
        self.assertEqual(len(self.entries), EXPECTED_STREAMS)

    def test_the_map_starts_at_the_first_compressed_stream(self):
        self.assertEqual(self.entries[0].source, FIRST_SOURCE)
        self.assertEqual(self.entries[0].target, 0)

    def test_the_declared_output_accounts_for_every_byte_of_the_graphics_blob(self):
        measured = sum(e.length for e in self.entries[:-1])

        self.assertEqual(measured, EXPECTED_GFX_BYTES)
        self.assertEqual(self.entries[-1].target, EXPECTED_GFX_BYTES)

    def test_targets_tile_the_graphics_blob_without_gaps(self):
        for previous, entry in itertools.pairwise(self.entries):
            self.assertEqual(previous.target + previous.length, entry.target)

    def test_every_stream_decompresses_from_the_untagged_rom(self):
        for entry in self.entries[:200]:
            stream = sdd1.decompress(self.retail, entry.source, entry.length)

            self.assertEqual(len(stream.data), entry.length)

    def test_most_streams_are_packed_end_to_end_in_the_rom(self):
        report = sdd1map.audit(self.retail, self.entries)

        self.assertGreater(report["packed"] / report["measured"], 0.9)

    def test_rebuilding_places_each_stream_at_its_declared_target(self):
        entries = self.entries[:64]
        total = entries[-1].target + entries[-1].length

        blob = sdd1map.rebuild(self.retail, entries, gfx_size=total)

        self.assertEqual(len(blob), total)
        for entry in entries:
            expected = sdd1.decompress(self.retail, entry.source, entry.length).data
            self.assertEqual(blob[entry.target : entry.target + entry.length], expected)

    def test_rebuilding_refuses_an_entry_of_unknown_length(self):
        with self.assertRaises(ValueError):
            sdd1map.rebuild(self.retail, self.entries[-1:])

    def test_rebuilding_refuses_a_blob_too_small_to_hold_a_stream(self):
        entries = self.entries[:4]

        with self.assertRaises(ValueError):
            sdd1map.rebuild(self.retail, entries, gfx_size=64)


if __name__ == "__main__":
    unittest.main(verbosity=2)
