FROM debian:bookworm-slim AS build

ARG SNES9X_REF=1.63
ARG SDD1EMU_SHA256=a5f9733418ae913e8ebb358b7dde55504a88b2b035aadaf5496e229071b30770

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git ca-certificates make \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 --branch "${SNES9X_REF}" \
        https://github.com/snes9xgit/snes9x.git /src/snes9x

RUN echo "${SDD1EMU_SHA256}  /src/snes9x/sdd1emu.cpp" | sha256sum --check --strict

RUN sed -i 's|^inline uint8 S9xGetByte (uint32 Address)\n{|&|' /src/snes9x/getset.h \
    && sed -i 's|^inline uint8 S9xGetByte (uint32 Address)$|extern unsigned long sf_bank_reads[256];\ninline uint8 S9xGetByte (uint32 Address)|' /src/snes9x/getset.h \
    && sed -i '0,/^{$/{}' /src/snes9x/getset.h \
    && perl -0pi -e 's/(inline uint8 S9xGetByte \(uint32 Address\)\n\{)/$1\n\tsf_bank_reads[(Address >> 16) & 0xFF]++;/' /src/snes9x/getset.h \
    && grep -c "sf_bank_reads" /src/snes9x/getset.h

RUN perl -0pi -e 's/(inline void S9xSetByte \(uint8 Byte, uint32 Address\)\n\{)/extern "C" void sf_note_write(uint32);\n$1\n\tsf_note_write(Address);/' /src/snes9x/getset.h \
    && grep -c "sf_note_write" /src/snes9x/getset.h

RUN perl -0pi -e 's/(\tsf_bank_reads\[\(Address >> 16\) & 0xFF\]\+\+;)/$1\n\tsf_note_read(Address);/' /src/snes9x/getset.h \
    && perl -0pi -e 's/(extern unsigned long sf_bank_reads\[256\];)/$1\nextern "C" void sf_note_read(uint32);/' /src/snes9x/getset.h \
    && grep -c "sf_note_read" /src/snes9x/getset.h

RUN sed -i 's|\tint32\tcount = d->TransferBytes;|\tint32\tcount = d->TransferBytes;\n\tif (getenv("SFDMA")) fprintf(stderr, "DMA ch=%d src=%02X:%04X n=%d b=%02X fixed=%d pc=%06X\\n", (int)(d - DMA), d->ABank, d->AAddress, (int)d->TransferBytes, d->BAddress, (int)d->AAddressFixed, (unsigned)Registers.PBPC);|' /src/snes9x/dma.cpp \
    && grep -c "SFDMA" /src/snes9x/dma.cpp

WORKDIR /src/snes9x/libretro
RUN make STATIC_LINKING=1 -j"$(nproc)" \
    && cp snes9x_libretro.so /src/snes9x/libretro/snes9x_libretro.a

COPY main.cpp /src/frontend/main.cpp

RUN g++ -O2 -std=c++11 -o /src/sfemu /src/frontend/main.cpp \
        -I/src/snes9x -I/src/snes9x/libretro -I/src/snes9x/libretro/libretro-common/include \
        -I/src/snes9x/apu -I/src/snes9x/apu/bapu \
        /src/snes9x/libretro/snes9x_libretro.a

FROM debian:bookworm-slim

COPY --from=build /src/sfemu /usr/local/bin/sfemu

RUN useradd --create-home --uid 1000 runner
USER runner
WORKDIR /work

ENTRYPOINT ["sfemu"]
