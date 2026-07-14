#pragma once
#include <Arduino.h>
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