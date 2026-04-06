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

SCRIPT_DIR = Path(__file__).parent.resolve()
SCREENSHOTS_DIR = SCRIPT_DIR / "screenshots"

# WoW screenshot locations to watch
WOW_SCREENSHOT_DIRS = [
    Path(r"C:\Users\Shadow\Desktop\WoW Solo\WoW Solo\Screenshots"),
]

WATCH_EXTENSIONS = {".tga", ".jpg", ".jpeg", ".png", ".bmp"}
POLL_INTERVAL = 2  # seconds


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
    """Generate a descriptive filename from the original WoW screenshot name."""
    ext = Path(original_name).suffix.lower()
    # Convert .tga to .tga (keep as-is, it's what WoW produces)
    stem = Path(original_name).stem

    if prefix:
        if counter is not None:
            return f"{prefix}_{counter:03d}{ext}"
        return f"{prefix}_{stem}{ext}"
    return f"{stem}{ext}"


def prompt_name(original_name):
    """Ask user for a descriptive name."""
    ext = Path(original_name).suffix.lower()
    print(f"\n  New screenshot: {original_name}")
    name = input("  Name (enter for timestamp, 'skip' to ignore): ").strip()

    if name.lower() == "skip":
        return None
    if not name:
        return original_name

    # Ensure correct extension
    if not name.endswith(ext):
        name = name + ext
    # Sanitize
    name = name.replace(" ", "_")
    return name


def copy_screenshot(src_path, dest_name):
    """Copy screenshot to our screenshots directory."""
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

    shutil.copy2(src_path, dest)
    return dest


def watch(watch_dir, auto=False, prefix=None):
    """Main watch loop."""
    print(f"Watching: {watch_dir}")
    print(f"Copying to: {SCREENSHOTS_DIR}")
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

                dest = copy_screenshot(src, dest_name)
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
