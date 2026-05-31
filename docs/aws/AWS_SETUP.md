# AWS Setup Notes

## Resources

- AWS IoT Core Thing/certificate for Raspberry Pi MQTT
- IoT Policy permitting connect/publish/subscribe/receive/retained publish on `smarthome/*`
- DynamoDB table `SmartHomeEvents`
- Lambda `SmartHomeTelemetryWriter`
- IoT Rule `SmartHomeToHistory`
- SNS topic `SmartHomeAlerts`

## Certificate Steps

1. AWS Console -> IoT Core -> Manage -> Things -> Create Thing.
2. Create and activate a certificate.
3. Download root CA, certificate, and private key.
4. Attach a policy allowing the `smarthome/*` MQTT topics.
5. Place cert files in `code/raspberry_pi/certs/` on the Pi.

## Mobile App Security

Do not ship private keys in production APKs. The placeholder assets are only for a classroom demo build. Production should use Cognito/custom authorizer/backend-issued credentials.
