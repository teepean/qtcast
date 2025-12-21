"""Screen saver inhibitor for Qt Cast"""
import subprocess


class ScreenSaverInhibitor:
    """Prevents screen saver activation during playback"""

    def __init__(self):
        self.cookie = None
        self.running = False

    def start(self):
        """Start inhibiting screen saver"""
        if self.running:
            return
        self.running = True

        # Try to inhibit using systemd-inhibit or similar
        try:
            # This is a simple implementation - could be enhanced
            subprocess.Popen([
                'systemd-inhibit',
                '--what=idle',
                '--who=QtCast',
                '--why=Playing media',
                'sleep', 'infinity'
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (FileNotFoundError, subprocess.SubprocessError):
            # systemd-inhibit not available, that's ok
            pass

    def stop(self):
        """Stop inhibiting screen saver"""
        self.running = False
        # The subprocess will be killed when the app exits
