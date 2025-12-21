"""
QtCast - Main application window and logic
"""
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QComboBox, QLabel, QSlider, QListWidget, QListWidgetItem,
    QFileDialog, QMessageBox, QTableWidget, QTableWidgetItem, QProgressBar,
    QHeaderView
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QUrl
from PyQt6.QtGui import QPixmap, QIcon, QDragEnterEvent, QDropEvent

try:
    import pychromecast
    DEPS_MET = True
except ImportError:
    DEPS_MET = False
    print("ERROR: pychromecast not installed. Run: pip install pychromecast")

from .version import __version__
from .webserver import QtCastWebServer
from .transcoder import Transcoder, AUDIO_EXTS
from .ffmpeg import (
    check_ffmpeg_installed,
    extract_thumbnail,
    get_media_duration,
)
from .subtitles import convert_subtitles_to_webvtt, extract_subtitles_from_file
from .screensaver import ScreenSaverInhibitor
from .utils import humanize_seconds

import re


def parse_tv_filename(filename):
    """Parse TV show filename to extract metadata for Chromecast.

    Supports patterns like:
    - Show.Name.S01E02.Episode.Title.1080p.WEB-DL.mkv
    - Show Name - S01E02 - Episode Title.mkv
    """
    basename = os.path.basename(filename)

    # Pattern 1: Show.Name.S01E02.Episode.Title.Quality...
    pattern1 = r'^(.+?)[.\s]+S(\d{1,2})E(\d{1,2})[.\s]+(.+?)[.\s]+\d{3,4}p'
    match = re.match(pattern1, basename, re.IGNORECASE)

    if match:
        return {
            "metadataType": 2,  # TV Show
            "seriesTitle": match.group(1).replace('.', ' ').strip(),
            "season": int(match.group(2)),
            "episode": int(match.group(3)),
            "title": match.group(4).replace('.', ' ').strip(),
        }

    # Pattern 2: Show.Name.S01E02... (without episode title before quality)
    pattern2 = r'^(.+?)[.\s]+S(\d{1,2})E(\d{1,2})'
    match = re.match(pattern2, basename, re.IGNORECASE)

    if match:
        return {
            "metadataType": 2,  # TV Show
            "seriesTitle": match.group(1).replace('.', ' ').strip(),
            "season": int(match.group(2)),
            "episode": int(match.group(3)),
        }

    return None


def parse_movie_filename(filename):
    """Parse movie filename to extract metadata for Chromecast.

    Supports patterns like:
    - Movie.Name.2024.1080p.BluRay.mkv
    - Movie Name (2024).mkv
    """
    basename = os.path.basename(filename)

    # Pattern 1: Movie.Name.2024.Quality...
    pattern1 = r'^(.+?)[.\s]+(\d{4})[.\s]+\d{3,4}p'
    match = re.match(pattern1, basename, re.IGNORECASE)

    if match:
        return {
            "metadataType": 1,  # Movie
            "title": match.group(1).replace('.', ' ').strip(),
            "releaseDate": match.group(2),
        }

    # Pattern 2: Movie Name (2024)
    pattern2 = r'^(.+?)\s*\((\d{4})\)'
    match = re.match(pattern2, basename, re.IGNORECASE)

    if match:
        return {
            "metadataType": 1,  # Movie
            "title": match.group(1).strip(),
            "releaseDate": match.group(2),
        }

    return None


class StreamMetadata:
    """Metadata for a media stream"""
    def __init__(self, index, codec, title):
        self.index = index
        self.codec = codec
        self.title = title

    def __repr__(self):
        fields = [
            "%s:%s" % (k, v)
            for k, v in self.__dict__.items()
            if v is not None and not k.startswith("_")
        ]
        return "%s(%s)" % (self.__class__.__name__, ", ".join(fields))


class AudioMetadata(StreamMetadata):
    """Metadata for an audio stream"""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.channels = 2

    def details(self):
        if self.channels == 1:
            channels = "mono"
        elif self.channels == 2:
            channels = "stereo"
        elif self.channels == 6:
            channels = "5.1"
        elif self.channels == 8:
            channels = "7.1"
        else:
            channels = str(self.channels)
        return "%s (%s/%s)" % (self.title, self.codec, channels)


