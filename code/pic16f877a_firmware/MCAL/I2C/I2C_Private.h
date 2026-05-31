#ifndef I2C_PRIVATE_H
#define I2C_PRIVATE_H

#include "STD_TYPES.h"

#define SSPCON_I2C  (*((volatile u8*)0x14))
#define SSPCON2_I2C (*((volatile u8*)0x91))
#define SSPSTAT_I2C (*((volatile u8*)0x94))
#define SSPADD_I2C  (*((volatile u8*)0x93))
#define SSPBUF_I2C  (*((volatile u8*)0x13))
#define PIR1_I2C    (*((volatile u8*)0x0C))

#define SSPEN_I2C_BIT 5
#define SEN_BIT       0
#define RSEN_BIT      1
#define PEN_BIT       2
#define RCEN_BIT      3
#define ACKEN_BIT     4
#define ACKDT_BIT     5
#define SSPIF_I2C_BIT 3

#endif
