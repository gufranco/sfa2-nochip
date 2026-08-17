#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include "libretro.h"
#include "snes9x.h"
#include "memmap.h"
#include "65c816.h"
#include "ppu.h"
#include "dma.h"
#include "bapu/snes/snes.hpp"

#include "windowed_lorom.h"

unsigned long sf_bank_reads[256];

static unsigned long loop_a_ipl, loop_a_drv, loop_b_ipl, loop_b_drv;
static unsigned long spc_pc_seen[64];
static unsigned long spc_pc_hits[64];

static void note_spc_pc(void)
{
    const unsigned long pc = (unsigned long)SNES::smp.regs.pc;
    for (int i = 0; i < 64; i++) {
        if (spc_pc_hits[i] == 0 || spc_pc_seen[i] == pc) {
            spc_pc_seen[i] = pc;
            spc_pc_hits[i]++;
            return;
        }
    }
}

static unsigned frames_seen = 0;
static unsigned long apu_writes_this_frame = 0;
static unsigned long apu_writer_pc[64];
static unsigned long apu_writer_hits[64];

#define WRITE_RING 512
static unsigned long ring_pc[WRITE_RING];
static unsigned long ring_addr[WRITE_RING];
static unsigned ring_stack[WRITE_RING];
static unsigned ring_frame[WRITE_RING];
static unsigned long ring_next = 0;

static bool blk_pending = false;
static unsigned blk_bank, blk_src, blk_len, blk_dest;
static unsigned blk_ok, blk_bad;
static unsigned long blk_writes;
static unsigned long cpu_pc_seen[64];
static unsigned long cpu_pc_hits[64];

static void verify_pending(void)
{
    if (!blk_pending) { return; }
    blk_pending = false;
    unsigned bad = 0, first = 0;
    for (unsigned i = 0; i < blk_len; i++) {
        const uint8 want = S9xGetByte((blk_bank << 16) | ((blk_src + i) & 0xFFFF));
        const uint8 got = SNES::smp.apuram[(blk_dest + i) & 0xFFFF];
        if (want != got) { if (!bad) { first = i; } bad++; }
    }
    printf("BLKEND src=%02X:%04X len=%u writes=%lu expect=%lu\n",
           blk_bank, blk_src, blk_len, blk_writes,
           (unsigned long)((blk_len + 1) / 2) * 3);
    if (bad) {
        blk_bad++;
        if (blk_bad <= 5) {
            printf("BLKBAD src=%02X:%04X dest=%04X len=%u bad=%u first=%u\n",
                   blk_bank, blk_src, blk_dest, blk_len, bad, first);
        }
    } else {
        blk_ok++;
    }
}

static uint32 vline_address(void)
{
    static int resolved = 0;
    static uint32 wanted = 0;
    if (!resolved) {
        resolved = 1;
        const char *text = getenv("SFVLINEAT");
        wanted = text ? (uint32)strtoul(text, NULL, 16) : 0x2100;
    }
    return wanted;
}

static unsigned long vline_samples = 0;
static unsigned long vline_total = 0;
static unsigned vline_low = 0xFFFF;
static unsigned vline_high = 0;
static unsigned long vline_histogram[16];

static uint32 poked_address(void)
{
    static uint32 wanted = 0xFFFFFFFF;
    if (wanted == 0xFFFFFFFF) {
        const char *text = getenv("SFPOKE");
        wanted = text ? (uint32)strtoul(text, NULL, 16) : 0;
    }
    return wanted;
}

static uint32 poked_length(void)
{
    static uint32 wanted = 0xFFFFFFFF;
    if (wanted == 0xFFFFFFFF) {
        const char *text = getenv("SFPOKELEN");
        wanted = text ? (uint32)strtoul(text, NULL, 16) : 1;
    }
    return wanted ? wanted : 1;
}

static void apply_forced_writes(void)
{
    const char *text = getenv("SFWRITE");
    if (!text) {
        return;
    }
    while (*text) {
        char *after_address = NULL;
        const unsigned long address = strtoul(text, &after_address, 16);
        if (after_address == text || *after_address != ':') {
            return;
        }
        const char *digits = after_address + 1;
        char *after_value = NULL;
        const unsigned long value = strtoul(digits, &after_value, 16);
        if (after_value == digits) {
            return;
        }
        Memory.RAM[address & 0x1FFFF] = (uint8)(value & 0xFF);
        if ((size_t)(after_value - digits) > 2) {
            Memory.RAM[(address + 1) & 0x1FFFF] = (uint8)((value >> 8) & 0xFF);
        }
        text = (*after_value == ',') ? after_value + 1 : after_value;
    }
}

static void note_poke_word(uint32 address)
{
    const uint32 wanted = poked_address();
    const unsigned bank = (address >> 16) & 0xFF;
    if (!wanted || (bank != 0x7E && address >= 0x2000)) {
        return;
    }
    const uint32 inside = address & 0xFFFF;
    if (inside < wanted || inside >= wanted + poked_length()) {
        return;
    }
    printf("POKE frame=%u addr=%06X pc=%06lX\n", frames_seen, (unsigned)address,
           (unsigned long)Registers.PBPC);
}

static void note_vline(uint32 address)
{
    if (!getenv("SFVLINE") || (address & 0xFFFF) != vline_address()) {
        return;
    }
    const char *pc_text = getenv("SFVLINEPC");
    if (pc_text) {
        const unsigned long wanted_pc = strtoul(pc_text, NULL, 16);
        if (((unsigned long)Registers.PBPC & 0xFFFFFF) != wanted_pc) {
            return;
        }
    }
    const unsigned line = (unsigned)CPU.V_Counter;
    if (vline_samples < 12 && getenv("SFVLINEPCS")) {
        printf("VLINEPC pc=%06lX addr=%06X line=%u\n", (unsigned long)Registers.PBPC,
               (unsigned)address, line);
    }
    vline_samples++;
    vline_total += line;
    if (line < vline_low) { vline_low = line; }
    if (line > vline_high) { vline_high = line; }
    vline_histogram[line < 256 ? line / 16 : 15]++;
}

