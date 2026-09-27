"""Read public brochures whose embedded fonts omit Unicode mappings."""
from io import BytesIO
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from pypdf import PdfReader


def brochure_text(raw):
    reader=PdfReader(BytesIO(raw))
    parts=[]
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'brochure.pdf'
        path.write_bytes(raw)
        for index,page in enumerate(reader.pages[:8]):
            text=page.extract_text() or ''
            # Missing ToUnicode produces CID values (including control bytes)
            # rather than words. Read the rendered page; never guess a cipher or
            # infer financial amounts from corrupt character codes.
            corrupt=sum(ord(c)<32 and c not in '\n\r\t' for c in text)>max(4,len(text)//100)
            if corrupt:
                if not shutil.which('pdftoppm') or not shutil.which('tesseract'):
                    continue
                stem=str(Path(folder)/f'page-{index}')
                subprocess.run(['pdftoppm','-f',str(index+1),'-l',str(index+1),'-r','160','-singlefile','-png',str(path),stem],check=True,capture_output=True,timeout=40)
                text=subprocess.run(['tesseract',stem+'.png','stdout','-l','eng'],check=True,capture_output=True,text=True,timeout=45).stdout
            if re.match(r'\s*AUCTION (?:NOTES|TERMS)',text,re.I):
                break
            parts.append(text)
    return re.sub(r'\s+',' ',' '.join(parts)).strip()
