"""Keep installed dependency license texts alongside the portable binary."""
from importlib import metadata
from pathlib import Path
import shutil
import sys

packages = ('PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6',
            'zeroconf', 'ifaddr', 'qrcode', 'Pillow', 'colorama')
target = Path(sys.argv[1]) / 'licenses'
target.mkdir(parents=True, exist_ok=True)
inventory = []
for name in packages:
    distribution = metadata.distribution(name)
    inventory.append(f'{name} {distribution.version}')
    copied = 0
    for entry in distribution.files or ():
        path = Path(str(entry))
        if not any(part.lower() in ('licenses', 'license', 'license.txt', 'license.md', 'copying', 'copying.txt')
                   or part.lower().startswith('license.') for part in path.parts):
            continue
        source = Path(distribution.locate_file(entry))
        if source.is_file():
            destination = target / name / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied += 1
    if not copied:
        print(f'No installed license file found for {name}; see THIRD_PARTY_NOTICES.md')
(target / 'versions.txt').write_text('\n'.join(inventory) + '\n', encoding='utf-8')
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.exists():
    shutil.copy2(python_license, target / 'Python-LICENSE.txt')
