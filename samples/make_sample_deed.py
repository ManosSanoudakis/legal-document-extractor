"""
Generate samples/sample_deed.pdf — a FICTIONAL Greek notarial sale deed.

Every name, number and address below is invented. Tax IDs (ΑΦΜ) are chosen
to fail the official check-digit test, so they cannot belong to a real person.

Usage:
    python samples/make_sample_deed.py
"""
from __future__ import annotations

from pathlib import Path

import fitz

OUTPUT = Path(__file__).with_name("sample_deed.pdf")

# ---------------------------------------------------------------------------
# Fictional data
# ---------------------------------------------------------------------------

NOTARY = {
    "name": "Ελένη Παπαδημητρίου-Δοκιμαστή",
    "location": "Αθήνα",
    "registry_number": "12.345",
}
SELLERS = [
    {"name": "Γεώργιος Υποθετικός του Νικολάου", "afm": "123456789",
     "id": "ΑΚ 000101", "address": "Οδός Φανταστικής 12, Αθήνα"},
    {"name": "Μαρία Υποθετική του Ιωάννη", "afm": "987654320",
     "id": "ΑΚ 000102", "address": "Οδός Φανταστικής 12, Αθήνα"},
]
BUYER = {"name": "Δημήτριος Παράδειγμα του Κωνσταντίνου", "afm": "111111110",
         "id": "ΑΜ 000201", "address": "Λεωφόρος Δοκιμών 45, Πειραιάς"}
REPRESENTATIVE = {"name": "Αικατερίνη Δείγμα του Παναγιώτη", "afm": "222222220",
                  "id": "ΑΝ 000301"}
PROPERTY = {
    "address": "Οδός Ανύπαρκτης 7, Αθήνα",
    "municipal_unit": "Δημοτική Ενότητα Ζωγράφου",
    "floor": "2ος όροφος",
    "area": "85,40",
    "kaek": "99 99 01 00 00 00012/0/5",
    "permit": "1234/2005 του Πολεοδομικού Γραφείου Δοκιμών",
}
PRICE_WORDS = "εκατόν ογδόντα πέντε χιλιάδων ευρώ"
PRICE = "185.000,00 €"
DATE_WORDS = "δεκαπέντε (15) Μαρτίου του έτους δύο χιλιάδες είκοσι τέσσερα (2024)"


def afm_is_valid(afm: str) -> bool:
    """Official Greek tax-ID check digit."""
    total = sum(int(d) * 2 ** (8 - i) for i, d in enumerate(afm[:8]))
    return total % 11 % 10 == int(afm[8])


for person in [*SELLERS, BUYER, REPRESENTATIVE]:
    assert not afm_is_valid(person["afm"]), f"ΑΦΜ {person['afm']} is valid — pick another"

# ---------------------------------------------------------------------------
# Deed text
# ---------------------------------------------------------------------------

CSS = """
* { font-family: sans-serif; }
body { font-size: 10.5pt; line-height: 1.45; text-align: justify; }
h1 { font-size: 14pt; text-align: center; margin-bottom: 2pt; }
.c { text-align: center; }
.banner { text-align: center; font-size: 9pt; color: #b00020; font-weight: bold; }
"""

def party(p: dict) -> str:
    return (
        f"<b>{p['name']}</b>, κάτοικος {p['address']}, "
        f"με Α.Φ.Μ. {p['afm']} και αριθμό δελτίου ταυτότητας {p['id']}"
    )


PAGE_1 = f"""
<p class="banner">ΔΕΙΓΜΑ — ΠΛΑΣΤΑ ΣΤΟΙΧΕΙΑ / SAMPLE — FICTIONAL DATA</p>
<h1>ΣΥΜΒΟΛΑΙΟ ΠΩΛΗΣΗΣ ΑΚΙΝΗΤΟΥ</h1>
<p class="c">Αριθμός {NOTARY['registry_number']}</p>
<p>Στην {NOTARY['location']} σήμερα, την {DATE_WORDS}, στο γραφείο μου,
ενώπιον εμού της συμβολαιογράφου {NOTARY['location']},
<b>{NOTARY['name']}</b>, εμφανίστηκαν οι παρακάτω συμβαλλόμενοι:</p>
<p><b>ΑΠΟ ΤΗ ΜΙΑ ΠΛΕΥΡΑ, ως πωλητές:</b></p>
<p>1) {party(SELLERS[0])}.</p>
<p>2) {party(SELLERS[1])}.</p>
<p><b>ΑΠΟ ΤΗΝ ΑΛΛΗ ΠΛΕΥΡΑ, ως αγοραστής:</b></p>
<p>3) {party(BUYER)}, ο οποίος εκπροσωπείται στο παρόν από την πληρεξούσιά του
<b>{REPRESENTATIVE['name']}</b>, με Α.Φ.Μ. {REPRESENTATIVE['afm']} και αριθμό
δελτίου ταυτότητας {REPRESENTATIVE['id']}, δυνάμει του υπ' αριθμ. 678/2024
πληρεξουσίου του Συμβολαιογράφου Δοκιμών.</p>
<p>Οι συμβαλλόμενοι, τους οποίους γνωρίζω προσωπικά, ζήτησαν τη σύνταξη του
παρόντος, με το οποίο συμφώνησαν τα εξής:</p>
<p><b>ΠΡΩΤΟ — ΤΟ ΑΚΙΝΗΤΟ.</b> Οι πωλητές είναι συγκύριοι, κατά ποσοστό 50% ο
καθένας, ενός διαμερίσματος του {PROPERTY['floor']}, εμβαδού
{PROPERTY['area']} τετραγωνικών μέτρων (τ.μ.), που βρίσκεται στην
{PROPERTY['address']}, στη {PROPERTY['municipal_unit']}, και φέρει
Κωδικό Αριθμό Εθνικού Κτηματολογίου (ΚΑΕΚ) <b>{PROPERTY['kaek']}</b>.
Η πολυκατοικία ανεγέρθηκε νόμιμα δυνάμει της υπ' αριθμ. {PROPERTY['permit']}
οικοδομικής άδειας.</p>
"""