static const uint32 PREFIGHT_TABLE_FIRST = 0x9440;
static const uint32 PREFIGHT_TABLE_LAST = 0x9440 + 0x6080;

static unsigned long prefight_writes = 0;
static unsigned prefight_first_frame = 0;
static unsigned prefight_last_frame = 0;
static unsigned prefight_busy_frames = 0;
static unsigned prefight_bursts = 0;
#define PREFIGHT_GAP 4

static const uint32 PLAYER_ONE_CHARACTER = 0x07A2;
static const uint32 PLAYER_TWO_CHARACTER = 0x0A22;
static const uint32 PLAYER_ONE_VARIANT = 0x1C20;

static const uint32 SOUND_GROUP_INDEX = 0x00008F;
static const uint32 SOUND_GROUP_IDS = 0x000080;
static const uint32 SOUND_ALLOC_LOW = 0x00008A;
static const uint32 SOUND_ALLOC_HIGH = 0x00008B;
static const uint32 SOUND_KEY_INDEX = 0x00008E;

extern "C" void sf_note_write_word(uint32 address)
{
    note_vline(address);
    note_poke_word(address);
    if (!getenv("SFTABLE")) {
        return;
    }
    const unsigned bank = (address >> 16) & 0xFF;
    const uint32 inside = address & 0xFFFF;
    if (bank != 0x7E && address >= 0x2000) {
        return;
    }
    if (inside < PREFIGHT_TABLE_FIRST || inside >= PREFIGHT_TABLE_LAST) {
        return;
    }
    if (prefight_writes == 0) {
        prefight_first_frame = frames_seen;
        prefight_bursts = 1;
        prefight_busy_frames = 1;
    } else if (frames_seen != prefight_last_frame) {
        prefight_busy_frames++;
        if (frames_seen > prefight_last_frame + PREFIGHT_GAP) {
            prefight_bursts++;
        }
    }
    prefight_last_frame = frames_seen;
    prefight_writes++;
}

static unsigned sound_list_id(void)
{
    return (unsigned)Memory.RAM[(Registers.S.W + 1) & 0x1FFF];
}

static void report_group_walk(void)
{
    const uint8 *page = Memory.RAM;
    printf("GROUP frame=%u pc=%06lX group=%02X ids=%02X,%02X,%02X alloc=%04X key=%02X list=%02X\n",
           frames_seen, (unsigned long)Registers.PBPC,
           (unsigned)page[SOUND_GROUP_INDEX],
           (unsigned)page[SOUND_GROUP_IDS],
           (unsigned)page[SOUND_GROUP_IDS + 1],
           (unsigned)page[SOUND_GROUP_IDS + 2],
           (unsigned)page[SOUND_ALLOC_LOW] | ((unsigned)page[SOUND_ALLOC_HIGH] << 8),
           (unsigned)page[SOUND_KEY_INDEX],
           sound_list_id());
}

static unsigned last_read_bank = 0xFFFF;
static unsigned char window_pages[64][256];
static unsigned long scan_run = 0;
static unsigned scan_start_addr = 0;

unsigned char sf_wram_touched[0x20000];

static bool ring_skipped(unsigned long pc)
{
    const char *ranges = getenv("SFRINGSKIP");
    if (!ranges) { return false; }
    unsigned long low = 0, high = 0;
    bool second = false;
    for (const char *p = ranges; ; p++) {
        const int digit = (*p >= '0' && *p <= '9') ? *p - '0'
                        : (*p >= 'a' && *p <= 'f') ? *p - 'a' + 10
                        : (*p >= 'A' && *p <= 'F') ? *p - 'A' + 10 : -1;
        if (digit >= 0) {
            if (second) { high = high * 16 + (unsigned long)digit; }
            else { low = low * 16 + (unsigned long)digit; }
            continue;
        }
        if (*p == '-') { second = true; continue; }
        if (second && pc >= low && pc <= high) { return true; }
        low = 0;
        high = 0;
        second = false;
        if (*p == 0) { return false; }
    }
}

static uint32 watched_address(void)
{
    static int resolved = 0;
    static uint32 wanted = 0;
    if (!resolved) {
        resolved = 1;
        const char *text = getenv("SFWATCH");
        wanted = text ? (uint32)strtoul(text, NULL, 16) : 0;
    }
    return wanted;
}

#define RECLAIM_MAX 4096
static unsigned reclaim_bank[RECLAIM_MAX];
static unsigned reclaim_start[RECLAIM_MAX];
static unsigned reclaim_end[RECLAIM_MAX];
static int reclaim_count = -1;
static unsigned long reclaim_hits = 0;
static unsigned long reclaim_pc[64];
static unsigned long reclaim_pc_hits[64];

static void load_reclaim(void)
{
    reclaim_count = 0;
    const char *path = getenv("SFRECLAIM");
    if (!path) { return; }
    FILE *in = fopen(path, "r");
    if (!in) { return; }
    unsigned b, s, e;
    while (reclaim_count < RECLAIM_MAX && fscanf(in, "%x %x %x", &b, &s, &e) == 3) {
        reclaim_bank[reclaim_count] = b;
        reclaim_start[reclaim_count] = s;
        reclaim_end[reclaim_count] = e;
        reclaim_count++;
    }
    fclose(in);
    printf("RECLAIM spans=%d\n", reclaim_count);
}

static void note_reclaim_read(uint32 address)
{
    if (reclaim_count < 0) { load_reclaim(); }
    if (reclaim_count == 0) { return; }
    const unsigned bank = (address >> 16) & 0xFF;
    if (bank < 0xC0) { return; }
    const unsigned inside = address & 0xFFFF;
    for (int i = 0; i < reclaim_count; i++) {
        if (reclaim_bank[i] == bank && inside >= reclaim_start[i] && inside < reclaim_end[i]) {
            reclaim_hits++;
            const unsigned long pc = (unsigned long)Registers.PBPC;
            for (int j = 0; j < 64; j++) {
                if (reclaim_pc_hits[j] == 0 || reclaim_pc[j] == pc) {
                    reclaim_pc[j] = pc; reclaim_pc_hits[j]++; return;
                }
            }
            return;
        }
    }
}

