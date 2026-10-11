"""Portable Windows app with first-use pairing and per-user setup controls."""
import argparse
import hashlib
import io
import ipaddress
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import sys

import qrcode
from PySide6.QtCore import QLockFile, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget)

import receiver
from pairing_web import shortcut_link
from windows_setup import request_firewall, resource_path, set_startup, startup_enabled

VERSION = '0.1.0-preview'


def app_icon():
    pixmap = QPixmap(128, 128)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#2465db'))
    painter.drawRoundedRect(4, 4, 120, 120, 28, 28)
    painter.setBrush(QColor('#9bc3ff'))
    painter.drawRoundedRect(30, 27, 58, 58, 8, 8)
    painter.setBrush(QColor('#ffffff'))
    painter.drawRoundedRect(42, 41, 58, 58, 8, 8)
    painter.setBrush(QColor('#2465db'))
    painter.drawRoundedRect(50, 52, 42, 5, 2, 2)
    painter.end()
    return QIcon(pixmap)


def qr_pixmap(url):
    code = qrcode.QRCode(border=3, box_size=6, error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(url)
    code.make(fit=True)
    stream = io.BytesIO()
    code.make_image(fill_color='#172437', back_color='white').save(stream, format='PNG')
    pixmap = QPixmap()
    pixmap.loadFromData(stream.getvalue(), 'PNG')
    return pixmap.scaled(208, 208, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)


class SetupWindow(receiver.Window):
    def __init__(self, server, network, shared_link=''):
        super().__init__(server, '')
        self.network = network
        self.shared_link = shortcut_link(shared_link)
        self.signature = None
        self.paired = (receiver.DATA_DIR / 'paired.txt').exists()
        self.setWindowTitle('AirBridge Screenshot · 截屏到电脑')
        self.setWindowIcon(app_icon())
        self.tray.setIcon(app_icon())
        self.resize(800, 580)
        self.setMinimumSize(720, 570)
        widget = QWidget()
        widget.setObjectName('setupRoot')
        self.setCentralWidget(widget)
        self.setStyleSheet('''
            QWidget#setupRoot { background:#f3f6fb; }
            QLabel { color:#172437; font-size:14px; }
            QFrame#card { background:white; border:1px solid #e1e7ef; border-radius:18px; }
            QPushButton { border:1px solid #d7e1ed; border-radius:9px; padding:9px 15px; background:white; color:#25435f; font-size:14px; }
            QPushButton:hover { background:#edf3fc; border-color:#a7bee0; }
            QPushButton#primary { background:#2465db; color:white; border:1px solid #2465db; }
            QPushButton#primary:hover { background:#1c54bc; }
            QPushButton:disabled { color:#99a4b0; background:#e6ebf2; }
            QLineEdit, QComboBox { border:1px solid #d7e1ed; border-radius:8px; padding:8px; color:#172437; background:#f8fafd; }
            QCheckBox { color:#25435f; font-size:14px; spacing:8px; }
        ''')
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(28, 24, 28, 22)
        layout.setSpacing(14)
        eyebrow = QLabel('AIRBRIDGE SCREENSHOT')
        eyebrow.setStyleSheet('color:#4d719c; font-size:12px; font-weight:600;')
        layout.addWidget(eyebrow)
        heading = QLabel('把 iPad 截图，送到电脑剪贴板')
        heading.setStyleSheet('font-size:26px; font-weight:600;')
        layout.addWidget(heading)
        helper = QLabel('第一次连接跟着下面两步走。设置好后，点 iPad 上的快捷指令就能发送。')
        helper.setWordWrap(True)
        helper.setStyleSheet('color:#687a90;')
        layout.addWidget(helper)
        row = QHBoxLayout()
        row.setSpacing(18)
        card = QFrame()
        card.setObjectName('card')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 18, 20, 16)
        card_layout.addWidget(QLabel('01 · 用 iPad 相机扫码'))
        self.qr = QLabel()
        self.qr.setFixedSize(208, 208)
        self.qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        card_layout.addWidget(self.qr, alignment=Qt.AlignmentFlag.AlignHCenter)
        qr_note = QLabel('打开配对页，复制地址\n添加快捷指令并填一次地址')
        qr_note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        qr_note.setStyleSheet('color:#687a90; font-size:13px;')
        card_layout.addWidget(qr_note)
        row.addWidget(card)
        right = QVBoxLayout()
        right.setSpacing(11)
        self.step = QLabel('02 · 从 iPad 试发一张截图')
        self.step.setStyleSheet('font-size:19px; font-weight:600;')
        right.addWidget(self.step)
        self.status = QLabel('收到图片后，右下角会出现预览，\n也会自动复制到电脑剪贴板。')
        self.status.setWordWrap(True)
        self.status.setStyleSheet('color:#566b83; line-height:1.5;')
        right.addWidget(self.status)
        right.addSpacing(5)
        right.addWidget(QLabel('连接方式'))
        self.mode = QComboBox()
        self.mode.addItems(['设备名称 · 通常换网不用改', '当前 IP · 设备名称不可用时选择'])
        self.mode.currentIndexChanged.connect(self.refresh_connection)
        right.addWidget(self.mode)
        self.address = QLineEdit()
        self.address.setReadOnly(True)
        self.address.setAccessibleName('完整截图发送地址')
        right.addWidget(self.address)
        copy = QPushButton('复制连接地址')
        copy.setObjectName('primary')
        copy.clicked.connect(self.copy_address)
        right.addWidget(copy)
        self.network_status = QLabel('正在准备网络连接…')
        self.network_status.setWordWrap(True)
        self.network_status.setStyleSheet('color:#687a90; font-size:12px;')
        right.addWidget(self.network_status)
        right.addStretch()
        row.addLayout(right, 1)
        layout.addLayout(row, 1)
        controls = QHBoxLayout()
        self.autostart = QCheckBox('登录 Windows 后自动接收')
        self.autostart.setChecked(startup_enabled())
        self.autostart.toggled.connect(self.change_startup)
        controls.addWidget(self.autostart)
        controls.addStretch()
        firewall = QPushButton('允许局域网连接…')
        firewall.clicked.connect(self.allow_lan)
        controls.addWidget(firewall)
        help_button = QPushButton('连接帮助')
        help_button.clicked.connect(self.connection_help)
        controls.addWidget(help_button)
        layout.addLayout(controls)
        bottom = QHBoxLayout()
        footer = QLabel('关闭窗口后继续接收 · 拖动缓存 24 小时后自动清理')
        footer.setStyleSheet('color:#687a90; font-size:12px;')
        bottom.addWidget(footer)
        bottom.addStretch()
        bottom.addWidget(self.pause)
        layout.addLayout(bottom)
        self.received.connect(self.on_received)
        network.changed.connect(self.on_network_changed)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_connection)
        self.refresh_timer.start(1000)
        if network.advertiser is None:
            self.mode.setCurrentIndex(1)
        self.refresh_connection()
        if self.paired:
            self.step.setText('连接已设置 · 正在等待截图')

    def refresh_connection(self, *_):
        host = self.network.host
        signature = (host, self.network.port, self.mode.currentIndex(), self.shared_link)
        if signature == self.signature:
            return
        self.signature = signature
        if not host:
            self.qr.clear()
            self.qr.setText('等待 Wi-Fi / 以太网连接')
            self.address.clear()
            self.server.state.pairing = {}
            return
        target_host = self.network.name if self.mode.currentIndex() == 0 else host
        upload_url = f'http://{target_host}:{self.network.port}/clip/{self.server.token}'
        setup_url = f'http://{host}:{self.network.port}/setup/{self.server.token}'
        self.address.setText(upload_url)
        self.qr.setPixmap(qr_pixmap(setup_url))
        self.server.state.pairing = {'upload_url': upload_url, 'shortcut_link': self.shared_link}

    def on_network_changed(self, message):
        self.network_status.setText(message)
        self.refresh_connection()

    def copy_address(self):
        if self.address.text():
            QApplication.clipboard().setText(self.address.text())
            self.network_status.setText('连接地址已复制；只需粘贴一次，不用拼接变量。')

    def foreground_window(self):
        # A launch using Windows SW_HIDE may leave Qt's visibility flag true
        # while the native window is hidden. Force a fresh show when requested.
        self.hide()
        super().foreground_window()

    def on_received(self):
        self.step.setText('✓ 连接成功，现在可以直接使用')
        if not self.paired:
            try:
                (receiver.DATA_DIR / 'paired.txt').write_text('connected\n', encoding='ascii')
                self.paired = True
            except OSError:
                receiver.EVENTS.warning('Could not save onboarding completion')

    def change_startup(self, enabled):
        try:
            set_startup(enabled)
        except OSError:
            self.autostart.blockSignals(True)
            self.autostart.setChecked(not enabled)
            self.autostart.blockSignals(False)
            QMessageBox.warning(self, '自动启动未保存', 'Windows 未能保存这个设置，请稍后重试。')

    def allow_lan(self):
        try:
            request_firewall(self.network.port)
            self.network_status.setText('请完成 Windows 管理员授权，再用 iPad 扫码测试。')
        except OSError:
            QMessageBox.warning(self, '无法打开授权', '请在 Windows 安全中心允许此应用通过专用网络防火墙。')

    def connection_help(self):
        QMessageBox.information(self, '连接帮助',
            '1. 两台设备连接同一 Wi-Fi，电脑保持运行。\n\n'
            '2. 二维码页面打不开：点击「允许局域网连接…」。只对专用网络、本地子网开放。'
            '传图端口和 UDP 5353 设备发现仅允许本地子网。若当前网络显示「公用」，'
            '请仅在信任的网络上改为「专用」；校园网也可能禁止设备互访。\n\n'
            '3. 页面能打开，但发送超时：切换到「当前 IP」，重新扫码复制地址。'
            'IP 方式换网后可能需要再次扫码。\n\n'
            '4. 允许快捷指令的本地网络访问。代理/VPN 有时会影响 .local 名称或局域网连接。\n\n'
            '5. 自动启动使用当前程序位置；移动解压目录后，重新打开并重新勾选自动启动。\n\n'
            '6. 接收成功会覆盖剪贴板。拖动缓存保留 24 小时，链接型文档请另存图片。')


