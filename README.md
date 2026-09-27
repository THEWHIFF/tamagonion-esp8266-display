# tamagonion-esp8266-display

ESP8266 / ESP-12F display client for Tamagonion.

Target hardware:
- ESP8266 ESP-12F
- 1.54" 240x240 LCD
- ST7789V
- Wi-Fi
- ESPHome

Planned features:
- 48x20 terminal rendering
- UTF-8 / Tamagonion glyph support
- TCP frame transport
- pairing + authenticated sessions
- OTA updates
- Wi-Fi recovery AP

Tamagonion remains responsible for generating the complete rendered frame.
The ESP8266 acts as a network display endpoint.

Copy `secrets.example.yaml` to `secrets.yaml` and configure local secrets before compiling.
