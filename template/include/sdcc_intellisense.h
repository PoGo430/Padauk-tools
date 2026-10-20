/*
 * sdcc_intellisense.h - lets editors (VS Code C/C++, clangd) understand SDCC code.
 *
 * SDCC has a few keywords other C parsers don't know (__sfr, __at, __interrupt...).
 * This file is force-included by .vscode/c_cpp_properties.json only. It does
 * nothing when compiling with SDCC, because SDCC defines __SDCC.
 */
#ifndef SDCC_INTELLISENSE_H
#define SDCC_INTELLISENSE_H

#if !defined(__SDCC)

#define __sfr           volatile unsigned char
#define __sfr16         volatile unsigned short
#define __sfr32         volatile unsigned long
#define __at(addr)
#define __interrupt(n)
#define __naked
#define __critical
#define __reentrant
#define __code          const
#define __data
#define __near
#define __far
#define __sbit          volatile unsigned char
#define __bit           unsigned char

#endif // !__SDCC
#endif // SDCC_INTELLISENSE_H
