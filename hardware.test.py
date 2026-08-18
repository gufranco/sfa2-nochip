import importlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import hardware


class PathTest(unittest.TestCase):
    def test_every_model_it_names_is_on_disk(self):
        missing = [name for name in hardware.PACKAGES if not hardware.root_of(name).is_dir()]

        self.assertEqual(missing, [])

    def test_a_model_it_does_not_carry_is_refused_by_name(self):
        with self.assertRaises(hardware.UnknownPackage):
            hardware.root_of("nonsense")

    def test_the_refusal_lists_what_is_available(self):
        with self.assertRaises(hardware.UnknownPackage) as raised:
            hardware.root_of("nonsense")

        self.assertIn("sdd1", str(raised.exception))

    def test_installing_puts_every_model_on_the_import_path(self):
        hardware.install()

        for name in hardware.PACKAGES:
            self.assertIn(str(hardware.root_of(name)), sys.path)

    def test_installing_twice_does_not_stack_the_path(self):
        hardware.install()
        before = list(sys.path)

        hardware.install()

        self.assertEqual(sys.path, before)


class LoadTest(unittest.TestCase):
    def test_a_model_comes_back_by_the_name_it_is_published_under(self):
        found = hardware.load("sdd1")

        self.assertTrue(hasattr(found, "decompress"))

    def test_loading_a_model_it_does_not_carry_is_refused_before_importing(self):
        with self.assertRaises(hardware.UnknownPackage):
            hardware.load("nonsense")

    def test_loading_the_same_model_twice_gives_the_same_module(self):
        self.assertIs(hardware.load("mapper"), hardware.load("mapper"))


class ModelTest(unittest.TestCase):
    def setUp(self):
        hardware.install()

    def test_the_processor_reads_as_well_as_runs(self):
        cpu = importlib.import_module("mos65xx")

        self.assertTrue(hasattr(cpu, "Cpu"))
        self.assertTrue(hasattr(cpu, "disassemble"))

    def test_the_audio_processor_is_the_one_that_was_vendored(self):
        apu = importlib.import_module("spc700")

        self.assertTrue(hasattr(apu, "Cpu"))
        self.assertTrue(hasattr(apu, "disassemble"))

    def test_the_decompressor_is_the_one_that_was_vendored(self):
        chip = importlib.import_module("sdd1")

        self.assertTrue(hasattr(chip, "decompress"))
        self.assertEqual(chip.MAX_LENGTH, 0x10000)

    def test_the_audio_mixer_is_the_one_that_was_vendored(self):
        mixer = importlib.import_module("sdsp")

        self.assertTrue(hasattr(mixer, "Sdsp"))
        self.assertEqual(mixer.VOICE_COUNT, 8)

    def test_the_image_handling_is_the_one_that_was_vendored(self):
        found = importlib.import_module("romimage")

        self.assertTrue(hasattr(found.dump, "read"))
        self.assertTrue(hasattr(found.rewrite, "declare_rom_only"))

    def test_the_image_package_reads_the_map_this_project_pinned(self):
        found = importlib.import_module("romimage")
        used = importlib.import_module("mapper")

        self.assertIs(found.rewrite.mapper, used)

    def test_the_cartridge_map_is_the_one_that_was_vendored(self):
        found = importlib.import_module("mapper")

        self.assertTrue(hasattr(found, "resolve"))
        self.assertEqual(found.ENABLE, 0x420B)

    def test_every_model_reports_a_released_version(self):
        for name in hardware.PACKAGES:
            found = importlib.import_module(name)

            self.assertRegex(found.__version__, r"^\d+\.\d+\.\d+$")


if __name__ == "__main__":
    unittest.main()
