"""Draw the STPA control structure in a SysML v2 model as a standalone SVG.

Writes an SVG image, D2 diagram source (https://d2lang.com), Mermaid, or Markdown with a Mermaid
block, chosen by the output file's suffix.

Reads the parts marked #controller / #controllerHuman / #actuator / #sensor / #process and
the flows marked #controlAction / #feedback or typed `: ControlAction` / `: Feedback`, with
their two `end ::> part;` ends, using the same sysml2py parse as trace_check.py. Layout
follows STPA convention: controllers at the top, controlled processes at the bottom, control
actions pointing down, feedback pointing up.

Usage (from trace-example/):
    ../.venv/bin/python tools/control_structure.py        # model/*.sysml -> control_structure.svg, .d2, .md
    ../.venv/bin/python tools/control_structure.py FILE.sysml -o out.svg -o out.d2 -o out.mmd

It also prints the structure as a table. Like trace_check.py it does no name resolution:
flow ends are matched to parts by their last name segment.
"""
import argparse, re, sys
from html import escape
from pathlib import Path

from trace_check import ROOT, ModelSyntaxError, marked_keywords, nodes, parse, unquote

PART_KINDS = {"controller": "controller", "controllerHuman": "human controller",
              "actuator": "actuator", "sensor": "sensor", "process": "process"}
FLOW_KINDS = {"controlAction": "control action", "feedback": "feedback"}
# Categorical slots 1-3 of the dataviz reference palette (validated all-pairs, light and dark).
# Actuators and sensors share a colour; the kind is written in every box.
GROUP = {"controller": 1, "human controller": 1, "actuator": 2, "sensor": 2, "process": 3,
         "undeclared": 0}

NODE_H, ROW_GAP, NODE_GAP, PAD, PORT_GAP, LABEL_PAD = 48, 44, 28, 24, 32, 8


# ---- Reading the model ------------------------------------------------------------------

# Flows can also be typed by the library definitions instead of marked with a keyword:
# `flow x : Feedback`. That avoids #feedback's sensor-to-controller restriction.
FLOW_TYPES = {"Feedback": "feedback", "ControlAction": "controlAction"}


def stpa_usages(tree, ancestors=()):
    """Yield (keyword, name, ancestors, body) for metadata-marked usages and for flows typed by
    a library flow definition, with the names of the STPA parts that enclose each one."""
    if isinstance(tree, list):
        for v in tree:
            yield from stpa_usages(v, ancestors)
        return
    if not isinstance(tree, dict):
        return
    metas = marked_keywords(tree)
    if metas:
        ident = next(nodes(tree["usage"].get("declaration"), "Identification"), {})
        # Same sysml2py 0.5.3 quirk as in trace_check.stpa_elements: without a short name,
        # the element's name is read as the last metadata keyword.
        name = unquote(ident.get("declaredName") or (metas[-1] if len(metas) > 2 else None))
        yield metas[0], name, ancestors, tree["usage"].get("completion")
        if metas[0] in PART_KINDS:
            ancestors = ancestors + (name,)
        yield from stpa_usages(tree["usage"].get("completion"), ancestors)
        return
    if tree.get("name") == "FlowConnectionUsage":
        decl = next(nodes(tree["declaration"], "FeatureDeclaration"), {})
        types = [q["names"][-1] for t in nodes(decl.get("specialization"), "FeatureType")
                 for q in nodes(t, "QualifiedName")]
        kw = next((FLOW_TYPES[t] for t in types if t in FLOW_TYPES), None)
        if kw:
            yield kw, unquote((decl.get("identification") or {}).get("declaredName")), ancestors, tree.get("body")
            return
    for v in tree.values():
        yield from stpa_usages(v, ancestors)


def flow_ends(body):
    ends = []
    for ref in nodes(body, "DefaultReferenceUsage"):
        if (ref.get("prefix") or {}).get("isEnd"):
            chain = [unquote(c["chainingFeature"]["names"][-1]) for c in nodes(ref, "OwnedFeatureChaining")]
            ends.append(chain[-1] if chain else None)
    return ends


