"""Exercise HTTP handling and the real Qt/Windows clipboard with synthetic pixels."""
import threading
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.request
from PySide6.QtCore import QBuffer, QIODevice, QMimeData
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QLabel, QSystemTrayIcon
from receiver import ReceiverServer, Window, drag_payload, clean_drag_cache, CACHE_RETENTION_SECONDS


def main():
    app = QApplication([])
    clipboard = app.clipboard()
    backup = QMimeData()
    original = clipboard.mimeData()
    if original:
        for fmt in original.formats():
            backup.setData(fmt, original.data(fmt))
    server = ReceiverServer(('127.0.0.1', 0), 'test-token')
    window = Window(server, 'test-only')
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    base = f'http://127.0.0.1:{server.server_port}'
    test_image = QImage(37, 23, QImage.Format.Format_RGB32)
    test_image.fill(QColor('#28a399'))
    test_image.setPixelColor(4, 5, QColor('#fd8431'))
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    test_image.save(buffer, 'PNG')
    raw = bytes(buffer.data())

    def settle(milliseconds):
        deadline = time.monotonic() + milliseconds / 1000
        while time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)

    def request(path='/clip/test-token', payload=raw, headers=None):
        result = []
        def worker():
            try:
                with client.open(urllib.request.Request(base + path, data=payload,
                        headers=headers or {}, method='POST'), timeout=12) as response:
                    result.append(response.status)
            except urllib.error.HTTPError as exc:
                result.append(exc.code)
            except Exception as exc:
                result.append(exc)
        thread = threading.Thread(target=worker)
        thread.start()
        deadline = time.monotonic() + 15
        while thread.is_alive() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert result, 'Request did not complete'
        return result[0]

    try:
        for reason in (QSystemTrayIcon.ActivationReason.Trigger,
                       QSystemTrayIcon.ActivationReason.DoubleClick):
            window.hide()
            window.tray.activated.emit(reason)
            settle(100)
            assert window.isVisible() and not window.isMinimized(), 'Tray click did not restore window'
        window.showMinimized()
        window.tray.contextMenu().actions()[0].trigger()
        settle(100)
        assert window.isVisible() and not window.isMinimized(), 'Tray menu did not restore window'
        window.hide()
        assert request('/clip/wrong') == 403
        assert request(payload=b'not an image') == 400
        assert request(payload=b'x', headers={'Content-Length': str(26 * 1024 * 1024)}) == 413
        assert request() == 200
        assert clipboard.image() == test_image, 'Actual clipboard pixel roundtrip failed'
        assert window.preview.isVisible(), 'Successful receipt did not show preview'
        assert not window.preview.thumbnail.pixmap().isNull(), 'Preview has no image'
        assert app.primaryScreen().availableGeometry().contains(window.preview.geometry()), 'Preview extends outside usable screen'
        settle(350)
        assert abs(window.preview.reveal.amount - 1.0) < 0.001
        with tempfile.TemporaryDirectory(prefix='airbridge-drag-test-') as folder:
            mime = drag_payload(test_image, folder)
            assert mime.hasUrls() and mime.hasImage() and mime.hasFormat('image/png')
            assert QImage(mime.urls()[0].toLocalFile()) == test_image, 'Dragged file changed pixels'
            assert QImage.fromData(mime.data('image/png')) == test_image, 'Dragged PNG data changed pixels'
            root = Path(folder)
            old = root / 'Screenshot-20260901-120000-1234abcd.png'
            old.write_bytes(raw)
            unrelated = root / 'my-photo.png'
            unrelated.write_bytes(raw)
            nested = root / 'nested'
            nested.mkdir()
            nested_file = nested / old.name
            nested_file.write_bytes(raw)
            now = time.time()
            expired = now - CACHE_RETENTION_SECONDS - 1
            for path in (old, unrelated, nested_file):
                os.utime(path, (expired, expired))
            clean_drag_cache(root, now)
            assert not old.exists(), 'Expired generated cache was not cleaned'
            assert Path(mime.urls()[0].toLocalFile()).exists(), 'Fresh drag cache was removed'
            assert unrelated.exists() and nested_file.exists(), 'Cleanup touched unrelated files'
        portrait = QImage(1311, 1888, QImage.Format.Format_RGB32)
        portrait.fill(QColor('#28a399'))
        window.preview.show_image(portrait)
        settle(350)
        assert window.preview.width() == window.preview.thumbnail.pixmap().width() + 28, 'Portrait preview has excess side space'
        assert window.preview.thumbnail.width() == window.preview.thumbnail.pixmap().width()
        assert not any('Ctrl+V' in label.text() for label in window.preview.findChildren(QLabel)), 'Footer still present'
        # A new receipt during an exit animation must reverse the exit, not disappear.
        window.preview.dismiss()
        settle(50)
        assert request() == 200
        settle(350)
        assert window.preview.isVisible() and window.preview.reveal.amount == 1.0
        window.preview.dismiss()
        settle(220)
        assert not window.preview.isVisible(), 'Dismiss animation did not hide preview'
        assert request(payload=b'not an image') == 400
        assert clipboard.image() == test_image, 'Rejected upload altered clipboard'
        window.toggle_pause()
        assert request() == 503
        window.toggle_pause()
        assert request() == 200
        print('PASS: tray single/double click and menu restoration; HTTP + clipboard; compact preview; animation; drag pixels; cache cleanup; pause/resume')
    finally:
        window.timer.stop()
        window.cache_timer.stop()
        window.preview.hide()
        window.tray.hide()
        clipboard.setMimeData(backup)
        app.processEvents()
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
