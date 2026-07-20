# Environments

NRSuite supports three runtime environments, detected automatically via `detect_backend()`. The same CLI commands work identically in all three.

## No root (stock Termux)

The most unique use-case. Works on any unmodified Android phone.

```
Android USB host stack
        ↓
   termux-usb  (requests permission, grants fd)
        ↓
libusb_wrap_sys_device(fd)
        ↓
   nrsuite Python
```

```bash
pkg install python termux-api libusb && pip install espbridge
# Install Termux:API from F-Droid
./nrsuite scan  # permission popup appears on first run
```

## With root (Termux + tsu/sudo)

When running as uid 0, libusb opens `/dev/bus/usb` directly — no `termux-usb`, no permission dialog, no bootstrap subprocess. Faster and simpler.

```bash
pkg install python libusb && pip install espbridge
tsu  # or: sudo ./nrsuite scan
./nrsuite scan
```

## Kali NetHunter

Works in both the NetHunter terminal (Kali chroot, root) and a Termux session running alongside it.

```bash
# In the NetHunter terminal (root)
apt update && apt install python3 python3-pip libusb-1.0-0
pip3 install espbridge
./nrsuite scan

# Note: if cdc_acm claimed the interface, nrsuite detaches it automatically
```

## Backend summary

| Environment | uid | USB access |
|---|:---:|---|
| Stock Termux (no root) | 1000 | `termux-usb` → `libusb_wrap_sys_device(fd)` |
| Termux + root (tsu/sudo) | 0 | libusb → `/dev/bus/usb` directly |
| NetHunter terminal | 0 | libusb → `/dev/bus/usb` directly |
| NetHunter + Termux (no root) | 1000 | `termux-usb` → `libusb_wrap_sys_device(fd)` |

Detection is fully automatic — no `--root` flag or manual configuration needed.

---

[← Back to README](../README.md)
