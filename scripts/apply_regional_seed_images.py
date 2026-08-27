from pathlib import Path
import py_compile

p=Path('app.py')
c=p.read_text(encoding='utf-8')

images={
'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151798':'https://www.auctionhouse.co.uk/lot-image/921603?w=670',
'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151516':'https://www.auctionhouse.co.uk/lot-image/917891?w=670',
'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151791':'https://www.auctionhouse.co.uk/lot-image/921518?w=670',
'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151501':'https://www.auctionhouse.co.uk/lot-image/917631?w=670',
'https://www.auctionhouse.co.uk/westyorkshire/auction/lot/152101':'https://www.auctionhouse.co.uk/lot-image/925288?w=670',
'https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151599':'https://www.auctionhouse.co.uk/lot-image/919095?w=670',
'https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151605':'https://www.auctionhouse.co.uk/lot-image/919155?w=670',
'https://www.auctionhouse.co.uk/westyorkshire/auction/lot/151636':'https://www.auctionhouse.co.uk/lot-image/919540?w=670',
'https://www.auctionhouse.co.uk/sussexandhampshire/auction/lot/151683':'https://www.auctionhouse.co.uk/lot-image/920193?w=670',
'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151473':'https://www.auctionhouse.co.uk/lot-image/917043?w=670',
'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151800':'https://www.auctionhouse.co.uk/lot-image/921627?w=670',
'https://www.auctionhouse.co.uk/eastanglia/auction/lot/151749':'https://www.auctionhouse.co.uk/lot-image/921063?w=670',
'https://www.auctionhouse.co.uk/southwest/auction/lot/151562':'https://www.auctionhouse.co.uk/lot-image/918620?w=670',
}

for url,img in images.items():
    marker=f'url="{url}"'
    idx=c.find(marker)
    assert idx>=0, url
    end=c.find(')',idx)
    assert end>=0, url
    block=c[idx:end]
    if 'image=' not in block:
        c=c[:idx]+c[idx:].replace(marker, marker+f', image="{img}"',1)

c=c.replace('BUILD = "V6.23-BTG-EXACT-FIRST"','BUILD = "V6.24-REGIONAL-IMAGES"',1)
p.write_text(c,encoding='utf-8')
py_compile.compile(str(p),doraise=True)

# Regression: every verified regional exact URL has its validated preview pinned.
text=p.read_text(encoding='utf-8')
for url,img in images.items():
    pos=text.find(f'url="{url}"')
    assert pos>=0
    assert img in text[pos:pos+400]
print('Pinned',len(images),'Auction House regional images')
