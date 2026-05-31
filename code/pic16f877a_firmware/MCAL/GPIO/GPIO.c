#include "GPIO_interface.h"
#include "GPIO_private.h"
#include "GPIO_config.h"
#include "BIT_MATH.h"

void GPIO_Init(void)
{
    TRISA = GPIO_PORTA_DIR;
    TRISB = GPIO_PORTB_DIR;
    TRISC = GPIO_PORTC_DIR;
    TRISD = GPIO_PORTD_DIR;
    TRISE = GPIO_PORTE_DIR;

    PORTA = GPIO_PORTA_INIT_VAL;
    PORTB = GPIO_PORTB_INIT_VAL;
    PORTC = GPIO_PORTC_INIT_VAL;
    PORTD = GPIO_PORTD_INIT_VAL;
    PORTE = GPIO_PORTE_INIT_VAL;
}

void GPIO_SetPinDirection(u8 Port, u8 Pin, u8 Direction)
{
    switch (Port)
    {
        case GPIO_PORTA:
            if (Direction == GPIO_OUTPUT) { CLR_BIT(TRISA, Pin); } else { SET_BIT(TRISA, Pin); }
            break;
        case GPIO_PORTB:
            if (Direction == GPIO_OUTPUT) { CLR_BIT(TRISB, Pin); } else { SET_BIT(TRISB, Pin); }
            break;
        case GPIO_PORTC:
            if (Direction == GPIO_OUTPUT) { CLR_BIT(TRISC, Pin); } else { SET_BIT(TRISC, Pin); }
            break;
        case GPIO_PORTD:
            if (Direction == GPIO_OUTPUT) { CLR_BIT(TRISD, Pin); } else { SET_BIT(TRISD, Pin); }
            break;
        case GPIO_PORTE:
            if (Direction == GPIO_OUTPUT) { CLR_BIT(TRISE, Pin); } else { SET_BIT(TRISE, Pin); }
            break;
        default:
            break;
    }
}

void GPIO_SetPinValue(u8 Port, u8 Pin, u8 Value)
{
    switch (Port)
    {
        case GPIO_PORTA:
            if (Value == GPIO_HIGH) { SET_BIT(PORTA, Pin); } else { CLR_BIT(PORTA, Pin); }
            break;
        case GPIO_PORTB:
            if (Value == GPIO_HIGH) { SET_BIT(PORTB, Pin); } else { CLR_BIT(PORTB, Pin); }
            break;
        case GPIO_PORTC:
            if (Value == GPIO_HIGH) { SET_BIT(PORTC, Pin); } else { CLR_BIT(PORTC, Pin); }
            break;
        case GPIO_PORTD:
            if (Value == GPIO_HIGH) { SET_BIT(PORTD, Pin); } else { CLR_BIT(PORTD, Pin); }
            break;
        case GPIO_PORTE:
            if (Value == GPIO_HIGH) { SET_BIT(PORTE, Pin); } else { CLR_BIT(PORTE, Pin); }
            break;
        default:
            break;
    }
}

void GPIO_TogglePin(u8 Port, u8 Pin)
{
    switch (Port)
    {
        case GPIO_PORTA: TOG_BIT(PORTA, Pin); break;
        case GPIO_PORTB: TOG_BIT(PORTB, Pin); break;
        case GPIO_PORTC: TOG_BIT(PORTC, Pin); break;
        case GPIO_PORTD: TOG_BIT(PORTD, Pin); break;
        case GPIO_PORTE: TOG_BIT(PORTE, Pin); break;
        default: break;
    }
}

u8 GPIO_GetPinValue(u8 Port, u8 Pin)
{
    u8 Local_Value = 0;

    switch (Port)
    {
        case GPIO_PORTA: Local_Value = GET_BIT(PORTA, Pin); break;
        case GPIO_PORTB: Local_Value = GET_BIT(PORTB, Pin); break;
        case GPIO_PORTC: Local_Value = GET_BIT(PORTC, Pin); break;
        case GPIO_PORTD: Local_Value = GET_BIT(PORTD, Pin); break;
        case GPIO_PORTE: Local_Value = GET_BIT(PORTE, Pin); break;
        default: break;
    }

    return Local_Value;
}
