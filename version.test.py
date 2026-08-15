import importlib.util
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


version = load_module("version")

SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class VersionTest(unittest.TestCase):
    def test_the_version_is_a_release_number(self):
        self.assertRegex(version.VERSION, SEMVER)

    def test_the_assignment_is_the_one_the_release_script_rewrites(self):
        source = (ROOT / "version.py").read_text()

        self.assertRegex(source, re.compile(r'^VERSION = "\d+\.\d+\.\d+"$', re.MULTILINE))


class StampedNameTest(unittest.TestCase):
    def test_the_name_carries_the_version(self):
        self.assertEqual(version.stamped("sfa2-usa-nochip", "1.2.3"), "sfa2-usa-nochip-v1.2.3.sfc")

    def test_the_shipped_version_is_the_default(self):
        self.assertIn(f"-v{version.VERSION}", version.stamped("x"))

    def test_a_development_build_is_marked_as_one(self):
        self.assertEqual(version.stamped("x", "0.0.0"), "x-v0.0.0-dev.sfc")


if __name__ == "__main__":
    unittest.main(verbosity=2)
