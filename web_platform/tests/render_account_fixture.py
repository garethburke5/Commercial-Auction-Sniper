"""Render the real account template for controlled browser acceptance tests."""
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
root = Path(__file__).resolve().parents[1]
env = Environment(loader=FileSystemLoader(root / "templates"), autoescape=select_autoescape())
print(env.get_template("page.html").render(title="My Auction Geek", description="Your private property research.", kind="account", url=lambda s:s, canonical="https://auctiongeek.co.uk/account/", noindex=True, structured="{}", asset_version="test", crumbs=[("Home","/"),("My Auction Geek","/account/")], catalogue={"generated_at":"2026-10-13T15:04"}, board=False))
