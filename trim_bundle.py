"""Drop unused Qt PDF/QML/virtual-keyboard plugins and their private dependencies."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
qt = root / '_internal' / 'PySide6'
names = ('Qt6Pdf.dll', 'Qt6Qml.dll', 'Qt6QmlMeta.dll', 'Qt6QmlModels.dll',
         'Qt6QmlWorkerScript.dll', 'Qt6Quick.dll', 'Qt6VirtualKeyboard.dll',
         'plugins/imageformats/qpdf.dll', 'plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll')
removed = 0
paths = [qt / name for name in names]
# Qt uses Windows' built-in ICU API. Do not bundle a same-name ICU from an
# unrelated tool injected into the build environment's PATH.
paths.extend((root / '_internal' / name for name in ('icuuc.dll', 'icudt78.dll')))
for path in paths:
    if path.resolve().is_relative_to(root) and path.is_file() and not path.is_symlink():
        removed += path.stat().st_size
        path.unlink()
print(f'Removed unused Qt plugins and libraries: {removed / 1024 / 1024:.1f} MB')
