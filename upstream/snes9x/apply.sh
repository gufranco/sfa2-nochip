#!/bin/sh
set -e
SRC="$1"
UPSTREAM="${2:-$(cd "$(dirname "$0")" && pwd)}"

perl -0pi -e 's|(\tvoid\tMap_SDD1LoROMMap \(void\);)|$1\n\tvoid\tMap_SDD1DecompressedMap (void);|' "$SRC/memmap.h"

cat "$UPSTREAM/map_sdd1_decompressed.cpp" >> "$SRC/memmap.cpp"

perl -0pi -e 's/\tif \(HiROM\)\n\t\{\n\t\tif \(Settings\.BS\)\n\t\t\t\/\* Do nothing \*\/;\n\t\telse if \(Settings\.SPC7110\)/\tconst bool8\tSDD1Decompressed = (CalculatedSize >= 0x800000) &&\n\t\t\t(Settings.SDD1 ||\n\t\t\t strncmp(ROMName, "STREET FIGHTER ALPHA2", 21) == 0 ||\n\t\t\t strncmp(ROMName, "STREET FIGHTER ZERO2", 20) == 0 ||\n\t\t\t strncmp(ROMName, "Star Ocean", 10) == 0);\n\n\tif (SDD1Decompressed)\n\t{\n\t\tSettings.SDD1 = FALSE;\n\t\tMap_SDD1DecompressedMap();\n\t}\n\telse if (HiROM)\n\t{\n\t\tif (Settings.BS)\n\t\t\t\/* Do nothing *\/;\n\t\telse if (Settings.SPC7110)/' "$SRC/memmap.cpp"

grep -c "Map_SDD1DecompressedMap" "$SRC/memmap.cpp"