extern "C" void sf_note_read(uint32 address)
{
    note_reclaim_read(address);
    note_vline(address);
    const uint32 wanted = watched_address();
    if (wanted && address == wanted) {
        printf("WATCH frame=%u addr=%06X pc=%06lX\n", frames_seen, (unsigned)address,
               (unsigned long)Registers.PBPC);
    }
    if (getenv("SFREADRING") && !ring_skipped((unsigned long)Registers.PBPC)) {
        const unsigned long slot = ring_next++ % WRITE_RING;
        ring_pc[slot] = (unsigned long)Registers.PBPC;
        ring_addr[slot] = (unsigned long)address;
        ring_stack[slot] = (unsigned)Registers.S.W;
        ring_frame[slot] = frames_seen;
    }
    const unsigned bank = (address >> 16) & 0xFF;
    if (bank == 0x7E || bank == 0x7F) {
        sf_wram_touched[((bank - 0x7E) << 16) | (address & 0xFFFF)] = 1;
    } else if (address < 0x2000) {
        sf_wram_touched[address & 0x1FFF] = 1;
    }
    if (bank >= 0xC0) {
        window_pages[bank - 0xC0][(address >> 8) & 0xFF] = 1;
    }
    if (bank == 0x60) {
        if (last_read_bank != 0x60) { scan_run = 1; scan_start_addr = address & 0xFFFF; }
        else { scan_run++; }
    } else if (last_read_bank == 0x60 && scan_run && getenv("SFSCANLEN")) {
        printf("SCANLEN addr=%04X steps=%lu\n", scan_start_addr, scan_run);
        scan_run = 0;
    }
    if (bank == 0x60 && last_read_bank != 0x60 && getenv("SFSCAN")) {
        printf("SCAN addr=%04X ch0=%02X:%04X:%u:fixed%d ch1=%02X:%04X:%u:fixed%d ch7=%02X:%04X:%u:fixed%d\n",
               (unsigned)(address & 0xFFFF),
               (unsigned)DMA[0].ABank, (unsigned)DMA[0].AAddress, (unsigned)DMA[0].TransferBytes,
               (int)DMA[0].AAddressFixed,
               (unsigned)DMA[1].ABank, (unsigned)DMA[1].AAddress, (unsigned)DMA[1].TransferBytes,
               (int)DMA[1].AAddressFixed,
               (unsigned)DMA[7].ABank, (unsigned)DMA[7].AAddress, (unsigned)DMA[7].TransferBytes,
               (int)DMA[7].AAddressFixed);
    }
    last_read_bank = bank;
}

extern unsigned char sf_wram_touched[0x20000];

static void note_vram_dma(uint32 address)
{
    if ((address & 0xFFFF) != 0x420B || !getenv("SFVRAMDMA")) {
        return;
    }
    for (int i = 0; i < 8; i++) {
        const SDMA *d = &DMA[i];
        if (d->BAddress != 0x18 && d->BAddress != 0x19) {
            continue;
        }
        printf("VDMA frame=%u ch=%d vram=%04X src=%02X:%04X n=%u fixed=%d pc=%06lX\n",
               frames_seen, i, (unsigned)PPU.VMA.Address,
               (unsigned)d->ABank, (unsigned)d->AAddress,
               (unsigned)d->TransferBytes, (int)d->AAddressFixed,
               (unsigned long)Registers.PBPC);
    }
}

