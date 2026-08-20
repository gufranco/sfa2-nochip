# Contributing

## The short version

Evidence over assertion. A change that claims something is correct carries the run that shows it,
and a claim that cannot be checked is not ready.

## Before you open a pull request

Run every gate, and read the output rather than the exit code:

```bash
uvx ruff@0.16.3 format --check .
uvx ruff@0.16.3 check .
pnpm install --frozen-lockfile && pnpm run format:check
for module in *.test.py tools/*.test.py; do python3 "$module" || echo "FAILED $module"; done
python3 doctor.py
```

Every model this project measures itself against lives in its own repository and is pinned here as
a submodule at the root. `python3 doctor.py` reports the whole chain, including each model's own
report and the digest of every dump it found, and it is the first thing to paste into an issue.

## What the parts are checked against

The retail cartridge is the only oracle for what the game contains, and every dump this project
reads is checked against a published digest before a byte of it is used. `python3 tools/identify.py`
is that check; it names what is wrong rather than only that something is.

The decompressor is held to an independent encoder rather than to its author's confidence, and the
processor and audio parts each to their own suites. All of them live in their own repositories and
are pinned here at the root.

## Tests

A test file sits beside the module it covers and is named after it. Test bodies carry no comments:
arrange, act and assert are separated by one blank line each, and the test name says what behaviour
is being pinned.

A test never needs a cartridge. Where a check needs one, the data is passed in, the tests pass a
stand-in, and the run against a real dump is a script rather than a test. That is what keeps the
suite meaningful on a machine that holds none.

## Commits

Conventional Commits, subject under fifty characters, imperative mood. The body explains what
changed and why, wrapped at seventy two columns. Releases are cut by semantic-release from those
subjects, so the type is what decides the version.

## What will be sent back

- A file nobody can legally redistribute: a cartridge, a stream out of one, or any bytes of either.
- A number in a document that no run produced.
- A behaviour changed without the recorded traffic or the pinned digests moving with it.
- A test that asserts what the code does rather than what the hardware does.
- A stream table changed without the run that produced it.

## Conduct

The [Code of Conduct](CODE_OF_CONDUCT.md) applies wherever this project is discussed. One line of it
is specific to this repository and worth reading twice: never post a copyrighted image, a game, or a
link to somewhere either can be downloaded. A digest identifies a file without carrying it, and a
digest is all anybody needs.

## What is welcome without asking

Measurements. A run against a region or a revision this has not been run against, a disagreement
between the rebuilt cartridge and the retail one, or a result from hardware nobody here has. A
recording of what really happened is worth more than an argument about what should.
