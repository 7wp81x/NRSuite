Import("env")
import os
import shutil

NAME_MAP = {
    "esp32-devkit": "nrsuite-esp32-generic.bin",
    "esp32-c3":     "nrsuite-esp32c3.bin",
    "esp32-s3":     "nrsuite-esp32s3.bin",
    "esp32-s2":     "nrsuite-esp32s2.bin",
}

BETA_NAME_MAP = {
    "esp32-devkit": "beta-nrsuite-esp32-generic.bin",
    "esp32-c3":     "beta-nrsuite-esp32c3.bin",
    "esp32-s3":     "beta-nrsuite-esp32s3.bin",
    "esp32-s2":     "beta-nrsuite-esp32s2.bin",
}

# Bootloader load offset differs by chip family
BOOT_OFFSET = {
    "esp32":   "0x1000",  # classic ESP32 - different offset!
    "esp32s2": "0x1000",
    "esp32s3": "0x0",
    "esp32c3": "0x0",
}

def merge_bin_action(source, target, env):
    board = env.BoardConfig()
    flash_size = board.get("upload.flash_size", "4MB")
    build_dir = env.subst("$BUILD_DIR")
    pioenv = env["PIOENV"]

    bootloader = os.path.join(build_dir, "bootloader.bin")
    partitions = os.path.join(build_dir, "partitions.bin")
    firmware = os.path.join(build_dir, "firmware.bin")

    project_dir = env.subst("$PROJECT_DIR")
    release_dir = os.path.join(project_dir, "release")
    beta_dir = os.path.join(release_dir, "Beta-release")
    os.makedirs(release_dir, exist_ok=True)
    os.makedirs(beta_dir, exist_ok=True)

    out_name = NAME_MAP.get(pioenv, f"nrsuite-{pioenv}.bin")
    beta_name = BETA_NAME_MAP.get(pioenv, f"beta-nrsuite-{pioenv}.bin")

    merged = os.path.join(release_dir, out_name)
    merged_beta = os.path.join(beta_dir, beta_name)

    mcu = board.get("build.mcu", "esp32")
    boot_offset = BOOT_OFFSET.get(mcu, "0x0")

    if not os.path.isfile(bootloader):
        print(f"[merge_script] WARNING: {bootloader} not found, skipping merge for {pioenv}")
        return

    cmd = (
        f'"{env.subst("$PYTHONEXE")}" -m esptool '
        f'--chip {mcu} merge_bin -o "{merged}" '
        f'--flash_size {flash_size} '
        f'{boot_offset} "{bootloader}" '
        f'0x8000 "{partitions}" '
        f'0x10000 "{firmware}"'
    )
    print(f"[merge_script] Merging -> {merged}  (mcu={mcu}, boot_offset={boot_offset})")
    result = env.Execute(cmd)
    if result != 0:
        print(f"[merge_script] ERROR: merge_bin failed for {pioenv} (exit {result})")
        return

    try:
        shutil.copyfile(merged, merged_beta)
        print(f"[merge_script] Copied  -> {merged_beta}")
    except OSError as e:
        print(f"[merge_script] ERROR: failed to copy beta binary for {pioenv}: {e}")

env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", merge_bin_action)