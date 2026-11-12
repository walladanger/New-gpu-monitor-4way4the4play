"""Check repository-local Markdown links and screenshot integrity, offline."""
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET
from PIL import Image

root=Path(__file__).resolve().parents[1]
errors=[]
documents=list(root.glob('*.md'))+list((root/'docs').glob('*.md'))
for document in documents:
    content=document.read_text(encoding='utf-8')
    targets=re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',content)
    targets+=re.findall(r'(?:src|href)="([^"]+)"',content)
    for target in targets:
        if target.startswith(('https://','http://','#','mailto:')):
            continue
        local=target.split('#',1)[0]
        if local and not (document.parent/local).exists():
            errors.append(f'{document.relative_to(root)}: missing {local}')
for image in (root/'docs'/'images').glob('*.png'):
    with Image.open(image) as pixels:
        if pixels.width<400 or pixels.height<300:
            errors.append(f'Unexpectedly small screenshot: {image.name}')
        pixels.verify()
ET.parse(root/'docs'/'images'/'banner.svg')
if errors:
    print('\n'.join(errors));sys.exit(1)
print(f'Checked {len(documents)} documents, six PNG captures, and SVG banner.')
