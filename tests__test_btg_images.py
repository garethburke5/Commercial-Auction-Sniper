"""Regression tests for exact-lot BTG/Pugh image selection."""

import ast
from pathlib import Path


def _load_btg_helpers(candidate_urls):
    tree = ast.parse(Path("app.py").read_text(encoding="utf-8"))
    wanted = {"_btg_property_key", "_btg_gallery_images"}
    functions = [
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in wanted
    ]
    assert {node.name for node in functions} == wanted

    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), "app.py", "exec"), namespace)
    namespace["_img_candidates"] = lambda _soup, _url: list(candidate_urls)
    return namespace


def test_btg_gallery_rejects_joint_agent_and_other_lot_images():
    page = (
        "https://www.btgeddisonspropertyauctions.com/properties/"
        "202607211014sq_kwai-270826/for-auction-south-molton"
    )
    joint_agent = (
        "https://asta.btgeddisonspropertyauctions.com/sdl_data/address/pkm_sdl/"
        "artnr_202604021548sq_7hap/_pictures/Charles_Darrow_NEW_2023.jpg"
    )
    exact_photo = (
        "https://asta.btgeddisonspropertyauctions.com/sdl_data/address/pkm_sdl/"
        "artnr_202607211014sq_kwai/_pictures/01.jpg"
    )
    other_lot = (
        "https://asta.btgeddisonspropertyauctions.com/sdl_data/address/pkm_sdl/"
        "artnr_202607010000sq_other/_pictures/01.jpg"
    )

    helpers = _load_btg_helpers([joint_agent, other_lot, exact_photo])
    assert helpers["_btg_property_key"](page) == "202607211014sq_kwai"
    assert helpers["_btg_gallery_images"](None, page) == [exact_photo]


def test_btg_gallery_never_returns_branding_from_exact_folder():
    page = (
        "https://www.btgeddisonspropertyauctions.com/properties/"
        "202607211014sq_kwai-270826/for-auction-south-molton"
    )
    exact_logo = (
        "https://asta.btgeddisonspropertyauctions.com/sdl_data/address/pkm_sdl/"
        "artnr_202607211014sq_kwai/_pictures/joint_agent_logo.jpg"
    )

    helpers = _load_btg_helpers([exact_logo])
    assert helpers["_btg_gallery_images"](None, page) == []
