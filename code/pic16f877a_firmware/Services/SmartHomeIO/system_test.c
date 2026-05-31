#define _XTAL_FREQ 20000000UL

#include <xc.h>
#include "system_test.h"
#include "ADC_Interface.h"
#include "GPIO_interface.h"
#include "I2C_Interface.h"
#include "UART_Interface.h"

#define MQ2_ADC_CHANNEL        ADC_CHANNEL_0
#define SOIL_1_ADC_CHANNEL     ADC_CHANNEL_1
#define SOIL_2_ADC_CHANNEL     ADC_CHANNEL_2

#define IR_1_PORT              GPIO_PORTB
#define IR_1_PIN               GPIO_PIN0
#define IR_2_PORT              GPIO_PORTB
#define IR_2_PIN               GPIO_PIN1
#define DHT_PORT               GPIO_PORTB
#define DHT_PIN                GPIO_PIN3

#define RELAY_1_PORT           GPIO_PORTD
#define RELAY_1_PIN            GPIO_PIN0
#define RELAY_2_PORT           GPIO_PORTD
#define RELAY_2_PIN            GPIO_PIN1
#define RELAY_3_PORT           GPIO_PORTD
#define RELAY_3_PIN            GPIO_PIN2

#define SERVO_PORT             GPIO_PORTC
#define SERVO_PIN              GPIO_PIN2

#define LCD_I2C_ADDR           0x27
#define LCD_BACKLIGHT          0x08
#define LCD_ENABLE             0x04
#define LCD_RS                 0x01

#define IR_ACTIVE_LEVEL        GPIO_LOW
#define RELAY_ACTIVE_LOW       1
#if RELAY_ACTIVE_LOW
#define RELAY_ON               GPIO_LOW
#define RELAY_OFF              GPIO_HIGH
#else
#define RELAY_ON               GPIO_HIGH
#define RELAY_OFF              GPIO_LOW
#endif

#define CMD_BUFFER_SIZE        48
#define LCD_LINE_SIZE          16

#define DHT_ERR_NONE           0
#define DHT_ERR_RESPONSE_LOW   1
#define DHT_ERR_RESPONSE_HIGH  2
#define DHT_ERR_DATA_START     3
#define DHT_ERR_BIT_HIGH       4
#define DHT_ERR_BIT_LOW        5
#define DHT_ERR_CHECKSUM       6
#define DHT_ERR_PULSE          7

#define DHT_PULSE_TIMEOUT      6000U
#define DHT_TIMEOUT_VALUE      0xFFFFU
#define DHT_PULLUP_TIME_US     55U
#define DHT_PIN_MASK           (1U << DHT_PIN)

#define SERVO_CLOSE_US         1000U
#define SERVO_OPEN_US          2500U
#define SERVO_MIN_US           500U
#define SERVO_MAX_US           2500U
#define SERVO_PULSE_COUNT      80U
#define SERVO_SWEEP_STEP_US    100U
#define SERVO_SWEEP_PULSES     3U

typedef struct
{
    u16 mq2;
    u16 soil1;
    u16 soil2;
    u8 temp_c;
    u8 humidity;
    u8 dht_ok;
    u8 ir1_active;
    u8 ir2_active;
    u8 relay1_on;
    u8 relay2_on;
    u8 relay3_on;
} SensorDataType;

static ADC_ConfigType AppAdcConfig = {MQ2_ADC_CHANNEL, 0, 0x80, 1};
static I2C_ConfigType AppI2cConfig = {100000UL};
static UART_ConfigType AppUartConfig = {9600UL, 1, 1, 1, 0};

static SensorDataType Sensors;
static char CmdBuffer[CMD_BUFFER_SIZE];
static u8 CmdIndex = 0;
static u8 DhtLastError = DHT_ERR_NONE;

