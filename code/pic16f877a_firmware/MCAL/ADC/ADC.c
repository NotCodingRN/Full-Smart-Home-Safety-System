#include "ADC_Interface.h"
#include "ADC_Private.h"
#include "GPIO_interface.h"
#include "BIT_MATH.h"

void ADC_Init(ADC_ConfigType *ConfigPtr)
{
    if (ConfigPtr == 0)
    {
        return;
    }

    ADCON1 = ConfigPtr->PortConfig;

    if (ConfigPtr->RightJustified != 0)
    {
        SET_BIT(ADCON1, ADFM_BIT);
    }
    else
    {
        CLR_BIT(ADCON1, ADFM_BIT);
    }

    ADC_SelectChannel(ConfigPtr->Channel);
    SET_BIT(ADCON0, ADON_BIT);
}

void ADC_SelectChannel(u8 Channel)
{
    ADCON0 &= (u8)~0x38;
    ADCON0 |= (u8)((Channel & 0x07) << CHS0_BIT);
    switch (Channel)
    {
        case ADC_CHANNEL_0: GPIO_SetPinDirection(GPIO_PORTA, GPIO_PIN0, GPIO_INPUT); break;
        case ADC_CHANNEL_1: GPIO_SetPinDirection(GPIO_PORTA, GPIO_PIN1, GPIO_INPUT); break;
        case ADC_CHANNEL_2: GPIO_SetPinDirection(GPIO_PORTA, GPIO_PIN2, GPIO_INPUT); break;
        case ADC_CHANNEL_3: GPIO_SetPinDirection(GPIO_PORTA, GPIO_PIN3, GPIO_INPUT); break;
        case ADC_CHANNEL_4: GPIO_SetPinDirection(GPIO_PORTA, GPIO_PIN5, GPIO_INPUT); break;
        case ADC_CHANNEL_5: GPIO_SetPinDirection(GPIO_PORTE, GPIO_PIN0, GPIO_INPUT); break;
        case ADC_CHANNEL_6: GPIO_SetPinDirection(GPIO_PORTE, GPIO_PIN1, GPIO_INPUT); break;
        case ADC_CHANNEL_7: GPIO_SetPinDirection(GPIO_PORTE, GPIO_PIN2, GPIO_INPUT); break;
        default: break;
    }
}

u16 ADC_ReadChannel(u8 Channel)
{
    ADC_SelectChannel(Channel);
    SET_BIT(ADCON0, GO_DONE_BIT);

    while (GET_BIT(ADCON0, GO_DONE_BIT) != 0)
    {
    }

    return (u16)(((u16)ADRESH << 8) | ADRESL);
}
