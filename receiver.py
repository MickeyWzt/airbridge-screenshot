"""Local-network screenshot receiver. Run with the existing PySide6 runtime."""
import argparse
import ctypes
import hmac
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import re
import secrets
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

from PySide6.QtCore import (QBuffer, QByteArray, QEasingCurve, QIODevice, QLockFile, QMimeData, QObject, Signal,
    QPoint, QPointF, QPropertyAnimation, Property, Qt, QTimer, QUrl)
from PySide6.QtGui import QDrag, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (QApplication, QLabel, QLineEdit, QMainWindow,
    QGraphicsEffect, QHBoxLayout, QMenu, QMessageBox, QPushButton, QStyle, QSystemTrayIcon,
    QVBoxLayout, QWidget)
from zeroconf import IPVersion, ServiceInfo, Zeroconf
from directory_client import load_publisher

MAX_BYTES = 25 * 1024 * 1024
MAX_PIXELS = 40_000_000
# AppData is virtualized when launched by packaged Codex, but not at Windows
# login. Both launch contexts must share credentials, configuration and lock.
DATA_DIR = Path.home() / '.airbridge-screenshot-community'
CACHE_RETENTION_SECONDS = 24 * 60 * 60
EVENTS = logging.getLogger('screenshot_receiver')
EVENTS.addHandler(logging.NullHandler())


def clean_drag_cache(directory=None, now=None):
    """Delete only our expired regular PNGs, never links or nested files."""
    directory = Path(directory) if directory is not None else DATA_DIR / 'DragCache'
    if directory.is_symlink() or directory.is_junction():
        return
    root = directory.resolve()
    cutoff = (time.time() if now is None else now) - CACHE_RETENTION_SECONDS
    try:
        paths = list(root.iterdir())
    except OSError:
        return
    for path in paths:
        if not re.fullmatch(r'Screenshot-\d{8}-\d{6}-[0-9a-f]{8}\.png', path.name):
            continue
        try:
            if (not path.is_symlink() and not path.is_junction() and path.is_file()
                    and path.resolve().parent == root and path.stat().st_mtime <= cutoff):
                path.unlink()
        except OSError:
            pass  # Locked files are retried on the next sweep.


def local_address():
    command = ('Get-NetIPConfiguration | Where-Object {$_.NetAdapter.HardwareInterface '
               '-and $_.IPv4DefaultGateway} | ForEach-Object {$_.IPv4Address.IPAddress}')
    result = subprocess.check_output(
        ['powershell.exe', '-NoProfile', '-Command', command],
        creationflags=subprocess.CREATE_NO_WINDOW, timeout=15, text=True)
    addresses = [s.strip() for s in result.splitlines() if s.strip()]
    if not addresses:
        raise RuntimeError('没有找到连接中的 Wi-Fi / 以太网，请先连接网络。')
    return addresses[0]


def load_token():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / 'token.txt'
    if not path.exists():
        path.write_text(secrets.token_hex(16), encoding='ascii')
    return path.read_text(encoding='ascii').strip()


def load_device_name():
    path = DATA_DIR / 'device-name.txt'
    if not path.exists():
        path.write_text(f'airbridge-{secrets.token_hex(3)}.local', encoding='ascii')
    return path.read_text(encoding='ascii').strip()


def decode_image(raw):
    buffer = QBuffer()
    buffer.setData(QByteArray(raw))
    buffer.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > MAX_PIXELS:
        raise ValueError('Invalid image dimensions')
    image = reader.read()
    if image.isNull():
        raise ValueError('Unsupported or incomplete image; send PNG')
    return image


class ReceiverServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, token, state=None):
        super().__init__(address, Handler)
        self.token = token
        self.state = state or SimpleNamespace(pending=queue.Queue(maxsize=4), accepting=True)

    @property
    def pending(self):
        return self.state.pending

    @property
    def accepting(self):
        return self.state.accepting

    @accepting.setter
    def accepting(self, value):
        self.state.accepting = value


class LocalAdvertisement:
    def __init__(self, host, port, name):
        self.zc = Zeroconf(interfaces=[host], ip_version=IPVersion.V4Only)
        self.info = ServiceInfo('_http._tcp.local.',
            f'{name.removesuffix(".local")}._http._tcp.local.',
            parsed_addresses=[host], port=port, server=name + '.',
            properties={'service': 'screenshot'}, host_ttl=30, other_ttl=30)
        try:
            self.zc.register_service(self.info)
        except Exception:
            self.zc.close()
            raise

    def close(self):
        try:
            self.zc.unregister_service(self.info)
        finally:
            self.zc.close()


