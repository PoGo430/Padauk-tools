# =============================================================================
#  Padauk MCU project Makefile (SDCC + Easy PDK programmer)
# =============================================================================
#  Quick start:
#     make                build + show ROM/RAM usage
#     make program        build + write to the chip in the programmer
#     make run            power the chip from the programmer, show serial output
#     make help           everything else
#
#  Any setting below can be overridden for one command:
#     make program DEVICE=PMS150C F_CPU=1000000
#  or saved into this file:
#     make set DEVICE=PFS122 F_CPU=4000000 TARGET_VDD_MV=3300
# =============================================================================

# ----- Project settings (edit these) -----------------------------------------
PROJECT_NAME  ?= MyProject
DEVICE        ?= PFS154          # see `make devices`
F_CPU         ?= 8000000         # system clock in Hz (IHRC: 16M/8M/4M/2M/1M/500k/250k)
TARGET_VDD_MV ?= 5000            # supply voltage of your circuit, used for clock calibration

# ----- Build options ---------------------------------------------------------
OPT_FLAGS     ?= --opt-code-size
EXTRA_CFLAGS  ?=                 # e.g. -DDEBUG
SOURCES       ?= $(wildcard *.c) $(wildcard src/*.c)

# ----- Programmer options ----------------------------------------------------
EASYPDKPROG   ?= easypdkprog
PROG_PORT     ?=                 # e.g. /dev/ttyACM0 or COM3 (empty = auto detect)
PROG_FLAGS    ?=                 # e.g. --securefill, --noverify, --nocalibrate
PROG_ICNAME   ?=                 # override the IC name passed to easypdkprog -n

# =============================================================================
#  Supported devices:  ARCH  ROM(words)  RAM(bytes)  MEMORY
#  Sources: free-pdk.github.io/chips, pdk-includes, easypdkprog IC table.
#  mtp = flash, can be re-written.  otp = one time programmable!
# =============================================================================
DEV_PMS150C := pdk13 1024  64 otp
DEV_PMS15A  := pdk13 1024  64 otp
DEV_PMS150G := pdk13 1024  64 otp
DEV_PMS15B  := pdk13 1024  64 otp
DEV_PFS154  := pdk14 2048 128 mtp
DEV_PFS172  := pdk14 2048 128 mtp
DEV_PFS122  := pdk14 2048 128 mtp
DEV_PFS121  := pdk14 2048 128 mtp
DEV_PFC151  := pdk14 2048 128 mtp
DEV_PFC154  := pdk14 2048 128 mtp
DEV_PFC161  := pdk14 2048 128 mtp
DEV_PMS131  := pdk14 1536  88 otp
DEV_PMS152  := pdk14 1280  80 otp
DEV_PMS154B := pdk14 2048 128 otp
DEV_PMS154C := pdk14 2048 128 otp
DEV_PMS171B := pdk14 1536  96 otp
DEV_PFS173  := pdk15 3072 256 mtp
DEV_PFS123  := pdk15 3072 256 mtp

ALL_DEVICES := $(sort $(patsubst DEV_%,%,$(filter DEV_%,$(.VARIABLES))))

# Strip comments/spaces that sneak in from the "VAR ?= value  # comment" lines
DEVICE        := $(strip $(DEVICE))
F_CPU         := $(strip $(F_CPU))
TARGET_VDD_MV := $(strip $(TARGET_VDD_MV))
PROJECT_NAME  := $(strip $(PROJECT_NAME))
PROG_PORT     := $(strip $(PROG_PORT))
PROG_ICNAME   := $(strip $(PROG_ICNAME))

DEV_INFO  := $(DEV_$(DEVICE))
ARCH      := $(word 1,$(DEV_INFO))
ROM_WORDS := $(word 2,$(DEV_INFO))
RAM_BYTES := $(word 3,$(DEV_INFO))
MEM_TYPE  := $(word 4,$(DEV_INFO))
ICNAME    := $(if $(PROG_ICNAME),$(PROG_ICNAME),$(DEVICE))

# Goals that work without a valid DEVICE
NO_DEVICE_GOALS := help devices clean distclean list probe test run start
ifeq ($(DEV_INFO),)
  ifneq ($(filter-out $(NO_DEVICE_GOALS),$(or $(MAKECMDGOALS),all)),)
    $(error Unknown DEVICE '$(DEVICE)'. Supported: $(ALL_DEVICES))
  endif
endif

# Volts for `easypdkprog -r` (e.g. 5000 -> 5.0)
TARGET_VDD := $(shell awk 'BEGIN { printf "%.2f", $(TARGET_VDD_MV) / 1000 }')

# ----- Files -----------------------------------------------------------------
BUILD_DIR  := .build/$(DEVICE)
OUTPUT_DIR := .output
OUTPUT     := $(OUTPUT_DIR)/$(PROJECT_NAME)_$(DEVICE)
OBJECTS    := $(patsubst %.c,$(BUILD_DIR)/%.rel,$(SOURCES))
HEADERS    := $(wildcard *.h src/*.h include/*.h)

# ----- Toolchain -------------------------------------------------------------
CC      := sdcc
CFLAGS  := -m$(ARCH) --std-sdcc11 $(OPT_FLAGS) \
           -D$(DEVICE) -DF_CPU=$(F_CPU) -DTARGET_VDD_MV=$(TARGET_VDD_MV) \
           -I. -Isrc -Iinclude $(EXTRA_CFLAGS)
LDFLAGS := -m$(ARCH) --out-fmt-ihx
PROG    := $(EASYPDKPROG) $(if $(PROG_PORT),-p $(PROG_PORT))

# =============================================================================
#  Targets
# =============================================================================
all: size

build: intellisense $(OUTPUT).ihx $(OUTPUT).bin

$(BUILD_DIR)/%.rel: %.c $(HEADERS) Makefile
	@mkdir -p $(dir $@)
	$(CC) $(CFLAGS) -c -o $@ $<

$(OUTPUT).ihx: $(OBJECTS)
	@mkdir -p $(OUTPUT_DIR)
	$(CC) $(LDFLAGS) -o $@ $(OBJECTS)

$(OUTPUT).bin: $(OUTPUT).ihx
	makebin -p $< $@

# ROM usage = data bytes in the .ihx / 2 (Padauk ROM is counted in words).
# RAM usage = highest RAM address used by global/static data + stack start.
size: build
	@awk -v dev="$(DEVICE)" -v arch="$(ARCH)" -v rom="$(ROM_WORDS)" -v ram="$(RAM_BYTES)" \
	     -v fcpu="$(F_CPU)" -v vdd="$(TARGET_VDD)" -v map="$(OUTPUT).map" ' \
	  function hex(s,  i, n, c) { n = 0; s = toupper(s); \
	    for (i = 1; i <= length(s); i++) { c = index("0123456789ABCDEF", substr(s, i, 1)) - 1; n = n * 16 + c } \
	    return n } \
	  /^:/ && substr($$0, 8, 2) == "00" { bytes += hex(substr($$0, 2, 2)) } \
	  END { \
	    while ((getline line < map) > 0) { \
	      split(line, f, " "); \
	      if (f[1] == "DATA" || f[1] == "OSEG" || f[1] == "RSEG0" || f[1] == "SSEG") { \
	        end = hex(f[2]) + hex(f[3]); if (end > ramtop) ramtop = end } } \
	    words = int((bytes + 1) / 2); \
	    printf "\n  %s (%s)  F_CPU=%s Hz  VDD=%s V\n", dev, arch, fcpu, vdd; \
	    printf "  ROM: %5d / %5d words  (%3d%%)\n", words, rom, words * 100 / rom; \
	    printf "  RAM: %5d / %5d bytes  (%3d%%)  static data, stack uses the rest\n\n", ramtop, ram, ramtop * 100 / ram; \
	    if (words > rom) { print "  ERROR: program does not fit in ROM!"; exit 1 } \
	    if (ramtop >= ram) { print "  ERROR: no RAM left for the stack!"; exit 1 } \
	    if (ram - ramtop < 8) print "  WARNING: less than 8 bytes left for the stack.\n"; \
	    if (fcpu + 0 > 8000000) print "  WARNING: F_CPU above 8 MHz is beyond the usual datasheet rating (check yours).\n" \
	  }' $(OUTPUT).ihx

# OTP chips can only be written once: ask first (only in an interactive
# terminal; pass OTP_OK=1 to skip the question).
program: size
ifeq ($(MEM_TYPE),otp)
	@if [ -t 0 ] && [ -z "$(OTP_OK)" ]; then \
	   printf "$(DEVICE) is OTP: it can only be written ONCE. Write it now? [y/N] "; read answer; \
	   case "$$answer" in y|Y|yes|YES) ;; *) echo "Cancelled."; exit 1 ;; esac; \
	 else echo "NOTE: $(DEVICE) is OTP (one time programmable)."; fi
endif
	$(PROG) -n $(ICNAME) $(PROG_FLAGS) write $(OUTPUT).ihx

flash: program

# Save settings into this Makefile: make set DEVICE=PFS122 F_CPU=4000000
set:
	@sed -i.bak -e 's/^DEVICE\( *\)?= *[A-Za-z0-9]*/DEVICE\1?= $(DEVICE)/' \
	            -e 's/^F_CPU\( *\)?= *[0-9]*/F_CPU\1?= $(F_CPU)/' \
	            -e 's/^TARGET_VDD_MV\( *\)?= *[0-9]*/TARGET_VDD_MV\1?= $(TARGET_VDD_MV)/' \
	            -e 's/^PROJECT_NAME\( *\)?= *[A-Za-z0-9_-]*/PROJECT_NAME\1?= $(PROJECT_NAME)/' Makefile
	@rm -f Makefile.bak
	@$(MAKE) --no-print-directory intellisense
	@echo "Saved: DEVICE=$(DEVICE) ($(ARCH), $(MEM_TYPE))  F_CPU=$(F_CPU)  TARGET_VDD_MV=$(TARGET_VDD_MV)"

# Tell VS Code IntelliSense which chip/clock we build for (only rewritten when it changes)
SDCC_REV = $(shell $(CC) --version 2>/dev/null | sed -n 's/.* \#\([0-9][0-9]*\).*/\1/p' | head -n 1)
intellisense:
	@mkdir -p .vscode
	@{ echo '// Generated by the Makefile from DEVICE / F_CPU / TARGET_VDD_MV. Do not edit.'; \
	   echo '// Lets VS Code IntelliSense show the registers of the chip you build for.'; \
	   echo '#define $(DEVICE) 1'; \
	   echo '#define __SDCC_$(ARCH) 1'; \
	   echo '#define __SDCC_REVISION $(or $(SDCC_REV),13081)'; \
	   echo '#define F_CPU $(F_CPU)'; \
	   echo '#define TARGET_VDD_MV $(TARGET_VDD_MV)'; \
	 } > .vscode/pdk_config.h.tmp
	@if cmp -s .vscode/pdk_config.h.tmp .vscode/pdk_config.h; then rm -f .vscode/pdk_config.h.tmp; \
	 else mv .vscode/pdk_config.h.tmp .vscode/pdk_config.h; fi

# Power the chip from the programmer and show serial output from PA7
# (see include/serial.h). Ctrl+C to stop.
run:
	$(PROG) -r $(TARGET_VDD) start

start: run

probe:
	$(PROG) probe

list:
	$(EASYPDKPROG) list

test:
	$(PROG) test

erase:
ifeq ($(MEM_TYPE),otp)
	@echo "$(DEVICE) is OTP and cannot be erased."; exit 1
endif
	$(PROG) -n $(ICNAME) erase

read:
	@mkdir -p $(OUTPUT_DIR)
	$(PROG) -n $(ICNAME) read $(OUTPUT_DIR)/readout_$(DEVICE).ihx

devices:
	@echo "DEVICE   ARCH   ROM(words) RAM(bytes) MEMORY"
	@$(foreach d,$(ALL_DEVICES),printf "%-8s %-6s %10s %10s %s\n" $(d) $(DEV_$(d));)

config:
	@echo "PROJECT_NAME  = $(PROJECT_NAME)"
	@echo "DEVICE        = $(DEVICE) ($(ARCH), $(ROM_WORDS) words ROM, $(RAM_BYTES) bytes RAM, $(MEM_TYPE))"
	@echo "F_CPU         = $(F_CPU)"
	@echo "TARGET_VDD_MV = $(TARGET_VDD_MV)"
	@echo "SOURCES       = $(SOURCES)"
	@echo "OUTPUT        = $(OUTPUT).ihx"
	@echo "PROGRAM WITH  = $(PROG) -n $(ICNAME) $(PROG_FLAGS) write $(OUTPUT).ihx"

clean:
	rm -rf .build $(OUTPUT_DIR)

distclean: clean
	rm -f *.ihx *.bin *.map *.lst *.rel *.sym *.rst *.cdb *.adb *.asm *.lk *.mem *.noi

# Print any variable: make print-ARCH
print-%:
	@echo '$*=$($*)'

help:
	@echo "Targets:"
	@echo "  make             build and show ROM/RAM usage"
	@echo "  make program     build and write the chip (alias: flash)"
	@echo "  make run         power the chip at TARGET_VDD and show its serial output (alias: start)"
	@echo "  make probe       detect the chip in the programmer socket"
	@echo "  make erase       erase a flash (PFS) chip"
	@echo "  make read        read the chip back into .output/"
	@echo "  make list        list chips your easypdkprog version supports"
	@echo "  make test        programmer self test"
	@echo "  make devices     list chips this Makefile knows"
	@echo "  make config      show the current settings"
	@echo "  make set ...     save settings, e.g. make set DEVICE=PFS122 F_CPU=4000000"
	@echo "  make clean       remove build output"
	@echo ""
	@echo "Settings (edit at the top of the Makefile or pass on the command line):"
	@echo "  DEVICE=$(DEVICE) F_CPU=$(F_CPU) TARGET_VDD_MV=$(TARGET_VDD_MV) PROJECT_NAME=$(PROJECT_NAME)"

.PHONY: all build size program flash set intellisense run start probe list test erase read devices config clean distclean help
