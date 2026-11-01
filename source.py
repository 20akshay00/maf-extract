"""What's where in Poptropica's files: the shared knowledge both targets build on.

Everything here returns SVG text, path lists or plain data; the targets (godot.py, pnp.py) decide file names and formats.
Style names map to episodes: clean = con2 (the original game), worn = con3 (its battle-damaged reskin).
"""
import os
import re
import shutil
import xml.etree.ElementTree as ET

from swf import IDENTITY, Composer, Swf, ffdec, leaves, mat_inv, mat_mul

STYLES = {"clean": "con2", "worn": "con3"}
CARD_SIZE = (280, 400)
CARD_BOX = (0, 0, *CARD_SIZE)
BADGE_BOX = (198, 0, 82, 82)        # the value badge's corner of the card

# Path indices in the composed background<N>.swf frames (paint order: text box, art window, art border,
# rest of the frame, value badge, its digit). pick() checks the colours, so a different source fails loudly.
FRAME = {
    "clean": {"border": [2, 3, 4], "badge": range(48, 54), "digit": range(54, 57)},
    "worn": {"border": [2, 3, 4], "badge": range(28, 34), "digit": range(34, 37)},
}
# Value 6: the normal frame with a purple art border. (con2's background6 also holds a gold frame, but the normal
# frame is drawn on top of it and the card renderer adds the whole SWF, so the gold one never shows.)
RARE_BORDER = {"clean": [52, 53, 54], "worn": [2, 11, 12]}
RARE_BADGE = {"badge": range(98, 105), "digit": range(105, 108)}   # clean background6: 7 layers, two stars

# Shell.swf font id -> name
FONTS = {8: "GrilledCheeseBTN-Wide", 26: "BillySerif", 14: "Arial-Bold", 22: "Arial-BoldItalic",
         13: "BillyBold", 3: "BillyLight", 9: "CreativeBlockBB", 6: "CreativeBlockBB-Bold",
         21: "WebLettererBB", 15: "GhostKidAOE"}


