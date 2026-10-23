"""Own-brand cards using recorded image permissions or explicit owner instructions."""
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
    if not grant or grant.get('social_reuse') is not True:return None
    licensed = bool(grant.get('permission_evidence'))
    owner_requested = grant.get('authorization_basis') == 'owner_instruction' and bool(grant.get('authorization_evidence'))
    if not (licensed or owner_requested):return None
    try:
        if date.fromisoformat(grant['expires_on'])<today:return None
    except (KeyError,ValueError):return None
    return grant

def photo_card(post, data, grant, destination):
    canvas=Image.new('RGB',(1080,1080),PAPER);draw=ImageDraw.Draw(canvas)
    draw.rectangle((0,0,1080,78),fill=NAVY)
    draw.rectangle((40,25,46,53),fill=TEAL)
    draw.text((62,22),'AUCTION GEEK',font=font(25,True),fill='white')
    with Image.open(BytesIO(data)) as original:
        if original.width*original.height>24000000:raise ValueError('Oversized image')
        # Preserve the whole source photograph, including any existing credit.
        photo=ImageOps.contain(ImageOps.exif_transpose(original).convert('RGB'),(1080,565),Image.Resampling.LANCZOS)
    canvas.paste(photo,((1080-photo.width)//2,78+(565-photo.height)//2))
    title=post.get('display_title') or post['title']
    lines=wrap(draw,title,font(32,True),1000)
    if len(lines)>3:raise ValueError('Photo card title too long')
    for n,line in enumerate(lines):draw.text((40,669+n*42),line,font=font(32,True),fill=NAVY)
    if len(lines)<=2 and len(post['stats'])>=3:
        draw.text((40,681+len(lines)*42),post['stats'][1][0]+' advertised annual rent',font=font(24),fill=GREY)
    draw.line((40,810,1040,810),fill='#dbe3e4',width=2)
    stats=[post['stats'][0]]
    if len(post['stats'])>=3:stats.append(post['stats'][-1])
    for n,(value,label) in enumerate(stats):
        x=40+n*540
        draw.text((x,831),value,font=font(43,True),fill=NAVY)
        for j,line in enumerate(wrap(draw,label,font(20),490)):
            draw.text((x,889+j*25),line,font=font(20),fill=GREY)
    draw.text((40,957),'Yield before purchase and running costs' if len(stats)>1 else 'Guide price excludes purchase costs',font=font(20),fill=GREY)
    attribution=grant.get('attribution','Source property photograph')
    if draw.textlength(attribution,font=font(17))>1000:raise ValueError('Attribution too long')
    draw.text((40,995),attribution,font=font(17),fill=GREY)
    draw.rectangle((0,1030,1080,1080),fill=NAVY)
    draw.text((40,1041),'auctiongeek.co.uk',font=font(22),fill='white')
    out=BytesIO();canvas.save(out,'JPEG',quality=90,optimize=True)
    result=out.getvalue();name=sha256(result).hexdigest()[:24]+'.jpg'
    Path(destination).mkdir(parents=True,exist_ok=True);(Path(destination)/name).write_bytes(result)
    return name, {'kind':'property_photograph','authorization_basis':grant.get('authorization_basis','documented_permission'),
                  'authorization_evidence':grant.get('authorization_evidence') or grant.get('permission_evidence'),
                  'source_url':post['image_source'],'attribution':attribution,
                  'alt':post['title']+'. '+'. '.join(value+' '+label for value,label in stats)}

def render(post, destination, permissions, *, today=None):
    grant=permission(post,permissions,today or date.today())
    if post.get('require_photo') and not grant:raise ValueError('No recorded image-use instruction')
    if grant:
        try:
            data=download_photo(post['image_source'],time.monotonic()+15)
            return photo_card(post,data,grant,destination)
        except (OSError,ValueError):
            if post.get('require_photo'):raise
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
    stats=post['stats']
    for value,label in stats:
        if y+108>970:raise ValueError('Card content overflow')
        draw.line((64,y,1016,y),fill='#dbe3e4',width=2)
        draw.text((64,y+18),value,font=font(51,True),fill=NAVY)
        draw.text((64,y+80),label,font=font(23),fill=GREY)
        y+=145
    draw.rectangle((0,1010,1080,1080),fill=NAVY)
    draw.text((64,1030),'auctiongeek.co.uk',font=font(25),fill='white')
    foot='Before purchase and running costs' if post['kind']=='property' and len(post['stats'])==3 else 'Independent property research'
    face=font(19)
    if draw.textlength(foot,font=face)>620:raise ValueError('Attribution too long')
    draw.text((1016-draw.textlength(foot,font=face),1034),foot,font=face,fill='#d4e6e0')
    out=BytesIO();canvas.save(out,'JPEG',quality=90,optimize=True)
    data=out.getvalue();name=sha256(data).hexdigest()[:24]+'.jpg'
    Path(destination).mkdir(parents=True,exist_ok=True);(Path(destination)/name).write_bytes(data)
    return name, {'kind':'original_typographic_card',
                  'permission_evidence':'Auction Geek original artwork',
                  'alt':post['title']+'. '+'. '.join(value+' '+label for value,label in post['stats'])}

def build(posts, directory, permissions, origin):
    for post in posts:
        name,evidence=render(post,directory,permissions)
        post['image_file']=name;post['image_url']=origin+name;post['media_evidence']=evidence
    return posts
