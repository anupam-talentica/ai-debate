#!/usr/bin/env python3
"""Build the 'Testing & Deploying an Agentic System' deck as a native .pptx.

Regenerate with:  python3 docs/build_pptx.py   (run from debate_bot/)
Assets:  docs/assets/logo-color.png (white slides), docs/assets/logo-white.png (teal slides)
"""
import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_AUTO_SIZE
from pptx.oxml.ns import qn

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, "assets")
LOGO_COLOR = os.path.join(ASSETS, "logo-color.png")
LOGO_WHITE = os.path.join(ASSETS, "logo-white.png")
LOGO_AR = 3.256  # width/height

# ---- palette -------------------------------------------------------------
TEAL      = "3FA9B4"; TEAL_DEEP = "2E9FA6"; GREEN = "6FBE55"; GREEN_DEEP = "5AAE45"
YELLOW    = "F3E43A"; INK = "38434C"; INK_SOFT = "68757E"; INK_FAINT = "9AA6AD"
WASH      = "F1F7F5"; WASH2 = "E9F3EF"; LINE = "E0E9E7"; WHITE = "FFFFFF"
CARD_ACC  = "E8F6EF"; CARD_ACC_LN = "CFEADF"
PILL_DET  = "EEF9EA"; PILL_DET_TX = "5AAE45"; PILL_JUD = "EAFAFB"; PILL_JUD_TX = "2E9FA6"
WARN_BG   = "FFF6E0"; WARN_LN = "F0DD7A"; WARN_TX = "B8891C"
FONT = "Segoe UI"; FONT_H = "Segoe UI"
TOTAL = 17  # total slides (drives footer page count)

def C(h): return RGBColor.from_string(h)

prs = Presentation()
prs.slide_width  = Inches(13.333)
prs.slide_height = Inches(7.5)
BLANK = prs.slide_layouts[6]
SW, SH = prs.slide_width, prs.slide_height

# ---- primitives ----------------------------------------------------------
def _no_shadow(shape):
    el = shape._element.spPr
    a = el.makeelement(qn('a:effectLst'), {})
    el.append(a)

def rect(slide, x, y, w, h, fill=None, line=None, line_w=1.0, round_=False, shadow=False):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if round_ else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h))
    if round_:
        try: shp.adjustments[0] = 0.08
        except Exception: pass
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid(); shp.fill.fore_color.rgb = C(fill)
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = C(line); shp.line.width = Pt(line_w)
    if not shadow:
        _no_shadow(shp)
    return shp

def grad_bg(slide, c1="43ABB5", c2="74C07E", angle=135):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, SW, SH)
    shp.line.fill.background()
    shp.fill.gradient()
    try: shp.fill.gradient_angle = angle
    except Exception: pass
    stops = shp.fill.gradient_stops
    stops[0].color.rgb = C(c1); stops[0].position = 0.0
    stops[1].color.rgb = C(c2); stops[1].position = 1.0
    _no_shadow(shp)
    return shp

def text(slide, x, y, w, h, runs, size=18, color=INK, bold=False, italic=False,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, font=FONT, spacing=1.0,
         wrap=True, space_after=0):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = wrap
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    # runs: string OR list of (text,color,bold) tuples OR list of paragraphs(list of tuples)
    if isinstance(runs, str):
        paras = [[(runs, color, bold, italic)]]
    elif runs and isinstance(runs[0], tuple):
        paras = [runs]
    else:
        paras = runs
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing: p.line_spacing = spacing
        if space_after: p.space_after = Pt(space_after)
        p.space_before = Pt(0)
        for seg in para:
            t = seg[0]; col = seg[1] if len(seg) > 1 and seg[1] else color
            bd = seg[2] if len(seg) > 2 else bold
            it = seg[3] if len(seg) > 3 else italic
            r = p.add_run(); r.text = t
            r.font.size = Pt(size); r.font.name = font
            r.font.bold = bd; r.font.italic = it
            r.font.color.rgb = C(col)
    return tb

def logo(slide, white=False, w=1.9, x=None, y=0.42):
    path = LOGO_WHITE if white else LOGO_COLOR
    h = w / LOGO_AR
    if x is None: x = 13.333 - 0.75 - w
    slide.shapes.add_picture(path, Inches(x), Inches(y), Inches(w), Inches(h))

def bar(slide, x, y, h=0.75):
    r = rect(slide, x, y, 0.11, h, fill=GREEN)  # accent bar (solid green, brand)
    return r

def footer(slide, page):
    text(slide, 0.75, 7.02, 8, 0.3, "Testing & Deploying an Agentic System",
         size=9, color=INK_FAINT)
    text(slide, 9.5, 7.02, 3.08, 0.3, f"{page:02d} / {TOTAL}", size=9, color=INK_SOFT,
         bold=True, align=PP_ALIGN.RIGHT)

def eyebrow(slide, s, x=0.75, y=0.62, color=GREEN_DEEP):
    text(slide, x, y, 11, 0.35, s.upper(), size=11.5, color=color, bold=True)