static void UART_WriteConst(const char *TextPtr);
static void UART_WriteU16(u16 Value);
static void LCD_Send4Bits(u8 Nibble, u8 Control);
static void LCD_SendCommand(u8 Command);
static void LCD_SendData(u8 Data);
static void LCD_Init(void);
static void LCD_Clear(void);
static void LCD_WriteLineConst(u8 Row, const char *TextPtr);
static void LCD_WriteLineRam(u8 Row, char *TextPtr);
static u8 DHT_ReadLevel(void);
static u16 DHT_ExpectPulse(u8 Level);
static u8 DHT_Read(u8 *TempPtr, u8 *HumidityPtr);
static u16 ReadAdcStable(u8 Channel);
static void ReadSensors(void);
static void SendSensorFrame(void);
static void SetRelay(u8 RelayNumber, u8 State);
static void ServoWritePulse(u16 HighTimeUs);
static void ServoMove(u16 HighTimeUs);
static void ServoSweep(u16 StartUs, u16 EndUs);
static u8 StringEquals(const char *LeftPtr, const char *RightPtr);
static u8 StringStartsWith(const char *TextPtr, const char *PrefixPtr);
static u16 ParseU16(const char *TextPtr);
static void HandleCommand(char *CommandPtr);

void APP_SystemTest_Init(void)
{
    GPIO_Init();

    ADC_Init(&AppAdcConfig);
    I2C_Init(&AppI2cConfig);
    UART_Init(&AppUartConfig);

    GPIO_SetPinDirection(IR_1_PORT, IR_1_PIN, GPIO_INPUT);
    GPIO_SetPinDirection(IR_2_PORT, IR_2_PIN, GPIO_INPUT);
    GPIO_SetPinDirection(DHT_PORT, DHT_PIN, GPIO_INPUT);

    GPIO_SetPinValue(RELAY_1_PORT, RELAY_1_PIN, RELAY_OFF);
    GPIO_SetPinValue(RELAY_2_PORT, RELAY_2_PIN, RELAY_OFF);
    GPIO_SetPinValue(RELAY_3_PORT, RELAY_3_PIN, RELAY_OFF);

    GPIO_SetPinDirection(RELAY_1_PORT, RELAY_1_PIN, GPIO_OUTPUT);
    GPIO_SetPinDirection(RELAY_2_PORT, RELAY_2_PIN, GPIO_OUTPUT);
    GPIO_SetPinDirection(RELAY_3_PORT, RELAY_3_PIN, GPIO_OUTPUT);
    GPIO_SetPinDirection(SERVO_PORT, SERVO_PIN, GPIO_OUTPUT);
    GPIO_SetPinValue(SERVO_PORT, SERVO_PIN, GPIO_LOW);

    Sensors.relay1_on = 0;
    Sensors.relay2_on = 0;
    Sensors.relay3_on = 0;

    LCD_Init();
    LCD_WriteLineConst(0, "PIC IO READY");
    LCD_WriteLineConst(1, "WAITING FOR PI");

    UART_WriteConst("READY PIC16F877A IO\r\n");
}

void APP_SystemTest_Task(void)
{
    u8 Byte = UART_ReadByte();

    if ((Byte == '\r') || (Byte == '\n'))
    {
        if (CmdIndex > 0)
        {
            CmdBuffer[CmdIndex] = '\0';
            HandleCommand(CmdBuffer);
            CmdIndex = 0;
        }
    }
    else if (CmdIndex < (CMD_BUFFER_SIZE - 1U))
    {
        CmdBuffer[CmdIndex] = (char)Byte;
        CmdIndex++;
    }
    else
    {
        CmdIndex = 0;
        UART_WriteConst("ERR CMD_TOO_LONG\r\n");
    }
}

static void UART_WriteConst(const char *TextPtr)
{
    while (*TextPtr != '\0')
    {
        UART_WriteByte((u8)*TextPtr);
        TextPtr++;
    }
}

static void UART_WriteU16(u16 Value)
{
    char Buffer[6];
    u8 Index = 0;

    if (Value == 0)
    {
        UART_WriteByte('0');
        return;
    }

    while (Value > 0)
    {
        Buffer[Index] = (char)('0' + (Value % 10U));
        Value /= 10U;
        Index++;
    }

    while (Index > 0)
    {
        Index--;
        UART_WriteByte((u8)Buffer[Index]);
    }
}

