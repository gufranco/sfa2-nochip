import importlib.util
import random
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


layout = load_module("layout")
romtools = load_module("romtools")

STAR_OCEAN = ROOT / "roms" / "star-ocean-jp-nochip-96mbit.sfc"
SO_BANKS = 192
SO_TABLE_LOW = 0x900000
SO_TABLE_HIGH = 0x300000


class AddressTest(unittest.TestCase):
    def test_the_high_half_of_a_bank_is_plain_lorom(self):
        self.assertEqual(layout.snes_to_file(0x00, 0x8000, SO_BANKS), 0x000000)
        self.assertEqual(layout.snes_to_file(0x01, 0x8000, SO_BANKS), 0x008000)
        self.assertEqual(layout.snes_to_file(0x60, 0x8000, SO_BANKS), 0x300000)

    def test_the_low_half_of_a_bank_sits_a_whole_rom_away(self):
        self.assertEqual(layout.snes_to_file(0x00, 0x0000, SO_BANKS), 0x600000)
        self.assertEqual(layout.snes_to_file(0x60, 0x0000, SO_BANKS), SO_TABLE_LOW)

    def test_the_two_directions_are_inverses(self):
        rng = random.Random(1)

        for _ in range(500):
            bank = rng.randrange(SO_BANKS)
            addr = rng.randrange(0x10000)

            offset = layout.snes_to_file(bank, addr, SO_BANKS)

            self.assertEqual(layout.file_to_snes(offset, SO_BANKS), (bank, addr))

    def test_every_file_offset_maps_somewhere(self):
        for offset in range(0, SO_BANKS * layout.BANK, 0x4000):
            bank, addr = layout.file_to_snes(offset, SO_BANKS)

            self.assertEqual(layout.snes_to_file(bank, addr, SO_BANKS), offset)

    def test_the_bank_count_comes_from_the_image_size(self):
        self.assertEqual(layout.bank_count(SO_BANKS * layout.BANK), SO_BANKS)


class WindowTest(unittest.TestCase):
    def test_the_window_halves_come_from_two_different_bases(self):
        low = layout.window_to_file(0xC0, 0x0000, SO_BANKS)
        high = layout.window_to_file(0xC0, 0x8000, SO_BANKS)

        self.assertEqual(low, 0xA00000)
        self.assertEqual(high, 0x600000)

    def test_the_window_advances_one_half_bank_per_bank(self):
        for offset in range(4):
            bank = 0xC0 + offset

            self.assertEqual(
                layout.window_to_file(bank, 0x0000, SO_BANKS),
                0xA00000 + offset * layout.HALF,
            )
            self.assertEqual(
                layout.window_to_file(bank, 0x8000, SO_BANKS),
                0x600000 + offset * layout.HALF,
            )

    def test_the_code_star_ocean_runs_at_c04d6a_is_where_the_rule_says(self):
        self.assertEqual(layout.window_to_file(0xC0, 0x4D6A, SO_BANKS), 0xA04D6A)

    def test_below_the_window_the_plain_interleave_still_applies(self):
        for bank in (0x00, 0x40, 0x60, 0xBF):
            for addr in (0x0000, 0x8000):
                self.assertEqual(
                    layout.address_to_file(bank, addr, SO_BANKS),
                    layout.snes_to_file(bank, addr, SO_BANKS),
                )

    def test_the_window_never_collides_with_the_banks_below_it(self):
        used = set()
        for bank in range(0x40, 0x7E):
            for addr in (0x0000, 0x8000):
                used.add(layout.snes_to_file(bank, addr, SO_BANKS))
        for bank in range(0xC0, 0x100):
            for addr in (0x0000, 0x8000):
                self.assertNotIn(layout.window_to_file(bank, addr, SO_BANKS), used)


class TransformTest(unittest.TestCase):
    def make_logical(self, banks=4):
        return bytes(
            (bank * 7 + (offset >> 8)) & 0xFF
            for bank in range(banks)
            for offset in range(layout.BANK)
        )

    def test_interleaving_then_deinterleaving_returns_the_original(self):
        logical = self.make_logical()

        self.assertEqual(layout.deinterleave(layout.interleave(logical)), logical)

    def test_interleaving_moves_each_half_where_the_address_math_says(self):
        logical = self.make_logical()
        n = layout.bank_count(len(logical))

        image = layout.interleave(logical)

        for bank in range(n):
            for addr in (0x0000, 0x4000, 0x8000, 0xC000):
                offset = layout.snes_to_file(bank, addr, n)
                self.assertEqual(image[offset], logical[bank * layout.BANK + addr])

    def test_an_image_that_is_not_a_whole_number_of_banks_is_rejected(self):
        with self.assertRaises(ValueError):
            layout.interleave(bytes(layout.BANK + 1))


@unittest.skipUnless(STAR_OCEAN.exists(), "the star ocean build is not present")
class StarOceanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = romtools.load(STAR_OCEAN)

    def test_the_build_is_a_whole_number_of_banks(self):
        self.assertEqual(layout.bank_count(len(self.image)), SO_BANKS)

    def test_the_lookup_tables_land_at_snes_bank_60(self):
        low = layout.file_to_snes(SO_TABLE_LOW, SO_BANKS)
        high = layout.file_to_snes(SO_TABLE_HIGH, SO_BANKS)

        self.assertEqual(low, (0x60, 0x0000))
        self.assertEqual(high, (0x60, 0x8000))

    def test_the_boot_bank_lands_where_lorom_expects_it(self):
        self.assertEqual(layout.file_to_snes(0x000000, SO_BANKS), (0x00, 0x8000))

    def test_deinterleaving_puts_bank_60_in_one_contiguous_run(self):
        logical = layout.deinterleave(self.image)
        base = 0x60 * layout.BANK

        self.assertEqual(
            logical[base : base + 0x8000],
            self.image[SO_TABLE_LOW : SO_TABLE_LOW + 0x8000],
        )
        self.assertEqual(
            logical[base + 0x8000 : base + 0x10000],
            self.image[SO_TABLE_HIGH : SO_TABLE_HIGH + 0x8000],
        )

    def test_the_transform_round_trips_on_the_real_build(self):
        self.assertEqual(layout.interleave(layout.deinterleave(self.image)), self.image)


if __name__ == "__main__":
    unittest.main(verbosity=2)
