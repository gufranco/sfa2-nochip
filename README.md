# Street Fighter Alpha 2 without the S-DD1

Removing the S-DD1 decompression chip from Street Fighter Alpha 2 (USA) and Street Fighter Zero 2
(Japan), so both run from a plain flash cartridge. The pre-fight pause gets fixed on the way past.

I started this in 2021 and finished it in 2026. Most of that was not work, it was the thing sitting
there while I did other things, but the calendar is the calendar.

This is the full record: what I tried, what failed, how I worked out why, and what the numbers said. I
have tried to write it so someone who has never opened a SNES ROM can follow along, without cutting the
details that actually mattered.

---

## TL;DR

Street Fighter Alpha 2 keeps most of its graphics compressed. A chip in the cartridge, the S-DD1,
decompresses them during DMA, on the fly, as the game asks for them. No chip, no graphics. Flash
cartridges do not have one.

So: decompress every stream in advance, lay the results out in a bigger ROM image, and patch the game
so that when it asks the chip for a compressed stream it reads the finished bytes instead. What comes
out is a 96 Mbit image that needs no chip.

The pause before every fight, about 2.6 seconds, turned out to have nothing to do with the chip. It is
the sound driver feeding samples to the audio chip one byte per handshake. Rewriting the receiving loop
and carrying two bytes per handshake takes it to 0.78 seconds.

Shin Akuma came almost free. He has been sitting in the retail cartridge since 1996 behind a cheat
nobody wrote down until 2021, and unlocking him is a two byte change.

The images also tell the truth about themselves now, chipset `$00` and their real size, instead of
repeating the retail header's claim to a chip they no longer contain. That sounds like housekeeping. It
is not: it is the first of two reasons no emulator can load these conversions today.

### Building it, in short

You supply the retail ROM. Nothing here contains game data.

```
# 1. patch the retail cartridge: faster sample upload, then Shin Akuma
python3 spcfast.py   roms/sfa2-usa-final.sfc build/step1.sfc
python3 shinakuma.py build/step1.sfc         build/step2.sfc

# 2. redirect the seven places that ask the chip to decompress
python3 build.py asm/sdd1-bypass.asm build/step2.sfc bypass.sfc

# 3. and 4. decompress every stream, lay out the 96 Mbit image, declare it honestly
python3 pack.py usa
```

Steps 1 and 2 alone give a patched retail cartridge that still needs the chip but loses the pause. All
four give the chip-free 96 Mbit image. Order matters, and section 21 explains why.

For Street Fighter Zero 2, `python3 pack.py jp`. Both regions build from the retail cartridge alone:
the stream tables are frozen into [`usastreams.py`](usastreams.py) and [`jpstreams.py`](jpstreams.py).

**Status:** the USA builds run on real hardware, the 96 Mbit chip-free image on a Game Doctor SF7 and
both that image and the 4 MB patched cartridge on an FXPAK Pro. The Japanese build is still settling:
its stream table is recovered by observation rather than read from a tagged dump, and every screen that
had never been driven kept exposing another missing stream. Section 15 is the record of that, including
the theory that turned out to be wrong.

---

## Contents

