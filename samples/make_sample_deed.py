"""
Generate FICTIONAL Greek notarial deeds, each with a ground-truth JSON file.

Every name, number and address is invented. Tax IDs (ΑΦΜ) are chosen to fail
the official check-digit test, so they cannot belong to a real person.

The JSON next to each PDF holds the values the extractor should return, which
makes field-level accuracy measurable (see accuracy.py and benchmark.py).

Usage:
    python samples/make_sample_deed.py               # samples/sample_deed.pdf + .json
    python samples/make_sample_deed.py --dataset 10  # also samples/dataset/deed_01..10
    python samples/make_sample_deed.py --dataset 10 --scanned  # + scan-like copies
"""
from __future__ import annotations

import argparse
import io
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import fitz
from PIL import Image, ImageEnhance, ImageFilter

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from validators import afm_is_valid  # noqa: E402

GREEK_MONTHS = [
    "Ιανουαρίου", "Φεβρουαρίου", "Μαρτίου", "Απριλίου", "Μαΐου", "Ιουνίου",
    "Ιουλίου", "Αυγούστου", "Σεπτεμβρίου", "Οκτωβρίου", "Νοεμβρίου", "Δεκεμβρίου",
]

# ---------------------------------------------------------------------------
# Deed specification
# ---------------------------------------------------------------------------

@dataclass
class Person:
    name: str
    afm: str
    id_doc: str
    address: str | None = None


@dataclass
class DeedSpec:
    deed_type: str                      # "sale" | "parental_provision"
    notary: str
    location: str
    registry_number: str
    signed: date
    date_style: str                     # "words" | "numeric"
    sellers: list[Person]
    buyers: list[Person]
    property_type: str
    property_address: str
    municipal_unit: str
    floor: str | None
    area: float
    kaek: str
    permit: str
    price: int | None
    representative: Person | None = None
    represents: Person | None = None
    extra: dict = field(default_factory=dict)

    def truth(self) -> dict:
        """The values a perfect extraction would return."""
        def party(p: Person) -> dict:
            return {"full_name": p.name, "tax_id": p.afm, "id_document": p.id_doc, "address": p.address}

        reps = []
        if self.representative:
            r = self.representative
            reps.append(
                {"full_name": r.name, "represents": self.represents.name, "tax_id": r.afm, "id_document": r.id_doc}
            )
        return {
            "notary": {"name": self.notary, "location": self.location, "registry_number": self.registry_number},
            "sellers": [party(p) for p in self.sellers],
            "buyers": [party(p) for p in self.buyers],
            "legal_representatives": reps,
            "property": {
                "type": self.property_type,
                "address": self.property_address,
                "municipal_unit": self.municipal_unit,
                "floor": self.floor,
                "area_sqm": self.area,
                "kaek": self.kaek,
                "building_permit": self.permit,
            },
            "transaction": {"deed_type": self.deed_type, "price": self.price, "date": self.signed.isoformat()},
        }


# The original demo deed, kept fixed so the app's sample stays the same
SAMPLE = DeedSpec(
    deed_type="sale",
    notary="Ελένη Παπαδημητρίου-Δοκιμαστή",
    location="Αθήνα",
    registry_number="12.345",
    signed=date(2024, 3, 15),
    date_style="words",
    sellers=[
        Person("Γεώργιος Υποθετικός του Νικολάου", "123456789", "ΑΚ 000101", "Οδός Φανταστικής 12, Αθήνα"),
        Person("Μαρία Υποθετική του Ιωάννη", "987654320", "ΑΚ 000102", "Οδός Φανταστικής 12, Αθήνα"),
    ],
    buyers=[Person("Δημήτριος Παράδειγμα του Κωνσταντίνου", "111111110", "ΑΜ 000201", "Λεωφόρος Δοκιμών 45, Πειραιάς")],
    representative=Person("Αικατερίνη Δείγμα του Παναγιώτη", "222222220", "ΑΝ 000301"),
    property_type="διαμέρισμα",
    property_address="Οδός Ανύπαρκτης 7, Αθήνα",
    municipal_unit="Δημοτική Ενότητα Ζωγράφου",
    floor="2ος όροφος",
    area=85.4,
    kaek="999901000012/0/5",
    permit="1234/2005 του Πολεοδομικού Γραφείου Δοκιμών",
    price=185000,
)
SAMPLE.represents = SAMPLE.buyers[0]

