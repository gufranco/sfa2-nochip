import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sdd1ref = load("sdd1ref")
romtools = load("romtools")
rombuild = load("rombuild")
jpstreams = load("jpstreams")

BATCH = 200

SETS = {
    "usa": (
        ROOT / "roms" / "sfa2-usa-final.sfc",
        lambda: [
            (entry.source, entry.length)
            for entry in rombuild.load_entries(
                romtools.load(ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc")
            )
            if entry.length
        ],
    ),
    "jp": (
        ROOT / "roms" / "sfz2-jp-final.sfc",
        lambda: list(jpstreams.STREAMS),
    ),
}


def verify(region):
    retail, cases_for = SETS[region]
    rom = romtools.load(retail)
    cases = cases_for()
    mismatches = []
    for start in range(0, len(cases), BATCH):
        chunk = cases[start : start + BATCH]
        mismatches.extend(sdd1ref.compare(rom, chunk))
        print(
            f"    {region}: {min(start + BATCH, len(cases)):5d}/{len(cases)} checked, "
            f"{len(mismatches)} differing",
            flush=True,
        )
    return cases, mismatches


def main(argv):
    wanted = argv[1:] or sorted(SETS)
    if sdd1ref.build_image() != 0:
        print("the reference image failed to build", file=sys.stderr)
        return 1

    failed = False
    for region in wanted:
        cases, mismatches = verify(region)
        for offset, length, why in mismatches[:20]:
            print(f"  MISMATCH {offset:#09x} len {length}: {why}")
        if mismatches:
            failed = True
            print(f"  {region}: {len(mismatches)} of {len(cases)} streams differ")
        else:
            print(f"  {region}: all {len(cases)} streams identical to the reference")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
