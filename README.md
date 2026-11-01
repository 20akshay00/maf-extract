# maf-extract

[![Made with Claude Code](https://img.shields.io/badge/made_with-Claude_Code-D97757?logo=claude&logoColor=white)](https://claude.com/claude-code)

Extracts the art, fonts, sounds and card data of Poptropica's Mighty Action Force card game from your own copy of the
game files, for projects that can't redistribute them:

- `godot`: might-action-force-tcg, a digital recreation in Godot
- `pnp`: [MightyActionForceTCG](https://github.com/20akshay00/MightyActionForceTCG), a print-and-play version

Nothing from Poptropica is in this repository; it only contains the code that reads the game's Flash files.

## Use

Each project includes this repository as a git submodule at `external/tools`. From the project root:

```
python external/tools/extract.py <godot|pnp> [steps ...] [--mirror DIR] [--out DIR]
```

You need:

- **The Poptropica Flash files**, for example from [Flashpoint](https://flashpointarchive.org/): the mirror folder
  that holds `game/Shell.swf`. Put it at `external/poptropica/` in the project, or point the `MAF_POPTROPICA`
  environment variable at it to share one copy between projects.
- **[JPEXS Free Flash Decompiler](https://github.com/jindrapetrik/jpexs-decompiler)**. If `ffdec-cli` isn't at
  `C:/Program Files (x86)/FFDec/ffdec-cli.exe`, set the `FFDEC` environment variable to it.
- **Python 3.10+**, standard library only.

`--out` writes the files under another folder instead of the project, which is handy for comparing a rebuild
against the current files. 

## How it works

| File                 | What                                                                                        |
| -------------------- | ------------------------------------------------------------------------------------------- |
| `extract.py`         | Command line                                                                                |
| `swf.py`             | Renders SWF characters to SVG, with JPEXS as the parser                                     |
| `source.py`          | What's where in Poptropica's files: card art, frame layers, badges, board, fonts, card data |
| `godot.py`, `pnp.py` | The two targets: which files each project gets, and where                                   |

**Why not JPEXS's own SVG export?** It drops per-placement colour transforms (fades and tints): whole background
layers of some card art (Fashion Ninja's smoke, Pony Girl's backdrop), the faded arrows on the card back, the dimmed
empty gem sockets. `swf.py` simulates each SWF's display list from JPEXS's `-swf2xml` dump and composes JPEXS's
per-shape SVGs itself. Alpha fades become group opacity (Flash's "layer" blend), and tints are baked into the colours.
Check any new extraction against JPEXS's PNG render (`-format frame:png`), which does apply them.

**Card frames** are split out of the `background<N>.swf` files by path index: text box, art window, art border, the
rest of the frame, the value badge, then its digit, in paint order. `source.py` checks the colours of every path it
picks, so a different source file fails loudly instead of producing a wrong split.

**Choices it makes**, all documented in `source.py`:
- Style names map to episodes: `clean` = con2 (the original game), `worn` = con3 (its battle-damaged reskin).
- The card back is the board's deck sprite: the game snapshots it for every face-down card (`CardGame.setUpDeck`).
- Value-6 cards (Omegon) use the normal frame with a purple art border. con2's `background6.swf` also holds a gold
  frame, but the normal frame is drawn over it and the game's card renderer adds the whole file, so it never shows.
- The logo is the MAF emblem from the card back, the only MAF logo in the game files (there's no "Mighty Action
  Force" wordmark in the comics, popups or banners). The full card game logo on the fan wiki isn't in them.

## Where things are in the game files

Paths are under the mirror's `game/`; `<ep>` is `con2` or `con3`.

| What                             | Where                                                                                                 |
| -------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Card data                        | `data/items/<ep>/<card>.xml` (the game uses the file name; three files have a copy-pasted wrong `id`) |
| Card art                         | `assets/items/<ep>/<card>.swf`                                                                        |
| Card frames, value badges        | `assets/items/<ep>/background<value>.swf`                                                             |
| Board, card back                 | `assets/scenes/<ep>/shared/cardGame/card_game.swf`                                                    |
| Dialog window                    | `assets/scenes/<ep>/shared/cardGame/dialog_window.swf` (same art in both episodes)                    |
| Deck organizer                   | `assets/scenes/con2/shared/popups/cardDeck.swf`                                                       |
| Opponents, their lines and looks | `data/scenes/<ep>/shared/cardGame/ccgnpcs.xml`, `dialog.xml`, `npcs.xml`                              |
| Fonts, game code                 | `Shell.swf`                                                                                           |
| Sounds                           | `sound/effects/`, `sound/music/`                                                                      |

Sprite IDs in `card_game.swf`, for going back to the source with JPEXS:

| Piece                                          | con2 ID    | con3 ID                           |
| ---------------------------------------------- | ---------- | --------------------------------- |
| Whole layout (`content`)                       | 108        | 110                               |
| Background (`bg`)                              | 6          | 6 (+ shape 7, the damage overlay) |
| Deck / card back                               | 20         | 21                                |
| Dock                                           | 27         | 28                                |
| Player attack / bounty                         | 48 / 68    | 69 / 73                           |
| Enemy attack / bounty                          | 64 / 72    | 49 / 53                           |
| Player / enemy tray                            | 86 / 94    | 87 / 96                           |
| Player / enemy score track                     | 83 / 93    | 84 / 95                           |
| Red / yellow gem                               | 82 / 92    | 83 / 94                           |
| End popup (`splash_mc`)                        | 107        | 109                               |
| Logo (shape) / card-back arrows (large, small) | 18 / 11, 9 | –                                 |

## Adding a target

Write a module with a `STEPS` dict of `step(src, out)` functions, where `src` is a `source.Source` and `out` an
`Output` (`out.write(path, text)`, `out.copy(file, path)`), and add it to `TARGETS` in `extract.py`.
