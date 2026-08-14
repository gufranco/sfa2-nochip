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

# 3. decompress every stream and lay out the 96 Mbit image
python3 rombuild.py asm/bypass.sfc roms/sfa2-usa-vc-sound-restored.sfc build/nochip.sfc

# 4. make the image declare itself: no coprocessor, real size
python3 header.py build/nochip.sfc build/sfa2-usa-nochip.sfc
```

Steps 1 and 2 alone give a patched retail cartridge that still needs the chip but loses the pause. All
four give the chip-free 96 Mbit image. Order matters, and section 21 explains why.

For Street Fighter Zero 2, use `asm/sdd1-bypass-jp.asm` and pass
[`maps/sfz2-jp.json`](maps/sfz2-jp.json) to `rombuild.py` instead of a tagged ROM, because no tagged
Japanese ROM exists.

**Status:** 16 build combinations validated under emulation, both regions, cartridge and 96 Mbit forms.
Not yet tested on hardware.

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
        return (bank + banks) * HALF + addr      # low half lives a whole ROM away
    return bank * HALF + (addr - HALF)           # high half is plain LoROM
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

The final map, [`maps/sfz2-jp.json`](maps/sfz2-jp.json), holds **2,814 streams**.
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

I recovered **13 streams** that way. They are listed as `RECOVERED_JP` in [`mapcheck.py`](mapcheck.py).

One more thing I learned the hard way: the map has to be harvested against the build that will ship.
Harvesting against the bypass-only ROM converged nicely, and then adding the faster sample upload shifted
the attract timing enough to walk a different path and ask for two more streams.

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

Every build: **12,000 of 12,000 frames delivered**, zero dropped; **10,929 to 11,360 of 12,000 frames
lit**, that is 91 to 95 per cent; three fight loads; **zero lookup misses**; **60 of 60 sample blocks
byte-identical** to their ROM source. All eight chip-free images are exactly 12,582,912 bytes.

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

**TL;DR.** Hardware, audio quality, and selecting Shin Akuma in-game. Three real gaps, said out loud
rather than buried at the bottom.

Hardware. Everything above is snes9x 1.63. None of it has run on a real Game Doctor SF7. My mapper is a
reconstruction, and it is supported by Star Ocean booting and by these images running, but an emulator
agreeing with itself is not silicon agreeing with me.

Audio quality. I verify sound as traffic and as payload integrity: the right bytes reach audio RAM.
Nothing listens to it. A build that transfers perfectly and sounds wrong would sail through every check
I have.

Selecting Shin Akuma in game. I can prove the unlock flag is set in exactly the patched builds, and the
substitution code is documented above, but my scripted input never lands the cursor on Akuma. The
selection itself needs a human with a controller.

### One idea considered and not built

Making the sample upload non-blocking, so it hides behind the pre-fight animation, would take the
perceived pause close to zero. I did not build it, for one specific reason: two different subsystems
write the same four APU ports.

```
bank $C7:  33 sites, 155,748 writes   the uploader
bank $C0:   8 sites,      43 writes   the game's sound-command interface
```

Today that is safe only because the upload blocks the main loop, so a sound command can never land in
the middle of a handshake. A background upload would collide on almost every fight, because the versus
screen is exactly when the announcer plays. Doing it safely means slicing the transfer inside the frame,
after the game's own command dispatch, which means touching the command path too. And its failure mode
is a sample arriving late, which every check listed above would happily report as green. I would rather
ship 0.78 seconds I can prove than zero I cannot.

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

**TL;DR.** One change is genuinely needed by anyone who wants to run these images, and I have raised it
with snes9x. Everything else I built is development-only and stays here.

### Proposed: support for S-DD1 games converted to run without the chip

Both S-DD1 cartridges have decompressed conversions in circulation, and snes9x loads neither. I measured
the Star Ocean conversion against snes9x 1.63 and it renders nothing across 3,000 frames.

There are two causes, and the first one is the conversions' own fault, mine included.

**The header lies.** Both conversions keep the retail header, so they still declare the chip and still
declare the retail ROM size. snes9x matches `(chipset << 8) | mapmode` against `$4332` and `$4532`,
enables chip emulation, and sizes the ROM from the header byte, so a 12 MB image is mapped as a 4 MB
S-DD1 cartridge with two thirds unmapped. [`header.py`](header.py) fixes this for the images built
here: chipset `$00`, the real size, at **all six** header copies, since these images mirror the
original ROM in several places and correcting only the two documented positions leaves the scoring to
find a dishonest one. With that done snes9x stops choosing `Map_SDD1LoROMMap`.

**The layout is unknown to snes9x.** With an honest header it falls through to `Map_JumboLoROMMap`,
which is a different layout, and still renders nothing. The mapping these conversions need is the one
described in section 6, including the window rule for banks `$C0` and above, which cannot be expressed
with the existing `map_lorom` and `map_hirom_offset` helpers.

I raised this with snes9x as [issue 1081](https://github.com/snes9xgit/snes9x/issues/1081). My
`Map_SDD1DecompressedMap` implementation is ready in [`upstream/snes9x/`](upstream/snes9x/), and I am
holding it back until the detection mechanism is agreed. Trusting a corrected header only helps
conversions that fix theirs, which the circulating Star Ocean one does not, so a size-based fallback is
probably needed as well. That is the maintainers' call to make, not mine, which is why I asked before
sending a patch.

I expect the same gap in [ares](https://github.com/ares-emulator/ares),
[Mesen2](https://github.com/SourMesen/Mesen2), [bsnes](https://github.com/bsnes-emu/bsnes) and
[Mednafen](https://mednafen.github.io/), and the same patch shape should apply to all of them. BizHawk
embeds bsnes, so that one is covered by bsnes. I have not verified any of them against their own source
yet, and I am not sending anything until I have.

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

Two of them I had to fix after they distorted my own results, which is at the end of section 12.

---

## 21. Reproducing this

**TL;DR.** Everything here rebuilds from your own ROMs with Docker and Python 3. No ROM data is
distributed.

You supply the retail cartridges. Nothing in this repository contains game data, and nothing ever will.

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
```

