"""Compare what the audio processor is actually given, stock against patched.

Two of the patches in this project change how the cartridge feeds the audio
processor. One replaces the sample-upload loop with a faster one. The other skips
an upload entirely when the list being asked for is the one already loaded. Both
are changes to timing and to work avoided, and neither is supposed to change a
single byte of what the audio processor ends up holding.

That is the claim, and it is checkable. The audio processor has its own sixty
four kilobytes of memory, and everything it will ever play lives there: the
driver that was uploaded into it, the directory of samples, and the sample data
itself. If the stock cartridge and the patched one leave that memory in the same
state after the same sequence of inputs, the patch changed how the bytes arrived
and not which bytes arrived, which is exactly what a faster upload is allowed to
do.

So this drives both images through the same deterministic tour, dumps that memory
at the end of each, and compares them byte for byte. A difference is reported as
the runs it falls in rather than as a count, because where a difference sits says
what it is: a handful of bytes low in memory is the driver's own scratch, and a
long run high in memory is sample data that did not arrive.

The four handshake ports and the timer registers are excluded, and the exclusion
is stated rather than quiet. They carry whatever was in flight when the run
stopped, so a comparison that reported them would report a difference between a
build and itself.

Listening is not a test. Two builds can sound identical to a person and differ in
a sample nobody reached, and a person cannot hold sixty four kilobytes in their
head. This can.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

IMAGES = ROOT / "build" / "all"
LOGS = ROOT / "build" / "logs"
DUMPS = ROOT / "build" / "apuram"

IMAGE = "street-fighter-alpha-2-nochip/sfemu:snes9x-1.63"

PORTS = range(0xF4, 0xF8)
TIMERS = range(0xFA, 0x100)
STACK = range(0x0100, 0x0200)
VARIABLES = range(0x0000, 0x0100)

ROSTER = 18
BUDGET = 4000
CART_MAPPING = "-1"
"""A cartridge-form image keeps the stock mapping; only a converted one is windowed."""


def run(image, dump, roster=ROSTER, budget=BUDGET, mapping=CART_MAPPING):
    """Drive one image through the tour and dump the audio processor's memory."""
    LOGS.mkdir(parents=True, exist_ok=True)
    DUMPS.mkdir(parents=True, exist_ok=True)
    image, dump = Path(image).resolve(), Path(dump).resolve()
    log = LOGS / f"audio-{image.stem}.txt"
    with log.open("wb") as handle:
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--network=none",
                "-e",
                "SFTOUR=1",
                "-e",
                f"SFTOURROSTER={roster}",
                "-e",
                f"SFTOURBUDGET={budget}",
                "-e",
                f"SFAPURAM=/work/{dump.relative_to(ROOT)}",
                "-v",
                f"{ROOT}:/work",
                IMAGE,
                str(image.relative_to(ROOT)),
                str(roster * budget),
                mapping,
            ],
            stdout=handle,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    return dump


def runs_of_difference(first, second):
    """Every contiguous stretch where two dumps differ, as start and length."""
    runs = []
    start = None
    for at in range(min(len(first), len(second))):
        if first[at] != second[at]:
            start = at if start is None else start
        elif start is not None:
            runs.append((start, at - start))
            start = None
    if start is not None:
        runs.append((start, min(len(first), len(second)) - start))
    return runs


def volatile(at):
    """Whether an address holds something that differs run to run by design."""
    return at in PORTS or at in TIMERS


def meaningful(runs):
    """The runs that are not explained by the handshake or the timers."""
    return [
        (start, length)
        for start, length in runs
        if any(not volatile(at) for at in range(start, start + length))
    ]


def where(at):
    """What part of the audio processor's memory an address falls in.

    The order matters. The hardware registers live inside the first page rather
    than beside it, so asking whether an address is a port has to come before
    asking whether it is in the page the driver keeps its variables in.
    """
    if volatile(at):
        return "ports and timers"
    if at in STACK:
        return "stack"
    if at in VARIABLES:
        return "driver variables"
    return "driver code or sample data"


def compare(first, second):
    """What differs between two dumps, and whether any of it matters."""
    left = Path(first).read_bytes()
    right = Path(second).read_bytes()
    runs = runs_of_difference(left, right)
    return {
        "sizes": (len(left), len(right)),
        "runs": runs,
        "meaningful": meaningful(runs),
        "bytes": sum(length for _, length in runs),
    }


def report(name, found):
    """What was compared and what came of it, in the order a reader needs it."""
    print(f"  {name}")
    if found["sizes"][0] != found["sizes"][1]:
        print(f"    the two dumps are different sizes: {found['sizes']}")
        return
    if not found["meaningful"]:
        print(f"    identical, ignoring ports and timers ({found['bytes']} volatile bytes differ)")
        return
    print(f"    {len(found['meaningful'])} runs differ, {found['bytes']} bytes in total")
    for start, length in found["meaningful"][:20]:
        print(f"      {start:#06x} for {length} bytes, in the {where(start)}")


def main(argv):
    if len(argv) != 3:
        print("usage: compare_audio.py <stock-image> <patched-image>", file=sys.stderr)
        return 2

    stock, patched = Path(argv[1]), Path(argv[2])
    left = run(stock, DUMPS / f"{stock.stem}.bin")
    right = run(patched, DUMPS / f"{patched.stem}.bin")

    found = compare(left, right)
    report(f"{stock.name} against {patched.name}", found)
    return 1 if found["meaningful"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
