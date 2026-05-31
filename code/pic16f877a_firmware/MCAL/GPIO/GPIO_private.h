#ifndef GPIO_PRIVATE_H
#define GPIO_PRIVATE_H

#include "STD_TYPES.h"

#define PORTA (*((volatile u8*)0x05))
#define PORTB (*((volatile u8*)0x06))
#define PORTC (*((volatile u8*)0x07))
#define PORTD (*((volatile u8*)0x08))
#define PORTE (*((volatile u8*)0x09))

#define TRISA (*((volatile u8*)0x85))
#define TRISB (*((volatile u8*)0x86))
#define TRISC (*((volatile u8*)0x87))
#define TRISD (*((volatile u8*)0x88))
#define TRISE (*((volatile u8*)0x89))

#endif
