"""Check new pairing flow over HTTP, QR decoding, and network-change UI refresh."""
import io
from pathlib import Path
import tempfile
import threading
import urllib.error
import urllib.request

from PySide6.QtWidgets import QApplication

import receiver
from app import SetupWindow, qr_pixmap
from pairing_web import setup_page, shortcut_link


class Advertisement:
    def __init__(self, *args):
        pass

    def close(self):
        pass


def main():
    app = QApplication([])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with tempfile.TemporaryDirectory(prefix='airbridge-onboarding-test-') as folder:
        previous = receiver.DATA_DIR
        receiver.DATA_DIR = Path(folder)
        server = receiver.ReceiverServer(('127.0.0.1', 0), 'test-pairing-secret')
        network = receiver.NetworkBinding(server, 'test-device.local', advertiser=Advertisement)
        window = SetupWindow(server, network)
        try:
            network.switch('127.0.0.1')
            window.refresh_connection()
            base = f'http://127.0.0.1:{network.port}'
            with opener.open(base + '/setup/test-pairing-secret', timeout=2) as response:
                page = response.read().decode()
                assert response.status == 200
                assert response.headers['Cache-Control'] == 'no-store'
                assert response.headers['Referrer-Policy'] == 'no-referrer'
                assert "connect-src 'self'" in response.headers['Content-Security-Policy']
                assert 'http://test-device.local:' in page
                assert '模板还在准备中' in page
                assert 'Request Body = File' in page
            for path in ('/setup/wrong', '/setup/', '/setup/test-pairing-secret?extra=1'):
                try:
                    opener.open(base + path, timeout=2)
                    raise AssertionError('Setup page accepted unpaired request')
                except urllib.error.HTTPError as error:
                    assert error.code == 404
            window.mode.setCurrentIndex(1)
            assert window.address.text().startswith(base + '/clip/')
            assert server.state.pairing['upload_url'] == window.address.text()
            network.switch('127.0.0.2')
            window.refresh_connection()
            assert '127.0.0.2' in window.address.text(), 'IP fallback did not refresh'
            assert network.server.state.pairing is server.state.pairing
            network.switch(None)
            window.refresh_connection()
            assert not window.address.text() and server.state.pairing == {}
            network.switch('127.0.0.1')
            window.refresh_connection()
            assert window.address.text(), 'UI did not recover after reconnection'
            window.received.emit()
            assert (Path(folder) / 'paired.txt').read_text().strip() == 'connected'
            assert '连接成功' in window.step.text()
            assert shortcut_link('https://evil.example/shortcuts/' + 'a' * 32) == ''
            assert shortcut_link('https://www.icloud.com/shortcuts/' + 'a' * 32)
            malicious = setup_page({'upload_url': '</textarea><script>alert(1)</script>'})
            assert '&lt;/textarea&gt;&lt;script&gt;' in malicious
            assert '</textarea><script>alert(1)</script>' not in malicious
            linked = setup_page({'shortcut_link': 'https://www.icloud.com/shortcuts/' + 'a' * 32})
            assert '添加截图快捷指令' in linked
            assert 'SETUP_URL' in linked and '唯一一块' in linked
            assert '模板的「电脑连接地址」' not in linked
            assert linked.index('id="copy"') < linked.index('添加截图快捷指令')
            window.shared_link = shortcut_link((Path(__file__).parent / 'shortcut-link.txt').read_text().strip())
            assert window.shared_link, 'Release is missing its shared template'
            window.signature = None
            window.refresh_connection()
            with opener.open(base + '/setup/test-pairing-secret', timeout=2) as response:
                shared_page = response.read().decode()
                assert window.shared_link in shared_page
                assert '模板还在准备中' not in shared_page
                assert 'SETUP_URL' in shared_page and '刚复制的完整连接地址' in shared_page
            assert not qr_pixmap(base + '/setup/test-pairing-secret').isNull()
            print('PASS: paired setup HTTP; restricted page; invalid secrets denied; IP/QR state follows rebind/offline; first screenshot completes onboarding; no fake import link; HTML escaping')
        finally:
            window.timer.stop()
            window.refresh_timer.stop()
            window.cache_timer.stop()
            window.tray.hide()
            window.preview.hide()
            window.hide()
            network.unpublish()
            if network.server:
                network.server.shutdown()
                network.server.server_close()
            receiver.DATA_DIR = previous


if __name__ == '__main__':
    main()
