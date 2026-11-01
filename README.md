# maf-extract

[![Made with Claude Code](https://img.shields.io/badge/made_with-Claude_Code-D97757?logo=claude&logoColor=white)](https://claude.com/claude-code)

Extracts the art, fonts, sounds and card data of Poptropica's Mighty Action Force card game from your own copy of the
game files, for projects that can't redistribute them. It contains no Poptropica files, only the code that reads them.

## Use

Add this repository as a submodule at `external/maf-extract`, then from the project root:

```
python external/maf-extract/extract.py <godot|pnp> [steps ...] [--mirror DIR] [--out DIR]
```

- `godot`: might-action-force-tcg, a digital recreation in Godot
- `pnp`: [MightyActionForceTCG](https://github.com/20akshay00/MightyActionForceTCG), a print-and-play version

You need Python 3.10+, [JPEXS](https://github.com/jindrapetrik/jpexs-decompiler) (set `FFDEC` if `ffdec-cli` isn't
at `C:/Program Files (x86)/FFDec/ffdec-cli.exe`), and the Poptropica Flash files, e.g. from
[Flashpoint](https://flashpointarchive.org/): the folder holding `game/Shell.swf`, at `external/poptropica/` or
wherever `MAF_POPTROPICA` points. `--out` writes elsewhere, for comparing a rebuild with the current files.

## How it works

`extract.py` is the command line, `swf.py` renders SWF characters to SVG, `source.py` knows where everything is in the
game files, and `godot.py` / `pnp.py` decide what each project gets. To add a target, write a module with a `STEPS`
dict of `step(src, out)` functions and register it in `extract.py`.

JPEXS's own SVG export drops per-placement colour transforms, losing whole layers of some card art and the card back's
faded arrows. So `swf.py` replays each SWF's display list (from `-swf2xml`) over JPEXS's per-shape SVGs: alpha fades
become group opacity, tints are baked into the colours. JPEXS's PNG render (`-format frame:png`) is the reference.

Choices it makes (details in `source.py`):
- `clean` = con2 (the original game), `worn` = con3 (its battle-damaged reskin).
- Card frames are split from `background<N>.swf` by path index, with colour checks so a changed source fails loudly.
- The card back is the board's deck sprite, which the game snapshots for every face-down card.
- Value-6 cards (Omegon) get the normal frame with a purple border; the gold frame in con2's `background6.swf` is
  drawn over in the game and never shows.

## Where things are

Under the mirror's `game/`, with `<ep>` = `con2` or `con3`:

| What | Where |
|---|---|
| Card data | `data/items/<ep>/<card>.xml` (the game uses the file name, not the `id`) |
| Card art / frames and badges | `assets/items/<ep>/<card>.swf` / `background<value>.swf` |
| Board, card back | `assets/scenes/<ep>/shared/cardGame/card_game.swf` |
| Dialog window | `assets/scenes/<ep>/shared/cardGame/dialog_window.swf` |
| Deck organizer | `assets/scenes/con2/shared/popups/cardDeck.swf` |
| Opponents, lines, looks | `data/scenes/<ep>/shared/cardGame/ccgnpcs.xml`, `dialog.xml`, `npcs.xml` |
| Fonts, game code | `Shell.swf` |
| Sounds | `sound/effects/`, `sound/music/` |

Sprite IDs in `card_game.swf` (con2 / con3): layout 108 / 110, background 6 / 6 (+ damage overlay shape 7),
card back 20 / 21, dock 27 / 28, player attack and bounty 48, 68 / 69, 73, enemy attack and bounty 64, 72 / 49, 53,
trays 86, 94 / 87, 96, score tracks 83, 93 / 84, 95, gems 82, 92 / 83, 94, end popup 107 / 109. In con2 the logo is
shape 18 and the card-back arrows are sprites 11 and 9. The logo is the only MAF logo in the game files; the full card
game logo on the fan wiki isn't in them.
