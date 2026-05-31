#include <xc.h>
#include "system_test.h"

#pragma config FOSC = HS
#pragma config WDTE = OFF
#pragma config PWRTE = ON
#pragma config BOREN = ON
#pragma config LVP = OFF
#pragma config CPD = OFF
#pragma config WRT = OFF
#pragma config CP = OFF

void main()
{
    APP_SystemTest_Init();

    while(1)
    {
        APP_SystemTest_Task();
    }
}
