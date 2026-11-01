"""Target: the Godot project (might-action-force-tcg).

  assets/cards/   art, frame layers, badge, card backs     assets/board/  pieces, layout.json, gem strips
  assets/ui/      dialog window, deck organizer             assets/logo/   MAF emblem
  assets/fonts/   TTFs from the game shell                  assets/sounds/ effects + music
  cards/data/     CardData .tres per card                   external/      data/, fonts/, actionscript/
"""
import json
import math
import os
import xml.etree.ElementTree as ET

from source import BADGE_BOX, CARD_BOX, STYLES, decorations, named, origin
from swf import NS, Composer, ffdec, layout, svg_of

EFFECTS = ["none", "block", "steal", "draw", "skip", "both"]   # CardData.Effect order
GAME_FONTS = ["GrilledCheeseBTN-Wide", "BillySerif", "Arial-Bold", "Arial-BoldItalic", "BillyBold", "BillyLight",
              "CreativeBlockBB", "CreativeBlockBB-Bold"]
REFERENCE_FONTS = ["WebLettererBB", "GhostKidAOE"]
SOUNDS = {
    "music": ["mighty_action_force", "mighty_action_force_omegon"],
    "effects": ["access_denied", "card_flip_01", "card_get", "gem_break_01", "get_gem_victory_01",
                *[f"get_gem_{i:02}" for i in range(1, 14)], "mini_game_loss", "mini_game_win",
                "pick_card_01", "pick_card_02", "slide_card_01", "stack_deck_01"],
}
# Board content instance -> file, shared by both styles (the worn board only differs in background and card back).
SHARED_PIECES = {
    "playerDock": "dock_slot",
    "playerAttack": "slot_player_attack", "playerBounty": "slot_player_bounty",
    "enemyAttack": "slot_enemy_attack", "enemyBounty": "slot_enemy_bounty",
    "playerTray": "tray_player", "enemyTray": "tray_enemy", "splash_mc": "end_popup",
}
ACTIONSCRIPT = ["game.scenes.con2.shared.cardGame.**", "game.scenes.con2.shared.turnBased.**",
                "game.scenes.con2.shared.CCGCardManager", "game.scenes.con2.shared.Poptropicon2Scene",
                "game.scenes.con2.shared.popups.CardDeck", "game.scenes.con2.shared.popups.CardOrganizer",
                "game.ui.card.CardView", "game.components.ui.CardItem", "game.data.ui.card.CardItemData",
                "game.scene.template.ui.CardGroup"]


def cards(src, out):
    """Card art, frame layers per style, and one value badge that the game tints per value
    (grayscale: outline = 0, fill gradient = 0.25 dark end .. 1 light end; see cards/badge.gdshader)."""
    for name, svg in src.card_art().items():
        out.write(f"assets/cards/art/{name}.svg", svg)   # drawn around its origin, the card centre
    for style in STYLES:
        out.write(f"assets/cards/frames/{style}/border.svg", svg_of(src.frame_border(style), CARD_BOX))
        out.write(f"assets/cards/frames/{style}/border_rare.svg", svg_of(src.frame_border(style, rare=True), CARD_BOX))
        out.write(f"assets/cards/frames/{style}/frame.svg", svg_of(src.frame_body(style), CARD_BOX))

    def grayscale(el):
        stops = [s for s in el if s.tag.endswith("stop")]
        if stops:
            stops[0].set("stop-color", "#ffffff")
            stops[-1].set("stop-color", "#404040")
        if el.get("stroke", "none") != "none":
            el.set("stroke", "#000000")
    layers = src.badge_layers()
    out.write("assets/cards/badge/badge_shadow.svg", svg_of(layers["shadow"], BADGE_BOX))
    out.write("assets/cards/badge/badge.svg", svg_of(layers["fill"], BADGE_BOX, grayscale))
    out.write("assets/cards/badge/badge_shine.svg", svg_of(layers["shine"], BADGE_BOX))
    out.write("assets/cards/badge/badge_star.svg", svg_of(layers["star"], BADGE_BOX))


