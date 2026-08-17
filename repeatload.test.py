import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


repeatload = load_module("repeatload")
spcfast = load_module("spcfast")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"
JP = ROOT / "roms" / "sfz2-jp-final.sfc"


def retail(path):
    if not path.exists():
        raise unittest.SkipTest(f"{path} is not present")
    return path.read_bytes()


class RoutineTest(unittest.TestCase):
    def test_the_routine_ends_in_a_return(self):
        self.assertEqual(repeatload.ROUTINE[-1], 0x60)

    def test_the_routine_restores_the_instruction_it_replaced(self):
        self.assertEqual(repeatload.ROUTINE[-4:-1], bytes([0xA9, 0x00, 0x15]))

    def test_every_marker_access_is_long_addressed(self):
        loads = repeatload.ROUTINE.count(0xAF)
        stores = repeatload.ROUTINE.count(0x8F)

        self.assertEqual(loads, 3)
        self.assertEqual(stores, 3)

    def test_the_routine_fits_the_filler_it_is_written_into(self):
        self.assertLess(len(repeatload.ROUTINE), repeatload.FILLER_SIZE)

    def test_the_hook_is_a_call_to_the_routine(self):
        self.assertEqual(repeatload.hook(), bytes([0x20, repeatload.ROUTINE_ADDRESS & 0xFF, 0xF6]))

    def test_the_hook_is_the_same_length_as_what_it_replaces(self):
        self.assertEqual(len(repeatload.hook()), len(repeatload.REPLACED))

    def test_the_routine_matches_what_the_assembler_emits(self):
        assembled = ROOT / "asm" / "repeat-out.sfc"
        if not assembled.exists():
            raise unittest.SkipTest("assemble asm/repeat-load.asm first")

        produced = assembled.read_bytes()

        self.assertEqual(
            produced[repeatload.FILLER_FILE : repeatload.FILLER_FILE + len(repeatload.ROUTINE)],
            repeatload.ROUTINE,
        )


class SiteTest(unittest.TestCase):
    def test_the_hook_site_carries_the_expected_instruction_in_both_regions(self):
        for path in (USA, JP):
            rom = retail(path)

            self.assertEqual(
                rom[repeatload.HOOK_FILE : repeatload.HOOK_FILE + len(repeatload.REPLACED)],
                repeatload.REPLACED,
                str(path),
            )

    def test_the_filler_is_free_in_both_regions(self):
        for path in (USA, JP):
            rom = retail(path)

            window = rom[repeatload.FILLER_FILE : repeatload.FILLER_FILE + repeatload.FILLER_SIZE]
            self.assertEqual(set(window), {0xFF}, str(path))

    def test_the_marker_sits_inside_the_run_no_write_was_seen_in(self):
        self.assertGreaterEqual(repeatload.MARKER, 0x1F3F)
        self.assertLessEqual(repeatload.MARKER + 3, 0x1FC6)


class ApplyTest(unittest.TestCase):
    def test_applying_installs_the_hook_and_the_routine(self):
        for path in (USA, JP):
            rom = retail(path)

            patched = repeatload.apply(rom)

            self.assertEqual(
                patched[repeatload.HOOK_FILE : repeatload.HOOK_FILE + 3],
                repeatload.hook(),
                str(path),
            )
            self.assertEqual(
                patched[repeatload.FILLER_FILE : repeatload.FILLER_FILE + len(repeatload.ROUTINE)],
                repeatload.ROUTINE,
                str(path),
            )

    def test_applying_twice_changes_nothing_the_second_time(self):
        rom = retail(USA)

        once = repeatload.apply(rom)

        self.assertEqual(repeatload.apply(once), once)

    def test_a_rom_without_the_site_is_refused(self):
        with self.assertRaises(ValueError):
            repeatload.apply(b"\x00" * 0x100000)

    def test_nothing_outside_the_hook_and_the_routine_moves(self):
        rom = retail(USA)

        patched = repeatload.apply(rom)

        allowed = set(range(repeatload.HOOK_FILE, repeatload.HOOK_FILE + 3))
        allowed.update(
            range(repeatload.FILLER_FILE, repeatload.FILLER_FILE + len(repeatload.ROUTINE))
        )
        allowed.update(range(spcfast.CHECKSUM_FIELD, spcfast.CHECKSUM_FIELD + 4))
        moved = {at for at, (a, b) in enumerate(zip(rom, patched, strict=True)) if a != b}
        self.assertTrue(moved <= allowed, sorted(moved - allowed)[:8])

    def test_it_does_not_collide_with_the_pre_fight_routine(self):
        prefight = load_module("prefight")

        first = range(prefight.FILLER_FILE, prefight.FILLER_FILE + len(prefight.ROUTINE))
        second = range(repeatload.FILLER_FILE, repeatload.FILLER_FILE + len(repeatload.ROUTINE))

        self.assertFalse(set(first) & set(second))


if __name__ == "__main__":
    unittest.main()
