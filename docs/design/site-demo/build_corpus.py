"""Build the nAI website's demo corpus (fictional; see README.md) into ./corpus.

    python build_corpus.py          # needs reportlab and Pillow (build time only)

Every name, number and address below is made up and looks it: "Example", "Beispiel" and "Demo" names,
.example domains, zeroed IBANs. Dates are in 2027, amounts in euro. Not part of nai-bench.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
OUT = HERE / "corpus"

CAR_INSURANCE = [
    ("Example Insurance Ltd.", 14),
    ("Car insurance: renewal notice 2027", 12),
    ("", 10),
    ("Policyholder: Alex Example, 1 Example Street, 00000 Demotown", 10),
    ("Policy number: DEMO-CAR-0000-1234", 10),
    ("Vehicle: compact estate car, registration DEMO 123", 10),
    ("", 10),
    ("Your policy renews on 1 March 2027 for another year.", 10),
    ("Cover: third-party liability and fully comprehensive.", 10),
    ("Yearly premium from 1 March 2027: EUR 486.40, paid by direct debit.", 10),
    ("Excess (deductible): EUR 300 per claim; glass damage EUR 150.", 10),
    ("No-claims class: SF 12 (unchanged).", 10),
    ("", 10),
    ("To cancel, tell us at least one month before the renewal date.", 10),
    ("Questions: service@insurance.example", 10),
]

INVOICE = [
    ("Demo Studio", 14),
    ("Invoice 2027-041", 12),
    ("", 10),
    ("Invoice date: 15 January 2027", 10),
    ("Due date: 14 February 2027 (30 days)", 10),
    ("Client: Beispiel Bakery, 2 Sample Road, 00000 Demotown", 10),
    ("", 10),
    ("Item                                   Hours   Rate      Amount", 10),
    ("Logo refresh and colour palette          12   EUR 85   EUR 1,020.00", 10),
    ("Menu board design (3 boards)              6   EUR 85     EUR 510.00", 10),
    ("", 10),
    ("Net                                                  EUR 1,530.00", 10),
    ("VAT 19 %                                               EUR 290.70", 10),
    ("Total due                                            EUR 1,820.70", 10),
    ("", 10),
    ("Please pay to IBAN DE00 0000 0000 0000 0000 00, reference 2027-041.", 10),
    ("studio@demo-studio.example", 10),
]

BOILER_LOG = """# Boiler service log

Gas condensing boiler in the basement (fictional demo household, 1 Example Street).

## 12 October 2026: yearly service

- Technician: Sam Demo, Demo Heating Service
- Burner cleaned, condensate trap rinsed, flue gas measured: 41 °C, CO 12 ppm (fine).
- The expansion vessel pressure was low (0.6 bar); topped up to 1.2 bar.
- Cost: EUR 164.50.

## Next service

Due in October 2027. Book it in September; Demo Heating Service asks for four weeks' notice.

The boiler warranty runs until 30 June 2029, as long as every yearly service is done and logged.
"""

FIBRE_CONTRACT = """Beispiel Glasfaser GmbH (fiktiv)
Glasfaser-Vertrag: Vertragsübersicht

Kunde: Alex Example, Beispielstraße 1, 00000 Demostadt
Kundennummer: DEMO-GF-000042

Tarif: Glasfaser 500 (500 Mbit/s im Download, 100 Mbit/s im Upload)
Monatlicher Preis: 44,90 EUR, ab dem 13. Monat 49,90 EUR
Einmaliger Bereitstellungspreis: 0,00 EUR

Vertragsbeginn: 1. September 2025
Mindestlaufzeit: 24 Monate, also bis zum 31. August 2027
Kündigungsfrist: Nach der Mindestlaufzeit ist der Vertrag mit einer Frist von einem Monat kündbar.
Kündigung in Textform an kuendigung@glasfaser.example

Router: Leihgerät, bei Vertragsende innerhalb von 14 Tagen zurückzusenden.
"""

RECEIPT_LINES = [
    "DEMO HARDWARE STORE",
    "1 Example Street, Demotown",
    "",
    "Receipt 0042    2027-03-06 10:14",
    "",
    "Wood screws 4x40, 200 pcs   7.99",
    "Wall plugs 6 mm, 100 pcs    4.49",
    "Cordless drill bits set    19.95",
    "Masking tape 30 mm          3.29",
    "",
    "TOTAL EUR                  35.72",
    "Paid by card",
    "",
    "Returns within 30 days with receipt",
]


def write_pdf(path: Path, lines: list[tuple[str, int]]) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4, invariant=1)  # invariant: byte-reproducible
    y = A4[1] - 25 * mm
    for text, size in lines:
        font = (
            "Courier"
            if text.startswith(("Item ", "Logo ", "Menu ", "Net ", "VAT ", "Total "))
            else "Helvetica"
        )
        pdf.setFont(font + ("-Bold" if size > 10 else ""), size)
        pdf.drawString(20 * mm, y, text)
        y -= size * 0.5 * mm + 3 * mm
    pdf.save()


def write_receipt_photo(path: Path) -> None:
    """A receipt on a grey table, slightly turned and soft, the way a phone photo of one looks."""
    font = ImageFont.truetype("/usr/share/fonts/TTF/DejaVuSansMono.ttf", 26)
    paper = Image.new("L", (640, 40 + 38 * len(RECEIPT_LINES)), 246)
    draw = ImageDraw.Draw(paper)
    for i, line in enumerate(RECEIPT_LINES):
        draw.text((28, 24 + 38 * i), line, fill=30, font=font)
    photo = Image.new("L", (840, paper.height + 160), 150)
    photo.paste(paper, (100, 80))
    photo = photo.rotate(-2.5, resample=Image.Resampling.BICUBIC, fillcolor=150).filter(
        ImageFilter.GaussianBlur(0.6)
    )
    photo.convert("RGB").save(path, "JPEG", quality=88)


def main() -> None:
    files = {
        "Household/Insurance/car-insurance-2027.pdf": lambda p: write_pdf(p, CAR_INSURANCE),
        "Household/Heating/boiler-service-log.md": lambda p: p.write_text(BOILER_LOG, "utf-8"),
        "Household/Internet/Glasfaser-Vertrag.txt": lambda p: p.write_text(FIBRE_CONTRACT, "utf-8"),
        "Work/Invoices/invoice-2027-041.pdf": lambda p: write_pdf(p, INVOICE),
        "Photos/receipt-hardware-store.jpg": write_receipt_photo,
    }
    for relative, build in files.items():
        path = OUT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        build(path)
        print(f"{relative}: {path.stat().st_size} bytes")


if __name__ == "__main__":
    main()
