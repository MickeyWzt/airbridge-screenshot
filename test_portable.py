"""Probe an already-running isolated portable app, restoring the real clipboard."""
import argparse
import io
import time
from pathlib import Path
import urllib.error
import urllib.request

from PySide6.QtCore import QBuffer, QIODevice, QMimeData
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18769)
    parser.add_argument('--data-dir', type=Path, required=True)
    args = parser.parse_args()
    app = QApplication([])
    clipboard = app.clipboard()
    backup = QMimeData()
    original = clipboard.mimeData()
    if original:
        for fmt in original.formats():
            backup.setData(fmt, original.data(fmt))
    token = (args.data_dir / 'token.txt').read_text(encoding='ascii').strip()
    base = f'http://127.0.0.1:{args.port}'
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    image = QImage(37, 23, QImage.Format.Format_RGB32)
    image.fill(QColor('#28a399'))
    image.setPixelColor(4, 5, QColor('#fd8431'))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, 'PNG')
    raw = bytes(buffer.data())
    try:
        with client.open(base + '/health', timeout=3) as response:
            assert response.status == 200 and b'"ready": true' in response.read()
        # The HTTP listener starts before Qt finishes building the pairing
        # window. Wait for its configuration, rather than testing that race.
        deadline = time.monotonic() + 5
        while True:
            with client.open(base + '/setup/' + token, timeout=3) as response:
                page = response.read().decode()
            if '添加截图快捷指令' in page or time.monotonic() >= deadline:
                break
            time.sleep(0.05)
        assert 'http://' in page and '/clip/' + token in page
        assert '添加截图快捷指令' in page and 'SETUP_URL' in page
        assert 'https://www.icloud.com/shortcuts/' in page
        assert '模板还在准备中' not in page
        try:
            client.open(urllib.request.Request(base + '/clip/wrong', data=raw), timeout=3)
            raise AssertionError('Bad pairing secret accepted')
        except urllib.error.HTTPError as error:
            assert error.code == 403
        with client.open(urllib.request.Request(base + '/clip/' + token, data=raw,
                        headers={'Content-Type': 'image/png'}), timeout=12) as response:
            assert response.status == 200 and b'Copied to Windows clipboard' in response.read()
        # Windows DIB transfer between processes can change QImage's storage
        # format. Compare normalized RGBA pixels, allowing clipboard events to arrive.
        expected = image.convertToFormat(QImage.Format.Format_RGBA8888)
        actual = QImage()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            app.processEvents()
            actual = clipboard.image().convertToFormat(QImage.Format.Format_RGBA8888)
            if actual == expected:
                break
            time.sleep(0.02)
        assert actual == expected, f'Portable clipboard pixels differ ({actual.width()} x {actual.height()})'
        assert (args.data_dir / 'paired.txt').exists(), 'First-use completion not saved'
        print('PASS: portable EXE health + setup; pairing enforced; HTTP POST 200; Windows clipboard exact pixels; first screenshot completes onboarding')
    finally:
        clipboard.setMimeData(backup)
        app.processEvents()


if __name__ == '__main__':
    main()
