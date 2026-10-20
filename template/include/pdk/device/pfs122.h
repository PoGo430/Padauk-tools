/*
  pfs122.h: FUSE and Register Definitions for the Padauk PFS122 device.

  Written from the PFS122 datasheet (PDK-DS-PFS122-EN V004, 2025-09-02), chapter 6
  "IO Registers", for Padauk-tools. It follows the layout of the free-pdk
  pdk-includes device headers so the usual macro names (PAC, TM2C_..., ADCC_...) work.

  Copyright (C) 2019-2020  freepdk  https://free-pdk.github.io  (pdk-includes structure)

  This library is free software; you can redistribute it and/or modify it
  under the terms of the GNU General Public License as published by the
  Free Software Foundation; either version 2, or (at your option) any later version.

  This library is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  As a special exception, if you link this library with other files,
  some of which are compiled with SDCC, to produce an executable,
  this library does not by itself cause the resulting executable to
  be covered by the GNU General Public License.
*/

#ifndef __PDK_DEVICE_PFS122_H__
#define __PDK_DEVICE_PFS122_H__

#if !defined(__PDK_DEVICE_XXX_H__)
	#define __PDK_DEVICE_XXX_H__ "pfs122.h"
#else
	#error "Attempt to include more than one "pdk/device/XXX.h" file."
#endif

#if !defined(__SDCC_pdk14)
	#error "PFS122 needs the PDK14 backend. You must compile with the -mpdk14 option."
#endif

// Datasheet 4.1: ILRC typ. 56 kHz at VDD = 5.0 V
#define ILRC_FREQ           56000


// ===========================================================================
// Registers in the datasheet (chapter 6, IO Registers)
// ===========================================================================
#define FLAG_ADDR           0x00    // 6.1  ACC status flag
//0x01
#define SP_ADDR             0x02    // 6.2  stack pointer
#define CLKMD_ADDR          0x03    // 6.3  clock mode
#define INTEN_ADDR          0x04    // 6.4  interrupt enable
#define INTRQ_ADDR          0x05    // 6.5  interrupt request
#define T16M_ADDR           0x06    // 6.6  Timer16 mode
//0x07..0x09
#define EOSCR_ADDR          0x0a    // 6.7  external oscillator setting
//0x0b: IHRCR, see below
#define INTEGS_ADDR         0x0c    // 6.8  interrupt edge select
#define PADIER_ADDR         0x0d    // 6.9  port A digital input enable
#define PBDIER_ADDR         0x0e    // 6.10 port B digital input enable
//0x0f
#define PA_ADDR             0x10    // 6.11
#define PAC_ADDR            0x11    // 6.12
#define PAPH_ADDR           0x12    // 6.13 pull-high
#define PAPL_ADDR           0x13    // 6.14 pull-low
//0x14
#define PB_ADDR             0x15    // 6.15
#define PBC_ADDR            0x16    // 6.16
#define PBPH_ADDR           0x17    // 6.17 pull-high
#define PBPL_ADDR           0x18    // 6.18 pull-low
//0x19..0x1f
#define ADCC_ADDR           0x20    // 6.19 ADC control
#define ADCM_ADDR           0x21    // 6.20 ADC mode
#define ADCRH_ADDR          0x22    // 6.21 ADC result bits 11..4
#define ADCRL_ADDR          0x23    // 6.22 ADC result bits 3..0 (in bits 7..4)
//0x24, 0x25
#define MISC_ADDR           0x26    // 6.23
//0x27, 0x28: code options, see below
//0x29, 0x2a
#define GPCC_ADDR           0x2b    // 6.24 comparator control
#define GPCS_ADDR           0x2c    // 6.25 comparator selection
//0x2d..0x2f
#define TM2C_ADDR           0x30    // 6.26
#define TM2CT_ADDR          0x31    // 6.27
#define TM2S_ADDR           0x32    // 6.28
#define TM2B_ADDR           0x33    // 6.29
#define TM3C_ADDR           0x34    // 6.30
#define TM3CT_ADDR          0x35    // 6.31
#define TM3S_ADDR           0x36    // 6.32
#define TM3B_ADDR           0x37    // 6.33


