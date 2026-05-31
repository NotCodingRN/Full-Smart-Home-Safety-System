#ifndef UART_PRIVATE_H
#define UART_PRIVATE_H

#include "STD_TYPES.h"

#define TXSTA    (*((volatile u8*)0x98))
#define RCSTA    (*((volatile u8*)0x18))
#define SPBRG    (*((volatile u8*)0x99))
#define TXREG    (*((volatile u8*)0x19))
#define RCREG    (*((volatile u8*)0x1A))
#define PIR1_U   (*((volatile u8*)0x0C))
#define PIE1_U   (*((volatile u8*)0x8C))
#define INTCON_U (*((volatile u8*)0x0B))

#define TXEN_BIT 5
#define SYNC_BIT 4
#define BRGH_BIT 2
#define TRMT_BIT 1

#define SPEN_BIT 7
#define CREN_BIT 4
#define FERR_BIT 2
#define OERR_BIT 1

#define RCIF_BIT 5
#define RCIE_BIT 5

#define PEIE_BIT 6
#define GIE_U_BIT 7

#endif
