"""Per-user startup and a narrowly scoped, user-invoked firewall helper."""
from pathlib import Path
import subprocess
import sys
import winreg

RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
RUN_NAME = 'AirBridgeScreenshotCommunity'


def resource_path(name):
    return Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / name


def launch_command():
    executable = Path(sys.executable)
    if getattr(sys, 'frozen', False):
        return [str(executable), '--background']
    windowed = executable.with_name('pythonw.exe')
    return [str(windowed if windowed.exists() else executable), str(Path(__file__).with_name('app.py')), '--background']


def startup_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_NAME)
            return value == subprocess.list2cmdline(launch_command())
    except FileNotFoundError:
        return False


def set_startup(enabled):
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(launch_command()))
        else:
            try:
                winreg.DeleteValue(key, RUN_NAME)
            except FileNotFoundError:
                pass


def request_firewall(port):
    script = resource_path('allow_lan.ps1')
    # Values are positional arguments, never interpolated into PowerShell code.
    args = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
            '-ProgramPath', launch_command()[0], '-Port', str(port)]
    subprocess.Popen(args, creationflags=subprocess.CREATE_NO_WINDOW)
