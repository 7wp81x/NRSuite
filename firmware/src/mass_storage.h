#pragma once
#include <Arduino.h>

class MassStorage {
public:
    // File operations — work on any chip, only need FFat, no USB hardware required
    static bool writeFile(const char* path, const String& content, bool append = false);
    static bool readFile(const char* path, String& out);
    static bool deleteFile(const char* path);
    static bool listFiles(String& out);              // newline-separated list, out = "name\tsize\n..."
    static bool getSpace(uint64_t& totalBytes, uint64_t& usedBytes, uint64_t& freeBytes);

#if CONFIG_IDF_TARGET_ESP32S2 || CONFIG_IDF_TARGET_ESP32S3
    // USB MSC mode — requires native USB-OTG hardware, unavailable on C3/plain ESP32/C6
    static bool setup();   // enter MSC mode (host sees drive) - call only from MSC boot path
    static void setMediaPresent(bool present);
#endif
};