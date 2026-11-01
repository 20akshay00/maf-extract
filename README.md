# maf-extract

Builds the art, fonts, sounds and card data of Poptropica's Mighty Action Force card game from your own copy of the
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
against the current files. Steps default to all of the target's (`python external/tools/extract.py -h` lists them).

## How it works

| File | What |
|---|---|
| `extract.py` | Command line |
| `swf.py` | Renders SWF characters to SVG, with JPEXS as the parser |
| `source.py` | What's where in Poptropica's files: card art, frame layers, badges, board, fonts, card data |
| `godot.py`, `pnp.py` | The two targets: which files each project gets, and where |

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
- The worn board only differs from the clean one in its background (and card back).

## Adding a target

Write a module with a `STEPS` dict of `step(src, out)` functions, where `src` is a `source.Source` and `out` an
`Output` (`out.write(path, text)`, `out.copy(file, path)`), and add it to `TARGETS` in `extract.py`.
