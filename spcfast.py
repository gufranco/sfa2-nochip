import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DRIVER_BASE = 0x071C56
RECEIVE_LOOP = 0x0EBD
BLOCK_HEADER = 0x0EFF

CHECKSUM_FIELD = 0x007FDC
CHECKSUM_FIELD_SUM = 0x01FE

BLANK_GATE = bytes([0xAF, 0x12, 0x42, 0x00, 0x29, 0xC0, 0xF0, 0xF8])

STOCK_PROBE = (
    (0x072B13, bytes([0xEC, 0xF4, 0x00, 0x5E, 0xF4, 0x00, 0xD0, 0xF8])),
    (0x07046D, bytes([0x01])),
    (0x070222, BLANK_GATE),
)

PATCH = (
    (0x070222, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x070241, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x07025f, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x0702b2, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x0702d1, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x0702ef, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x070337, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x070355, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x070373, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x0703c1, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x0703e2, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x070401, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x070420, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x07043b, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x07046d, bytes.fromhex("02")),
    (0x070479, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x070488, bytes.fromhex("4ceb04")),
    (0x070498, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x0704b6, bytes.fromhex("eaeaeaeaeaeaeaea")),
    (0x0704eb, bytes.fromhex("5adac2208a1a4aaae220b90000c88f412100b90000c88f422100a9008f402100ebcaf023b90000c8ebcf402100d0fa1a1aeb8f412100b90000c88f422100eb8f402100ebcad0ddeb48c220a302186304a8e22068fafa4cb504")),
    (0x072b13, bytes.fromhex("eb")),
    (0x072b15, bytes.fromhex("ad00d0fae4e66802f0157ef4d00de4f5cbf4d714fcd0f3ab152fef10e72f217ef4d0f8e4f5")),
    (0x072b3c, bytes.fromhex("e4f6cbf4fcd714fcd0eeab152fea")),
    (0x072b55, bytes.fromhex("e4")),
    (0x072b57, bytes.fromhex("ebf7da14ebf4e4f5c4e6cbf46800f0172faa")),
)


def checksum(rom):
    zeroed = bytearray(rom)
    zeroed[CHECKSUM_FIELD : CHECKSUM_FIELD + 4] = bytes(4)
    return (sum(zeroed) + CHECKSUM_FIELD_SUM) & 0xFFFF


def write_checksum(rom):
    stamped = bytearray(rom)
    value = checksum(stamped)
    complement = value ^ 0xFFFF
    stamped[CHECKSUM_FIELD : CHECKSUM_FIELD + 4] = bytes(
        [complement & 0xFF, complement >> 8, value & 0xFF, value >> 8]
    )
    return bytes(stamped)


def patch_bytes():
    return sum(len(data) for _, data in PATCH)


def find_blank_gates(rom):
    found = []
    position = rom.find(BLANK_GATE, 0x070000)
    while position != -1 and position < 0x080000:
        found.append(position)
        position = rom.find(BLANK_GATE, position + 1)
    return found


def is_stock(rom):
    return all(rom[at : at + len(want)] == want for at, want in STOCK_PROBE)


def is_patched(rom):
    return all(rom[at : at + len(data)] == data for at, data in PATCH)


def apply(rom):
    if is_patched(rom):
        return bytes(rom)
    if not is_stock(rom):
        raise ValueError("this is not an unpatched retail Alpha 2 or Zero 2 ROM")

    patched = bytearray(rom)
    for at, data in PATCH:
        patched[at : at + len(data)] = data
    return write_checksum(patched)


def main(argv):
    if len(argv) != 3:
        print("usage: spcfast.py <source-rom> <output-rom>", file=sys.stderr)
        return 2

    source, output = Path(argv[1]), Path(argv[2])
    if source.resolve() == output.resolve():
        print("refusing to patch the source ROM in place", file=sys.stderr)
        return 1

    rom = source.read_bytes()
    patched = apply(rom)
    output.write_bytes(patched)

    print(f"  driver        {DRIVER_BASE + RECEIVE_LOOP:#08x}  two bytes per handshake")
    print(f"  blank gates   {len(find_blank_gates(rom))} sites retired")
    print(f"  patch         {patch_bytes()} bytes in {len(PATCH)} runs")
    print(f"[done] {output} ({len(patched):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
