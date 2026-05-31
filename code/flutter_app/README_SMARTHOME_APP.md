# Smart Home Flutter App

The app controls relays/door through MQTT, requests `smarthome/camera/backend`, opens the Pi LAN stream in WebView, and calls `/enroll` and `/faces`.

Build:

```bash
flutter pub get
flutter build apk --debug
```

MQTT modes:

- AWS mode: replace placeholder cert files in `assets/certs/`.
- Local mode: enable a LAN Mosquitto listener on the Pi and set MQTT mode to Local in the app settings.