static void LCD_Send4Bits(u8 Nibble, u8 Control)
{
    u8 Data = (u8)((Nibble & 0xF0U) | LCD_BACKLIGHT | Control);
    I2C_MasterStart();
    I2C_MasterWriteByte((u8)(LCD_I2C_ADDR << 1));
    I2C_MasterWriteByte((u8)(Data | LCD_ENABLE));
    I2C_MasterStop();
    __delay_us(1);
    I2C_MasterStart();
    I2C_MasterWriteByte((u8)(LCD_I2C_ADDR << 1));
    I2C_MasterWriteByte((u8)(Data & (u8)~LCD_ENABLE));
    I2C_MasterStop();
    __delay_us(50);
}

static void LCD_SendCommand(u8 Command)
{
    LCD_Send4Bits((u8)(Command & 0xF0U), 0);
    LCD_Send4Bits((u8)(((u16)Command << 4) & 0xF0U), 0);
}

static void LCD_SendData(u8 Data)
{
    LCD_Send4Bits((u8)(Data & 0xF0U), LCD_RS);
    LCD_Send4Bits((u8)(((u16)Data << 4) & 0xF0U), LCD_RS);
}

static void LCD_Init(void)
{
    __delay_ms(50);
    LCD_Send4Bits(0x30, 0);
    __delay_ms(5);
    LCD_Send4Bits(0x30, 0);
    __delay_us(150);
    LCD_Send4Bits(0x30, 0);
    LCD_Send4Bits(0x20, 0);

    LCD_SendCommand(0x28);
    LCD_SendCommand(0x0C);
    LCD_SendCommand(0x06);
    LCD_Clear();
}

static void LCD_Clear(void)
{
    LCD_SendCommand(0x01);
    __delay_ms(2);
}

static void LCD_WriteLineConst(u8 Row, const char *TextPtr)
{
    u8 Count = 0;
    u8 Address = (Row == 0) ? 0x00 : 0x40;

    LCD_SendCommand((u8)(0x80U | Address));
    while ((*TextPtr != '\0') && (Count < LCD_LINE_SIZE))
    {
        LCD_SendData((u8)*TextPtr);
        TextPtr++;
        Count++;
    }

    while (Count < LCD_LINE_SIZE)
    {
        LCD_SendData(' ');
        Count++;
    }
}

static void LCD_WriteLineRam(u8 Row, char *TextPtr)
{
    u8 Count = 0;
    u8 Address = (Row == 0) ? 0x00 : 0x40;

    LCD_SendCommand((u8)(0x80U | Address));
    while ((*TextPtr != '\0') && (Count < LCD_LINE_SIZE))
    {
        LCD_SendData((u8)*TextPtr);
        TextPtr++;
        Count++;
    }

    while (Count < LCD_LINE_SIZE)
    {
        LCD_SendData(' ');
        Count++;
    }
}

static u8 DHT_ReadLevel(void)
{
    return ((PORTB & DHT_PIN_MASK) != 0U) ? GPIO_HIGH : GPIO_LOW;
}

static u16 DHT_ExpectPulse(u8 Level)
{
    u16 Count = 0;

    while (DHT_ReadLevel() == Level)
    {
        Count++;
        if (Count >= DHT_PULSE_TIMEOUT)
        {
            return DHT_TIMEOUT_VALUE;
        }
    }

    return Count;
}

