"""Génère les icônes de la PWA (assiette vue de dessus, vert herbe sur fond crème).

Usage : python scripts/make_icons.py   (bibliothèque standard seulement)
"""

import struct
import zlib
from pathlib import Path

CREAM = (250, 246, 236)
GREEN = (79, 122, 58)
SAMPLES = 4  # suréchantillonnage pour des bords lisses
OUTPUT = Path(__file__).resolve().parent.parent / "static" / "icons"


def coverage(x: float, y: float, size: int) -> tuple[float, float]:
    """Part de pixel couverte par l'anneau vert et par le disque intérieur."""
    cx = cy = size / 2
    ring = disc = 0
    for sy in range(SAMPLES):
        for sx in range(SAMPLES):
            dx = x + (sx + 0.5) / SAMPLES - cx
            dy = y + (sy + 0.5) / SAMPLES - cy
            distance = (dx * dx + dy * dy) ** 0.5 / size
            ring += 0.28 <= distance <= 0.36
            disc += distance < 0.2
    total = SAMPLES * SAMPLES
    return ring / total, disc / total


def pixel(x: int, y: int, size: int, background) -> tuple[int, int, int]:
    ring, disc = coverage(x, y, size)
    colour = [float(c) for c in background]
    for part, tint in ((ring, GREEN), (disc, GREEN)):
        colour = [c * (1 - part) + t * part for c, t in zip(colour, tint, strict=True)]
    return tuple(round(c) for c in colour)


def png(size: int, background) -> bytes:
    rows = bytearray()
    for y in range(size):
        rows.append(0)  # filtre « aucun »
        for x in range(size):
            rows.extend(pixel(x, y, size, background))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        (OUTPUT / name).write_bytes(png(size, CREAM))
        print("écrit", name)


if __name__ == "__main__":
    main()
