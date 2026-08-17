import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage_diff = load_module("stage_diff")


class HashesTest(unittest.TestCase):
    def write(self, text):
        path = Path(self.enterContext(__import__("tempfile").TemporaryDirectory())) / "h.txt"
        path.write_text(text)
        return path

    def test_a_missing_file_reads_as_no_frames(self):
        self.assertEqual(stage_diff.hashes(ROOT / "no-such-file.txt"), {})

    def test_each_line_becomes_a_frame_and_its_hash(self):
        path = self.write("0 aaaa\n1 bbbb\n")

        self.assertEqual(stage_diff.hashes(path), {0: "aaaa", 1: "bbbb"})

    def test_a_short_line_is_skipped(self):
        path = self.write("0 aaaa\ngarbage\n2 cccc\n")

        self.assertEqual(stage_diff.hashes(path), {0: "aaaa", 2: "cccc"})


class CompareTest(unittest.TestCase):
    def test_identical_runs_report_nothing_differing(self):
        both = {0: "a", 1: "b"}

        shared, differing = stage_diff.compare(both, dict(both))

        self.assertEqual(shared, [0, 1])
        self.assertEqual(differing, [])

    def test_a_changed_frame_is_reported(self):
        _, differing = stage_diff.compare({0: "a", 1: "b"}, {0: "a", 1: "z"})

        self.assertEqual(differing, [1])

    def test_only_frames_present_in_both_are_compared(self):
        shared, differing = stage_diff.compare({0: "a", 1: "b"}, {0: "z"})

        self.assertEqual(shared, [0])
        self.assertEqual(differing, [0])

    def test_the_frames_are_reported_in_order(self):
        before = {5: "a", 1: "a", 3: "a"}
        after = {5: "z", 1: "z", 3: "z"}

        _, differing = stage_diff.compare(before, after)

        self.assertEqual(differing, [1, 3, 5])


if __name__ == "__main__":
    unittest.main()
