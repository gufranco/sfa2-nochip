FROM debian:bookworm-slim AS build

ARG ASAR_REF=v1.81

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential cmake git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 --branch "${ASAR_REF}" https://github.com/RPGHacker/asar.git /src/asar \
    && cmake -S /src/asar/src -B /build -DCMAKE_BUILD_TYPE=Release \
    && cmake --build /build --parallel

FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 xxd \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /build/asar/asar-standalone /usr/local/bin/asar

RUN useradd --create-home --uid 1000 builder
USER builder
WORKDIR /work

ENTRYPOINT ["asar"]
CMD ["--version"]
