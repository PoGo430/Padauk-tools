#include <pdk/device.h>
#include <stdint.h>
#include <auto_sysclock.h>
#include <startup.h>


void main(void)
{


}

// Startup code - Setup/calibrate system clock
unsigned char STARTUP_FUNCTION(void)
{

    // Initialize the system clock (CLKMD register) with the IHRC, ILRC, or EOSC clock source and correct divider.
    // The AUTO_INIT_SYSCLOCK() macro uses F_CPU to choose the IHRC or ILRC clock source and divider.
    // Alternatively, replace this with the more specific PDK_SET_SYSCLOCK(...) macro from pdk/sysclock.h
    AUTO_INIT_SYSCLOCK();

    // Insert placeholder code to tell EasyPdkProg to calibrate the IHRC or ILRC internal oscillator.
    // The AUTO_CALIBRATE_SYSCLOCK(...) macro uses F_CPU to choose the IHRC or ILRC oscillator.
    // Alternatively, replace this with the more specific EASY_PDK_CALIBRATE_IHRC(...) or EASY_PDK_CALIBRATE_ILRC(...) macro from easy-pdk/calibrate.h
    AUTO_CALIBRATE_SYSCLOCK(TARGET_VDD_MV);

    return 0; // Return 0 to inform SDCC to continue with normal initialization.
}
