#!/usr/bin/env bash

RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Bump this on each release
LATEST_VERSION="v1.2.0"

BINS=(
    "nrsuite-esp32c3.bin:ESP32-C3"
    "nrsuite-esp32s3.bin:ESP32-S3"
    "nrsuite-esp32s2.bin:ESP32-S2"
    "nrsuite-esp32-generic.bin:Classic ESP32 devkit (WROOM-32)"
)

echo -e "${BLUE}[*] Verifying target environment...${NC}"

IS_ROOT=0
if [ "$(id -u)" -eq 0 ]; then
    IS_ROOT=1
fi

IS_NETHUNTER=0
IS_TERMUX=0

if [ -f /etc/os-release ] && grep -q -i "kali" /etc/os-release; then
    IS_NETHUNTER=1
elif [ -n "$TERMUX_VERSION" ] || [ -d "/data/data/com.termux" ]; then
    IS_TERMUX=1
fi

if [ "$IS_NETHUNTER" -eq 1 ]; then
    echo -e "${GREEN}[+] Environment: Kali NetHunter${NC}"
    PKG_MANAGER="apt"
elif [ "$IS_TERMUX" -eq 1 ] && [ "$IS_ROOT" -eq 1 ]; then
    echo -e "${GREEN}[+] Environment: Termux (Root)${NC}"
    PKG_MANAGER="pkg"
elif [ "$IS_TERMUX" -eq 1 ] && [ "$IS_ROOT" -eq 0 ]; then
    echo -e "${GREEN}[+] Environment: Termux (Non-Root)${NC}"
    PKG_MANAGER="pkg"
else
    echo -e "${RED}[!] Error: Unsupported environment platform.${NC}"
    exit 1
fi

echo -e "${BLUE}[*] Syncing repositories and core dependencies...${NC}"
if [ "$PKG_MANAGER" = "apt" ]; then
    apt update -y && apt install -y python3 python3-pip libusb-1.0-0 git
    PIP_CMD="pip3"
elif [ "$PKG_MANAGER" = "pkg" ]; then
    pkg update -y && pkg install -y python termux-api libusb git
    PIP_CMD="pip"
fi

echo -e "${BLUE}[*] Configuring Python framework...${NC}"
$PIP_CMD install --upgrade pip 2>/dev/null
$PIP_CMD install pyusb || {
    echo -e "${RED}[!] Error: Failed to build pyusb constraints.${NC}"
    exit 1
}
$PIP_CMD install espbridge

if [ "$IS_TERMUX" -eq 1 ]; then
    echo -e "${BLUE}[*] Installing nrflash (Termux-native flasher)...${NC}"
    $PIP_CMD install nrflash || {
        echo -e "${RED}[!] Error: Failed to install nrflash.${NC}"
        exit 1
    }
fi

# Termux:API companion app check — needed for termux-usb regardless of root
if [ "$IS_TERMUX" -eq 1 ]; then
    if ! pm path com.termux.api 2>/dev/null | grep -q "com.termux.api"; then
        echo -e "${RED}[!] Termux:API companion app is missing.${NC}"
        echo -e "${YELLOW}[i] Install it from F-Droid, then re-run this script:${NC}"
        echo -e "${YELLOW}    https://f-droid.org/packages/com.termux.api/${NC}"
        echo -e "${YELLOW}[i] Note: the Play Store build is outdated — use F-Droid.${NC}"
        exit 1
    fi
fi

if [ ! -f "nrsuite" ] || [ ! -d "nrsuite_lib" ]; then
    echo -e "${BLUE}[*] Fetching NRSuite source...${NC}"
    git clone https://github.com/7wp81x/NRSuite.git || exit 1
    cd NRSuite || exit 1
fi

if [ -f "nrsuite" ] && [ -d "nrsuite_lib" ]; then
    chmod +x nrsuite
else
    echo -e "${RED}[!] Error: Script infrastructure layout missing (need nrsuite + nrsuite_lib).${NC}"
    exit 1
fi

echo -e "${GREEN}[+] Setup finalized successfully.${NC}"

# ── Firmware flashing (Termux only, no-root via nrflash) ────────────────────