def read_structure(trees):
    """Return (title, parts, flows, warnings). parts: name -> {kind, within}; flows: list of
    {kind, name, src, dst}."""
    parts, flows, warnings, titles = {}, [], [], []
    for tree in trees:
        for kw, name, ancestors, body in stpa_usages(tree):
            if kw == "controlStructure":
                titles.append(name)
            elif kw in PART_KINDS:
                parts[name] = {"kind": PART_KINDS[kw], "within": ".".join(ancestors)}
            elif kw in FLOW_KINDS:
                ends = flow_ends(body)
                if len(ends) != 2 or None in ends:
                    warnings.append(f"{FLOW_KINDS[kw]} {name}: needs exactly two ends, found {len(ends)}; skipped")
                    continue
                flows.append({"kind": FLOW_KINDS[kw], "name": name, "src": ends[0], "dst": ends[1]})
    for f in flows:
        for end in (f["src"], f["dst"]):
            if end not in parts:
                parts[end] = {"kind": "undeclared", "within": ""}
                warnings.append(f"{f['kind']} {f['name']}: end {end} is not a marked STPA part")
    # A part that only groups other parts (Ushift in ExampleSTPA) and has no flows of its own
    # would float unconnected; leave it out and name its container in its children's boxes.
    used = {e for f in flows for e in (f["src"], f["dst"])}
    containers = {a for p in parts.values() for a in p["within"].split(".") if a}
    for name in [n for n in parts if n in containers and n not in used]:
        del parts[name]
    return (", ".join(titles) or None), parts, flows, warnings


def merge_parallel(flows):
    """One flow per (kind, source, target), its name listing every merged flow on its own line.
    Two control actions from the same controller to the same process draw as one arrow."""
    merged = {}
    for f in flows:
        key = (f["kind"], f["src"], f["dst"])
        if key in merged:
            merged[key]["name"] += "\n" + f["name"]
        else:
            merged[key] = dict(f)
    return list(merged.values())


# ---- Layout -------------------------------------------------------------------------------

def levels(parts, flows):
    """STPA rows: control actions point down; sensors sit just below the controller they feed;
    processes go to the bottom row."""
    ca = [(f["src"], f["dst"]) for f in flows if f["kind"] == "control action"]
    has_ca_in = {d for _, d in ca}
    level = {n: 0 for n, p in parts.items() if p["kind"] in ("controller", "human controller")
             and n not in has_ca_in}
    for _ in range(len(parts)):  # longest path; the bound stops on control-action cycles
        for s, d in ca:
            if s in level and level.get(d, -1) < level[s] + 1:
                level[d] = level[s] + 1
    for f in flows:
        if f["kind"] == "feedback" and f["src"] not in level and f["dst"] in level:
            level[f["src"]] = min(level[f["dst"]] + 1, level.get(f["src"], 99))
    for n in parts:
        level.setdefault(n, 0)
    bottom = max([level[n] for n, p in parts.items() if p["kind"] != "process"] + [-1]) + 1
    for n, p in parts.items():
        if p["kind"] == "process":
            level[n] = max(level[n], bottom)
    return level


def text_w(s, size):
    return len(s) * size * 0.6  # rough advance width for a sans-serif font