class FileMetadata:
    """Metadata for a media file"""
    def __init__(self, fn, callback):
        self.fn = fn
        self.ready = False
        self.thumbnail_fn = None
        self._ffmpeg_output = None
        self.container = None
        self.video_streams = []
        self.audio_streams = []
        self.subtitles = []

        # Parse in a thread
        threading.Thread(target=self._parse, args=(callback,), daemon=True).start()

    def _parse(self, callback):
        """Parse file metadata using ffmpeg"""
        self.thumbnail_fn = str(extract_thumbnail(self.fn))
        try:
            self._ffmpeg_output = subprocess.check_output(
                ["ffmpeg", "-i", self.fn, "-f", "ffmetadata", "-"],
                stderr=subprocess.STDOUT,
            ).decode()
        except subprocess.CalledProcessError as e:
            self._ffmpeg_output = e.output.decode() if e.output else ""

        output = self._ffmpeg_output.split("\n")
        self.container = self.fn.lower().split(".")[-1]
        stream = None

        for line in output:
            line = line.strip()
            if line.startswith("Stream") and "Video" in line:
                id = line.split()[1].strip("#").strip(":")
                title = "Video #%i" % (len(self.video_streams) + 1)
                if "(" in id:
                    title = id[id.index("(") + 1 : id.index(")")]
                    id = id[: id.index("(")]
                # Strip hex notation like [0x1] from stream id
                if "[" in id:
                    id = id[: id.index("[")]
                video_codec = line.split()[3]
                stream = StreamMetadata(id, video_codec, title)
                self.video_streams.append(stream)
            elif line.startswith("Stream") and "Audio" in line:
                title = "Audio #%i" % (len(self.audio_streams) + 1)
                id = line.split()[1].strip("#").strip(":")
                if "(" in id:
                    title = id[id.index("(") + 1 : id.index(")")]
                    id = id[: id.index("(")]
                # Strip hex notation like [0x2] from stream id
                if "[" in id:
                    id = id[: id.index("[")]
                audio_codec = line.split()[3].strip(",")
                stream = AudioMetadata(id, audio_codec, title=title)
                if ", mono, " in line:
                    stream.channels = 1
                if ", stereo, " in line:
                    stream.channels = 2
                if ", 5.1" in line:
                    stream.channels = 6
                if ", 7.1" in line:
                    stream.channels = 8
                self.audio_streams.append(stream)
            elif line.startswith("Stream") and "Subtitle" in line:
                id = line.split()[1].strip("#").strip(":")
                if "(" in id:
                    title = id[id.index("(") + 1 : id.index(")")]
                    id = id[: id.index("(")]
                else:
                    title = "Subtitle #%i" % (len(self.subtitles) + 1)
                # Strip hex notation like [0x3] from stream id
                if "[" in id:
                    id = id[: id.index("[")]
                stream = StreamMetadata(id, None, title)
                self.subtitles.append(stream)
            elif stream and line.startswith("title"):
                parts = line.split()
                if len(parts) >= 3:
                    stream.title = parts[2]

        self.load_subtitles()
        self.ready = True
        print(self)
        if callback:
            callback(self)

    def __repr__(self):
        return (f"FileMetadata(fn:{self.fn}, ready:{self.ready}, "
                f"thumbnail_fn:{self.thumbnail_fn}, container:{self.container}, "
                f"video_streams:{self.video_streams}, audio_streams:{self.audio_streams}, "
                f"subtitles:{self.subtitles})")

    def load_subtitles(self):
        """Load embedded subtitles"""
        stream_indexes = [stream.index for stream in self.subtitles]
        subtitles = extract_subtitles_from_file(self.fn, stream_indexes)
        if subtitles is not None:
            for i, stream in enumerate(self.subtitles):
                stream._subtitles = subtitles[i]
        else:
            self.subtitles = []

    def wait(self):
        """Wait for parsing to complete"""
        while not self.ready:
            time.sleep(0.1)


class ChromecastDiscoveryThread(QThread):
    """Thread for discovering Chromecasts"""
    found = pyqtSignal(list)  # list of chromecasts

    def run(self):
        chromecasts, _ = pychromecast.get_chromecasts(timeout=10)
        self.found.emit(chromecasts)


