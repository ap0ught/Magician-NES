# Magician-NES

Hello!

This package is the complete project for the NES version of Magician, released by Taxan Kaga in 1991.

http://en.wikipedia.org/wiki/Magician_(video_game)

> Magician is a side-scrolling role-playing game released in February 1991 for the Nintendo Entertainment System. It was designed by Eurocom Entertainment Software and published by Taxan.

I am releasing this package to the community for educational purposes only. You are free to play with it and do with it as you will, but you are NOT allowed to make money out of it or profit in any way, shape or form. I know you won't. I trust you.

This was the Eurocom's first game, and was the game we used to pitch to Taxan and get our first gig. I designed the game, and programmed our tools and game editors. I also started programming John Smith (Special Agent), later released as James Bond Jr., on NES, while Magician was under development. If you ever meet me and buy me a beer, I'll tell you some stories. I hope you enjoy messing with this code as much as I did creating it.

Cheers!

Chris Shrigley - 12/24/12
http://www.shrigley.com

PLEASE KEEP THIS READ_ME FILE WITH THE PACKAGE. THANKS!
Source code for the 1990 NES game Magician

## Building a ROM

Chris Shrigley's terms above still apply: this is for education, and it is not for sale. Keep `_READ_ME.TXT` with the package.

The assembler is [pds6502](https://github.com/ap0ught/pds6502). There is no separate `pdsasm` program or repository; `pds6502` is the PDS 1.26 assembler, and `asm/pds6502.py` is the loader its README describes. Its CLI assembles one file into a flat PRG image. Placing the MMC3 slots and packing CHR is this repository's build, and that build does not open a cartridge dump.

Clone pds6502 next to this repository, or set `PDS6502_HOME` to the checkout:

```
git clone https://github.com/ap0ught/pds6502.git ../pds6502
make -C asm source-rom
```

That writes `asm/out/magician-source.nes`. The file is git-ignored. PRG comes from `X0.PDS`–`X7.PDS` and `SEQ.SRC`. Each CHR file is filed at the 1 KiB bank offset `SENDG` declares (`$nn*4` for a 4 KiB set, so `SH.CHR` is at `$F000`, `BANK40.DAT` at `$10000`, `TIT1.CHR` at `$1D000`, `TIT2.CHR` at `$1E000`). X7 is placed so `reset` is the Beta 1 vector `$F930` recorded in `asm/build.py`.

With pds6502 `0110a54` this tree produces a 262160-byte ROM, sha256 `23607f17d6bd980b252214156d484e2f9bd6259ab652093bcb79ef81f82e8674`, vectors nmi `$F917` reset `$F930` irq `$F922`, header byte 6 `$40`. That image is the source-drop files filed at the `SENDG` bank offsets. No cartridge is read.