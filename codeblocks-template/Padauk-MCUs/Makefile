# ---------------------------------------------------------------------
# Project configuration
# ---------------------------------------------------------------------
# Set the following variables:
#
# DEVICE = PFS154        # e.g., PFS154, PMS150C, etc.
# ARCH = pdk14  # e.g., pdk14, pdk15, pdk13
# PROJECT_NAME = karkol       # e.g., MyProject
#
# Required compile settings:
# F_CPU        = <Frequency>          # e.g., 8000000
# TARGET_VDD_MV = <Voltage_Millivolts> # e.g., 5000
# TARGET_VDD    = <Voltage_Volts>     # e.g., 5.0
#
# Optional:
# OPT_FLAGS = --opt-code-size
#
# Example:
# DEVICE = PFS154
# ARCH = pdk14
# PROJECT_NAME = karkol
# F_CPU = 8000000
# TARGET_VDD_MV = 5000
# TARGET_VDD = 5.0
#
# ---------------------------------------------------------------------

# Default settings
DEVICE = PFS154
ARCH = pdk14
PROJECT_NAME = karkol
F_CPU = 8000000
TARGET_VDD_MV = 5000
TARGET_VDD = 5.0
OPT_FLAGS = --opt-code-size

# Directories and filenames
OUTPUT_NAME = $(PROJECT_NAME)_$(DEVICE)
BUILD_DIR = .build
OUTPUT_DIR = .output
MYPROJECT_OUTPUT = $(OUTPUT_DIR)/$(OUTPUT_NAME)

# Sources and object files
SOURCES = main.c
OBJECTS = $(patsubst %.c,$(BUILD_DIR)/%.rel,$(SOURCES))

# Toolchain
COMPILE = sdcc-sdcc -m$(ARCH) -c $(OPT_FLAGS) -D$(DEVICE) -DF_CPU=$(F_CPU) -DTARGET_VDD_MV=$(TARGET_VDD_MV) -DTARGET_VDD=$(TARGET_VDD) -I. -I include
LINK = sdcc-sdcc -m$(ARCH)
EASYPDKPROG = easypdkprog

# ROM and RAM sizes
ROM_SIZES = MCU390=2048 PFS154=2048 PFS172=2048 PFS173=3072 PMC131=1536 PMC251=1024 PMC271=1024 PMS131=1536 PMS132=2048 PMS132B=2048 PMS133=4096 PMS134=4096 PMS150C=1024 PMS152=1280 PMS154B=2048 PMS154C=2048 PMS15A=1024 PMS171B=1536 PMS271=1024
RAM_SIZES = MCU390=128 PFS154=128 PFS172=128 PFS173=256 PMC131=88 PMC251=59 PMC271=64 PMS131=88 PMS132=128 PMS132B=128 PMS133=256 PMS134=256 PMS150C=64 PMS152=80 PMS154B=128 PMS154C=128 PMS15A=64 PMS171B=96 PMS271=64

# Extract sizes
ROM_SIZE = $(shell echo "$(ROM_SIZES)" | tr ' ' '\n' | grep "^$(DEVICE)=" | cut -d'=' -f2)
RAM_SIZE = $(shell echo "$(RAM_SIZES)" | tr ' ' '\n' | grep "^$(DEVICE)=" | cut -d'=' -f2)

# Check device
check_device:
	@echo "$(ROM_SIZES)" | tr ' ' '\n' | grep -q "^$(DEVICE)=" || { \
		echo "Error: Invalid device '$(DEVICE)'"; \
		echo "Available devices:"; \
		echo "$(ROM_SIZES)" | tr ' ' '\n' | cut -d'=' -f1 | sort; \
		exit 1; \
	}

# Build rules
$(BUILD_DIR)/%.rel: %.c
	@mkdir -p $(dir $@)
	$(COMPILE) -o $@ $<

$(MYPROJECT_OUTPUT).ihx: $(OBJECTS)
	@mkdir -p $(dir $(MYPROJECT_OUTPUT))
	$(LINK) --out-fmt-ihx -o $(MYPROJECT_OUTPUT).ihx $(OBJECTS)

$(MYPROJECT_OUTPUT).bin: $(MYPROJECT_OUTPUT).ihx
	makebin -p $(MYPROJECT_OUTPUT).ihx $(MYPROJECT_OUTPUT).bin

# Targets
all: size

build: check_device $(MYPROJECT_OUTPUT).bin

size: build
	@echo
	@echo "Memory Usage Summary for $(DEVICE)"
	@echo "================================="
	@echo
	@echo "Memory Segments:"
	@echo "---------------"
	@grep -E '(ABS,CON)|(REL,CON)' $(MYPROJECT_OUTPUT).map | \
		gawk --non-decimal-data '{dec = sprintf("%d","0x" $$2); print dec " " $$0}' | \
		sort -n -k1 | \
		cut -f2- -d' ' | \
		while read -r name size rest; do \
			if [ "$$size" != ".ABS." ]; then \
				printf "%-25s %10s bytes\n" "$$name" "$$size"; \
			fi \
		done
	@echo
	@echo "Binary Statistics:"
	@echo "----------------"
	@BINARY_SIZE=$$(stat -c %s $(MYPROJECT_OUTPUT).bin) && \
		printf "%-25s %10d bytes\n" "Total binary size:" "$$BINARY_SIZE" && \
		printf "%-25s %10d bytes\n" "Available ROM:" "$(ROM_SIZE)" && \
		PERCENT=$$(echo "scale=0; $$BINARY_SIZE * 100 / $(ROM_SIZE)" | bc) && \
		printf "%-25s %10d%%\n" "ROM usage:" "$$PERCENT"
	@echo
	@PERCENT=$$(echo "scale=0; $$(stat -c %s $(MYPROJECT_OUTPUT).bin) * 100 / $(ROM_SIZE)" | bc); \
	if [ $$PERCENT -gt 90 ]; then \
		echo "Warning: ROM usage is above 90%!"; \
	elif [ $$PERCENT -gt 75 ]; then \
		echo "Note: ROM usage is above 75%."; \
	fi
	@echo

program: size
	$(EASYPDKPROG) -n $(DEVICE) write $(MYPROJECT_OUTPUT).ihx

run:
	$(EASYPDKPROG) -r $(TARGET_VDD) start

clean:
	rm -rf $(BUILD_DIR) $(OUTPUT_DIR)

# Clean everything including generated files
distclean: clean
	rm -f *.ihx *.bin *.map *.lst *.rel *.sym *.rst *.cdb *.adb

# Display help message
help:
	@echo "Available targets:"
	@echo "  all         - Build the project"
	@echo "  build       - Build the project binary"
	@echo "  size        - Display the size of the binary"
	@echo "  program     - Program the device (write the .ihx file)"
	@echo "  run         - Run the program on the device"
	@echo "  clean       - Clean the build and output directories"
	@echo "  distclean   - Clean everything including generated files"
	@echo "  help        - Display this help message"

.PHONY: all build size program run clean distclean check_device help

