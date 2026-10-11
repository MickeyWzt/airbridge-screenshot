"""Create a source-only handoff archive from a small explicit allowlist."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parent
files = [path for path in root.iterdir() if path.is_file() and
         (path.suffix in ('.py', '.ps1', '.md', '.txt') or path.name in ('LICENSE', '.gitignore'))]
files.extend(path for directory in ('assets', 'third_party', 'shortcuts') for path in (root / directory).rglob('*') if path.is_file())
output = root / 'dist' / 'AirBridgeScreenshot-0.1.0-preview-source.zip'
output.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, 'airbridge-screenshot/' + path.relative_to(root).as_posix())
print(f'Source archive: {output.name} ({output.stat().st_size} bytes)')