def layout(parts, flows):
    """Layered layout. Node rows sit on even layers; every edge gets waypoints on the layers in
    between. The middle waypoint also holds the label, beside the line: control-action labels
    to its left, feedback labels to its right. Its width reserves room for the label, so labels
    never overlap, and its `off` says where the line runs relative to the waypoint's centre.
    Lines are aligned on those line positions, which keeps them straight."""
    level = levels(parts, flows)
    items = {}  # id -> {layer, w, kind ('node'|'way'), ...}
    for n, p in parts.items():
        sub = p["kind"] + (f" · in {p['within']}" if p["within"] else "")
        # Wide enough for the text, and for every attached line to get its own spot on a side.
        ends = sum((f["src"] == n) + (f["dst"] == n) for f in flows)
        items[n] = {"layer": 2 * level[n], "type": "node", "sub": sub,
                    "w": max(max(text_w(n, 13) + 7, text_w(sub, 11)) + 2 * 12, (ends + 1) * PORT_GAP)}
    edges = []
    for i, f in enumerate(flows):
        a, b = items[f["src"]]["layer"], items[f["dst"]]["layer"]
        between = list(range(a + 1, b)) if b > a else list(range(a - 1, b, -1)) if b < a else [a + 1]
        gaps = [l for l in between if l % 2]  # odd layers are the gaps between node rows
        label_layer = gaps[len(gaps) // 2]
        ways = []
        for l in between:
            wid = f"~{i}.{l}"
            if l == label_layer:
                w = max(text_w(t, 11) for t in f["name"].split("\n")) + 2 * LABEL_PAD
                left = f["kind"] == "control action"  # label side: actions left, feedback right
                items[wid] = {"layer": l, "w": w, "type": "way", "label": True,
                              "side": "left" if left else "right", "off": (w / 2) * (1 if left else -1)}
            else:
                items[wid] = {"layer": l, "w": 10, "type": "way", "label": False, "off": 0}
            ways.append(wid)
        edges.append({**f, "chain": [f["src"], *ways, f["dst"]]})

    n_layers = max(it["layer"] for it in items.values()) + 1
    rows = [[] for _ in range(n_layers)]
    # Start with declaration order, control-action waypoints left of feedback ones.
    for iid, it in items.items():
        rows[it["layer"]].append(iid)
    kind_of = {w: e["kind"] for e in edges for w in e["chain"][1:-1]}
    for r in rows:
        r.sort(key=lambda i: 0 if kind_of.get(i) == "control action" else 1 if i in parts else 2)
    nbrs = {i: set() for i in items}
    for e in edges:
        for u, v in zip(e["chain"], e["chain"][1:]):
            nbrs[u].add(v)
            nbrs[v].add(u)

    def place():
        x = {}
        for r in rows:
            cur = 0
            for i in r:
                x[i] = cur + items[i]["w"] / 2
                cur += items[i]["w"] + NODE_GAP
        return x

    segs = [[] for _ in range(n_layers)]  # segs[l]: edge pieces between layer l and l + 1
    for e in edges:
        for u, v in zip(e["chain"], e["chain"][1:]):
            segs[min(items[u]["layer"], items[v]["layer"])].append((u, v))

    def crossings(l_range=None):
        pos = {i: k for r in rows for k, i in enumerate(r)}
        total = 0
        for l in (l_range if l_range is not None else range(n_layers)):
            s = [(pos[u], pos[v]) if items[u]["layer"] == l else (pos[v], pos[u]) for u, v in segs[l]]
            total += sum(1 for a in range(len(s)) for b in range(a + 1, len(s))
                         if (s[a][0] - s[b][0]) * (s[a][1] - s[b][1]) < 0)
        return total

    # Barycenter sweeps, keeping the ordering with the fewest crossings...
    best, best_rows = crossings(), [r[:] for r in rows]
    for sweep in range(24):
        x = place()
        order = range(n_layers) if sweep % 2 == 0 else range(n_layers - 1, -1, -1)
        for l in order:
            def bary(i):
                ns = [x[n] for n in nbrs[i]]
                return sum(ns) / len(ns) if ns else x[i]
            rows[l].sort(key=bary)
        if crossings() < best:
            best, best_rows = crossings(), [r[:] for r in rows]
    rows = best_rows
    # ...then swap neighbours while that removes crossings.
    improved = True
    while improved and best:
        improved = False
        for l, r in enumerate(rows):
            near = range(max(l - 1, 0), l + 1)
            for k in range(len(r) - 1):
                before = crossings(near)
                r[k], r[k + 1] = r[k + 1], r[k]
                if crossings(near) < before:
                    improved, best = True, crossings()
                else:
                    r[k], r[k + 1] = r[k + 1], r[k]

    # Coordinates: line up each item's line position (its centre, for boxes) with the mean of
    # its neighbours' line positions, keeping order and spacing.
    # A waypoint aims for the midpoint of its edge's two end boxes rather than its immediate
    # neighbours, so every waypoint of a long edge aims for the same x and the edge runs straight.
    off = {i: items[i].get("off", 0) for i in items}
    ends_of = {w: (e["chain"][0], e["chain"][-1]) for e in edges for w in e["chain"][1:-1]}

    def want_x(i):
        if i in ends_of:
            a, b = ends_of[i]
            return (x[a] + x[b]) / 2 - off[i]
        return sum(x[n] + off[n] for n in nbrs[i]) / len(nbrs[i]) - off[i] if nbrs[i] else x[i]

    # Straighten long edges: put all of an edge's waypoints on one x, taken from the range that
    # is free in every row the edge crosses, as close as possible to the midpoint of its ends.
    pos = {i: (l, k) for l, r in enumerate(rows) for k, i in enumerate(r)}

    def free(i):
        """Range of line positions item i can take without touching its row neighbours."""
        l, k = pos[i]
        r, w = rows[l], items[i]["w"]
        lo = x[r[k - 1]] + items[r[k - 1]]["w"] / 2 + NODE_GAP + w / 2 if k > 0 else -1e9
        hi = x[r[k + 1]] - items[r[k + 1]]["w"] / 2 - NODE_GAP - w / 2 if k + 1 < len(r) else 1e9
        return lo + off[i], hi + off[i]

    def straighten():
        for e in edges:
            ways = e["chain"][1:-1]
            if len(ways) < 2:
                continue
            ranges = [free(w) for w in ways]
            lo, hi = max(r[0] for r in ranges), min(r[1] for r in ranges)
            if lo <= hi:
                target = min(max((x[e["chain"][0]] + x[e["chain"][-1]]) / 2, lo), hi)
                for w in ways:
                    x[w] = target - off[w]

    x = place()
    for it_ in range(60):
        if it_ % 5 == 4:
            straighten()
        for r in rows:
            want = [want_x(i) for i in r]
            fwd, edge = [], -1e9  # packed left to right, then right to left; average the two
            for i, wx in zip(r, want):
                fwd.append(max(wx, edge + NODE_GAP + items[i]["w"] / 2))
                edge = fwd[-1] + items[i]["w"] / 2
            back, edge = [], 1e9
            for i, wx in zip(reversed(r), reversed(want)):
                back.append(min(wx, edge - NODE_GAP - items[i]["w"] / 2))
                edge = back[-1] - items[i]["w"] / 2
            for i, a, b in zip(r, fwd, reversed(back)):
                x[i] = (a + b) / 2
    straighten()

    # Widen boxes to take in the lines attached to them, as far as the row has room, so those
    # lines can meet the box straight instead of jogging at its edge.
    for n in parts:
        lines = [x[w] + off[w] for w in nbrs[n]]
        if not lines:
            continue
        l, k = pos[n]
        left, right = x[n] - items[n]["w"] / 2, x[n] + items[n]["w"] / 2
        room_l = x[rows[l][k - 1]] + items[rows[l][k - 1]]["w"] / 2 + NODE_GAP if k > 0 else -1e9
        room_r = x[rows[l][k + 1]] - items[rows[l][k + 1]]["w"] / 2 - NODE_GAP if k + 1 < len(rows[l]) else 1e9
        left = max(min(left, min(lines) - 16), room_l)
        right = min(max(right, max(lines) + 16), room_r)
        x[n], items[n]["w"] = (left + right) / 2, right - left
    left = min(x[i] - items[i]["w"] / 2 for i in items)
    for i in items:
        x[i] += PAD - left
    y = {}
    for i, it in items.items():
        l = it["layer"]
        y[i] = PAD + 56 + (l // 2) * (NODE_H + 2 * ROW_GAP) + (NODE_H / 2 if l % 2 == 0 else NODE_H + ROW_GAP)
    width = max(x[i] + items[i]["w"] / 2 for i in items) + PAD
    height = max(y.values()) + NODE_H / 2 + PAD
    return items, edges, x, y, width, height


def line_x(items, x, i):
    """Where a line runs through item i: a box's centre, or a waypoint's line position."""
    return x[i] + items[i].get("off", 0)


def ports(items, edges, x, y):
    """Attach each edge end to its box straight above or below the edge's next waypoint, so the
    line runs vertically. Clamped to the box, in which case the line jogs sideways once."""
    at = {}
    for ei, e in enumerate(edges):
        for end, nxt in ((0, 1), (-1, -2)):
            node, other = e["chain"][end], e["chain"][nxt]
            half = items[node]["w"] / 2 - 10
            px = min(max(line_x(items, x, other), x[node] - half), x[node] + half)
            py = y[node] + (NODE_H / 2 if y[other] > y[node] else -NODE_H / 2)
            at[(ei, end)] = (px, py)
    return at


# ---- SVG -----------------------------------------------------------------------------------

STYLE = """
  .surface { fill: #fcfcfb; } .ink { fill: #0b0b0b; } .ink2 { fill: #52514e; }
  .edge { fill: none; stroke: #52514e; stroke-width: 2; }
  .fb { stroke-dasharray: 6 4; }
  .arrow { fill: #52514e; }
  .box { fill: #fcfcfb; stroke-width: 2; }
  .g0 { stroke: #8a8984; stroke-dasharray: 4 3; } .f0 { fill: #8a8984; }
  .g1 { stroke: #2a78d6; } .f1 { fill: #2a78d6; }
  .g2 { stroke: #eb6834; } .f2 { fill: #eb6834; }
  .g3 { stroke: #1baf7a; } .f3 { fill: #1baf7a; }
  text { font-family: system-ui, -apple-system, "Segoe UI", sans-serif; }
  @media (prefers-color-scheme: dark) {
    .surface, .box { fill: #1a1a19; } .ink { fill: #ffffff; } .ink2 { fill: #c3c2b7; }
    .edge { stroke: #c3c2b7; } .arrow { fill: #c3c2b7; }
    .g1 { stroke: #3987e5; } .f1 { fill: #3987e5; }
    .g2 { stroke: #d95926; } .f2 { fill: #d95926; }
    .g3 { stroke: #199e70; } .f3 { fill: #199e70; }
  }
"""


def orthogonal(points, r=6):
    """Path through the points with vertical runs and, where x changes, one horizontal jog
    halfway, with rounded corners."""
    pts = [points[0]]
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if abs(x1 - x0) > 0.5:
            my = (y0 + y1) / 2
            pts += [(x0, my), (x1, my)]
        pts.append((x1, y1))
    pts = [p for k, p in enumerate(pts) if k == 0 or abs(p[0] - pts[k - 1][0]) + abs(p[1] - pts[k - 1][1]) > 0.5]
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}"
    for k in range(1, len(pts) - 1):
        (xa, ya), (xb, yb), (xc, yc) = pts[k - 1], pts[k], pts[k + 1]
        if (xa == xb and xb == xc) or (ya == yb and yb == yc):
            d += f" L{xb:.1f},{yb:.1f}"
            continue
        ra = min(r, abs(xb - xa) / 2 + abs(yb - ya) / 2)
        rc = min(r, abs(xc - xb) / 2 + abs(yc - yb) / 2)
        sx, sy = (xb - xa) and (1 if xb > xa else -1), (yb - ya) and (1 if yb > ya else -1)
        tx, ty = (xc - xb) and (1 if xc > xb else -1), (yc - yb) and (1 if yc > yb else -1)
        d += f" L{xb - sx * ra:.1f},{yb - sy * ra:.1f} Q{xb:.1f},{yb:.1f} {xb + tx * rc:.1f},{yb + ty * rc:.1f}"
    d += f" L{pts[-1][0]:.1f},{pts[-1][1]:.1f}"
    return d


def render(title, parts, flows):
    flows = merge_parallel(flows)
    items, edges, x, y, width, height = layout(parts, flows)
    at = ports(items, edges, x, y)
    # Legend, one row under the title.
    legend, lx, ly = [], PAD, PAD + 36
    groups = {GROUP[p["kind"]] for p in parts.values()}
    kinds = {f["kind"] for f in flows}
    for label, g in (("controller", 1), ("actuator / sensor", 2), ("process", 3)):
        if g not in groups:
            continue
        legend.append(f'<rect class="f{g}" x="{lx}" y="{ly - 9}" width="12" height="12" rx="2"/>'
                      f'<text class="ink2" x="{lx + 18}" y="{ly + 1}" font-size="12">{label}</text>')
        lx += 18 + text_w(label, 12) + 20
    for label, cls in (("control action", ""), ("feedback", " fb")):
        if label not in kinds:
            continue
        legend.append(f'<path class="edge{cls}" d="M{lx},{ly - 3} h28" marker-end="url(#arrow)"/>'
                      f'<text class="ink2" x="{lx + 36}" y="{ly + 1}" font-size="12">{label}</text>')
        lx += 36 + text_w(label, 12) + 20

    width = max(width, lx - 20 + PAD)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" '
           f'viewBox="0 0 {width:.0f} {height:.0f}" role="img">',
           f"<title>Control structure{': ' + escape(title) if title else ''}</title>",
           f"<style>{STYLE}</style>",
           '<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
           'markerHeight="7" orient="auto-start-reverse"><path class="arrow" d="M0,0 L10,5 L0,10 z"/></marker></defs>',
           f'<rect class="surface" width="100%" height="100%"/>',
           f'<text class="ink" x="{PAD}" y="{PAD + 14}" font-size="15" font-weight="600">'
           f'Control structure{": " + escape(title) if title else ""}</text>']
    out += legend

    labels = []
    for ei, e in enumerate(edges):
        pts = [at[(ei, 0)], *[(line_x(items, x, w), y[w]) for w in e["chain"][1:-1]], at[(ei, -1)]]
        # Snap jogs too short to read as a deliberate step (the last point stays on its box).
        tgt = e["chain"][-1]
        for k in range(1, len(pts)):
            if 0 < abs(pts[k][0] - pts[k - 1][0]) < 12:
                nx = pts[k - 1][0]
                if k == len(pts) - 1:
                    half = items[tgt]["w"] / 2 - 10
                    nx = min(max(nx, x[tgt] - half), x[tgt] + half)
                pts[k] = (nx, pts[k][1])
        cls = "edge fb" if e["kind"] == "feedback" else "edge"
        tip = f"{e['kind']} {e['name'].replace(chr(10), ', ')}: {e['src']} → {e['dst']}"
        out.append(f'<path class="{cls}" d="{orthogonal(pts)}" marker-end="url(#arrow)"><title>{escape(tip)}</title></path>')
        lw = next(w for w in e["chain"][1:-1] if items[w]["label"])
        labels.append((line_x(items, x, lw), y[lw], items[lw]["side"], e["name"], tip))
    for lx, ly, side, name, tip in labels:
        rows = name.split("\n")
        h = 14 * len(rows)
        tx, anchor = (lx - LABEL_PAD, "end") if side == "left" else (lx + LABEL_PAD, "start")
        spans = "".join(f'<tspan x="{tx:.1f}" y="{ly - h / 2 + 11 + 14 * i:.1f}">{escape(r)}</tspan>'
                        for i, r in enumerate(rows))
        out.append(f'<g><title>{escape(tip)}</title><text class="ink" font-size="11" '
                   f'text-anchor="{anchor}">{spans}</text></g>')

    for n, p in parts.items():
        it, g = items[n], GROUP[p["kind"]]
        bx, by = x[n] - it["w"] / 2, y[n] - NODE_H / 2
        out.append(f'<g><title>{escape(n)} ({escape(it["sub"])})</title>'
                   f'<rect class="box g{g}" x="{bx:.1f}" y="{by:.1f}" width="{it["w"]:.1f}" height="{NODE_H}" rx="4"/>'
                   f'<rect class="f{g}" x="{bx + 1:.1f}" y="{by + 1:.1f}" width="6" height="{NODE_H - 2}" rx="2"/>'
                   f'<text class="ink" x="{x[n] + 3:.1f}" y="{y[n] - 3:.1f}" font-size="13" font-weight="600" '
                   f'text-anchor="middle">{escape(n)}</text>'
                   f'<text class="ink2" x="{x[n] + 3:.1f}" y="{y[n] + 13:.1f}" font-size="11" '
                   f'text-anchor="middle">{escape(it["sub"])}</text></g>')
    out.append("</svg>")
    return "\n".join(out)

