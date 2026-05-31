#include "UART_Interface.h"
#include "UART_Private.h"
#include "UART_Config.h"
#include "GPIO_interface.h"
#include "BIT_MATH.h"

static u8 UART_CalculateSpbrg(u32 BaudRate, u8 HighSpeed)
{
    if (BaudRate == 0)
    {
        return 0;
    }

    if (HighSpeed != 0)
    {
        return (u8)((UART_FOSC_HZ / (16UL * BaudRate)) - 1UL);
    }

    return (u8)((UART_FOSC_HZ / (64UL * BaudRate)) - 1UL);
}

void UART_Init(UART_ConfigType *ConfigPtr)
{
    if (ConfigPtr == 0)
    {
        return;
    }

    GPIO_SetPinDirection(GPIO_PORTC, GPIO_PIN6, GPIO_OUTPUT);
    GPIO_SetPinDirection(GPIO_PORTC, GPIO_PIN7, GPIO_INPUT);

    CLR_BIT(TXSTA, SYNC_BIT);
    SET_BIT(RCSTA, SPEN_BIT);

    if (ConfigPtr->HighSpeed != 0)
    {
        SET_BIT(TXSTA, BRGH_BIT);
    }
    else
    {
        CLR_BIT(TXSTA, BRGH_BIT);
    }

    SPBRG = UART_CalculateSpbrg(ConfigPtr->BaudRate, ConfigPtr->HighSpeed);

    if (ConfigPtr->EnableTx != 0)
    {
        SET_BIT(TXSTA, TXEN_BIT);
    }
    else
    {
        CLR_BIT(TXSTA, TXEN_BIT);
    }

    if (ConfigPtr->EnableRx != 0)
    {
        SET_BIT(RCSTA, CREN_BIT);
    }
    else
    {
        CLR_BIT(RCSTA, CREN_BIT);
    }

    if (ConfigPtr->RxInterruptEnable != 0)
    {
        SET_BIT(PIE1_U, RCIE_BIT);
        SET_BIT(INTCON_U, PEIE_BIT);
        SET_BIT(INTCON_U, GIE_U_BIT);
    }
}

void UART_WriteByte(u8 Data)
{
    while (GET_BIT(TXSTA, TRMT_BIT) == 0)
    {
    }

    TXREG = Data;
}

void UART_WriteString(u8 *StringPtr)
{
    if (StringPtr == 0)
    {
        return;
    }

    while (*StringPtr != '\0')
    {
        UART_WriteByte(*StringPtr);
        StringPtr++;
    }
}

u8 UART_ReadByte(void)
{
    if (GET_BIT(RCSTA, OERR_BIT) != 0)
    {
        CLR_BIT(RCSTA, CREN_BIT);
        SET_BIT(RCSTA, CREN_BIT);
    }

    while (GET_BIT(PIR1_U, RCIF_BIT) == 0)
    {
    }

    return RCREG;
}