extern "C" void sf_note_write(uint32 address)
{
    note_vram_dma(address);
    note_poke_word(address);
    if (getenv("SFRING") && ((((unsigned long)Registers.PBPC >> 16) & 0xFF) == 0xC7
                            || (address & 0xFFFC) == 0x2140)) {
        const unsigned long slot = ring_next++ % WRITE_RING;
        ring_pc[slot] = (unsigned long)Registers.PBPC;
        ring_addr[slot] = (unsigned long)address;
        ring_stack[slot] = (unsigned)Registers.S.W;
        ring_frame[slot] = frames_seen;
    }
    const unsigned written = (address >> 16) & 0xFF;
    if (written == 0x7E || written == 0x7F) {
        sf_wram_touched[((written - 0x7E) << 16) | (address & 0xFFFF)] = 1;
    } else if (address < 0x2000) {
        sf_wram_touched[address & 0x1FFF] = 1;
    }
    note_vline(address);
    if (getenv("SFTABLE")) {
        const unsigned bank = (address >> 16) & 0xFF;
        const uint32 inside = address & 0xFFFF;
        if ((bank == 0x7E || address < 0x2000 || bank == 0x00)
            && inside >= PREFIGHT_TABLE_FIRST && inside < PREFIGHT_TABLE_LAST) {
            if (prefight_writes == 0) { prefight_first_frame = frames_seen; }
            prefight_last_frame = frames_seen;
            prefight_writes++;
        }
    }
    if (address == SOUND_GROUP_INDEX && ((((unsigned long)Registers.PBPC >> 16) & 0xFF) == 0xC7)
        && getenv("SFGROUP")) {
        report_group_walk();
    }
    if ((address & 0xFFFC) != 0x2140) {
        return;
    }
    apu_writes_this_frame++;
    blk_writes++;
    const unsigned long pc = (unsigned long)Registers.PBPC;
    if (getenv("SFVERIFY") && (pc == 0xC7056AUL || pc == 0xC70472UL || pc == 0xC7021CUL)) {
        verify_pending();
        blk_bank = (unsigned)Registers.DB;
        blk_src = (unsigned)Registers.Y.W;
        blk_len = (unsigned)Registers.X.W;
        if (pc == 0xC7056AUL || pc == 0xC7021CUL) {
            blk_dest = (unsigned)S9xGetByte((blk_bank << 16) | ((blk_src - 2) & 0xFFFF))
                     | ((unsigned)S9xGetByte((blk_bank << 16) | ((blk_src - 1) & 0xFFFF)) << 8);
        } else {
            const uint32 dp = (uint32)Registers.D.W;
            const unsigned tail = (unsigned)S9xGetByte(dp + 0x8A)
                                | ((unsigned)S9xGetByte(dp + 0x8B) << 8);
            blk_dest = (tail - blk_len) & 0xFFFF;
        }
        blk_pending = blk_len > 0 && blk_len < 0x8000;
        blk_writes = 0;
        printf("HDR pc=%06lX src=%02X:%04X len=%u dest=%04X\n", pc, blk_bank, blk_src, blk_len, blk_dest);
    }
    if (pc == 0xC704ADUL || pc == 0xC70256UL) {
        const unsigned spc = (unsigned)SNES::smp.regs.pc;
        const bool ipl = spc >= 0xFFC0;
        if (pc == 0xC70256UL) {
            if (ipl) { loop_a_ipl++; } else { loop_a_drv++; }
        } else {
            if (ipl) { loop_b_ipl++; } else { loop_b_drv++; }
        }
        note_spc_pc();
    }
    if (pc == 0xC70221UL && getenv("SFCALLER")) {
        const unsigned s = (unsigned)Registers.S.W;
        const unsigned ret = (unsigned)S9xGetByte(s + 3) | ((unsigned)S9xGetByte(s + 4) << 8);
        (void)ret;
        printf("CALLER s=%04X stack=%02X %02X %02X %02X %02X %02X %02X %02X spc=%s\n", s,
               S9xGetByte(s+1), S9xGetByte(s+2), S9xGetByte(s+3), S9xGetByte(s+4),
               S9xGetByte(s+5), S9xGetByte(s+6), S9xGetByte(s+7), S9xGetByte(s+8),
               SNES::smp.regs.pc >= 0xFFC0 ? "ipl" : "driver");
    }
    if (getenv("SFSESSION")) {
        if (pc >= 0xC701A5UL && pc <= 0xC701C0UL) { printf("OPEN frames=%u pc=%06lX\n", frames_seen, pc); }
        if (pc >= 0xC701DDUL && pc <= 0xC701F8UL) { printf("TERM frames=%u pc=%06lX\n", frames_seen, pc); }
        if (pc >= 0xC704EBUL && pc <= 0xC70540UL) { printf("ARM frames=%u pc=%06lX\n", frames_seen, pc); }
    }
    if ((pc == 0xC70221UL || pc == 0xC70478UL) && getenv("SFAPU")) {
        printf("BLOCK src=%02X:%04X len=%u\n",
               (unsigned)Registers.DB, (unsigned)Registers.Y.W, (unsigned)Registers.X.W);
    }
    for (int i = 0; i < 64; i++) {
        if (apu_writer_hits[i] == 0 || apu_writer_pc[i] == pc) {
            apu_writer_pc[i] = pc;
            apu_writer_hits[i]++;
            return;
        }
    }
}


static std::vector<uint16_t> frame;
static unsigned frame_width = 0;
static unsigned frame_height = 0;
static unsigned frame_pitch = 0;

static void cb_video(const void *data, unsigned width, unsigned height, size_t pitch)
{
    if (!data) {
        return;
    }
    frames_seen++;
    frame_width = width;
    frame_height = height;
    frame_pitch = (unsigned)(pitch / sizeof(uint16_t));
    frame.assign((const uint16_t *)data,
                 (const uint16_t *)data + frame_pitch * height);
}

static void cb_audio(int16_t, int16_t) {}
static size_t cb_audio_batch(const int16_t *, size_t frames) { return frames; }
static void cb_input_poll(void) {}
static bool start_pressed = false;

static bool confirm_pressed = false;
static bool left_pressed = false;
static bool right_pressed = false;
static bool down_pressed = false;
static bool up_pressed = false;
static int attack_button = -1;
static unsigned char char_seen[256];
static unsigned char variant_seen[256];

static int16_t cb_input_state(unsigned port, unsigned, unsigned, unsigned id)
{
    if (port != 0) {
        return 0;
    }
    if (start_pressed && id == RETRO_DEVICE_ID_JOYPAD_START) {
        return 1;
    }
    if (confirm_pressed && id == RETRO_DEVICE_ID_JOYPAD_A) {
        return 1;
    }
    if (left_pressed && id == RETRO_DEVICE_ID_JOYPAD_LEFT) {
        return 1;
    }
    if (right_pressed && id == RETRO_DEVICE_ID_JOYPAD_RIGHT) {
        return 1;
    }
    if (down_pressed && id == RETRO_DEVICE_ID_JOYPAD_DOWN) {
        return 1;
    }
    if (up_pressed && id == RETRO_DEVICE_ID_JOYPAD_UP) {
        return 1;
    }
    if (attack_button >= 0 && (int)id == attack_button) {
        return 1;
    }
    return 0;
}

static bool cb_environment(unsigned cmd, void *data)
{
    switch (cmd) {
    case RETRO_ENVIRONMENT_GET_SYSTEM_DIRECTORY:
    case RETRO_ENVIRONMENT_GET_SAVE_DIRECTORY:
        *(const char **)data = ".";
        return true;
    case RETRO_ENVIRONMENT_SET_PIXEL_FORMAT:
    case RETRO_ENVIRONMENT_SET_PERFORMANCE_LEVEL:
    case RETRO_ENVIRONMENT_SET_INPUT_DESCRIPTORS:
    case RETRO_ENVIRONMENT_SET_VARIABLES:
    case RETRO_ENVIRONMENT_SET_MEMORY_MAPS:
    case RETRO_ENVIRONMENT_SET_GEOMETRY:
    case RETRO_ENVIRONMENT_SET_SUPPORT_ACHIEVEMENTS:
        return true;
    case RETRO_ENVIRONMENT_GET_VARIABLE_UPDATE:
        *(bool *)data = false;
        return true;
    default:
        return false;
    }
}

static uint8 mapped_byte(uint32 address)
{
    uint8 *const block = Memory.Map[(address >> 12) & 0xFFF];
    if ((size_t)block <= (size_t)CMemory::MAP_LAST) {
        return 0xFF;
    }
    return block[address & 0xFFFF];
}

