# PIC16F877A Firmware

Layering:

- `Common/`: types and bit macros
- `MCAL/`: GPIO, ADC, UART, I2C
- `HAL/`: documentation of hardware-abstraction blocks
- `Services/SmartHomeIO/`: LCD, DHT11, sensors, relays, servo, UART protocol
- `APP/`: fuse bits and scheduler loop

Build with XC8 using include paths listed in the root README.
