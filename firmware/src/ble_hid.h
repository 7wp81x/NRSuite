#pragma once
#include <Arduino.h>

#ifdef ENABLE_BLE_HID

// ====================== BLE HID Module ======================
// Ported from DuckESP. Scope intentionally reduced:
//   - No BLE scanning
//   - No device-name cloning
//   - No onboard WebServer/UI — driven entirely by NRSuite's
//     existing framed bridge protocol (CMD/RESP/EVENT) over USB CDC


namespace BleHid {

// Lifecycle
void begin(const String& deviceName);
void end();
bool isConnected();
String peerAddress();
int runScript(const String& payload);
void stop();
bool isAdvertising();
void keyDown(const String& keyName);
void keyUp(const String& keyName);
void releaseAll();
uint8_t resolveKey(String keyName);

} // namespace BleHid

#endif // ENABLE_BLE_HID