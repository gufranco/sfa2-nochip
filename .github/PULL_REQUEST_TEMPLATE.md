## What this changes

One or two sentences. What is different afterwards, and why it needed to be.

## How it was checked

Paste the output rather than describing it. A claim that the tests pass is not evidence that they
did.

```text
```

- [ ] `ruff format --check .` and `ruff check .` are clean
- [ ] Every test module runs
- [ ] `python3 doctor.py` reports nothing on this machine
- [ ] Where the dumps are present, `python3 tools/identify.py` and `python3 gate.py` are both clean

## If this changes what an image contains

The retail cartridge is the authority. A change to a stream table, an address, or a patch has to say
which run produced it, because a value that came from anywhere else is a value nobody can act on.

## What it does not carry

- [ ] No cartridge, no stream out of one, and no bytes of either
- [ ] Nothing that says where to obtain them
