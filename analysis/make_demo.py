"""Build demo_slides.pdf: the slides behind the two-minute demo in demo_script.md.

    python analysis/make_demo.py

Figures: May to July 2026 check and the 20 rolling tests in validate_rolling.py.
"""

from __future__ import annotations

from reportlab.lib.colors import HexColor, white
from reportlab.pdfgen import canvas

from make_pitch import (ACCENT, DIM, H, INK, MUTED, NAVY, PANEL, RED, SITE, TEAL, W, bullet_list,
                        card, para, slide)

OUT = __import__("pathlib").Path(__file__).resolve().parent.parent / "demo_slides.pdf"


def question_slide(c):
    c.setFillColor(NAVY)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(TEAL)
    c.roundRect(56, H - 92, 178, 28, 14, stroke=0, fill=1)
    c.setFillColor(NAVY)
    c.setFont("Helvetica-Bold", 11)
    c.drawCentredString(145, H - 82, "UNI TRIFECTA")
    para(c, "What should a 2-bedroom flat with parking in Zetland rent for?", 56, H - 160, 820, size=36,
         font="Helvetica-Bold", color=white, leading=1.15)
    x0, x1, y = 90, 870, 190
    lo_axis, hi_axis = 900, 1560

    def px(v):
        return x0 + (v - lo_axis) / (hi_axis - lo_axis) * (x1 - x0)

    c.setFillColor(HexColor("#1e3a5f"))
    c.roundRect(x0, y - 9, x1 - x0, 18, 9, stroke=0, fill=1)
    c.setFillColor(ACCENT)
    c.roundRect(px(978), y - 9, px(1500) - px(978), 18, 9, stroke=0, fill=1)
    for value, label, color, above in ((978, "$978", white, False), (1500, "$1,500", white, False),
                                       (1165, "Suburb median $1,165", HexColor("#fca5a5"), True)):
        c.setStrokeColor(color)
        c.setLineWidth(3 if above else 1.5)
        c.line(px(value), y - 26, px(value), y + 26)
        c.setFont("Helvetica-Bold", 15)
        c.setFillColor(color)
        c.drawCentredString(px(value), y + 36 if above else y - 46, label)
    c.setFont("Helvetica", 13)
    c.setFillColor(HexColor("#94a3b8"))
    c.drawCentredString((x0 + x1) / 2, 80, "Typical weekly ask, building by building")


def found_slide(c):
    slide(c, 2, "What we found", "The building sets the rent. Not the suburb, not the floor.")
    card(c, 56, 220, 270, 150, "$522", "a week between the cheapest and dearest Zetland building, same flat type", ACCENT)
    card(c, 345, 220, 270, 150, "$1.46", "a week per extra floor, once you know the building", ACCENT)
    card(c, 634, 220, 270, 150, "$76", "a week for a car space, typically", ACCENT)
    c.setFillColor(PANEL)
    c.roundRect(56, 80, 848, 100, 10, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 40)
    c.setFillColor(RED)
    c.drawString(80, 112, "$100")
    para(c, "a week: how far a suburb average typically misses a flat's asking rent", 230, 132, 640, size=18,
         color=INK)


def how_slide(c):
    slide(c, 3, "How it works", "Start with the closest evidence. Widen only when it runs out.")
    boxes = [
        ("This flat's own past rents", "count most when it advertised before"),
        ("Same building", "same bedrooms, bathrooms and parking"),
        ("Nearest buildings", "within 1 km, closer ones count more"),
        ("Suburb", "only if nothing is close"),
    ]
    x, y, w, h, gap = 56, 250, 196, 120, 22
    for i, (head, sub) in enumerate(boxes):
        bx = x + i * (w + gap)
        c.setFillColor(NAVY if i == 0 else PANEL)
        c.roundRect(bx, y, w, h, 10, stroke=0, fill=1)
        para(c, head, bx + 16, y + h - 30, w - 32, size=15, font="Helvetica-Bold",
             color=white if i == 0 else INK, leading=1.2)
        para(c, sub, bx + 16, y + h - 72, w - 32, size=12,
             color=HexColor("#cbd5e1") if i == 0 else DIM, leading=1.3)
        if i < len(boxes) - 1:
            ax = bx + w + 4
            c.setStrokeColor(MUTED)
            c.setLineWidth(2)
            c.line(ax, y + h / 2, ax + gap - 6, y + h / 2)
    bullet_list(c, [
        "65,777 flats, each with two weekly rents: with a car space and without.",
        "Older adverts are brought up to July 2026 prices, and newer ones count more.",
        "Nothing dated after 31 July 2026 is used.",
    ], 56, 200, 850, size=15, gap=8)


