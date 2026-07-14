#include "FileUpload.h"
#include "mass_storage.h"

namespace {
    uint8_t* _buf     = nullptr;
    size_t   _len     = 0;
    size_t   _cap     = 0;
    char     _path[64] = {0};
    bool     _active  = false;
}

bool FileUpload::isAllowedExtension(const char* filename) {
    size_t len = strlen(filename);
    const char* exts[] = { ".txt", ".conf" };
    for (const char* ext : exts) {
        size_t elen = strlen(ext);
        if (len >= elen && strcasecmp(filename + len - elen, ext) == 0) {
            return true;
        }
    }
    return false;
}

void FileUpload::reset() {
    if (_buf) free(_buf);
    _buf = nullptr;
    _len = 0;
    _cap = 0;
    _path[0] = '\0';
    _active = false;
}

bool FileUpload::addChunk(const char* filename, const uint8_t* data, size_t len, bool isLast) {
    // First chunk of a new upload — validate + latch the filename.
    if (!_active) {
        if (!isAllowedExtension(filename)) {
            return false;  // reject anything not .txt/.conf
        }
        // Ensure leading slash, since FFat paths need it.
        if (filename[0] == '/') {
            strncpy(_path, filename, sizeof(_path) - 1);
        } else {
            snprintf(_path, sizeof(_path), "/%s", filename);
        }
        _active = true;
    }

    if (data && len > 0) {
        if (_len + len > _cap) {
            size_t newCap = _len + len + 512;
            uint8_t* grown = (uint8_t*)realloc(_buf, newCap);
            if (!grown) {
                reset();
                return false;  // OOM
            }
            _buf = grown;
            _cap = newCap;
        }
        memcpy(_buf + _len, data, len);
        _len += len;
    }

    if (isLast) {
        String content;
        content.reserve(_len);
        for (size_t i = 0; i < _len; i++) content += (char)_buf[i];

        bool ok = MassStorage::writeFile(_path, content);
        reset();  // clear accumulator regardless of outcome, ready for next upload
        return ok;
    }

    return true;  // chunk accepted, upload still in progress
}