import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


header = load_module("header")
romtools = load_module("romtools")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"


class ConstantTest(unittest.TestCase):
    def test_the_two_header_positions_are_the_documented_ones(self):
        self.assertEqual(header.POSITIONS, (0x007FC0, 0x00FFC0))

    def test_the_field_offsets_match_the_cartridge_layout(self):
        self.assertEqual(header.MAP_MODE, 0x15)
        self.assertEqual(header.CHIPSET, 0x16)
        self.assertEqual(header.ROM_SIZE, 0x17)
        self.assertEqual(header.SRAM_SIZE, 0x18)

    def test_rom_only_means_no_coprocessor(self):
        self.assertEqual(header.CHIPSET_ROM_ONLY, 0x00)


class SizeByteTest(unittest.TestCase):
    def test_a_four_megabyte_image_reports_twelve(self):
        self.assertEqual(header.size_byte(4 * 1024 * 1024), 0x0C)

    def test_a_twelve_megabyte_image_rounds_up_to_sixteen(self):
        self.assertEqual(header.size_byte(12 * 1024 * 1024), 0x0E)

    def test_an_exact_power_of_two_is_not_rounded_further(self):
        self.assertEqual(header.size_byte(8 * 1024 * 1024), 0x0D)

    def test_a_tiny_image_still_produces_a_usable_byte(self):
        self.assertGreater(header.size_byte(32 * 1024), 0)


class ReadTest(unittest.TestCase):
    def make_image(self, chipset=0x43, size=0x0C):
        image = bytearray(0x100000)
        for at in header.POSITIONS:
            image[at : at + 21] = b"TEST CARTRIDGE       "
            image[at + header.MAP_MODE] = 0x32
            image[at + header.CHIPSET] = chipset
            image[at + header.ROM_SIZE] = size
        return bytes(image)

    def test_a_populated_position_is_recognised(self):
        image = self.make_image()

        self.assertEqual(header.populated_positions(image), list(header.POSITIONS))

    def test_a_position_holding_non_text_is_ignored(self):
        image = bytearray(self.make_image())
        image[0x00FFC0 : 0x00FFC0 + 21] = bytes(21)

        self.assertEqual(header.populated_positions(bytes(image)), [0x007FC0])

    def test_a_position_past_the_end_is_ignored(self):
        self.assertEqual(header.populated_positions(bytes(0x1000)), [])


class DeclareTest(unittest.TestCase):
    def make_image(self):
        image = bytearray(0x100000)
        for at in header.POSITIONS:
            image[at : at + 21] = b"TEST CARTRIDGE       "
            image[at + header.MAP_MODE] = 0x32
            image[at + header.CHIPSET] = 0x43
            image[at + header.ROM_SIZE] = 0x0C
        return bytes(image)

    def test_every_position_loses_the_coprocessor(self):
        declared = header.declare_no_coprocessor(self.make_image())

        for at in header.POSITIONS:
            self.assertEqual(declared[at + header.CHIPSET], header.CHIPSET_ROM_ONLY)

    def test_every_position_reports_the_real_size(self):
        declared = header.declare_no_coprocessor(self.make_image())

        for at in header.POSITIONS:
            self.assertEqual(declared[at + header.ROM_SIZE], header.size_byte(0x100000))

    def test_the_map_mode_is_left_alone(self):
        declared = header.declare_no_coprocessor(self.make_image())

        self.assertEqual(declared[header.POSITIONS[0] + header.MAP_MODE], 0x32)

    def test_the_title_is_left_alone(self):
        image = self.make_image()

        declared = header.declare_no_coprocessor(image)

        self.assertEqual(declared[0x7FC0:0x7FD5], image[0x7FC0:0x7FD5])

    def test_the_source_image_is_not_modified(self):
        image = self.make_image()

        header.declare_no_coprocessor(image)

        self.assertEqual(image[0x7FC0 + header.CHIPSET], 0x43)

    def test_declaring_twice_changes_nothing_further(self):
        once = header.declare_no_coprocessor(self.make_image())

        self.assertEqual(header.declare_no_coprocessor(once), once)

    def test_the_checksum_agrees_at_every_position(self):
        declared = header.declare_no_coprocessor(self.make_image())
        first = declared[0x7FDE] | (declared[0x7FDF] << 8)
        second = declared[0xFFDE] | (declared[0xFFDF] << 8)

        self.assertEqual(first, second)

    def test_the_checksum_and_its_complement_are_a_pair(self):
        declared = header.declare_no_coprocessor(self.make_image())
        complement = declared[0x7FDC] | (declared[0x7FDD] << 8)
        value = declared[0x7FDE] | (declared[0x7FDF] << 8)

        self.assertEqual(complement ^ value, 0xFFFF)


@unittest.skipUnless(USA.exists(), "the retail ROM is not present")
class RetailRomTest(unittest.TestCase):
    def test_the_retail_cartridge_declares_the_chip(self):
        rom = romtools.load(USA)

        for at in header.populated_positions(rom):
            self.assertEqual(rom[at + header.CHIPSET], 0x43)

    def test_the_retail_cartridge_has_two_headers(self):
        self.assertEqual(len(header.populated_positions(romtools.load(USA))), 2)

    def test_every_mirrored_header_copy_is_found(self):
        rom = romtools.load(USA)

        self.assertGreaterEqual(len(header.header_positions(rom)), 2)

    def test_every_copy_loses_the_coprocessor(self):
        declared = header.declare_no_coprocessor(romtools.load(USA))

        for at in header.header_positions(declared):
            self.assertEqual(declared[at + header.CHIPSET], header.CHIPSET_ROM_ONLY)


if __name__ == "__main__":
    unittest.main(verbosity=2)
