#pragma once
#include <Arduino.h>

class FileUpload {
public:
    // Call on each chunk. filename only needs to be passed once (first chunk) -
    // path is cached until isLast completes the write.
    static bool addChunk(const char* filename, const uint8_t* data, size_t len, bool isLast);
    static void reset();

private:
    static bool isAllowedExtension(const char* filename);
};