# ---- Text formats (D2, Mermaid) ----------------------------------------------------------

def row_pins(flows, level, order):
    """Pairs (upper, lower) for invisible links that hold each box in its STPA row. Layout
    engines pull boxes toward their neighbours, so a box with no link to the row directly above
    or below drifts out of its row; pin it to the first box of that row."""
    above, below = {n: set() for n in order}, {n: set() for n in order}
    for f in flows:
        upper, lower = sorted((f["src"], f["dst"]), key=lambda n: level[n])
        above[lower].add(upper)
        below[upper].add(lower)
    first_in = {}
    for n in order:
        first_in.setdefault(level[n], n)
    pins = []
    for n in order:
        if level[n] - 1 in first_in and not any(level[a] == level[n] - 1 for a in above[n]):
            pins.append((first_in[level[n] - 1], n))
        if level[n] + 1 in first_in and not any(level[b] == level[n] + 1 for b in below[n]):
            pins.append((n, first_in[level[n] + 1]))
    return list(dict.fromkeys(pins))


# ---- D2 ------------------------------------------------------------------------------------

D2_CLASS = {1: "controller", 2: "interface", 3: "process", 0: "undeclared"}
D2_STROKE = {1: "#2a78d6", 2: "#eb6834", 3: "#1baf7a", 0: "#8a8984"}


