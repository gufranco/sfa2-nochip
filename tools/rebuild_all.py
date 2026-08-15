import importlib.util
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


spcfast = load("spcfast")
shinakuma = load("shinakuma")
rombuild = load("rombuild")
romtools = load("romtools")
header = load("header")
sdd1map = load("sdd1map")

OUT = ROOT / "build" / "all"
RETAIL = {"usa": ROOT / "roms" / "sfa2-usa-final.sfc", "jp": ROOT / "roms" / "sfz2-jp-final.sfc"}
BYPASS = {"usa": "sdd1-bypass.asm", "jp": "sdd1-bypass-jp.asm"}
TAGGED = ROOT / "roms" / "sfa2-usa-vc-sound-restored.sfc"


def variants(retail):
    fast = spcfast.apply(retail)
    return {
        "base": retail,
        "spc": fast,
        "sa": shinakuma.apply(retail),
        "both": shinakuma.apply(fast),
    }


def entries_for(region):
    if region == "usa":
        return rombuild.load_entries(romtools.load(TAGGED))
    return rombuild.entries_from_map({str(s): n for s, n in load("jpstreams").STREAMS})


def assemble(region, name, cart):
    staged = OUT / f"{region}-{name}-cart.sfc"
    staged.write_bytes(cart)
    output = f"{region}-{name}-bypass.sfc"
    subprocess.run(
        [
            sys.executable,
            "build.py",
            f"asm/{BYPASS[region]}",
            str(staged.relative_to(ROOT)),
            output,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    produced = ROOT / "asm" / output
    target = OUT / output
    target.write_bytes(produced.read_bytes())
    produced.unlink()
    return target


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for region, path in RETAIL.items():
        retail = romtools.load(path)
        entries = entries_for(region)
        for name, cart in variants(retail).items():
            bypass = assemble(region, name, cart)
            image = rombuild.build(romtools.load(bypass), entries).image
            free = OUT / f"{region}-{name}-free.sfc"
            free.write_bytes(header.declare_no_coprocessor(image))
            print(f"  {region}-{name}: cart, bypass, free ({len(entries)} streams)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
