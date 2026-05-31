#ifndef ADC_INTERFACE_H
#define ADC_INTERFACE_H

#include "STD_TYPES.h"

#define ADC_CHANNEL_0 0
#define ADC_CHANNEL_1 1
#define ADC_CHANNEL_2 2
#define ADC_CHANNEL_3 3
#define ADC_CHANNEL_4 4
#define ADC_CHANNEL_5 5
#define ADC_CHANNEL_6 6
#define ADC_CHANNEL_7 7

typedef struct
{
    u8 Channel;
    u8 ConversionClock;
    u8 PortConfig;
    u8 RightJustified;
} ADC_ConfigType;

void ADC_Init(ADC_ConfigType *ConfigPtr);
void ADC_SelectChannel(u8 Channel);
u16 ADC_ReadChannel(u8 Channel);

#endif
