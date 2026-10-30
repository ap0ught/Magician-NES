#!/usr/bin/env python3
"""Assemble a loadable iNES ROM from the PDS sources in this repository.

The assembler is pds6502 (loaded by asm/pds6502.py). Its own CLI writes one
source file into a flat PRG image and does not place MMC3 slots or pack CHR,
which its README leaves to the game. This script is that placement:

* X0-X7 and SEQ.SRC are assembled with the slots the source-only Magician
  build already proved (pinned where the source says so, assumed otherwise).
* X7 is anchored so ``reset`` lands on the Beta 1 reset vector recorded below.
  That vector is a constant in this file. No cartridge dump is opened.
* CHR is packed from ``DAT/`` in the order ``SENDG`` sends it.

    python3 asm/build.py
    make -C asm source-rom

The ROM is written to asm/out/magician-source.nes and is git-ignored.
"""
from __future__ import annotations

import builtins
import hashlib
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from pds6502 import Assembler  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / "asm" / "out"
ROM = OUT / "magician-source.nes"

PRG_SIZE = 128 * 1024
CHR_SIZE = 128 * 1024

# Beta 1 vectors, recorded here so the anchor does not read a .nes file.
# nmi, reset, irq. Reset is what X7 is fitted to.
BETA1_VECTORS = (0xF917, 0xF930, 0xF922)

# Mapper 4, 128 KiB PRG, 128 KiB CHR. Byte 6 is $40: mapper low nibble 4,
# battery bit clear. Recorded, not copied out of a dump at build time.
INES_HEADER = bytes([
    0x4E, 0x45, 0x53, 0x1A,
    0x08,
    0x10,
    0x40,
    0x00,
    0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00,
])

MODULES = [f"X{i}.PDS" for i in range(8)]

# Slots the source-only build uses when it is not scoring modules against a
# cartridge. X4, X6 and X7 are pinned from the source's own bank notes and from
# the recorded reset vector (X7). The others are the assumed slots that build
# falls through to. X1 and X2 are chained onto the previous module on the
# project pass, so the slot stored here is only the provisional one.
PINNED_SLOTS = {"X4.PDS": 2, "X6.PDS": 15, "X7.PDS": 15}
ASSUMED_SLOTS = {
    "X0.PDS": 0, "X1.PDS": 1, "X2.PDS": 0, "X3.PDS": 4, "X5.PDS": 14,
}
CHAINED = ("X1.PDS", "X2.PDS")

# First-pass origin for X6. The project pass replaces it with a derived start
# once X6's length and X7's anchor are both known. $E605 is the literal the
# measurement pass uses; it is not the address that ends up in the ROM.
X5_CEILING_LITERAL = 0xE605

WINDOW_SLOTS = {
    "X2.PDS": {0x8000: 0, 0xA000: 1},
    "X4.PDS": {0x8000: 2, 0xA000: 3},
    "SEQ.SRC": {0xA000: 5, 0xC000: None},
}

# CHR, in the order SENDG sends it, then the sprite banks, then IN.CHR.
# The slot numbers SENDG records are not file offsets; packing is sequential.
CHR_SEND_ORDER = [
    "10.chr", "20.chr", "21.chr", "30.chr", "40.chr", "50.chr", "53.chr",
    "60.chr", "70.chr", "73.chr", "80.chr", "su.chr", "spr/inv.spr",
    "map.chr", "tit0.chr", "tit1.chr", "tit2.chr", "sh.chr",
]
SPRITE_FIRST, SPRITE_LAST = 0x40, 0x73


def _refuse_cartridge_reads() -> None:
    """A .nes path may be created as output. It may not be read."""
    real = builtins.open

    def guard(file, mode="r", *args, **kwargs):
        name = getattr(file, "name", None)
        text = name if isinstance(name, str) else (file if isinstance(file, str) else "")
        low = text.lower()
        writing = any(flag in mode for flag in ("w", "a", "x"))
        if low.endswith((".nes", ".unif", ".unl")) and not writing:
            raise SystemExit(f"refusing to read cartridge file {text}")
        return real(file, mode, *args, **kwargs)

    builtins.open = guard


def _sources() -> list[pathlib.Path]:
    return [ROOT / name for name in MODULES] + sorted(ROOT.glob("*.SRC"))


def _new_asm(image: bytearray) -> Assembler:
    asm = Assembler(image, ROOT, [ROOT])
    # X7.PDS ends with `end`. SEQ.SRC is assembled after that on purpose.
    asm.stop_at_end = False
    asm.force_conditions = {"0=1": True}
    asm.prebank_symbols = frozenset({"b"})
    asm.prebank_split = True
    asm.demo_errors = (">$FB80!",)
    asm.prescan(_sources())
    asm.collect_macros(_sources())
    return asm