class NetworkBinding(QObject):
    changed = Signal(str)

    def __init__(self, server, name, address_source=local_address,
                 advertiser=LocalAdvertisement, config_path=None, clock=time.time, publisher=None):
        super().__init__()
        self.server = server
        self.state = server.state
        self.token = server.token
        self.port = server.server_port
        self.host = server.server_address[0]
        self.name = name
        self.address_source = address_source
        self.advertiser = advertiser
        self.advertisement = None
        self.publisher = publisher
        self.clock = clock
        self.advertised_at = 0
        self.config_path = config_path
        self.last_config = None
        self.stop_event = threading.Event()
        self.worker = None
        threading.Thread(target=server.serve_forever, daemon=True).start()

    def unpublish(self):
        if self.advertisement is not None:
            try:
                self.advertisement.close()
            except Exception:
                EVENTS.warning('Discovery cleanup failed after network change')
            self.advertisement = None

    def switch(self, host):
        """Rebind only to the selected physical interface; retain clipboard queue/pause."""
        if host != self.host:
            replacement = ReceiverServer((host, self.port), self.token, self.state) if host else None
            self.unpublish()
            if self.server:
                self.server.shutdown()
                self.server.server_close()
            self.server, self.host = replacement, host
            if replacement:
                threading.Thread(target=replacement.serve_forever, daemon=True).start()
            EVENTS.info('Network binding changed; connected=%s', bool(host))
        # Wi-Fi reconnects and resume can invalidate multicast sockets while
        # preserving the same IP. Rejoin periodically instead of trusting it forever.
        age = self.clock() - self.advertised_at
        if self.advertisement is not None and (age >= 60 or age < 0):
            self.unpublish()
            EVENTS.info('Refreshing local discovery on current network')
        if host and self.advertisement is None and self.publisher is None and self.advertiser is not None:
            try:
                self.advertisement = self.advertiser(host, self.port, self.name)
                self.advertised_at = self.clock()
            except Exception:
                EVENTS.warning('Local discovery unavailable; retrying automatically')
        if self.config_path:
            payload = {'url': self.publisher.lookup_url if self.publisher else f'http://{self.name}:{self.port}/clip/{self.token}',
                       'mode': 'directory' if self.publisher else 'mdns',
                       'hostname': self.name, 'host': host, 'port': self.port}
            if payload != self.last_config:
                temp = self.config_path.with_suffix('.tmp')
                temp.write_text(json.dumps(payload, indent=2), encoding='utf-8')
                temp.replace(self.config_path)
                self.last_config = payload
        published = self.publisher.update(host, self.port) if self.publisher else False
        if not host:
            self.changed.emit('等待 Wi-Fi / 以太网连接，连上后自动恢复…')
        elif self.publisher:
            self.changed.emit('最新地址已同步；图片仍在局域网直接传输。' if published
                              else '地址更新暂未成功，正在自动重试；IP 直连仍可使用。')
        elif self.advertisement:
            self.changed.emit('固定设备地址已启用，换网后自动更新连接。')
        elif self.advertiser is None:
            self.changed.emit('本地测试模式；仅接受此电脑的连接。')
        else:
            self.changed.emit('当前可通过 IP 接收；固定设备名称正在重试…')

    def run(self):
        try:
            try:
                self.switch(self.host)
            except Exception:
                EVENTS.warning('Initial discovery setup failed; retrying automatically')
            while not self.stop_event.wait(10):
                try:
                    host = self.address_source()
                except Exception:
                    host = None
                try:
                    self.switch(host)
                except Exception:
                    EVENTS.warning('Network reconnect failed; retrying automatically')
        finally:
            self.unpublish()
            if self.server:
                self.server.shutdown()
                self.server.server_close()

    def start(self):
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def close(self):
        self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=25)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # Never log pairing tokens or image content.

    def reply(self, status, payload):
        EVENTS.info('method=%s status=%s result=%s', self.command, status,
                    payload.get('error') or payload.get('message') or 'health')
        raw = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == '/health':
            self.reply(200, {'service': 'Screenshot to PC', 'ready': self.server.accepting})
        elif hmac.compare_digest(self.path, '/setup/' + self.server.token):
            from pairing_web import setup_page
            raw = setup_page(getattr(self.server.state, 'pairing', {})).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.reply(404, {'error': 'Not found'})

    def do_POST(self):
        self.connection.settimeout(15)
        if not hmac.compare_digest(self.path, '/clip/' + self.server.token):
            self.reply(403, {'error': 'Invalid pairing address'})
            return
        if not self.server.accepting:
            self.reply(503, {'error': 'Receiver paused'})
            return
        if self.headers.get('Transfer-Encoding'):
            self.reply(400, {'error': 'Send a file with Content-Length'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if not 0 < length <= MAX_BYTES:
            self.reply(413, {'error': 'Image must be 1 byte to 25 MB'})
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError('Incomplete upload')
            image = decode_image(raw)
        except (ValueError, OSError) as exc:
            self.reply(400, {'error': str(exc)})
            return
        task = {'image': image, 'done': threading.Event(), 'cancelled': False,
                'lock': threading.Lock(), 'ok': False}
        try:
            self.server.pending.put_nowait(task)
        except queue.Full:
            self.reply(429, {'error': 'Receiver busy; retry'})
            return
        if not task['done'].wait(10):
            with task['lock']:
                if not task['done'].is_set():
                    task['cancelled'] = True
                    self.reply(504, {'error': 'Clipboard timeout'})
                    return
        self.reply(200 if task['ok'] else 503,
                   {'ok': task['ok'], 'message': task.get('message', 'Clipboard unavailable')})


def animations_enabled():
    """Respect Windows' client-area animation preference (read only)."""
    enabled = ctypes.c_int(1)
    if sys.platform == 'win32':
        ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0)
    return bool(enabled.value)


class CornerReveal(QGraphicsEffect):
    """Paint a small scale + fade from bottom right without relaying out children."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._amount = 1.0
        self.motion_enabled = animations_enabled()

    def get_amount(self):
        return self._amount

    def set_amount(self, value):
        self._amount = float(value)
        self.update()

    amount = Property(float, get_amount, set_amount)

    def draw(self, painter):
        bounds = self.sourceBoundingRect()
        scale = 0.94 + 0.06 * self._amount if self.motion_enabled else 1.0
        painter.save()
        painter.setOpacity(self._amount)
        painter.translate(bounds.right(), bounds.bottom())
        painter.scale(scale, scale)
        painter.translate(-bounds.right(), -bounds.bottom())
        self.drawSource(painter)
        painter.restore()


def drag_payload(image, directory=None):
    """Keep the PNG available after drop: other apps may read it asynchronously."""
    directory = Path(directory) if directory is not None else DATA_DIR / 'DragCache'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f'Screenshot-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.png'
    if not image.save(str(path), 'PNG'):
        raise OSError('Could not prepare PNG for dragging')
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path.resolve()))])
    mime.setImageData(image)
    mime.setData('image/png', QByteArray(path.read_bytes()))
    return mime


class DraggableThumbnail(QLabel):
    def __init__(self, preview):
        super().__init__(preview)
        self.preview = preview
        self.press_position = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip('按住图片，拖到聊天窗口、文档或文件夹')
        self.setAccessibleName('截图预览，可拖动到其他应用')

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (event.buttons() & Qt.MouseButton.LeftButton and self.press_position is not None
                and (event.position().toPoint() - self.press_position).manhattanLength()
                >= QApplication.startDragDistance()):
            self.press_position = None
            self.preview.begin_drag()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.press_position = None
        super().mouseReleaseEvent(event)


class ScreenshotPreview(QWidget):
    """A non-activating thumbnail above the primary screen's taskbar."""
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('收到截图 · AirBridge Preview')
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_QuitOnClose, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.current_image = QImage()
        self.dragging = False
        self.pending_image = None
        self.reveal = CornerReveal(self)
        self.setGraphicsEffect(self.reveal)
        self.animation = QPropertyAnimation(self.reveal, b'amount', self)
        ease = QEasingCurve(QEasingCurve.Type.BezierSpline)
        ease.addCubicBezierSegment(QPointF(0.23, 1), QPointF(0.32, 1), QPointF(1, 1))
        self.animation.setEasingCurve(ease)
        self.animation.finished.connect(self.animation_finished)
        self.setObjectName('screenshotPreview')
        self.setStyleSheet('''
            QWidget#screenshotPreview {
                background: #fafbfc; border: 1px solid #ccd4dc; border-radius: 12px;
            }
            QLabel { color: #192631; background: transparent; border: none; }
            QPushButton {
                border: none; border-radius: 6px; background: transparent;
                color: #536475; font-size: 18px;
            }
            QPushButton:hover { background: #e6ebef; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel('已收到截图')
        title.setStyleSheet('font-size: 15px; font-weight: 600;')
        header.addWidget(title)
        header.addStretch()
        dismiss = QPushButton('×')
        dismiss.setAccessibleName('关闭截图预览')
        dismiss.setFixedSize(28, 28)
        dismiss.clicked.connect(self.dismiss)
        header.addWidget(dismiss)
        layout.addLayout(header)
        self.thumbnail = DraggableThumbnail(self)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.thumbnail, alignment=Qt.AlignmentFlag.AlignHCenter)
        self.header_min_width = header.minimumSize().width()
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.timeout.connect(self.dismiss)

    def animate_to(self, amount, duration):
        self.animation.stop()
        self.animation.setDuration(duration)
        self.animation.setStartValue(self.reveal.amount)
        self.animation.setEndValue(amount)
        self.animation.start()

    def animation_finished(self):
        if self.reveal.amount < 0.001:
            self.hide()

    def dismiss(self):
        if not self.dragging:
            self.dismiss_timer.stop()
            self.animate_to(0.0, 160)

    def show_image(self, image):
        if self.dragging:
            self.pending_image = image.copy()
            return
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        self.current_image = image.copy()
        self.thumbnail.setToolTip('按住图片，拖到聊天窗口、文档或文件夹')
        was_visible = self.isVisible()
        self.animation.stop()
        width = min(360, max(120, area.width() - 32))
        height = min(260, max(80, area.height() - 150))
        # Scale from the original on every receipt; keep portrait screenshots intact.
        pixmap = QPixmap.fromImage(image).scaled(width - 28, height,
            Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self.thumbnail.setPixmap(pixmap)
        self.thumbnail.setFixedSize(pixmap.size())
        self.setFixedWidth(max(pixmap.width(), self.header_min_width) + 28)
        self.adjustSize()
        self.move(area.right() - self.width() - 15, area.bottom() - self.height() - 15)
        self.reveal.motion_enabled = animations_enabled()
        if not was_visible:
            self.reveal.amount = 0.0
        self.show()
        self.animate_to(1.0, 260 if self.reveal.motion_enabled else 160)
        self.dismiss_timer.start(8000)
        if self.underMouse():
            self.dismiss_timer.stop()

    def begin_drag(self):
        if self.current_image.isNull() or self.dragging:
            return
        self.dragging = True
        self.dismiss_timer.stop()
        self.animation.stop()
        self.reveal.amount = 1.0
        self.thumbnail.setCursor(Qt.CursorShape.ClosedHandCursor)
        drag = QDrag(self.thumbnail)
        try:
            drag.setMimeData(drag_payload(self.current_image.copy()))
            ghost = QPixmap.fromImage(self.current_image).scaled(160, 160,
                Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            drag.setPixmap(ghost)
            drag.setHotSpot(QPoint(ghost.width() // 2, ghost.height() // 2))
            drag.exec(Qt.DropAction.CopyAction, Qt.DropAction.CopyAction)
        except OSError:
            self.thumbnail.setToolTip('暂时无法拖动，可用 Ctrl+V 粘贴')
        finally:
            drag.deleteLater()
            self.dragging = False
            self.thumbnail.setCursor(Qt.CursorShape.OpenHandCursor)
            if self.pending_image is not None:
                latest, self.pending_image = self.pending_image, None
                self.show_image(latest)
            elif self.isVisible() and not self.underMouse():
                self.dismiss_timer.start(8000)

    def enterEvent(self, event):
        self.dismiss_timer.stop()
        if self.isVisible() and self.reveal.amount < 1.0:
            self.animate_to(1.0, 120)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self.dragging:
            self.dismiss_timer.start(8000)
        super().leaveEvent(event)

    def hideEvent(self, event):
        self.dismiss_timer.stop()
        self.animation.stop()
        super().hideEvent(event)


class Window(QMainWindow):
    received = Signal()
    def __init__(self, server, url, directory_mode=False):
        super().__init__()
        self.server = server
        self.preview = ScreenshotPreview()
        self.setWindowTitle('截屏到电脑 · AirBridge Screenshot')
        self.resize(700, 340)
        widget = QWidget()
        self.setCentralWidget(widget)
        layout = QVBoxLayout(widget)
        heading = QLabel('截屏到电脑')
        heading.setStyleSheet('font-size: 24px; font-weight: 600;')
        layout.addWidget(heading)
        layout.addWidget(QLabel('收到截图后，右下角显示图片预览，并自动复制，按 Ctrl+V 粘贴。'))
        layout.addWidget(QLabel('iPad 自动查询电脑地址的入口（用于查询步骤）：' if directory_mode
                                else '在 iPad 快捷指令的 URL 中填入以下完整地址：'))
        address = QLineEdit(url)
        address.setReadOnly(True)
        layout.addWidget(address)
        self.network_status = QLabel('正在准备网络连接…')
        layout.addWidget(self.network_status)
        copy = QPushButton('复制连接地址')
        copy.clicked.connect(lambda: QApplication.clipboard().setText(url))
        layout.addWidget(copy)
        self.status = QLabel('正在等待 iPad 截图…')
        layout.addWidget(self.status)
        self.pause = QPushButton('暂停接收')
        self.pause.clicked.connect(self.toggle_pause)
        layout.addWidget(self.pause)
        layout.addWidget(QLabel('关闭窗口会继续在托盘接收；右键托盘图标可退出。\n拖拽缓存保留 24 小时后自动清理。连接地址仅供自己的设备使用。'))
        self.tray = QSystemTrayIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon), self)
        self.tray.setToolTip('截屏到电脑 — 正在接收')
        menu = QMenu(self)
        menu.addAction('打开窗口', self.open_window)
        menu.addAction('退出接收器', QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self.tray_activated)
        self.tray.show()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.drain)
        self.timer.start(80)
        self.cache_timer = QTimer(self)
        self.cache_timer.timeout.connect(self.clean_cache)
        self.cache_timer.start(15 * 60 * 1000)
        QTimer.singleShot(0, self.clean_cache)

    def clean_cache(self):
        if not self.preview.dragging:
            clean_drag_cache()

    def tray_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                      QSystemTrayIcon.ActivationReason.DoubleClick):
            self.open_window()

    def open_window(self):
        self.showNormal()
        # A hidden Windows launch can consume the first ShowWindow call.
        # Repeat after the tray callback and bring the restored window forward.
        QTimer.singleShot(0, self.foreground_window)

    def foreground_window(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def toggle_pause(self):
        self.server.accepting = not self.server.accepting
        self.pause.setText('暂停接收' if self.server.accepting else '恢复接收')
        self.status.setText('正在等待 iPad 截图…' if self.server.accepting else '已暂停接收')
        self.tray.setToolTip('截屏到电脑 — ' + ('正在接收' if self.server.accepting else '已暂停'))

    def drain(self):
        try:
            task = self.server.pending.get_nowait()
        except queue.Empty:
            return
        with task['lock']:
            if task['cancelled']:
                return
            if self.server.accepting:
                clipboard = QApplication.clipboard()
                clipboard.setImage(task['image'])
                task['ok'] = clipboard.image() == task['image']
            if task['ok']:
                task['message'] = 'Copied to Windows clipboard'
                size = task['image'].size()
                self.status.setText(f'已复制 {size.width()} × {size.height()} · {datetime.now():%H:%M:%S} · 可按 Ctrl+V')
                self.preview.show_image(task['image'])
                self.received.emit()
            else:
                task['message'] = 'Clipboard unavailable or receiver paused'
            task['done'].set()

    def closeEvent(self, event):
        if self.tray.isSystemTrayAvailable():
            self.hide()
            event.ignore()
        else:
            QApplication.quit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host')
    parser.add_argument('--port', type=int, default=8769)
    parser.add_argument('--background', action='store_true', help='Start in the tray and wait for a network connection')
    args = parser.parse_args()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    instance_lock = QLockFile(str(DATA_DIR / f'receiver-{args.port}.lock'))
    instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(0):
        return 0
    event_file = RotatingFileHandler(DATA_DIR / 'receiver-events.log',
                                    maxBytes=65536, backupCount=1, encoding='utf-8')
    event_file.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    EVENTS.addHandler(event_file)
    EVENTS.setLevel(logging.INFO)
    EVENTS.info('Receiver starting; data directory=%s', DATA_DIR)
    while True:
        try:
            host = args.host or local_address()
            token = load_token()
            server = ReceiverServer((host, args.port), token)
            break
        except Exception as exc:
            if args.background:
                time.sleep(5)  # Wi-Fi may not be connected yet at Windows login.
                continue
            QMessageBox.critical(None, '无法启动截图接收器', str(exc))
            return 1
    name = load_device_name()
    try:
        publisher = load_publisher(DATA_DIR / 'directory.json')
    except Exception:
        publisher = None
        EVENTS.warning('Address directory configuration invalid; using local mode')
    EVENTS.info('Address discovery mode=%s', 'directory' if publisher else 'mdns')
    url = publisher.lookup_url if publisher else f'http://{name}:{server.server_port}/clip/{token}'
    network = NetworkBinding(server, name, address_source=(lambda: args.host) if args.host else local_address,
                             config_path=DATA_DIR / 'connection.json', publisher=publisher)
    window = Window(server, url, directory_mode=bool(publisher))
    network.changed.connect(window.network_status.setText)
    network.start()
    if not args.background:
        window.show()
        QTimer.singleShot(250, window.showNormal)
    result = app.exec()
    network.close()
    return result


if __name__ == '__main__':
    sys.exit(main())
