import re
import zlib
from pathlib import Path

COPIER_HEADER = 512
GD_PART = re.compile(r"\.078$", re.IGNORECASE)


def has_copier_header(data):
    if len(data) <= COPIER_HEADER:
        return False
    return (len(data) - COPIER_HEADER) % 32768 == 0 or len(data) % 32768 == COPIER_HEADER


def strip_header(data):
    return data[COPIER_HEADER:] if has_copier_header(data) else data


def join_game_doctor(folder):
    parts = sorted(
        (p for p in Path(folder).iterdir() if GD_PART.search(p.name)),
        key=lambda p: p.name.upper(),
    )
    if not parts:
        return b""
    chunks = [strip_header(parts[0].read_bytes())]
    chunks += [p.read_bytes() for p in parts[1:]]
    return b"".join(chunks)


def deflate_ratio(block):
    if not block:
        return 0.0
    return len(zlib.compress(block, 6)) / len(block)


def block_ratios(data, block=65536):
    return [deflate_ratio(data[i : i + block]) for i in range(0, len(data) - block + 1, block)]


def chunk_index(data, chunk=1024, stride=512):
    index = {}
    for i in range(0, len(data) - chunk + 1, stride):
        index.setdefault(data[i : i + chunk], i)
    return index


def measure_reuse(source, target, chunk=1024, stride=512):
    index = chunk_index(target, chunk=chunk, stride=stride)
    found = total = 0
    for i in range(0, len(source) - chunk + 1, chunk):
        total += 1
        if source[i : i + chunk] in index:
            found += 1
    return found, total


def load(path):
    return strip_header(Path(path).read_bytes())
