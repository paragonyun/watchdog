import platform
import subprocess

from .base import Notifier


class WindowsNotifier(Notifier):
    def notify(self, message: str) -> None:
        if platform.system() != "Windows":
            print(message)
            return
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "Add-Type -AssemblyName System.Windows.Forms; "
                "[System.Windows.Forms.MessageBox]::Show($args[0], 'Portfolio Watchdog')",
                message,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
