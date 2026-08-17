#include <cstddef>

#include "snes9x.h"
#include "memmap.h"

#include "windowed_lorom.h"

static const int SNES_BANKS = 256;
static const int BLOCKS_PER_BANK = 16;
static const int BLOCKS_PER_HALF = 8;
static const size_t HALF_BANK = 0x8000;
static const int WRAM_BANK_FIRST = 0x7E;
static const int WRAM_BANK_LAST = 0x7F;

static const int WINDOW_FIRST_BANK = 0xC0;
static const int WINDOW_LOW_SOURCE_BANK = 0x80;
static const int WINDOW_HIGH_SOURCE_BANK = 0x00;

static bool bank_exposes_only_its_high_half(int bank)
{
    return bank < 0x40 || (bank >= 0x80 && bank < 0xC0);
}

static bool bank_is_wram(int bank)
{
    return bank == WRAM_BANK_FIRST || bank == WRAM_BANK_LAST;
}

static uint8 *interleaved_low_half(int image_bank, int image_banks)
{
    return Memory.ROM + (size_t)(image_bank + image_banks) * HALF_BANK;
}

static uint8 *interleaved_high_half(int image_bank)
{
    return Memory.ROM + (size_t)image_bank * HALF_BANK - HALF_BANK;
}

void install_windowed_lorom_map(int mirror_shift)
{
    const int image_banks = (int)(Memory.CalculatedSize >> 16);
    if (image_banks <= 0) {
        return;
    }

    for (int bank = 0; bank < SNES_BANKS; bank++) {
        if (bank_is_wram(bank)) {
            continue;
        }

        uint8 *low = NULL;
        uint8 *high = NULL;

        if (mirror_shift == -3 && bank >= 0x60 && bank <= 0x7D) {
            const int n = bank - 0x60;
            low = Memory.ROM + (size_t)(2 * n) * HALF_BANK;
            high = Memory.ROM + (size_t)(2 * n + 1) * HALF_BANK - HALF_BANK;
        } else if (mirror_shift < 0 && bank >= WINDOW_FIRST_BANK) {
            const int offset = bank - WINDOW_FIRST_BANK;
            const int low_bank = WINDOW_LOW_SOURCE_BANK + offset;
            const int high_bank = WINDOW_HIGH_SOURCE_BANK + offset;
            if (low_bank >= image_banks || high_bank >= image_banks) {
                continue;
            }
            low = interleaved_low_half(low_bank, image_banks);
            high = interleaved_low_half(high_bank, image_banks) - HALF_BANK;
        } else {
            const int image_bank =
                bank < image_banks ? bank : bank - (mirror_shift < 0 ? 0 : mirror_shift);
            if (image_bank < 0 || image_bank >= image_banks) {
                continue;
            }
            low = interleaved_low_half(image_bank, image_banks);
            high = interleaved_high_half(image_bank);
        }

        for (int block = 0; block < BLOCKS_PER_BANK; block++) {
            const bool in_low_half = block < BLOCKS_PER_HALF;
            if (in_low_half && bank_exposes_only_its_high_half(bank)) {
                continue;
            }
            const int slot = (bank << 4) | block;
            Memory.Map[slot] = in_low_half ? low : high;
            Memory.BlockIsROM[slot] = TRUE;
            Memory.BlockIsRAM[slot] = FALSE;
        }
    }
}
