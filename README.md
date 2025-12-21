# QtCast

A PyQt6-based GUI for casting local media files to Chromecast devices.

**QtCast is a port of [Gnomecast](https://github.com/julienc91/gnomecast) using PyQt6 instead of GTK3.**

![QtCast Logo](https://raw.githubusercontent.com/julienc91/gnomecast/master/icons/gnomecast_16.png)

## Features

- ✓ Cast any audio/video file to Chromecast (anything ffmpeg can read)
- ✓ Automatic smart transcoding (only when needed)
- ✓ Subtitle support (embedded and external .srt files)
- ✓ Multi-file queue with drag-and-drop
- ✓ Fast seeking and scrubbing
- ✓ Multiple audio/video stream selection
- ✓ 5.1/7.1 surround sound support
- ✓ 4K video support on compatible devices
- ✓ Cross-platform (Linux, macOS, Windows)

## Installation

### Prerequisites

```bash
# Install ffmpeg (required)
sudo apt install ffmpeg

# On macOS:
brew install ffmpeg
```

### Install from source

```bash
cd /home/teemu/qtcast
python3 -m venv venv
source venv/bin/activate
pip install -e .
```

### Install in Gnomecast venv

If you already have Gnomecast installed:

```bash
cd /home/teemu/gnomecast
source venv/bin/activate
cd /home/teemu/qtcast
pip install PyQt6
pip install -e .
```

## Usage

### GUI Mode

```bash
# If installed in venv
source venv/bin/activate
python3 -m qtcast

# Or use the launcher script
./launch-qtcast.sh
```

### Features

1. **Select Chromecast**: Choose your device from the dropdown (or click Refresh)
2. **Add Files**: Click the + button or drag & drop media files
3. **Select Streams**: Choose audio tracks and subtitles from the dropdowns
4. **Play**: Double-click a file or click the play button
5. **Control**: Use the playback controls (play/pause, stop, rewind, forward)
6. **Seek**: Drag the scrubber to any position in the video

## How It Works

### Smart Transcoding

QtCast only transcodes when necessary:

- **Container only**: If your video has h264 video + AAC audio in an MKV container, QtCast just rewrites the container to MP4 (100x realtime on most systems)
- **Audio only**: If video is h264 but audio is AC3, it copies the video stream and only transcodes audio (20x realtime)
- **Full transcode**: Only if both streams are incompatible (5x realtime)

### Chromecast Compatibility

Chromecasts support:
- Video: h264, h265 (on Ultra and newer)
- Audio: AAC, MP3, AC3 (5.1/7.1 on supported devices)
- Containers: MP4

## Architecture

- **Frontend**: PyQt6 for cross-platform GUI
- **Backend**: pychromecast for Chromecast communication
- **Transcoding**: ffmpeg for media analysis and conversion
- **Streaming**: bottle + paste HTTP server
- **Subtitles**: pycaption for WebVTT conversion

## Differences from Gnomecast

- Uses PyQt6 instead of GTK3
- Cross-platform (works on Linux, macOS, Windows)
- Slightly different UI layout (table instead of tree view)
- Same core functionality and transcoding logic

## Credits

- Original Gnomecast by [Derek Anderson](https://github.com/keredson/gnomecast) and [contributors](https://github.com/julienc91/gnomecast)
- [pychromecast](https://github.com/balloob/pychromecast)
- [pycaption](https://github.com/pbs/pycaption)
- [ffmpeg](https://www.ffmpeg.org/)

## License

GPL-3.0-or-later (same as Gnomecast)