def board(src, out):
    """Shared board pieces + layout from the clean board; background and card back per style."""
    pieces, layout_data = {}, None
    for style in STYLES:
        swf, _, placed = src.board_content(style)
        comp = Composer(swf)
        chars = named(placed)
        extras = decorations(placed)
        bg = comp.svg(chars["bg"], extras=extras.get("bg", ()))
        out.write(f"assets/board/{style}/background.svg", bg)
        pieces.setdefault("bg", {"files": {}, "origin": {}})
        pieces["bg"]["files"][style] = f"{style}/background.svg"
        pieces["bg"]["origin"][style] = origin(bg)
        out.write(f"assets/cards/frames/{style}/back.svg", src.card_back(style))
        if style != "clean":
            continue
        for inst, fname in SHARED_PIECES.items():
            cid = chars[inst]
            if inst == "splash_mc":
                files = {label: (f"{fname}_{label}.svg", comp.svg(cid, frame)) for label, frame in swf.labels[cid].items()}
            else:
                files = {"default": (f"{fname}.svg", comp.svg(cid, extras=extras.get(inst, ())))}
            for name, text in files.values():
                out.write(f"assets/board/{name}", text)
            pieces[inst] = {"files": {k: n for k, (n, _) in files.items()},
                            "origin": {k: origin(t) for k, (_, t) in files.items()}}
        for inst, cid in chars.items():   # instances sharing a character reuse its file (enemyDock -> dock_slot)
            for other in list(pieces):
                if inst not in pieces and other in chars and chars[other] == cid:
                    pieces[inst] = pieces[other]
        layout_data = {"stage_size": swf.stage, "instances": layout(swf, placed)}
    out.write("assets/board/layout.json", json.dumps({**layout_data, "pieces": pieces}, indent=1))


def gems(src, out):
    """Gem socket animations as one SVG strip per colour: frame i in cell i, left to right."""
    for color, fname in (("red", "gem_player_red"), ("yellow", "gem_enemy_yellow")):
        swf, gem = src.gem(color)
        frames = swf.frames[gem]
        rects = [swf.bounds(gem, i) for i in range(len(frames))]
        x0, y0 = min(r[0] for r in rects), min(r[1] for r in rects)
        # whole-unit cells, so the 2x import gives whole-pixel frames
        w = math.ceil(max(r[0] + r[2] for r in rects) - x0)
        h = math.ceil(max(r[1] + r[3] for r in rects) - y0)
        comp = Composer(swf)
        svg = ET.Element(f"{{{NS}}}svg", {"width": str(w * len(frames)), "height": str(h),
                                          "viewBox": f"0 0 {w * len(frames)} {h}"})
        defs = ET.SubElement(svg, f"{{{NS}}}defs")
        for i in range(len(frames)):
            g = comp.render(gem, i, None, defs)
            g.set("transform", "translate(%g %g)" % (i * w - x0, -y0))
            svg.append(g)
        ET.indent(svg)
        out.write(f"assets/board/{fname}.svg", ET.tostring(svg, encoding="unicode"))
        labels = sorted(swf.labels[gem].items(), key=lambda kv: kv[1])
        anims = {name: {"from": start, "to": (labels[i + 1][1] - 1 if i + 1 < len(labels) else len(frames) - 1)}
                 for i, (name, start) in enumerate(labels)}
        out.write(f"assets/board/{fname}.json", json.dumps({
            "image": f"{fname}.svg", "frame_count": len(frames), "frame_size": [w, h],
            "origin": [x0, y0],   # cell top-left relative to the socket's registration point (score/slotN in layout.json)
            "fps": 28, "animations": anims}, indent=1))


def ui(src, out):
    swf = src.swf(f"scenes/{STYLES['clean']}/shared/cardGame/dialog_window.swf")   # same art in both episodes
    window = next(cid for cid, k in swf.kind.items() if k == "sprite" and cid in swf.grids)
    out.write("assets/ui/dialog_window.svg", Composer(swf).svg(window))
    x, y, w, h = swf.bounds(window)
    gx0, gy0, gx1, gy1 = swf.grids[window]
    out.write("assets/ui/dialog_window.json", json.dumps({
        "size": [w, h],
        # NinePatchRect margins, in SVG units (multiply by the import scale)
        "patch_margin": {"left": gx0 - x, "top": gy0 - y, "right": x + w - gx1, "bottom": y + h - gy1},
        "instances": layout(swf, swf.root_frames[0])}, indent=1))

    swf = src.swf(f"scenes/{STYLES['clean']}/shared/popups/cardDeck.swf")
    content = next(p for p in swf.root_frames[0].values() if p.get("name") == "content")
    text = Composer(swf).svg(content["char"])
    out.write("assets/ui/deck_organizer.svg", text)
    out.write("assets/ui/deck_organizer.json", json.dumps({
        "stage_size": swf.stage, "origin": origin(text),
        "instances": layout(swf, swf.frames[content["char"]][0])}, indent=1))


