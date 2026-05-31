#include "I2C_Interface.h"
#include "I2C_Private.h"
#include "I2C_Config.h"
#include "GPIO_interface.h"
#include "BIT_MATH.h"

void I2C_Init(I2C_ConfigType *ConfigPtr)
{
    if ((ConfigPtr == 0) || (ConfigPtr->ClockHz == 0))
    {
        return;
    }

    GPIO_SetPinDirection(GPIO_PORTC, GPIO_PIN3, GPIO_INPUT);
    GPIO_SetPinDirection(GPIO_PORTC, GPIO_PIN4, GPIO_INPUT);

    SSPCON_I2C = 0x28;
    SSPSTAT_I2C = 0x00;
    SSPADD_I2C = (u8)((I2C_FOSC_HZ / (4UL * ConfigPtr->ClockHz)) - 1UL);
    SET_BIT(SSPCON_I2C, SSPEN_I2C_BIT);
}

void I2C_MasterStart(void)
{
    while ((SSPCON2_I2C & 0x1F) != 0)
    {
    }
    SET_BIT(SSPCON2_I2C, SEN_BIT);
    while (GET_BIT(SSPCON2_I2C, SEN_BIT) != 0)
    {
    }
}

void I2C_MasterRepeatedStart(void)
{
    while ((SSPCON2_I2C & 0x1F) != 0)
    {
    }
    SET_BIT(SSPCON2_I2C, RSEN_BIT);
    while (GET_BIT(SSPCON2_I2C, RSEN_BIT) != 0)
    {
    }
}

void I2C_MasterStop(void)
{
    while ((SSPCON2_I2C & 0x1F) != 0)
    {
    }
    SET_BIT(SSPCON2_I2C, PEN_BIT);
    while (GET_BIT(SSPCON2_I2C, PEN_BIT) != 0)
    {
    }
}

void I2C_MasterWriteByte(u8 Data)
{
    while ((SSPCON2_I2C & 0x1F) != 0)
    {
    }
    CLR_BIT(PIR1_I2C, SSPIF_I2C_BIT);
    SSPBUF_I2C = Data;
    while (GET_BIT(PIR1_I2C, SSPIF_I2C_BIT) == 0)
    {
    }
}

u8 I2C_MasterReadByte(u8 AckState)
{
    while ((SSPCON2_I2C & 0x1F) != 0)
    {
    }
    SET_BIT(SSPCON2_I2C, RCEN_BIT);
    while (GET_BIT(SSPCON2_I2C, RCEN_BIT) != 0)
    {
    }

    if (AckState != 0)
    {
        CLR_BIT(SSPCON2_I2C, ACKDT_BIT);
    }
    else
    {
        SET_BIT(SSPCON2_I2C, ACKDT_BIT);
    }

    SET_BIT(SSPCON2_I2C, ACKEN_BIT);
    while (GET_BIT(SSPCON2_I2C, ACKEN_BIT) != 0)
    {
    }

    return SSPBUF_I2C;
}
