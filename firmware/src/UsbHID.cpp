#include "UsbHID.h"

#if CONFIG_IDF_TARGET_ESP32S2 || CONFIG_IDF_TARGET_ESP32S3


#include "mass_storage.h"
#include <Preferences.h>
#include <USB.h>
#include "USBHIDKeyboard.h"
#include <Arduino.h>

#if defined(CONFIG_IDF_TARGET_ESP32S2)
    #define LED_PIN 17
#endif
USBHIDKeyboard Keyboard;   // definition, no "static" — must be visible to main.cpp too

bool UsbHID::armScript(const String& filename, bool mscMode) {
    Preferences prefs;
    prefs.begin("boot", false);
    bool ok = prefs.putString("ducky_file", filename) > 0;
    if (ok) prefs.putBool("ducky_mode", true);
    prefs.putBool("duck_mscMode", mscMode);
    prefs.end();
    
    return ok;
}

bool UsbHID::runIfArmed() {
    Preferences prefs;
    prefs.begin("boot", false);

    bool armed = prefs.getBool("ducky_mode", false);
    String filename = prefs.getString("ducky_file", "");

    bool duckmscMode = prefs.getBool("duck_mscMode", false);
    if (duckmscMode) prefs.putBool("duck_mscMode", false);


    prefs.putBool("ducky_mode", false);
    prefs.remove("ducky_file");
    prefs.end();

    if (!armed || filename.length() == 0) return false;

    String script;
    if (!MassStorage::readFile(filename.c_str(), script)) {
        Serial.printf("Failed to read ducky file: %s\n", filename.c_str());
        return false;
    }

    if (duckmscMode) {
        MassStorage::setup();
    }

    Serial.printf("Executing armed ducky script: %s (%d bytes)\n", filename.c_str(), script.length());
    runScript(script);
    return true;
}

uint8_t keyCodeFor(String name) {
    String upper = name;
    upper.toUpperCase();

    if (upper == "CTRL" || upper == "CONTROL") return KEY_LEFT_CTRL;
    if (upper == "SHIFT")                      return KEY_LEFT_SHIFT;
    if (upper == "ALT")                        return KEY_LEFT_ALT;
    if (upper == "GUI" || upper == "WINDOWS" || upper == "SUPER") return KEY_LEFT_GUI;
    if (upper == "TAB")                        return KEY_TAB;
    if (upper == "ENTER" || upper == "RETURN") return KEY_RETURN;
    if (upper == "ESC" || upper == "ESCAPE")   return KEY_ESC;
    if (upper == "BACKSPACE")                  return KEY_BACKSPACE;
    if (upper == "SPACE")                      return ' ';
    if (upper == "UP")                         return KEY_UP_ARROW;
    if (upper == "DOWN")                       return KEY_DOWN_ARROW;
    if (upper == "LEFT")                       return KEY_LEFT_ARROW;
    if (upper == "RIGHT")                      return KEY_RIGHT_ARROW;
    if (upper == "HOME")                       return KEY_HOME;
    if (upper == "END")                        return KEY_END;
    if (upper == "PAGEUP")                     return KEY_PAGE_UP;
    if (upper == "PAGEDOWN")                   return KEY_PAGE_DOWN;
    if (upper == "DELETE" || upper == "DEL")   return KEY_DELETE;

    if (upper.length() == 2 && upper[0] == 'F') {
        int n = upper.substring(1).toInt();
        switch (n) {
            case 1: return KEY_F1;
            case 2: return KEY_F2;
            case 3: return KEY_F3;
            case 4: return KEY_F4;
            case 5: return KEY_F5;
            case 6: return KEY_F6;
            case 7: return KEY_F7;
            case 8: return KEY_F8;
            case 9: return KEY_F9;
        }
    }
    if (upper.length() == 3 && upper[0] == 'F') {
        if (upper.substring(1) == "10") return KEY_F10;
        if (upper.substring(1) == "11") return KEY_F11;
        if (upper.substring(1) == "12") return KEY_F12;
    }

    if (name.length() == 1) return (uint8_t)name[0]; // use ORIGINAL case here, not `upper`

    return 0;
}

// Track currently-held keys for HOLD / RELEASE
#define MAX_HELD 8
uint8_t heldKeys[MAX_HELD];
int heldCount = 0;

void holdKey(uint8_t k) {
    if (heldCount < MAX_HELD) heldKeys[heldCount++] = k;
    Keyboard.press(k);
}

void releaseKey(uint8_t k) {
    Keyboard.release(k);
    for (int i = 0; i < heldCount; i++) {
        if (heldKeys[i] == k) {
            heldKeys[i] = heldKeys[--heldCount];
            break;
        }
    }
}

void releaseAllTracked() {
    Keyboard.releaseAll();
    heldCount = 0;
}

// ------------------------------------------------------------------

