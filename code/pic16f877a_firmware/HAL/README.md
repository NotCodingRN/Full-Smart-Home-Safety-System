# HAL Layer

The tested HAL-like behavior is kept inside `Services/SmartHomeIO/system_test.c` to preserve the stack-safe firmware path that was validated on PIC16F877A.

Logical HAL blocks implemented there:

- I2C 16x2 LCD over PCF8574
- DHT11 one-wire acquisition
- MQ-2 and soil ADC sampling
- Relay active-low control
- Servo pulse generation
- IR digital sensing

Reusable low-level drivers are under `MCAL/`.