Order matters. The sample and Shin Akuma patches apply to the retail ROM; the bypass must come next
because the re-layout reclaims the compressed data it reads; the header must come last because it
checksums the finished image.

For the Japanese build, substitute `asm/sdd1-bypass-jp.asm`, and supply the stream map from
[`maps/sfz2-jp.json`](maps/sfz2-jp.json) rather than a tagged ROM, since none exists for that region.

### Checking a stream map

```
python3 mapcheck.py roms/sfz2-jp-final.sfc maps/sfz2-jp.json
```

Reports duplicate sources, streams that fail to decode, and the worst key-scan distance against its
budget. A map that passes this can still be incomplete, which is what section 15 is about, but a map
that fails it is definitely broken.

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
| [`sdd1map.py`](sdd1map.py) | stream map extraction from a tagged ROM |
| [`sdd1sites.py`](sdd1sites.py) | finds every write to the chip's registers |
| [`sdd1tables.py`](sdd1tables.py) | builds and verifies the lookup tables |
| [`layout.py`](layout.py) | the interleaved address arithmetic |
| [`rombuild.py`](rombuild.py) | assembles the 96 Mbit image |
| [`mapcheck.py`](mapcheck.py) | validates a stream map offline |
| [`header.py`](header.py) | makes a converted image declare itself honestly |
| [`wdc65816.py`](wdc65816.py) | 65816 disassembler with M and X width tracking |
| [`spc700.py`](spc700.py) | SPC700 disassembler |
| [`emu65816.py`](emu65816.py) | minimal 65816 interpreter |
| [`patchrun.py`](patchrun.py) | executes the assembled patch against a memory model |
| [`spcfast.py`](spcfast.py) | applies the sample upload patch |
| [`shinakuma.py`](shinakuma.py) | applies the Shin Akuma unlock |
| [`build.py`](build.py) | Docker wrapper around asar |

Assembly that goes into the ROM lives in [`asm/`](asm/): the bypass patches for both regions, the shared
translate routine, the sample upload patch, and the Shin Akuma unlock for both regions.

Both disassemblers had their opcode tables extracted programmatically from reference implementations
rather than typed, and both are validated against known listings.

[`upstream/snes9x/`](upstream/snes9x/) holds the proposed emulator change: the map implementation and a
script that applies it to a checkout. The discussion is in
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

---

## Legal

No ROM data is distributed here. Everything in this repository operates on files you must already own.
The patches are derived from analysis of retail cartridges you supply.

The tooling, the assembly and this document are released under the [MIT licence](LICENSE), so that the
emulator mapper in [`upstream/snes9x/`](upstream/snes9x/) can be taken by projects whose own licences
range from GPL to snes9x's non-commercial terms. That covers my own work and nothing else. It grants no
rights in the game.