static u8 DHT_Read(u8 *TempPtr, u8 *HumidityPtr)
{
    u8 Data[5] = {0, 0, 0, 0, 0};
    u8 ByteIndex;
    u8 BitIndex;
    u16 LowCycles;
    u16 HighCycles;

    DhtLastError = DHT_ERR_NONE;

    GPIO_SetPinDirection(DHT_PORT, DHT_PIN, GPIO_INPUT);
    __delay_ms(1);
    GPIO_SetPinDirection(DHT_PORT, DHT_PIN, GPIO_OUTPUT);
    GPIO_SetPinValue(DHT_PORT, DHT_PIN, GPIO_LOW);
    __delay_ms(20);
    GPIO_SetPinDirection(DHT_PORT, DHT_PIN, GPIO_INPUT);
    __delay_us(DHT_PULLUP_TIME_US);

    LowCycles = DHT_ExpectPulse(GPIO_LOW);
    if ((LowCycles == DHT_TIMEOUT_VALUE) || (LowCycles == 0U))
    {
        DhtLastError = DHT_ERR_RESPONSE_LOW;
        return 0;
    }
    HighCycles = DHT_ExpectPulse(GPIO_HIGH);
    if ((HighCycles == DHT_TIMEOUT_VALUE) || (HighCycles == 0U))
    {
        DhtLastError = DHT_ERR_RESPONSE_HIGH;
        return 0;
    }

    for (ByteIndex = 0; ByteIndex < 5; ByteIndex++)
    {
        for (BitIndex = 0; BitIndex < 8; BitIndex++)
        {
            LowCycles = DHT_ExpectPulse(GPIO_LOW);
            HighCycles = DHT_ExpectPulse(GPIO_HIGH);

            if ((LowCycles == DHT_TIMEOUT_VALUE) || (LowCycles == 0U))
            {
                DhtLastError = DHT_ERR_BIT_HIGH;
                return 0;
            }
            if ((HighCycles == DHT_TIMEOUT_VALUE) || (HighCycles == 0U))
            {
                DhtLastError = DHT_ERR_BIT_LOW;
                return 0;
            }

            Data[ByteIndex] <<= 1;
            if (HighCycles > LowCycles)
            {
                Data[ByteIndex] |= 1U;
            }
        }
    }

    if ((u8)(Data[0] + Data[1] + Data[2] + Data[3]) != Data[4])
    {
        DhtLastError = DHT_ERR_CHECKSUM;
        return 0;
    }

    *HumidityPtr = Data[0];
    *TempPtr = Data[2];
    return 1;
}

static u16 ReadAdcStable(u8 Channel)
{
    (void)ADC_ReadChannel(Channel);
    __delay_us(30);
    return ADC_ReadChannel(Channel);
}

static void ReadSensors(void)
{
    u8 Temp = Sensors.temp_c;
    u8 Humidity = Sensors.humidity;

    Sensors.mq2 = ReadAdcStable(MQ2_ADC_CHANNEL);
    Sensors.soil1 = 1023 - ReadAdcStable(SOIL_1_ADC_CHANNEL);
    Sensors.soil2 = ReadAdcStable(SOIL_2_ADC_CHANNEL);
    Sensors.ir1_active = (GPIO_GetPinValue(IR_1_PORT, IR_1_PIN) == IR_ACTIVE_LEVEL) ? 1U : 0U;
    Sensors.ir2_active = (GPIO_GetPinValue(IR_2_PORT, IR_2_PIN) == IR_ACTIVE_LEVEL) ? 1U : 0U;

    Sensors.dht_ok = DHT_Read(&Temp, &Humidity);
    if (Sensors.dht_ok != 0)
    {
        Sensors.temp_c = Temp;
        Sensors.humidity = Humidity;
    }
}

static void SendSensorFrame(void)
{
    UART_WriteConst("{\"mq2\":");
    UART_WriteU16(Sensors.mq2);
    UART_WriteConst(",\"soil1\":");
    UART_WriteU16(Sensors.soil1);
    UART_WriteConst(",\"soil2\":");
    UART_WriteU16(Sensors.soil2);
    UART_WriteConst(",\"temp_c\":");
    UART_WriteU16(Sensors.temp_c);
    UART_WriteConst(",\"humidity\":");
    UART_WriteU16(Sensors.humidity);
    UART_WriteConst(",\"dht_ok\":");
    UART_WriteU16(Sensors.dht_ok);
    UART_WriteConst(",\"dht_error\":");
    UART_WriteU16(DhtLastError);
    UART_WriteConst(",\"ir1\":");
    UART_WriteU16(Sensors.ir1_active);
    UART_WriteConst(",\"ir2\":");
    UART_WriteU16(Sensors.ir2_active);
    UART_WriteConst(",\"relays\":[");
    UART_WriteU16(Sensors.relay1_on);
    UART_WriteByte(',');
    UART_WriteU16(Sensors.relay2_on);
    UART_WriteByte(',');
    UART_WriteU16(Sensors.relay3_on);
    UART_WriteConst("]}\r\n");
}

