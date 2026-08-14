#!/bin/sh
# Applies the S-DD1 decompressed-conversion support to a snes9x checkout.
set -e
SRC="$1"
sed -i 's|^\tvoid\tMap_SDD1LoROMMap (void);|\tvoid\tMap_SDD1LoROMMap (void);\n\tvoid\tMap_SDD1DecompressedMap (void);|' "$SRC/memmap.h"
cat /upstream/map_sdd1_decompressed.cpp >> "$SRC/memmap.cpp"
perl -0pi -e 's/(\t\telse if \(Settings\.SDD1\)\n)(\t\t\tMap_SDD1LoROMMap\(\);\n)/$1\t\t{\n\t\t\tif (CalculatedSize >= 0x800000)\n\t\t\t{\n\t\t\t\tSettings.SDD1 = FALSE;\n\t\t\t\tMap_SDD1DecompressedMap();\n\t\t\t}\n\t\t\telse\n\t\t\t\tMap_SDD1LoROMMap();\n\t\t}\n/' "$SRC/memmap.cpp"
grep -c "Map_SDD1DecompressedMap" "$SRC/memmap.cpp"
