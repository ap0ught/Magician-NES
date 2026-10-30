# Source-only iNES image from the PDS files in this repository.
#
#   make -C asm source-rom
#
# The assembler is pds6502 (https://github.com/ap0ught/pds6502), loaded by
# asm/pds6502.py from ../pds6502 or from $PDS6502_HOME. There is no separate
# pdsasm program. Nothing here reads a cartridge dump. *.nes is git-ignored.

PYTHON ?= python3

.PHONY: source-rom clean

source-rom:
	$(PYTHON) build.py

clean:
	rm -rf out