class Source:
    """The Poptropica mirror (its game/ folder) plus a scratch folder for JPEXS exports, with parsed SWFs cached."""

    def __init__(self, mirror, tmp):
        self.game = os.path.join(mirror, "game")
        if not os.path.exists(os.path.join(self.game, "Shell.swf")):
            raise SystemExit(f"Poptropica mirror not found: expected {os.path.join(self.game, 'Shell.swf')}")
        self.tmp, self._swfs, self._frames = tmp, {}, {}

    def swf(self, rel):
        """A SWF under game/assets/."""
        if rel not in self._swfs:
            self._swfs[rel] = Swf(os.path.join(self.game, "assets", rel), os.path.join(self.tmp, "swf", str(len(self._swfs))))
        return self._swfs[rel]

    def path(self, *parts):
        return os.path.join(self.game, *parts)

    # --- cards ----------------------------------------------------------------------------------------------

    def card_items(self):
        """{episode: [(id, xml root)]} for the card game's cards. The game uses the file name, not the id attribute."""
        out = {}
        for ep in STYLES.values():
            d = self.path("data", "items", ep)
            out[ep] = []
            for fn in sorted(os.listdir(d)):
                x = ET.parse(os.path.join(d, fn)).getroot()
                if re.fullmatch(r"\d+(,\w+)?", x.findtext("value") or "") and x.find(".//asset[@id='cardBack']") is not None:
                    out[ep].append((os.path.splitext(fn)[0], x))
        return out

    def cards(self):
        """One dict per card per episode: id, style, episode, name, value, effect, power_name, description,
        quotation, art (the art file's name), xml_id_mismatch."""
        style = {ep: s for s, ep in STYLES.items()}
        out = []
        for ep, items in self.card_items().items():
            for cid, x in items:
                value, _, effect = x.findtext("value").partition(",")
                text = {t.get("id"): t.findtext("value") for t in x.iter("text")}
                out.append({"id": cid, "style": style[ep], "episode": ep, "name": text.get("title"),
                            "value": int(value), "effect": effect or "none",
                            "power_name": text.get("power"), "description": text.get("description"),
                            "quotation": text.get("quotation"), "art": art_name(x),
                            "xml_id_mismatch": x.get("id") if x.get("id") != cid else None})
        return out

    def card_art(self):
        """{art name: SVG}, each drawn around the card centre (0, 0) in card units."""
        out = {}
        for items in self.card_items().values():
            for _, x in items:
                rel = x.find(".//asset[@id='cardContent']/assetPath").text   # items/con2/elf_archer.swf
                w, h = CARD_SIZE
                out.setdefault(art_name(x), Composer(self.swf(rel)).svg_root((-w / 2, -h / 2, w, h)))
        return out

    def frame(self, style, value=1):
        """(paths, gradients) of background<value>.swf, composed on the card (see FRAME)."""
        key = (style, value)
        if key not in self._frames:
            self._frames[key] = leaves(Composer(self.swf(f"items/{STYLES[style]}/background{value}.swf")).svg_root(CARD_BOX))
        return self._frames[key]

    def frame_border(self, style, rare=False):
        """Art window + its border. Rare = value 6."""
        if rare:
            return pick(self.frame(style, 6), RARE_BORDER[style], ["#6f8", "url", "#4d3145"])
        return pick(self.frame(style), FRAME[style]["border"], ["#6f8", "url", "#401414"])

    def frame_body(self, style):
        """The rest of the frame: no art border, badge or digit. Goes over the border: the text box (paths 0, 1)
        never overlaps it, so the original stacking is kept."""
        f = FRAME[style]
        paths, grads = self.frame(style)
        skip = {*f["border"], *f["badge"], *f["digit"]}
        pick(self.frame(style), f["digit"], ["#1c2a47"])   # check the digit is where we think
        return [(paths[i], grads) for i in range(len(paths)) if i not in skip]

    def badge_layers(self):
        """The clean value-1 badge split into shadow, fill (gradient + outline), shine (highlight, ring, star),
        plus the second star of the value-6 badge."""
        f1 = self.frame("clean")
        return {"shadow": pick(f1, [48], ["#000000"]),
                "fill": pick(f1, [49, 50], ["url", "#5c3017"]),
                "shine": pick(f1, [51, 52, 53], ["#fff8e3", "#4d3c13", "#fff8d1"]),
                "star": pick(self.frame("clean", 6), [104], ["#fff8d1"])}

    def badge(self, value):
        """The game's own badge for a value (clean style), with its digit: (badge paths, digit paths)."""
        if value == 6:
            f, r = self.frame("clean", 6), RARE_BADGE
        else:
            f, r = self.frame("clean", value), FRAME["clean"]
        return pick(f, r["badge"], ["#000000"]), pick(f, r["digit"], ["#1c2a47"])

    # --- board ----------------------------------------------------------------------------------------------

    def board(self, style):
        return self.swf(f"scenes/{STYLES[style]}/shared/cardGame/card_game.swf")

    def board_content(self, style):
        """(swf, content placement, its display list)."""
        swf = self.board(style)
        content = next(p for p in swf.root_frames[0].values() if p.get("name") == "content")
        return swf, content, swf.frames[content["char"]][0]

    def card_back(self, style):
        """The game snapshots the player's deck clip as the back of every face-down card (CardGame.setUpDeck),
        and the deck on the board is just those cards stacked: one asset."""
        swf, _, placed = self.board_content(style)
        return Composer(swf).svg(named(placed)["playerDeck"])

    def gem(self, color):
        """(swf, sprite id) of the gem socket animation, color "red" (player) or "yellow" (opponent)."""
        swf, _, placed = self.board_content("clean")
        tray = named(placed)["playerTray" if color == "red" else "enemyTray"]
        score = named(swf.frames[tray][0])["score"]
        return swf, named(swf.frames[score][0])["slot1"]

    def arrow(self, size):
        """One of the arrows on the card back (sprite 11 large, sprite 9 small)."""
        return Composer(self.board("clean")).svg({"large": "11", "small": "9"}[size])

    def logo(self, shine=True):
        """The MAF emblem from the card back (shape 18); without shine, its last 5 paths (the streaks) go."""
        text = Composer(self.board("clean")).svg("18")
        if shine:
            return text
        from swf import svg_of
        ps, grads = leaves(text)
        box = tuple(float(v) for v in re.search(r'viewBox="([^"]+)"', text)[1].split())
        return svg_of([(p, grads) for p in ps[:-5]], box)

    # --- files ------------------------------------------------------------------------------------------------

    def fonts(self):
        """{name: exported TTF path} for the fonts in FONTS, and the paths of every font in the shell."""
        tmp = os.path.join(self.tmp, "fonts")
        if not os.path.isdir(tmp):
            ffdec("-format", "font:ttf", "-export", "font", tmp, self.path("Shell.swf"))
        every = {int(fn.split("_", 1)[0]): os.path.join(d, fn) for d, _, fs in os.walk(tmp) for fn in fs if fn.endswith(".ttf")}
        return {name: every[fid] for fid, name in FONTS.items()}, list(every.values())

    def sound(self, kind, name):
        return self.path("sound", kind, f"{name}.mp3")


def art_name(x):
    return os.path.splitext(os.path.basename(x.find(".//asset[@id='cardContent']/assetPath").text))[0]


def named(display_list):
    return {p["name"]: p["char"] for p in display_list.values() if p.get("name")}


def pick(paths_and_grads, keep, expect):
    """Paths by index from leaves(), checked against expected fill/stroke fragments: [((path, matrix), gradients)]."""
    ps, grads = paths_and_grads
    out = [(ps[i], grads) for i in keep]
    got = ["%s %s" % (e.get("fill"), e.get("stroke")) for (e, _), _ in out]
    assert all(x in g for g, x in zip(got, expect)), (got, expect)
    return out


def origin(svg_text):
    """The SVG's top-left relative to its registration point (Sprite2D offset, centered = false)."""
    return [float(v) for v in re.search(r'viewBox="([-\d.]+) ([-\d.]+)', svg_text).groups()]


def decorations(placed):
    """Unnamed placements in a display list are static decoration (worn's damage overlay): map each to the named
    piece right below it, in that piece's local space, so it can be baked in without changing the stacking."""
    extras, below = {}, None
    for depth, p in sorted(placed.items()):
        if p.get("name"):
            below = p
        elif "char" in p:
            local = dict(p, matrix=mat_mul(mat_inv(below.get("matrix", IDENTITY)), p.get("matrix", IDENTITY)))
            extras.setdefault(below["name"], []).append(local)
    return extras


class Output:
    """Writes into a target's root folder."""

    def __init__(self, root):
        self.root = root

    def write(self, rel, text):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print("wrote", rel.replace(os.sep, "/"))

    def copy(self, src, rel):
        path = os.path.join(self.root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.copyfile(src, path)
        print("copied", rel.replace(os.sep, "/"))