def d2_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def d2(title, parts, flows):
    """D2 source in STPA rows, laid out with ELK. Both of D2's built-in layout engines rank
    boxes along links, but only ELK follows the direction a link is written in (dagre follows
    the arrowhead). So upward feedback is written from the upper box, `controller <- sensor`,
    which keeps its arrowhead at the controller. Invisible links pin each box to its STPA row."""
    flows = merge_parallel(flows)
    level = levels(parts, flows)
    nid = {n: "n_" + re.sub(r"\W", "_", n) for n in parts}
    order = sorted(parts, key=lambda n: level[n])  # stable: declaration order within a row
    head = f"Control structure{': ' + title if title else ''}"
    lines = [f"# {head}. Generated by tools/control_structure.py from the SysML v2 model; do not edit.",
             "# Render with the d2 tool (https://d2lang.com):  d2 THIS_FILE.d2 OUTPUT.svg", "",
             "vars: {",
             "  d2-config: {layout-engine: elk}",
             "  d2-legend: {",
             '    l1: "controller" {class: controller}',
             '    l2: "actuator / sensor" {class: interface}',
             '    l3: "process" {class: process}',
             *[f'    l{i}: "" {{style.opacity: 0}}' for i in range(4, 8)],  # line samples' ends
             "    l4 -> l5: control action {class: control-action}",
             "    l6 -> l7: feedback {class: feedback}",
             "  }",
             "}",
             "classes: {"]
    for g, cls in D2_CLASS.items():
        dash = "; stroke-dash: 3" if g == 0 else ""
        lines.append(f'  {cls}: {{style: {{stroke: "{D2_STROKE[g]}"; stroke-width: 2; fill: "#fcfcfb"; '
                     f'font-color: "#0b0b0b"; border-radius: 4{dash}}}}}')
    # Link labels at 12px (D2 default 16): ELK places parallel links closer together than
    # 16px labels need, and smaller labels read as secondary to the box names.
    lines += ['  control-action: {style: {stroke: "#52514e"; font-color: "#0b0b0b"; font-size: 12}}',
              '  feedback: {style: {stroke: "#52514e"; font-color: "#0b0b0b"; font-size: 12; stroke-dash: 4}}',
              "  pin: {style: {opacity: 0}}",
              "}",
              f"title: {d2_str(head)} {{shape: text; near: top-center; style: {{font-size: 20; bold: true}}}}",
              "direction: down", ""]
    for n in order:
        p = parts[n]
        sub = p["kind"] + (f" · in {p['within']}" if p["within"] else "")
        lines.append(f'{nid[n]}: {d2_str(n + chr(10) + sub).replace(chr(10), "\\n")} '
                     f'{{class: {D2_CLASS[GROUP[p["kind"]]]}}}')
    lines.append("")
    for f in flows:
        s, d, name = f["src"], f["dst"], d2_str(f["name"]).replace("\n", "\\n")
        if f["kind"] == "control action":
            lines.append(f"{nid[s]} -> {nid[d]}: {name} {{class: control-action}}")
        elif level[d] < level[s]:
            lines.append(f"{nid[d]} <- {nid[s]}: {name} {{class: feedback}}")
        else:
            lines.append(f"{nid[s]} -> {nid[d]}: {name} {{class: feedback}}")
    # Pins carry a (hidden) label because ELK gives every edge label a row of its own: an
    # unlabelled pin spans fewer rows than a labelled link and lets boxes settle between rows.
    lines += [f"{nid[a]} -> {nid[b]}: pin {{class: pin}}" for a, b in row_pins(flows, level, order)]
    return "\n".join(lines) + "\n"