# ---------------------------------------------------------------------------
# Random fictional deeds
# ---------------------------------------------------------------------------

MALE = ["Γεώργιος", "Δημήτριος", "Νικόλαος", "Ιωάννης", "Κωνσταντίνος", "Παναγιώτης", "Αθανάσιος", "Χρήστος"]
FEMALE = ["Μαρία", "Ελένη", "Αικατερίνη", "Σοφία", "Βασιλική", "Ευαγγελία", "Γεωργία", "Δήμητρα"]
FATHERS = ["Νικολάου", "Ιωάννη", "Γεωργίου", "Δημητρίου", "Κωνσταντίνου", "Παναγιώτη", "Αθανασίου", "Χρήστου"]
SURNAMES = [  # (male, female) — all invented
    ("Υποθετικός", "Υποθετική"), ("Δοκιμαστής", "Δοκιμαστή"), ("Φανταστικός", "Φανταστική"),
    ("Πλασματικός", "Πλασματική"), ("Εικονικός", "Εικονική"), ("Παράδειγμα", "Παράδειγμα"),
    ("Δείγμα", "Δείγμα"), ("Ανύπαρκτος", "Ανύπαρκτη"),
]
STREETS = ["Οδός Ανύπαρκτης", "Οδός Φανταστικής", "Λεωφόρος Δοκιμών", "Οδός Πλασματικής", "Οδός Υποθέσεων"]
CITIES = {
    "Αθήνα": ["Δημοτική Ενότητα Ζωγράφου", "Δημοτική Ενότητα Αμπελοκήπων", "Δημοτική Ενότητα Κυψέλης"],
    "Πειραιάς": ["Δημοτική Ενότητα Καστέλλας", "Δημοτική Ενότητα Νέου Φαλήρου"],
    "Θεσσαλονίκη": ["Δημοτική Ενότητα Καλαμαριάς", "Δημοτική Ενότητα Τριανδρίας"],
    "Πάτρα": ["Δημοτική Ενότητα Ρίου", "Δημοτική Ενότητα Πατρέων"],
    "Ηράκλειο": ["Δημοτική Ενότητα Νέας Αλικαρνασσού", "Δημοτική Ενότητα Ηρακλείου"],
}
PROPERTY_TYPES = {  # type → possible floors (None = no floor, e.g. a plot)
    "διαμέρισμα": ["1ος όροφος", "2ος όροφος", "3ος όροφος", "4ος όροφος"],
    "κατάστημα": ["ισόγειο"],
    "μονοκατοικία": [None],
    "οικόπεδο": [None],
}


def fake_afm(rng: random.Random) -> str:
    while True:
        afm = "".join(rng.choice("0123456789") for _ in range(9))
        if not afm_is_valid(afm):
            return afm


def fake_person(rng: random.Random, city: str, with_address: bool = True) -> Person:
    female = rng.random() < 0.5
    first = rng.choice(FEMALE if female else MALE)
    surname = rng.choice(SURNAMES)[1 if female else 0]
    id_doc = f"Α{rng.choice('ΚΜΝΒΕΗΙΤΧ')} {rng.randint(0, 999_999):06d}"
    address = f"{rng.choice(STREETS)} {rng.randint(1, 120)}, {city}" if with_address else None
    return Person(f"{first} {surname} του {rng.choice(FATHERS)}", fake_afm(rng), id_doc, address)


