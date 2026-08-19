import sys
from collections import namedtuple
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ROMS = ROOT / "roms"

sys.path.insert(0, str(ROOT))

import hardware  # noqa: E402

try:
    identity = hardware.load("romimage").identity
except hardware.ModelMissing as unchecked:
    raise SystemExit(str(unchecked)) from None

Identity = namedtuple("Identity", "size crc32 md5 sha1 sha256")

NO_INTRO = {
    "sfa2-usa-final.sfc": "Street Fighter Alpha 2 (USA)",
    "sfz2-jp-final.sfc": "Street Fighter Zero 2 (Japan)",
    "sfa2-usa-vc-sound-restored.sfc": "not a retail cartridge, the tagged SNES Classic dump",
}

EXPECTED = {
    "sfa2-usa-final.sfc": Identity(
        size=4194304,
        crc32="9C59DDFF",
        md5="aa3c90fa7d89eb3dc3389a9436bd0cf8",
        sha1="f4ede150b5281f7f5d7e3188c6d9163c2bc66475",
        sha256="910a29f834199c63c22beddc749baba746da9922196a553255deade59f4fc127",
    ),
    "sfz2-jp-final.sfc": Identity(
        size=4194304,
        crc32="7455A7CF",
        md5="70761ab447f48091a8dc437fd2e9c14d",
        sha1="a0db1045fb308d6a2975a4d305b69f877be727a4",
        sha256="f15731675e22dbf3882b777b2d8cd541a637dfdf5d8880c83903cf1e0b64590e",
    ),
    "sfa2-usa-vc-sound-restored.sfc": Identity(
        size=4194304,
        crc32="72A9E2C1",
        md5="058471b547ebc59b43704bca664cb690",
        sha1="dfa7cd6f713c44b6a01a6f91de068eb7ace63676",
        sha256="f8aa2ae1f4bc993092fc282a883ecaf669269c17a175a5f43fa95e9da6459dc0",
    ),
}

OPTIONAL = {"sfa2-usa-vc-sound-restored.sfc"}
COPIER_HEADER = 512


def digests(data):
    return Identity(**identity.measure(data))


def verdict(wanted, found):
    if found.size != wanted.size:
        extra = " and carries a copier header" if found.size - wanted.size == COPIER_HEADER else ""
        return f"size is {found.size:,} not {wanted.size:,}{extra}"
    for field in ("sha256", "sha1", "md5", "crc32"):
        if getattr(found, field) != getattr(wanted, field):
            return f"{field} is {getattr(found, field)}"
    return "ok"


def main(argv):
    wanted_only = argv[1:] or sorted(EXPECTED)
    failed = False
    for name in wanted_only:
        expected = EXPECTED.get(name)
        if expected is None:
            print(f"  {name}: not a file this project reads", file=sys.stderr)
            failed = True
            continue
        path = ROMS / name
        if not path.exists():
            note = (
                "optional, only needed to regenerate the USA table"
                if name in OPTIONAL
                else "MISSING"
            )
            print(f"  {name}: {note}")
            failed = failed or name not in OPTIONAL
            continue
        answer = verdict(expected, digests(path.read_bytes()))
        print(f"  {name}: {answer}  [{NO_INTRO[name]}]")
        failed = failed or answer != "ok"
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
