#pragma once
#include <Arduino.h>

class MassStorage {
public:
    static bool setup();   // enter MSC mode (host sees drive) - call only from MSC boot path
    static bool writeFile(const char* path, const String& content, bool append = false);
    static bool readFile(const char* path, String& out);
    static bool deleteFile(const char* path);
    static bool listFiles(String& out);              // newline-separated list, out = "name\tsize\n..."
    static bool getSpace(uint64_t& totalBytes, uint64_t& usedBytes, uint64_t& freeBytes);
    static void setMediaPresent(bool present);

};