# ---- Mermaid -------------------------------------------------------------------------------

MERMAID_CLASS = {1: "controller", 2: "interface", 3: "process", 0: "undeclared"}
MERMAID_STYLE = {1: "stroke:#2a78d6", 2: "stroke:#eb6834", 3: "stroke:#1baf7a",
                 0: "stroke:#8a8984,stroke-dasharray:4 3"}


def mermaid(title, parts, flows):
    """Mermaid flowchart in STPA rows, laid out with ELK. Mermaid has no link with an arrowhead
    only at its start, so feedback is written in its real direction (sensor -> controller).
    In Mermaid 12, ELK's MODEL_ORDER cycle breaking treats every link that points from a
    later-declared box to an earlier one as reversed when it assigns rows, so declaring boxes
    top-down keeps controllers above the sensors that feed them. Mermaid 11 needs the invisible
    counter-links added below. Invisible links also pin each box to its row."""
    flows = merge_parallel(flows)
    level = levels(parts, flows)
    nid = {n: "n_" + re.sub(r"\W", "_", n) for n in parts}
    order = sorted(parts, key=lambda n: level[n])  # stable: declaration order within a row
    head = f"Control structure{': ' + title if title else ''}"
    # The base theme's variables match the SVG: light boxes, grey lines, the same font.
    # NETWORK_SIMPLEX node placement centres boxes over each other. Mermaid's ELK puts every
    # label in the middle of its link, so parallel links still bend slightly around their labels.
    # No Mermaid `title:`: it renders dark-on-dark in dark previews. The name goes in the
    # comment below, and the Markdown output has it as a heading.
    lines = ["---", "config:", "  theme: base", "  themeVariables:",
             '    primaryColor: "#fcfcfb"', '    primaryTextColor: "#0b0b0b"', '    lineColor: "#52514e"',
             '    edgeLabelBackground: "#fcfcfb"',
             '    fontFamily: "system-ui, -apple-system, Segoe UI, sans-serif"',
             "  layout: elk", "  elk:", "    cycleBreakingStrategy: MODEL_ORDER",
             "    nodePlacementStrategy: NETWORK_SIMPLEX", "    considerModelOrder: NODES_AND_EDGES",
             "---", "flowchart TB",
             f"  %% {head}. Generated by tools/control_structure.py from the SysML v2 model; do not edit."]
    for g, style in MERMAID_STYLE.items():
        lines.append(f"  classDef {MERMAID_CLASS[g]} {style},stroke-width:2px")
    for n in order:
        p = parts[n]
        sub = p["kind"] + (f" · in {p['within']}" if p["within"] else "")
        lines.append(f'  {nid[n]}["<b>{n}</b><br/>{sub}"]:::{MERMAID_CLASS[GROUP[p["kind"]]]}')
    # Which side a link lands on follows the declaration order (considerModelOrder above).
    # Feedback-first is the order verified to put control actions left and feedback right in
    # Markdown Preview Mermaid Support (Mermaid 11.12.2) and in Mermaid 11.17 and 12, with
    # several fonts. The Mermaid Chart VS Code extension doesn't pass ELK's ordering options at
    # all, so its sides depend on the viewer's fonts and no order is reliable there.
    for f in sorted(flows, key=lambda f: f["kind"] != "feedback"):
        arrow = "-->" if f["kind"] == "control action" else "-.->"
        label = f["name"].replace("\n", "<br/>")
        lines.append(f'  {nid[f["src"]]} {arrow}|"{label}"| {nid[f["dst"]]}')
    # Mermaid 11's ELK ignores MODEL_ORDER in practice (tested with 11.17.2 and layout-elk
    # 0.2.3, and seen in the Mermaid Chart VS Code extension), and its default cycle breaking
    # then ranks by link counts. An invisible upper ~~~ lower link beside every upward feedback
    # link tips that count toward the controller, so both versions keep controllers on top.
    counter = [(f["dst"], f["src"]) for f in flows
               if f["kind"] == "feedback" and level[f["dst"]] < level[f["src"]]]
    lines += [f"  {nid[a]} ~~~ {nid[b]}" for a, b in dict.fromkeys(counter + row_pins(flows, level, order))]
    return "\n".join(lines) + "\n"