class QtCastWindow(QMainWindow):
    """Main application window"""

    # Signal for thread-safe UI updates from background threads
    file_ui_ready = pyqtSignal(int, object)  # index, fmd

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"QtCast v{__version__}")
        self.setAcceptDrops(True)

        # State
        self.cast = None
        self.webserver = None
        self.chromecasts = []
        self.files_data = []  # List of (filename, fmd, transcoder, duration)
        self.transcoder_lock = threading.Lock()  # Prevent race conditions
        self.current_file = None
        self.current_transcoder = None
        self.current_duration = None
        self.video_stream = None
        self.audio_stream = None
        self.subtitles = None
        self.last_known_player_state = None
        self.last_known_current_time = None
        self.last_time_current_time = None
        self.seeking = False
        self.screen_saver_inhibitor = ScreenSaverInhibitor()

        # Set up UI
        self.init_ui()

        # Connect signals for thread-safe operations
        self.file_ui_ready.connect(self._update_file_ui)

        # Start webserver in background
        threading.Thread(target=self.start_webserver, daemon=True).start()

        # Start status monitoring
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.monitor_cast_status)
        self.status_timer.start(1000)  # Check every second

        # Check ffmpeg
        threading.Thread(target=self.check_ffmpeg, daemon=True).start()

        # Discover Chromecasts
        self.discover_chromecasts()

    def init_ui(self):
        """Initialize the user interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Chromecast selection row
        chromecast_layout = QHBoxLayout()
        self.chromecast_combo = QComboBox()
        self.chromecast_combo.addItem("Searching...")
        self.chromecast_combo.currentIndexChanged.connect(self.on_chromecast_selected)
        chromecast_layout.addWidget(self.chromecast_combo)

        self.refresh_button = QPushButton("🔄")
        self.refresh_button.setMaximumWidth(40)
        self.refresh_button.clicked.connect(self.discover_chromecasts)
        chromecast_layout.addWidget(self.refresh_button)

        self.device_info_button = QPushButton("ℹ")
        self.device_info_button.setMaximumWidth(40)
        self.device_info_button.setToolTip("Show device capabilities")
        self.device_info_button.clicked.connect(self.show_device_info)
        self.device_info_button.setEnabled(False)
        chromecast_layout.addWidget(self.device_info_button)

        main_layout.addLayout(chromecast_layout)

        # Status label for device capabilities
        self.device_status_label = QLabel("")
        self.device_status_label.setStyleSheet("QLabel { color: #666; font-size: 10px; padding: 2px; }")
        main_layout.addWidget(self.device_status_label)

        # Thumbnail display
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.thumbnail_label.setMinimumHeight(200)
        self.thumbnail_label.setStyleSheet("QLabel { background-color: #2a2a2a; }")
        main_layout.addWidget(self.thumbnail_label)

        # File list
        files_layout = QHBoxLayout()

        self.file_table = QTableWidget()
        self.file_table.setColumnCount(3)
        self.file_table.setHorizontalHeaderLabels(["File", "Duration", "Progress"])
        self.file_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.file_table.cellDoubleClicked.connect(self.on_file_double_clicked)
        files_layout.addWidget(self.file_table)

        # Add/Remove buttons
        btn_layout = QVBoxLayout()
        self.add_button = QPushButton("+")
        self.add_button.clicked.connect(self.add_files)
        btn_layout.addWidget(self.add_button)

        self.remove_button = QPushButton("-")
        self.remove_button.clicked.connect(self.remove_selected_files)
        self.remove_button.setEnabled(False)
        btn_layout.addWidget(self.remove_button)
        btn_layout.addStretch()

        files_layout.addLayout(btn_layout)
        main_layout.addLayout(files_layout)

        # Stream selection row
        stream_layout = QHBoxLayout()
        self.audio_combo = QComboBox()
        self.audio_combo.currentIndexChanged.connect(self.on_audio_changed)
        stream_layout.addWidget(self.audio_combo)

        self.subtitle_combo = QComboBox()
        self.subtitle_combo.currentIndexChanged.connect(self.on_subtitle_changed)
        stream_layout.addWidget(self.subtitle_combo)

        self.info_button = QPushButton("ℹ")
        self.info_button.setMaximumWidth(40)
        self.info_button.clicked.connect(self.show_file_info)
        stream_layout.addWidget(self.info_button)
        main_layout.addLayout(stream_layout)

        # Playback scrubber
        scrubber_layout = QHBoxLayout()
        self.scrubber = QSlider(Qt.Orientation.Horizontal)
        self.scrubber.setEnabled(False)
        self.scrubber.sliderPressed.connect(self.on_scrubber_pressed)
        self.scrubber.sliderMoved.connect(self.on_scrubber_moved)
        self.scrubber.sliderReleased.connect(self.on_scrubber_released)
        scrubber_layout.addWidget(self.scrubber)

        self.time_label = QLabel("0s")
        scrubber_layout.addWidget(self.time_label)
        main_layout.addLayout(scrubber_layout)

        # Media controls
        controls_layout = QHBoxLayout()
        self.rewind_button = QPushButton("⏪")
        self.rewind_button.clicked.connect(self.rewind)
        self.rewind_button.setEnabled(False)
        controls_layout.addWidget(self.rewind_button)

        self.play_button = QPushButton("▶")
        self.play_button.clicked.connect(self.toggle_play)
        self.play_button.setEnabled(False)
        controls_layout.addWidget(self.play_button)

        self.forward_button = QPushButton("⏩")
        self.forward_button.clicked.connect(self.forward)
        self.forward_button.setEnabled(False)
        controls_layout.addWidget(self.forward_button)

        self.stop_button = QPushButton("⏹")
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setEnabled(False)
        controls_layout.addWidget(self.stop_button)

        self.volume_button = QPushButton("🔊")
        controls_layout.addWidget(self.volume_button)
        main_layout.addLayout(controls_layout)

        self.resize(600, 700)

    def start_webserver(self):
        """Start the HTTP server for streaming"""
        self.webserver = QtCastWebServer(
            get_subtitles=lambda: self.subtitles,
            get_transcoder=lambda: self.current_transcoder,
            get_thumbnail=lambda: self.get_current_thumbnail(),
        )
        print(f"serving on http://{self.webserver.ip}:{self.webserver.port}")
        self.webserver.start()

    def get_current_thumbnail(self):
        """Get thumbnail path for current file"""
        if not self.current_file:
            return None
        for fn, fmd, _, _ in self.files_data:
            if fn == self.current_file and fmd and fmd.thumbnail_fn:
                return fmd.thumbnail_fn
        return None

    def check_ffmpeg(self):
        """Check if ffmpeg is installed"""
        time.sleep(1)
        if not check_ffmpeg_installed():
            QMessageBox.critical(
                self,
                "ffmpeg not found",
                "Could not find ffmpeg. Please install it:\nsudo apt install ffmpeg"
            )
            sys.exit(1)

    def discover_chromecasts(self):
        """Discover Chromecasts on the network"""
        self.chromecast_combo.clear()
        self.chromecast_combo.addItem("Searching...")
        self.discovery_thread = ChromecastDiscoveryThread()
        self.discovery_thread.found.connect(self.on_chromecasts_found)
        self.discovery_thread.start()

    def on_chromecasts_found(self, chromecasts):
        print(f"Found {len(chromecasts)} Chromecast(s)")
        for cc in chromecasts:
            print(cc)
        """Handle discovered Chromecasts"""
        self.chromecasts = chromecasts
        self.chromecast_combo.clear()
        self.chromecast_combo.addItem("Select a Chromecast...")

        for cc in chromecasts:
            friendly_name = cc.cast_info.friendly_name
            if cc.cast_type != "cast":
                friendly_name = f"{friendly_name} ({cc.cast_type})"
            self.chromecast_combo.addItem(friendly_name, cc)

        if len(chromecasts) == 1:
            self.chromecast_combo.setCurrentIndex(1)

    def on_chromecast_selected(self, index):
        """Handle Chromecast selection"""
        if index > 0:
            cc = self.chromecast_combo.itemData(index)
            if cc:
                self.cast = cc
                self.device_info_button.setEnabled(True)

                # Show brief capability summary
                from .devices import get_device
                device = get_device(cc.cast_info.manufacturer, cc.model_name)
                caps = []
                if device.h265:
                    caps.append("4K/HEVC")
                if device.ac3:
                    caps.append("Dolby 5.1/7.1")

                status = f"✓ {cc.model_name}"
                if caps:
                    status += f" - Supports: {', '.join(caps)}"
                self.device_status_label.setText(status)

                # Create transcoder for current file if one is selected
                if self.current_file and self.video_stream:
                    for i, (fn, fmd, _, duration) in enumerate(self.files_data):
                        if fn == self.current_file and fmd.ready:
                            self._create_transcoder(i, fmd)
                            break

                self.update_button_states()
        else:
            self.device_info_button.setEnabled(False)
            self.device_status_label.setText("")

    def show_device_info(self):
        """Show detailed device capabilities dialog"""
        if not self.cast:
            return

        from .devices import get_device

        cc = self.cast
        device = get_device(cc.cast_info.manufacturer, cc.model_name)

        # Build detailed info text
        info = f"""<h2>{cc.name}</h2>
