# Third-party components

AirBridge Screenshot source is MIT licensed. Bundled components retain their own licenses.
The portable build keeps Python and Qt libraries as separate files in `_internal`.
Dependency license texts and the exact installed versions are collected in `licenses/`.
The app uses Qt Core, GUI, Widgets, Network and SVG libraries and image-format plugins.
Unused PDF, QML and virtual-keyboard plugins are excluded from the portable build.
Open-source license texts and source locations are also included in `third_party/`.

| Component | Project and source | License |
| --- | --- | --- |
| Python | https://www.python.org/ / https://github.com/python/cpython | PSF |
| PySide6 / shiboken6 | https://code.qt.io/cgit/pyside/pyside-setup.git/ | LGPLv3 / GPL / commercial |
| Qt | https://code.qt.io/ | LGPLv3 / GPL / commercial; individual modules may differ |
| zeroconf | https://github.com/python-zeroconf/python-zeroconf | LGPL-2.1 |
| ifaddr | https://github.com/pydron/ifaddr | MIT |
| qrcode | https://github.com/lincolnloop/python-qrcode | BSD |
| Pillow | https://github.com/python-pillow/Pillow | MIT-CMU |
| colorama | https://github.com/tartley/colorama | BSD |

Do not remove the bundled license files or the Python/Qt runtime libraries. The build
uses dynamically loaded Qt libraries; the application does not prohibit their replacement
or reverse engineering for debugging changes to these libraries.

PyInstaller is a build tool, licensed GPL with its bootloader distribution exception:
https://pyinstaller.org/en/stable/license.html
