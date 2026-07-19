#include "ble_hid.h"

#ifdef ENABLE_BLE_HID

#include <HijelHID_BLEKeyboard.h>
#include <NimBLEDevice.h>

namespace BleHid {

static HijelHID_BLEKeyboard* keyboard = nullptr;
static volatile bool advertising = false;
static volatile bool connected   = false;
static String peerAddr = "";

void begin(const String& deviceName) {
    if (keyboard) {
        if (keyboard->isPaired()) {
            return;
        }
        if (!advertising) {
            keyboard->begin();
            advertising = true;
        }
        return;
    }
    keyboard = new HijelHID_BLEKeyboard(deviceName.c_str(), "NRSuite", 100);
    keyboard->begin();
    advertising = true;
}

void end() {
    if (!keyboard) return;
    keyboard->releaseAll();
    NimBLEDevice::stopAdvertising();
    advertising = false;
    delete keyboard;
    keyboard = nullptr;
}

bool isAdvertising() {
    return keyboard && advertising;
}

bool isConnected() {
    return keyboard && keyboard->isPaired();
}

String peerAddress() {
    if (!isConnected()) return "";
    auto pServer = NimBLEDevice::getServer();
    if (pServer->getConnectedCount() == 0) return "";
    NimBLEConnInfo peerInfo = pServer->getPeerInfo(0);
    return String(peerInfo.getAddress().toString().c_str());
}

// ====================== Keymap ======================
uint8_t resolveKey(String keyName) {
    keyName.toUpperCase();
    keyName.trim();
    if (keyName.length() == 0) return 0;

    // Modifiers
    if (keyName == "CTRL" || keyName == "CONTROL" || keyName == "LCTRL") return KEY_LCTRL;
    if (keyName == "RCTRL") return KEY_RCTRL;
    if (keyName == "ALT" || keyName == "LALT") return KEY_LALT;
    if (keyName == "RALT") return KEY_RALT;
    if (keyName == "SHIFT" || keyName == "LSHIFT") return KEY_LSHIFT;
    if (keyName == "RSHIFT") return KEY_RSHIFT;
    if (keyName == "GUI" || keyName == "WINDOWS" || keyName == "COMMAND" || keyName == "LGUI") return KEY_LGUI;
    if (keyName == "RGUI") return KEY_RGUI;

    // Common action keys
    if (keyName == "ENTER" || keyName == "RETURN") return KEY_RETURN;
    if (keyName == "TAB") return KEY_TAB;
    if (keyName == "ESC" || keyName == "ESCAPE") return KEY_ESCAPE;
    if (keyName == "BACKSPACE" || keyName == "BACK") return KEY_BACKSPACE;
    if (keyName == "DELETE" || keyName == "DEL") return KEY_DELETE;
    if (keyName == "SPACE") return KEY_SPACE;

    // Navigation & arrows
    if (keyName == "UP") return KEY_UP;
    if (keyName == "DOWN") return KEY_DOWN;
    if (keyName == "LEFT") return KEY_LEFT;
    if (keyName == "RIGHT") return KEY_RIGHT;
    if (keyName == "HOME") return KEY_HOME;
    if (keyName == "END") return KEY_END;
    if (keyName == "INSERT") return KEY_INSERT;
    if (keyName == "PAGEUP" || keyName == "PGUP") return KEY_PAGE_UP;
    if (keyName == "PAGEDOWN" || keyName == "PGDN") return KEY_PAGE_DOWN;
    if (keyName == "PRINTSCREEN" || keyName == "PRTSC") return KEY_PRINT_SCREEN;


    if (keyName.startsWith("F") && keyName.length() <= 3) {
        int num = keyName.substring(1).toInt();
        if (num >= 1 && num <= 12) return KEY_F1 + (num - 1);
    }


    if (keyName.length() == 1) {
        char c = keyName[0];
        if (c >= 'A' && c <= 'Z') return KEY_A + (c - 'A');
        if (c == '0') return KEY_0;
        if (c >= '1' && c <= '9') return KEY_1 + (c - '1');
    }

    return 0;
}

// ====================== Script mode ======================
int runScript(const String& payload) {
    if (!isConnected()) return 0;

    int lineCount = 0;
    int lineStart = 0;

    while (lineStart < payload.length()) {
        int lineEnd = payload.indexOf('\n', lineStart);
        String line = (lineEnd == -1) ? payload.substring(lineStart) : payload.substring(lineStart, lineEnd);
        line.trim();

        if (line.length() == 0 || line.startsWith("REM")) {
            lineStart = (lineEnd == -1) ? payload.length() : lineEnd + 1;
            continue;
        }

        int spaceIdx = line.indexOf(' ');
        String cmd  = (spaceIdx == -1) ? line : line.substring(0, spaceIdx);
        String args = (spaceIdx == -1) ? "" : line.substring(spaceIdx + 1);

        if (cmd == "STRING") {
            keyboard->print(args);
        } else if (cmd == "STRINGLN") {
            keyboard->println(args);
        } else if (cmd == "DELAY") {
            delay(args.toInt());
        } else {
            // Key combo support (GUI r, etc.)
            int pos = 0;
            bool pressedAny = false;
            while (pos < line.length()) {
                int nextSpace = line.indexOf(' ', pos);
                String token = (nextSpace == -1) ? line.substring(pos) : line.substring(pos, nextSpace);
                token.trim();
                pos = (nextSpace == -1) ? line.length() : nextSpace + 1;
                if (token.length() == 0) continue;

                uint8_t key = resolveKey(token);
                if (key != 0) {
                    keyboard->press(key);
                    pressedAny = true;
                    delay(8);
                }
            }
            if (pressedAny) {
                delay(50);
                keyboard->releaseAll();
            }
        }

        lineCount++;
        delay(40);
        lineStart = (lineEnd == -1) ? payload.length() : lineEnd + 1;
    }

    keyboard->releaseAll();
    return lineCount;
}

void stop() {
    if (keyboard) keyboard->releaseAll();
}

// ====================== Realtime mode ======================
void keyDown(const String& keyName) {
    if (!isConnected()) return;
    uint8_t key = resolveKey(keyName);
    if (key != 0) keyboard->press(key);
}

void keyUp(const String& keyName) {
    if (!isConnected()) return;
    uint8_t key = resolveKey(keyName);
    if (key != 0) keyboard->release(key);
}

void releaseAll() {
    if (keyboard) keyboard->releaseAll();
}

} // namespace BleHid

#endif // ENABLE_BLE_HID