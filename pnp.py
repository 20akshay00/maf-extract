"""Target: the print-and-play project (MightyActionForceTCG-PnP).

  assets/svg/art/       character art, drawn around the card centre (0, 0) in card units
  assets/svg/frames/    clean.svg, worn.svg: the card frame (art border + body, no badge), card units
  assets/svg/badges/    badge_<value>.svg: the game's own badges, digits tagged class="dg"
  assets/svg/backs/     clean.svg, worn.svg: card backs
  assets/svg/pieces/    gem_red/yellow.svg (a filled gem socket), arrow_large/small.svg (from the card back)
  assets/fonts/         the three fonts the build uses
  data/original_cards.json   the game's cards (data/cards.json is left for custom cards)

The logo (assets/img/logo_card_game.png) isn't in the game files and isn't produced here.
"""
import json

from source import BADGE_BOX, CARD_BOX, STYLES
from swf import Composer, svg_of

FONTS = ["BillySerif", "CreativeBlockBB", "GrilledCheeseBTN-Wide"]


def cards(src, out):
    for name, svg in src.card_art().items():
        out.write(f"assets/svg/art/{name}.svg", svg)
    for style in STYLES:
        out.write(f"assets/svg/frames/{style}.svg", svg_of(src.frame_border(style) + src.frame_body(style), CARD_BOX))
        out.write(f"assets/svg/backs/{style}.svg", src.card_back(style))

    for value in (1, 2, 3, 4, 6):
        badge, digit = src.badge(value)
        # the build hides the game's digits (.dg) and draws the value as text; mark them on the way through svg_of
        for (el, _), _ in digit:
            el.set("data-dg", "1")
        text = svg_of(badge + digit, BADGE_BOX)
        for (el, _), _ in digit:
            del el.attrib["data-dg"]
        out.write(f"assets/svg/badges/badge_{value}.svg", text.replace(' data-dg="1"', ' class="dg"'))


def pieces(src, out):
    for color in ("red", "yellow"):
        swf, gem = src.gem(color)
        out.write(f"assets/svg/pieces/gem_{color}.svg", Composer(swf).svg(gem, swf.labels[gem]["hasGem"]))
    for size in ("large", "small"):
        out.write(f"assets/svg/pieces/arrow_{size}.svg", src.arrow(size))


def fonts(src, out):
    named_fonts, _ = src.fonts()
    for name in FONTS:
        out.copy(named_fonts[name], f"assets/fonts/{name}.ttf")


def data(src, out):
    keys = ("id", "style", "name", "value", "effect", "power_name", "description", "quotation")
    cards = [{k: c[k] for k in keys} | {"art": f"svg/art/{c['art']}.svg"} for c in src.cards()]
    out.write("data/original_cards.json",
              "[\n" + ",\n".join(" " + json.dumps(c, ensure_ascii=False) for c in cards) + "\n]\n")


STEPS = {"cards": cards, "pieces": pieces, "fonts": fonts, "data": data}