void UsbHID::runScript(const String& script) {
    // Keyboard.begin() should already have been called in setup()

    int start = 0;
    while (start < script.length()) {
        int nl = script.indexOf('\n', start);
        String line = (nl == -1) ? script.substring(start) : script.substring(start, nl);
        line.trim();
        start = (nl == -1) ? script.length() : nl + 1;

        if (line.length() == 0 || line.startsWith("REM") || line.startsWith("//")) continue;

        int spaceIndex = line.indexOf(' ');
        String cmd = (spaceIndex > 0) ? line.substring(0, spaceIndex) : line;
        String arg = (spaceIndex > 0) ? line.substring(spaceIndex + 1) : "";

        cmd.toUpperCase();

        // ==================== BASIC COMMANDS ====================
        if (cmd == "DELAY") {
            delay(arg.toInt());
        }
        else if (cmd == "STRING") {
            Keyboard.print(arg);
        }
        else if (cmd == "STRINGLN") {
            Keyboard.println(arg);
        }

        // Generic single key press (replaces all old individual handlers)
        else if (cmd == "ENTER" || cmd == "RETURN" ||
                 cmd == "GUI" || cmd == "WINDOWS" || cmd == "SUPER" ||
                 cmd == "ALT" || cmd == "CTRL" || cmd == "CONTROL" ||
                 cmd == "SHIFT" || cmd == "TAB" || cmd == "ESC" || cmd == "ESCAPE" ||
                 cmd == "BACKSPACE" || cmd == "SPACE" ||
                 cmd == "UP" || cmd == "DOWN" || cmd == "LEFT" || cmd == "RIGHT" ||
                 cmd == "HOME" || cmd == "END" || cmd == "PAGEUP" || cmd == "PAGEDOWN" ||
                 cmd == "DELETE" || cmd == "DEL" || cmd.startsWith("F")) {

            uint8_t k = keyCodeFor(cmd);
            if (k) {
                Keyboard.press(k);
                // Support combined keys like: GUI R, CTRL C, ALT TAB, etc.
                if (arg.length() > 0) {
                    uint8_t extra = keyCodeFor(arg);
                    if (extra) Keyboard.press(extra);
                }
                Keyboard.releaseAll();
            }
        }

        // ==================== ADVANCED COMMANDS ====================
        else if (cmd == "HOLD") {
            // HOLD <KEY> [seconds]  e.g. HOLD TAB 2
            int sp = arg.indexOf(' ');
            String keyName = (sp == -1) ? arg : arg.substring(0, sp);
            float secs = (sp == -1) ? 0 : arg.substring(sp + 1).toFloat();
            uint8_t k = keyCodeFor(keyName);
            if (k) {
                holdKey(k);
                if (secs > 0) {
                    delay((int)(secs * 1000));
                    releaseKey(k);
                }
            }
        }
        else if (cmd.startsWith("HOLD_")) {
            // HOLD_TAB, HOLD_SHIFT, etc.
            String keyName = cmd.substring(5);
            uint8_t k = keyCodeFor(keyName);
            if (k) holdKey(k);
        }
        else if (cmd == "RELEASE") {
            uint8_t k = keyCodeFor(arg);
            if (k) releaseKey(k);
        }
        else if (cmd.startsWith("RELEASE_")) {
            String keyName = cmd.substring(8);
            uint8_t k = keyCodeFor(keyName);
            if (k) releaseKey(k);
        }
        else if (cmd == "RELEASEALL") {
            releaseAllTracked();
        }
        else if (cmd == "COMBO" || cmd == "KEYS") {
            // COMBO CTRL ALT DELETE
            int s = 0;
            while (s < arg.length()) {
                int sp2 = arg.indexOf(' ', s);
                String part = (sp2 == -1) ? arg.substring(s) : arg.substring(s, sp2);
                uint8_t k = keyCodeFor(part);
                if (k) Keyboard.press(k);
                s = (sp2 == -1) ? arg.length() : sp2 + 1;
            }
            delay(50);
            Keyboard.releaseAll();
        }

        // ==================== DEVICE COMMANDS ====================
        else if (cmd == "DEVICE_REBOOT") {
            ESP.restart();
        }
        else if (cmd == "DEVICE_MSC_STOP") {
            MassStorage::setMediaPresent(false);
        }
        else if (cmd == "DEVICE_MSC_START") {
            MassStorage::setup();
        }
        else {
            Serial.printf("Unknown command: %s\n", cmd.c_str());
        }

        delay(40);
    }

    Serial.println("Ducky script finished.");

#if defined(CONFIG_IDF_TARGET_ESP32S2)
    pinMode(LED_PIN, OUTPUT);
    for (int i = 0; i < 5; i++) {
        digitalWrite(LED_PIN, HIGH);
        delay(150);
        digitalWrite(LED_PIN, LOW);
        delay(150);
    }
#endif

    delay(200);
}

#endif // CONFIG_IDF_TARGET_ESP32S2 || CONFIG_IDF_TARGET_ESP32S3
