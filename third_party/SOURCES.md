# Library source code

The bundled libraries are unmodified upstream builds. You may replace the dynamic
libraries in `_internal` with ABI-compatible builds, and debug changes to them.
Build the application with the documented Python/PyInstaller commands in README.md.

Corresponding Qt 6.11.1, PySide6/shiboken6 and zeroconf source archives are
provided as separate assets alongside the Windows binary in the same release:

https://github.com/MickeyWzt/airbridge-screenshot/releases/tag/v0.1.0-preview

The original upstream sources are:

- Qt Core / GUI / Widgets / Network / OpenGL and platform plugins:
  https://download.qt.io/archive/qt/6.11/6.11.1/submodules/qtbase-everywhere-src-6.11.1.tar.xz
- Qt SVG:
  https://download.qt.io/archive/qt/6.11/6.11.1/submodules/qtsvg-everywhere-src-6.11.1.tar.xz
- Qt image-format plugins:
  https://download.qt.io/archive/qt/6.11/6.11.1/submodules/qtimageformats-everywhere-src-6.11.1.tar.xz
- PySide6 / shiboken 6.11.1:
  https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.11.1-src/pyside-setup-everywhere-src-6.11.1.tar.xz
- zeroconf 0.151.3:
  https://pypi.org/project/zeroconf/0.151.3/#files

The release includes `SHA256SUMS.txt`. Dependency archives are checked against
Qt's official mirror-list hashes or PyPI's published source-distribution hash.

These sources include the applicable third-party notices for dependencies within Qt.
The release distributor must keep corresponding source available when distributing
the binary, including if any upstream URL becomes unavailable. The source archives
are separate downloads; users do not need them to run the Windows application.
