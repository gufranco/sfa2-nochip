import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


spcfast = _load("spcfast")

HOOK_FILE = 0x070069
REPLACED = bytes([0xA9, 0x00, 0x15])

FILLER_FILE = 0x07F600
FILLER_END = 0x07F700
FILLER_SIZE = FILLER_END - FILLER_FILE
ROUTINE_ADDRESS = FILLER_FILE & 0xFFFF

MARKER = 0x1F3F

JSR = 0x20

ROUTINE = bytes.fromhex(
    "e220a303f03148af3f1f00c95ad017af401f00c9a5d00faf411f00c301d00768"
    "a90083038011688f411f00a95a8f3f1f00a9a58f401f00c220a9001560"
)


def hook():
    return bytes([JSR, ROUTINE_ADDRESS & 0xFF, ROUTINE_ADDRESS >> 8])


def is_patched(rom):
    if rom[HOOK_FILE : HOOK_FILE + len(REPLACED)] != hook():
        return False
    return rom[FILLER_FILE : FILLER_FILE + len(ROUTINE)] == ROUTINE


def apply(rom):
    if is_patched(rom):
        return bytes(rom)
    if rom[HOOK_FILE : HOOK_FILE + len(REPLACED)] != REPLACED:
        raise ValueError("the sound engine's allocator setup is not where this patch expects it")
    if set(rom[FILLER_FILE:FILLER_END]) != {0xFF}:
        raise ValueError("the filler the routine needs is not free")

    patched = bytearray(rom)
    patched[FILLER_FILE : FILLER_FILE + len(ROUTINE)] = ROUTINE
    patched[HOOK_FILE : HOOK_FILE + len(REPLACED)] = hook()
    return spcfast.write_checksum(patched)


def report(rom):
    state = "already applied" if is_patched(rom) else "ready"
    print(f"  hook      $C7:{HOOK_FILE & 0xFFFF:04X}  {REPLACED.hex(' ')} -> {hook().hex(' ')}")
    print(f"  routine   $C7:{ROUTINE_ADDRESS:04X}  {len(ROUTINE)} bytes")
    print(f"  marker    ${MARKER:04X}  two byte magic and the last list id")
    print(f"  state     {state}")


def main(argv):
    if len(argv) != 3:
        print("usage: repeatload.py <source-rom> <output-rom>", file=sys.stderr)
        return 2

    source, output = Path(argv[1]), Path(argv[2])
    if source.resolve() == output.resolve():
        print("refusing to patch the source ROM in place", file=sys.stderr)
        return 1

    rom = source.read_bytes()
    report(rom)
    output.write_bytes(apply(rom))
    print(f"[done] {output} ({output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
