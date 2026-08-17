import hashlib
import importlib.util
import subprocess
import sys
from collections import namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


romtools = _load("romtools")
rombuild = _load("rombuild")
header = _load("header")
spcfast = _load("spcfast")
shinakuma = _load("shinakuma")
gamefixes = _load("gamefixes")
repeatload = _load("repeatload")
prefight = _load("prefight")
jpstreams = _load("jpstreams")
usastreams = _load("usastreams")
version = _load("version")
gate = _load("gate")

Region = namedtuple("Region", "title retail bypass tagged")

REGIONS = {
    "usa": Region(
        title="sfa2-usa",
        retail=ROOT / "roms" / "sfa2-usa-final.sfc",
        bypass="asm/sdd1-bypass.asm",
        tagged=ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc",
    ),
    "jp": Region(
        title="sfz2-jp",
        retail=ROOT / "roms" / "sfz2-jp-final.sfc",
        bypass="asm/sdd1-bypass-jp.asm",
        tagged=None,
    ),
}

DIST = ROOT / "dist"
MANIFEST = "SHA256SUMS"


def output_name(region, release=None):
    return version.stamped(f"{REGIONS[region].title}-nochip", release)


def manifest_line(name, image):
    return f"{hashlib.sha256(image).hexdigest()}  {name}"


def entries_for(region):
    table = jpstreams.STREAMS if region == "jp" else usastreams.STREAMS
    return rombuild.entries_from_map({str(source): length for source, length in table})


def assemble_bypass(region, cart, workdir):
    staged = workdir / f"{region}-patched.sfc"
    staged.write_bytes(cart)
    produced_name = f"{region}-bypass.sfc"
    subprocess.run(
        [
            sys.executable,
            "build.py",
            REGIONS[region].bypass,
            str(staged.relative_to(ROOT)),
            produced_name,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    produced = ROOT / "asm" / produced_name
    image = produced.read_bytes()
    produced.unlink()
    return image


def build(region, workdir):
    retail = romtools.load(REGIONS[region].retail)
    cart = repeatload.apply(gamefixes.apply(shinakuma.apply(spcfast.apply(retail))))
    bypass = prefight.apply(assemble_bypass(region, cart, workdir))
    extra = ((prefight.TABLE_ADDRESS, prefight.table()),)
    image = rombuild.build(bypass, entries_for(region), extra=extra).image
    return header.declare_no_coprocessor(image)


def main(argv):
    wanted = argv[1:] or sorted(REGIONS)
    unknown = [region for region in wanted if region not in REGIONS]
    if unknown:
        print(f"unknown region: {', '.join(unknown)}", file=sys.stderr)
        return 2

    missing = [str(REGIONS[r].retail) for r in wanted if not REGIONS[r].retail.exists()]
    if missing:
        print("these retail dumps are not present:", file=sys.stderr)
        for path in missing:
            print(f"  {path}", file=sys.stderr)
        return 1

    for region in wanted:
        findings = gate.check(region)
        if findings:
            print(f"the {region} stream table does not pass the gate:", file=sys.stderr)
            for finding in findings:
                print(f"  {finding}", file=sys.stderr)
            return 1

    DIST.mkdir(exist_ok=True)
    workdir = DIST / "work"
    workdir.mkdir(exist_ok=True)

    lines = []
    for region in wanted:
        image = build(region, workdir)
        name = output_name(region)
        (DIST / name).write_bytes(image)
        lines.append(manifest_line(name, image))
        print(f"  {name}  {len(image):,} bytes", flush=True)

    (DIST / MANIFEST).write_text("\n".join(lines) + "\n")
    print(f"  {MANIFEST}  {len(lines)} images")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
