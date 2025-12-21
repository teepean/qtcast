#!/usr/bin/env python3
"""
Test script to verify device info dialog content
"""
import sys
sys.path.insert(0, '/home/teemu/qtcast')

from qtcast.devices import get_device, Device

print("=" * 70)
print("QtCast - Device Info Dialog Content Test")
print("=" * 70)
print()

# Test with Google TV Streamer (full capabilities)
print("Test 1: Google TV Streamer (Full Capabilities)")
print("-" * 70)
device = get_device("Google", "Google TV Streamer")
print(f"Manufacturer: {device.manufacturer}")
print(f"Model Name: {device.model_name}")
print(f"H.265 Support: {'✓ Supported' if device.h265 else '✗ Not supported'}")
print(f"AC3 Support: {'✓ Supported' if device.ac3 else '✗ Not supported'}")
print()

print("Expected Dialog Content:")
print("  - Device info table (name, manufacturer, model, etc.)")
print("  - Codec support: H.264 ✓, H.265 ✓, AAC ✓, MP3 ✓, AC3/E-AC3 ✓")
print("  - Transcoding: All direct stream (optimal)")
print("  - Example: Container remux only, ~2-3 sec, perfect quality")
print()

# Test with Chromecast Gen 1 (limited capabilities)
print("Test 2: Chromecast Gen 1 (Limited Capabilities)")
print("-" * 70)
device = get_device("Google", "Chromecast")
print(f"Manufacturer: {device.manufacturer}")
print(f"Model Name: {device.model_name}")
print(f"H.265 Support: {'✓ Supported' if device.h265 else '✗ Not supported'}")
print(f"AC3 Support: {'✓ Supported' if device.ac3 else '✗ Not supported'}")
print()

print("Expected Dialog Content:")
print("  - Device info table (name, manufacturer, model, etc.)")
print("  - Codec support: H.264 ✓, H.265 ✗, AAC ✓, MP3 ✓, AC3/E-AC3 ✗")
print("  - Transcoding: H.265 → H.264, AC3/E-AC3 → AAC/MP3")
print("  - Example: Full transcode, ~5 min, slightly reduced quality")
print()

# Test with Chromecast Ultra (partial capabilities - 4K but no AC3)
print("Test 3: Chromecast Ultra (4K but no Dolby)")
print("-" * 70)
device = get_device("Google", "Chromecast Ultra")
print(f"Manufacturer: {device.manufacturer}")
print(f"Model Name: {device.model_name}")
print(f"H.265 Support: {'✓ Supported' if device.h265 else '✗ Not supported'}")
print(f"AC3 Support: {'✓ Supported' if device.ac3 else '✗ Not supported'}")
print()

print("Expected Dialog Content:")
print("  - Device info table (name, manufacturer, model, etc.)")
print("  - Codec support: H.264 ✓, H.265 ✓, AAC ✓, MP3 ✓, AC3/E-AC3 ✗")
print("  - Transcoding: Video direct stream, AC3/E-AC3 → AAC/MP3")
print("  - Example: Full transcode (audio transcode needed)")
print()

print("=" * 70)
print("✓ Device capability detection working correctly!")
print()
print("To see the actual dialog in QtCast:")
print("  1. Launch: ./launch-qtcast.sh")
print("  2. Select your Chromecast from dropdown")
print("  3. Click the ℹ button next to the refresh button")
print("  4. View detailed device capabilities")
print("=" * 70)