def mermaid_markdown(title, parts, flows):
    return (f"# Control structure{': ' + title if title else ''}\n\n"
            "Generated by `tools/control_structure.py` from the SysML v2 model. Do not edit by hand.\n\n"
            f"```mermaid\n{mermaid(title, parts, flows)}```\n\n"
            "Solid arrows are control actions, dotted arrows are feedback. Box outlines: blue for "
            "controllers, orange for actuators and sensors, green for controlled processes.\n\n"
            "The diagram needs Mermaid's ELK layout. In VS Code, view it with the Markdown Preview "
            "Mermaid Support extension (bierner.markdown-mermaid). The Mermaid Chart extension may put "
            "feedback on the wrong side, and renderers without ELK draw sensors above the controllers "
            "they feed.\n")


WRITERS = {".svg": render, ".d2": d2, ".mmd": mermaid, ".md": mermaid_markdown}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="*", type=Path, help="model files (default: model/*.sysml)")
    ap.add_argument("-o", "--out", type=Path, action="append",
                    help="output file, repeatable; .svg (image), .d2 (D2 source), .mmd (Mermaid) "
                         "or .md (Markdown with a Mermaid block). "
                         "Default: control_structure.svg, .d2 and .md")
    args = ap.parse_args(argv)
    outs = args.out or [Path(f"control_structure{x}") for x in (".svg", ".d2", ".md")]
    for out in outs:
        if out.suffix not in WRITERS:
            ap.error(f"{out}: unknown output type; use one of {', '.join(WRITERS)}")
    files = args.files or sorted((ROOT / "model").rglob("*.sysml"))
    try:
        trees = [parse(f) for f in files]
    except ModelSyntaxError as e:
        sys.exit(f"{e}: not valid SysML v2")
    title, parts, flows, warnings = read_structure(trees)
    for w in warnings:
        print("warning:", w, file=sys.stderr)
    if not flows:
        sys.exit("no #controlAction or #feedback flows found; nothing to draw")
    w = max(len(f["kind"]) for f in flows)
    for f in flows:
        print(f"{f['kind']:<{w}}  {f['name']:<24} {f['src']} -> {f['dst']}")
    for out in outs:
        out.write_text(WRITERS[out.suffix](title, parts, flows))
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
