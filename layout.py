BANK = 0x10000
HALF = 0x8000

WINDOW_FIRST_BANK = 0xC0
WINDOW_LOW_BASE = 0x80
WINDOW_HIGH_BASE = 0x00


def bank_count(size):
    if size % BANK:
        raise ValueError(f"{size} is not a whole number of 64K banks")
    return size // BANK


def snes_to_file(bank, addr, banks):
    if addr < HALF:
        return (bank + banks) * HALF + addr
    return bank * HALF + (addr - HALF)


def window_to_file(bank, addr, banks):
    offset = bank - WINDOW_FIRST_BANK
    base = WINDOW_LOW_BASE if addr < HALF else WINDOW_HIGH_BASE
    return (base + offset + banks) * HALF + (addr & (HALF - 1))


def address_to_file(bank, addr, banks):
    if bank >= WINDOW_FIRST_BANK:
        return window_to_file(bank, addr, banks)
    return snes_to_file(bank, addr, banks)


def file_to_snes(offset, banks):
    block, rest = divmod(offset, HALF)
    if block < banks:
        return block, HALF + rest
    return block - banks, rest


def interleave(logical):
    banks = bank_count(len(logical))
    image = bytearray(len(logical))
    for bank in range(banks):
        base = bank * BANK
        image[bank * HALF : (bank + 1) * HALF] = logical[base + HALF : base + BANK]
        image[(bank + banks) * HALF : (bank + banks + 1) * HALF] = logical[base : base + HALF]
    return bytes(image)


def deinterleave(image):
    banks = bank_count(len(image))
    logical = bytearray(len(image))
    for bank in range(banks):
        base = bank * BANK
        logical[base : base + HALF] = image[(bank + banks) * HALF : (bank + banks + 1) * HALF]
        logical[base + HALF : base + BANK] = image[bank * HALF : (bank + 1) * HALF]
    return bytes(logical)
