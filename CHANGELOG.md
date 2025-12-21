# Changelog

## 2025-12-21

### Added
- Chromecast metadata support: TV show and movie information now displays on the Chromecast screen during playback and pause
- Filename parsing for TV shows (e.g., `Show.Name.S01E02.Episode.Title.1080p...`) and movies (e.g., `Movie.Name.2024.1080p...`)
- Thumbnail serving via webserver for Chromecast pause screen display
- Thread lock to prevent race conditions when creating transcoders
- Queue functionality: files are transcoded sequentially, with pre-transcoding of the next file while the current one plays

### Fixed
- Transcoder now properly initializes device capabilities
- Stream ID parsing handles ffmpeg hex notation (e.g., `0:0[0x1]`)
- Audio transcoding logic only triggers when codec is unsupported
- Thread-safe UI updates using PyQt signals instead of QTimer from background threads
- Transcoder replacement no longer emits spurious error messages
- Auto-play now correctly switches to the next file's transcoder
- Scrubber resets to start position when switching files
- Duplicate transcoder creation prevented via existence check

### Changed
- Files are now transcoded one at a time instead of in parallel
- Transcoder creation consolidated through guarded methods