def title(slide, s, x=0.75, y=1.02, w=11.4, color=TEAL_DEEP, size=33):
    text(slide, x, y, w, 1.1, s, size=size, color=color, bold=True, spacing=1.0)

def content_head(slide, eb, ttl, page, sub=None):
    bar(slide, 0.75, 1.06, 0.86 if not sub else 1.05)
    eyebrow(slide, eb)
    title(slide, ttl, x=1.02)
    if sub:
        text(slide, 1.02, 1.86, 11.2, 0.7, sub, size=15, color=INK_SOFT, spacing=1.1)
    logo(slide, white=False)
    footer(slide, page)

def card(slide, x, y, w, h, tag=None, head=None, body=None, accent=False,
         head_color=INK, tag_color=TEAL_DEEP):
    fill = CARD_ACC if accent else WASH
    ln   = CARD_ACC_LN if accent else LINE
    rect(slide, x, y, w, h, fill=fill, line=ln, line_w=1.0, round_=True)
    pad = 0.32; cy = y + 0.34
    if tag:
        text(slide, x+pad, cy, w-2*pad, 0.3, tag.upper(), size=11, color=tag_color, bold=True)
        cy += 0.42
    if head:
        text(slide, x+pad, cy, w-2*pad, 0.7, head, size=18, color=head_color, bold=True, spacing=1.0)
        cy += 0.68 if len(head) < 22 else 1.05
    if body:
        text(slide, x+pad, cy, w-2*pad, y+h-cy-0.2, body, size=13, color=INK_SOFT, spacing=1.12)

def arrow_r(slide, x, y, size=0.24, color=TEAL):
    shp = slide.shapes.add_shape(MSO_SHAPE.ISOSCELES_TRIANGLE, Inches(x), Inches(y),
                                 Inches(size), Inches(size*1.4))
    shp.rotation = 90
    shp.fill.solid(); shp.fill.fore_color.rgb = C(color); shp.line.fill.background()
    _no_shadow(shp)

def arrow_d(slide, x, y, size=0.26, color=TEAL):
    shp = slide.shapes.add_shape(MSO_SHAPE.ISOSCELES_TRIANGLE, Inches(x), Inches(y),
                                 Inches(size*1.3), Inches(size))
    shp.rotation = 180
    shp.fill.solid(); shp.fill.fore_color.rgb = C(color); shp.line.fill.background()
    _no_shadow(shp)

def pill(slide, x, y, w, s, bg, tx):
    rect(slide, x, y, w, 0.34, fill=bg, round_=True)
    text(slide, x, y+0.03, w, 0.28, s, size=10.5, color=tx, bold=True,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

# =========================================================================
# SLIDE 1 — TITLE
# =========================================================================
s = prs.slides.add_slide(BLANK)
grad_bg(s)
logo(s, white=True, w=2.0)
text(s, 0.95, 1.35, 10, 0.4, "AN ENGINEERING DEEP-DIVE", size=13, color="EAF7F4", bold=True)
text(s, 0.9, 1.85, 11, 1.6, "Beyond the Demo", size=68, color=YELLOW, bold=True)
text(s, 0.95, 3.35, 11, 0.7, "Testing & Deploying an Agentic System", size=27, color=WHITE, bold=True)
text(s, 0.95, 4.15, 7.6, 1.0,
     [[("What it takes to make a multi-agent system ", "EAF7F4"),
       ("trustworthy", WHITE, True), (" and ", "EAF7F4"), ("resilient", WHITE, True),
       (" — using a LangGraph debate bot as the running example.", "EAF7F4")]],
     size=15, spacing=1.2)
# pillars
py = 5.35
for i,(pn,ph,pp) in enumerate([
    ("PART 1","Testing","Earning trust in a non-deterministic system"),
    ("PART 2","Deployment","Surviving failure in a long-running one")]):
    px = 0.95 + i*4.35
    rect(s, px, py, 4.05, 1.35, fill=None, line="BFE6DE", line_w=1.25, round_=True)
    # translucent-ish panel: overlay light fill
    text(s, px+0.3, py+0.2, 3.5, 0.3, pn, size=12, color=YELLOW, bold=True)
    text(s, px+0.3, py+0.55, 3.5, 0.4, ph, size=20, color=WHITE, bold=True)
    text(s, px+0.3, py+0.98, 3.5, 0.5, pp, size=11.5, color="EAF7F4", spacing=1.05)
text(s, 0.95, 6.95, 6, 0.3, "23 Jul 2026  ·  Talentica", size=12, color="EAF7F4", bold=True)

# =========================================================================
# SLIDE 2 — SYSTEM UNDER TEST
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "The running example", "The System Under Test", 2,
             sub="A LangGraph multi-agent debate — Pro & Con argue, a Moderator decides.")
# flow row
nodes = [("Topic","user input",WASH,LINE),
         ("Round 1","Opening · Pro + Con","F0FAEC","BFE4B3"),
         ("Round 2","Rebuttal · Pro + Con","EFFAFB","B8E2E6"),
         ("Round 3","Closing · Pro + Con","F0FAEC","BFE4B3"),
         ("Moderator","verdict → Winner","FFFDF0","F0DD7A")]