// ===========================================================================
// Not in the PFS122 datasheet's register list, but needed:
// - IHRCR / ILRCR / BGTR: oscillator and bandgap trim registers. The datasheet says
//   IHRC calibration is done by the writer (9.1.6); easypdkprog's calibration code
//   (easy-pdk/calibrate.h) writes these, at the same addresses as on the PFS172.
// - Code options (datasheet chapter 8): Interrupt Src0/Src1, LVR, Comparator Edge,
//   GPC_PWM, TMx_Source, TMx_Bit are chosen "at compile time" in Padauk's IDE, which
//   writes them to registers the datasheet doesn't describe. The PFS122 has the same
//   chip ID as the PFS172, whose code-option registers (ROP, MISCLVR, MISC2) free-pdk
//   documented from Padauk's PFS172.INC. Security, Boot-up_Time and PB4_PB7_Drive are
//   in the fuse word.
// ===========================================================================
#define IHRCR_ADDR          0x0b
#define MISC2_ADDR          0x27    // code option: Comparator Edge
#define MISCLVR_ADDR        0x28    // code option: LVR
#define ILRCR_ADDR          0x3b
#define BGTR_ADDR           0x3c
#define ROP_ADDR            0x3d    // code options: Interrupt Src0/Src1, TMx_Bit, TMx_Source, GPC_PWM

// Factory calibration values in the reserved area at the end of the ROM
#define FACTORY_IHRCR_ADDR  0x07ed
#define FACTORY_BGTR_ADDR   0x07ee

// Fuse word (code options Security, PB4_PB7_Drive, Boot-up_Time)
#define FUSE_WORD_ADDR      0x07ff
#define FUSE_RES_BITS_HIGH  0x017C    // - - B B   0 0 0 1   D 1 1 1   1 1 0 S => 0x017C
#define FUSE_SECURITY_ON    0x0000    //(S) program can't be read back
#define FUSE_SECURITY_OFF   (1 << 0)
#define FUSE_PB4_PB7_NORMAL 0x0000    //(D) datasheet 4.1: sink 21 mA, drive 11 mA
#define FUSE_PB4_PB7_STRONG (1 << 7)  //    sink 35 mA, drive 23 mA
#define FUSE_BOOTUP_SLOW    0x0000    //(B)
#define FUSE_BOOTUP_FAST    (3 << 12)

// ROP bits: code options (chapter 8)
#define ROP_PB0_PA4_SEL_BIT          0    // Interrupt Src1: PB0 / PA4
#define ROP_PA0_PB5_SEL_BIT          1    // Interrupt Src0: PA0 / PB5
#define ROP_TMX_BIT_SEL_BIT          4    // TMx_Bit: 6 / 7 bit PWM when TMxS.7 = 1
#define ROP_TMX_FREQ_SEL_BIT         5    // TMx_Source: IHRC 16 MHz / IHRC*2 32 MHz
#define ROP_PWM_SEL_BIT              6    // GPC_PWM: comparator controls the PWM outputs


// ===========================================================================
// Peripherals. The shared pdk-includes peripheral headers below match the PFS122
// datasheet bit for bit (checked against chapter 6); the ADC is defined here because
// the PFS122's 12-bit ADC has no resolution bits in ADCM.
// ===========================================================================
#define __PDK_HAS_COMP
#define __PDK_HAS_EOSC
#define __PDK_HAS_PORTB
#define __PDK_HAS_PB5_PA4_INT
#define __PDK_HAS_TM3
#define __PDK_HAS_ADC

#include "periph/accumulator.h"
#include "periph/stack.h"
#include "periph/clock.h"
#include "periph/external_oscillator.h"
#include "periph/interrupt.h"
#include "periph/port_a.h"
#include "periph/port_b.h"
#include "periph/timer_16.h"
#include "periph/timer_2.h"
#include "periph/timer_3.h"
#include "periph/bandgap.h"
#include "periph/comparator.h"
#include "periph/misc.h"
#include "periph/misc2.h"
#include "periph/misclvr.h"
#include "periph/rop.h"


// ---- ADC (datasheet 5.13, 6.19 - 6.22) -------------------------------------
__sfr __at(ADCC_ADDR)         _adcc;
__sfr __at(ADCM_ADDR)         _adcm;
__sfr __at(ADCRH_ADDR)        _adcrh;
__sfr __at(ADCRL_ADDR)        _adcrl;

