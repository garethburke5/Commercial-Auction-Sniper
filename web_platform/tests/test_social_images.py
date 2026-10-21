from io import BytesIO
from pathlib import Path
import socket
import pytest
from PIL import Image
from web_platform.social_images import branded_photo, build_social_images, public_image_url
from web_platform.tests.test_platform import site
from bs4 import BeautifulSoup


def photo():
    out=BytesIO();Image.new('RGB',(640,480),'#bd7154').save(out,'JPEG');return out.getvalue()


def test_contained_photo_and_separate_brand_band():
    image=Image.open(BytesIO(branded_photo(photo())))
    assert image.size==(1200,630)
    assert image.getpixel((600,275))[0]>150
    assert image.getpixel((600,600))[0]<40
    with pytest.raises(Exception):branded_photo(b'not a photo')


def test_public_image_fetch_rejects_internal_and_credentials(monkeypatch):
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(None,None,None,None,('127.0.0.1',443))])
    assert not public_image_url('https://images.example.com/shop.jpg')
    assert not public_image_url('http://images.example.com/shop.jpg')
    assert not public_image_url('https://user:pass@images.example.com/shop.jpg')
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(None,None,None,None,('8.8.8.8',443))])
    assert public_image_url('https://images.example.com/shop.jpg')


def test_build_uses_real_downloads_once_and_falls_back_safely(site,tmp_path):
    row=site.catalogue.properties[0];row['image_url']='https://images.example.com/shop.jpg'
    calls=[]
    def download(url,deadline):calls.append(url);return photo()
    site.social_images=build_social_images([row,row],tmp_path,downloader=download)
    assert calls==[row['image_url']]
    path=site.social_images[row['image_url']]
    assert (tmp_path/path.lstrip('/')).is_file()
    html=site.snapshot_page(row);soup=BeautifulSoup(html,'html.parser')
    assert soup.select_one('meta[property="og:image"]')['content']==site.origin+path
    assert soup.select_one('meta[property="og:image:width"]')['content']=='1200'
    def failed(url,deadline):raise ValueError('blocked')
    assert build_social_images([row],tmp_path/'failed',downloader=failed)=={}
    assert build_social_images([row],tmp_path/'expired',downloader=download,max_seconds=-1)=={}


def test_savills_fallback_is_gallery_sized_and_cached_brand_still_wins(site):
    row=site.catalogue.properties[0]
    row['image_url']='https://resize.auctions.savills.co.uk/assets/images/lots/1/2/photo.png'
    assert site.social_details(row)['image']=='https://resize.auctions.savills.co.uk/resized/images/w1500/lots/1/2/photo.png'
    site.social_images={row['image_url']:'/static/share-images/example.jpg'}
    assert site.social_details(row)['image']==site.origin+'/static/share-images/example.jpg'
