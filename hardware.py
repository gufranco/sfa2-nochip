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

The third consequence is the one that reaches whoever clones this. A submodule is
a pinned commit, not content, so `git clone` on its own leaves six named but empty
directories behind. Everything here imports through `load()`, so `load()` is where
that has to be said, rather than leaving a bare import error to stand in for the
explanation.
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


class ModelMissing(Exception):
    """A model is pinned here but its submodule was never checked out."""


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


def is_checked_out(package):
    """Whether a pinned model has content and not just a directory."""
    directory = root_of(package)
    return directory.is_dir() and any(directory.iterdir())


def missing_models():
    """Every model that is pinned here and not checked out."""
    return [package for package in PACKAGES if not is_checked_out(package)]


def checkout_message(missing):
    named = ", ".join(sorted(missing))
    subject = "model is" if len(missing) == 1 else "models are"
    return (
        f"the {named} {subject} pinned here but not checked out. "
        "A submodule is a pinned commit rather than content, so a plain git clone "
        "leaves the directory empty and nothing here can import.\n"
        "    git submodule update --init --recursive\n"
        "fixes an existing clone. A fresh one wants: "
        "git clone --recurse-submodules <url>"
    )


def load(package):
    """A model, by the name it is published under."""
    if not is_checked_out(package):
        raise ModelMissing(checkout_message(missing_models()))
    install()
    return importlib.import_module(package)