nx = 0.85; ny = 2.75; nw = 2.15; nh = 1.35; gap = 0.28
for i,(nt,ns,fl,ln) in enumerate(nodes):
    x = nx + i*(nw+gap)
    rect(s, x, ny, nw, nh, fill=fl, line=ln, line_w=1.25, round_=True)
    text(s, x, ny+0.34, nw, 0.4, nt, size=15, color=INK, bold=True, align=PP_ALIGN.CENTER)
    text(s, x, ny+0.78, nw, 0.5, ns, size=10.5, color=INK_SOFT, align=PP_ALIGN.CENTER, spacing=1.0)
    if i < len(nodes)-1:
        arrow_r(s, x+nw+0.02, ny+nh/2-0.16, size=0.22)
# state bar
rect(s, 0.85, 4.4, 11.6, 0.6, fill=WASH2, line=CARD_ACC_LN, round_=True)
text(s, 0.85, 4.52, 11.6, 0.4,
     [[("Shared state (DebateState) flows through every node", TEAL_DEEP, True),
       ("   — topic, all arguments, memory context, winner", INK_SOFT)]],
     size=13.5, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
# bullets
text(s, 0.95, 5.3, 11.4, 1.4, [
    [("● ", GREEN),("What makes it agentic: multiple cooperating agents, a shared evolving state, streamed output, and a decision at the end.", INK)],
    [("● ", GREEN),("Two hard questions follow: ", INK),("can we trust its output?", TEAL_DEEP, True),("  and  ", INK),("will it stay up when something breaks?", GREEN_DEEP, True)],
], size=14, spacing=1.2, space_after=8)

# =========================================================================
# SLIDE 3 — WHY DIFFERENT
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "The problem", "Why Agentic Systems Break the Playbook", 3)
cw = 5.65; cx1 = 0.75; cx2 = 0.75+cw+0.35; cy = 2.35; ch = 3.0
card(s, cx1, cy, cw, ch, tag="Property 1", head="Non-deterministic",
     body="Same input, a different answer every time. You cannot assert equality — traditional pass/fail tests don't apply to the interesting behavior.")
text(s, cx1+0.32, cy+ch-0.55, cw-0.6, 0.4, "→ Part 1 · Testing solves this.", size=13, color=GREEN_DEEP, bold=True)
card(s, cx2, cy, cw, ch, tag="Property 2", head="Long-running & stateful",
     body="A task is a sequence of steps, not one request. A crash mid-run loses real work — not just a connection.")