<table border="0" cellpadding="4">
<tr><td><b>Friendly Name:</b></td><td>{cc.cast_info.friendly_name}</td></tr>
<tr><td><b>Manufacturer:</b></td><td>{cc.cast_info.manufacturer}</td></tr>
<tr><td><b>Model Name:</b></td><td>{cc.model_name}</td></tr>
<tr><td><b>Cast Type:</b></td><td>{cc.cast_type}</td></tr>
<tr><td><b>UUID:</b></td><td>{cc.uuid}</td></tr>
<tr><td><b>IP Address:</b></td><td>{cc.cast_info.host}:{cc.cast_info.port}</td></tr>
</table>

<h3>Codec Support</h3>
<table border="0" cellpadding="4">
<tr><td>H.264 (AVC):</td><td><b>✓ Always supported</b></td></tr>
<tr><td>H.265 (HEVC):</td><td><b>{'✓ Supported' if device.h265 else '✗ Not supported'}</b></td></tr>
<tr><td>AAC Audio:</td><td><b>✓ Always supported</b></td></tr>
<tr><td>MP3 Audio:</td><td><b>✓ Always supported</b></td></tr>
<tr><td>AC3/E-AC3 (Dolby):</td><td><b>{'✓ Supported' if device.ac3 else '✗ Not supported'}</b></td></tr>
</table>

