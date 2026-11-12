"""Build a source ZIP and SHA-256 record without local logs or user captures."""
from pathlib import Path
import hashlib
import zipfile

root=Path(__file__).resolve().parents[1]
destination=root/'dist'
destination.mkdir(exist_ok=True)
archive=destination/'GPU-Live-Graphs-0.4.1-source.zip'
excluded={'.git','__pycache__','.venv','logs','captures','exports','dist','build'}
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
    for file in sorted(root.rglob('*')):
        if file.is_file() and not set(file.relative_to(root).parts)&excluded:
            output.write(file,Path('GPU-Live-Graphs')/file.relative_to(root))
with zipfile.ZipFile(archive) as output:
    assert output.testzip() is None
checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
(destination/'SHA256SUMS.txt').write_text(f'{checksum}  {archive.name}\n',encoding='utf-8')
print(archive.name,archive.stat().st_size,'bytes')