def assemble_prg() -> tuple[bytearray, Assembler, list[str]]:
    """Two project passes. The first measures X7; the second anchors it."""
    slots = []
    for name in MODULES:
        if name in PINNED_SLOTS:
            slots.append(PINNED_SLOTS[name])
        elif name in ASSUMED_SLOTS:
            slots.append(ASSUMED_SLOTS[name])
        else:
            raise SystemExit(f"{name} has no slot")
    placed = [(name, None if name in CHAINED else slot)
              for name, slot in zip(MODULES, slots)]
    placed.append(("SEQ.SRC", 5))
    paths = [ROOT / name for name, _slot in placed]
    slot_list = [slot for _name, slot in placed]
    for path in paths:
        if not path.is_file():
            raise SystemExit(f"missing source {path}")

    log: list[str] = []
    x7_base = None
    derived: dict[str, int] | None = None
    image = bytearray(PRG_SIZE)
    asm = _new_asm(image)
    want = BETA1_VECTORS[1]

    for attempt in range(2):
        image = bytearray(PRG_SIZE)
        asm = _new_asm(image)
        origins: dict[str, int] = {
            "SEQ.SRC": 0xA000,
            "X6.PDS": X5_CEILING_LITERAL,
        }
        if x7_base is not None:
            origins["X7.PDS"] = x7_base
        if derived is not None:
            origins["X6.PDS"] = derived["X5.PDS"]
        ceilings = {} if derived is None else dict(derived)
        asm.run_all(paths, slot_list, origins, WINDOW_SLOTS, ceilings)

        reset = asm.sym.get("reset")
        if reset is None:
            raise SystemExit("X7 did not define reset")
        if attempt == 0:
            x7_off = reset - Assembler.slot_origin(PINNED_SLOTS["X7.PDS"])
            x7_base = want - x7_off
            x6 = asm.writes_by_file.get("X6.PDS") or ()
            if not x6:
                raise SystemExit("X6 emitted nothing; cannot derive the slot 15 split")
            x6_len = max(x6) - min(x6) + 1
            x6_base = x7_base - x6_len
            derived = {"X5.PDS": x6_base, "X6.PDS": x7_base}
            log.append(
                f"X7.PDS: reset is ${x7_off:04X} into the module; "
                f"recorded reset ${want:04X} puts X7 at ${x7_base:04X}"
            )
            log.append(
                f"X6.PDS: {x6_len} bytes, so X6 starts at ${x6_base:04X} "
                f"and X5's ceiling is ${x6_base:04X}"
            )
            continue
        log.append(
            f"X7.PDS: anchored at ${x7_base:04X}; "
            f"reset ${asm.sym['reset']:04X} (recorded ${want:04X}), "
            f"nmi ${asm.sym.get('nmi', 0):04X}, irq ${asm.sym.get('irq', 0):04X}"
        )
    return image, asm, log


def dat_file(name: str) -> pathlib.Path:
    want = name.replace("\\", "/").lower()
    root = ROOT / "DAT"
    for path in root.rglob("*"):
        if path.is_file() and str(path.relative_to(root)).lower() == want:
            return path
    raise SystemExit(f"no DAT file for {name!r}")


def build_chr() -> bytearray:
    image = bytearray(CHR_SIZE)
    names = list(CHR_SEND_ORDER)
    names += [f"SPR/BANK{bank:02X}.DAT" for bank in range(SPRITE_FIRST, SPRITE_LAST + 1)]
    names.append("IN.CHR")
    cursor = 0
    for name in names:
        data = dat_file(name).read_bytes()
        if cursor + len(data) > CHR_SIZE:
            raise SystemExit(f"{name} does not fit at {cursor:#x}")
        image[cursor:cursor + len(data)] = data
        cursor += len(data)
    return image


def vectors_of(prg: bytes) -> tuple[int, int, int]:
    """nmi, reset, irq from the last six bytes of the 128 KiB PRG image."""
    off = 0x1FFFA
    nmi = prg[off] | (prg[off + 1] << 8)
    reset = prg[off + 2] | (prg[off + 3] << 8)
    irq = prg[off + 4] | (prg[off + 5] << 8)
    return nmi, reset, irq


def main() -> int:
    _refuse_cartridge_reads()
    prg, asm, log = assemble_prg()
    chr_rom = build_chr()
    if len(prg) != PRG_SIZE or len(chr_rom) != CHR_SIZE:
        raise SystemExit("PRG or CHR is not 128 KiB")

    body = bytes(prg) + bytes(chr_rom)
    rom = INES_HEADER + body
    OUT.mkdir(parents=True, exist_ok=True)
    ROM.write_bytes(rom)
    (OUT / "prg.bin").write_bytes(bytes(prg))
    (OUT / "chr.bin").write_bytes(bytes(chr_rom))

    nmi, reset, irq = vectors_of(bytes(prg))
    digest = hashlib.sha256(rom).hexdigest()
    body_sha1 = hashlib.sha1(body).hexdigest()
    print("\n".join(log))
    print(f"symbols: {len(asm.sym)}")
    print(f"wrote {ROM}")
    print(f"size {len(rom)}")
    print(f"sha256 {digest}")
    print(f"body sha1 {body_sha1}")
    print(f"header[6] ${rom[6]:02X}")
    print(f"vectors nmi ${nmi:04X} reset ${reset:04X} irq ${irq:04X}")
    print("cartridge file opened: no")
    if reset != BETA1_VECTORS[1]:
        print(
            f"warning: reset is ${reset:04X}, recorded anchor is "
            f"${BETA1_VECTORS[1]:04X}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