static void report_probes(void)
{
    static const uint32 probes[] = {
        0x00FFFC, 0x00FFFD, 0x00FEC1, 0x008000,
        0x600000, 0x610000, 0x620000, 0x630000,
        0xC00000, 0xC08000,
    };
    printf("PROBE");
    for (size_t i = 0; i < sizeof(probes) / sizeof(probes[0]); i++) {
        printf(" %06X=%02X", probes[i], mapped_byte(probes[i]));
    }
    printf("\n");
}

static double frame_brightness(void)
{
    if (frame.empty() || frame_width == 0) {
        return -1.0;
    }
    double total = 0.0;
    for (unsigned y = 0; y < frame_height; y++) {
        for (unsigned x = 0; x < frame_width; x++) {
            const uint16_t pixel = frame[y * frame_pitch + x];
            total += ((pixel >> 11) & 0x1F) * 8 + ((pixel >> 5) & 0x3F) * 4 + (pixel & 0x1F) * 8;
        }
    }
    return total / (double)(frame_width * frame_height * 3);
}

static unsigned long long frame_hash(void)
{
    unsigned long long hash = 1469598103934665603ULL;
    for (unsigned y = 0; y < frame_height; y++) {
        for (unsigned x = 0; x < frame_width; x++) {
            hash ^= (unsigned long long)frame[y * frame_pitch + x];
            hash *= 1099511628211ULL;
        }
    }
    return hash;
}

static void write_ppm(const char *path)
{
    if (frame.empty() || frame_width == 0) {
        return;
    }
    FILE *out = fopen(path, "wb");
    if (!out) {
        return;
    }
    fprintf(out, "P6\n%u %u\n255\n", frame_width, frame_height);
    for (unsigned y = 0; y < frame_height; y++) {
        for (unsigned x = 0; x < frame_width; x++) {
            const uint16_t pixel = frame[y * frame_pitch + x];
            const unsigned char rgb[3] = {
                (unsigned char)(((pixel >> 11) & 0x1F) << 3),
                (unsigned char)(((pixel >> 5) & 0x3F) << 2),
                (unsigned char)((pixel & 0x1F) << 3),
            };
            fwrite(rgb, 1, 3, out);
        }
    }
    fclose(out);
}

