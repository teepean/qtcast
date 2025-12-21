"""
Transcoder for QtCast - handles media transcoding for Chromecast compatibility
"""
import os
import re
import subprocess
import tempfile
import threading
from PyQt6.QtCore import QObject, pyqtSignal

from .devices import get_device, Device
from .ffmpeg import parse_ffmpeg_time


AUDIO_EXTS = ("aac", "mp3", "wav")


class Transcoder(QObject):
    """Handles transcoding of media files for Chromecast compatibility"""

    # Signals for thread-safe communication
    progress_updated = pyqtSignal(int, int)  # progress_bytes, progress_seconds
    transcode_completed = pyqtSignal(bool)  # did_transcode
    transcode_error = pyqtSignal(str)  # error_message

    def __init__(
        self,
        cast,
        fmd,
        video_stream,
        audio_stream,
        prev_transcoder=None,
    ):
        super().__init__()
        self.fmd = fmd
        self.video_stream = video_stream
        self.audio_stream = audio_stream
        fn = fmd.fn
        self.cast = cast
        self.source_fn = fn
        self.p = None

        # Get device capabilities
        self.device = get_device(cast.cast_info.manufacturer, cast.model_name)

        if prev_transcoder:
            prev_transcoder.destroy()

        print("Transcoder", fn)
        transcode_container = fmd.container not in ("mp4", "aac", "mp3", "wav")
        self.transcode_video = not self.can_play_video_codec(video_stream.codec)
        # Only transcode audio if codec is not supported (container handled separately)
        self.transcode_audio = not self.can_play_audio_stream(self.audio_stream)
        self.transcode = (
            transcode_container or self.transcode_video or self.transcode_audio
        )
        self.trans_fn = None

        self.progress_bytes = 0
        self.progress_seconds = 0
        self.done = False
        self.destroyed = False

        print(
            "transcode, transcode_video, transcode_audio",
            self.transcode,
            self.transcode_video,
            self.transcode_audio,
        )

        if self.transcode:
            dir = "/var/tmp" if os.path.isdir("/var/tmp") else None
            self.trans_fn = tempfile.mkstemp(
                suffix=".mp4",
                prefix="qtcast_pid%i_transcode_" % os.getpid(),
                dir=dir,
            )[1]
            os.remove(self.trans_fn)

            transcode_audio_to = (
                "ac3"
                if self.device.ac3 and audio_stream and audio_stream.channels > 2
                else "mp3"
            )

            self.transcode_cmd = [
                "ffmpeg",
                "-i",
                self.source_fn,
                "-map",
                self.video_stream.index,
            ]
            if self.audio_stream:
                self.transcode_cmd += [
                    "-map",
                    self.audio_stream.index,
                    "-c:a",
                    transcode_audio_to if self.transcode_audio else "copy",
                ] + (["-b:a", "256k"] if self.transcode_audio else [])
            self.transcode_cmd += [
                "-c:v",
                "h264" if self.transcode_video else "copy",
            ]
            self.transcode_cmd += [self.trans_fn]
            print(" ".join(["'%s'" % s if " " in s else s for s in self.transcode_cmd]))
            print("---------------------")
            print(" starting ffmpeg at:")
            print("---------------------")
            self.p = subprocess.Popen(
                self.transcode_cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            # Start monitoring in a thread
            self.monitor_thread = threading.Thread(target=self.monitor, daemon=True)
            self.monitor_thread.start()
        else:
            self.done = True
            self.transcode_completed.emit(False)

    @property
    def fn(self):
        return self.trans_fn if self.transcode else self.source_fn

    def can_play_video_codec(self, video_codec):
        h265 = False if self.cast.cast_info.cast_type == "audio" else self.device.h265
        if h265:
            return video_codec in ("h264", "h265", "hevc")
        else:
            return video_codec in ("h264",)

    def can_play_audio_stream(self, stream):
        if not stream:
            return True
        if self.device.ac3:
            return stream.codec in ("aac", "mp3", "ac3")
        else:
            return stream.codec in ("aac", "mp3")

    def wait_for_byte(self, offset, buffer=128 * 1024 * 1024):
        if self.done:
            return
        import time
        if self.source_fn.lower().split(".")[-1] == "mp4":
            while offset > self.progress_bytes + buffer:
                print("waiting for", offset, "at", self.progress_bytes + buffer)
                time.sleep(2)
        else:
            while not self.done:
                print("waiting for transcode to finish")
                time.sleep(2)
        print("done waiting")

    def monitor(self):
        line = b""
        r = re.compile(r"=\s+")
        total_output = b""
        while self.p and not self.destroyed:
            byte = self.p.stdout.read(1)
            total_output += byte
            if byte == b"" and self.p.poll() is not None:
                break
            if byte != b"":
                line += byte
                if byte == b"\r":
                    line = line.decode()
                    line = r.sub("=", line)
                    items = [s.split("=") for s in line.split()]
                    d = dict([x for x in items if len(x) == 2])
                    print(d)
                    self.progress_bytes = (
                        int(d.get("size", "0kb").lower().rstrip("kib")) * 1024
                    )
                    self.progress_seconds = parse_ffmpeg_time(d.get("time", "00:00:00"))
                    # Emit signal for UI update
                    self.progress_updated.emit(self.progress_bytes, self.progress_seconds)
                    line = b""
        if self.p:
            self.p.stdout.close()
            # Don't report error if transcoder was explicitly destroyed (replaced)
            if self.p.returncode and not self.destroyed:
                print("--== transcode error ==--")
                print(total_output)
                self.transcode_error.emit(total_output.decode())
                return
        if not self.destroyed:
            self.done = True
            self.transcode_completed.emit(True)

    def destroy(self):
        self.destroyed = True
        if self.p and self.p.poll() is None:
            self.p.terminate()
        if self.trans_fn and os.path.isfile(self.trans_fn):
            os.remove(self.trans_fn)

    def __del__(self):
        self.destroy()