text(s, cx2+0.32, cy+ch-0.55, cw-0.6, 0.4, "→ Part 2 · Deployment solves this.", size=13, color=GREEN_DEEP, bold=True)
rect(s, 0.75, 5.75, 11.83, 0.6, fill=WASH2, line=CARD_ACC_LN, round_=True)
text(s, 0.75, 5.87, 11.83, 0.4,
     [[("Agenda   ", INK_SOFT),("Part 1 · Testing (trust)   →   Part 2 · Deployment (resilience)", TEAL_DEEP, True)]],
     size=14, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

# =========================================================================
# SLIDE 4 — 3-STEP FRAMEWORK
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "Part 1 · Testing", "A Shift in Thinking: 3 Steps", 4)
steps = [
    ("1","Define the dimensions that matter for this system",
     "Dimensions come from what the agent is for:",
     ["Argument quality","Correctness & robustness","Coherence / integrity","Performance & streaming"]),
    ("2","Split each into deterministic vs. non-deterministic",
     "Some things have a right answer (is the winner \"Pro\" or \"Con\"?). Some are judgments (is the argument persuasive?).", None),
    ("3","Route each to the right tool",
     "Rubric metric = a named criterion + a 1–5 scale, graded by a stronger model.", None),
]
stx = 0.75; sty = 2.15; stw = 3.85; sth = 3.35; sgap = 0.14
for i,(num,h,p,chips) in enumerate(steps):
    x = stx + i*(stw+sgap)
    rect(s, x, sty, stw, sth, fill=WASH, line=LINE, round_=True)
    cc = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x+0.32), Inches(sty+0.3), Inches(0.58), Inches(0.58))
    cc.fill.solid(); cc.fill.fore_color.rgb = C(GREEN); cc.line.fill.background(); _no_shadow(cc)
    text(s, x+0.32, sty+0.33, 0.58, 0.5, num, size=21, color=WHITE, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    text(s, x+0.3, sty+1.02, stw-0.55, 0.95, h, size=15, color=INK, bold=True, spacing=1.0)
    text(s, x+0.3, sty+1.98, stw-0.55, 0.9, p, size=12, color=INK_SOFT, spacing=1.08)
# step 1 chips — 2x2 grid (color = deterministic vs judge)
cbw=1.58; cbh=0.34
for j,c_ in enumerate(steps[0][3]):
    col = TEAL_DEEP if j in (0,2) else GREEN_DEEP
    bg  = PILL_JUD if j in (0,2) else PILL_DET
    cx_ = stx+0.3 + (j%2)*(cbw+0.12); cy_ = sty+2.48 + (j//2)*0.42
    rect(s, cx_, cy_, cbw, cbh, fill=bg, round_=True)
    text(s, cx_, cy_+0.03, cbw, 0.28, c_, size=9.5, color=col, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
# step 3 routing
x3 = stx + 2*(stw+sgap)
ry = sty+2.55
text(s, x3+0.3, ry, stw-0.55, 0.35, [[("Deterministic  →  ", INK, True),("script / regex", GREEN_DEEP, True)]], size=12.5)
text(s, x3+0.3, ry+0.4, stw-0.55, 0.35, [[("Non-deterministic  →  ", INK, True),("LLM-as-a-judge", TEAL_DEEP, True)]], size=12.5)
# --- rubric-metrics band: what each dimension is actually scored on ---------
my=5.62
rect(s, 0.75, my, 11.83, 1.26, fill=CARD_ACC, line=CARD_ACC_LN, round_=True)
text(s, 1.05, my+0.15, 11.2, 0.3, "The metrics each dimension is actually scored on", size=13.5, color=INK, bold=True)
pill(s, 1.05, my+0.56, 1.78, "LLM-judge", PILL_JUD, PILL_JUD_TX)
text(s, 3.0, my+0.55, 9.5, 0.3,
     [("Relevance · Persuasiveness · Rebuttal engagement · Moderator soundness", TEAL_DEEP, True),
      ("   — scored 1–5", INK_SOFT)], size=12.5, anchor=MSO_ANCHOR.MIDDLE)
pill(s, 1.05, my+0.9, 1.78, "Deterministic", PILL_DET, PILL_DET_TX)
text(s, 3.0, my+0.89, 9.5, 0.3,
     [("winner-valid · all fields present · word-count caps · moderator 3-part structure", GREEN_DEEP, True)],
     size=12.5, anchor=MSO_ANCHOR.MIDDLE)

# =========================================================================
# SLIDE 5 — NEXUS GUARD
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "Part 1 · Testing", "The Method Generalizes — \"Nexus Guard\"", 5,
             sub="A different agentic system (a guarded customer-ops agent network). Same 3 steps — dimensions fall out of its purpose.")
rows = [
    ("Routing & loop integrity","Passes a query across ≥3 agents; breaks routing loops",
        [("hops ≤ 3 · no A→B→A cycle", GREEN_DEEP)]),
    ("PII masking / safety","Aadhaar, cards, API keys masked in every stream",
        [("mask recall = 100%", GREEN_DEEP),("   ·   ", INK_FAINT),("Safety", TEAL_DEEP)]),
    ("Self-correction quality","A judge gates the reply before it reaches the user",
        [("Relevance · Factuality · Safety", TEAL_DEEP)]),
    ("Streaming performance","Eval + masking keep up with the token stream",
        [("P95 latency < 200 ms / chunk", GREEN_DEEP)]),
    ("Cost & budget guardrails","Runaway session degrades to human-in-the-loop",
        [("tokens ≤ budget · graceful handoff", GREEN_DEEP)]),
]
tx = 0.75; ty = 2.4; col1 = 2.9; col2 = 4.85; col3 = 4.05
# header
text(s, tx, ty, col1, 0.3, "DIMENSION", size=11, color=TEAL_DEEP, bold=True)
text(s, tx+col1, ty, col2, 0.3, "WHAT IT TESTS", size=11, color=TEAL_DEEP, bold=True)
text(s, tx+col1+col2, ty, col3, 0.3, "SCORED ON — THE METRIC", size=11, color=TEAL_DEEP, bold=True)
rect(s, tx, ty+0.34, col1+col2+col3, 0.02, fill=WASH2)
ry = ty+0.52
for (d,w,metric) in rows:
    text(s, tx, ry+0.05, col1-0.2, 0.6, d, size=12.5, color=INK, bold=True, spacing=1.0)
    text(s, tx+col1, ry+0.05, col2-0.2, 0.6, w, size=12, color=INK_SOFT, spacing=1.02)
    text(s, tx+col1+col2, ry+0.05, col3-0.15, 0.6, metric, size=12, bold=True, spacing=1.02)
    ry += 0.66
    rect(s, tx, ry-0.05, col1+col2+col3, 0.012, fill=LINE)
rect(s, 0.75, 6.4, 11.83, 0.55, fill=WASH2, line=CARD_ACC_LN, round_=True)
text(s, 0.75, 6.5, 11.83, 0.4,
     [[("green = deterministic  ·  teal = LLM-judge", INK_SOFT),("      |      Same 3 steps, new dimensions — ", INK_SOFT),("the method transfers.", TEAL_DEEP, True)]],
     size=12.5, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

# =========================================================================
# SLIDE 6 — 4-WAY TRADEOFF
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "Part 1 · Testing", "One System, Validated Four Ways", 6,
             sub="Same system, dataset, and judge — the only variable is the harness. It's a buy-vs-build decision.")
cw = 3.78; cy = 2.5; ch = 2.75; gx = 0.75
cards = [("Build our own","Custom pytest","Total control, zero cost, fully private. Every metric and judge prompt is yours — but you maintain it.",False),
         ("Hosted","LangSmith","Dashboards, history, free per-node traces. The price: data leaves the machine.",False),
         ("Off-the-shelf","deepeval / promptfoo","Fast to adopt, rich prebuilt rubrics. The abstraction can hide what's actually measured.",False)]
for i,(tag,h,b,acc) in enumerate(cards):
    card(s, gx+i*(cw+0.24), cy, cw, ch, tag=tag, head=h, body=b, accent=acc)

# =========================================================================
# Approach slides 7-8-10 (shared layout)
# =========================================================================
def approach_slide(page, num, ttl, what, how, strengths, cost, role, sub=None):
    s = prs.slides.add_slide(BLANK)
    content_head(s, f"Approach {num} of 4 · Testing", ttl, page, sub=sub)
    top = 2.35 if not sub else 2.75
    lx = 0.75; lw = 5.7; rx = 0.75+lw+0.4; rw = 5.7
    def field(x, y, w, lbl, val, lblcol=GREEN_DEEP):
        text(s, x, y, w, 0.3, lbl.upper(), size=11, color=lblcol, bold=True)
        text(s, x, y+0.34, w, 1.0, val, size=14.5, color=INK, spacing=1.14)
    field(lx, top, lw, "What it is", what)
    field(lx, top+1.55, lw, "How it works", how)
    field(rx, top, rw, "Strengths", strengths)
    field(rx, top+1.55, rw, "Cost", cost)
    ry = top+3.05
    rect(s, rx, ry, rw, 0.95, fill=CARD_ACC, line=CARD_ACC_LN, round_=True)
    text(s, rx+0.3, ry+0.16, rw-0.6, 0.3, "ROLE", size=11, color=TEAL_DEEP, bold=True)
    text(s, rx+0.3, ry+0.46, rw-0.6, 0.4, role, size=14, color=INK, spacing=1.05)
    return s

approach_slide(7, "1", "Custom pytest + LLM-as-judge",
    [[("A small ", INK),("evals/", TEAL_DEEP, True),(" harness on the existing pytest + Anthropic stack. ", INK),("No new dependencies.", INK, True)]],
    [[("run_debate(topic)", TEAL_DEEP, True),(" over a golden dataset → deterministic scorers (Python / regex) + an LLM-judge scorer (1–5 on 4 axes) → a scorecard.", INK)]],
    "Zero-dependency, fully offline, you own every metric, trivial in CI.",
    "You build & maintain the harness, dataset, and report yourself.",
    [[("The backbone", INK, True),(" — the default CI gate and single source of scoring truth.", INK)]])

approach_slide(8, "2", "LangSmith (hosted)",
    [[("Flip on a dependency that's ", INK),("already present", INK, True),(" — upload the dataset, define evaluators, turn on tracing.", INK)]],
    [[("Reuses the ", INK),("same scorers", INK, True),(" as Approach 1, run on a hosted platform. LangGraph auto-emits per-node traces.", INK)]],
    "Hosted dashboard for scores + traces, free per-node latency, versioned datasets and regression history.",
    [[("Needs an account + network — ", INK),("data leaves the machine.", INK, True),(" Don't point it at sensitive data.", INK)]],
    [[("Add when you need ", INK),("history + performance monitoring.", INK, True)]])

# =========================================================================
# SLIDE 9 — deepeval + G-EVAL
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "Approach 3 of 4 · Testing", "deepeval — G-Eval rubrics in pytest", 9,
             sub="Off-the-shelf rubric metrics, run in pytest. Here's G-Eval, adapted to a debate exchange.")
gy = 2.85
# left column boxes
lboxes = [("Task Introduction","\"You will be given one exchange from a debate. Rate it on one metric.\"","F2F7FD","A9C7E8","33557D"),
          ("Evaluation Criteria","Rebuttal Engagement (1–5) — does the Con rebuttal address ≥1 specific point from the Pro opening?","F2F7FD","A9C7E8","33557D"),
          ("Evaluation Steps","1. Read Pro opening. 2. Read Con rebuttal; check which Pro points it addresses. 3. Assign 1–5.","EFF9F1","A7D8B0","2F7D47")]
lx=0.75; lw=4.7; bh=1.15
for i,(h,b,fl,ln,tc) in enumerate(lboxes):
    y=gy+i*(bh+0.14)
    rect(s, lx, y, lw, bh, fill=fl, line=ln, round_=True)
    text(s, lx+0.28, y+0.16, lw-0.5, 0.3, h, size=13, color=tc, bold=True)
    text(s, lx+0.28, y+0.5, lw-0.5, 0.6, b, size=11, color=tc, italic=True, spacing=1.06)
text(s, lx+lw+0.05, gy+1.6, 1.0, 0.3, "Auto-CoT", size=11, color=INK_SOFT, bold=True, align=PP_ALIGN.CENTER)
arrow_r(s, lx+lw+0.35, gy+1.35, size=0.26)
# right column
rx=lx+lw+1.1; rw=4.55
rboxes=[("Input Context","Topic + Pro opening: \"Athletes are overpaid…\""),
        ("Input Target","Con rebuttal (the text being scored)")]
for i,(h,b) in enumerate(rboxes):
    y=gy+i*0.95
    rect(s, rx, y, rw, 0.82, fill="EFF9F1", line="A7D8B0", round_=True)
    text(s, rx+0.28, y+0.13, rw-0.5, 0.3, h, size=12.5, color="2F7D47", bold=True)
    text(s, rx+0.28, y+0.45, rw-0.5, 0.3, b, size=10.5, color="2F7D47", italic=True)
arrow_d(s, rx+rw/2-0.16, gy+1.92, size=0.24)
# score box with bars
sby=gy+2.3
rect(s, rx, sby, rw, 1.55, fill="ECE6F9", line="CBBDEC", round_=True)
text(s, rx+0.28, sby+0.14, rw-0.5, 0.3, "G-Eval", size=14, color="5B45A8", bold=True)
bx=rx+0.5; bb=sby+1.02; bw=0.42
heights=[0.22,0.34,0.55,0.88,0.4]
for j,hh in enumerate(heights):
    bh2=hh*0.75
    rect(s, bx+j*0.55, bb-bh2, bw, bh2, fill="A78FE0")
    text(s, bx+j*0.55, bb+0.02, bw, 0.2, str(j+1), size=9, color="6A5AA8", align=PP_ALIGN.CENTER)
text(s, rx+2.7, sby+0.55, rw-2.8, 0.6, "Rebuttal\nEngagement: 4.2", size=14, color="4A3894", bold=True, spacing=1.0)

# =========================================================================
# SLIDE 10 — promptfoo
# =========================================================================
approach_slide(10, "4", "promptfoo (declarative YAML + CLI)",
    [[("Config-driven eval — YAML test cases + a Python provider wrapping ", INK),("run_debate", TEAL_DEEP, True),(", run via a Node CLI.", INK)]],
    [[("Declare ", INK),("llm-rubric", TEAL_DEEP, True),(" asserts (Claude grader) + ", INK),("javascript", TEAL_DEEP, True),(" deterministic asserts (winner valid, word caps) → HTML report grid.", INK)]],
    "Declarative and readable, polished local HTML report, no pip dependency (uses Node).",
    "Needs a Node toolchain; another tool's conventions to learn.",
    [[("Nice when you want ", INK),("declarative config + a visual report.", INK, True)]])

# =========================================================================
# SLIDE 11 — COMPARISON OF THE THREE OPTIONS
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "Part 1 · Testing", "How the Three Options Compare", 11,
             sub="Same job, different harness — here's where each one wins.")
