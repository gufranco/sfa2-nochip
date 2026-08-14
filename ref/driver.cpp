#include <cstdio>
#include <vector>

#include "port.h"
#include "sdd1emu.h"

static const size_t MAX_LENGTH = 0x10000;

static bool read_exact(void *dest, size_t size) {
    return fread(dest, 1, size, stdin) == size;
}

static bool read_u32(uint32_t *out) {
    unsigned char raw[4];
    if (!read_exact(raw, sizeof(raw))) {
        return false;
    }
    *out = (uint32_t)raw[0] | ((uint32_t)raw[1] << 8) | ((uint32_t)raw[2] << 16) |
           ((uint32_t)raw[3] << 24);
    return true;
}

int main(void) {
    uint32_t rom_size = 0;
    if (!read_u32(&rom_size)) {
        return 1;
    }

    std::vector<uint8> rom((size_t)rom_size + MAX_LENGTH, 0);
    if (rom_size != 0 && !read_exact(rom.data(), rom_size)) {
        return 1;
    }

    uint32_t count = 0;
    if (!read_u32(&count)) {
        return 1;
    }

    std::vector<uint8> out(MAX_LENGTH, 0);
    for (uint32_t index = 0; index < count; index++) {
        uint32_t offset = 0;
        uint32_t length = 0;
        if (!read_u32(&offset) || !read_u32(&length)) {
            return 1;
        }
        if (offset >= rom_size || length > MAX_LENGTH) {
            return 2;
        }

        size_t produced = length != 0 ? (size_t)length : MAX_LENGTH;
        SDD1_decompress(out.data(), rom.data() + offset, (int)length);
        if (fwrite(out.data(), 1, produced, stdout) != produced) {
            return 1;
        }
    }
    return 0;
}
