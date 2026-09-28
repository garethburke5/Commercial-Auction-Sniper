"""Publish only rendered public pages, never databases, code or account state."""
import argparse
import shutil
from pathlib import Path
from .site import Site, HERE

def export(destination, origin):
    dest=Path(destination)
    dest.mkdir(parents=True, exist_ok=True)
    site=Site(origin=origin)
    routes=dict(site.routes())
    for path,html in routes.items():
        target=dest/path.strip('/')/'index.html'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(html)
    shutil.copytree(HERE/'static',dest/'static',dirs_exist_ok=True)
    for path,content in site.board_assets():
        target=dest/path.lstrip('/')
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content)
    (dest/'sitemap.xml').write_text(site.sitemap(routes))
    (dest/'robots.txt').write_text('User-agent: *\nAllow: /\nDisallow: /api/\nDisallow: /account/\nSitemap: '+origin.rstrip('/')+'/sitemap.xml\n')
    (dest/'.nojekyll').touch()
    (dest/'404.html').write_text(site.page('/404.html','Page not found','missing','This address does not identify a published page. Use Properties or Auctions to continue.',noindex=True))
    site.catalogue.close()
    print(f'Exported {len(routes)} useful public pages to {dest}')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',default='public-dist');p.add_argument('--origin',required=True)
    a=p.parse_args();export(a.output,a.origin)