tx=0.75; ty=2.62
dimw=2.7; colw=(11.83-dimw)/3.0
opts_hdr=[("Custom pytest","EEF9EA","5AAE45"),("LangSmith","EAFAFB","2E9FA6"),("deepeval / promptfoo","F1EEFA","6A5AA8")]
hh=0.58
for j,(nm,bg,tc) in enumerate(opts_hdr):
    x=tx+dimw+j*colw
    rect(s, x+0.06, ty, colw-0.12, hh, fill=bg, round_=True)
    text(s, x+0.06, ty, colw-0.12, hh, nm, size=13, color=tc, bold=True,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
cmp_rows=[
 ("New dependency", [("None",True),("Already present",False),("Adds a library",False)]),
 ("Offline / privacy", [("Fully local",True),("Data leaves machine",False),("Mostly local",False)]),
 ("Scoring control", [("Own every metric",True),("Custom evaluators",False),("Prebuilt rubrics",False)]),
 ("Dashboards & traces", [("Build your own",False),("Hosted + free traces",True),("Local HTML report",False)]),
 ("Regression history", [("Manual JSON diff",False),("Versioned & hosted",True),("Stored runs",False)]),
 ("CI fit", [("Excellent — is pytest",True),("Needs key + network",False),("Needs Node / lib",False)]),
 ("Best at", [("Zero-dep CI gate",True),("Tracing & history",True),("Declarative rubrics",True)]),
]
ry=ty+hh+0.14; rh=0.5
for i,(dim,vals) in enumerate(cmp_rows):
    if i%2==1:
        rect(s, tx, ry-0.03, dimw+3*colw, rh, fill="FAFCFB")
    text(s, tx+0.06, ry, dimw-0.12, rh, dim, size=12, color=INK, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    for j,(val,best) in enumerate(vals):
        x=tx+dimw+j*colw
        text(s, x+0.12, ry, colw-0.24, rh, val, size=11.5,
             color=(GREEN_DEEP if best else INK_SOFT), bold=best,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    ry+=rh

# =========================================================================
# SLIDE 12 — TESTING RECOMMENDATION
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "Part 1 · Testing", "Testing: The Recommendation", 12)
cw=3.78; cy=2.45; ch=2.15
recs=[("Default","Custom pytest","Zero-cost, offline, enforced on every release. Start here.",True),
      ("Add when needed","LangSmith","For regression history and per-node performance over time.",False),
      ("Optional","deepeval / promptfoo","Proof the system can be scored by third-party tooling without forking.",False)]
for i,(t,h,b,acc) in enumerate(recs):
    card(s, 0.75+i*(cw+0.24), cy, cw, ch, tag=t, head=h, body=b, accent=acc)
# --- release-gate explainer ------------------------------------------------
gy=4.82
rect(s, 0.75, gy, 11.83, 2.0, fill=CARD_ACC, line=CARD_ACC_LN, round_=True)
text(s, 1.05, gy+0.2, 11.2, 0.35, "The bottom line: turn subjective quality into a release gate",
     size=15.5, color=INK, bold=True)
text(s, 1.05, gy+0.58, 11.2, 0.4,
     [[("CI runs the evals on every change. If scores fall below thresholds you set, the release is ", INK_SOFT),
       ("blocked automatically", INK, True),(" — no human eyeballing each debate.", INK_SOFT)]],
     size=12.5, spacing=1.08)
by=gy+1.05; bw=5.4; bh=0.82
# left threshold — deterministic
rect(s, 1.05, by, bw, bh, fill=WHITE, line=LINE, round_=True)
pill(s, 1.28, by+0.24, 1.68, "Deterministic", PILL_DET, PILL_DET_TX)
text(s, 3.1, by+0.12, bw-2.2, 0.3, "winner-valid ≥ 90%", size=13, color=INK, bold=True)
text(s, 3.1, by+0.44, bw-2.2, 0.32, "≥90% of test debates parsed a valid Pro/Con winner (a hard fact).",
     size=10.5, color=INK_SOFT, spacing=1.02)
# right threshold — judged
rx=1.05+bw+0.5
rect(s, rx, by, bw, bh, fill=WHITE, line=LINE, round_=True)
pill(s, rx+0.23, by+0.24, 1.42, "LLM-judge", PILL_JUD, PILL_JUD_TX)
text(s, rx+1.8, by+0.12, bw-1.95, 0.3, "mean relevance ≥ 3.5", size=13, color=INK, bold=True)
text(s, rx+1.8, by+0.44, bw-1.95, 0.32, "judge's average relevance across the set, ≥ 3.5 out of 5.",
     size=10.5, color=INK_SOFT, spacing=1.02)

# =========================================================================
# SLIDE 12 — DEPLOYMENT OPTIONS
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "Part 2 · Deployment", "Deployment: The Landscape", 13,
             sub="Managed = speed & convenience. Self-hosted = control & privacy, at the cost of building the resilience machinery yourself.")
cw=3.78; cy=2.75; ch=3.4
opts=[("Managed platform","LangSmith / LangGraph Platform","Hosted agent server — durable state and streaming handled for you. Fastest path; vendor lock-in + Enterprise license to self-host the server.",False),
      ("Managed platform","Google ADK","Google's managed agent runtime (Vertex Agent Engine). Cloud-native, scales for you — ties you to GCP.",False),
      ("Self-hosted","Roll our own","Full control and privacy. You must solve durability, streaming, and failover — the next slides show how.",True)]
for i,(t,h,b,acc) in enumerate(opts):
    card(s, 0.75+i*(cw+0.24), cy, cw, ch, tag=t, head=h, body=b, accent=acc)

# =========================================================================
# SLIDE 13 — REDIS CHALLENGE
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "Part 2 · Deployment", "The Self-Hosting Challenge: Life Without Redis", 14)
cw=5.65; cy=2.4; ch=3.7
rect(s, 0.75, cy, cw, ch, fill=WASH, line=LINE, round_=True)
text(s, 0.75+0.32, cy+0.34, cw-0.6, 0.3, "THE PROBLEM", size=11, color="C0392B", bold=True)
text(s, 0.75+0.32, cy+0.72, cw-0.6, 0.5, "Streaming is glued to execution", size=18, color=INK, bold=True)
text(s, 0.75+0.32, cy+1.35, cw-0.6, 2.2,
     "A single node couples graph execution and the client's live stream into one process.\n\nBehind a load balancer, the node a user is watching may not be the node doing the work — and there's no way to relay between them. The connection drops, the live view dies.",
     size=13, color=INK_SOFT, spacing=1.14)