1. [Where this came from](#1-where-this-came-from)
2. [The problem](#2-the-problem)
3. [Ground rules](#3-ground-rules)
4. [Dead ends worth recording](#4-dead-ends-worth-recording)
5. [The decompressor](#5-the-decompressor)
6. [What Star Ocean taught me](#6-what-star-ocean-taught-me)
7. [Finding the streams](#7-finding-the-streams)
8. [The Game Doctor image format](#8-the-game-doctor-image-format)
9. [Rebuilding the ROM](#9-rebuilding-the-rom)
10. [The bypass patch](#10-the-bypass-patch)
11. [Making it boot](#11-making-it-boot)
12. [Emulator work](#12-emulator-work)
13. [The pre-fight pause](#13-the-pre-fight-pause)
14. [Shin Akuma](#14-shin-akuma)
15. [The Japanese build that never worked](#15-the-japanese-build-that-never-worked)
16. [Declaring the cartridge honestly](#16-declaring-the-cartridge-honestly)
17. [Validation](#17-validation)
18. [What is not verified](#18-what-is-not-verified)
19. [Lessons](#19-lessons)
20. [Upstream contributions](#20-upstream-contributions)
21. [Reproducing this](#21-reproducing-this)
22. [Repository guide](#22-repository-guide)
23. [Acknowledgements](#23-acknowledgements)
24. [References](#24-references)

---

## 1. Where this came from

**TL;DR.** A video in 2021 asked why Alpha 2 pauses before every fight and why it needed a special
chip. I wanted to answer both by building the cartridge that does not need one.

In March 2021 Modern Vintage Gamer published
[A closer look at Street Fighter Alpha 2 on the Super Nintendo](https://www.youtube.com/watch?v=fB9GlZUYNUQ).
Two things in it stuck with me. Capcom fit a CPS2 arcade game into a 32 Mbit cartridge by compressing
the graphics and shipping a chip to decompress them. And the pause before each fight, the one everybody
who owned this game remembers, is not the chip at all. It is the sound.

The video also pointed at [gizaha's patches](https://www.zeldix.net/t1831-street-fighter-alpha-2) on
Zeldix, which fix the pause among a long list of other things, and at the fact that Shin Akuma had been
sitting in the cartridge for twenty five years without anyone noticing.

My question was narrower than gizaha's. Could the chip come out completely, so the game runs from a
flash cartridge? I had a Game Doctor SF7 with 128 Mbit of DRAM, which set the size budget and made the
whole thing concrete rather than academic.

Then it sat. I would pick it up, get somewhere, hit something I could not explain, and put it down
again. The decompressor came early and was easy, because the algorithm is documented. Everything after
that was addressing, and addressing is not documented anywhere. The Japanese build in particular was
quietly broken for most of those five years and I did not know it, which is section 15.

---

## 2. The problem

**TL;DR.** The S-DD1 decompresses graphics mid-DMA. Take it away and the game happily sends compressed
bytes to video memory and draws noise. Everything else in the cartridge is completely ordinary.

Alpha 2 is a 32 Mbit LoROM cartridge with an S-DD1 soldered on. The chip does two things, and only two.

It maps memory. Registers `$4804` to `$4807` choose which megabyte of ROM appears in each of the bank
groups `$C0`-`$CF`, `$D0`-`$DF`, `$E0`-`$EF` and `$F0`-`$FF`. Alpha 2 never writes them, so the mapping
sits at its power-on default and banks `$C0`-`$FF` expose the 4 MB linearly. Convenient, and it means
that half of the chip can be ignored.

And it decompresses. When the CPU writes something non-zero to `$4801` and kicks off a DMA whose
channel has a fixed A-bus address, bit 3 of `$43x0`, the chip steps in front of the transfer. Rather
than reading raw bytes out of ROM it decodes a stream and hands the decoded bytes to whatever the DMA
was pointed at, usually video memory. `$4801` clears itself afterwards, so the game re-arms it before
every single stream.

That is the entire contract. The CPU code, the sound driver, the uncompressed data, all of it is
ordinary SNES with no idea anything unusual is happening.

Which reduces the project to three questions:

1. Can I decompress the streams myself, exactly?
2. Where are they, and how big is each one once decompressed?
3. Can I make the game read the decompressed data instead, with no chip present?

The answers, in the order they cost me effort, were yes, sort of, and yes.

---

## 3. Ground rules

**TL;DR.** If I claim it here, I measured it. Analysis is Python with tests beside it. Code that goes
into the ROM is assembly, commented far past what anyone would normally tolerate. Builds run in
containers.

I set a few rules early, mostly out of self-defence, and they are the reason this converged instead of
turning into a pile of half-remembered guesses.

The first is that I do not believe anything I have not measured. Every number in this document has a
command behind it. When a measurement contradicted something I already believed, the belief lost, and
several of those reversals are written up here including the ones that make me look slow.

Analysis lives in Python with tests next to each module, 19 of them and 281 tests. That is not
ceremony. More than once a failing test was the first sign an assumption had rotted, and twice the test
turned out to be wrong rather than the code, which I have left in the record because it is the more
useful failure of the two.

Code that ends up inside the ROM is assembly, and I comment it to a degree that would be absurd
anywhere else. Every routine states its entry and exit register state, including the M and X width
flags. Every hardware register gets named. Every address I recovered by reverse engineering carries a
note on how I found it, because an address like `$C0:EC6E` means nothing six months later without the
sentence explaining that it turned up by searching for a joypad bit pattern.

Builds run in Docker and never on my machine. [`asm/Dockerfile`](asm/Dockerfile) pins asar and builds
it from source; [`emu/Dockerfile`](emu/Dockerfile) pins snes9x 1.63 and checks the S-DD1 source by
sha256 before compiling anything. No network, non-root, and the source ROM is never patched in place.

And the last one, which is why a Star Ocean section exists in a Street Fighter project: I do not trust
the decompressor until it reproduces something known good.

---

## 4. Dead ends worth recording

**TL;DR.** Four shortcuts, all closed before the real work started. One of them handed me the most
interesting fact in the whole project: the port ran without the chip in September 1996.

Negative results are cheap to leave out and expensive for the next person to rediscover, so here they
are.

### The prototype is not a source of uncompressed art

There is a prototype dated 1996-09-15 that does not use the S-DD1. The obvious hope, and I did hope
it, was that it holds the graphics uncompressed and I could skip the hard part entirely.

It does not. Only **14.7%** of the prototype's data shows up in the final build. It is an earlier
revision with different content, not an uncompressed copy of the game that shipped. That was the most
attractive shortcut on the table and it closed hard.

What it gave me instead was worth more. **The port ran without the S-DD1 in September 1996.** The chip
was a late decision to save space, not something the engine was built around. That is not a hint that
removal might work, it is evidence that it already did once.

### Star Ocean's conversion is not transferable

Only the technique carries. Its relocation map, its code patches, its assets, all of it belongs to Star
Ocean's engine. What I got from it was the addressing rule in section 6 and an oracle to check my
decompressor against, which is a lot, but not one reusable line.

### The existing Alpha 2 patch cannot work on hardware

DarkAkuma's `WUP-JCGE` package gets described as a chip-free Alpha 2. It is not. It is an emulator
hook: the ROM carries a tag that Canoe recognises, and nothing in the ROM itself does the substitution.
On real silicon there is no chip, no replacement code, just a tag nobody reads.

I did not assume this. ikari_01, who writes the sd2snes firmware, reached the same conclusion by
inspecting the patch, DarkAkuma confirmed it himself, and people who tried it on an sd2snes got a black
screen. Same family as the ZSNES-era graphics packs.

It turned out to matter enormously to me anyway, for a reason nobody intended: the `SDD1` marker tags
it embeds are the complete USA stream map. That is section 7.

### Byte-scanning for register writes does not work

I tried counting `8D xx 48` style opcode patterns to find the S-DD1 register writes. It finds **more
hits in the patched Star Ocean, 316, than in the original, 252**, because graphics data contains those
byte sequences by accident. Any real register analysis needs a disassembler that follows code paths and
can tell code from data, which is why [`wdc65816.py`](wdc65816.py) and [`sdd1sites.py`](sdd1sites.py)
exist at all.

---

## 5. The decompressor

**TL;DR.** I reimplemented the S-DD1 algorithm in Python and proved it byte-identical to the reference
C implementation by running both against each other inside a container.

Andreas Naive reverse engineered this algorithm, and every serious SNES emulator implements it. Five
pieces work together: an input manager feeding bits from the stream, a Golomb-code decoder turning bit
runs into values, a probability estimator that adapts as decoding proceeds, a context model choosing
which probability state applies based on what has already been decoded, and output logic reassembling
bitplanes into the order video memory expects.

Four bitplane modes and four context configurations, all selected by the first byte of the stream:

```python
header = rom[offset]
bitplane_type = header >> 6
high_mask, low_mask = CONTEXT_MASKS[(header >> 4) & 3]
stream = ((header << 11) | (rom[offset + 1] << 3)) & 0xFFFF
valid = 5
pos = offset + 2
```

That is [`sdd1.py`](sdd1.py). I did not type the lookup tables by hand. They are extracted
programmatically from snes9x's `sdd1emu.cpp`, which removes an entire category of mistake I would
certainly have made.

### Proving it correct

A decompressor that is subtly wrong produces plausible garbage, and plausible garbage is exactly what
you get when a graphics decoder goes slightly astray. "It looks right" was never going to be good
enough, so I proved it three ways.

The first is a differential test. [`sdd1ref.py`](sdd1ref.py) builds a container holding snes9x 1.63's
actual `sdd1emu.cpp`, verified by sha256, wraps it in a small driver and compares its output against
mine. They agree byte for byte across 400 random offsets, all 16 header configurations, and a full
64 KB block.

The second falls out of the map. If both the map and the decompressor are right, each stream's
compressed data should end exactly where the next one starts. 91.7% pack exactly. I did not wave the
other 8% away: it resolves into 2,578 packed exactly, 125 where the map declares more bytes than the
stream actually consumes, and 108 padded to a bank boundary, which accounts for all 2,811.

The third is Star Ocean, which is the next section.

---

## 6. What Star Ocean taught me

**TL;DR.** Star Ocean is the only other S-DD1 game, and someone already converted it to run without
the chip. I used it twice: as ground truth for my decompressor, and, far more importantly, as the
source of the addressing rule this entire project rests on.

It is the only other cartridge with an S-DD1 in it. At 48 Mbit it becomes 96 Mbit once the graphics
come out compressed, and a chip-free conversion of it has been circulating for years.

I treated that conversion as more than a curiosity. It is somebody else's finished answer to my exact
problem, and I got two things out of taking it apart.

### It checked my decompressor against real data

I decompressed Star Ocean's streams with [`sdd1.py`](sdd1.py) and compared the result against the
chip-free build: 185,919 bytes reproduced exactly, at 8 KB aligned destinations. That is a better test
than my synthetic one, because these are real streams with real header variety, and because the
expected output came from an implementation that has nothing to do with mine.

### It showed me how a 96 Mbit image is addressed

This is the part that unlocked everything.

A 4 MB LoROM cartridge maps cleanly, 32 KB per bank at `$8000`-`$FFFF`. A 12 MB image cannot, because
there are not enough banks to go round. Star Ocean's conversion solves it with a rule I could not find
documented anywhere, so I recovered it by inspection and then tested it by prediction.

For an image of `N` 64 KB banks:

```python
BANK = 0x10000
HALF = 0x8000


def snes_to_file(bank, addr, banks):
    if addr < HALF:
        return (bank + banks) * HALF + addr  # low half lives a whole ROM away
    return bank * HALF + (addr - HALF)  # high half is plain LoROM
```

The high half of each bank is where LoROM would put it. The low half of each bank lives `N` half-banks
further into the file. So the file is two interleaved halves.

Banks `$C0` and above follow a second rule, because that is where the window lives:

```python
WINDOW_FIRST_BANK = 0xC0
WINDOW_LOW_BASE = 0x80
WINDOW_HIGH_BASE = 0x00


def window_to_file(bank, addr, banks):
    offset = bank - WINDOW_FIRST_BANK
    base = WINDOW_LOW_BASE if addr < HALF else WINDOW_HIGH_BASE
    return (base + offset + banks) * HALF + (addr & (HALF - 1))
```

Prediction rather than curve-fitting is the point here. I worked out that the code Star Ocean runs at
`$C0:4D6A` should sit at file offset `0xA04D6A`, went and looked, and it does. That is
[`layout.py`](layout.py), 18 tests.

When a problem has been solved before, the previous solution is a specification, not just
inspiration. Most of the difficulty here was not the compression, which was documented, but the
addressing, which was not.

---

## 7. Finding the streams

**TL;DR.** The USA map came free from an existing patched ROM that tags every stream. The Japanese map
had to be recovered the hard way and was still incomplete two years later, which caused the single
worst bug in the project.

Decompressing a stream requires knowing where it starts and how many bytes it should produce. The
length matters: the S-DD1 decodes until the requested byte count is reached, so different lengths from
the same start produce different amounts of consumed input.

### Content search, and why I abandoned it

[`sdd1find.py`](sdd1find.py) hunts for streams by decompressing at candidate offsets and asking whether
the output looks like graphics. Against the known USA map it scores **100% precision and 14% recall**.
The recall ceiling is not a bug I could fix: most streams open on a blank tile, and you cannot find a
run of zeroes by looking at its content.

### The USA map, handed to me

A file I had sitting around as `sfa2-usa-vc-sound-restored.sfc` turned out to be DarkAkuma's patched
ROM for the SNES Classic, and it carries `SDD1` marker tags at every stream so that the SNES Classic's
own decompressor can find them. [`sdd1map.py`](sdd1map.py) just reads them: **2,815 streams, 4,947,202
bytes decompressed**. Complete, authoritative, no guessing. I did not earn that one.

### The Japanese map, the hard way

Nothing equivalent exists for Zero 2. The map I used for years was recovered heuristically and had
**2,801 streams** in it. It was wrong the whole time. Section 15 is how I found out.

The table, [`jpstreams.py`](jpstreams.py), holds **2,855 streams**, against 2,815 in the tagged USA
dump. The count moved eleven times before it settled, and every move came from reaching a screen nobody
had reached before. The rest of this section is that story, including a theory of mine that was wrong
and did real damage.
[`mapcheck.py`](mapcheck.py) validates any map offline: no duplicate sources, every stream decodes, and
the worst key-scan distance stays inside budget.

---

## 8. The Game Doctor image format

**TL;DR.** The flash cartridge expects the file split into two interleaved halves. It was derived from
Star Ocean's conversion and confirmed by that build booting.

A 4 MB LoROM cartridge stores 32 KB per bank and the file is simply those banks end to end. A 12 MB
image cannot work that way, because the address space does not have room: 192 banks of 64 KB is more
than the 256 banks the 24-bit address space provides once mirrors and work RAM are accounted for.

The layout described in section 6 solves it by splitting every bank in two and storing the halves in
separate regions of the file:

```
file offset 0                     banks' upper halves, in order
file offset banks * 0x8000        banks' lower halves, in order
```

So for a 192-bank image, the upper half of bank 3 is at `3 * 0x8000`, and its lower half is at
`(192 + 3) * 0x8000`. [`layout.py`](layout.py) implements both directions:

```python
def snes_to_file(bank, addr, banks):
    if addr < HALF:
        return (bank + banks) * HALF + addr
    return bank * HALF + (addr - HALF)
```

`interleave` and `deinterleave` convert whole images, and their tests assert the pair round-trips on the
real Star Ocean build rather than on synthetic data.

### Why the window banks are the interesting part

Banks `$C0` and above do not follow that rule. They are a **window**, and their contents are assembled
from the lower halves of two other banks:

- the upper half of `$C0+k` comes from the lower half of bank `k`
- the lower half of `$C0+k` comes from the lower half of bank `$80+k`

This is what makes the format unlike any standard SNES mapping, and it is why an emulator cannot serve
these images by deinterleaving the file and applying an existing map. The window aliases content that
other banks also expose, which is how 192 banks of storage cover a 256-bank address space, and it is
the specific rule quoted in the upstream issue in section 20.

### How I confirmed it

Not with a unit test. I used the arithmetic to predict where Star Ocean's code at `$C0:4D6A` should
land in the file, said `0xA04D6A` out loud, and went to look. The better confirmation came later, when
Star Ocean's chip-free build booted to its name entry screen under an emulator that had been taught
this mapping and nothing else.

---

## 9. Rebuilding the ROM

**TL;DR.** [`rombuild.py`](rombuild.py) produces the 96 Mbit image: original ROM in the window banks,
decompressed graphics packed into free banks, and four lookup tables the patch uses to translate
addresses.

[`rombuild.py`](rombuild.py), 20 tests, assembles the image:

| region | contents |
|--------|----------|
| banks `$00`-`$3F` | the original ROM's LoROM view |
| banks `$40`-`$7D` | decompressed graphics |
| banks `$60`-`$63` | four lookup tables, overwriting graphics space |
| banks `$7E`-`$7F` | reserved, this is work RAM |
| banks `$80`-`$BF` | FastROM mirror of `$00`-`$3F` |
| banks `$C0`-`$FF` | the original 4 MB ROM, linear, as the window |

The decompressed graphics need about 5 MB and the free banks do not hold that, so once a stream has
been decompressed I reclaim the compressed bytes it came from in the window banks. `reclaimed_regions`
works out each stream's real extent by decompressing it and taking the input position it reached:

```python
consumed = sdd1.decompress(rom, entry.source, entry.length).end - READ_AHEAD
end = min(consumed, (entry.source | 0xFFFF) + 1)
```

The word doing the work there is real. Getting that wrong cost me the title screen, in section 11.

### The lookup tables

The patch must translate a compressed source address into the address where the decompressed bytes
were placed. It does this with four 64 KB tables in banks `$60`-`$63`, indexed by the low 16 bits of
the source address:

| bank | contents |
|------|----------|
| `$60` | the source bank byte, used as the key |
| `$61` | destination low byte |
| `$62` | destination high byte |
| `$63` | destination bank |

Two streams can share the same low 16 bits if they live in different banks, so
[`sdd1tables.py`](sdd1tables.py) puts a colliding key at the first free slot at or after its address,
and the lookup scans forward until the key byte matches the source bank. `allocate` has a repair loop,
and `verify` proves that every stream's scan lands on its own slot and nobody else's. Median scan
distance is 0 in both regions, worst case 31.

I had no idea at the time that this number would later be the thing that cracked section 15.

---

## 10. The bypass patch

**TL;DR.** Seven places in the game arm the chip. Each is replaced with a call to a routine that looks
up where the decompressed data was placed, rewrites the DMA source, and clears the bit that would have
triggered decompression.

[`sdd1sites.py`](sdd1sites.py) finds every write to `$4801` that is not inside compressed data. There
are exactly seven in each region:

```
USA  $00:8482  $00:885A  $00:8881  $00:F7BF  $25:BBD3  $35:E002  $35:E131
JP   $00:847E  $00:8856  $00:887D  $00:F7BF  $25:C54A  $35:E002  $35:E131
```

Three sit at the same address in both regions. Four moved, because the code in front of them differs
between the builds.

They are not interchangeable. Each one programs the DMA differently, and the replacement at each has to
preserve whatever the original instructions were doing:

| site | what it is | channel |
|------|-----------|---------|
| `$00:8482` | the VRAM queue at `$0300,x`, the main graphics path | 0 |
| `$00:885A` | source taken from direct page `$18`/`$1a` | 0 |
| `$00:8881` | a continuation transfer, bank+1 and address 0 | 0 |
| `$00:F7BF` | a table-driven helper, channel offset arrives in Y | variable |
| `$25:BBD3` | into work RAM, parameters at `$C8:F017` | 1 |
| `$35:E002` | into work RAM | 7 |
| `$35:E131` | into video RAM | 0 |

The variable-channel site is why the routine has four entry points rather than one: three fixed
channels and one that reads the channel from Y.

Each site is replaced with a call to the shared routine in
[`asm/sdd1-translate.asm`](asm/sdd1-translate.asm). Its core:

```asm
    lda.l !SRC_ADDR+<channel> : tay      ; Y = the DMA source address
    sep #$20
    lda.l !SRC_BANK+<channel>            ; A = the source bank
    pea $6060 : plb : plb                ; data bank = $60, the key table
?scan:
    cmp $0000,y : beq ?found             ; scan forward for our bank byte
    iny : bra ?scan
?found:
    phy : tyx
    lda.l !TABLE_LOW,x  : sta.l !SRC_ADDR+<channel>
    lda.l !TABLE_HIGH,x : sta.l !SRC_ADDR+1+<channel>
    lda.l !TABLE_BANK,x : sta.l !SRC_BANK+<channel>
    lda.l !DMAP+<channel> : and #$F7 : sta.l !DMAP+<channel>   ; clear fixed A-bus
```

That last line is the one that matters. Clearing bit 3 of the DMA parameter register turns the
transfer back into an ordinary incrementing read, which is what you need when the bytes are already
decompressed.

The routine lives in filler space, `$35:CD84` in the USA ROM and `$35:D700` in the Japanese one, where
`$35:CD84` holds real data.

### Testing ROM code without an emulator

Assembly that runs on a console is miserable to test. The usual answer is to boot the whole game and
look at the screen, which tells you that it broke and nothing about where.

[`patchrun.py`](patchrun.py) does something narrower. It takes the **actual assembled machine code**
out of the built ROM and executes it against a memory model, using [`emu65816.py`](emu65816.py), a
minimal 65816 interpreter covering the roughly 28 opcodes the patch uses. The memory model maps SNES
addresses to file offsets through [`layout.py`](layout.py), so the routine reads the real lookup tables
out of the real image, and it records a snapshot when the code writes the DMA trigger at `$420B`.

A test can then assert the thing that actually matters: given this compressed source address in the DMA
registers, the routine leaves the translated destination in those registers and clears the fixed A-bus
bit. That is checked for each of the four entry points, `$35:CD84`, `$35:CDD0`, `$35:CE1C` and the
variable-channel `$35:CE68`, without launching an emulator or a game.

The interpreter is where the M and X width flags earned their own naming argument. They were first
called `x_wide`, which turned out to mean the opposite of what it said, and two tests were wrong
because of it. Renaming them `m8` and `x8`, stating the width directly, ended the confusion.

### Two bugs caught by reading the assembler's output back

Both were found by disassembling the assembled ROM rather than trusting the source, a habit that paid
for itself repeatedly.

**`pea $0000` sets the data bank to `$00`, not `$60`.** The instruction pushes a 16-bit value and the
two `plb` instructions each pop one byte, so the pushed value must have the target bank in both bytes.
Corrected to `pea $6060`.

**A stray `plb` ate a byte of the saved Y register.** Removed, because the data bank stays `$60` and
every later access uses long addressing anyway.

---

## 11. Making it boot

**TL;DR.** Three failures, each diagnosed by measurement rather than inspection. The last one is the
most instructive: video memory was already perfect and the bug was in data the CPU reads directly.

### Stuck at `$C0:0032`

The first build hung on the spot. I built a variant with no hooks in it at all, expecting that to work
and narrow things down, and it failed in exactly the same place. So the hooks were innocent and the
layout was the problem. Banks `$80`-`$BF`, the FastROM mirror the game actually executes from, were
full of zeros. [`rombuild.py`](rombuild.py) gained `LOROM_MIRROR_BASE` and now writes both views.

### The title screen, off by 8,942 pixels

Almost right, which is far worse than obviously wrong. I killed four theories in turn: reading past the
end of a stream, continuation into `bank+1:0000`, mirroring of banks `$60`-`$7F`, and banks
`$40`-`$5F`. Then I chased a fifth that was my own fault. Twelve transfers from `$00:FFAE` looked like
S-DD1 work because they had the fixed A-bus bit set, and I spent a while on them. They are a video
memory fill. I had quietly decided that `fixed=1` meant S-DD1, when the chip also needs `$4801` armed.

The break came from a per-bank read counter. Bank `$40`-`$5F` was never read at all, and bank `$DD`
was read 9,996 times fewer than on the retail cartridge.

`reclaimed_regions` was freeing the gap between stream markers instead of each stream's real extent.
The surplus bytes held sprite layout tables that the CPU reads directly, never through DMA. Which is
precisely why video memory and palette memory already matched perfectly: the graphics path was fine
the whole time, and the corruption sat on a path that no amount of comparing graphics could reveal.

Fixing the extent calculation took it to zero differing pixels.

The lesson I took: when two things that should differ do not, the bug is on a path you are not looking at.

### A test that encoded a disproved theory

One test asserted that 90% of streams were adjacent, left over from the read-past theory I had already
disproved. A passing test resting on a false premise is worse than no test, so I changed the threshold
to what the allocator actually achieves.

---

## 12. Emulator work

**TL;DR.** No emulator can load a 96 Mbit image in this layout, so I taught one. Separately I built a
lot of instrumentation purely to find bugs, which is development-only and stays here.

### The part needed to run the ROMs

snes9x cannot load these images. It sees a 12 MB file with a LoROM header and maps it as best it can,
which is wrong in the low half of every bank and wrong across the entire `$C0`-`$FF` window.

[`emu/main.cpp`](emu/main.cpp) has `install_game_doctor_map`, which rewrites `Memory.Map` after load
following the rules in section 6. Two things caught me out beyond the addressing itself:

The emulated S-DD1 has to be switched off. snes9x's chip rewrites the `$C0`-`$FF` mapping whenever
`$4804`-`$4807` are written, and on a chip-free build those writes must not remap anything. Star Ocean's
conversion stayed garbled after the logo until I set `Settings.SDD1 = FALSE`.

And banks `$7E` and `$7F` have to be left alone. They are work RAM, not ROM, and remapping them is an
easy way to lose an afternoon.

This is the change that would let anyone run these images in snes9x, and it is what I eventually took
upstream in section 20.

### The part that exists only for diagnosis

None of this is needed to play the game. All of it was needed to find the bugs, and I am documenting it
because none of the diagnoses in this file can be reproduced without it.

| instrumentation | what it answered |
|-----------------|------------------|
| DMA trace with the triggering program counter | which transfers happen, from where, and in what order |
| per-bank read counters | which banks the CPU actually reads, which broke the title screen case |
| APU port write counters keyed by program counter | which code paths talk to the sound chip |
| SPC700 program counter sampling | whether the boot ROM or the game's own driver was receiving |
| APU RAM dump | recovering the running sound driver for disassembly |
| per-block sample verification | comparing every uploaded block against its ROM source |
| lookup scan logging | the address each translation asks for and how far it walks |
| frame brightness sampling | whether the game is still drawing |
| closed-loop input driver | steering menus toward a character |

The instruments themselves taught me two things, both the hard way.

Reading memory through the emulator's own accessor perturbs the run. I had a probe reading work RAM
every frame, and it changed open-bus behaviour enough to shift timing. It cost me a whole validation
matrix and skewed a map harvest before I noticed. It now reads the RAM array directly and only runs when
its environment variable is set.

Instruments can also interfere with each other. Running the block verifier alongside the frame counter
changed the frame count, because the verifier's reads had side effects of their own. I now collect
metrics that interact in separate runs.

---

## 13. The pre-fight pause

**TL;DR.** The pause is the sound driver taking samples one byte per handshake, and the slow loop is on
the audio chip rather than the CPU, which is not where I expected to find it. Rewriting it and carrying
two bytes per handshake takes 2.60 seconds down to 0.78.

### Measuring it

With the APU write ports instrumented, one pre-fight burst on the retail USA cartridge comes to **184
frames, 3.07 seconds, 47,915 bytes**. That is 15.3 KB/s, or 260 bytes per frame against 262 scanlines.
One byte per scanline, which is a suspiciously round result and the first clue that something is
synchronised to the display. The 12,000 frame runs used for the final matrix show a longest burst of
2.60 seconds; the difference is just which burst a given run happens to catch.

The CPU half of the transfer looks like this:

```
C70491  xba
C70492  lda $0000,y      next sample byte
C70495  iny
C70496  xba
C70497  pha
C70498  lda $004212      wait for H-blank or V-blank
C7049C  and #$c0
C7049E  beq $0498
C704A0  pla
C704A1  cmp $002140      wait for the SPC to echo the counter
C704A5  bne $04a1
C704A7  inc
C704A8  xba
C704A9  sta $002141      one data byte
C704AD  xba
C704AE  sta $002140      the counter, which kicks the SPC
C704B2  dex
C704B3  bne $0491
```

### The receiver is not the boot ROM

I assumed for a while that the S-SMP's IPL boot ROM was doing the receiving, because the protocol looks
exactly like the documented boot protocol. It is not. Sampling the SPC700 program counter on every port
write settles it: about **3,600 hits inside `$FFC0`-`$FFFF` against roughly 180,000 in RAM at
`$0EBD`-`$0F26`**. That was the moment the job became possible, because RAM can be changed and mask ROM
cannot.

That RAM code is the game's own sound driver, which reimplements the boot protocol. It is uploaded from
ROM, so it can be changed. Dumping the audio RAM and disassembling it with [`spc700.py`](spc700.py), a
disassembler whose opcode table was extracted from the bsnes reference and validated against the boot
ROM's own documented listing, gives the loop with cycle counts:

```
0EC9  push y           4
0ECA  mov y,$00f4      4    read the counter port
0ECD  cmp y,$00f4      4    read it again
0ED0  bne $0eca        2    loop while the two reads disagree
0ED2  mov $0e7,y       4
0ED4  pop y            4
0ED5  cmp y,$0e7       3    has the CPU posted our index?
0ED7  bne $0eed        2
0ED9  mov a,$00f5      4    one data byte
0EDC  cmp a,$00f5      4    read it again
0EDF  bne $0ed9        2
0EE1  mov $00f4,y      5    echo the counter
0EE4  mov ($014)+y,a   7    store
0EE6  inc y            2
0EE7  bne $0ec9        4
```

About **55 cycles**. At 1.024 MHz that is 54 microseconds of the 65 measured per byte, so the CPU is
idle, waiting on the audio chip.

Locating this in ROM is a single search: the 32-byte signature from the live dump appears exactly once,
at file offset `0x072B13`, **byte-identical in both regional ROMs**. One patch covers both.

### The boot ROM as a specification

The S-SMP's own boot ROM does the same job in about 24 cycles:

```
ffda  cmp y,$f4        compare the index against the counter port directly
ffdc  bne $ffe9
ffde  mov a,$f5
ffe0  mov $f4,y
ffe2  mov ($00)+y,a
ffe4  inc y
ffe5  bne $ffda
```

Three things the game's driver does are pure overhead. It pushes and pops Y around the port read only
because it loads the counter into Y instead of comparing against it in place. It reads each port twice
to filter a condition that cannot occur, since a port is a single latched byte and a read of it is
atomic. And it addresses the ports absolutely at four cycles when its own direct page is zero, which
the surrounding code proves, so the two-cycle-cheaper form is available.

Removing all three: **25 cycles per byte**, and the pause falls to 1.03 seconds.

### Two bytes per handshake

Only port `$F5` carries payload. `$F6` and `$F7` are written once at block start and idle for the rest
of the block. Carrying a second byte in `$F6` halves the handshakes: **18 cycles per byte**, and the
pause falls to **0.78 seconds**.

Three bytes is not better than two, which surprised me. Stepping
the store index by three means the page carry can fall on any of the three stores and must be tested
three times, and that cancels the saving. Two steps evenly from zero, so the index can only wrap on the
second store and one test covers it.

### The trap, and how it was avoided

A first attempt at two bytes deadlocked. The game does not have one uploader; it has seven, and the one
at `$C7:0252` **also drives the IPL boot ROM**, which is mask ROM inside the audio chip and can only
ever read one byte per handshake. Converting only some uploaders left the rest talking a protocol the
new receiver did not understand: the CPU sat at `$C7:035E` for 484 frames of a 1,200 frame run with a
black screen.

The solution avoids the problem instead of fighting it. The CPU already sends a **kind byte** in each
block header, which the boot ROM reads and discards, caring only that it is non-zero. Sending 2 instead
of 1 means "pairs" to the driver and nothing at all to the boot ROM. So the driver dispatches on that
byte, and only the uploader carrying **161,910 of 173,596 driver bytes, 93%**, was converted. The boot
path is untouched.

The patch is [`asm/spc-fast-upload.asm`](asm/spc-fast-upload.asm), applied by
[`spcfast.py`](spcfast.py), 25 tests, which reproduces the assembled output byte for byte in both
regions.

### What was ruled out

gizaha's changelog mentions disabling wasteful sample loads, so redundant uploads were measured before
attempting anything: over 20,000 frames, **12 large upload sessions, all distinct, 2% redundant bytes**.
Deduplication buys nothing here. Measuring first saved building it.

---

## 14. Shin Akuma

**TL;DR.** He is already in the retail cartridge behind a cheat. The patch is two bytes and removes
the cheat's preconditions.

I did not add Shin Akuma and I did not touch a byte of graphics or character data. He is already in the
retail cartridge, behind a cheat that nobody documented for 25 years and that was
[found in January 2021](https://www.nintendolife.com/news/2021/01/after_25_years_a_new_cheat_code_has_been_discovered_for_street_fighter_alpha_2_on_the_snes):

1. enter the initials K, A, J in the high score table,
2. return to the title screen,
3. hold L, X, Y and Start on controller two while player one picks Versus,
4. hold Start over Akuma at the character select.

Steps 1 to 3 do exactly one thing: set `$7E:1B09` to `$4A4B`.

The whole cheat is one routine. I found it by searching for `cmp #$5060`, the joypad word for L, X, Y
and Start held together, which has exactly one match anywhere in executable code:

```
C0EC6E  php
C0EC6F  rep #$30
C0EC71  ad 05 1b     lda $1b05        screen state, must be negative
C0EC74  10 27        bpl $ec9d
C0EC76  lda $1b09                     the unlock flag
C0EC79  cmp #$4a4b
C0EC7C  beq $ec9d                     already unlocked
C0EC7E  lda $7efe04                   initials, first two letters
C0EC82  cmp #$414b                    "K" then "A"
C0EC85  bne $ec9d
C0EC87  lda $7efe05                   initials, second and third
C0EC8B  cmp #$4a41                    "A" then "J"
C0EC8E  bne $ec9d
C0EC90  lda $b0                       buttons held on controller two
C0EC92  cmp #$5060                    L | X | Y | Start
C0EC95  bne $ec9d
C0EC97  lda #$4a4b
C0EC9A  sta $1b09                     the flag, and all any of it does
```

The two overlapping reads at `$7E:FE04` and `$7E:FE05` are how three letters are checked with two
16-bit compares: `$FE04` holds "K", `$FE05` "A", `$FE06` "J", so the pairs read back as `$414B` and
`$4A41` on a little-endian bus.

The consumer at `$C0:CA7F` is left untouched, so holding Start over Akuma remains the way in. It checks
the flag, then that the character under the cursor is `$02`, then that Start is held, then writes
variant `$14`.

So the change is two bytes. The precondition test at `$C0:EC71` becomes `bra $ec97`, and the routine's
only remaining job is setting the flag.

Branching from `$C0:EC71` rather than from the initials test matters, and the narrower edit I tried
first does not work. `$1B05` is read there and never written by any absolute store in the ROM, and it
reads back as `$000F` during attract, so bit 15 is clear and the `bpl` would leave before any of the
cheat's own tests ran. I confirmed the result by reading work RAM: stock leaves `$7E:1B09` at `$0000`,
patched leaves it at `$4A4B`, in both regions.

The gate is byte-identical across regions, at file `0x00EC6E` in the USA ROM and `0x00ECA0` in the
Japanese one. [`shinakuma.py`](shinakuma.py), 22 tests, finds it by signature and works on either.

---

## 15. The Japanese build that never worked

**TL;DR.** The Japanese 96 Mbit image had never rendered a frame. The cause was an incomplete stream
map, and the diagnostic that found it was how far the lookup had to scan.

The Japanese chip-free image rendered nothing, in every mapper mode, while the USA one was fine. I had
said earlier that both regions were verified. That was not true, and this section is how I found out.

### A misdiagnosis worth recording

My first isolation was wrong. The Japanese 4 MB intermediate, with only the bypass applied and the chip
still emulated, was black, and I took that as proof the Japanese bypass patch was broken. I had not run
the control. **The USA 4 MB intermediate is black too**, and it should be, because the bypass routine
needs lookup tables that only exist after the re-layout. My test proved nothing at all, and I spent a
while acting on it.

### What was actually checked, and was fine

All seven hook addresses re-derived exactly. The bytes at every site matched their USA counterparts. The
DMA channel each site uses matched. The routine's home at `$35:D700` was genuine filler. All 2,813
decompressed streams landed byte-exact where the tables said they should. No reclaimed region overlapped
a page the CPU ever reads. Everything I knew how to check was fine, which is the least comfortable place
to be.

### The diagnostic

What gave it away was the lookup table scan, because a missing key is silent. The scan walks forward
until some unrelated slot happens to hold a matching bank byte, and hands back a **wrong translation**
without complaining.

| build | scans | median | worst | total steps |
|-------|-------|--------|-------|-------------|
| USA chip-free | 153 | 1 | 24 | 250 |
| Japan, before | 190 | 1 | 3,837 | 203,597 |
| Japan, after | 10,131 | 1 | 31 | 14,142 |

At 3,837 steps a miss costs roughly 8 milliseconds. The build was dropping a third of its frames, 1,912
delivered out of 3,000, and never reached anything worth drawing.

### The fix

Scan length turns out to be a completeness gauge, which is the useful realisation here. I taught the
emulator to log the address every lookup asks for and how many slots it walks. Any scan longer than 64
steps is a miss, and the DMA registers at that instant hand over the exact source and transfer size.
Feed those back into the map, rebuild, repeat until nothing misses.

I recovered **13 streams** that way, and the build came up.

One more thing I learned the hard way: the map has to be harvested against the build that will ship.
Harvesting against the bypass-only ROM converged nicely, and then adding the faster sample upload shifted
the attract timing enough to walk a different path and ask for two more streams.

### It was still wrong, and gameplay is what found it

The build booted, played its attract sequence and passed every check I had, and it was still broken. A
character select screen full of corrupted tiles is what surfaced it, which no automated run had reached,
because my scripted input walked the cursor over a handful of slots and settled.

The cause was a length, not a missing address. A stream carries no length of its own in this format: it
ends where the cartridge stops reading. Record a length longer than the cartridge ever asks for and the
decoder keeps running into whatever follows, so the next stream's start falls inside the previous entry
and never gets a key. Every request for it then misses, and the scan hands back an unrelated bank.

I concluded that the fix was to shorten the covering entry so it ended exactly where the next stream
began. That was wrong, and it took most of a day and five separate corruptions to find out.

Streams overlap. The tagged USA dump proves it: 593 of its 2,773 in-bank pairs have one stream's decode
running past the next stream's start. The cartridge also asks a single address for different amounts at
different times. So an entry covering another entry's start is normal, and the only defect was the
missing entry. Every trim I made was damage, and the hardware eventually reported all five of them:

| entry | I cut it to | the cartridge asks for |
|-------|-------------|------------------------|
| `$190B01` | 5670 | 8192 |
| `$15E82D` | 5686 | 8192 |
| `$16F177` | 3072 | 8192 |
| `$18F7E3` | 5696 | 8192 |
| `$192B62` | 5680 | 8192 |

Each one corrupted a character portrait on the select screen. Only two operations on this table are
safe: adding an address the cartridge asks for, and raising a length to what it asks for. Nothing else.

What settled it was building a proper oracle. Run the retail cartridge with the chip emulated, log every
DMA whose A-bus is fixed, which is the exact condition the chip decompresses under, and you have the
hardware's own list of what a stream is. Nothing in the conversion is involved, so it cannot inherit a
mistake from it.

### Coverage is the whole problem

The oracle answers what, never how much. A stream nobody asks for cannot be discovered, and a fighting
game hides most of itself behind screens a script does not reach. The evidence set grew like this:

| how it was driven | addresses recorded |
|-------------------|--------------------|
| the original scripted input | 42 |
| a driver that sweeps the character roster | 274 |
| a driver that forces a character and enters a fight | 579 |
| a human playing for a few minutes | 790 |
| the same human hovering two specific characters | 820 |
| a human losing a fight and reaching game over | 1,513 |
| an automated tour of the whole roster at three pacings | 1,560 |
| the same tour at six pacings and two ways of advancing menus | 1,661 |

Each widening exposed streams the previous one could not see, and each of those was a screen somebody
had photographed as broken. Once the tour driver existed the loop could close on its own, because it
resets the console between characters, walks the cursor by reading the cursor value out of work RAM
rather than by blind timing, and confirms only when it has arrived.

### Why it took so long, and why it then stopped

Every missing stream blocks the build at the screen that needs it, which stops it reaching anything
beyond, which hides the next missing stream. That is why this came in one screen at a time for a day.
Adding a single address, `$1A64D6`, took the converted build from 67 distinct requests to 496 and
exposed five more behind it.

Once that was understood the search is mechanical, and
[`tools/converge_jp.py`](tools/converge_jp.py) does it: build all three Japanese variants, drive each
through five input regimes, collect every address requested that is not a stream start, confirm it
decodes to exactly the size asked for, add it, rebuild, repeat. It only ever adds. It converged in
three rounds:

| round | candidates | added | table |
|-------|-----------|-------|-------|
| 1 | 8 | 8 | 2,854 |
| 2 | 1 | 1 | 2,855 |
| 3 | 0 | 0 | converged |

Convergence is not proof of completeness. It says that along every path five drivers can reach, across
all three builds, the game never asks for anything the table lacks. A screen no driver reaches can still
hide a stream, and the remedy is the same loop pointed at that screen.

Writing that driver took two mistakes worth naming. The first schedule pressed Start during frames 0 to
900, when this game does not draw a picture until frame 1079, so every press landed during boot. The
second was worse: the driver computed its inputs after the frame had already been emulated, so two
completely different schedules produced byte-identical results, 61 addresses each. Identical output from
changed input is the signal, and I should have read it immediately.

### What must never be done

Harvesting from the converted build. Once that build misses a lookup it programs meaningless DMA
parameters, and a loop that records those as if they were streams will invent entries the cartridge
never asks for and shorten entries it genuinely needs. One run of exactly that produced a table with
eighteen invented streams and two truncations, and it would have shipped had the gate in section 17 not
rejected it in under a second.

Decompressing a candidate proves nothing either. The format carries no header, no length and no
terminator, so any offset in the ROM decodes to something and returns exactly the number of bytes
asked for. An address is a stream because the cartridge asks for it, and for no other reason.

### A wrong turn worth recording

Before finding the lengths I was convinced the bypass routine was translating transfers it should have
left alone. The chip only decompresses when `$4801` is armed **and** the channel's A-bus is fixed, and
the routine only ever checked the first condition, which looked like a clear bug. I added the missing
test, and it made things worse: clean lookups fell from 83 to 56.

The reason is that the routine clears the fixed-address bit itself, as it must, and the engine programs
the parameter register once and then reuses it for every block of a multi-block transfer. So a
continuation legitimately arrives with the bit already clear. Testing it skips exactly the transfers
that most need translating. The unconditional translate is correct, and the guard came straight back
out.

---

## 16. Declaring the cartridge honestly

**TL;DR.** Both conversions, mine included, kept the retail header, so both keep claiming a chip they no
longer contain and a size they no longer are. That is the first reason no emulator can load them.

I found this last, while preparing the upstream contribution, and it changed what that contribution
should say.

A converted image is a different cartridge from the one it came from. It has no coprocessor and it is
three times the size. Both circulating conversions claim otherwise, because both were built by copying
the retail header straight through, and mine did exactly the same thing:

```
Star Ocean, converted:  chipset=$45 (S-DD1)  size byte=$0D (8 MB)   actual file 12 MB
Alpha 2, converted:     chipset=$43 (S-DD1)  size byte=$0C (4 MB)   actual file 12 MB
```

That is not cosmetic. snes9x identifies the chip by matching `(chipset << 8) | mapmode` against `$4332`
or `$4532`, and it takes the ROM size from the header byte. So a 12 MB image gets mapped as a 4 MB S-DD1
cartridge: two thirds of it never gets mapped at all, and chip emulation is switched on for hardware
that is not in the file.

### Six copies, not two

The obvious fix, rewriting the header at `$007FC0` and `$00FFC0`, does not work. These images mirror the
original ROM into the window banks and into the FastROM mirror, so the header turns up six times:

```
0x007FC0  0x00FFC0  0x407FC0  0x40FFC0  0x607FC0  0xA07FC0
```

Correct only the two documented positions and four copies still claim the chip, and the emulator's
header scoring is free to settle on one of those. I measured it: with two copies corrected snes9x still
chose `Map_SDD1LoROMMap`, and only with all six corrected did it stop.

[`header.py`](header.py), 22 tests, finds every copy by searching for the title of whichever documented
header is present, checks the map mode is plausible, and rewrites the chipset and size fields at each.
It restamps one checksum consistent across all copies.

### What it changes, and what it does not

With an honest header snes9x moves from `Map_SDD1LoROMMap` to `Map_JumboLoROMMap`. That is still the
wrong layout and still renders nothing, but the failure has moved from "expects hardware that is not
there" to "does not know this mapping", and the second one is something I can reasonably ask an emulator
author to fix.

One thing I am still not completely comfortable with: four of the six copies live in game-visible ROM.
Header fields are not read by game code, and all 16 builds pass unchanged, but this is the only change
in the whole project that touches bytes the game could in principle read.

---
## 17. Validation

**TL;DR.** I build every combination of region, cartridge form and patch set, and run each one for
12,000 frames. All 16 pass.

| checked | how |
|---------|-----|
| boots and renders | video frames delivered, and frame brightness sampled every 300 frames |
| sound runs | APU port write counts |
| sample uploads intact | every block compared byte for byte against its ROM source |
| menus respond | fights load, which only happens by passing through the menus |
| pause | longest pre-fight upload burst |
| graphics lookups | table scan length; anything over 64 steps is a miss |
| Shin Akuma | `$7E:1B09` reads `$4A4B` only where patched |

Results:

| region | patches | cartridge | 96 Mbit chip-free | Shin Akuma |
|--------|---------|-----------|-------------------|-----------|
| USA | none | 2.60s | 2.60s | not set |
| USA | fast upload | **0.78s** | **0.78s** | not set |
| USA | Shin Akuma | 2.60s | 2.60s | set |
| USA | both | **0.78s** | **0.78s** | set |
| Japan | none | 2.60s | 2.60s | not set |
| Japan | fast upload | **0.80s** | **0.80s** | not set |
| Japan | Shin Akuma | 2.60s | 2.60s | set |
| Japan | both | **0.80s** | **0.80s** | set |

Every build: **12,000 of 12,000 frames delivered**, zero dropped; **34 to 38 of 40 brightness samples
lit**; three fight loads; **zero lookup misses** across all sixteen; **60 of 60 sample blocks
byte-identical** to their ROM source. All eight chip-free images are exactly 12,582,912 bytes.

The lookup counts are worth reading alongside the misses, because they say how far each build gets. The
Japanese chip-free builds perform 3,863 lookups without the sound patch and 1,500 with it, the USA ones
4,155 and 2,711, and none of them misses. The Japanese build that shipped with the wrong stream lengths
managed 154 lookups and missed 69 of them, which is what a build looks like when it derails early.

### On hardware

The USA builds run on real hardware. This is the check the whole document was waiting on, because every
number above comes from an emulator and an emulator can only ever confirm that it agrees with itself.

| hardware | image | result |
|----------|-------|--------|
| Game Doctor SF7, 128 Mbit DRAM | 96 Mbit chip-free, 12,582,912 bytes | runs |
| FXPAK Pro | 96 Mbit chip-free, 12,582,912 bytes | runs |
| FXPAK Pro | 4 MB patched cartridge, S-DD1 still required | runs |

The SF7 result is the one the project set out to get, and it settles the part that was least certain:
the addressing rule in section 6, recovered by inspection from somebody else's build and never checked
against the machine it was written for. It is right.

The two FXPAK Pro results answer different questions, so they are listed separately. That cartridge
emulates the S-DD1 in its FPGA, so the 4 MB patched image running there exercises the sound patch and
the Shin Akuma change against real silicon with the chip present, and says nothing at all about the
decompression. The 96 Mbit image running there says the opposite: no chip is involved, so the
decompressed streams, the reclaimed banks and the bypass routine are all doing their job on hardware
that is not a Game Doctor.

What I am not claiming from these runs is a number. The 0.78 seconds in the table above is a measured
emulator figure, and nobody has put a frame counter on a real console. The hardware result is that the
builds run, not that they run to a stopwatch.

### Checks that do not need the game running

Four of them, and between them they cover everything except whether the table is complete.

**Every stream against the reference decompressor.** [`tools/verify_streams.py`](tools/verify_streams.py)
sends all 2,815 USA and 2,855 Japanese streams through snes9x's own `sdd1emu.cpp` in a container and
compares byte for byte with the Python decompressor. Both regions come back identical, in about thirteen
seconds each.

**Every stream inside the finished image.** [`tools/verify_image.py`](tools/verify_image.py) reads the
12 MB image the way the console does: it walks the lookup tables in banks `$60` to `$63`, follows each
translation, and compares the bytes actually sitting at the destination against what the chip produces.
Zero unresolved lookups and zero wrong bytes. This is what rules out the re-layout having damaged
something, and it is worth stating that it does: of 1,172,430 original bytes replaced in the window
banks, every run sits inside a stream's compressed data except twelve, which are the header fields
section 16 rewrites on purpose.

**The build gate.** [`gate.py`](gate.py) refuses to produce an image unless the table has no repeated
sources, every entry decodes to exactly its recorded length, the worst key scan stays inside its budget,
and every request in [`requests_jp.py`](requests_jp.py) is covered with a length at least as large. That
last clause is the one that earns its keep: 1,661 addresses recorded from working hardware, and it
rejected a table that had invented eighteen streams and truncated two real ones.

**The sound patch against its own source.** [`spcfast.py`](spcfast.py) carries the sound patch as
frozen byte runs rather than calling the assembler, which keeps the build independent of a toolchain
but lets the table drift away from [`asm/spc-fast-upload.asm`](asm/spc-fast-upload.asm) without anything
noticing. It had drifted, and three rounds of assembly changes reached no image at all before I worked
out why. [`tools/freeze_spcfast.py`](tools/freeze_spcfast.py) assembles both regions and compares the
result against what the frozen table produces, byte for byte; `--check` reports without rewriting.

```
python3 tools/freeze_spcfast.py --check
  jp: the frozen table reproduces the assembler exactly
  usa: the frozen table reproduces the assembler exactly
  25 runs, 300 bytes
```

### Reading the brightness metric

It counts frames whose averaged pixel brightness is above 5 out of 255. It is never 100 per cent, and it
should not be, because the game is legitimately black for long stretches. Unmodified retail sits at 0.0
from frame 379 to 519 and again from 699 to 1059 while it boots and decompresses, and picture appears
around frame 1079. What matters is that a patched build matches retail. A build with substantially more
dark frames than retail is the warning sign.

The metric proves the game keeps drawing. It does not prove the images are right, which is what the
block integrity and lookup miss checks are for.

---

## 18. What is not verified

**TL;DR.** Whether the Japanese stream table is complete, the Japanese build on hardware, and audio
quality. Said out loud rather than buried at the bottom.

Completeness of the Japanese table. This is the honest headline. The table is correct for everything
1,661 recorded hardware requests cover, and there is no way to prove it covers everything, because a
stream nobody asks for cannot be found. Eleven times the count moved because a screen that had never
been driven produced another missing stream, and the search has since converged: three rounds of all
three builds under five input regimes, and the last round found nothing. That is the strongest
statement available and it is not proof. Anyone running this build should expect that a screen nobody
has visited may still be wrong, and the fix when it happens is mechanical: drive the retail cartridge
to that screen, read what it asks for, add it.

The Japanese build has never left the emulator, and it is also the build whose table is still settling,
so those two gaps compound. The USA builds have run on real hardware, which is section 17, and that
removes the largest doubt hanging over the mapper. It does not transfer to Street
Fighter Zero 2. That build differs in the seven hook addresses, in where the routine lives, and above
all in its stream map, which is the one part that was rebuilt from scratch by harvesting rather than
read out of a tagged ROM. Section 15 is the record of that map being confidently wrong once already.
Until somebody puts it on a cartridge, treat the Japanese image as emulator-only.

Audio quality. I verify sound as traffic and as payload integrity: the right bytes reach audio RAM.
Nothing listens to it. A build that transfers perfectly and sounds wrong would sail through every check
I have.

Selecting Shin Akuma in game. I can prove the unlock flag is set in exactly the patched builds, and the
substitution code is documented above, but my scripted input never lands the cursor on Akuma. The
selection itself needs a human with a controller.

### The background upload, attempted and not finished

The pause that remains is short but it is still a freeze: the main loop stops, so the picture stops.
Moving the transfer into the frame interrupt would leave the game running and the pause would stop
reading as one, even if it lasted longer. I built it far enough to learn what it costs, and it is not
in the shipping images.

The first thing worth writing down is that spreading the work does not reduce it. The receiving chip
absorbs about 52,500 bytes per second whoever feeds it, so a 47,915 byte set is 0.91 seconds of chip
time in any design. Slicing only helps where there is somewhere to hide it, and the room varies:

| spare time per frame | throughput | one set takes |
|---|---|---|
| 20% | 175 bytes/frame | 274 frames, 4.6s |
| 40% | 350 bytes/frame | 137 frames, 2.3s |
| 60% | 524 bytes/frame | 91 frames, 1.5s |

Measured gaps between one block list and the next are a median of 213 frames, a tenth percentile of 53
and a minimum of 7. So the median case has ample room and the worst tenth does not, which means a
background design has to fall back to a synchronous drain and some stalls survive by construction.

What I built: the transfer state moved out of registers into work RAM at `$7F:0A00`, so a block can be
posted in slices and resumed; the block list walk suspends instead of running to the end; the frame
interrupt posts one slice per frame from the point where the handler waits on the auto joypad read; and
the engine drains synchronously if a new command arrives while a list is still outstanding.

It does work, and I have it crossing frame boundaries. Tracing the state every frame, a block armed on
frame 345 was sliced over the next two and closed itself on frame 347, with the list cursor and the APU
destination advancing exactly as they should.

Eight defects surfaced on the way, and each is worth keeping:

- Work RAM does not come up zeroed on a console. The state block needed a mark written by the code that
  fills it in, checked before anything reads it. Emulators mostly do clear it, which is precisely why
  testing would not have caught this.
- The interlock that keeps the interrupt off the ports was set after the synchronous drain instead of
  before it. The interrupt fires during the drain's wait spin, so both sides started feeding the same
  block and each waited for a handshake the other had taken.
- There are two block list walks, at `$C7:00AE` and `$C7:015B`, byte for byte the same loop. I hooked
  one and the samples go through the other.
- The upload is a session. `$C7:01DD` posts a header whose kind byte is zero, and that releases the
  chip to go back to playing. A block that arrives after it has nobody listening, and the console hangs
  waiting for an echo that is never coming.
- The suspend routine drained the previously suspended list and then recorded the cursor, but draining
  walks a different list through the same registers and the same direct page. It was recording a sample
  source address as a list pointer, and the walk then read ids that resolved into bank `$06`, which
  holds compressed graphics and no samples at all.
- The engine's entry hook runs at `$C7:005B`, and the engine does not set its direct page to zero until
  `$C7:0065`. Every `$84` and `$8A` through `$8E` access in the drain was landing on whichever page the
  caller happened to have, so the terminator posted a counter the driver never recognised.
- Setup has its own return path at `$C7:0053`, not the engine's. Clearing the interlock at the end of
  the entry hook instead of there left a window in which the interrupt opened a block while setup was
  still talking to the driver, and setup then waited forever for a `$BBAA` that a busy driver cannot
  send.
- The handler clears the interrupt by reading `$4210` at `$C0:01BA`, long before this hook runs, so the
  next vblank re-enters it while a slice is still waiting on the driver. Two slices interleaved their
  handshakes. This is the one that produced the impossible-looking reading: a block reporting every
  pair posted with only 844 of its 5,571 bytes arrived.

With those fixed, every block transfers byte-identical in the background. The block verifier walks each
one against the bytes actually sitting in sound RAM and reports `ok=30 bad=0`, including blocks of
7,227 and 5,571 bytes carried across many frames.

Where it stops, and what the stall turned out to mean: the console still hangs with the screen dark,
and the reason is not a bug so much as the shape of the design. The emulator reports both sides of the
deadlock, the driver's own index and the counter the CPU last posted:

```
STUCK cpu=00FFE0 spc=0EC5 ya=2401 x=0E port0=23 port1=BB
```

The driver's index is `$24` and the counter posted is `$23`. One even, one odd. The index steps by two,
because it is inside one of the blocks this patch sends two bytes at a time; the counter steps by one,
because the code posting it is one of the engine's own uploaders sending one byte at a time. They are
two different transfers talking over each other, and the driver waits forever for a counter that the
other side is never going to send.

That rules out the explanations I spent the longest on. It is not who is allowed to close the session:
giving the deferred transfer a session entirely of its own, opened with `$C7:01A5` and closed with
`$C7:01DD`, changes nothing. It is not the order of the two lists, and it is not the counter arithmetic.
The exposure is simply that a block of ours stays open across a frame boundary at all. The moment it
does, any path that reaches an uploader talks into the middle of it, and every entry into the sound
bank has now been hooked and checked, so there is no door left to close.

The shape that follows from this is to stop yielding inside a block. A block header carries its own
destination, so one block of 7,227 bytes can be sent as a series of smaller ones at consecutive
destinations and the bytes land identically. Slice the data into sub-blocks, and every point where the
interrupt hands control back is then a boundary with nothing open and the driver idle. That is a
rewrite of the block layer rather than another guard on top of the one that exists, which is why it is
written down here rather than half-built.

Two narrower variants were measured along the way and are worse, not better: deferring only the second
walk gives 13 corrupted blocks, and making the interrupt inert starves the game of samples entirely.

The transfers themselves are correct and the remaining fault is structural. Shipping it would mean
shipping a hang, so the images carry the blocking transfer that is proved.

---

## 19. Lessons

**TL;DR.** Measure before you build. Disassemble what the assembler actually emitted. And when two
things that ought to differ come out identical, the bug is somewhere you are not looking.

The compression was the documented part, and it was the easy part. Everything expensive in this project
was addressing, which nobody wrote down. Star Ocean's conversion answered that question years before I
asked it, and I spent a while treating it as inspiration when I should have been treating it as a
specification. Prior art is not encouragement. It is a spec with the comments removed.

Every assembly bug I hit was found by disassembling the output, never by rereading the source. `pea
$0000` looks correct. An assembler quietly widening a direct-page operand looks like nothing at all,
and it moved my code far enough to overwrite the routine it was supposed to fall into. I now read back
what came out, every time, and I would not trust myself to do otherwise.

The Japanese map was wrong for most of five years and nothing told me. That is the part that stings. A
missing entry does not raise an error, it produces a plausible wrong address, and the build limps
instead of stopping. What eventually cracked it was finding a number that moved when the fault was
present: how far the lookup had to scan. Two rounds of that and the map was complete. Two years of not
having it and the map was quietly broken. If a failure is silent, the job is to find something loud
that correlates with it.

I also wasted real effort concluding the Japanese bypass was broken, because its intermediate build was
black. One run of the equivalent USA build would have shown me that it is black too, by design, and
that the test proved nothing. Run the control. It costs one command.

Two instrumentation lessons, both learned the hard way. A probe that read memory through the emulator's
own accessor changed timing enough to invalidate an entire validation matrix and skew a map harvest, so
measurement now avoids the accessor. And two instruments running together changed each other's results,
so metrics that interact get collected in separate runs.

Twice a failing test turned out to be wrong rather than the code, once because I had copied an expected
value out of a hand-written comment instead of the reference implementation. Test the test before you
change the thing it is accusing.

The last one only surfaced at the very end. Both chip-free conversions, mine included, spent their
whole existence claiming hardware they do not contain and a size they are not, because we all copied
the retail header through without thinking about it. Nobody noticed because everyone running these
files already knew what they were. It took a tool that had to decide without being told.

---

## 20. Upstream contributions

**TL;DR.** One change is genuinely needed by anyone who wants to run these images. I raised it as
[snes9x issue 1081](https://github.com/snes9xgit/snes9x/issues/1081), and it was merged as
[pull request 1082](https://github.com/snes9xgit/snes9x/pull/1082) on 15 August 2026, so current snes9x
loads these conversions out of the box. Everything else I built is development-only and stays here.

### Merged into snes9x: support for S-DD1 games converted to run without the chip

Both S-DD1 cartridges have decompressed conversions in circulation, and snes9x loads neither. I measured
the Star Ocean conversion against snes9x 1.63 and it renders nothing across 3,000 frames.

There are two causes, and the first one is the conversions' own fault, mine included.

**The header lies.** Both conversions keep the retail header, so they still declare the chip and still
declare the retail ROM size. snes9x matches `(chipset << 8) | mapmode` against `$4332` and `$4532`,
enables chip emulation, and then maps that 12 MB image as an S-DD1 cartridge, which is the wrong
layout. I originally wrote that it also takes the ROM size from the header byte. It does not:
`CalculatedSize` comes from the file size, and the header size byte only drives the reported size and a
warning colour. I corrected that on the issue rather than leave it standing. [`header.py`](header.py) fixes this for the images built
here: chipset `$00`, the real size, at **all six** header copies, since these images mirror the
original ROM in several places and correcting only the two documented positions leaves the scoring to
find a dishonest one. With that done snes9x stops choosing `Map_SDD1LoROMMap`.

**The layout is unknown to snes9x.** With an honest header it falls through to `Map_JumboLoROMMap`,
which is a different layout, and still renders nothing. The mapping these conversions need is the one
described in section 6, including the window rule for banks `$C0` and above, which cannot be expressed
with the existing `map_lorom` and `map_hirom_offset` helpers. That layout is not a guess about what an
emulator ought to accept: an image built to it runs on a Game Doctor SF7 and on an FXPAK Pro, which is
section 17.

The detection has to sit above the HiROM and LoROM split, not inside the LoROM chain beside
`Map_SDD1LoROMMap`. I put it in the obvious place first and the USA image worked, which is exactly how
this kind of mistake survives. The Japanese image at 96 Mbit scores as HiROM, takes the other branch
entirely and lands in `Map_ExtendedHiROMMap`, so the check never runs. Testing one region proved
nothing about the other, and only building both caught it.

I opened [issue 1081](https://github.com/snes9xgit/snes9x/issues/1081) before writing any of it,
because how these images should be identified is a maintainer's decision and not mine. Trusting a
corrected header only helps conversions that fix theirs, which the circulating Star Ocean one does not,
so a size test is needed as well for images that still declare the chip. OV2 chose that combination,
size with the honest header as a fast path, and
[merged it as pull request 1082](https://github.com/snes9xgit/snes9x/pull/1082) on 15 August 2026. It
is in snes9x master, and [issue 1081](https://github.com/snes9xgit/snes9x/issues/1081) is closed with a
note recording the detection placement and correcting a claim in my original description.

The work was done on the
[`sdd1-decompressed-map`](https://github.com/gufranco/snes9x/tree/sdd1-decompressed-map) branch of a
snes9x fork rather than as a patch file in this repository, so it could be built and run the way any
other snes9x change would be. It touches two files: `Map_SDD1DecompressedMap` in `memmap.cpp`, and the
detection ahead of the mapper dispatch.

The same gap almost certainly exists in [ares](https://github.com/ares-emulator/ares),
[Mesen2](https://github.com/SourMesen/Mesen2), [bsnes](https://github.com/bsnes-emu/bsnes) and
[Mednafen](https://mednafen.github.io/), and BizHawk inherits bsnes. I read all three GitHub codebases
far enough to know what the work would be, and it is not one patch three times. Mesen2's mapping is
explicit C++ and would need a per-bank registration, since each bank's lower half comes from a different
place in the file. ares and bsnes are data-driven: a board string derived from the header selects a
memory map defined in a manifest, so the change there is a board definition rather than mapper code.
Mednafen is not on GitHub and takes a patch to its own tracker.

I stopped there deliberately. snes9x is the one that matters for this project, the change is merged, and
sending untested mapper code to three more projects would be worse than sending none. Each would need
building and running against both conversions first, the way snes9x was, and none of that happened.

### Development-only, documented here rather than submitted

Everything in the instrumentation table in section 12 exists to diagnose this project and has no place
upstream. I am describing it here so the measurements in this document can be reproduced. Each
instrument is gated behind an environment variable and is inert without it.

| variable | effect |
|----------|--------|
| `SFDMA` | trace every DMA with its triggering program counter |
| `SFREADS` | per-bank read counters |
| `SFAPU` | APU port writes per frame, and writer program counters |
| `SFAPURAM` | dump audio RAM, and report SPC700 program counters |
| `SFVERIFY` | compare every uploaded sample block against its ROM source |
| `SFSCAN`, `SFSCANLEN` | log lookup addresses and scan lengths |
| `SFBRIGHT` | sample frame brightness at a chosen interval |
| `SFSHOTS` | write a screenshot timeline |
| `SFFLAG`, `SFSELECT` | read the Shin Akuma flag and the selected character |
| `SFDRIVE`, `SFFORCE` | closed-loop input driving |
| `SFGRID`, `SFSETTLE` | sweep the character roster, one slot per interval |
| `SFTOUR`, `SFTOURBUDGET` | reset between characters and play each one in turn |
| `SFHASH` | a hash of every frame, for comparing two runs |
| `SFDUMP`, `SFSHOTEVERY` | write frames as images, periodically or over a range |
| `SFPORTRAIT` | capture one frame per character, keyed on the cursor |

`SFTOUR` is the one that closed the loop. It resets the console between characters, waits out the boot,
walks the cursor by reading its value out of work RAM rather than by counting frames, confirms only once
it has arrived, then lets the match run and moves on. Reading the game's own state instead of trusting
timing is what makes it reliable where every open-loop schedule before it drifted.

Two of them I had to fix after they distorted my own results, which is at the end of section 12.

### Playing it by hand, with the chip watching

Scripted input is a poor explorer of a fighting game, and the numbers in section 15 say so: a few
minutes of a person playing found more streams than every driver I wrote. So the instrumentation also
runs under a frontend a human can use. A small SDL frontend drives the same libretro core, and a second
build of that core logs every DMA to stderr, which makes an ordinary play session a recording session.

Point it at the 4 MB cartridge form with the chip emulated and everything it draws is correct by
construction, while everything it asks for is hardware truth. That is where most of `requests_jp.py`
came from. The Shin Akuma unlock is applied to that build for a specific reason: on a genuine cartridge
he sits behind a cheat, so no capture of the retail ROM can ever contain his assets.

None of this is in the repository. It is scaffolding, it lives outside the project, and it is described
here because the measurements cannot be reproduced without knowing it existed.

### The native macOS build of snes9x, and why it is not used here

Worth recording as a dead end. snes9x 1.63's Xcode project still links `AGL` and `GLUT`, both removed
from current macOS SDKs, and Xcode 26 no longer ships the Metal compiler by default. After clearing
both, the app builds and runs, emulates with audio, and never creates a window. The frontend used here
is the SDL one instead, which is a few hundred lines and entirely under control.

---

## 21. Reproducing this

**TL;DR.** Everything here rebuilds from your own ROMs with Docker and Python 3. No ROM data is
distributed.

You supply the retail cartridges, and nothing else. Both stream tables are frozen into the repository,
so building needs only your own dumps.

Two retail cartridges, named here as No-Intro names them. Every digest below is of the whole file with
no copier header, 4,194,304 bytes each, and the scripts read them from `roms/` under the filenames in
the second column:

| `Street Fighter Alpha 2 (USA)` | read as `roms/sfa2-usa-final.sfc` |
|---------------------------|--------------------------------------|
| size | 4,194,304 |
| CRC32 | `9C59DDFF` |
| MD5 | `aa3c90fa7d89eb3dc3389a9436bd0cf8` |
| SHA-1 | `f4ede150b5281f7f5d7e3188c6d9163c2bc66475` |
| SHA-256 | `910a29f834199c63c22beddc749baba746da9922196a553255deade59f4fc127` |

| `Street Fighter Zero 2 (Japan)` | read as `roms/sfz2-jp-final.sfc` |
|--------------------------|---------------------------------------|
| size | 4,194,304 |
| CRC32 | `7455A7CF` |
| MD5 | `70761ab447f48091a8dc437fd2e9c14d` |
| SHA-1 | `a0db1045fb308d6a2975a4d305b69f877be727a4` |
| SHA-256 | `f15731675e22dbf3882b777b2d8cd541a637dfdf5d8880c83903cf1e0b64590e` |

| the tagged dump | read as `roms/sfa2-usa-vc-sound-restored.sfc` |
|---------------------------------------|---------------------------------------------------|
| size | 4,194,304 |
| CRC32 | `72A9E2C1` |
| MD5 | `058471b547ebc59b43704bca664cb690` |
| SHA-1 | `dfa7cd6f713c44b6a01a6f91de068eb7ace63676` |
| SHA-256 | `f8aa2ae1f4bc993092fc282a883ecaf669269c17a175a5f43fa95e9da6459dc0` |

The third file has no No-Intro name because it is not a retail cartridge: it is DarkAkuma's SNES
Classic dump, which carries the stream tags.

SHA-256 is the one that decides. The other three are there so you can cross-check a file against the
community databases that still key on them, and the size is there because it rejects the wrong file for
one `stat` call. The tagged dump is needed only by [`sdd1map.py`](sdd1map.py) when regenerating
[`usastreams.py`](usastreams.py), never to build an image, and an image built from the frozen table is
byte-identical to one built by reading its tags.

Check what you have before building anything:

```
python3 tools/identify.py
```

Nothing in this repository contains game data, and nothing ever will.

### Prerequisites

Docker, Python 3, and retail dumps in `roms/`. The two build containers pin their toolchains: asar is
built from source at a fixed version, and the emulator pins snes9x 1.63 and verifies the S-DD1 source
file by sha256 before compiling. Both run with no network access as a non-root user.

### Building a chip-free image

```
python3 spcfast.py    roms/sfa2-usa-final.sfc  build/step1.sfc     # faster sample upload
python3 shinakuma.py  build/step1.sfc          build/step2.sfc     # unlock Shin Akuma
python3 build.py      asm/sdd1-bypass.asm build/step2.sfc bypass.sfc
python3 rombuild.py   asm/bypass.sfc roms/sfa2-usa-vc-sound-restored.sfc build/nochip.sfc
python3 header.py     build/nochip.sfc build/final.sfc             # declare it honestly

The tagged ROM in step 3 is only needed to regenerate [`usastreams.py`](usastreams.py). `pack.py` reads
the frozen table and needs nothing but the retail cartridge.
```

Order matters. The sample and Shin Akuma patches apply to the retail ROM; the bypass must come next
because the re-layout reclaims the compressed data it reads; the header must come last because it
checksums the finished image.

For the Japanese build, substitute `asm/sdd1-bypass-jp.asm`, and supply the stream map from
[`jpstreams.py`](jpstreams.py), since no tagged ROM exists for that region.

### Building the release images

```
python3 pack.py            # both regions into dist/, named with the version
python3 pack.py jp         # one region
```

`pack.py` runs the gate first and refuses to write anything if the table fails it, then produces
`sfa2-usa-nochip-v<version>.sfc` and `sfz2-jp-nochip-v<version>.sfc` alongside a `SHA256SUMS` manifest.
The version comes from [`version.py`](version.py), which `scripts/set-version.sh` rewrites during a
release, so an image on disk always says which build of this project produced it. An unreleased build is
marked `-dev` rather than pretending to be a version.

Releases are cut by semantic-release from Conventional Commit messages, wired in
[`.releaserc.json`](.releaserc.json) and run by the `release` job in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml). There is no changelog file: the notes live on
the GitHub release, because this repository keeps exactly one markdown file.

### Checking the stream table

```
python3 mapcheck.py roms/sfz2-jp-final.sfc     # shape of the table
python3 gate.py                                 # the gate both regions must pass
python3 tools/verify_streams.py                 # every stream against the C reference
python3 tools/verify_image.py                   # every stream inside the finished image
```

The first reports duplicate sources, streams that fail to decode, and the worst key-scan distance. The
other three are section 17. A table that passes all of them can still be incomplete, which is what
section 15 is about, but one that fails any of them is definitely broken.

### Running the tests

```
for t in *.test.py; do python3 "$t" || break; done
```

19 modules, 281 tests. Several require the retail ROMs and skip cleanly without them.

### Reproducing the measurements

Every figure in this document comes from the instrumented emulator, and each instrument is gated behind
the environment variable listed in section 20. For example, the pre-fight pause is the longest run of
consecutive frames with heavy APU port traffic:

```
docker run --rm --network=none -e SFAPU=1 -v "$PWD:/work" \
  sf-decompressed/sfemu:snes9x-1.63 build/final.sfc 12000 -2
```

The third argument selects the memory map: `-1` is stock, `-2` installs the Game Doctor mapping needed
for a 96 Mbit image.

---

## 22. Repository guide

**TL;DR.** Analysis modules with tests beside them, assembly that goes into the ROM, and a pinned
container for each toolchain.

| file | role |
|------|------|
| [`romtools.py`](romtools.py) | copier headers, Game Doctor part joining |
| [`analyse.py`](analyse.py) | compression ratios and chunk indexing |
| [`sdd1.py`](sdd1.py) | the S-DD1 decompressor |
| [`sdd1ref.py`](sdd1ref.py) | differential test against the C reference |
| [`sdd1find.py`](sdd1find.py) | content search for streams |
| [`sdd1map.py`](sdd1map.py) | stream table extraction from a tagged ROM |
| [`usastreams.py`](usastreams.py) | the USA stream table, transcribed from the tags |
| [`tools/identify.py`](tools/identify.py) | checks the cartridge dumps against their published digests |
| [`sdd1sites.py`](sdd1sites.py) | finds every write to the chip's registers |
| [`sdd1tables.py`](sdd1tables.py) | builds and verifies the lookup tables |
| [`layout.py`](layout.py) | the interleaved address arithmetic |
| [`rombuild.py`](rombuild.py) | assembles the 96 Mbit image |
| [`mapcheck.py`](mapcheck.py) | validates the stream table offline |
| [`jpstreams.py`](jpstreams.py) | the Japanese stream table, with its derivation |
| [`header.py`](header.py) | makes a converted image declare itself honestly |
| [`wdc65816.py`](wdc65816.py) | 65816 disassembler with M and X width tracking |
| [`spc700.py`](spc700.py) | SPC700 disassembler |
| [`emu65816.py`](emu65816.py) | minimal 65816 interpreter |
| [`patchrun.py`](patchrun.py) | executes the assembled patch against a memory model |
| [`spcfast.py`](spcfast.py) | applies the sample upload patch |
| [`shinakuma.py`](shinakuma.py) | applies the Shin Akuma unlock |
| [`build.py`](build.py) | Docker wrapper around asar |
| [`gate.py`](gate.py) | the checks an image must pass before it is written |
| [`requests_jp.py`](requests_jp.py) | decompression requests recorded from working hardware |
| [`pack.py`](pack.py) | builds the release images, named with the version |
| [`version.py`](version.py) | the release number, rewritten by `scripts/set-version.sh` |

Development tooling lives in [`tools/`](tools/): the differential and image checks from section 17, a
full rebuild of every combination, the validation matrix runner, and the drivers that recover streams
by watching the retail cartridge. None of it is needed to build an image; all of it is needed to
reproduce the measurements in this document.

Both stream tables are frozen, and every tool that produced them is kept. That is deliberate. A frozen
table is a claim, and the only thing that keeps a claim honest is the ability to make it again from
scratch. [`sdd1map.py`](sdd1map.py) still reads the tags out of the tagged ROM, and a test asserts that
what it extracts is exactly what [`usastreams.py`](usastreams.py) holds, so the freeze cannot drift
without the suite noticing. The Japanese side has no such single source, which is why the drivers that
recovered it, and the recorded requests they produced, are kept as well: if a screen nobody has visited
ever turns out to be wrong, the same loop is pointed at it and the table grows again.

Assembly that goes into the ROM lives in [`asm/`](asm/): the bypass patches for both regions, the shared
translate routine, the sample upload patch, and the Shin Akuma unlock for both regions.

Both disassemblers had their opcode tables extracted programmatically from reference implementations
rather than typed, and both are validated against known listings.

The emulator change is not in this repository. It lives on the
[`sdd1-decompressed-map`](https://github.com/gufranco/snes9x/tree/sdd1-decompressed-map) branch of a
snes9x fork, where it is ordinary source rather than a patch script, and the discussion is in
[snes9x issue 1081](https://github.com/snes9xgit/snes9x/issues/1081).

I keep a snapshot of every state that passed the full matrix, source and assembly and maps and
emulator and all 24 built images, each with a sha256 manifest, so that a change which turns out badly
gets reverted to a known-good point instead of debugged under pressure. Those snapshots stay on my
machine and are not in this repository, because most of their bulk is built ROM images. The states are
the lean receive loop at 1.03 seconds, two bytes per handshake at 0.78, and the honest header.

Run the tests with `python3 <module>.test.py`. All 19 modules, 281 tests.

---

## 23. Acknowledgements

This project is assembled almost entirely out of other people's work. Naming them is not a courtesy, it
is an accurate description of where the parts came from.

**Andreas Naive** reverse engineered the S-DD1 compression algorithm. Without that published work there
is no project at all; the rest of this is plumbing around his result.

**Modern Vintage Gamer** made [the video](https://www.youtube.com/watch?v=fB9GlZUYNUQ) that started
this, and in particular made the point that the pause is the sound rather than the chip, which is where
section 13 begins.

**gizaha** did the original work on the pause and published a
[changelog](https://www.zeldix.net/t1831-street-fighter-alpha-2) precise enough to act as a
specification. The entry "Faster audio load, upload 2 bytes at the time instead of 1" is the idea in
section 13, arrived at independently here only after his note said where to look. His "Disable some
waste sample loads" is why I measured redundancy before building deduplication, which saved
building something worthless.

**DarkAkuma** produced the SNES Classic patch whose `SDD1` marker tags gave the complete USA stream map.
The Japanese map, which had no equivalent, took two years longer and was still wrong, which is the best
possible illustration of what that work was worth.

**The Star Ocean chip-free conversion authors**, whose build was the ground truth for the decompressor
and the source of the addressing rule in section 6.

**The snes9x team**, both for the emulator and for `sdd1emu.cpp` serving as the reference the Python
decompressor is tested against.

**The bsnes project**, whose disassembler tables both disassemblers here were extracted from.

**The Zeldix community**, where most of the SNES romhacking knowledge this leans on is written down.

**Whoever found the Shin Akuma code** after 25 years, reported in January 2021.

---

## 24. References

- Modern Vintage Gamer, [A closer look at Street Fighter Alpha 2 on the Super Nintendo](https://www.youtube.com/watch?v=fB9GlZUYNUQ)
- [Street Fighter Alpha 2 thread on Zeldix](https://www.zeldix.net/t1831-street-fighter-alpha-2), gizaha's patches and changelog
- Nintendo Life, [After 25 Years, A New Cheat Code Has Been Discovered For Street Fighter Alpha 2 On The SNES](https://www.nintendolife.com/news/2021/01/after_25_years_a_new_cheat_code_has_been_discovered_for_street_fighter_alpha_2_on_the_snes)
- [Retroware, The Curious Case of Street Fighter Alpha 2 on the SNES](https://articles.retroware.com/2021/03/08/the-curious-case-of-street-fighter-alpha-2-on-the-snes/)
- [snes9x](https://github.com/snes9xgit/snes9x), `sdd1emu.cpp` for the compression reference and `iplrom.cpp` for the S-SMP boot ROM listing
- [Romhacking.net hack 7928](https://www.romhacking.net/hacks/7928/), Street Fighter Alpha 2 Ultra
- [snes9x issue 1081](https://github.com/snes9xgit/snes9x/issues/1081), where the mapper support was
  proposed and the detection mechanism agreed
- [snes9x pull request 1082](https://github.com/snes9xgit/snes9x/pull/1082), merged 15 August 2026,
  which is the change itself
- [The fork it was written on](https://github.com/gufranco/snes9x/tree/sdd1-decompressed-map)

---

## Legal

No ROM data is distributed here. Everything in this repository operates on files you must already own.
The patches are derived from analysis of retail cartridges you supply.

The tooling, the assembly and this document are released under the [MIT licence](LICENSE), so that the
emulator mapper written for the [fork](https://github.com/gufranco/snes9x/tree/sdd1-decompressed-map)
can be taken by projects whose own licences
range from GPL to snes9x's non-commercial terms. That covers my own work and nothing else. It grants no
rights in the game.
