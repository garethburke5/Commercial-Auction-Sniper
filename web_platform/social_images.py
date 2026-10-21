"""Build-time branded JPEGs from existing property photographs; no AI or paid API.

A bounded best-effort pass: missing/blocked images keep their existing source URL
in metadata. The property photograph is contained in full above a separate band.
"""
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit, urljoin
import hashlib
import ipaddress
import socket
import time
import warnings
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

MAX_BYTES = 8 * 1024 * 1024
VERSION = 'auction-geek-social-1'


def public_image_url(url):
    p=urlsplit(url)
    if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):
        return False
    try:
        addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
        return bool(addresses) and all(ipaddress.ip_address(a[4][0]).is_global for a in addresses)
    except (OSError,ValueError):
        return False


def download_photo(url, deadline):
    # Savills' own gallery uses generateAssetUrl(image, 'w1500'). Its unresized
    # originals can exceed 30 MB; preserve the exact photograph at gallery size.
    parsed=urlsplit(url)
    if parsed.hostname=='resize.auctions.savills.co.uk' and parsed.path.startswith('/assets/images/'):
        url=url.replace('/assets/images/','/resized/images/w1500/',1)
    for _ in range(4):
        if time.monotonic()>=deadline or not public_image_url(url):
            raise ValueError('Image unavailable')
        with requests.get(url,stream=True,timeout=(2,3),allow_redirects=False,
                          headers={'User-Agent':'AuctionGeek-SocialPreview/1.0'}) as response:
            if response.is_redirect:
                url=urljoin(url,response.headers['Location']);continue
            response.raise_for_status()
            if not response.headers.get('Content-Type','').lower().startswith('image/'):
                raise ValueError('Not an image response')
            chunks=[];size=0
            for chunk in response.iter_content(65536):
                size+=len(chunk)
                if size>MAX_BYTES or time.monotonic()>=deadline:raise ValueError('Image budget exceeded')
                chunks.append(chunk)
            return b''.join(chunks)
    raise ValueError('Too many image redirects')


def branded_photo(data):
    with warnings.catch_warnings():
        warnings.simplefilter('error',Image.DecompressionBombWarning)
        with Image.open(BytesIO(data)) as original:
            if original.width*original.height>24_000_000:raise ValueError('Image dimensions too large')
            if original.width<200 or original.height<120:raise ValueError('Image too small for a property preview')
            photo=ImageOps.exif_transpose(original).convert('RGB')
            photo=ImageOps.contain(photo,(1200,554),Image.Resampling.LANCZOS)
    canvas=Image.new('RGB',(1200,630),'#f0f3f2')
    canvas.paste(photo,((1200-photo.width)//2,(554-photo.height)//2))
    draw=ImageDraw.Draw(canvas)
    draw.rectangle((0,554,1200,630),fill='#182e48')
    draw.rectangle((0,554,8,630),fill='#36b59a')
    # Pillow's bundled font avoids dependence on host-installed fonts.
    draw.text((30,574),'AUCTION GEEK',font=ImageFont.load_default(size=31),fill='white')
    draw.text((873,582),'auctiongeek.co.uk',font=ImageFont.load_default(size=22),fill='#d4e6e0')
    out=BytesIO();canvas.save(out,'JPEG',quality=85,optimize=True)
    return out.getvalue()


def build_social_images(rows, destination, *, max_seconds=90, workers=16, downloader=download_photo):
    urls=list(dict.fromkeys(r.get('image_url') for r in rows if r.get('image_url')))
    output=Path(destination)/'static/share-images';output.mkdir(parents=True,exist_ok=True)
    deadline=time.monotonic()+max_seconds
    def build(url):
        if time.monotonic()>=deadline:return None
        name=hashlib.sha256((VERSION+url).encode()).hexdigest()[:24]+'.jpg'
        try:
            data=branded_photo(downloader(url,deadline))
            (output/name).write_bytes(data)
            return url,'/static/share-images/'+name
        except (OSError,ValueError,requests.RequestException,Image.DecompressionBombWarning,Image.DecompressionBombError):
            return None
    with ThreadPoolExecutor(max_workers=workers) as pool:
        generated=dict(item for item in pool.map(build,urls) if item)
    print(f'Social preview photographs: {len(generated)}/{len(urls)} branded; remaining pages retain original image URLs')
    return generated
