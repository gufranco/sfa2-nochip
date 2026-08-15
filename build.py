import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASM_DIR = ROOT / "asm"
IMAGE = "sf-decompressed/asar:1.81"


def build_image_command():
    return [
        "docker",
        "build",
        "--tag",
        IMAGE,
        str(ASM_DIR),
    ]


def patch_command(work_dir, patch_name, rom_name):
    return [
        "docker",
        "run",
        "--rm",
        "--network=none",
        "--volume",
        f"{work_dir}:/work",
        IMAGE,
        patch_name,
        rom_name,
    ]


def stage_rom(source, work_dir, output_name):
    target = Path(work_dir) / output_name
    if target.resolve() == Path(source).resolve():
        raise ValueError("refusing to patch the source ROM in place")
    shutil.copy2(source, target)
    return target


def run(args):
    print("  $ " + " ".join(args), flush=True)
    result = subprocess.run(args, text=True, check=False)
    return result.returncode


def wants_image_only(argv):
    return len(argv) == 2 and argv[1] == "--image"


def main():
    if wants_image_only(sys.argv):
        return run(build_image_command())

    if len(sys.argv) < 4:
        print("usage: build.py <patch.asm> <source-rom> <output-rom>", file=sys.stderr)
        print(
            "       build.py --image        (build the toolchain image only)",
            file=sys.stderr,
        )
        return 2

    patch, source, output = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
    work = Path(patch).resolve().parent

    if run(build_image_command()) != 0:
        print("toolchain image failed to build", file=sys.stderr)
        return 1

    staged = stage_rom(source, work, output)
    print(f"  staged {source} -> {staged}")

    code = run(patch_command(work, Path(patch).name, output))
    if code == 0:
        print(f"[done] {staged} ({staged.stat().st_size:,} bytes)")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
