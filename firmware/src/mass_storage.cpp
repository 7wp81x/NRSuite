#include "mass_storage.h"
#include "FFat.h"
#include "esp_partition.h"
#include "wear_levelling.h"

#if CONFIG_IDF_TARGET_ESP32S2 || CONFIG_IDF_TARGET_ESP32S3
#include <USB.h>
#include "USBMSC.h"
#endif

namespace {
    #if CONFIG_IDF_TARGET_ESP32S2 || CONFIG_IDF_TARGET_ESP32S3
        USBMSC msc;
    #endif
    wl_handle_t wl_handle = WL_INVALID_HANDLE;

    int32_t onWrite(uint32_t lba, uint32_t offset, uint8_t* buffer, uint32_t bufsize) {
        size_t sector_size = wl_sector_size(wl_handle);
        return (wl_write(wl_handle, (lba * sector_size) + offset, buffer, bufsize) == ESP_OK)
                ? bufsize : -1;
    }
    int32_t onRead(uint32_t lba, uint32_t offset, void* buffer, uint32_t bufsize) {
        size_t sector_size = wl_sector_size(wl_handle);
        return (wl_read(wl_handle, (lba * sector_size) + offset, buffer, bufsize) == ESP_OK)
                ? bufsize : -1;
    }
    bool onStartStop(uint8_t, bool, bool) { return true; }

    // Shared FAT label - must match the partition CSV entry name.
    constexpr const char* FAT_LABEL = "msc_ffat";
    bool mscStarted = false;

}

// ── MSC mode (host sees a USB drive) ────────────────────────────────────
#if CONFIG_IDF_TARGET_ESP32S2 || CONFIG_IDF_TARGET_ESP32S3

bool MassStorage::setup() {

    if (mscStarted) {
        msc.mediaPresent(true);
        return true;
    }

    if (!FFat.begin(true, "/ffat", 10, FAT_LABEL)) return false;

    const esp_partition_t* partition = esp_partition_find_first(
        ESP_PARTITION_TYPE_DATA, ESP_PARTITION_SUBTYPE_DATA_FAT, FAT_LABEL);
    if (!partition) return false;

    if (wl_mount(partition, &wl_handle) != ESP_OK) return false;

    size_t sector_size  = wl_sector_size(wl_handle);
    size_t sector_count = wl_size(wl_handle) / sector_size;

    msc.vendorID("ESP32");
    msc.productID("MassStorage");
    msc.productRevision("1.0");
    msc.onRead(onRead);
    msc.onWrite(onWrite);
    msc.onStartStop(onStartStop);
    msc.mediaPresent(true);
    msc.begin(sector_count, sector_size);

    USB.begin();
    
    mscStarted = true;
    return true;
}

void MassStorage::setMediaPresent(bool present) {
    msc.mediaPresent(present);
}
#endif
// ── File operations (normal firmware mode) ──────────────────────────────

bool MassStorage::writeFile(const char* path, const String& content, bool append) {
    if (!FFat.begin(true, "/ffat", 10, FAT_LABEL)) return false;

    File f = FFat.open(path, append ? FILE_APPEND : FILE_WRITE);
    if (!f) {
        FFat.end();
        return false;
    }
    size_t written = f.print(content);
    f.close();
    FFat.end();

    return written == content.length();
}

bool MassStorage::readFile(const char* path, String& out) {
    String normalizedPath = path;
    if (normalizedPath.length() && normalizedPath[0] != '/') {
        normalizedPath = "/" + normalizedPath;
    }

    if (!FFat.begin(false, "/ffat", 10, FAT_LABEL)) return false;

    File f = FFat.open(normalizedPath.c_str(), FILE_READ);
    if (!f || f.isDirectory()) {
        if (f) f.close();
        FFat.end();
        return false;
    }

    out = "";
    out.reserve(f.size());
    while (f.available()) {
        out += (char)f.read();
    }
    f.close();
    FFat.end();
    return true;
}

bool MassStorage::deleteFile(const char* path) {
    if (!FFat.begin(true, "/ffat", 10, FAT_LABEL)) return false;

    bool ok = FFat.remove(path);
    FFat.end();
    return ok;
}

bool MassStorage::listFiles(String& out) {
    if (!FFat.begin(true, "/ffat", 10, FAT_LABEL)) return false;

    out = "";
    File root = FFat.open("/");
    if (!root || !root.isDirectory()) {
        if (root) root.close();
        FFat.end();
        return false;
    }

    File entry = root.openNextFile();
    while (entry) {
        out += entry.name();
        out += "\t";
        out += String(entry.size());
        out += "\n";
        entry.close();
        entry = root.openNextFile();
    }
    root.close();
    FFat.end();
    return true;
}

bool MassStorage::getSpace(uint64_t& totalBytes, uint64_t& usedBytes, uint64_t& freeBytes) {
    if (!FFat.begin(true, "/ffat", 10, FAT_LABEL)) return false;

    totalBytes = FFat.totalBytes();
    usedBytes  = FFat.usedBytes();
    freeBytes  = totalBytes - usedBytes;

    FFat.end();
    return true;
}