static void SetRelay(u8 RelayNumber, u8 State)
{
    u8 PinValue = (State != 0) ? RELAY_ON : RELAY_OFF;

    switch (RelayNumber)
    {
        case 1:
            Sensors.relay1_on = (State != 0) ? 1U : 0U;
            GPIO_SetPinValue(RELAY_1_PORT, RELAY_1_PIN, PinValue);
            break;
        case 2:
            Sensors.relay2_on = (State != 0) ? 1U : 0U;
            GPIO_SetPinValue(RELAY_2_PORT, RELAY_2_PIN, PinValue);
            break;
        case 3:
            Sensors.relay3_on = (State != 0) ? 1U : 0U;
            GPIO_SetPinValue(RELAY_3_PORT, RELAY_3_PIN, PinValue);
            break;
        default:
            break;
    }
}

static void ServoWritePulse(u16 HighTimeUs)
{
    GPIO_SetPinValue(SERVO_PORT, SERVO_PIN, GPIO_HIGH);

    while (HighTimeUs >= 100U)
    {
        __delay_us(100);
        HighTimeUs -= 100U;
    }
    while (HighTimeUs >= 10U)
    {
        __delay_us(10);
        HighTimeUs -= 10U;
    }

    GPIO_SetPinValue(SERVO_PORT, SERVO_PIN, GPIO_LOW);
    __delay_ms(18);
}

static void ServoMove(u16 HighTimeUs)
{
    u8 Count;
    for (Count = 0; Count < SERVO_PULSE_COUNT; Count++)
    {
        ServoWritePulse(HighTimeUs);
    }
}

static void ServoSweep(u16 StartUs, u16 EndUs)
{
    u16 PulseUs;
    u8 Count;

    if (StartUs <= EndUs)
    {
        for (PulseUs = StartUs; PulseUs <= EndUs; PulseUs += SERVO_SWEEP_STEP_US)
        {
            for (Count = 0; Count < SERVO_SWEEP_PULSES; Count++)
            {
                ServoWritePulse(PulseUs);
            }
        }
    }
    else
    {
        PulseUs = StartUs;
        while (PulseUs >= EndUs)
        {
            for (Count = 0; Count < SERVO_SWEEP_PULSES; Count++)
            {
                ServoWritePulse(PulseUs);
            }

            if (PulseUs < (EndUs + SERVO_SWEEP_STEP_US))
            {
                break;
            }
            PulseUs -= SERVO_SWEEP_STEP_US;
        }
    }
}

static u8 StringEquals(const char *LeftPtr, const char *RightPtr)
{
    while ((*LeftPtr != '\0') && (*RightPtr != '\0'))
    {
        if (*LeftPtr != *RightPtr)
        {
            return 0;
        }

        LeftPtr++;
        RightPtr++;
    }

    return (*LeftPtr == '\0') && (*RightPtr == '\0');
}

static u8 StringStartsWith(const char *TextPtr, const char *PrefixPtr)
{
    while (*PrefixPtr != '\0')
    {
        if (*TextPtr != *PrefixPtr)
        {
            return 0;
        }

        TextPtr++;
        PrefixPtr++;
    }

    return 1;
}

static u16 ParseU16(const char *TextPtr)
{
    u16 Value = 0;

    while ((*TextPtr >= '0') && (*TextPtr <= '9'))
    {
        Value = (u16)((Value * 10U) + (u16)(*TextPtr - '0'));
        TextPtr++;
    }

    return Value;
}

