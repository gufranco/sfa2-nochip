"""Put the hardware models this project is checked against on the import path.

The models used to live in this repository as loose modules, imported by file
path. They are now separate repositories, pinned here as submodules, so that the
thing this project is measured against is measured itself: the processor and the
audio processor each against a per-opcode suite, the decompressor against the
chip's own reference implementation, and the cartridge map and the image handling
against a library of real cartridges.

Two consequences are worth stating, because both change what code here must do.

The models start unclean. Their memory and registers hold arbitrary but
reproducible values rather than zeroes, because hardware does. Anything here that
relied on a register being zero without setting it was relying on the model being
tidier than the machine, and now has to say what it wants.

The audio mixer is pinned even though nothing here has used it yet. That is
deliberate rather than speculative: the sample-upload and repeat-load patches
change what reaches it, and a patch to audio code that is never played through a
model of the thing that plays it has been checked for shape and not for effect.

And nothing is loaded by file path any more. `load()` returns a model by the name
it is published under, which reads the same way at the top of a module as the
file-path helper it replaces and does not need an import to be moved below a
statement to work.
"""

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

EMULATORS = ROOT / "emulators"

PACKAGES = {
    "mos65xx": "mos65xx",
    "spc700": "sony-spc700",
    "sdd1": "snes-sdd1",
    "sdsp": "sony-s-dsp",
    "mapper": "snes-mapper",
    "romimage": "snes-rom-image",
}
"""The package each submodule provides, and the directory it lives in."""


class UnknownPackage(Exception):
    pass


def root_of(package):
    """Where a vendored model lives, by the name it is imported under."""
    directory = PACKAGES.get(package)
    if directory is None:
        raise UnknownPackage(
            f"{package} is not vendored here; this project carries {', '.join(sorted(PACKAGES))}"
        )
    return EMULATORS / directory


def install():
    """Make every vendored model importable, without stacking the path."""
    for package in PACKAGES:
        entry = str(root_of(package))
        if entry not in sys.path:
            sys.path.insert(0, entry)


def load(package):
    """A model, by the name it is published under."""
    root_of(package)
    install()
    return importlib.import_module(package)
