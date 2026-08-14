import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


romtools = _load("romtools")

POSITIONS = (0x007FC0, 0x00FFC0)

TITLE_LENGTH = 21
MAP_MODE = 0x15
CHIPSET = 0x16
ROM_SIZE = 0x17
SRAM_SIZE = 0x18
CHECKSUM_COMPLEMENT = 0x1C
CHECKSUM = 0x1E
HEADER_LENGTH = 0x20

CHIPSET_ROM_ONLY = 0x00
CHECKSUM_FIELD_SUM = 0x01FE


def size_byte(length):
    kilobytes = max(1, (length + 1023) // 1024)
    exponent = 0
    while (1 << exponent) < kilobytes:
        exponent += 1
    return exponent


def _looks_like_a_title(image, at):
    if at + HEADER_LENGTH > len(image):
        return False
    title = image[at : at + TITLE_LENGTH]
    return all(0x20 <= byte < 0x7F for byte in title)


def populated_positions(image):
    return [at for at in POSITIONS if _looks_like_a_title(image, at)]


PLAUSIBLE_MAP_MODES = frozenset({0x20, 0x21, 0x23, 0x25, 0x30, 0x31, 0x32, 0x35})


def header_positions(image):
    primary = populated_positions(image)
    if not primary:
        return []

    title = bytes(image[primary[0] : primary[0] + TITLE_LENGTH])
    found = []
    at = image.find(title)
    while at != -1:
        if (
            at + HEADER_LENGTH <= len(image)
            and image[at + MAP_MODE] in PLAUSIBLE_MAP_MODES
        ):
            found.append(at)
        at = image.find(title, at + 1)
    return found


def checksum(image, at):
    positions = header_positions(image)
    zeroed = bytearray(image)
    for position in positions:
        start = position + CHECKSUM_COMPLEMENT
        zeroed[start : start + 4] = bytes(4)
    return (sum(zeroed) + CHECKSUM_FIELD_SUM * len(positions)) & 0xFFFF


def declare_no_coprocessor(image):
    declared = bytearray(image)
    positions = header_positions(image)
    if not positions:
        raise ValueError("no cartridge header found at either documented position")

    for at in positions:
        declared[at + CHIPSET] = CHIPSET_ROM_ONLY
        declared[at + ROM_SIZE] = size_byte(len(image))

    value = checksum(declared, positions[0])
    complement = value ^ 0xFFFF
    for at in positions:
        declared[at + CHECKSUM_COMPLEMENT] = complement & 0xFF
        declared[at + CHECKSUM_COMPLEMENT + 1] = complement >> 8
        declared[at + CHECKSUM] = value & 0xFF
        declared[at + CHECKSUM + 1] = value >> 8

    return bytes(declared)


def report(image):
    for at in header_positions(image):
        title = bytes(image[at : at + TITLE_LENGTH]).decode("ascii", "replace")
        print(
            f"  {at:#08x}  {title!r}  map={image[at + MAP_MODE]:02X} "
            f"chipset={image[at + CHIPSET]:02X} size={image[at + ROM_SIZE]:02X} "
            f"sram={image[at + SRAM_SIZE]:02X}"
        )


def main(argv):
    if len(argv) not in (2, 3):
        print("usage: header.py <image> [output]", file=sys.stderr)
        return 2

    image = romtools.load(Path(argv[1]))
    print("before:")
    report(image)

    if len(argv) == 2:
        return 0

    declared = declare_no_coprocessor(image)
    Path(argv[2]).write_bytes(declared)
    print("after:")
    report(declared)
    print(f"[done] {argv[2]} ({len(declared):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
