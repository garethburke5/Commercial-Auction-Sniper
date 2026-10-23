"""Own-brand JPEG cards, optionally with an explicitly permitted real photograph."""
from datetime import date
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont, ImageOps
from web_platform.social_images import download_photo
import time

NAVY='#182e48';TEAL='#36b59a';GREY='#596873';PAPER='#f6f8f7'

def font(size,bold=False):
    name='DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/'+name,size)

def wrap(draw, text, face, width):
    lines=[];line=''
    for word in text.split():
        candidate=(line+' '+word).strip()
        if draw.textlength(candidate,font=face)>width and line:lines.append(line);line=word
        else:line=candidate
    if line:lines.append(line)
    return lines

def permission(post, permissions, today):
    grant=permissions.get('images',{}).get(post.get('image_source'))
    if not grant or grant.get('social_reuse') is not True or not grant.get('permission_evidence'):return None
    try:
        if date.fromisoformat(grant['expires_on'])<today:return None
    except (KeyError,ValueError):return None
    return grant

def render(post, destination, permissions, *, today=None):
    canvas=Image.new('RGB',(1080,1080),PAPER);draw=ImageDraw.Draw(canvas)
    draw.rectangle((0,0,1080,122),fill=NAVY)
    draw.rectangle((64,43,72,80),fill=TEAL)
    draw.text((92,40),'AUCTION GEEK',font=font(31,True),fill='white')
    draw.text((64,163),'AUCTION WATCH' if post['kind']=='property' else 'INVESTOR NOTES',font=font(22,True),fill=GREY)
    titleface=font(43,True);title=wrap(draw,post['title'],titleface,952)
    if len(title)>4:titleface=font(35,True);title=wrap(draw,post['title'],titleface,952)
    if len(title)>5:raise ValueError('Title too long for professional card')
    y=216
    for line in title:draw.text((64,y),line,font=titleface,fill=NAVY);y+=57
    sub=wrap(draw,post['subtitle'],font(23),952)
    for line in sub:draw.text((64,y+12),line,font=font(23),fill=GREY);y+=34
    y+=50
    grant=permission(post,permissions,today or date.today())
    used_photo=False
    if grant:
        try:
            data=download_photo(post['image_source'],time.monotonic()+15)
            with Image.open(BytesIO(data)) as original:
                if original.width*original.height>24000000:raise ValueError('Oversized image')
                photo=ImageOps.contain(ImageOps.exif_transpose(original).convert('RGB'),(952,280))
            canvas.paste(photo,(64+(952-photo.width)//2,y));y+=300;used_photo=True
        except (OSError,ValueError):pass
    if used_photo:
        # Photo layout has only one lead figure; all figures remain in the caption.
        stats=post['stats'][:1]
    else:stats=post['stats']
    for value,label in stats:
        if y+108>970:raise ValueError('Card content overflow')
        draw.line((64,y,1016,y),fill='#dbe3e4',width=2)
        draw.text((64,y+18),value,font=font(51,True),fill=NAVY)
        draw.text((64,y+80),label,font=font(23),fill=GREY)
        y+=145
    draw.rectangle((0,1010,1080,1080),fill=NAVY)
    draw.text((64,1030),'auctiongeek.co.uk',font=font(25),fill='white')
    foot=grant.get('attribution','') if used_photo else ('Before purchase and running costs' if post['kind']=='property' and len(post['stats'])==3 else 'Independent property research')
    face=font(19)
    if draw.textlength(foot,font=face)>620:raise ValueError('Attribution too long')
    draw.text((1016-draw.textlength(foot,font=face),1034),foot,font=face,fill='#d4e6e0')
    out=BytesIO();canvas.save(out,'JPEG',quality=90,optimize=True)
    data=out.getvalue();name=sha256(data).hexdigest()[:24]+'.jpg'
    Path(destination).mkdir(parents=True,exist_ok=True);(Path(destination)/name).write_bytes(data)
    return name, {'kind':'permitted_property_photograph' if used_photo else 'original_typographic_card',
                  'permission_evidence':grant['permission_evidence'] if used_photo else 'Auction Geek original artwork',
                  'alt':post['title']+'. '+'. '.join(value+' '+label for value,label in post['stats'])}

def build(posts, directory, permissions, origin):
    for post in posts:
        name,evidence=render(post,directory,permissions)
        post['image_file']=name;post['image_url']=origin+name;post['media_evidence']=evidence
    return posts