def logo(src, out):
    out.write("assets/logo/maf_logo.svg", src.logo())
    out.write("assets/logo/maf_logo_clean.svg", src.logo(shine=False))


def fonts(src, out):
    named_fonts, every = src.fonts()
    for name in GAME_FONTS:
        out.copy(named_fonts[name], f"assets/fonts/{name}.ttf")
    for name in REFERENCE_FONTS:
        out.copy(named_fonts[name], f"external/fonts/{name}.ttf")
    for path in every:
        out.copy(path, f"external/fonts/all_embedded/{os.path.basename(path)}")


def sounds(src, out):
    for kind, names in SOUNDS.items():
        for name in names:
            out.copy(src.sound(kind, name), f"assets/sounds/{kind}/{name}.mp3")


def esc(s):
    """A Godot resource string literal's contents."""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def data(src, out):
    """cards/data/*.tres for the game, plus reference JSON and the source XML in external/data/."""
    all_cards = src.cards()
    done = set()
    for c in all_cards:
        if c["id"] in done:
            continue   # worn reuses clean's cards; the shared ones are identical
        done.add(c["id"])
        out.write(f"cards/data/{c['id']}.tres", f'''[gd_resource type="Resource" script_class="CardData" format=3]

[ext_resource type="Script" path="res://cards/card_data.gd" id="1"]
[ext_resource type="Texture2D" path="res://assets/cards/art/{c["art"]}.svg" id="2"]

[resource]
script = ExtResource("1")
id = &"{c["id"]}"
display_name = "{esc(c["name"])}"
value = {c["value"]}
effect = {EFFECTS.index(c["effect"])}
power_name = "{esc(c["power_name"]) if c["effect"] != "none" else ""}"
description = "{esc(c["description"])}"
quote = "{esc(c["quotation"])}"
art = ExtResource("2")
''')
    reference = [{k: c[k] for k in ("id", "xml_id_mismatch", "episode", "name", "value", "effect",
                                    "power_name", "description", "quotation")} | {"art": f"assets/cards/art/{c['art']}.svg"}
                 for c in all_cards]
    out.write("external/data/cards.json", json.dumps(reference, indent=2, ensure_ascii=False))
    opponents = []
    for ep in STYLES.values():
        root = ET.parse(src.path("data", "scenes", ep, "shared", "cardGame", "ccgnpcs.xml")).getroot()
        for npc in root:
            c = npc.find("cards")
            opponents.append({"id": npc.get("id"), "episode": ep, "ai": c.get("ai"),
                              "deck": [e.text for e in c.findall("card")],
                              "reward": [e.text for e in npc.findall("reward/card")]})
    out.write("external/data/opponents.json", json.dumps(opponents, indent=2, ensure_ascii=False))
    for ep, items in src.card_items().items():
        for cid, _ in items:
            out.copy(src.path("data", "items", ep, f"{cid}.xml"), f"external/data/source_xml/{ep}/items/{cid}.xml")
        for fn in ("ccgnpcs.xml", "dialog.xml", "npcs.xml"):
            out.copy(src.path("data", "scenes", ep, "shared", "cardGame", fn), f"external/data/source_xml/{ep}/{fn}")


def actionscript(src, out):
    tmp = os.path.join(src.tmp, "as3")
    ffdec("-selectclass", ",".join(ACTIONSCRIPT), "-export", "script", tmp, src.path("Shell.swf"))
    base = os.path.join(tmp, "scripts")
    for d, _, files in os.walk(base):
        for fn in files:
            out.copy(os.path.join(d, fn), os.path.join("external", "actionscript", os.path.relpath(os.path.join(d, fn), base)))


STEPS = {"cards": cards, "board": board, "ui": ui, "gems": gems, "logo": logo, "fonts": fonts,
         "sounds": sounds, "data": data, "actionscript": actionscript}