def instance_name(directory, port):
    digest = hashlib.sha256(str(directory.resolve()).lower().encode('utf-8')).hexdigest()[:16]
    return f'AirBridgeScreenshot-{digest}-{port}'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--background', action='store_true')
    parser.add_argument('--host', help='Development/testing: override network interface')
    parser.add_argument('--port', type=int, default=8769)
    parser.add_argument('--data-dir', type=Path, help='Development/testing: isolated state directory')
    parser.add_argument('--version', action='version', version=VERSION)
    args = parser.parse_args()
    if args.data_dir:
        receiver.DATA_DIR = args.data_dir.resolve()
    app = QApplication(sys.argv)
    app.setApplicationName('AirBridge Screenshot')
    app.setApplicationVersion(VERSION)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)
    receiver.DATA_DIR.mkdir(parents=True, exist_ok=True)
    lock = QLockFile(str(receiver.DATA_DIR / f'receiver-{args.port}.lock'))
    lock.setStaleLockTime(0)
    ipc_name = instance_name(receiver.DATA_DIR, args.port)
    if not lock.tryLock(0):
        socket = QLocalSocket()
        socket.connectToServer(ipc_name)
        if socket.waitForConnected(1500):
            socket.write(b'open')
            socket.waitForBytesWritten(1000)
        return 0
    handler = RotatingFileHandler(receiver.DATA_DIR / 'receiver-events.log', maxBytes=65536, backupCount=1, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    receiver.EVENTS.addHandler(handler)
    receiver.EVENTS.setLevel(logging.INFO)
    receiver.EVENTS.info('Community receiver starting; version=%s', VERSION)
    offline = False
    try:
        host = args.host or receiver.local_address()
    except Exception:
        host, offline = '127.0.0.1', True
    try:
        server = receiver.ReceiverServer((host, args.port), receiver.load_token())
    except OSError:
        QMessageBox.warning(None, '暂时无法启动', '这个端口可能已有接收器在使用。请退出另一个版本后再试。')
        return 1
    network = receiver.NetworkBinding(server, receiver.load_device_name(),
        address_source=(lambda: args.host) if args.host else receiver.local_address,
        advertiser=None if args.host and ipaddress.IPv4Address(args.host).is_loopback else receiver.LocalAdvertisement,
        config_path=receiver.DATA_DIR / 'connection.json')
    if offline:
        network.switch(None)
    link_path = resource_path('shortcut-link.txt')
    shared_link = link_path.read_text(encoding='utf-8') if link_path.exists() else ''
    window = SetupWindow(server, network, shared_link)
    ipc = QLocalServer()
    QLocalServer.removeServer(ipc_name)
    ipc.listen(ipc_name)
    def activate():
        while ipc.hasPendingConnections():
            socket = ipc.nextPendingConnection()
            socket.close()
            socket.deleteLater()
        window.open_window()
    ipc.newConnection.connect(activate)
    network.start()
    if not args.background or not window.paired:
        window.show()
        QTimer.singleShot(250, window.foreground_window)
    result = app.exec()
    ipc.close()
    network.close()
    lock.unlock()
    return result


if __name__ == '__main__':
    sys.exit(main())
