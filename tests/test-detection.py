#!/usr/bin/env python3
"""
Test script to demonstrate Chromecast detection and capability recognition
"""
import sys
import time
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Add qtcast to path
sys.path.insert(0, '/home/teemu/qtcast')

print("=" * 70)
print("QtCast - Chromecast Detection Test")
print("=" * 70)
print()

print("Step 1: Importing modules...")
from qtcast.main import ChromecastDiscoveryThread
from qtcast.devices import get_device
import pychromecast

print("✓ Modules loaded")
print()

print("Step 2: Discovering Chromecasts on network...")
print("  Scanning local network for Chromecast devices...")
print("  (This may take up to 10 seconds)")
print()

# Create QApplication (required for QThread)
app = QApplication(sys.argv)

# Create discovery thread
discovery = ChromecastDiscoveryThread()
chromecasts_found = []

def on_found(chromecasts):
    global chromecasts_found
    chromecasts_found = chromecasts

    print("-" * 70)
    print(f"✓ Discovery Complete: Found {len(chromecasts)} device(s)")
    print("-" * 70)
    print()

    for i, cc in enumerate(chromecasts, 1):
        cc.wait()  # Wait for device info to load

        print(f"Device #{i}: {cc.name}")
        print(f"  {'Friendly Name:':<20} {cc.cast_info.friendly_name}")
        print(f"  {'Manufacturer:':<20} {cc.cast_info.manufacturer}")
        print(f"  {'Model Name:':<20} {cc.model_name}")
        print(f"  {'Cast Type:':<20} {cc.cast_type}")
        print(f"  {'UUID:':<20} {cc.uuid}")
        print(f"  {'IP Address:':<20} {cc.cast_info.host}:{cc.cast_info.port}")
        print()

        # Get device capabilities from database
        print("  Checking QtCast device capabilities database...")
        device = get_device(cc.cast_info.manufacturer, cc.model_name)

        print(f"  {'Device Record:':<20} {device.manufacturer} / {device.model_name}")
        print()
        print("  Codec Support:")
        print(f"    H.264 (AVC):       ✓ Always supported")
        print(f"    H.265 (HEVC):      {'✓ Supported' if device.h265 else '✗ Not supported'}")
        print(f"    AAC Audio:         ✓ Always supported")
        print(f"    MP3 Audio:         ✓ Always supported")
        print(f"    AC3/E-AC3 (Dolby): {'✓ Supported' if device.ac3 else '✗ Not supported'}")
        print()

        print("  Transcoding Behavior:")
        if device.h265:
            print("    • H.264 video → Direct stream (no transcode)")
            print("    • H.265 video → Direct stream (no transcode)")
        else:
            print("    • H.264 video → Direct stream (no transcode)")
            print("    • H.265 video → Transcode to H.264")

        if device.ac3:
            print("    • AAC audio   → Direct stream (no transcode)")
            print("    • MP3 audio   → Direct stream (no transcode)")
            print("    • AC3 audio   → Direct stream (no transcode)")
            print("    • E-AC3 audio → Direct stream (no transcode)")
        else:
            print("    • AAC audio   → Direct stream (no transcode)")
            print("    • MP3 audio   → Direct stream (no transcode)")
            print("    • AC3 audio   → Transcode to AAC/MP3")
            print("    • E-AC3 audio → Transcode to AAC/MP3")

        print()
        print("  Container Handling:")
        print("    • MP4 files   → Direct stream")
        print("    • MKV files   → Remux to MP4 (~100x realtime)")
        print("    • AVI files   → Remux to MP4 (~100x realtime)")
        print()

        # Show what this means for a typical file
        print("  Example: 1080p MKV with H.264 video + E-AC3 5.1 audio")
        if device.h265 and device.ac3:
            print("    → Container remux only (video & audio copied)")
            print("    → Processing time: ~2-3 seconds for 20-minute video")
            print("    → Quality: Perfect (no re-encoding)")
        else:
            print("    → Full transcode required")
            print("    → Processing time: ~5 minutes for 20-minute video")
            print("    → Quality: Slightly reduced (re-encoding)")

        print()
        print("=" * 70)

    # Quit the application
    QTimer.singleShot(100, app.quit)

print("  Initiating discovery thread...")
discovery.found.connect(on_found)
discovery.start()

# Set a timeout
QTimer.singleShot(15000, lambda: (print("\n⚠ Discovery timeout after 15 seconds\n"), app.quit()))

# Run the event loop
app.exec()

if not chromecasts_found:
    print("\n✗ No Chromecasts found on the network")
    print("\nTroubleshooting:")
    print("  • Make sure your Chromecast is powered on")
    print("  • Check that your computer and Chromecast are on the same network")
    print("  • Verify firewall allows mDNS (port 5353)")
    sys.exit(1)

print("\n✓ Detection test complete!")
print()
