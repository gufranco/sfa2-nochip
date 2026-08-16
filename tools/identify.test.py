import hashlib
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_module(name, where):
    spec = importlib.util.spec_from_file_location(name, where / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


identify = load_module("identify", ROOT / "tools")


class CatalogueTest(unittest.TestCase):
    def test_every_rom_the_scripts_read_is_listed(self):
        self.assertEqual(
            sorted(identify.EXPECTED),
            [
                "sfa2-usa-final.sfc",
                "sfa2-usa-vc-sound-restored.sfc",
                "sfz2-jp-final.sfc",
            ],
        )

    def test_each_entry_carries_every_digest(self):
        for name, wanted in identify.EXPECTED.items():
            self.assertEqual(wanted.size, 4194304, name)
            self.assertEqual(len(wanted.crc32), 8, name)
            self.assertEqual(len(wanted.md5), 32, name)
            self.assertEqual(len(wanted.sha1), 40, name)
            self.assertEqual(len(wanted.sha256), 64, name)

    def test_the_digests_are_distinct_between_roms(self):
        digests = {wanted.sha256 for wanted in identify.EXPECTED.values()}

        self.assertEqual(len(digests), len(identify.EXPECTED))


class DigestTest(unittest.TestCase):
    def test_digests_of_known_bytes(self):
        measured = identify.digests(b"sf")

        self.assertEqual(measured.size, 2)
        self.assertEqual(measured.crc32, "E11AFCA7")
        self.assertEqual(measured.md5, hashlib.md5(b"sf").hexdigest())

    def test_the_same_bytes_always_measure_the_same(self):
        self.assertEqual(identify.digests(b"abc"), identify.digests(b"abc"))

    def test_different_bytes_measure_differently(self):
        self.assertNotEqual(identify.digests(b"abc"), identify.digests(b"abd"))


class VerdictTest(unittest.TestCase):
    def test_a_match_is_reported_as_one(self):
        wanted = next(iter(identify.EXPECTED.values()))

        self.assertEqual(identify.verdict(wanted, wanted), "ok")

    def test_a_wrong_size_is_named_first(self):
        wanted = next(iter(identify.EXPECTED.values()))
        found = wanted._replace(size=1)

        self.assertIn("size", identify.verdict(wanted, found))

    def test_a_wrong_digest_is_named(self):
        wanted = next(iter(identify.EXPECTED.values()))
        found = wanted._replace(sha256="0" * 64)

        self.assertIn("sha256", identify.verdict(wanted, found))


if __name__ == "__main__":
    unittest.main(verbosity=2)
