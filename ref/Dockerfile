FROM debian:bookworm-slim AS build

ARG SNES9X_REF=1.63
ARG SDD1EMU_SHA256=a5f9733418ae913e8ebb358b7dde55504a88b2b035aadaf5496e229071b30770

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 --branch "${SNES9X_REF}" \
        https://github.com/snes9xgit/snes9x.git /src/snes9x

WORKDIR /ref

RUN cp /src/snes9x/sdd1emu.cpp /src/snes9x/sdd1emu.h /ref/ \
    && echo "${SDD1EMU_SHA256}  /ref/sdd1emu.cpp" | sha256sum --check --strict

COPY port.h driver.cpp /ref/

RUN g++ -O2 -Wall -Wextra -I/ref -o /ref/sdd1ref /ref/driver.cpp /ref/sdd1emu.cpp

FROM debian:bookworm-slim

COPY --from=build /ref/sdd1ref /usr/local/bin/sdd1ref

RUN useradd --create-home --uid 1000 builder
USER builder
WORKDIR /work

ENTRYPOINT ["sdd1ref"]
