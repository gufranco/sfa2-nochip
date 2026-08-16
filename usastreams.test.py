import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


usastreams = load_module("usastreams")
jpstreams = load_module("jpstreams")
rombuild = load_module("rombuild")
romtools = load_module("romtools")

TAGGED = ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc"


class ShapeTest(unittest.TestCase):
    def test_the_table_holds_every_tagged_stream(self):
        self.assertEqual(len(usastreams.STREAMS), 2815)

    def test_sources_are_unique(self):
        sources = [source for source, _ in usastreams.STREAMS]

        self.assertEqual(len(sources), len(set(sources)))

    def test_sources_are_ordered(self):
        sources = [source for source, _ in usastreams.STREAMS]

        self.assertEqual(sources, sorted(sources))

    def test_every_length_is_positive(self):
        for source, length in usastreams.STREAMS:
            self.assertGreater(length, 0, f"{source:#08x}")

    def test_every_source_lies_inside_a_four_megabyte_rom(self):
        for source, _ in usastreams.STREAMS:
            self.assertLess(source, 0x400000)

    def test_the_two_regions_are_different_tables(self):
        self.assertNotEqual(set(usastreams.STREAMS), set(jpstreams.STREAMS))


@unittest.skipUnless(TAGGED.exists(), "the tagged ROM is not present")
class RegenerationTest(unittest.TestCase):
    def test_the_frozen_table_matches_what_the_tags_say(self):
        entries = rombuild.load_entries(romtools.load(TAGGED))
        extracted = tuple((entry.source, entry.length) for entry in entries if entry.length)

        self.assertEqual(extracted, usastreams.STREAMS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
