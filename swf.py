"""Render SWF characters to SVG with JPEXS (ffdec) as the parser.

JPEXS's own SVG export drops per-placement colour transforms (faded arrows, dimmed sockets), so characters are
composed here from its per-shape SVGs and the SWF's display lists (from -swf2xml): alpha fades become group
opacity (Flash's "layer" blend), tints are baked into the colours.
"""
import copy, json, os, re, subprocess, sys, tempfile
import xml.etree.ElementTree as ET

FFDEC = os.environ.get("FFDEC", r"C:/Program Files (x86)/FFDec/ffdec-cli.exe")
NS, XL = "http://www.w3.org/2000/svg", "http://www.w3.org/1999/xlink"
ET.register_namespace("", NS)
ET.register_namespace("xlink", XL)

def ffdec(*args):
    subprocess.run([FFDEC, *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class Swf:
    """Characters and per-frame display lists of one SWF, plus ffdec's per-shape/per-sprite SVGs."""

    def __init__(self, path, tmp):
        self.tmp = tmp
        ffdec("-format", "shape:svg,sprite:svg", "-export", "shape,sprite", tmp, path)
        ffdec("-swf2xml", path, os.path.join(tmp, "swf.xml"))
        root = ET.parse(os.path.join(tmp, "swf.xml")).getroot()
        r = root.find("displayRect")
        self.stage = (int(r.get("Xmax")) / 20, int(r.get("Ymax")) / 20)
        self.kind, self.frames, self.labels, self.texts, self.grids = {}, {}, {}, {}, {}
        tags = root.find("tags")
        for t in tags:
            ty = t.get("type")
            if ty.startswith("DefineShape"):
                self.kind[t.get("shapeId")] = "shape"
            elif ty == "DefineEditTextTag":
                cid = t.get("characterID")
                self.kind[cid] = "text"
                b = t.find("bounds")
                self.texts[cid] = {"rect": [int(b.get(k)) / 20 for k in ("Xmin", "Ymin", "Xmax", "Ymax")],
                                   "font_size": int(t.get("fontHeight")) / 20}
            elif ty == "DefineSpriteTag":
                sid = t.get("spriteId")
                self.kind[sid] = "sprite"
                self.frames[sid], self.labels[sid] = self._timeline(t.find("subTags"))
            elif ty == "DefineScalingGridTag":
                g = t.find("splitter")
                self.grids[t.get("characterId")] = [int(g.get(k)) / 20 for k in ("Xmin", "Ymin", "Xmax", "Ymax")]
        self.root_frames, _ = self._timeline(tags)

    @staticmethod
    def _timeline(tags):
        """Display list ({depth: placement}) after each ShowFrame, and frame labels."""
        frames, labels, dl = [], {}, {}
        for t in tags:
            ty = t.get("type")
            if ty in ("PlaceObject2Tag", "PlaceObject3Tag"):
                d = int(t.get("depth"))
                p = dict(dl[d]) if t.get("placeFlagMove") == "true" and d in dl else {}
                if t.get("characterId") is not None and t.get("placeFlagHasCharacter") == "true":
                    if p.get("char") != t.get("characterId"):
                        p["start"] = len(frames)  # nested timelines play from where they're placed
                    p["char"] = t.get("characterId")
                if t.get("name"):
                    p["name"] = t.get("name")
                if (m := t.find("matrix")) is not None:
                    p["matrix"] = (float(m.get("scaleX", 1)) if m.get("hasScale") == "true" else 1.0,
                                   float(m.get("rotateSkew0", 0)), float(m.get("rotateSkew1", 0)),
                                   float(m.get("scaleY", 1)) if m.get("hasScale") == "true" else 1.0,
                                   int(m.get("translateX")) / 20, int(m.get("translateY")) / 20)
                if (c := t.find("colorTransform")) is not None:
                    mult = [int(c.get(k + "MultTerm", 256)) / 256 for k in ("red", "green", "blue", "alpha")] \
                        if c.get("hasMultTerms") == "true" else [1.0] * 4
                    add = [int(c.get(k + "AddTerm", 0)) / 255 for k in ("red", "green", "blue", "alpha")] \
                        if c.get("hasAddTerms") == "true" else [0.0] * 4
                    p["cx"] = (mult, add)
                dl[d] = p
            elif ty in ("RemoveObjectTag", "RemoveObject2Tag"):
                dl.pop(int(t.get("depth")), None)
            elif ty == "FrameLabelTag":
                labels[t.get("name").split(",")[0].strip()] = len(frames)
            elif ty == "ShowFrameTag":
                frames.append({d: dict(p) for d, p in dl.items()})
        return frames, labels

    def bounds(self, cid, frame=0):
        """(x, y, w, h) of a shape/sprite in its own coordinates, from ffdec's export."""
        if self.kind[cid] == "text":
            x0, y0, x1, y1 = self.texts[cid]["rect"]
            return x0, y0, x1 - x0, y1 - y0
        path = os.path.join(self.tmp, "shapes", f"{cid}.svg") if self.kind[cid] == "shape" \
            else os.path.join(self.tmp, "sprites", f"DefineSprite_{cid}", f"{frame + 1}.svg")
        head = open(path, encoding="utf-8").read(600)
        w, h = (float(v) for v in re.search(r'height="([\d.]+)px" width="([\d.]+)px"', head).groups()[::-1])
        tx, ty = (float(v) for v in re.search(r"<g transform=\"matrix\([^,]+,[^,]+,[^,]+,[^,]+, ([-\d.]+), ([-\d.]+)\)", head).groups())
        return -tx, -ty, w, h


IDENTITY = (1, 0, 0, 1, 0, 0)


def mat_mul(p, m):
    """p after m (both SVG-style a, b, c, d, e, f)."""
    a, b, c, d, e, f = p
    return (a * m[0] + c * m[1], b * m[0] + d * m[1], a * m[2] + c * m[3], b * m[2] + d * m[3],
            a * m[4] + c * m[5] + e, b * m[4] + d * m[5] + f)


def mat_inv(m):
    a, b, c, d, e, f = m
    det = a * d - b * c
    return (d / det, -b / det, -c / det, a / det, (c * f - d * e) / det, (b * e - a * f) / det)


def rect_of(m, x, y, w, h):
    pts = [(m[0] * px + m[2] * py + m[4], m[1] * px + m[3] * py + m[5])
           for px, py in ((x, y), (x + w, y), (x, y + h), (x + w, y + h))]
    xs, ys = [q[0] for q in pts], [q[1] for q in pts]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def mul_cx(child, parent):
    """Flash colour transform concatenation: parent(child(c))."""
    (m1, a1), (m2, a2) = child, parent
    return [x * y for x, y in zip(m1, m2)], [a * m + b for a, m, b in zip(a1, m2, a2)]


def tint(color, cx):
    c = color.lstrip("#")
    rgb = [int(c[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    out = [min(1, max(0, v * m + a)) for v, m, a in zip(rgb, cx[0], cx[1])]
    return "#" + "".join(f"{round(v * 255):02x}" for v in out)


class Composer:
    def __init__(self, swf):
        self.swf, self.uid = swf, 0
        self.shape_cache = {}

    def _shape(self, cid):
        if cid not in self.shape_cache:
            txt = open(os.path.join(self.swf.tmp, "shapes", f"{cid}.svg"), encoding="utf-8").read()
            txt = re.sub(r'\s+ffdec:[\w-]+="[^"]*"', "", txt)
            root = ET.fromstring(txt)
            g = root.find(f"{{{NS}}}g")
            defs = root.find(f"{{{NS}}}defs")
            self.shape_cache[cid] = (list(g), list(defs) if defs is not None else [])
        return self.shape_cache[cid]

    def render(self, cid, frame, cx, defs):
        """SVG <g> for a character in its own coordinates. cx = composed RGB tint (alpha is done with opacity)."""
        g = ET.Element(f"{{{NS}}}g")
        kind = self.swf.kind.get(cid)
        if kind == "shape":
            paths, grads = self._shape(cid)
            self.uid += 1
            rename = {}
            for gr in grads:
                gr = copy.deepcopy(gr)
                new = f"g{self.uid}_{gr.get('id')}"
                rename[gr.get("id")] = new
                gr.set("id", new)
                for s in gr.iter(f"{{{NS}}}stop"):
                    if cx and s.get("stop-color"):
                        s.set("stop-color", tint(s.get("stop-color"), cx))
                defs.append(gr)
            for p in paths:
                p = copy.deepcopy(p)
                for el in p.iter():
                    for attr in ("fill", "stroke"):
                        v = el.get(attr, "")
                        if v.startswith("url(#"):
                            el.set(attr, "url(#%s)" % rename[v[5:-1]])
                        elif cx and v.startswith("#"):
                            el.set(attr, tint(v, cx))
                g.append(p)
        elif kind == "sprite":
            frames = self.swf.frames[cid]
            for depth, p in sorted(frames[min(frame, len(frames) - 1)].items()):
                self.place(g, p, cx, defs, frame)
        return g

    def place(self, g, p, cx, defs, parent_frame=0):
        """Append one display-list placement (matrix, colour transform, character) to g."""
        if "char" not in p or self.swf.kind.get(p["char"]) == "text":
            return
        child = ET.SubElement(g, f"{{{NS}}}g")
        if "matrix" in p:
            child.set("transform", "matrix(%s)" % ", ".join("%g" % round(v, 5) for v in p["matrix"]))
        if "cx" in p:
            mult, add = p["cx"]
            assert add[3] == 0, "alpha add terms not supported"
            if mult[3] != 1:
                child.set("opacity", "%g" % round(mult[3], 4))
            rgb = ([*mult[:3], 1.0], [*add[:3], 0.0])
            if rgb != ([1.0] * 4, [0.0] * 4):
                cx = mul_cx(rgb, cx) if cx else rgb
        frame = 0
        if self.swf.kind.get(p["char"]) == "sprite":  # looping child timeline
            frame = (parent_frame - p.get("start", 0)) % len(self.swf.frames[p["char"]])
        child.extend(list(self.render(p["char"], frame, cx, defs)))

    def svg(self, cid, frame=0, extras=()):
        """A character as a standalone SVG. extras: placements (in its local space) drawn on top of it."""
        x0, y0, w, h = self.swf.bounds(cid, frame)
        x1, y1 = x0 + w, y0 + h
        for p in extras:
            ex, ey, ew, eh = rect_of(p.get("matrix", IDENTITY), *self.swf.bounds(p["char"]))
            x0, y0, x1, y1 = min(x0, ex), min(y0, ey), max(x1, ex + ew), max(y1, ey + eh)
        w, h = x1 - x0, y1 - y0
        svg = ET.Element(f"{{{NS}}}svg", {"width": "%g" % w, "height": "%g" % h,
                                          "viewBox": "%g %g %g %g" % (x0, y0, w, h)})
        defs = ET.SubElement(svg, f"{{{NS}}}defs")
        g = self.render(cid, frame, None, defs)
        for p in extras:
            self.place(g, p, None, defs)
        svg.append(g)
        ET.indent(svg)
        return ET.tostring(svg, encoding="unicode")

    def svg_root(self, viewbox, frame=0):
        """The SWF's root timeline at a frame, cropped to viewbox (x, y, w, h)."""
        x, y, w, h = viewbox
        svg = ET.Element(f"{{{NS}}}svg", {"width": "%g" % w, "height": "%g" % h,
                                          "viewBox": "%g %g %g %g" % (x, y, w, h)})
        defs = ET.SubElement(svg, f"{{{NS}}}defs")
        g = ET.SubElement(svg, f"{{{NS}}}g")
        for depth, p in sorted(self.swf.root_frames[frame].items()):
            self.place(g, p, None, defs, frame)
        ET.indent(svg)
        return ET.tostring(svg, encoding="unicode")


def layout(swf, display_list, matrix=IDENTITY, path=""):
    """Every named instance (and text field) in a display list, recursively: transform and bounding rect."""
    out = {}
    for depth, p in sorted(display_list.items()):
        if "char" not in p:
            continue
        world = mat_mul(matrix, p.get("matrix", IDENTITY))
        name = p.get("name") or ("text" if swf.kind[p["char"]] == "text" else None)
        key = f"{path}/{name}" if name else path
        if name:
            entry = {"position": [round(world[4], 2), round(world[5], 2)],
                     "scale": [round(world[0], 4), round(world[3], 4)],
                     "rect": [round(v, 2) for v in rect_of(world, *swf.bounds(p["char"]))]}
            if swf.kind[p["char"]] == "text":
                entry["font_size"] = round(swf.texts[p["char"]]["font_size"] * world[3], 2)
            out[key.lstrip("/")] = entry
        if swf.kind[p["char"]] == "sprite":
            out.update(layout(swf, swf.frames[p["char"]][0], world, key))
    return out


def leaves(svg_text):
    """Every <path> of an SVG in paint order, with its accumulated transform: [(element, matrix)].
    Used to pick paths out of a composed SVG by index (the order follows the SWF's depths and shape records)."""
    root = ET.fromstring(svg_text)
    defs = {e.get("id"): e for e in root.iter() if e.get("id")}

    def matrix(el):
        v = [float(x) for x in re.findall(r"-?[\d.]+(?:e-?\d+)?", el.get("transform", ""))]
        return tuple(v) if len(v) == 6 else IDENTITY

    def walk(el, m):
        tag = el.tag.split("}")[1]
        if tag == "defs":
            return
        m = mat_mul(m, matrix(el))
        if tag == "use":
            yield from walk(defs[el.get(f"{{{XL}}}href")[1:]], m)
        elif tag == "path":
            yield el, m
        else:
            for c in el:
                yield from walk(c, m)
    return list(walk(root, IDENTITY)), {e.get("id"): e for e in root.iter() if e.tag.endswith("Gradient")}


def svg_of(items, viewbox, recolor=None):
    """A standalone SVG from (path, matrix) items picked out of leaves(), with the gradients they use."""
    x, y, w, h = viewbox
    svg = ET.Element(f"{{{NS}}}svg", {"width": "%g" % w, "height": "%g" % h, "viewBox": "%g %g %g %g" % viewbox})
    defs = ET.SubElement(svg, f"{{{NS}}}defs")
    seen = set()
    for (el, m), grads in items:
        el = copy.deepcopy(el)
        el.attrib.pop("transform", None)
        if m != IDENTITY:
            el.set("transform", "matrix(%s)" % ", ".join("%g" % round(v, 5) for v in m))
        for attr in ("fill", "stroke"):
            ref = re.fullmatch(r"url\(#(.+)\)", el.get(attr, ""))
            if ref and ref[1] not in seen:
                seen.add(ref[1])
                g = copy.deepcopy(grads[ref[1]])
                if recolor:
                    recolor(g)
                defs.append(g)
        if recolor:
            recolor(el)
        svg.append(el)
    if not len(defs):
        svg.remove(defs)
    ET.indent(svg)
    return ET.tostring(svg, encoding="unicode")
