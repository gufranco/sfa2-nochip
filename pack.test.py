import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = load_module("pack")
version = load_module("version")


class RegionTest(unittest.TestCase):
    def test_both_cartridges_are_covered(self):
        self.assertEqual(sorted(pack.REGIONS), ["jp", "usa"])

    def test_each_region_names_its_retail_dump_and_its_patch(self):
        for region in pack.REGIONS.values():
            self.assertTrue(region.retail.name.endswith(".sfc"))
            self.assertTrue(region.bypass.endswith(".asm"))

    def test_the_two_regions_use_different_sources(self):
        self.assertNotEqual(pack.REGIONS["usa"].retail, pack.REGIONS["jp"].retail)


class NameTest(unittest.TestCase):
    def test_the_output_carries_the_region_and_the_version(self):
        name = pack.output_name("usa", "1.4.2")

        self.assertEqual(name, "sfa2-usa-nochip-v1.4.2.sfc")

    def test_the_japanese_output_uses_its_own_title(self):
        self.assertEqual(pack.output_name("jp", "1.4.2"), "sfz2-jp-nochip-v1.4.2.sfc")

    def test_an_unreleased_build_says_so(self):
        self.assertIn("-dev", pack.output_name("usa", version.UNRELEASED))

    def test_an_unknown_region_is_rejected(self):
        with self.assertRaises(KeyError):
            pack.output_name("eu", "1.0.0")


class ManifestTest(unittest.TestCase):
    def test_a_manifest_line_pairs_the_digest_with_the_name(self):
        line = pack.manifest_line("name.sfc", b"abc")

        self.assertTrue(line.endswith("  name.sfc"))
        self.assertEqual(len(line.split("  ")[0]), 64)

    def test_the_digest_is_of_the_image_and_not_the_name(self):
        first = pack.manifest_line("a.sfc", b"same")
        second = pack.manifest_line("b.sfc", b"same")

        self.assertEqual(first.split("  ")[0], second.split("  ")[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