x2=0.75+cw+0.35
rect(s, x2, cy, cw, ch, fill=CARD_ACC, line=CARD_ACC_LN, round_=True)
text(s, x2+0.32, cy+0.34, cw-0.6, 0.3, "THE FIX", size=11, color=TEAL_DEEP, bold=True)
text(s, x2+0.32, cy+0.72, cw-0.6, 0.5, "Redis pub/sub decouples them", size=18, color=INK, bold=True)
text(s, x2+0.32, cy+1.35, cw-0.6, 2.2,
     [[("A channel per run separates \"who streams to the user\" from \"who executes the agent.\" ", INK_SOFT),("Any node can relay any run.", INK, True)],
      [("", INK_SOFT)],
      [("Pair it with durable state (", INK_SOFT),("Postgres checkpoints", TEAL_DEEP, True),(") so a dead executor can be resumed — Redis alone fixes streaming, not execution recovery.", INK_SOFT)]],
     size=13, spacing=1.14, space_after=6)

# =========================================================================
# SLIDE 14 — REFERENCE ARCHITECTURE
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "Part 2 · Deployment", "The Reference Architecture (with Redis)", 15,
             sub="A hand-rolled version of the official LangGraph Agent Server — the same two building blocks it uses.")
cx=13.333/2
def abox(cxc, y, w, h, t, sub2=None, fill=WHITE, ln=LINE):
    rect(s, cxc-w/2, y, w, h, fill=fill, line=ln, line_w=1.25, round_=True)
    text(s, cxc-w/2, y+(0.16 if sub2 else h/2-0.16), w, 0.35, t, size=14, color=INK, bold=True, align=PP_ALIGN.CENTER)
    if sub2:
        text(s, cxc-w/2, y+0.52, w, 0.4, sub2, size=10, color=INK_SOFT, align=PP_ALIGN.CENTER, spacing=1.0)
