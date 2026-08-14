// Street Fighter Alpha 2 and Star Ocean are the only two S-DD1 cartridges. Both
// have circulating conversions whose graphics were decompressed ahead of time so
// that the chip is no longer needed, which is what lets them run from flash
// cartridges. The decompressed data does not fit the original address space, so
// the conversions grow the image and address it in two halves: the upper half of
// each bank sits where LoROM would put it, and the lower half sits one whole
// image further into the file. Banks $C0 and above are a window composed from the
// lower halves of two other banks.
//
// No real S-DD1 cartridge is larger than Star Ocean's 48 Mbit, so an S-DD1 image
// at or above 64 Mbit is one of these conversions.

void CMemory::Map_SDD1DecompressedMap (void)
{
	const int	banks = (int) (CalculatedSize >> 16);

	map_System();

	for (int bank = 0; bank < 256; bank++)
	{
		if (bank == 0x7e || bank == 0x7f)
			continue;

		uint8	*low, *high;

		if (bank >= 0xc0)
		{
			const int	offset = bank - 0xc0;

			if (0x80 + offset >= banks || offset >= banks)
				continue;

			low  = ROM + (size_t) (0x80 + offset + banks) * 0x8000;
			high = ROM + (size_t) (offset + banks) * 0x8000 - 0x8000;
		}
		else
		{
			if (bank >= banks)
				continue;

			low  = ROM + (size_t) (bank + banks) * 0x8000;
			high = ROM + (size_t) bank * 0x8000 - 0x8000;
		}

		for (int block = 0; block < 16; block++)
		{
			const bool8	upper_half_only = (bank < 0x40) || (bank >= 0x80 && bank < 0xc0);

			if (block < 8 && upper_half_only)
				continue;

			const int	slot = (bank << 4) | block;

			Map[slot] = (block < 8) ? low : high;
			BlockIsROM[slot] = TRUE;
			BlockIsRAM[slot] = FALSE;
		}
	}

	map_WRAM();
	map_WriteProtectROM();
}