<h3>Transcoding Behavior</h3>
<p><b>Video:</b></p>
<ul>
<li>H.264 video → Direct stream (no transcode)</li>"""

        if device.h265:
            info += "\n<li>H.265 video → Direct stream (no transcode)</li>"
        else:
            info += "\n<li>H.265 video → <i>Transcode to H.264</i></li>"

        info += "\n</ul>\n<p><b>Audio:</b></p>\n<ul>"
        info += "\n<li>AAC audio → Direct stream (no transcode)</li>"
        info += "\n<li>MP3 audio → Direct stream (no transcode)</li>"

        if device.ac3:
            info += "\n<li>AC3 audio → Direct stream (no transcode)</li>"
            info += "\n<li>E-AC3 audio → Direct stream (no transcode)</li>"
        else:
            info += "\n<li>AC3 audio → <i>Transcode to AAC/MP3</i></li>"
            info += "\n<li>E-AC3 audio → <i>Transcode to AAC/MP3</i></li>"

        info += """</ul>

<h3>Container Handling</h3>
<ul>
<li>MP4 files → Direct stream</li>
<li>MKV files → Remux to MP4 (~100x realtime)</li>
<li>AVI files → Remux to MP4 (~100x realtime)</li>
</ul>

<h3>Example: 1080p MKV with H.264 video + E-AC3 5.1 audio</h3>"""

        if device.h265 and device.ac3:
            info += """<p><b>✓ Optimal Performance:</b></p>
<ul>
<li>Container remux only (video & audio copied)</li>
<li>Processing time: ~2-3 seconds for 20-minute video</li>
<li>Quality: Perfect (no re-encoding)</li>
</ul>"""
        else:
            info += """<p><b>⚠ Transcoding Required:</b></p>