abox(cx, 2.55, 4.0, 0.9, "Streamlit UI Client", "POST /start  ·  GET /stream (SSE)")
arrow_d(s, cx-0.13, 3.5, size=0.22)
abox(cx, 3.78, 6.6, 0.85, "Load Balancer · nginx", "routes to any node — client doesn't care which", fill="F2FBFC", ln="B8E2E6")
arrow_d(s, cx-0.13, 4.7, size=0.22)
# node row
nw=2.0; ny=4.95
for i in range(3):
    nxx = cx-3.1+i*2.1
    rect(s, nxx, ny, nw, 0.6, fill=WHITE, line=CARD_ACC_LN, line_w=1.25, round_=True)
    text(s, nxx, ny+0.13, nw, 0.35, f"debate-node {i+1}", size=12.5, color=INK, bold=True, align=PP_ALIGN.CENTER)
text(s, cx-4.5, 5.66, 9.0, 0.3, "↓  checkpoint read/write & ownership heartbeat   ·   publish / subscribe  ↓",
     size=10.5, color=INK_FAINT, bold=True, align=PP_ALIGN.CENTER)
# datastores
dw=4.7; dy=6.02
abox(cx-2.5, dy, dw, 0.85, "Postgres", "durable checkpoints + run ownership → any node resumes", fill="F4F8FD", ln="A9C7E8")
abox(cx+2.5, dy, dw, 0.85, "Redis", "pub/sub channel per run → streaming decoupled from execution", fill="FDF4F4", ln="E8B3B3")

