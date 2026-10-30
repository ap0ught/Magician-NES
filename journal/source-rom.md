# Source ROM

Magician-NES is Eurocom's PDS source. `make -C asm source-rom` runs `asm/build.py` and writes `asm/out/magician-source.nes`, so the ROM can be built and released without a cartridge dump. Cart hashes, cart paths, and cart comparison belong in magician-nes-re.

## CHR

`build_chr` files each `DAT/` asset at the bank offset `SENDG` declares. The offset is `off = bank * 0x400` (`CHR_PAGE`). Files are placed at that offset. They are not concatenated from 0.

`CHR_BANKS` includes `("tit1.chr", 0x1D * 4)`, `("tit2.chr", 0x1E * 4)`, and `("sh.chr", 0x0F * 4)`. Sprite pages are `spr/bank40.dat` through `spr/bank73.dat` at bank numbers `0x40`..`0x73`. A 4 KiB set uses SENDG's `$nn*4` index; a sprite page uses the bank number itself. Both are multiplied by `0x400`:

| Asset | Bank index | Offset |
| --- | --- | --- |
| SH.CHR | `0x0F * 4` | `0xF000` |
| BANK40.DAT | `0x40` | `0x10000` |
| TIT1.CHR | `0x1D * 4` | `0x1D000` |
| TIT2.CHR | `0x1E * 4` | `0x1E000` |

`in.chr` follows SENDG's `bank $1f*4`, so its index is `0x1F * 4`. A placement that overlaps an asset already filed is rejected.

## X7

`LAST_AT = 0xFB80`. X7.PDS pads with `ds $fb80-last` and loads samples with `load mus\sam.sam,$fb80`. The module is placed so the source label `last` meets that address:

```
x7_base = LAST_AT - (last - slot_base)
```

The first pass measures `last` from slot 15. The second pass sets X7's origin to `x7_base`.

The vectors are whatever `org $fffa` / `dw nmi,reset,irq` assemble into the last six PRG bytes. The build keeps no Beta 1 reset constant, cart hash, cart path, or cart comparison. A build of `d8067c9e4920d83a53b48a4008359b2e250c769d` emitted nmi `$F998`, reset `$F9B1`, irq `$F9A3` because those are the assembled labels, not anchors.

## The file the command opens

`make -C asm source-rom` does not open a cartridge dump. `_refuse_cartridge_reads` rejects a read of a `.nes`, `.unif`, or `.unl`. The only `.nes` open is a write-only create of the gitignored output `asm/out/magician-source.nes`.
