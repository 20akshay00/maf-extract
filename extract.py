"""Build a project's Poptropica-derived files from your own copy of the game.

    python external/tools/extract.py <target> [steps ...] [--mirror DIR] [--out DIR]

target: godot (might-action-force-tcg) or pnp (MightyActionForceTCG-PnP). Steps default to all of the target's.
This folder is expected at <project>/external/tools, and the Poptropica mirror (the folder holding game/Shell.swf)
at $MAF_POPTROPICA or <project>/external/poptropica; --mirror and --out override those. Needs Python 3.10+ and JPEXS ffdec-cli
(FFDEC env var, default C:/Program Files (x86)/FFDec/ffdec-cli.exe).
"""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import godot
import pnp
from source import Output, Source

TARGETS = {"godot": godot, "pnp": pnp}
PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target", choices=TARGETS)
    ap.add_argument("steps", nargs="*", help="; ".join(f"{t}: {', '.join(m.STEPS)}" for t, m in TARGETS.items()))
    ap.add_argument("--mirror", default=os.environ.get("MAF_POPTROPICA") or os.path.join(PROJECT, "external", "poptropica"),
                    help="the Poptropica mirror (default: $MAF_POPTROPICA, else <project>/external/poptropica)")
    ap.add_argument("--out", default=PROJECT, help="root to write into (default: the project)")
    args = ap.parse_args()
    steps = TARGETS[args.target].STEPS
    if unknown := set(args.steps) - set(steps):
        ap.error(f"unknown {args.target} steps: {', '.join(sorted(unknown))}")
    with tempfile.TemporaryDirectory() as tmp:
        src, out = Source(args.mirror, tmp), Output(os.path.abspath(args.out))
        for step in args.steps or steps:
            print(f"== {step}")
            steps[step](src, out)


if __name__ == "__main__":
    main()