static bool read_file(const char *path, std::vector<unsigned char> &out)
{
    FILE *file = fopen(path, "rb");
    if (!file) {
        return false;
    }
    fseek(file, 0, SEEK_END);
    const long size = ftell(file);
    fseek(file, 0, SEEK_SET);
    out.resize((size_t)size);
    const bool complete = fread(out.data(), 1, (size_t)size, file) == (size_t)size;
    fclose(file);
    return complete;
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "usage: sfemu <rom> <frames> [-1 stock | -2 window rule | shift] [out.ppm]\n");
        return 2;
    }

    const int frames_to_run = atoi(argv[2]);
    const int mirror_shift = argc > 3 ? atoi(argv[3]) : 0;
    const char *ppm_path = argc > 4 ? argv[4] : NULL;

    std::vector<unsigned char> rom;
    if (!read_file(argv[1], rom)) {
        fprintf(stderr, "cannot read %s\n", argv[1]);
        return 1;
    }

    retro_set_environment(cb_environment);
    retro_set_video_refresh(cb_video);
    retro_set_audio_sample(cb_audio);
    retro_set_audio_sample_batch(cb_audio_batch);
    retro_set_input_poll(cb_input_poll);
    retro_set_input_state(cb_input_state);
    retro_init();

    retro_game_info info;
    memset(&info, 0, sizeof(info));
    info.path = argv[1];
    info.data = rom.data();
    info.size = rom.size();

    if (!retro_load_game(&info)) {
        printf("RESULT load=failed\n");
        return 1;
    }

    const bool use_windowed_lorom_map = mirror_shift != -1;
    if (use_windowed_lorom_map) {
        if (Memory.ROM && Memory.MAX_ROM_SIZE >= rom.size()) {
            memcpy(Memory.ROM, rom.data(), rom.size());
        }
        Memory.CalculatedSize = (uint32)rom.size();
        if (mirror_shift != -4) {
            Settings.SDD1 = FALSE;
        }

        install_windowed_lorom_map(mirror_shift);
        S9xReset();
        install_windowed_lorom_map(mirror_shift);
    }

    report_probes();

    static unsigned char wram_shadow[0x20000];
    memcpy(wram_shadow, Memory.RAM, sizeof(wram_shadow));

    unsigned portrait_id = 0xFFFF;
    int portrait_wait = 0;
    unsigned char portrait_done[256] = {0};

    FILE *hash_out = getenv("SFHASH") ? fopen(getenv("SFHASH"), "w") : NULL;
    const int dump_first = getenv("SFDUMPFIRST") ? atoi(getenv("SFDUMPFIRST")) : 0;
    const int dump_count = getenv("SFDUMPCOUNT") ? atoi(getenv("SFDUMPCOUNT")) : 0;

    unsigned samples = 0;
    uint32 previous = 0xFFFFFFFF;
    for (int i = 0; i < frames_to_run; i++) {
        start_pressed = (i % 240) >= 200;
        confirm_pressed = (i % 180) >= 150;
        if (getenv("SFIDLE")) {
            start_pressed = confirm_pressed = false;
            left_pressed = right_pressed = up_pressed = down_pressed = false;
        } else if (getenv("SFGRID")) {
            const int settle = getenv("SFSETTLE") ? atoi(getenv("SFSETTLE")) : 90;
            const int step = i / settle;
            start_pressed = (i % 300) >= 260;
            confirm_pressed = (i % 300) >= 240 && (i % 300) < 250;
            const bool tick = (i % settle) < 4;
            right_pressed = tick && (step % 6) != 5;
            down_pressed  = tick && (step % 6) == 5;
            left_pressed = up_pressed = false;
            if (getenv("SFSEEN")) {
                char_seen[Memory.RAM[0x07A2]] = 1;
            }
        } else if (getenv("SFTOUR")) {
            const int budget = getenv("SFTOURBUDGET") ? atoi(getenv("SFTOURBUDGET")) : 7200;
            const int roster = getenv("SFTOURROSTER") ? atoi(getenv("SFTOURROSTER")) : 18;
            const int slot = i % budget;
            const int target = (i / budget) % roster;

            if (slot == 0 && i > 0) {
                S9xReset();
                blk_pending = false;
                if (use_windowed_lorom_map) {
                    install_windowed_lorom_map(mirror_shift);
                }
                printf("TOUR character=%d frame=%d\n", target, i);
                fflush(stdout);
            }

            start_pressed = false;
            confirm_pressed = false;
            left_pressed = right_pressed = down_pressed = up_pressed = false;

            const bool menu_with_confirm = getenv("SFTOURCONFIRM") != NULL;
            if (slot < 3000) {
                if (menu_with_confirm) {
                    start_pressed = (slot % 240) < 8;
                    confirm_pressed = (slot % 60) >= 30 && (slot % 60) < 38;
                } else {
                    start_pressed = (slot % 60) < 8;
                }
            } else if (slot < 4200) {
                const int columns = getenv("SFTOURCOLUMNS") ? atoi(getenv("SFTOURCOLUMNS")) : 5;
                const int rights = target % columns;
                const int downs = target / columns;
                const int press = (slot - 3000) / 24;
                const bool tick = ((slot - 3000) % 24) < 5;
                right_pressed = tick && press < rights;
                down_pressed = tick && press >= rights && press < rights + downs;
            } else if (slot < 4400) {
                confirm_pressed = (slot % 25) < 10;
            } else if (slot >= budget - 1500) {
                confirm_pressed = ((slot - (budget - 1500)) % 50) < 10;
                start_pressed = ((slot - (budget - 1500)) % 90) < 10;
            }
        } else if (getenv("SFSCENE")) {
            const char *wanted = getenv("SFSCENE");
            const unsigned long first = strtoul(wanted, NULL, 16);
            const char *comma = strchr(wanted, ',');
            const unsigned long second = comma ? strtoul(comma + 1, NULL, 16) : first;
            Memory.RAM[PLAYER_ONE_CHARACTER] = (uint8)first;
            Memory.RAM[PLAYER_TWO_CHARACTER] = (uint8)second;
            if (getenv("SFSCENEVARIANT")) {
                const unsigned long variant = strtoul(getenv("SFSCENEVARIANT"), NULL, 16);
                Memory.RAM[PLAYER_ONE_VARIANT] = (uint8)variant;
            }
            const int menu = getenv("SFSCENEMENU") ? atoi(getenv("SFSCENEMENU")) : 1800;
            start_pressed = i < menu && (i % 60) < 8;
            confirm_pressed = i < menu && (i % 40) < 12;
            left_pressed = right_pressed = down_pressed = up_pressed = false;
            attack_button = -1;
            if (i >= menu && getenv("SFSCENECONTINUE")) {
                const int every =
                    getenv("SFSCENECONTINUE")[0] ? atoi(getenv("SFSCENECONTINUE")) : 0;
                const int period = every > 0 ? every : 240;
                start_pressed = (i % period) < 8;
                confirm_pressed = (i % period) >= 40 && (i % period) < 48;
            }
            if (i >= menu && getenv("SFSCENEJUMP")) {
                static const int attacks[] = {
                    RETRO_DEVICE_ID_JOYPAD_Y, RETRO_DEVICE_ID_JOYPAD_X,
                    RETRO_DEVICE_ID_JOYPAD_L, RETRO_DEVICE_ID_JOYPAD_B,
                    RETRO_DEVICE_ID_JOYPAD_A, RETRO_DEVICE_ID_JOYPAD_R,
                };
                const int cycle = (i - menu) / 90;
                const int step = (i - menu) % 90;
                up_pressed = step < 12;
                if (step >= 26 && step < 34) {
                    attack_button = attacks[cycle % 6];
                }
            }
        } else if (getenv("SFFORCE")) {
            Memory.RAM[PLAYER_ONE_CHARACTER] = 0x02;
            start_pressed = true;
            confirm_pressed = (i % 40) < 12;
            left_pressed = right_pressed = down_pressed = up_pressed = false;
        } else if (getenv("SFDRIVE")) {
            const unsigned cur = Memory.RAM[0x07A2];
            const bool on_akuma = (cur == 0x02);
            start_pressed = on_akuma ? true : ((i % 240) >= 200);
            confirm_pressed = on_akuma ? ((i % 40) < 12) : ((i % 60) < 20);
            const int phase = (i / 150) % 4;
            const bool tick = (i % 24) < 6;
            right_pressed = (!on_akuma && tick && phase == 0);
            left_pressed  = (!on_akuma && tick && phase == 1);
            down_pressed  = (!on_akuma && tick && phase == 2);
            up_pressed    = (!on_akuma && tick && phase == 3);
        } else {
            left_pressed = (i % 97) < 8;
            right_pressed = (i % 131) < 8;
            down_pressed = (i % 211) < 6;
            up_pressed = false;
        }
        if (getenv("SFSELECT")) {
            char_seen[Memory.RAM[0x07A2]] = 1;
            variant_seen[Memory.RAM[0x1C20]] = 1;
        }
        apply_forced_writes();
        apu_writes_this_frame = 0;
        retro_run();
        if (getenv("SFPC")) {
            const unsigned long cpc = (unsigned long)Registers.PBPC;
            int j = 0;
            for (; j < 64; j++) {
                if (cpu_pc_hits[j] == 0 || cpu_pc_seen[j] == cpc) {
                    cpu_pc_seen[j] = cpc; cpu_pc_hits[j]++; break;
                }
            }
        }
        const int tick_every = getenv("SFTICK") ? atoi(getenv("SFTICK")) : 0;
        if (tick_every > 0 && (i % tick_every) == 0) {
            printf("TICK frame=%d main=%02X nmi=%02X ready=%02X busy=%02X mode=%02X port0=%02X spc=%04X\n",
                   i, (unsigned)Memory.RAM[0x1A96], (unsigned)Memory.RAM[0x1A9A],
                   (unsigned)Memory.RAM[0x1A99], (unsigned)Memory.RAM[0x1A9C],
                   (unsigned)Memory.RAM[0x1A9D], (unsigned)SNES::smp.apuram[0xF4],
                   (unsigned)SNES::smp.regs.pc);
        }
        const int bright_every = getenv("SFBRIGHT") ? atoi(getenv("SFBRIGHT")) : 0;
        if (bright_every > 0 && (i % bright_every) == bright_every - 1) {
            printf("BRIGHT frame=%d value=%.1f char=%02X\n", i, frame_brightness(),
                   (unsigned)Memory.RAM[PLAYER_ONE_CHARACTER]);
        }
        if (getenv("SFPORTRAIT")) {
            const unsigned id = Memory.RAM[0x07A2];
            if (id != portrait_id) {
                portrait_id = id;
                portrait_wait = getenv("SFPORTRAITWAIT") ? atoi(getenv("SFPORTRAITWAIT")) : 45;
            } else if (portrait_wait > 0 && --portrait_wait == 0 && !portrait_done[id]) {
                char named[512];
                snprintf(named, sizeof(named), "%s/char-%02X.ppm", getenv("SFPORTRAIT"), id);
                write_ppm(named);
                portrait_done[id] = 1;
                printf("PORTRAIT id=%02X frame=%d\n", id, i);
            }
        }
        if (getenv("SFSTATE")) {
            const unsigned background_state_in_wram = 0x10A00;
            const uint8 *state = &Memory.RAM[background_state_in_wram];
            printf("STATE frame=%d pairs=%u busy=%u walk=%u flight=%u"
                   " cursor=%04X dest=%04X ticket=%02X fe=%02X ready=%04X ticks=%u opens=%u parks=%u slices=%u closes=%u\n",
                   i,
                   (unsigned)(state[0] | (state[1] << 8)),
                   (unsigned)state[0x0A], (unsigned)state[0x0B], (unsigned)state[0x0C],
                   (unsigned)(state[0x0E] | (state[0x0F] << 8)),
                   (unsigned)(state[0x12] | (state[0x13] << 8)),
                   (unsigned)state[0x14],
                   (unsigned)Memory.RAM[0x00FE],
                   (unsigned)(state[0x18] | (state[0x19] << 8)),
                   (unsigned)(state[0x1A] | (state[0x1B] << 8)),
                   (unsigned)(state[0x1C] | (state[0x1D] << 8)),
                   (unsigned)(state[0x1E] | (state[0x1F] << 8)),
                   (unsigned)(state[0x20] | (state[0x21] << 8)),
                   (unsigned)(state[0x22] | (state[0x23] << 8)));
        }
        if (getenv("SFWRAM")) {
            const int watched = getenv("SFWRAMSIZE") ? atoi(getenv("SFWRAMSIZE")) : 0x2000;
            unsigned changed = 0;
            for (int address = 0; address < watched; address++) {
                const uint8 now = Memory.RAM[address];
                if (now != wram_shadow[address]) {
                    changed++;
                    wram_shadow[address] = now;
                }
            }
            printf("WRAM frame=%d changed=%u\n", i, changed);
        }
        if (hash_out) {
            fprintf(hash_out, "%d %016llx\n", i, frame_hash());
        }
        const int shot_every = getenv("SFSHOTEVERY") ? atoi(getenv("SFSHOTEVERY")) : 0;
        if (shot_every > 0 && getenv("SFDUMP") && (i % shot_every) == 0) {
            char numbered[512];
            snprintf(numbered, sizeof(numbered), "%s/%07d.ppm", getenv("SFDUMP"), i);
            write_ppm(numbered);
        }
        if (getenv("SFDUMP") && dump_count > 0 && i >= dump_first && i < dump_first + dump_count) {
            char numbered[512];
            snprintf(numbered, sizeof(numbered), "%s/%06d.ppm", getenv("SFDUMP"), i);
            write_ppm(numbered);
        }
        if (getenv("SFSHOTS") && (i % 1500) == 1499) {
            char path[512];
            snprintf(path, sizeof(path), "%s-%05d.ppm", getenv("SFSHOTS"), i);
            write_ppm(path);
        }
        if (getenv("SFAPU") && apu_writes_this_frame > 16) {
            printf("APU frame=%d writes=%lu\n", i, apu_writes_this_frame);
        }
        if (Registers.PBPC != previous && samples < 8) {
            printf("TRACE frame=%d pbpc=%06X\n", i, (unsigned)Registers.PBPC);
            previous = Registers.PBPC;
            samples++;
        }
        if (ppm_path && i > 0 && i % 600 == 0) {
            char numbered[512];
            snprintf(numbered, sizeof(numbered), "%s.%04d.ppm", ppm_path, i);
            write_ppm(numbered);
        }
    }

    unsigned long lit_pixels = 0;
    unsigned long lit_rows = 0;
    for (unsigned y = 0; y < frame_height; y++) {
        bool row_has_light = false;
        for (unsigned x = 0; x < frame_width; x++) {
            if (frame[y * frame_pitch + x] != 0) {
                lit_pixels++;
                row_has_light = true;
            }
        }
        lit_rows += row_has_light ? 1 : 0;
    }

    if (getenv("SFFLAG")) {
        printf("FLAG $1B09=%04X  $1B05=%04X\n",
               (unsigned)S9xGetByte(0x7E1B09) | ((unsigned)S9xGetByte(0x7E1B0A) << 8),
               (unsigned)S9xGetByte(0x7E1B05) | ((unsigned)S9xGetByte(0x7E1B06) << 8));
    }
    if (getenv("SFSELECT")) {
        printf("CHARS");
        for (int i = 0; i < 256; i++) { if (char_seen[i]) printf(" %02X", i); }
        printf("\nVARIANTS");
        for (int i = 0; i < 256; i++) { if (variant_seen[i]) printf(" %02X", i); }
        printf("\n");
    }
    if (getenv("SFPPU")) {
        printf("PPUSTATE brightness=%u forced=%u screen=%02X frames_seen=%u\n",
               (unsigned)PPU.Brightness, (unsigned)PPU.ForcedBlanking,
               (unsigned)Memory.FillRAM[0x212c], frames_seen);
    }
    if (getenv("SFPAGES")) {
        FILE *out = fopen(getenv("SFPAGES"), "wb");
        if (out) { fwrite(window_pages, 1, sizeof(window_pages), out); fclose(out); }
    }
    if (getenv("SFPC")) {
        for (int i = 0; i < 64 && cpu_pc_hits[i]; i++) {
            printf("CPUPC pc=%06lX frames=%lu\n", cpu_pc_seen[i], cpu_pc_hits[i]);
        }
    }
    if (getenv("SFVERIFY")) {
        verify_pending();
        printf("BLOCKS ok=%u bad=%u\n", blk_ok, blk_bad);
    }
    if (getenv("SFAPURAM")) {
        printf("LOOPS c70256_ipl=%lu c70256_drv=%lu c704ad_ipl=%lu c704ad_drv=%lu\n",
               loop_a_ipl, loop_a_drv, loop_b_ipl, loop_b_drv);
        printf("STUCK cpu=%06lX spc=%04X ya=%04X x=%02X port0=%02X port1=%02X port2=%02X\n",
               (unsigned long)Registers.PBPC, (unsigned)SNES::smp.regs.pc,
               (unsigned)SNES::smp.regs.ya, (unsigned)SNES::smp.regs.x,
               (unsigned)SNES::smp.apuram[0xF4], (unsigned)SNES::smp.apuram[0xF5],
               (unsigned)SNES::smp.apuram[0xF6]);
        FILE *out = fopen(getenv("SFAPURAM"), "wb");
        if (out) {
            fwrite(SNES::smp.apuram, 1, 0x10000, out);
            fclose(out);
        }
        for (int i = 0; i < 64 && spc_pc_hits[i]; i++) {
            printf("SPCPC pc=%04lX hits=%lu\n", spc_pc_seen[i], spc_pc_hits[i]);
        }
    }
    if (getenv("SFAPU")) {
        for (int i = 0; i < 64 && apu_writer_hits[i]; i++) {
            printf("APUPC pc=%06lX writes=%lu\n", apu_writer_pc[i], apu_writer_hits[i]);
        }
    }
    if (getenv("SFRECLAIM")) {
        printf("RECLAIMREAD hits=%lu\n", reclaim_hits);
        for (int i = 0; i < 64 && reclaim_pc_hits[i]; i++) {
            printf("RECLAIMPC pc=%06lX reads=%lu\n", reclaim_pc[i], reclaim_pc_hits[i]);
        }
    }
    if (getenv("SFWRAMMAP")) {
        unsigned run_start = 0, best_start = 0, best_len = 0, len = 0;
        for (unsigned address = 0; address <= 0x20000; address++) {
            const bool free_here = address < 0x20000 && !sf_wram_touched[address];
            if (free_here) {
                if (len == 0) { run_start = address; }
                len++;
            } else {
                if (len > best_len) { best_len = len; best_start = run_start; }
                if (len >= 64) { printf("WRAMFREE start=%05X len=%u\n", run_start, len); }
                len = 0;
            }
        }
        printf("WRAMFREE largest start=%05X len=%u\n", best_start, best_len);
    }
    if (getenv("SFREADS")) {
        for (int bank = 0; bank < 256; bank++) {
            if (sf_bank_reads[bank]) {
                printf("READS bank=%02X count=%lu\n", bank, sf_bank_reads[bank]);
            }
        }
    }
    if (getenv("SFRING") || getenv("SFREADRING")) {
        const unsigned long shown = ring_next < WRITE_RING ? ring_next : WRITE_RING;
        for (unsigned long i = 0; i < shown; i++) {
            const unsigned long slot = (ring_next - shown + i) % WRITE_RING;
            printf("RING frame=%u pc=%06lX addr=%06lX s=%04X\n",
                   ring_frame[slot], ring_pc[slot], ring_addr[slot], ring_stack[slot]);
        }
    }
    if (getenv("SFWRAM")) {
        FILE *out = fopen(getenv("SFWRAM"), "wb");
        if (out) { fwrite(Memory.RAM, 1, 0x20000, out); fclose(out); }
    }
    if (getenv("SFVLINE") && vline_samples) {
        printf("VLINE samples=%lu mean=%.1f low=%u high=%u\n", vline_samples,
               (double)vline_total / (double)vline_samples, vline_low, vline_high);
        for (int slot = 0; slot < 16; slot++) {
            if (vline_histogram[slot]) {
                printf("VLINEBIN %3d-%3d %lu\n", slot * 16, slot * 16 + 15, vline_histogram[slot]);
            }
        }
    }
    if (getenv("SFTABLE")) {
        printf("TABLE writes=%lu first=%u last=%u busy=%u bursts=%u\n", prefight_writes,
               prefight_first_frame, prefight_last_frame, prefight_busy_frames,
               prefight_bursts);
    }
    printf("CPU pbpc=%06X sdd1=%d\n", (unsigned)Registers.PBPC, (int)Settings.SDD1);
    printf("RESULT load=ok frames=%u size=%ux%u lit=%lu rows=%lu banks=%u\n",
           frames_seen, frame_width, frame_height, lit_pixels, lit_rows,
           (unsigned)(Memory.CalculatedSize >> 16));

    if (ppm_path) {
        write_ppm(ppm_path);
        char name[512];
        snprintf(name, sizeof(name), "%s.vram", ppm_path);
        FILE *v = fopen(name, "wb");
        if (v) { fwrite(Memory.VRAM, 1, 0x10000, v); fclose(v); }
        snprintf(name, sizeof(name), "%s.oam", ppm_path);
        FILE *o = fopen(name, "wb");
        if (o) { fwrite(PPU.OAMData, 1, 544, o); fclose(o); }
        snprintf(name, sizeof(name), "%s.cgram", ppm_path);
        FILE *c = fopen(name, "wb");
        if (c) { fwrite(PPU.CGDATA, 2, 256, c); fclose(c); }
    }
    retro_unload_game();
    retro_deinit();
    return 0;
}