def random_deed(rng: random.Random) -> DeedSpec:
    city = rng.choice(list(CITIES))
    deed_type = "parental_provision" if rng.random() < 0.3 else "sale"
    ptype = rng.choice(list(PROPERTY_TYPES))
    area = round(rng.uniform(800, 1200) if ptype == "οικόπεδο" else rng.uniform(35, 180), 2)
    sellers = [fake_person(rng, city) for _ in range(1 if deed_type == "parental_provision" else rng.randint(1, 3))]
    buyers = [fake_person(rng, rng.choice(list(CITIES))) for _ in range(rng.randint(1, 2))]
    spec = DeedSpec(
        deed_type=deed_type,
        notary=f"{rng.choice(FEMALE + MALE)} {rng.choice(SURNAMES)[0]}",
        location=city,
        registry_number=f"{rng.randint(1, 40)}.{rng.randint(0, 999):03d}",
        signed=date(rng.randint(2015, 2025), rng.randint(1, 12), rng.randint(1, 28)),
        date_style=rng.choice(["words", "numeric"]),
        sellers=sellers,
        buyers=buyers,
        property_type=ptype,
        property_address=f"{rng.choice(STREETS)} {rng.randint(1, 120)}, {city}",
        municipal_unit=rng.choice(CITIES[city]),
        floor=rng.choice(PROPERTY_TYPES[ptype]),
        area=area,
        kaek="99" + "".join(rng.choice("0123456789") for _ in range(10)) + f"/0/{rng.randint(0, 9)}",
        permit=f"{rng.randint(100, 9999)}/{rng.randint(1975, 2012)} του Πολεοδομικού Γραφείου Δοκιμών",
        price=None if deed_type == "parental_provision" else rng.randrange(40_000, 600_000, 500),
    )
    if rng.random() < 0.4:
        spec.representative = fake_person(rng, city, with_address=False)
        spec.represents = rng.choice(spec.buyers + spec.sellers)
    return spec

# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

CSS = """
* { font-family: sans-serif; }
body { font-size: 10.5pt; line-height: 1.45; text-align: justify; }
h1 { font-size: 14pt; text-align: center; margin-bottom: 2pt; }
.c { text-align: center; }
.banner { text-align: center; font-size: 9pt; color: #b00020; font-weight: bold; }
"""


