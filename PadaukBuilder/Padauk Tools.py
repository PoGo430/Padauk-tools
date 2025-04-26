#!/usr/bin/env python3
import sys
import os
import subprocess
import re
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QLabel, QComboBox, QPushButton, 
                            QSpinBox, QDoubleSpinBox, QTextEdit, QGroupBox,
                            QTabWidget, QLineEdit, QMessageBox)
from PyQt5.QtCore import Qt, QProcess

class MakefileConfigTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Device options
        self.devices = [
            "MCU390", "PFS154", "PFS172", "PFS173", "PMC131", "PMC251", "PMC271",
            "PMS131", "PMS132", "PMS132B", "PMS133", "PMS134", "PMS150C", "PMS152",
            "PMS154B", "PMS154C", "PMS15A", "PMS171B", "PMS271"
        ]
        
        # Architecture options
        self.architectures = ["pdk13", "pdk14", "pdk15"]
        
        # Project Name
        name_layout = QHBoxLayout()
        name_label = QLabel("Project Name:")
        self.project_name = QLineEdit()
        self.project_name.setText("MyProject")
        name_layout.addWidget(name_label)
        name_layout.addWidget(self.project_name)
        layout.addLayout(name_layout)
        
        # Device Selection
        device_layout = QHBoxLayout()
        device_label = QLabel("Device:")
        self.device_combo = QComboBox()
        self.device_combo.addItems(self.devices)
        self.device_combo.setCurrentText("PFS154")
        device_layout.addWidget(device_label)
        device_layout.addWidget(self.device_combo)
        layout.addLayout(device_layout)
        
        # Architecture Selection
        arch_layout = QHBoxLayout()
        arch_label = QLabel("Architecture:")
        self.arch_combo = QComboBox()
        self.arch_combo.addItems(self.architectures)
        self.arch_combo.setCurrentText("pdk14")
        arch_layout.addWidget(arch_label)
        arch_layout.addWidget(self.arch_combo)
        layout.addLayout(arch_layout)
        
        # CPU Frequency
        fcpu_layout = QHBoxLayout()
        fcpu_label = QLabel("CPU Frequency (Hz):")
        self.f_cpu = QSpinBox()
        self.f_cpu.setRange(1000000, 20000000)
        self.f_cpu.setValue(8000000)
        self.f_cpu.setSingleStep(1000000)
        fcpu_layout.addWidget(fcpu_label)
        fcpu_layout.addWidget(self.f_cpu)
        layout.addLayout(fcpu_layout)
        
        # Target VDD (mV)
        vdd_mv_layout = QHBoxLayout()
        vdd_mv_label = QLabel("Target VDD (mV):")
        self.vdd_mv = QSpinBox()
        self.vdd_mv.setRange(1800, 5500)
        self.vdd_mv.setValue(5000)
        self.vdd_mv.setSingleStep(100)
        vdd_mv_layout.addWidget(vdd_mv_label)
        vdd_mv_layout.addWidget(self.vdd_mv)
        layout.addLayout(vdd_mv_layout)
        
        # Target VDD (V)
        vdd_v_layout = QHBoxLayout()
        vdd_v_label = QLabel("Target VDD (V):")
        self.vdd_v = QDoubleSpinBox()
        self.vdd_v.setRange(1.8, 5.5)
        self.vdd_v.setValue(5.0)
        self.vdd_v.setSingleStep(0.1)
        vdd_v_layout.addWidget(vdd_v_label)
        vdd_v_layout.addWidget(self.vdd_v)
        layout.addLayout(vdd_v_layout)
        
        # Optimization Flags
        opt_layout = QHBoxLayout()
        opt_label = QLabel("Optimization Flags:")
        self.opt_flags = QLineEdit()
        self.opt_flags.setText("--opt-code-size")
        opt_layout.addWidget(opt_label)
        opt_layout.addWidget(self.opt_flags)
        layout.addLayout(opt_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.update_btn = QPushButton("Update Makefile")
        self.update_btn.clicked.connect(self.update_makefile)
        button_layout.addWidget(self.update_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.load_current_values()
    
    def load_current_values(self):
        try:
            with open("Makefile", "r") as f:
                content = f.read()
                
                # Extract current values using regex with more lenient patterns
                project_match = re.search(r'PROJECT_NAME\s*=\s*(\S+)', content)
                if project_match:
                    self.project_name.setText(project_match.group(1))
                
                device_match = re.search(r'DEVICE\s*=\s*(\S+)', content)
                if device_match:
                    self.device_combo.setCurrentText(device_match.group(1))
                
                arch_match = re.search(r'ARCH\s*=\s*(\S+)', content)
                if arch_match:
                    self.arch_combo.setCurrentText(arch_match.group(1))
                
                f_cpu_match = re.search(r'F_CPU\s*=\s*(\d+)', content)
                if f_cpu_match:
                    self.f_cpu.setValue(int(f_cpu_match.group(1)))
                
                vdd_mv_match = re.search(r'TARGET_VDD_MV\s*=\s*(\d+)', content)
                if vdd_mv_match:
                    self.vdd_mv.setValue(int(vdd_mv_match.group(1)))
                
                vdd_v_match = re.search(r'TARGET_VDD\s*=\s*([\d.]+)', content)
                if vdd_v_match:
                    self.vdd_v.setValue(float(vdd_v_match.group(1)))
                
                # Fixed regex pattern for optimization flags
                opt_flags_match = re.search(r'OPT_FLAGS\s*=\s*([^\n]+)', content)
                if opt_flags_match:
                    self.opt_flags.setText(opt_flags_match.group(1))
        except FileNotFoundError:
            if QMessageBox.question(self, "Makefile Not Found", 
                                  "No Makefile found. Would you like to create a new one with default values?",
                                  QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                self.generate_default_makefile()
                # Don't call load_current_values recursively here
                # Just set default values directly
                self.project_name.setText("MyProject")
                self.device_combo.setCurrentText("PFS154")
                self.arch_combo.setCurrentText("pdk14")
                self.f_cpu.setValue(8000000)
                self.vdd_mv.setValue(5000)
                self.vdd_v.setValue(5.0)
                self.opt_flags.setText("--opt-code-size")
    
    def generate_default_makefile(self):
        """Generate a new Makefile with default values"""
        default_content = r"""# ---------------------------------------------------------------------
# Project configuration
# ---------------------------------------------------------------------
# Set the following variables:
#
# DEVICE       = <Device_Name>        # e.g., PFS154, PMS150C, etc.
# ARCH         = <Architecture_Name>  # e.g., pdk14, pdk15, pdk13
# PROJECT_NAME = <Project_Name>       # e.g., MyProject
#
# Required compile settings:
# F_CPU        = <Frequency>          # e.g., 8000000
# TARGET_VDD_MV = <Voltage_Millivolts> # e.g., 5000
# TARGET_VDD    = <Voltage_Volts>     # e.g., 5.0
#
# Optional:
# OPT_FLAGS     = --opt-code-size     # Code optimization flags
#
# Example:
# DEVICE = PFS154
# ARCH = pdk14
# PROJECT_NAME = MyProject
# F_CPU = 8000000
# TARGET_VDD_MV = 5000
# TARGET_VDD = 5.0
#
# ---------------------------------------------------------------------

# Default settings
DEVICE = PFS154
ARCH = pdk14
PROJECT_NAME = MyProject
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
COMPILE = sdcc -m$(ARCH) -c $(OPT_FLAGS) -D$(DEVICE) -DF_CPU=$(F_CPU) -DTARGET_VDD_MV=$(TARGET_VDD_MV) -DTARGET_VDD=$(TARGET_VDD) -I. -I include
LINK = sdcc -m$(ARCH)
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

"""
        try:
            with open("Makefile", "w") as f:
                f.write(default_content)
            QMessageBox.information(self, "Success", "New Makefile has been created with default values!")
            return True
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to create Makefile: {str(e)}")
            return False
    
    def update_makefile(self):
        try:
            with open("Makefile", "r") as f:
                content = f.read()
            
            # Update the values in the content with more lenient patterns
            content = re.sub(r'PROJECT_NAME\s*=\s*\S+', f'PROJECT_NAME = {self.project_name.text()}', content)
            content = re.sub(r'DEVICE\s*=\s*\S+', f'DEVICE = {self.device_combo.currentText()}', content)
            content = re.sub(r'ARCH\s*=\s*\S+', f'ARCH = {self.arch_combo.currentText()}', content)
            content = re.sub(r'F_CPU\s*=\s*\d+', f'F_CPU = {self.f_cpu.value()}', content)
            content = re.sub(r'TARGET_VDD_MV\s*=\s*\d+', f'TARGET_VDD_MV = {self.vdd_mv.value()}', content)
            content = re.sub(r'TARGET_VDD\s*=\s*[\d.]+', f'TARGET_VDD = {self.vdd_v.value()}', content)
            content = re.sub(r'OPT_FLAGS\s*=\s*[^\n]+', f'OPT_FLAGS = {self.opt_flags.text()}', content)
            
            with open("Makefile", "w") as f:
                f.write(content)
            
            QMessageBox.information(self, "Success", "Makefile has been updated successfully!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update Makefile: {str(e)}")

class BuildToolsTab(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.process = QProcess()
        self.process.readyReadStandardOutput.connect(self.handle_output)
        self.process.readyReadStandardError.connect(self.handle_error)
        
    def init_ui(self):
        layout = QVBoxLayout()
        
        # Action buttons
        button_layout = QHBoxLayout()
        self.build_btn = QPushButton("Build")
        self.size_btn = QPushButton("Show Size")
        self.program_btn = QPushButton("Program")
        self.run_btn = QPushButton("Run")
        self.clean_btn = QPushButton("Clean")
        
        button_layout.addWidget(self.build_btn)
        button_layout.addWidget(self.size_btn)
        button_layout.addWidget(self.program_btn)
        button_layout.addWidget(self.run_btn)
        button_layout.addWidget(self.clean_btn)
        
        layout.addLayout(button_layout)
        
        # Output display
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        layout.addWidget(self.output_text)
        
        # Connect signals
        self.build_btn.clicked.connect(self.build_project)
        self.size_btn.clicked.connect(self.show_size)
        self.program_btn.clicked.connect(self.program_device)
        self.run_btn.clicked.connect(self.run_project)
        self.clean_btn.clicked.connect(self.clean_project)
        
        self.setLayout(layout)
    
    def run_make_command(self, target):
        """Run a make command and display output"""
        self.output_text.clear()
        self.output_text.append(f"Running: make {target}\n")
        
        self.process.start('make', [target])
    
    def handle_output(self):
        """Handle process standard output"""
        output = self.process.readAllStandardOutput().data().decode()
        self.output_text.append(output)
    
    def handle_error(self):
        """Handle process standard error"""
        error = self.process.readAllStandardError().data().decode()
        self.output_text.append(error)
    
    def build_project(self):
        """Build the project"""
        self.run_make_command('build')
    
    def show_size(self):
        """Show memory usage"""
        self.run_make_command('size')
    
    def program_device(self):
        """Program the device"""
        self.run_make_command('program')
    
    def run_project(self):
        """Run the project"""
        self.run_make_command('run')
    
    def clean_project(self):
        """Clean the project"""
        self.run_make_command('clean')

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Padauk-maketools")
        self.setMinimumSize(800, 600)
        
        # Create tab widget
        tabs = QTabWidget()
        tabs.addTab(MakefileConfigTab(), "Makefile Config")
        tabs.addTab(BuildToolsTab(), "Build Tools")
        
        self.setCentralWidget(tabs)

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main() 
