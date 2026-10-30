#!/usr/bin/env python3
"""Assemble a loadable iNES ROM from the PDS sources in this repository.

The assembler is pds6502 (loaded by asm/pds6502.py). Its own CLI writes one
source file into a flat PRG image and does not place MMC3 slots or pack CHR,
which its README leaves to the game. This script is that placement:

* X0-X7 and SEQ.SRC are assembled into the MMC3 slots the sources name.
* X7 is placed so the label ``last`` meets ``$FB80``, the address X7.PDS
  pads to and where it loads SAM.SAM. ``org $fffa`` / ``dw nmi,reset,irq``
  in that file emits the vectors. No cartridge dump is opened.
* CHR is packed from ``DAT/`` at the 1 KiB bank offsets ``SENDG`` declares.

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

# X7.PDS: `if last>$fb80` / `ds $fb80-last` / `load mus\sam.sam,$fb80`.
# The module is placed so `last` is that address. The vectors are the
# words `org $fffa` / `dw nmi,reset,irq` assemble, not a copied header.
LAST_AT = 0xFB80

# iNES mapper 4 (MMC3, the map X5.PDS describes), 128 KiB PRG, 128 KiB CHR.
# Byte 6 is $40: mapper low nibble 4, battery bit clear.
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

# Slots named by the sources. X5 is `org $c000` (bank $0E). X6 and X7 have no
# `org` and share that fixed $C000-$FFFF window (X5.PDS). X4 is slot 2 at
# $8000 and slot 3 at $A000 (`farjsr67` and "must reside above $9FFF").
# X0 is `org $8000` with `bnk 6,#$0`. X3 is `bnk 6,#4`. SEQ.SRC is included
# from DISP.SRC's `org $a000`, and X4.PDS sets `bfra equ $5` for that window.
# X1 and X2 are chained onto the previous module, so their slot here is only
# the window they continue in.
PINNED_SLOTS = {"X4.PDS": 2, "X6.PDS": 15, "X7.PDS": 15}
ASSUMED_SLOTS = {
    "X0.PDS": 0, "X1.PDS": 1, "X2.PDS": 0, "X3.PDS": 4, "X5.PDS": 14,
}
CHAINED = ("X1.PDS", "X2.PDS")

WINDOW_SLOTS = {
    "X2.PDS": {0x8000: 0, 0xA000: 1},
    "X4.PDS": {0x8000: 2, 0xA000: 3},
    "SEQ.SRC": {0xA000: 5, 0xC000: None},
}

# SENDG's fourth `load` argument is a 1 KiB CHR bank index (`radix 10`, `$` hex).
# A 4 KiB set is written `$nn*4` because it occupies four of those banks, which
# is also its 4 KiB page: `s0f = $f*$4` in X0.PDS, and SH.CHR is filed at $F000.
# Sprite banks are one page each (`$40`..`$73`). `in.chr` follows `bank $1f*4`.
# File offset is that index times 0x400. Do not concatenate from cursor 0.
CHR_PAGE = 0x400
CHR_BANKS = [
    ("10.chr", 0x00 * 4), ("20.chr", 0x01 * 4), ("21.chr", 0x02 * 4),
    ("30.chr", 0x03 * 4), ("40.chr", 0x04 * 4), ("50.chr", 0x05 * 4),
    ("53.chr", 0x06 * 4), ("60.chr", 0x07 * 4), ("70.chr", 0x08 * 4),
    ("73.chr", 0x09 * 4), ("80.chr", 0x0A * 4), ("su.chr", 0x0B * 4),
    ("spr/inv.spr", 0x0C * 4), ("map.chr", 0x0D * 4), ("tit0.chr", 0x0E * 4),
    ("tit1.chr", 0x1D * 4), ("tit2.chr", 0x1E * 4), ("sh.chr", 0x0F * 4),
]
CHR_BANKS += [(f"spr/bank{n:02x}.dat", n) for n in range(0x40, 0x74)]
CHR_BANKS.append(("in.chr", 0x1F * 4))


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
    """Two project passes. The first measures X7; the second places `last`."""
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

    for attempt in range(2):
        image = bytearray(PRG_SIZE)
        asm = _new_asm(image)
        origins: dict[str, int] = {"SEQ.SRC": 0xA000}
        if x7_base is not None:
            origins["X7.PDS"] = x7_base
        if derived is not None:
            origins["X6.PDS"] = derived["X5.PDS"]
        ceilings = {} if derived is None else dict(derived)
        asm.run_all(paths, slot_list, origins, WINDOW_SLOTS, ceilings)

        reset = asm.sym.get("reset")
        last = asm.sym.get("last")
        if reset is None or last is None:
            raise SystemExit("X7 did not define reset and last")
        if attempt == 0:
            # First pass starts X7 at slot 15's $E000. `last` and `reset`
            # sit before X7's only `org`, so both move by the same amount
            # when the second pass sets the origin.
            slot_base = Assembler.slot_origin(PINNED_SLOTS["X7.PDS"])
            x7_base = LAST_AT - (last - slot_base)
            x6 = asm.writes_by_file.get("X6.PDS") or ()
            if not x6:
                raise SystemExit("X6 emitted nothing; cannot derive the slot 15 split")
            x6_len = max(x6) - min(x6) + 1
            x6_base = x7_base - x6_len
            derived = {"X5.PDS": x6_base, "X6.PDS": x7_base}
            log.append(
                f"X7.PDS: last is ${last:04X} from slot ${slot_base:04X}; "
                f"X7.PDS names ${LAST_AT:04X}, so X7 begins at ${x7_base:04X}"
            )
            log.append(
                f"X6.PDS: {x6_len} bytes, so X6 starts at ${x6_base:04X} "
                f"and X5 stops there"
            )
            continue
        log.append(
            f"X7.PDS: last ${asm.sym['last']:04X}; "
            f"org $fffa emits nmi ${asm.sym.get('nmi', 0):04X} "
            f"reset ${asm.sym['reset']:04X} irq ${asm.sym.get('irq', 0):04X}"
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
    """File each DAT asset at the bank offset SENDG declares."""
    image = bytearray(CHR_SIZE)
    placed: list[tuple[str, int, int]] = []
    for name, bank in CHR_BANKS:
        data = dat_file(name).read_bytes()
        off = bank * CHR_PAGE
        end = off + len(data)
        if off < 0 or end > CHR_SIZE:
            raise SystemExit(f"{name} bank ${bank:02X} does not fit at {off:#x}")
        for prev, prev_off, prev_len in placed:
            if off < prev_off + prev_len and prev_off < end:
                raise SystemExit(
                    f"{name} at {off:#x} overlaps {prev} at {prev_off:#x}"
                )
        image[off:end] = data
        placed.append((name, off, len(data)))
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