def greek_amount(value: float, decimals: int = 2) -> str:
    """185000 → 185.000,00"""
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def deed_html(d: DeedSpec) -> str:
    if d.date_style == "words":
        when = f"σήμερα, την {d.signed.day}η {GREEK_MONTHS[d.signed.month - 1]} του έτους {d.signed.year}"
    else:
        when = f"σήμερα, {d.signed:%d.%m.%Y}"

    def party(p: Person) -> str:
        text = f"<b>{p.name}</b>, κάτοικος {p.address}, με Α.Φ.Μ. {p.afm} και αριθμό δελτίου ταυτότητας {p.id_doc}"
        if d.representative and d.represents is p:
            r = d.representative
            text += (
                f", που εκπροσωπείται στο παρόν από τον/την πληρεξούσιο <b>{r.name}</b>, "
                f"με Α.Φ.Μ. {r.afm} και αριθμό δελτίου ταυτότητας {r.id_doc}, δυνάμει του "
                f"υπ' αριθμ. 678/{d.signed.year} πληρεξουσίου του Συμβολαιογράφου Δοκιμών"
            )
        return text + "."

    sale = d.deed_type == "sale"
    title = "ΣΥΜΒΟΛΑΙΟ ΠΩΛΗΣΗΣ ΑΚΙΝΗΤΟΥ" if sale else "ΣΥΜΒΟΛΑΙΟ ΓΟΝΙΚΗΣ ΠΑΡΟΧΗΣ"
    side_a = "ως πωλητές" if sale else "ως παρέχων γονέας"
    side_b = "ως αγοραστές" if sale else "ως αποδέκτες τέκνα"
    n = iter(range(1, 20))
    sellers = "".join(f"<p>{next(n)}) {party(p)}</p>" for p in d.sellers)
    buyers = "".join(f"<p>{next(n)}) {party(p)}</p>" for p in d.buyers)

    floor = f", {d.floor}" if d.floor else ""
    prop = (
        f"<p><b>ΠΡΩΤΟ — ΤΟ ΑΚΙΝΗΤΟ.</b> Ο πρώτος συμβαλλόμενος είναι κύριος ενός ακινήτου "
        f"(<b>{d.property_type}</b>){floor}, εμβαδού {greek_amount(d.area)} τετραγωνικών μέτρων (τ.μ.), "
        f"που βρίσκεται στην {d.property_address}, στη {d.municipal_unit}, και φέρει Κωδικό Αριθμό "
        f"Εθνικού Κτηματολογίου (ΚΑΕΚ) <b>{d.kaek}</b>. Το ακίνητο ανεγέρθηκε ή οριοθετήθηκε νόμιμα "
        f"δυνάμει της υπ' αριθμ. {d.permit} άδειας.</p>"
    )
    if sale:
        deal = (
            "<p><b>ΔΕΥΤΕΡΟ — Η ΠΩΛΗΣΗ.</b> Με το παρόν οι πωλητές πωλούν και μεταβιβάζουν στους "
            "αγοραστές την πλήρη κυριότητα του παραπάνω ακινήτου, ελεύθερου από κάθε βάρος.</p>"
            f"<p><b>ΤΡΙΤΟ — ΤΟ ΤΙΜΗΜΑ.</b> Το συμφωνημένο τίμημα ανέρχεται στο ποσό των "
            f"<b>{greek_amount(d.price)} €</b>, το οποίο οι πωλητές δηλώνουν ότι εισέπραξαν ολόκληρο "
            "μέσω τραπεζικής μεταφοράς πριν από την υπογραφή του παρόντος.</p>"
        )
    else:
        deal = (
            "<p><b>ΔΕΥΤΕΡΟ — Η ΠΑΡΟΧΗ.</b> Με το παρόν ο γονέας παραχωρεί λόγω γονικής παροχής στα "
            "τέκνα του την πλήρη κυριότητα του παραπάνω ακινήτου, χωρίς αντάλλαγμα, για τη "
            "δημιουργία αυτοτελούς οικονομικής ζωής τους.</p>"
        )
    return f"""
<p class="banner">ΔΕΙΓΜΑ — ΠΛΑΣΤΑ ΣΤΟΙΧΕΙΑ / SAMPLE — FICTIONAL DATA</p>
<h1>{title}</h1>
<p class="c">Αριθμός {d.registry_number}</p>
<p>Στην {d.location} {when}, στο γραφείο μου, ενώπιον εμού του/της συμβολαιογράφου
{d.location}, <b>{d.notary}</b>, εμφανίστηκαν οι παρακάτω συμβαλλόμενοι:</p>
<p><b>ΑΠΟ ΤΗ ΜΙΑ ΠΛΕΥΡΑ, {side_a}:</b></p>{sellers}
<p><b>ΑΠΟ ΤΗΝ ΑΛΛΗ ΠΛΕΥΡΑ, {side_b}:</b></p>{buyers}
<p>Οι συμβαλλόμενοι, τους οποίους γνωρίζω προσωπικά, ζήτησαν τη σύνταξη του παρόντος,
με το οποίο συμφώνησαν τα εξής:</p>
{prop}
{deal}
<p><b>ΤΕΛΕΥΤΑΙΟ — ΔΗΛΩΣΕΙΣ.</b> Οι συμβαλλόμενοι δηλώνουν ότι έχουν καταβληθεί όλοι οι
φόροι και τα τέλη που αφορούν το ακίνητο και ότι προσκομίστηκαν όλα τα νόμιμα
δικαιολογητικά, τα οποία προσαρτώνται στο παρόν.</p>
<p>Σε πίστωση των ανωτέρω συντάχθηκε το παρόν, το οποίο αφού αναγνώστηκε καθαρά και
μεγαλόφωνα σε όλους, βεβαιώθηκε και υπογράφεται νόμιμα.</p>
<p class="c" style="margin-top: 24pt">ΟΙ ΣΥΜΒΑΛΛΟΜΕΝΟΙ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
Ο/Η ΣΥΜΒΟΛΑΙΟΓΡΑΦΟΣ</p>
<p class="c">{d.notary}</p>
"""


