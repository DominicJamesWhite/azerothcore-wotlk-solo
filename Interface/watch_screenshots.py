#!/usr/bin/env python3
"""Watch WoW's Screenshots folder and copy new screenshots to Interface/screenshots/.

Runs as a background daemon. When a new screenshot appears (WoWScrnShot_MMDDYY_HHMMSS.tga/jpg),
it's copied to Interface/screenshots/ with a prompt for a descriptive name.

Usage:
  python watch_screenshots.py              # interactive mode (prompts for names)
  python watch_screenshots.py --auto       # auto-name mode (uses timestamp)
  python watch_screenshots.py --prefix mythic-plus  # auto-name with prefix
"""

import os
import sys
import time
import shutil
import argparse
from pathlib import Path

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

SCRIPT_DIR = Path(__file__).parent.resolve()
SCREENSHOTS_DIR = SCRIPT_DIR / "screenshots"

# WoW screenshot locations to watch
WOW_SCREENSHOT_DIRS = [
    Path(r"C:\Users\Shadow\Desktop\WoW Solo\WoW Solo\Screenshots"),
]

WATCH_EXTENSIONS = {".tga", ".jpg", ".jpeg", ".png", ".bmp"}
POLL_INTERVAL = 2  # seconds
MAX_WIDTH = 1920  # resize to this width max (maintains aspect ratio)
OUTPUT_FORMAT = ".jpg"  # convert all screenshots to JPEG
OUTPUT_QUALITY = 85


def find_wow_screenshot_dir():
    """Find the first existing WoW screenshot directory."""
    for d in WOW_SCREENSHOT_DIRS:
        if d.is_dir():
            return d
    return None


def get_existing_files(watch_dir):
    """Get set of existing screenshot files."""
    if not watch_dir.is_dir():
        return set()
    return {
        f.name for f in watch_dir.iterdir()
        if f.is_file() and f.suffix.lower() in WATCH_EXTENSIONS
    }


def make_name(original_name, prefix=None, counter=None):
    """Generate a descriptive filename, always using OUTPUT_FORMAT."""
    stem = Path(original_name).stem
    ext = OUTPUT_FORMAT

    if prefix:
        if counter is not None:
            return f"{prefix}_{counter:03d}{ext}"
        return f"{prefix}_{stem}{ext}"
    return f"{stem}{ext}"


def prompt_name(original_name):
    """Ask user for a descriptive name."""
    print(f"\n  New screenshot: {original_name}")
    name = input("  Name (enter for timestamp, 'skip' to ignore): ").strip()

    if name.lower() == "skip":
        return None
    if not name:
        return make_name(original_name)

    # Sanitize and ensure correct extension
    name = name.replace(" ", "_")
    if not name.endswith(OUTPUT_FORMAT):
        name = Path(name).stem + OUTPUT_FORMAT
    return name


def process_screenshot(src_path, dest_name):
    """Resize, convert to JPEG, and save screenshot."""
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = SCREENSHOTS_DIR / dest_name

    # Avoid overwrites
    if dest.exists():
        stem = dest.stem
        ext = dest.suffix
        i = 1
        while dest.exists():
            dest = SCREENSHOTS_DIR / f"{stem}_{i}{ext}"
            i += 1

    if HAS_PIL:
        img = Image.open(src_path)
        orig_size = f"{img.width}x{img.height}"
        if img.width > MAX_WIDTH:
            ratio = MAX_WIDTH / img.width
            new_h = int(img.height * ratio)
            img = img.resize((MAX_WIDTH, new_h), Image.LANCZOS)
        # Convert RGBA (TGA) to RGB for JPEG
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(dest, "JPEG", quality=OUTPUT_QUALITY)
        print(f"    {orig_size} -> {img.width}x{img.height}")
    else:
        # Fallback: just copy without resizing
        shutil.copy2(src_path, dest)
        print("    (Pillow not installed - copied without resize)")

    return dest


def watch(watch_dir, auto=False, prefix=None):
    """Main watch loop."""
    print(f"Watching: {watch_dir}")
    print(f"Copying to: {SCREENSHOTS_DIR}")
    if HAS_PIL:
        print(f"Resize: max {MAX_WIDTH}px wide, JPEG q{OUTPUT_QUALITY}")
    else:
        print("WARNING: Pillow not installed (pip install Pillow) - no resize")
    if auto:
        print(f"Auto-name mode{f' (prefix: {prefix})' if prefix else ''}")
    else:
        print("Interactive mode - will prompt for names")
    print("Press Ctrl+C to stop.\n")

    known_files = get_existing_files(watch_dir)
    counter = 0

    while True:
        try:
            time.sleep(POLL_INTERVAL)
            current_files = get_existing_files(watch_dir)
            new_files = current_files - known_files

            for fname in sorted(new_files):
                src = watch_dir / fname
                # Wait a moment for the file to finish writing
                time.sleep(0.5)

                if auto:
                    dest_name = make_name(fname, prefix=prefix, counter=counter)
                    counter += 1
                else:
                    dest_name = prompt_name(fname)
                    if dest_name is None:
                        print("  Skipped.")
                        known_files.add(fname)
                        continue

                dest = process_screenshot(src, dest_name)
                print(f"  Saved: {dest.relative_to(SCRIPT_DIR)}")

            known_files = current_files

        except KeyboardInterrupt:
            print("\nStopping screenshot watcher.")
            break


def main():
    parser = argparse.ArgumentParser(description="Watch WoW screenshots folder")
    parser.add_argument("--auto", action="store_true",
                        help="Auto-name screenshots without prompting")
    parser.add_argument("--prefix", type=str, default=None,
                        help="Prefix for auto-named screenshots")
    parser.add_argument("--wow-dir", type=str, default=None,
                        help="Override WoW screenshots directory path")
    args = parser.parse_args()

    if args.wow_dir:
        watch_dir = Path(args.wow_dir)
    else:
        watch_dir = find_wow_screenshot_dir()

    if watch_dir is None or not watch_dir.is_dir():
        # WoW creates the Screenshots folder on first screenshot
        # If it doesn't exist yet, we can create it or wait
        if watch_dir is None:
            watch_dir = WOW_SCREENSHOT_DIRS[0]
        print(f"Screenshots folder not found: {watch_dir}")
        print("It will be created when you take your first screenshot in WoW (Print Screen).")
        print("Starting watcher anyway...\n")
        watch_dir.mkdir(parents=True, exist_ok=True)

    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    watch(watch_dir, auto=args.auto, prefix=args.prefix)


if __name__ == "__main__":
    main()
