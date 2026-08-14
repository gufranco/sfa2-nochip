import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent / "build.py"


def load_module():
    spec = importlib.util.spec_from_file_location("build", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


bd = load_module()


class ImageTest(unittest.TestCase):
    def test_the_image_tag_is_pinned_not_latest(self):
        self.assertNotIn(":latest", bd.IMAGE)
        self.assertIn(":", bd.IMAGE)

    def test_the_dockerfile_sits_beside_the_sources(self):
        self.assertTrue((bd.ASM_DIR / "Dockerfile").exists())


class CommandTest(unittest.TestCase):
    def test_the_build_command_names_the_pinned_tag(self):
        args = bd.build_image_command()

        self.assertIn("build", args)
        self.assertIn(bd.IMAGE, args)

    def test_the_patch_command_mounts_the_work_tree_read_write(self):
        args = bd.patch_command(Path("/w"), "p.asm", "rom.sfc")

        joined = " ".join(args)
        self.assertIn("--rm", args)
        self.assertIn("/w:/work", joined)
        self.assertIn("p.asm", args)
        self.assertIn("rom.sfc", args)

    def test_the_container_runs_without_network(self):
        args = bd.patch_command(Path("/w"), "p.asm", "rom.sfc")

        self.assertIn("--network=none", args)

    def test_paths_are_passed_as_names_not_host_paths(self):
        args = bd.patch_command(Path("/some/host/dir"), "patch.asm", "rom.sfc")

        self.assertNotIn("/some/host/dir/patch.asm", args)


class ArgumentTest(unittest.TestCase):
    def test_the_image_only_flag_is_reachable_on_its_own(self):
        self.assertTrue(bd.wants_image_only(["build.py", "--image"]))

    def test_a_normal_invocation_is_not_image_only(self):
        self.assertFalse(bd.wants_image_only(["build.py", "p.asm", "in", "out"]))

    def test_too_few_arguments_is_not_image_only(self):
        self.assertFalse(bd.wants_image_only(["build.py"]))


class SafetyTest(unittest.TestCase):
    def test_a_rom_is_copied_before_patching(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            rom = work / "orig.sfc"
            rom.write_bytes(b"x" * 1024)

            out = bd.stage_rom(rom, work, "out.sfc")

            self.assertTrue(out.exists())
            self.assertEqual(out.read_bytes(), rom.read_bytes())
            self.assertNotEqual(out, rom)

    def test_staging_never_overwrites_the_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            rom = work / "orig.sfc"
            rom.write_bytes(b"A" * 512)

            out = bd.stage_rom(rom, work, "out.sfc")
            out.write_bytes(b"B" * 512)

            self.assertEqual(rom.read_bytes(), b"A" * 512)


if __name__ == "__main__":
    unittest.main(verbosity=2)
