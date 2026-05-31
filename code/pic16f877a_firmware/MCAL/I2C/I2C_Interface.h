#ifndef I2C_INTERFACE_H
#define I2C_INTERFACE_H

#include "STD_TYPES.h"

typedef struct
{
    u32 ClockHz;
} I2C_ConfigType;

void I2C_Init(I2C_ConfigType *ConfigPtr);
void I2C_MasterStart(void);
void I2C_MasterRepeatedStart(void);
void I2C_MasterStop(void);
void I2C_MasterWriteByte(u8 Data);
u8 I2C_MasterReadByte(u8 AckState);

#endif