PAGE_2 = f"""
<p class="banner">ΔΕΙΓΜΑ — ΠΛΑΣΤΑ ΣΤΟΙΧΕΙΑ / SAMPLE — FICTIONAL DATA</p>
<p><b>ΔΕΥΤΕΡΟ — Η ΠΩΛΗΣΗ.</b> Με το παρόν οι πωλητές πωλούν και μεταβιβάζουν
στον αγοραστή, ο οποίος αγοράζει δια της πληρεξουσίας του, την πλήρη κυριότητα
του παραπάνω ακινήτου, ελεύθερου από κάθε βάρος, υποθήκη ή διεκδίκηση τρίτου.</p>
<p><b>ΤΡΙΤΟ — ΤΟ ΤΙΜΗΜΑ.</b> Το συμφωνημένο τίμημα ανέρχεται στο ποσό των
{PRICE_WORDS} (<b>{PRICE}</b>), το οποίο οι πωλητές δηλώνουν ότι
εισέπραξαν ολόκληρο από τον αγοραστή μέσω τραπεζικής μεταφοράς πριν από την
υπογραφή του παρόντος και παρέχουν σε αυτόν πλήρη και ολοσχερή εξόφληση.</p>
<p><b>ΤΕΤΑΡΤΟ — ΔΗΛΩΣΕΙΣ.</b> Οι πωλητές δηλώνουν ότι το ακίνητο δεν
εμπίπτει σε απαλλοτρίωση, ότι έχουν καταβληθεί όλοι οι φόροι και τα τέλη που
το αφορούν, και ότι προσκομίστηκαν όλα τα νόμιμα δικαιολογητικά, τα οποία
προσαρτώνται στο παρόν.</p>
<p><b>ΠΕΜΠΤΟ — ΠΑΡΑΔΟΣΗ.</b> Η νομή και κατοχή του ακινήτου μεταβιβάζεται
στον αγοραστή από σήμερα, ο οποίος θα το καταχωρίσει στο Κτηματολογικό
Γραφείο με δικά του έξοδα.</p>
<p>Σε πίστωση των ανωτέρω συντάχθηκε το παρόν, το οποίο αφού αναγνώστηκε
καθαρά και μεγαλόφωνα σε όλους, βεβαιώθηκε και υπογράφεται νόμιμα.</p>
<p class="c" style="margin-top: 24pt">ΟΙ ΣΥΜΒΑΛΛΟΜΕΝΟΙ &nbsp;&nbsp;&nbsp;&nbsp;
&nbsp;&nbsp;&nbsp;&nbsp; Η ΣΥΜΒΟΛΑΙΟΓΡΑΦΟΣ</p>
<p class="c">{NOTARY['name']}</p>
"""

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def add_watermark(page: fitz.Page) -> None:
    text, size = "SAMPLE - FICTIONAL DATA", 46
    width = fitz.get_text_length(text, fontname="helv", fontsize=size)
    centre = fitz.Point(page.rect.width / 2, page.rect.height / 2)
    page.insert_text(
        fitz.Point(centre.x - width / 2, centre.y + size / 3), text,
        fontsize=size, fontname="helv", color=(0.85, 0.85, 0.85),
        morph=(centre, fitz.Matrix(55)), overlay=False,
    )


def main() -> None:
    doc = fitz.open()
    for html in (PAGE_1, PAGE_2):
        page = doc.new_page(width=595, height=842)  # A4
        add_watermark(page)
        spare, _ = page.insert_htmlbox(page.rect + (60, 50, -60, -50), html, css=CSS)
        assert spare >= 0, "Text did not fit on the page"
    doc.set_metadata({"title": "Sample deed — fictional data", "author": "Generated"})
    doc.save(OUTPUT, garbage=4, deflate=True)
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
