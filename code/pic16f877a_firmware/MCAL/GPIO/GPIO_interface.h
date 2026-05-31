#ifndef GPIO_INTERFACE_H
#define GPIO_INTERFACE_H

#include "STD_TYPES.h"

#define GPIO_PORTA 0
#define GPIO_PORTB 1
#define GPIO_PORTC 2
#define GPIO_PORTD 3
#define GPIO_PORTE 4

#define GPIO_PIN0 0
#define GPIO_PIN1 1
#define GPIO_PIN2 2
#define GPIO_PIN3 3
#define GPIO_PIN4 4
#define GPIO_PIN5 5
#define GPIO_PIN6 6
#define GPIO_PIN7 7

#define GPIO_OUTPUT 0
#define GPIO_INPUT  1

#define GPIO_LOW  0
#define GPIO_HIGH 1

void GPIO_Init(void);
void GPIO_SetPinDirection(u8 Port, u8 Pin, u8 Direction);
void GPIO_SetPinValue(u8 Port, u8 Pin, u8 Value);
void GPIO_TogglePin(u8 Port, u8 Pin);
u8 GPIO_GetPinValue(u8 Port, u8 Pin);

#endif
