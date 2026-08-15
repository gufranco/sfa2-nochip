import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


shinakuma = load_module("shinakuma")
wdc65816 = load_module("wdc65816")
romtools = load_module("romtools")

USA = ROOT / "roms" / "sfa2-usa-final.sfc"
JP = ROOT / "roms" / "sfz2-jp-final.sfc"


class SignatureTest(unittest.TestCase):
    def test_the_gate_signature_is_the_documented_length(self):
        self.assertEqual(len(shinakuma.GATE), 0x2F)

    def test_the_signature_starts_with_php_and_a_sixteen_bit_switch(self):
        self.assertEqual(shinakuma.GATE[:3], bytes([0x08, 0xC2, 0x30]))

    def test_the_signature_ends_by_storing_the_unlock_flag(self):
        self.assertEqual(shinakuma.GATE[-6:], bytes([0xA9, 0x4B, 0x4A, 0x8D, 0x09, 0x1B]))

    def test_the_branch_lands_on_the_unconditional_store(self):
        landing = shinakuma.PRECONDITION + 2 + shinakuma.BRANCH[1]

        self.assertEqual(landing, shinakuma.SET_FLAG)

    def test_the_initials_spell_the_documented_code(self):
        self.assertEqual(shinakuma.INITIALS, b"KAJ")

    def test_the_button_combination_is_l_x_y_and_start(self):
        self.assertEqual(
            shinakuma.COMBINATION,
            shinakuma.BUTTON_L | shinakuma.BUTTON_X | shinakuma.BUTTON_Y | shinakuma.BUTTON_START,
        )


class FindGateTest(unittest.TestCase):
    def test_a_rom_without_the_gate_yields_nothing(self):
        self.assertIsNone(shinakuma.find_gate(bytes(0x20000)))

    def test_the_gate_is_located_by_its_signature(self):
        rom = bytearray(0x20000)
        rom[0x00ABCD : 0x00ABCD + len(shinakuma.GATE)] = shinakuma.GATE

        self.assertEqual(shinakuma.find_gate(bytes(rom)), 0x00ABCD)

    def test_two_gates_are_rejected_as_ambiguous(self):
        rom = bytearray(0x20000)
        rom[0x001000 : 0x001000 + len(shinakuma.GATE)] = shinakuma.GATE
        rom[0x009000 : 0x009000 + len(shinakuma.GATE)] = shinakuma.GATE

        with self.assertRaises(ValueError):
            shinakuma.find_gate(bytes(rom))


class ApplyTest(unittest.TestCase):
    def make_rom(self):
        rom = bytearray(0x20000)
        rom[0x00EC6E : 0x00EC6E + len(shinakuma.GATE)] = shinakuma.GATE
        return bytes(rom)

    def test_the_branch_replaces_the_precondition_test(self):
        patched = shinakuma.apply(self.make_rom())
        site = 0x00EC6E + shinakuma.PRECONDITION

        self.assertEqual(patched[site : site + 2], shinakuma.BRANCH)

    def test_only_the_branch_and_the_checksum_change(self):
        rom = self.make_rom()

        patched = shinakuma.apply(rom)
        changed = {i for i in range(len(rom)) if rom[i] != patched[i]}
        site = 0x00EC6E + shinakuma.PRECONDITION
        allowed = {site, site + 1} | set(
            range(shinakuma.spcfast.CHECKSUM_FIELD, shinakuma.spcfast.CHECKSUM_FIELD + 4)
        )

        self.assertTrue(changed.issubset(allowed))

    def test_the_store_itself_is_left_alone(self):
        rom = self.make_rom()
        patched = shinakuma.apply(rom)
        site = 0x00EC6E + shinakuma.SET_FLAG

        self.assertEqual(patched[site : site + 6], rom[site : site + 6])

    def test_the_source_rom_is_not_modified(self):
        rom = self.make_rom()

        shinakuma.apply(rom)

        self.assertEqual(rom[0x00EC6E + shinakuma.PRECONDITION], 0xAD)

    def test_applying_twice_changes_nothing_further(self):
        once = shinakuma.apply(self.make_rom())

        self.assertEqual(shinakuma.apply(once), once)

    def test_a_rom_without_the_gate_is_rejected(self):
        with self.assertRaises(ValueError):
            shinakuma.apply(bytes(0x20000))


class DisassemblyTest(unittest.TestCase):
    def test_the_stock_gate_disassembles_to_the_documented_listing(self):
        listing = [
            instruction.text
            for instruction in wdc65816.disassemble(shinakuma.GATE, 0, 0xC0EC6E, m=False, x=False)
        ]

        self.assertEqual(
            listing,
            [
                "php",
                "rep #$30",
                "lda $1b05",
                "bpl $ec9d",
                "lda $1b09",
                "cmp #$4a4b",
                "beq $ec9d",
                "lda $7efe04",
                "cmp #$414b",
                "bne $ec9d",
                "lda $7efe05",
                "cmp #$4a41",
                "bne $ec9d",
                "lda $b0",
                "cmp #$5060",
                "bne $ec9d",
                "lda #$4a4b",
                "sta $1b09",
            ],
        )

    def test_the_patched_gate_branches_straight_to_the_store(self):
        patched = bytearray(shinakuma.GATE)
        patched[shinakuma.PRECONDITION : shinakuma.PRECONDITION + 2] = shinakuma.BRANCH
        listing = list(wdc65816.disassemble(bytes(patched), 0, 0xC0EC6E, count=3, m=False, x=False))

        self.assertEqual([i.text for i in listing], ["php", "rep #$30", "bra $ec97"])


@unittest.skipUnless(USA.exists() and JP.exists(), "the retail ROMs are not present")
class RetailRomTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.usa = romtools.load(USA)
        cls.jp = romtools.load(JP)

    def test_the_gate_is_present_exactly_once_in_each_region(self):
        self.assertEqual(shinakuma.find_gate(self.usa), 0x00EC6E)
        self.assertEqual(shinakuma.find_gate(self.jp), 0x00ECA0)

    def test_the_gate_is_byte_identical_across_regions(self):
        usa = shinakuma.find_gate(self.usa)
        jp = shinakuma.find_gate(self.jp)

        self.assertEqual(
            self.usa[usa : usa + len(shinakuma.GATE)],
            self.jp[jp : jp + len(shinakuma.GATE)],
        )

    def test_patching_touches_only_the_branch_and_the_checksum(self):
        patched = shinakuma.apply(self.usa)
        changed = {i for i in range(len(patched)) if patched[i] != self.usa[i]}
        site = 0x00EC6E + shinakuma.PRECONDITION
        allowed = {site, site + 1} | set(
            range(shinakuma.spcfast.CHECKSUM_FIELD, shinakuma.spcfast.CHECKSUM_FIELD + 4)
        )

        self.assertTrue(changed.issubset(allowed))
        self.assertIn(site, changed)
        self.assertIn(site + 1, changed)

    def test_the_substitution_handler_is_untouched(self):
        patched = shinakuma.apply(self.usa)

        self.assertEqual(patched[0x00CA7F:0x00CAD0], self.usa[0x00CA7F:0x00CAD0])

    def test_both_regions_patch_at_their_own_offset(self):
        for rom, offset in ((self.usa, 0x00EC6E), (self.jp, 0x00ECA0)):
            patched = shinakuma.apply(rom)
            site = offset + shinakuma.PRECONDITION

            self.assertEqual(patched[site : site + 2], shinakuma.BRANCH)


if __name__ == "__main__":
    unittest.main(verbosity=2)