def add_watermark(page: fitz.Page) -> None:
    text, size = "SAMPLE - FICTIONAL DATA", 46
    width = fitz.get_text_length(text, fontname="helv", fontsize=size)
    centre = fitz.Point(page.rect.width / 2, page.rect.height / 2)
    page.insert_text(
        fitz.Point(centre.x - width / 2, centre.y + size / 3), text,
        fontsize=size, fontname="helv", color=(0.85, 0.85, 0.85),
        morph=(centre, fitz.Matrix(55)), overlay=False,
    )


def render(spec: DeedSpec, pdf_path: Path) -> None:
    """Write the deed PDF (text flows over as many A4 pages as needed) and its truth JSON."""
    for p in [*spec.sellers, *spec.buyers, *([spec.representative] if spec.representative else [])]:
        assert not afm_is_valid(p.afm), f"ΑΦΜ {p.afm} is valid — pick another"

    buffer = io.BytesIO()
    story = fitz.Story(html=deed_html(spec), user_css=CSS)
    writer = fitz.DocumentWriter(buffer)
    mediabox = fitz.paper_rect("a4")
    more = True
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(mediabox + (60, 50, -60, -50))
        story.draw(device)
        writer.end_page()
    writer.close()

    with fitz.open("pdf", buffer.getvalue()) as doc:
        for page in doc:
            add_watermark(page)
        doc.set_metadata({"title": "Sample deed — fictional data", "author": "Generated"})
        doc.save(pdf_path, garbage=4, deflate=True)

    truth = json.dumps(spec.truth(), ensure_ascii=False, indent=2)
    pdf_path.with_suffix(".json").write_text(truth + "\n", encoding="utf-8")
    print(f"Wrote {pdf_path.relative_to(ROOT.parent)} (+ .json)")


def scan(src: Path, dest: Path, rng: random.Random) -> None:
    """Turn a clean PDF into an image-only one that looks like a cheap office scan."""
    pages = []
    with fitz.open(src) as doc:
        for page in doc:
            pix = page.get_pixmap(dpi=130, colorspace=fitz.csGRAY)
            img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            img = img.rotate(rng.uniform(-1.8, 1.8), resample=Image.BICUBIC, expand=True, fillcolor=255)
            img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.4, 0.9)))
            grain = Image.effect_noise(img.size, rng.uniform(10, 22))
            img = Image.blend(img, grain, 0.12)
            img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.75, 1.0))
            img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.92, 1.05))
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=rng.randint(40, 60))
            pages.append((page.rect, buffer.getvalue()))

    with fitz.open() as out:
        for rect, jpeg in pages:
            out.new_page(width=rect.width, height=rect.height).insert_image(rect, stream=jpeg)
        out.save(dest, garbage=4, deflate=True)
    dest.with_suffix(".json").write_text(src.with_suffix(".json").read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Wrote {dest.relative_to(ROOT.parent)} (+ .json)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=int, default=0, help="Also generate N random deeds in samples/dataset/")
    parser.add_argument("--scanned", action="store_true",
                        help="Also write scan-like, image-only copies to samples/dataset_scanned/")
    parser.add_argument("--seed", type=int, default=7, help="Random seed, so the dataset is reproducible")
    args = parser.parse_args()

    render(SAMPLE, ROOT / "sample_deed.pdf")
    if args.dataset:
        out = ROOT / "dataset"
        out.mkdir(exist_ok=True)
        rng = random.Random(args.seed)
        for i in range(1, args.dataset + 1):
            render(random_deed(rng), out / f"deed_{i:02d}.pdf")

        if args.scanned:
            scanned = ROOT / "dataset_scanned"
            scanned.mkdir(exist_ok=True)
            rng = random.Random(args.seed)
            for i in range(1, args.dataset + 1):
                scan(out / f"deed_{i:02d}.pdf", scanned / f"deed_{i:02d}.pdf", rng)


if __name__ == "__main__":
    main()
