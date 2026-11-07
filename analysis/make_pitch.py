"""Build pitch.pdf: the slide deck and 45-second script for the rents task.

    python analysis/make_pitch.py

Figures are the May to July 2026 check from report.html. Rerun make_report.py
first if the estimate changes, then update FIGURES below.
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "pitch.pdf"
ASSETS = HERE / "pitch_assets"
SITE = "microburbsdataanalysis.vercel.app"

W, H = 960, 540
NAVY = HexColor("#0b1f3a")
INK = HexColor("#1f2933")
DIM = HexColor("#5b6770")
LINE = HexColor("#d9dee3")
PANEL = HexColor("#f2f4f7")
ACCENT = HexColor("#3b82f6")
TEAL = HexColor("#14b8a6")
RED = HexColor("#d7153a")
MUTED = HexColor("#9aa5b1")

STEPS = [
    ("Suburb, bedrooms, parking (example)", 100.00, 56.8, 0.645),
    ("Same building, last year", 59.41, 69.4, 0.781),
    ("Older asks brought forward", 53.48, 72.0, 0.820),
    ("Plus nearest buildings", 52.29, 72.2, 0.834),
    ("Plus own past asks, bathrooms", 45.00, 77.1, 0.872),
]


def wrap(c, text, font, size, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if c.stringWidth(trial, font, size) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def para(c, text, x, y, width, size=15, font="Helvetica", color=INK, leading=1.35):
    c.setFont(font, size)
    c.setFillColor(color)
    for line in wrap(c, text, font, size, width):
        c.drawString(x, y, line)
        y -= size * leading
    return y


def slide(c, number, kicker, title):
    c.setFillColor(white)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(ACCENT)
    c.rect(0, H - 6, W, 6, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(ACCENT)
    c.drawString(56, H - 50, kicker.upper())
    y = para(c, title, 56, H - 86, 850, size=28, font="Helvetica-Bold", color=INK, leading=1.2)
    c.setFont("Helvetica", 9)
    c.setFillColor(MUTED)
    c.drawString(56, 24, "Uni Trifecta  |  Microburbs Hackathon  |  Rents task  |  City of Sydney flats at 31 July 2026")
    c.drawRightString(W - 56, 24, str(number))
    return y


def card(c, x, y, w, h, big, label, color=INK):
    c.setFillColor(PANEL)
    c.roundRect(x, y, w, h, 10, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 30)
    c.setFillColor(color)
    c.drawString(x + 20, y + h - 50, big)
    para(c, label, x + 20, y + h - 76, w - 40, size=12.5, color=DIM, leading=1.3)


def bullet_list(c, items, x, y, width, size=15, gap=10):
    for item in items:
        c.setFillColor(ACCENT)
        c.circle(x + 4, y + size * 0.33, 3.2, stroke=0, fill=1)
        y = para(c, item, x + 18, y, width - 18, size=size) - gap
    return y


def title_slide(c):
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(TEAL)
    c.roundRect(56, H - 92, 178, 28, 14, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(145, H - 82, "MICROBURBS HACKATHON")
    para(c, "Which building a flat is in sets its rent.", 56, H - 170, 820, size=42,
         font="Helvetica-Bold", color=white, leading=1.15)
    para(c, "Its floor barely does.", 56, H - 270, 820, size=42, font="Helvetica-Bold",
         color=HexColor("#93c5fd"), leading=1.15)
    para(c, "Two weekly rents, with and without a car space, for all 65,777 City of Sydney flats, "
            "and a rent check any tenant can use.", 56, H - 340, 760, size=17, color=HexColor("#cbd5e1"))
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(white)
    c.drawString(56, 70, SITE)
    c.setFont("Helvetica", 12)
    c.setFillColor(HexColor("#94a3b8"))
    c.drawString(56, 50, "Uni Trifecta  |  Rents task, 7 November 2026")


def problem_slide(c):
    slide(c, 2, "The problem", "A suburb median misses a flat's rent by $100 a week.")
    para(c, "2-bedroom flats with parking in Zetland: one suburb, one flat type, 96 buildings with at least five adverts.",
         56, 380, 840, size=16, color=DIM)
    x0, x1, y = 90, 870, 270
    low, high, suburb = 978, 1500, 1165
    lo_axis, hi_axis = 900, 1560

    def px(v):
        return x0 + (v - lo_axis) / (hi_axis - lo_axis) * (x1 - x0)

    c.setFillColor(LINE)
    c.roundRect(x0, y - 9, x1 - x0, 18, 9, stroke=0, fill=1)
    c.setFillColor(ACCENT)
    c.roundRect(px(low), y - 9, px(high) - px(low), 18, 9, stroke=0, fill=1)
    for value, label, color, above in ((low, "$978", INK, False), (high, "$1,500", INK, False),
                                       (suburb, "Suburb median $1,165", RED, True)):
        c.setStrokeColor(color)
        c.setLineWidth(3 if color == RED else 1.5)
        c.line(px(value), y - 26, px(value), y + 26)
        c.setFont("Helvetica-Bold", 14)
        c.setFillColor(color)
        c.drawCentredString(px(value), y + 36 if above else y - 46, label)
    c.setFont("Helvetica", 13)
    c.setFillColor(DIM)
    c.drawCentredString((x0 + x1) / 2, y - 80, "Typical weekly asking rent of each building, brought forward to April 2026")
    card(c, 56, 60, 270, 100, "$522", "a week between the cheapest and dearest building")
    card(c, 345, 60, 270, 100, "$100", "typical miss for suburb, bedrooms and parking")
    card(c, 634, 60, 270, 100, "56.8%", "of asks within $100 with the suburb method")


def insight_slide(c):
    slide(c, 3, "What we found", "The building sets the rent. Height, once the building is known, adds almost nothing.")
    card(c, 56, 200, 270, 160, "$522", "Spread across Zetland buildings for one flat type. Waterloo: $905 to $1,376.", ACCENT)
    card(c, 345, 200, 270, 160, "$1.46", "a week per floor, across 18,153 adverts in 1,709 same-building groups.", ACCENT)
    card(c, 634, 200, 270, 160, "$76", "a week for a car space, about $3,971 a year. Studio $32, 3-bedroom $105.", ACCENT)
    bullet_list(c, [
        "11.9% of new asks were more than $100 above their building's going rate. In Surry Hills and Potts Point, about 17%.",
        "Flats in fast-growing blocks (homes up more than 30% since 2021) asked 2.5% above their suburb. Blocks with no new homes asked 2.6% below.",
        "Relisted flats asked 3.8% more than last time, but 0.6% less once the market move is taken out.",
    ], 56, 160, 850, size=14, gap=6)


def method_slide(c):
    slide(c, 4, "How we estimate", "Start with the narrowest evidence, widen only when it runs out.")
    boxes = [
        ("This flat's own past asks", "75% of the weight where it advertised before"),
        ("Same building", "bedrooms, bathrooms, parking; one advert is enough"),
        ("10 nearest buildings", "within 1 km, where the building never advertised"),
        ("Suburb, then bedrooms", "only when nothing is in reach"),
    ]
    x, y, w, h, gap = 56, 250, 196, 120, 22
    for i, (head, sub) in enumerate(boxes):
        bx = x + i * (w + gap)
        c.setFillColor(NAVY if i == 0 else PANEL)
        c.roundRect(bx, y, w, h, 10, stroke=0, fill=1)
        para(c, head, bx + 16, y + h - 30, w - 32, size=15, font="Helvetica-Bold",
             color=white if i == 0 else INK, leading=1.2)
        para(c, sub, bx + 16, y + h - 72, w - 32, size=11.5,
             color=HexColor("#cbd5e1") if i == 0 else DIM, leading=1.3)
        if i < len(boxes) - 1:
            ax = bx + w + 4
            c.setStrokeColor(MUTED)
            c.setLineWidth(2)
            c.line(ax, y + h / 2, ax + gap - 8, y + h / 2)
            c.setFillColor(MUTED)
            p = c.beginPath()
            p.moveTo(ax + gap - 8, y + h / 2 + 5)
            p.lineTo(ax + gap - 2, y + h / 2)
            p.lineTo(ax + gap - 8, y + h / 2 - 5)
            p.close()
            c.drawPath(p, stroke=0, fill=1)
    bullet_list(c, [
        "Every older ask is brought forward with a city-wide quarterly index, then weighted down as it ages (three-year half-life).",
        "Where a building only advertised one parking answer, the other rent adds or removes the local car-space gap.",
        "Nothing dated after 31 July 2026 is read. No live listings.",
    ], 56, 200, 850, size=14, gap=6)


def results_slide(c):
    slide(c, 5, "Separate check: 3,954 adverts, May to July 2026", "Typical miss: $100 down to $45 a week.")
    top, bar_h, gap, x_label, x_bar, max_w = 370, 30, 16, 56, 330, 420
    for i, (name, miss, within, r2) in enumerate(STEPS):
        y = top - i * (bar_h + gap)
        last = i == len(STEPS) - 1
        c.setFont("Helvetica-Bold" if last else "Helvetica", 13.5)
        c.setFillColor(INK)
        c.drawString(x_label, y + 10, name)
        c.setFillColor(ACCENT if last else (MUTED if i == 0 else HexColor("#bfd3f2")))
        c.roundRect(x_bar, y, max_w * miss / 100, bar_h, 5, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 13.5)
        c.setFillColor(INK)
        c.drawString(x_bar + max_w * miss / 100 + 10, y + 10, f"${miss:.2f}")
    card(c, 56, 60, 270, 100, "77.1%", "of asks within $100 (was 56.8%)", ACCENT)
    card(c, 345, 60, 270, 100, "0.872", "R squared: share of rent variation explained (was 0.645)", ACCENT)
    card(c, 634, 60, 270, 100, "$0.97", "typical bias: half asked more, half asked less")


def trust_slide(c):
    slide(c, 6, "Why you can trust it", "Tuned on the past, scored once on adverts it never saw.")
    bullet_list(c, [
        "Every setting was chosen on three earlier folds: Aug-Oct 2025, Nov 2025-Jan 2026 and Feb-Apr 2026. "
        "The May-July 2026 adverts were scored once, after the rule was frozen.",
        "No drift across the test window: May $44.12, June $43.53, July $49.04. The hidden ads run two months past the as-at date.",
        "Rebuilt before each of seven earlier quarters, the typical miss stayed between $50 and $62.",
        "Drawing 1,699 adverts at random (the hidden set's size) 2,000 times: typical miss $42.38 to $47.30, nine times in ten.",
        "Floor level was tested the same way and dropped: it made two of the three folds worse.",
    ], 56, 370, 850, size=15, gap=10)


def product_slide(c):
    slide(c, 7, "The product", "A rent check any City of Sydney tenant can use in 20 seconds.")
    image = ImageReader(str(ASSETS / "rent_check_result.png"))
    iw, ih = image.getSize()
    w = 395
    h = w * ih / iw
    c.setStrokeColor(LINE)
    c.setLineWidth(1)
    c.rect(56, 395 - h + 0, w, h, stroke=1, fill=0)
    c.drawImage(image, 56, 395 - h, w, h)
    bullet_list(c, [
        "Find your flat from 65,777 addresses: '1406/157 Redfern St' or 'Unit 1611, 301 Botany Rd'.",
        "Bedrooms and parking come pre-filled from the flat's records.",
        "See your rent against the typical ask, the middle half of new adverts, and the dollars a year at stake.",
        "Ranges tighten with evidence: 7.4% wide where the flat advertised before, 13% from its building alone.",
    ], 480, 380, 425, size=14, gap=8)
    c.setFont("Helvetica-Bold", 15)
    c.setFillColor(ACCENT)
    c.drawString(480, 80, SITE)


def who_slide(c):
    slide(c, 8, "Who it helps", "One estimate, three decisions.")
    cols = [
        ("Tenants", "Check an advert or a rent rise against the same building before signing. "
                    "11.9% of asks sat more than $100 above the building's rate."),
        ("Landlords and agents", "Price against their own building and flat type, with and without a car space, "
                                 "instead of a suburb figure that can be $300 off."),
        ("Microburbs", "Building-level rent for every flat in the city, ready for property profiles, "
                       "rental yield and the Median Mirage story."),
    ]
    for i, (head, body) in enumerate(cols):
        x = 56 + i * 289
        c.setFillColor(PANEL)
        c.roundRect(x, 110, 270, 260, 10, stroke=0, fill=1)
        c.setFillColor(ACCENT)
        c.rect(x, 364, 270, 6, stroke=0, fill=1)
        para(c, head, x + 20, 330, 230, size=19, font="Helvetica-Bold")
        para(c, body, x + 20, 295, 230, size=14, color=DIM, leading=1.4)


def limits_slide(c):
    slide(c, 9, "What remains uncertain", "Honest limits, and what we would add next.")
    para(c, "Limits", 56, 380, 400, size=17, font="Helvetica-Bold")
    bullet_list(c, [
        "Buildings that never advertised a flat type still miss by about $98 a week, against $43 with building evidence.",
        "Flats that never advertised themselves can expect nearer $59 than $45.",
        "Condition, view and orientation are not in the data.",
    ], 56, 348, 400, size=14, gap=8)
    para(c, "Next", 500, 380, 400, size=17, font="Helvetica-Bold")
    bullet_list(c, [
        "Microburbs API features (stations, schools, development) for the never-advertised buildings.",
        "Refresh monthly so every tenant check uses the latest asks.",
        "Rent-rise alerts: flag increases far above the building's own movement.",
    ], 500, 348, 400, size=14, gap=8)


def script_slide(c):
    slide(c, 10, "45-second pitch (pitch.mp4)", "Script")
    lines = [
        ("0-8 s", "Two buildings in Zetland. Same suburb, same flat: two bedrooms with parking. One asks $978 a "
                  "week, the other $1,500. The suburb median says $1,165 for both."),
        ("8-18 s", "We found that the building a flat is in sets its rent. Its floor barely matters: about "
                   "$1.46 a week per floor."),
        ("18-32 s", "So we price every one of the 65,777 City of Sydney flats from its own past adverts and its "
                    "own building, with and without a car space. On adverts we held back, the typical miss is "
                    "$45 a week, against $100 for the suburb method. More than three in four land within $100."),
        ("32-45 s", "And any tenant can use it. Type your address, enter your rent, and see in 20 seconds whether "
                    "you are paying fair. Building by building, not suburb by suburb."),
    ]
    y = 380
    for when, text in lines:
        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(ACCENT)
        c.drawString(56, y, when)
        y = para(c, text, 140, y, 760, size=15, leading=1.4) - 14


def main() -> None:
    c = canvas.Canvas(str(OUT), pagesize=(W, H))
    c.setTitle("Which building a flat is in sets its rent - Microburbs Hackathon pitch")
    c.setAuthor("Uni Trifecta")
    for build in (title_slide, problem_slide, insight_slide, method_slide, results_slide,
                  trust_slide, product_slide, who_slide, limits_slide, script_slide):
        build(c)
        c.showPage()
    c.save()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
