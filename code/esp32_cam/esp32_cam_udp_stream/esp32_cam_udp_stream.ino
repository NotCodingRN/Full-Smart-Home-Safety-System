#include "esp_camera.h"
#include <WiFi.h>
#include <WiFiUdp.h>
#include <WebServer.h>

// ================= WIFI =================
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";

// ================= UDP DISCOVERY =================
WiFiUDP udp;
const unsigned int DISCOVERY_PORT = 4210;
unsigned long lastAnnounce = 0;

// ================= CAMERA PINS =================
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     15
#define SIOD_GPIO_NUM     4
#define SIOC_GPIO_NUM     5
#define Y2_GPIO_NUM       11
#define Y3_GPIO_NUM       9
#define Y4_GPIO_NUM       8
#define Y5_GPIO_NUM       10
#define Y6_GPIO_NUM       12
#define Y7_GPIO_NUM       18
#define Y8_GPIO_NUM       17
#define Y9_GPIO_NUM       16
#define VSYNC_GPIO_NUM    6
#define HREF_GPIO_NUM     7
#define PCLK_GPIO_NUM     13

WebServer server(80);

void handleStream();

void announcePresence()
{
    IPAddress ip = WiFi.localIP();

    char msg[80];
    snprintf(msg, sizeof(msg), "ESP32CAM_HERE,%u.%u.%u.%u,80",
             ip[0], ip[1], ip[2], ip[3]);

    udp.beginPacket(IPAddress(255, 255, 255, 255), DISCOVERY_PORT);
    udp.write((const uint8_t*)msg, strlen(msg));
    udp.endPacket();

    Serial.print("UDP announce: ");
    Serial.println(msg);
}

void startCamera()
{
    camera_config_t config;

    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;

    config.pin_d0 = Y2_GPIO_NUM;
    config.pin_d1 = Y3_GPIO_NUM;
    config.pin_d2 = Y4_GPIO_NUM;
    config.pin_d3 = Y5_GPIO_NUM;
    config.pin_d4 = Y6_GPIO_NUM;
    config.pin_d5 = Y7_GPIO_NUM;
    config.pin_d6 = Y8_GPIO_NUM;
    config.pin_d7 = Y9_GPIO_NUM;

    config.pin_xclk = XCLK_GPIO_NUM;
    config.pin_pclk = PCLK_GPIO_NUM;
    config.pin_vsync = VSYNC_GPIO_NUM;
    config.pin_href = HREF_GPIO_NUM;

    config.pin_sccb_sda = SIOD_GPIO_NUM;
    config.pin_sccb_scl = SIOC_GPIO_NUM;

    config.pin_pwdn = PWDN_GPIO_NUM;
    config.pin_reset = RESET_GPIO_NUM;

    config.xclk_freq_hz = 18000000;
    config.pixel_format = PIXFORMAT_JPEG;

    if (psramFound())
    {
        config.frame_size = FRAMESIZE_VGA;
        config.jpeg_quality = 20;
        config.fb_count = 2;
        config.fb_location = CAMERA_FB_IN_PSRAM;
        config.grab_mode = CAMERA_GRAB_LATEST;
    }
    else
    {
        config.frame_size = FRAMESIZE_VGA;
        config.jpeg_quality = 20;
        config.fb_count = 1;
        config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    }

    esp_err_t err = esp_camera_init(&config);

    if (err != ESP_OK)
    {
        Serial.printf("Camera init failed: 0x%x\n", err);
        while (true) {}
    }

    sensor_t *s = esp_camera_sensor_get();
    s->set_vflip(s, 1);
    s->set_framesize(s, FRAMESIZE_VGA);
    s->set_quality(s, 20);
    s->set_brightness(s, 0);
    s->set_contrast(s, 0);
    s->set_saturation(s, 0);
    s->set_sharpness(s, 0);
    s->set_whitebal(s, 1);
    s->set_awb_gain(s, 1);
    s->set_gain_ctrl(s, 1);
    s->set_exposure_ctrl(s, 1);
    s->set_denoise(s, 1);
    s->set_aec2(s, 1);

    Serial.println("Camera initialized");
}

void handleStream()
{
    WiFiClient client = server.client();

    client.println("HTTP/1.1 200 OK");
    client.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
    client.println("Access-Control-Allow-Origin: *");
    client.println();

    while (client.connected())
    {
        camera_fb_t *fb = esp_camera_fb_get();

        if (!fb)
        {
            delay(10);
            continue;
        }

        client.printf("--frame\r\n");
        client.printf("Content-Type: image/jpeg\r\n");
        client.printf("Content-Length: %u\r\n\r\n", fb->len);

        client.write(fb->buf, fb->len);
        client.printf("\r\n");

        esp_camera_fb_return(fb);

        if (!client.connected())
            break;

        delay(30);
    }
}

void setup()
{
    Serial.begin(115200);

    Serial.println();
    Serial.println("BOOTING...");

    startCamera();

    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);
    WiFi.begin(ssid, password);

    Serial.print("Connecting to WiFi");

    while (WiFi.status() != WL_CONNECTED)
    {
        Serial.print(".");
        delay(300);
    }

    Serial.println();
    Serial.println("WiFi connected");
    Serial.print("ESP32 IP: ");
    Serial.println(WiFi.localIP());
    Serial.print("STREAM URL: http://");
    Serial.print(WiFi.localIP());
    Serial.println("/stream");

    udp.begin(DISCOVERY_PORT);
    Serial.println("UDP discovery started");
    announcePresence();

    server.on("/stream", HTTP_GET, handleStream);
    server.begin();

    Serial.println("HTTP server started");
}

void loop()
{
    server.handleClient();

    if (WiFi.status() == WL_CONNECTED && (millis() - lastAnnounce > 3000))
    {
        lastAnnounce = millis();
        announcePresence();
    }
}