<ul>
<li>Full transcode needed</li>
<li>Processing time: ~5 minutes for 20-minute video</li>
<li>Quality: Slightly reduced (re-encoding)</li>
</ul>"""

        # Create and show message box
        msg = QMessageBox(self)
        msg.setWindowTitle(f"Device Info - {cc.name}")
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.setText(info)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def add_files(self):
        """Add files to the queue"""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select media files",
            os.path.expanduser("~/"),
            "Media files (*.mp4 *.mkv *.avi *.mov *.mp3 *.wav);;All files (*.*)"
        )
        if files:
            for fn in files:
                self.queue_file(fn)

    def queue_file(self, fn):
        """Queue a single file"""
        # Check if already in queue
        for file_fn, _, _, _ in self.files_data:
            if file_fn == fn:
                return

        display_name = os.path.basename(fn)
        if len(display_name) > 50:
            display_name = display_name[:40] + "..." + display_name[-10:]

        # Add to table
        row = self.file_table.rowCount()
        self.file_table.insertRow(row)
        self.file_table.setItem(row, 0, QTableWidgetItem(display_name))
        self.file_table.setItem(row, 1, QTableWidgetItem("..."))

        # Create progress bar
        progress = QProgressBar()
        progress.setValue(0)
        self.file_table.setCellWidget(row, 2, progress)

        # Parse metadata in background
        def on_metadata_ready(fmd):
            duration = get_media_duration(fn)
            for i, (file_fn, _, existing_transcoder, _) in enumerate(self.files_data):
                if file_fn == fn:
                    # Preserve existing transcoder if any
                    self.files_data[i] = (fn, fmd, existing_transcoder, duration)
                    self.file_table.item(i, 1).setText(humanize_seconds(duration))
                    break

        fmd = FileMetadata(fn, on_metadata_ready)
        self.files_data.append((fn, fmd, None, None))

        # Select first file if none selected
        if len(self.files_data) == 1 and self.current_file is None:
            self.select_file(0)

    def remove_selected_files(self):
        """Remove selected files from queue"""
        selected_rows = set(item.row() for item in self.file_table.selectedItems())
        for row in sorted(selected_rows, reverse=True):
            self.file_table.removeRow(row)
            del self.files_data[row]

    def on_file_double_clicked(self, row, col):
        """Handle file double-click"""
        self.select_file(row)

    def select_file(self, index):
        """Select a file for playback"""
        if index < 0 or index >= len(self.files_data):
            return

        fn, fmd, transcoder, duration = self.files_data[index]
        self.current_file = fn
        self.current_duration = duration
        self.current_transcoder = transcoder  # Use existing transcoder if available
        self.video_stream = None
        self.audio_stream = None

        # Reset scrubber for new file
        self.scrubber.setValue(0)
        self.time_label.setText("0:00")
        self.last_known_current_time = 0
        self.last_time_current_time = None

        # Wait for metadata to be ready
        threading.Thread(target=self._load_file_data, args=(index, fmd), daemon=True).start()

    def _load_file_data(self, index, fmd):
        """Load file data in background"""
        fmd.wait()

        # Update UI on main thread via signal (thread-safe)
        self.file_ui_ready.emit(index, fmd)

    def _update_file_ui(self, index, fmd):
        """Update UI with file data (must be called on main thread)"""
        # Load thumbnail
        if fmd.thumbnail_fn and os.path.isfile(fmd.thumbnail_fn):
            pixmap = QPixmap(fmd.thumbnail_fn)
            scaled = pixmap.scaled(
                self.thumbnail_label.width(), 300,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.thumbnail_label.setPixmap(scaled)

        # Populate audio/video streams
        self.audio_combo.clear()
        if fmd.video_streams and fmd.audio_streams:
            self.video_stream = fmd.video_streams[0]
            self.audio_stream = fmd.audio_streams[0]
            print(f"{self.video_stream.title} - {self.audio_stream.title}",
                  self.video_stream, self.audio_stream)
            for video in fmd.video_streams:
                for audio in fmd.audio_streams:
                    self.audio_combo.addItem(
                        f"{video.title} - {audio.details()}",
                        (video, audio)
                    )

        # Populate subtitles
        self.subtitle_combo.clear()
        self.subtitle_combo.addItem("No subtitles", None)
        for sub in fmd.subtitles:
            self.subtitle_combo.addItem(sub.title, sub)
        self.subtitle_combo.addItem("Add subtitle file...", "browse")

        # Create transcoder if we have a cast selected
        if self.cast and self.video_stream:
            self._create_transcoder(index, fmd)

        self.update_button_states()

    def _create_transcoder(self, index, fmd):
        """Create transcoder for the file"""
        with self.transcoder_lock:
            fn, _, old_transcoder, duration = self.files_data[index]

            # Don't create a new transcoder if one already exists and is working
            if old_transcoder and not old_transcoder.destroyed:
                return

            transcoder = Transcoder(
                self.cast,
                fmd,
                self.video_stream,
                self.audio_stream,
                old_transcoder
            )

            # Connect signals
            transcoder.progress_updated.connect(
                lambda bytes, secs: self._on_transcode_progress(index, bytes, secs, duration)
            )
            transcoder.transcode_completed.connect(
                lambda: self._on_transcode_complete(index)
            )
            transcoder.transcode_error.connect(self.on_transcode_error)

            self.files_data[index] = (fn, fmd, transcoder, duration)
            if fn == self.current_file:
                self.current_transcoder = transcoder

    def _create_transcoder_for_file(self, index, fmd):
        """Create transcoder for a queued file using its own streams"""
        with self.transcoder_lock:
            fn, _, old_transcoder, duration = self.files_data[index]

            # Don't create a new transcoder if one already exists and is working
            if old_transcoder and not old_transcoder.destroyed:
                return

            # Use the file's own streams
            video_stream = fmd.video_streams[0] if fmd.video_streams else None
            audio_stream = fmd.audio_streams[0] if fmd.audio_streams else None

            if not video_stream:
                return

            transcoder = Transcoder(
                self.cast,
                fmd,
                video_stream,
                audio_stream,
                old_transcoder
            )

            # Connect signals
            transcoder.progress_updated.connect(
                lambda bytes, secs: self._on_transcode_progress(index, bytes, secs, duration)
            )
            transcoder.transcode_completed.connect(
                lambda: self._on_transcode_complete(index)
            )
            transcoder.transcode_error.connect(self.on_transcode_error)

            self.files_data[index] = (fn, fmd, transcoder, duration)
            if fn == self.current_file:
                self.current_transcoder = transcoder

    def _on_transcode_progress(self, index, bytes, seconds, duration):
        """Update transcode progress"""
        if duration and duration > 0:
            progress = int((seconds / duration) * 100)
            widget = self.file_table.cellWidget(index, 2)
            if widget:
                widget.setValue(min(progress, 100))

    def _on_transcode_complete(self, index):
        """Handle transcode completion"""
        widget = self.file_table.cellWidget(index, 2)
        if widget:
            widget.setValue(100)
        # Pre-transcode the next file in queue
        self.prep_next_transcode()

    def on_transcode_error(self, error_msg):
        """Handle transcode error"""
        QMessageBox.critical(self, "Transcoding Error", error_msg[:500])

    def on_audio_changed(self, index):
        """Handle audio track change"""
        data = self.audio_combo.itemData(index)
        if data:
            self.video_stream, self.audio_stream = data
            # Recreate transcoder with new streams (only if cast is selected)
            if self.cast:
                for i, (fn, fmd, _, duration) in enumerate(self.files_data):
                    if fn == self.current_file:
                        self._create_transcoder(i, fmd)
                        break

    def on_subtitle_changed(self, index):
        """Handle subtitle change"""
        data = self.subtitle_combo.itemData(index)
        if data == "browse":
            # Browse for subtitle file
            fn, _ = QFileDialog.getOpenFileName(
                self,
                "Select subtitle file",
                os.path.dirname(self.current_file) if self.current_file else "",
                "Subtitle files (*.srt *.vtt);;All files (*.*)"
            )
            if fn:
                self.subtitles = convert_subtitles_to_webvtt(Path(fn))
        elif data:
            self.subtitles = data._subtitles if hasattr(data, '_subtitles') else None
        else:
            self.subtitles = None

    def show_file_info(self):
        """Show file information dialog"""
        if not self.current_file:
            return

        info_text = f"File: {os.path.basename(self.current_file)}\n"
        for fn, fmd, _, _ in self.files_data:
            if fn == self.current_file:
                fmd.wait()
                if fmd.video_streams:
                    info_text += "Video: " + ", ".join(f"{s.title} ({s.codec})" for s in fmd.video_streams) + "\n"
                if fmd.audio_streams:
                    info_text += "Audio: " + ", ".join(s.details() for s in fmd.audio_streams) + "\n"
                if fmd.subtitles:
                    info_text += "Subtitles: " + ", ".join(s.title for s in fmd.subtitles) + "\n"
                break

        if self.cast:
            info_text += f"\nDevice: {self.cast.cast_info.model_name} ({self.cast.cast_info.manufacturer})"

        QMessageBox.information(self, "File Info", info_text)

    def toggle_play(self):
        """Toggle play/pause"""
        if not self.cast or not self.current_transcoder:
            return

        mc = self.cast.media_controller
        if mc.status.player_state == "PLAYING":
            mc.pause()
        elif mc.status.player_state == "PAUSED":
            mc.play()
        else:
            # Start playback
            self.play_current_file()

    def play_current_file(self):
        """Start playing the current file"""
        if not self.cast or not self.current_file or not self.current_transcoder:
            return

        self.cast.wait()
        mc = self.cast.media_controller

        kwargs = {}
        if self.subtitles:
            kwargs["subtitles"] = self.webserver.get_subtitles_url()

        current_time = self.scrubber.value()
        if current_time:
            kwargs["current_time"] = current_time

        # Add thumbnail
        thumb_path = self.get_current_thumbnail()
        if thumb_path:
            kwargs["thumb"] = self.webserver.get_thumbnail_url()

        # Parse filename for metadata
        metadata = parse_tv_filename(self.current_file)
        if not metadata:
            metadata = parse_movie_filename(self.current_file)

        if metadata:
            # Add thumbnail to metadata images
            if thumb_path:
                metadata["images"] = [{"url": self.webserver.get_thumbnail_url()}]
            kwargs["metadata"] = metadata

            # Build display title
            if metadata.get("metadataType") == 2:  # TV Show
                title = f"{metadata.get('seriesTitle', '')} S{metadata.get('season', 0):02d}E{metadata.get('episode', 0):02d}"
                if metadata.get("title"):
                    title += f" - {metadata['title']}"
                kwargs["title"] = title
            elif metadata.get("metadataType") == 1:  # Movie
                kwargs["title"] = metadata.get("title", os.path.basename(self.current_file))

            print(f"Chromecast metadata: {metadata}")
        else:
            # Fallback to filename
            kwargs["title"] = os.path.basename(self.current_file)

        ext = self.current_file.split(".")[-1].lower()
        mc.play_media(
            f"{self.webserver.get_media_base_url()}/{hash(self.current_file)}.{ext}",
            "audio/%s" % ext if ext in AUDIO_EXTS else "video/mp4",
            **kwargs,
        )

    def stop(self):
        """Stop playback"""
        if self.cast:
            self.cast.media_controller.stop()

    def rewind(self):
        """Rewind 10 seconds"""
        self.seek_delta(-10)

    def forward(self):
        """Forward 30 seconds"""
        self.seek_delta(30)

    def seek_delta(self, delta):
        """Seek by delta seconds"""
        if not self.cast:
            return
        mc = self.cast.media_controller
        new_time = mc.status.current_time + delta
        self.scrubber.setValue(int(new_time))
        self.seeking = True
        mc.seek(new_time)

    def on_scrubber_pressed(self):
        """Handle scrubber press"""
        self.seeking = True

    def on_scrubber_moved(self, value):
        """Handle scrubber movement"""
        self.time_label.setText(humanize_seconds(value))

    def on_scrubber_released(self):
        """Handle scrubber release"""
        if self.cast:
            self.cast.media_controller.seek(self.scrubber.value())
            self.seeking = False

    def monitor_cast_status(self):
        """Monitor Chromecast status and update UI"""
        if not self.cast:
            return

        mc = self.cast.media_controller

        # Update player state
        if mc.status.player_state != self.last_known_player_state:
            old_state = self.last_known_player_state
            self.last_known_player_state = mc.status.player_state
            self.update_button_states()

            if mc.status.player_state == "PLAYING":
                self.screen_saver_inhibitor.start()
            else:
                self.screen_saver_inhibitor.stop()

            # Check for next file when playback finishes
            if old_state == "PLAYING" and mc.status.player_state == "IDLE":
                self.check_for_next_in_queue()

        # Pre-transcode next file while playing
        if mc.status.player_state == "PLAYING":
            self.prep_next_transcode()

        # Update scrubber position
        if not self.seeking and mc.status.player_state == "PLAYING":
            if mc.status.current_time != self.last_known_current_time:
                self.last_known_current_time = mc.status.current_time
                self.last_time_current_time = time.time()

            if self.last_time_current_time:
                elapsed = time.time() - self.last_time_current_time
                current = int(self.last_known_current_time + elapsed)
                self.scrubber.setValue(current)
                self.time_label.setText(humanize_seconds(current))

    def check_for_next_in_queue(self):
        """When current file finishes, auto-play the next one in queue"""
        if not self.cast or not self.current_file:
            return

        next_file = False
        for i, (fn, fmd, transcoder, duration) in enumerate(self.files_data):
            if next_file and fmd.ready:
                print(f"Auto-playing next in queue: {os.path.basename(fn)}")
                self.select_file(i)
                # Auto-start playback after a short delay
                QTimer.singleShot(500, self.toggle_play)
                return
            if fn == self.current_file:
                next_file = True

    def prep_next_transcode(self):
        """Pre-transcode the next file in queue while current is playing"""
        if not self.cast or not self.current_file:
            return

        transcode_next = False
        for i, (fn, fmd, transcoder, duration) in enumerate(self.files_data):
            if transcode_next and not transcoder and fmd.ready:
                print(f"Pre-transcoding next file: {os.path.basename(fn)}")
                # Use the file's own streams, not the current file's streams
                self._create_transcoder_for_file(i, fmd)
                return
            # Start pre-transcoding after current file's transcoder is done
            if fn == self.current_file and transcoder and transcoder.done:
                transcode_next = True

    def update_button_states(self):
        """Update button enabled states"""
        has_cast = self.cast is not None
        has_file = self.current_file is not None and self.current_transcoder is not None
        playing = has_cast and self.cast.media_controller.status.player_state in ("PLAYING", "PAUSED", "BUFFERING")

        self.play_button.setEnabled(has_cast and has_file)
        self.stop_button.setEnabled(playing)
        self.rewind_button.setEnabled(playing)
        self.forward_button.setEnabled(playing)
        self.scrubber.setEnabled(has_file)

        if has_cast and self.cast.media_controller.status.player_state == "PLAYING":
            self.play_button.setText("⏸")
        else:
            self.play_button.setText("▶")

        if self.current_duration:
            self.scrubber.setMaximum(int(self.current_duration))

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Handle drag enter event"""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        """Handle drop event"""
        for url in event.mimeData().urls():
            fn = url.toLocalFile()
            if os.path.isfile(fn):
                self.queue_file(fn)

    def closeEvent(self, event):
        """Handle window close"""
        self.screen_saver_inhibitor.stop()
        # Clean up transcoders
        for _, _, transcoder, _ in self.files_data:
            if transcoder:
                transcoder.destroy()
        event.accept()


def main():
    """Main entry point"""
    import argparse

    if not DEPS_MET:
        print("ERROR: Missing dependencies. Install with:")
        print("  pip install pychromecast PyQt6 bottle paste pycaption")
        sys.exit(1)

    parser = argparse.ArgumentParser(description='QtCast - Cast media to Chromecast')
    parser.add_argument('files', nargs='*', help='Media files to add to queue')
    parser.add_argument('-d', '--device', help='Chromecast device name')
    parser.add_argument('-s', '--subtitles', help='Subtitle file (.srt)')
    args = parser.parse_args()

    app = QApplication(sys.argv)
    app.setApplicationName("QtCast")
    app.setOrganizationName("QtCast")

    window = QtCastWindow()

    # Add files from command line
    if args.files:
        for fn in args.files:
            if os.path.isfile(fn):
                window.queue_file(os.path.abspath(fn))

    window.show()

    sys.exit(app.exec())


if __name__ == '__main__':
    main()