# =========================================================================
# SLIDE 15 — PAYOFF
# =========================================================================
s = prs.slides.add_slide(BLANK)
content_head(s, "Part 2 · Deployment", "The Payoff: Surviving a Crash", 16)
rect(s, 0.75, 2.5, 11.83, 1.0, fill=WASH2, line=CARD_ACC_LN, round_=True)
text(s, 0.9, 2.66, 11.5, 0.7, [[("Kill the node running a live debate — ", INK),("another node picks it up mid-sentence and finishes it.", INK, True),("  The user never notices.", INK)]],
     size=17, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, spacing=1.05)
cw=5.65; cy=3.95; ch=2.3
card(s, 0.75, cy, cw, ch, tag="Failure mode 1", head="You lose your screen",
     body="The client disconnects, but the executor is fine. Redis re-attach — reconnect to the same run's channel.")
card(s, 0.75+cw+0.35, cy, cw, ch, tag="Failure mode 2", head="You lose the worker",
     body="The executing node dies. Its heartbeat goes stale, another node claims ownership and resumes from the Postgres checkpoint.")

# =========================================================================
# SLIDE 16 — CLOSE
# =========================================================================
s = prs.slides.add_slide(BLANK)
grad_bg(s)
logo(s, white=True, w=2.0)
text(s, 0.95, 1.5, 10, 0.4, "WHAT TRANSFERS TO EVERY AGENT WE BUILD", size=13, color="EAF7F4", bold=True)
text(s, 0.9, 2.15, 11.5, 2.0,
     [[("An agent isn't ready when it ", WHITE),("works", YELLOW, True),(" —", WHITE)],
      [("it's ready when it's ", WHITE),("measurable", YELLOW, True),(" and ", WHITE),("survivable.", YELLOW, True)]],
     size=38, bold=True, spacing=1.08)
py=4.7
for i,(pn,pp) in enumerate([("TRUST","Define dimensions → split deterministic vs. judge → gate releases automatically."),
                             ("RESILIENCE","Durable state + streaming decoupled with Redis + automatic failover.")]):
    px=0.95+i*5.9
    rect(s, px, py, 5.6, 1.4, fill=None, line="BFE6DE", line_w=1.25, round_=True)
    text(s, px+0.35, py+0.25, 5.0, 0.3, pn, size=13, color=YELLOW, bold=True)
    text(s, px+0.35, py+0.62, 5.0, 0.7, pp, size=14, color=WHITE, spacing=1.08)
text(s, 0.95, 6.6, 6, 0.3, "Thank you  ·  Talentica", size=13, color="EAF7F4", bold=True)

out = os.path.join(HERE, "presentation.pptx")
prs.save(out)
print("saved:", out, "| slides:", len(prs.slides._sldIdLst))