#define ADCC                  _adcc
#define ADCM                  _adcm
#define ADCRH                 _adcrh      // result bits 11..4
#define ADCRL                 _adcrl      // result bits 3..0 in bits 7..4
#define ADCR                  ADCRH       // 8-bit result (upper bits), for code written for 8-bit ADCs

// 12-bit result 0..4095 (4096 = VDD, the only ADC reference on the PFS122)
#define ADC_RESULT_12BIT()    ((uint16_t)(((uint16_t)ADCRH << 4) | (ADCRL >> 4)))

// ADCC (6.19)
#define ADCC_CHANNEL_SEL_BIT0        2
#define ADCC_PROCESS_CONTROL_BIT     6
#define ADCC_ENABLE_BIT              7

#define ADCC_CH_AD0_PB0              0x00
#define ADCC_CH_AD1_PB1              (1 << ADCC_CHANNEL_SEL_BIT0)
#define ADCC_CH_AD2_PB2              (2 << ADCC_CHANNEL_SEL_BIT0)
#define ADCC_CH_AD3_PB3              (3 << ADCC_CHANNEL_SEL_BIT0)
#define ADCC_CH_AD4_PB4              (4 << ADCC_CHANNEL_SEL_BIT0)
#define ADCC_CH_AD5_PB5              (5 << ADCC_CHANNEL_SEL_BIT0)
#define ADCC_CH_AD6_PB6              (6 << ADCC_CHANNEL_SEL_BIT0)
#define ADCC_CH_AD7_PB7              (7 << ADCC_CHANNEL_SEL_BIT0)
#define ADCC_CH_AD8_PA3              (8 << ADCC_CHANNEL_SEL_BIT0)
#define ADCC_CH_AD9_PA4              (9 << ADCC_CHANNEL_SEL_BIT0)
#define ADCC_CH_AD10_PA0             (10 << ADCC_CHANNEL_SEL_BIT0)
#define ADCC_CH_BANDGAP              (15 << ADCC_CHANNEL_SEL_BIT0)   // 1.20 V bandgap ("channel F")
#define ADCC_CH_AD16_BANDGAP         ADCC_CH_BANDGAP

#define ADCC_START_ADC_CONV          (1 << ADCC_PROCESS_CONTROL_BIT) // write 1: start
#define ADCC_IS_ADC_CONV_READY       (1 << ADCC_PROCESS_CONTROL_BIT) // read 1: done
#define ADCC_ADC_ENABLE              (1 << ADCC_ENABLE_BIT)

// ADCM (6.20): ADC clock = system clock / n. Datasheet 5.13.2: about 2 us per ADC clock (500 kHz)
#define ADCM_CLK_SRC_BIT0            1

#define ADCM_CLK_SYSCLK              0x00
#define ADCM_CLK_SYSCLK_DIV2         (1 << ADCM_CLK_SRC_BIT0)
#define ADCM_CLK_SYSCLK_DIV4         (2 << ADCM_CLK_SRC_BIT0)
#define ADCM_CLK_SYSCLK_DIV8         (3 << ADCM_CLK_SRC_BIT0)
#define ADCM_CLK_SYSCLK_DIV16        (4 << ADCM_CLK_SRC_BIT0)
#define ADCM_CLK_SYSCLK_DIV32        (5 << ADCM_CLK_SRC_BIT0)
#define ADCM_CLK_SYSCLK_DIV64        (6 << ADCM_CLK_SRC_BIT0)
#define ADCM_CLK_SYSCLK_DIV128       (7 << ADCM_CLK_SRC_BIT0)


// ---- Code option values (chapter 8) not covered by the peripheral headers ----
// LVR (code option): the 8 levels the datasheet lists
#define LVR_4V                       MISCLVR_4V
#define LVR_3V5                      MISCLVR_3V5
#define LVR_3V                       MISCLVR_3V
#define LVR_2V7                      MISCLVR_2V7
#define LVR_2V5                      MISCLVR_2V5
#define LVR_2V2                      MISCLVR_2V2
#define LVR_2V                       MISCLVR_2V
#define LVR_1V8                      MISCLVR_1V8

#endif //__PDK_DEVICE_PFS122_H__
