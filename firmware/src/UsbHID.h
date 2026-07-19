#pragma once
#include <Arduino.h>

#if CONFIG_IDF_TARGET_ESP32S2 || CONFIG_IDF_TARGET_ESP32S3

#include <USBHIDKeyboard.h>

#ifdef String
#undef String
#endif

extern USBHIDKeyboard Keyboard;

class UsbHID {
public:
    static bool armScript(const String& filename, bool mscMode);
    static bool runIfArmed();

private:
    static void runScript(const String& scriptContent);
};

#endif // CONFIG_IDF_TARGET_ESP32S2 || CONFIG_IDF_TARGET_ESP32S3