if [ "$IS_TERMUX" -eq 1 ]; then
    echo ""
    echo -e "${BLUE}[*] Firmware flashing${NC}"
    echo "  1) Stable release ($LATEST_VERSION)"
    echo "  2) Beta build (firmware/beta-release/)"
    echo "  3) Skip flashing"
    read -r -p "Select an option [1-3]: " FW_CHOICE

    BIN_PATH=""

    case "$FW_CHOICE" in
        1)
            echo ""
            echo -e "${BLUE}[*] Select target board:${NC}"
            for i in "${!BINS[@]}"; do
                LABEL="${BINS[$i]#*:}"
                printf "  %d) %s\n" "$((i+1))" "$LABEL"
            done
            read -r -p "Board [1-${#BINS[@]}]: " BOARD_CHOICE

            IDX=$((BOARD_CHOICE-1))
            if [ -z "${BINS[$IDX]:-}" ]; then
                echo -e "${RED}[!] Invalid selection.${NC}"
                exit 1
            fi

            BIN_FILE="${BINS[$IDX]%%:*}"
            URL="https://github.com/7wp81x/NRSuite/releases/download/${LATEST_VERSION}/${BIN_FILE}"

            echo -e "${BLUE}[*] Downloading ${BIN_FILE} (${LATEST_VERSION})...${NC}"
            curl -sSL -o "$BIN_FILE" "$URL" || {
                echo -e "${RED}[!] Error: Failed to download ${URL}${NC}"
                exit 1
            }
            BIN_PATH="$BIN_FILE"
            ;;
        2)
            BETA_DIR="firmware/beta-release"
            if [ ! -d "$BETA_DIR" ]; then
                echo -e "${RED}[!] Error: ${BETA_DIR} not found — clone the full repo first.${NC}"
                exit 1
            fi

            mapfile -t BETA_BINS < <(find "$BETA_DIR" -maxdepth 1 -name "*.bin" | sort)
            if [ "${#BETA_BINS[@]}" -eq 0 ]; then
                echo -e "${RED}[!] Error: No .bin files found in ${BETA_DIR}${NC}"
                exit 1
            fi

            echo -e "${BLUE}[*] Select beta build:${NC}"
            for i in "${!BETA_BINS[@]}"; do
                printf "  %d) %s\n" "$((i+1))" "$(basename "${BETA_BINS[$i]}")"
            done
            read -r -p "Build [1-${#BETA_BINS[@]}]: " BETA_CHOICE

            IDX=$((BETA_CHOICE-1))
            if [ -z "${BETA_BINS[$IDX]:-}" ]; then
                echo -e "${RED}[!] Invalid selection.${NC}"
                exit 1
            fi
            BIN_PATH="${BETA_BINS[$IDX]}"
            ;;
        3)
            echo -e "${YELLOW}[i] Skipping firmware flash. Run 'nrflash write --offset 0x0 <file>.bin' manually later.${NC}"
            ;;
        *)
            echo -e "${RED}[!] Invalid selection.${NC}"
            exit 1
            ;;
    esac

    if [ -n "$BIN_PATH" ]; then
        echo ""
        echo -e "${YELLOW}[i] Enable OTG in your phone settings if it isn't already, then plug in the ESP32.${NC}"
        echo -e "${BLUE}[*] Waiting for device...${NC}"

        while true; do
            USB_LIST="$(termux-usb -l 2>/dev/null)"
            if [ -n "$USB_LIST" ] && [ "$USB_LIST" != "[]" ]; then
                break
            fi
            printf "\r${BLUE}[*] Waiting for device...${NC}   "
            sleep 1
        done

        echo ""
        echo -e "${GREEN}[+] Device detected.${NC}"
        read -r -p "Press Enter to flash ${BIN_PATH}..."

        echo -e "${BLUE}[*] Flashing with nrflash...${NC}"
        nrflash write --offset 0x0 "$BIN_PATH" || {
            echo -e "${RED}[!] Flash failed. If this persists, retry with --no-stub while holding the boot button.${NC}"
            exit 1
        }

        echo -e "${GREEN}[+] Flash complete.${NC}"
    fi
fi
cd NRSuite
echo -e "${GREEN}[+] Done. Run ./nrsuite scan to get started.${NC}"