static void HandleCommand(char *CommandPtr)
{
    if (StringEquals(CommandPtr, "GET") != 0)
    {
        ReadSensors();
        SendSensorFrame();
    }
    else if (StringEquals(CommandPtr, "ID") != 0)
    {
        UART_WriteConst("PIC16F877A_IO_V6\r\n");
    }
    else if (StringEquals(CommandPtr, "R1=0") != 0)
    {
        SetRelay(1, 0);
        UART_WriteConst("OK R1=0\r\n");
    }
    else if (StringEquals(CommandPtr, "R1=1") != 0)
    {
        SetRelay(1, 1);
        UART_WriteConst("OK R1=1\r\n");
    }
    else if (StringEquals(CommandPtr, "R2=0") != 0)
    {
        SetRelay(2, 0);
        UART_WriteConst("OK R2=0\r\n");
    }
    else if (StringEquals(CommandPtr, "R2=1") != 0)
    {
        SetRelay(2, 1);
        UART_WriteConst("OK R2=1\r\n");
    }
    else if (StringEquals(CommandPtr, "R3=0") != 0)
    {
        SetRelay(3, 0);
        UART_WriteConst("OK R3=0\r\n");
    }
    else if (StringEquals(CommandPtr, "R3=1") != 0)
    {
        SetRelay(3, 1);
        UART_WriteConst("OK R3=1\r\n");
    }
    else if (StringEquals(CommandPtr, "RALL=0") != 0)
    {
        SetRelay(1, 0);
        SetRelay(2, 0);
        SetRelay(3, 0);
        UART_WriteConst("OK RALL=0\r\n");
    }
    else if (StringEquals(CommandPtr, "RALL=1") != 0)
    {
        SetRelay(1, 1);
        SetRelay(2, 1);
        SetRelay(3, 1);
        UART_WriteConst("OK RALL=1\r\n");
    }
    else if (StringEquals(CommandPtr, "LCDCLR") != 0)
    {
        LCD_Clear();
        UART_WriteConst("OK LCDCLR\r\n");
    }
    else if ((StringEquals(CommandPtr, "DOOR=OPEN") != 0) || (StringEquals(CommandPtr, "SERVO=OPEN") != 0))
    {
        UART_WriteConst("OK DOOR=OPEN\r\n");
        ServoSweep(SERVO_CLOSE_US, SERVO_OPEN_US);
    }
    else if ((StringEquals(CommandPtr, "DOOR=CLOSE") != 0) || (StringEquals(CommandPtr, "SERVO=CLOSE") != 0))
    {
        ServoMove(SERVO_CLOSE_US);
        UART_WriteConst("OK DOOR=CLOSE\r\n");
    }
    else if (StringStartsWith(CommandPtr, "SERVO=") != 0)
    {
        u16 PulseUs = ParseU16(&CommandPtr[6]);
        if ((PulseUs >= SERVO_MIN_US) && (PulseUs <= SERVO_MAX_US))
        {
            ServoMove(PulseUs);
            UART_WriteConst("OK SERVO=");
            UART_WriteU16(PulseUs);
            UART_WriteConst("\r\n");
        }
        else
        {
            UART_WriteConst("ERR SERVO_RANGE\r\n");
        }
    }
    else if (StringEquals(CommandPtr, "ACCESS=GRANTED") != 0)
    {
        LCD_WriteLineConst(0, "ACCESS GRANTED");
        LCD_WriteLineConst(1, "DOOR OPEN");
        UART_WriteConst("OK ACCESS=GRANTED\r\n");
        ServoSweep(SERVO_CLOSE_US, SERVO_OPEN_US);
    }
    else if (StringEquals(CommandPtr, "ACCESS=DENIED") != 0)
    {
        LCD_WriteLineConst(0, "ACCESS DENIED");
        LCD_WriteLineConst(1, "TRY AGAIN");
        UART_WriteConst("OK ACCESS=DENIED\r\n");
    }
    else if (StringStartsWith(CommandPtr, "LCD1=") != 0)
    {
        LCD_WriteLineRam(0, &CommandPtr[5]);
        UART_WriteConst("OK LCD1\r\n");
    }
    else if (StringStartsWith(CommandPtr, "LCD2=") != 0)
    {
        LCD_WriteLineRam(1, &CommandPtr[5]);
        UART_WriteConst("OK LCD2\r\n");
    }
    else if (StringEquals(CommandPtr, "PING") != 0)
    {
        UART_WriteConst("PONG\r\n");
    }
    else
    {
        UART_WriteConst("ERR UNKNOWN_CMD\r\n");
    }
}