def works_slide(c):
    slide(c, 4, "Does it work?", "Tested only on adverts the model had not seen.")
    rows = [("Suburb average (the example)", 100.00, MUTED), ("Ours, 20 rolling two-month tests", 51.00, HexColor("#93c5fd")),
            ("Ours, May to July 2026", 45.37, ACCENT)]
    top, bar_h, gap, x_bar, max_w = 370, 34, 18, 360, 440
    for i, (name, miss, color) in enumerate(rows):
        y = top - i * (bar_h + gap)
        c.setFont("Helvetica-Bold" if i else "Helvetica", 15)
        c.setFillColor(INK)
        c.drawString(56, y + 11, name)
        c.setFillColor(color)
        c.roundRect(x_bar, y, max_w * miss / 100, bar_h, 6, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 15)
        c.setFillColor(INK)
        c.drawString(x_bar + max_w * miss / 100 + 10, y + 11, f"${miss:.2f}")
    c.setFont("Helvetica", 12)
    c.setFillColor(DIM)
    c.drawString(56, 205, "Typical (median) miss, dollars a week. Lower is better.")
    card(c, 56, 60, 410, 110, "3 in 4", "estimates land within $100 (74% rolling, 77% May to July; suburb method 57%)",
         ACCENT)
    card(c, 494, 60, 410, 110, "Same setup", "learn from adverts up to a month's end, then score the next two months, "
                                             "just like the real test")


def demo_slide(c):
    slide(c, 5, "Live demo", "Is my rent fair? Ask in 20 seconds.")
    steps = [
        ("1", "Type your address", "e.g. 841/2C Defries Avenue, Zetland"),
        ("2", "Check the details", "bedrooms and parking fill in from the records"),
        ("3", "Enter your rent", "see how it compares with similar flats"),
    ]
    for i, (num, head, sub) in enumerate(steps):
        x = 56 + i * 289
        c.setFillColor(PANEL)
        c.roundRect(x, 170, 270, 190, 10, stroke=0, fill=1)
        c.setFillColor(ACCENT)
        c.circle(x + 40, 315, 22, stroke=0, fill=1)
        c.setFont("Helvetica-Bold", 20)
        c.setFillColor(white)
        c.drawCentredString(x + 40, 308, num)
        para(c, head, x + 20, 260, 230, size=18, font="Helvetica-Bold")
        para(c, sub, x + 20, 230, 230, size=14, color=DIM, leading=1.35)
    para(c, "The range tightens when we know more: about 7% wide for a flat with its own advert history.",
         56, 130, 850, size=15, color=INK)
    c.setFont("Helvetica-Bold", 18)
    c.setFillColor(ACCENT)
    c.drawString(56, 80, SITE)


def next_slide(c):
    slide(c, 6, "What's next", "Building by building, not suburb by suburb.")
    para(c, "Where it's weaker", 56, 370, 400, size=18, font="Helvetica-Bold")
    bullet_list(c, [
        "Buildings that have never advertised: no evidence of their own.",
        "Renovated or furnished flats asking well above their building (about 1 ask in 8).",
    ], 56, 336, 400, size=15, gap=10)
    para(c, "What we'd add", 500, 370, 400, size=18, font="Helvetica-Bold")
    bullet_list(c, [
        "Microburbs data such as transport, schools and new development for buildings with no adverts.",
        "Monthly refresh, so every check uses the latest adverts.",
    ], 500, 336, 400, size=15, gap=10)
    c.setFillColor(NAVY)
    c.roundRect(56, 70, 848, 80, 10, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(white)
    c.drawCentredString(W / 2, 102, f"Thanks!   {SITE}")


def backup_slide(c):
    slide(c, 7, "Backup for questions", "The technical details, if asked.")
    bullet_list(c, [
        "Estimate: weighted median of past asking rents. Older asks are brought forward with a citywide quarterly "
        "index and count half as much every 3 years.",
        "Order of evidence: own past asks (75% weight) > building (same bedrooms, parking; bathrooms if 3+ adverts) "
        "> 10 nearest buildings within 1 km (weight halves every 500 m) > suburb > bedrooms.",
        "Thin buildings are pulled toward their neighbours. Each parking side is adjusted by its own evidence.",
        "Missing parking side: other rent plus or minus the local car-space gap, capped at 25% of rent.",
        "Testing: settings chosen on rolling tests before May 2026. May to July was looked at across versions, "
        "so the rolling $51 is the fairer guide.",
        "Hard cases (rolling tests): no own history $63 typical miss; no usable building history $90.",
        "Tried and dropped: floor adjustment, forcing parking above no parking, a growth lift after 31 July.",
    ], 56, 380, 850, size=13.5, gap=7)


def main() -> None:
    c = canvas.Canvas(str(OUT), pagesize=(W, H))
    c.setTitle("Uni Trifecta - two-minute demo")
    c.setAuthor("Uni Trifecta")
    for build in (question_slide, found_slide, how_slide, works_slide, demo_slide, next_slide, backup_slide):
        build(c)
        c.showPage()
    c.save()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
