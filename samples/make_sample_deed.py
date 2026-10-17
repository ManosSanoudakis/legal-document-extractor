"""
Generate FICTIONAL Greek notarial deeds, each with a ground-truth JSON file.

Every name, number and address is invented. Tax IDs (ΑΦΜ) are chosen to fail
the official check-digit test, so they cannot belong to a real person.

The JSON next to each PDF holds the values the extractor should return, which
makes field-level accuracy measurable (see deed_extractor/accuracy.py and benchmark.py).

Long deeds (--long) run to several pages and add the look-alike values real
deeds are full of: previous owners, earlier deeds and their notaries, other
units in the building with their own areas and ΚΑΕΚ, lawyers and engineers
with tax IDs, the assessed value, taxes and fees. The truth JSON has the same
shape; only the real values count, so a model that grabs a look-alike is wrong.

Varied deeds (--varied) are long deeds that also differ in wording and layout:
headings, how parties and dates are written, amounts, section order. Harsh
scans (--harsh) add what real scans have: a notary stamp over the text,
signatures, a handwritten note in the margin, photocopy streaks.

Usage:
    python samples/make_sample_deed.py               # samples/sample_deed.pdf + .json
    python samples/make_sample_deed.py --dataset 10  # also samples/dataset/deed_01..10
    python samples/make_sample_deed.py --dataset 10 --scanned  # + scan-like copies
    python samples/make_sample_deed.py --long 10     # also samples/dataset_long/deed_01..10
    python samples/make_sample_deed.py --varied 10 --harsh  # samples/dataset_varied(_scanned)/
"""
from __future__ import annotations

import argparse
import io
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import fitz
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent))
from deed_extractor.validators import afm_is_valid  # noqa: E402

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
class Unit:
    """Another unit in the same building (a look-alike for the deed's property)."""
    name: str
    floor: str
    area: float
    kaek: str
    owner: str


@dataclass
class Transfer:
    """An earlier transfer of the property, listed in the title history."""
    owner: str
    deed_number: str
    notary: str
    signed: date
    price: str


@dataclass
class Distractors:
    previous_owner: Person
    history: list[Transfer]
    lawyers: list[tuple[Person, str]]   # (lawyer, bar registry number)
    engineer: Person
    neighbours: list[str]
    plot_area: float
    units: list[Unit]
    objective_value: int
    tax_declaration: str
    tax_office: str
    declared: date
    mortgage: int
    certificate: str
    energy_cert: str
    energy_class: str
    building_id: str
    fees: float
    clauses: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    attachments: list[tuple[str, str, date]] = field(default_factory=list)   # (document, number, issued)


@dataclass
class Style:
    """How a deed is worded and laid out. The defaults are the original template."""
    heading: str = "ordinal"       # "ordinal" ΠΡΩΤΟ — Χ. | "article" Άρθρο 1 — Χ. | "number" 1. Χ.
    party: str = "prose"           # "prose" | "fields" (Α.Φ.Μ.: … · Δ.Α.Τ.: …) | "formal" (with birth year, Δ.Ο.Υ.)
    when: str | None = None        # None: as date_style | "weekday" Παρασκευή 15 Μαρτίου 2024 | "slash" 15/3/2024
    amount: str = "symbol"         # "symbol" 185.000,00 € | "words" 185.000 ευρώ | "prefix" ευρώ 185.000,00
    area: str = "words"            # "words" τετραγωνικών μέτρων (τ.μ.) | "short" τ.μ. | "m2" m²
    intro: str = "notary_first"    # "notary_first" | "before_me": ενώπιον εμού (name, συμβολαιογράφου …)
    shuffle_seed: int | None = None  # reorder a long deed's extra sections
    permit: str = "default"        # "default" υπ' αριθμ. … άδειας | "building" άδεια οικοδομής αριθ. … | "plain"


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
    long: Distractors | None = None     # set for long deeds only
    style: Style = field(default_factory=Style)

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
# City → ("in the city", "the city" as an object). Accusative, not genitive ("Αθηνών"),
# so the notary's location reads the same as in the truth JSON.
CITY_FORMS = {
    "Αθήνα": ("στην Αθήνα", "την Αθήνα"),
    "Πειραιάς": ("στον Πειραιά", "τον Πειραιά"),
    "Θεσσαλονίκη": ("στη Θεσσαλονίκη", "τη Θεσσαλονίκη"),
    "Πάτρα": ("στην Πάτρα", "την Πάτρα"),
    "Ηράκλειο": ("στο Ηράκλειο", "το Ηράκλειο"),
}
PROPERTY_TYPES = {  # type → possible floors (None = no floor, e.g. a plot)
    "διαμέρισμα": ["1ος όροφος", "2ος όροφος", "3ος όροφος", "4ος όροφος"],
    "κατάστημα": ["ισόγειο"],
    "μονοκατοικία": [None],
    "οικόπεδο": [None],
}


def gendered(name: str, male: str, female: str) -> str:
    """Pick the form that agrees with a person, judged by their first name."""
    return female if name.split()[0] in FEMALE else male


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
    first = rng.choice(FEMALE + MALE)
    notary = f"{first} {rng.choice(SURNAMES)[first in FEMALE]}"
    spec = DeedSpec(
        deed_type=deed_type,
        notary=notary,
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
# Long deeds: same truth, many look-alike values
# ---------------------------------------------------------------------------

TAX_OFFICES = ["Α' Αθηνών", "Ψυχικού", "Α' Πειραιά", "Δ' Θεσσαλονίκης", "Πατρών", "Α' Ηρακλείου"]
UNIT_FLOORS = ["ισογείου", "1ου ορόφου", "2ου ορόφου", "3ου ορόφου", "4ου ορόφου", "5ου ορόφου"]

# Generic standard declarations of the kind real deeds carry. Each long deed uses a random subset.
CLAUSES = [
    "Ο μεταβιβάζων δηλώνει υπεύθυνα, κατ' εφαρμογή των διατάξεων της κείμενης πολεοδομικής νομοθεσίας, "
    "ότι στο μεταβιβαζόμενο ακίνητο δεν υφίστανται αυθαίρετες κατασκευές ή αυθαίρετες αλλαγές χρήσης, "
    "ότι δεν έχει υπαχθεί σε καμία ρύθμιση νομιμοποίησης και ότι το ακίνητο είναι σύμφωνο με την "
    "οικοδομική άδεια και τα εγκεκριμένα σχέδια. Προσαρτάται στο παρόν σχετική βεβαίωση μηχανικού, "
    "ο οποίος βεβαιώνει ότι διενήργησε αυτοψία και ότι η βεβαίωση εκδόθηκε μετά από επιτόπιο έλεγχο.",
    "Οι συμβαλλόμενοι δηλώνουν ότι το ακίνητο δεν βρίσκεται σε δασική ή αναδασωτέα περιοχή, σε "
    "αρχαιολογικό χώρο ή σε ζώνη αιγιαλού και παραλίας, και ότι δεν απαιτείται καμία ειδική άδεια "
    "ή έγκριση δημόσιας αρχής για τη μεταβίβασή του. Δηλώνουν επίσης ότι έλαβαν γνώση των διατάξεων "
    "για τις παραμεθόριες περιοχές και ότι αυτές δεν εφαρμόζονται στο παρόν.",
    "Ο αποκτών δηλώνει ότι επισκέφθηκε το ακίνητο, το εξέτασε προσεκτικά μαζί με τεχνικό σύμβουλο "
    "της επιλογής του και το βρήκε της απολύτου αρεσκείας του, κατάλληλο για τη χρήση για την οποία "
    "το προορίζει, και παραιτείται από κάθε δικαίωμα να ζητήσει μείωση του τιμήματος ή υπαναχώρηση "
    "για πραγματικά ελαττώματα, εκτός αν αυτά αποκρύφθηκαν δολίως.",
    "Η νομή και κατοχή του ακινήτου, μαζί με όλα τα δικαιώματα, τις αγωγές και τις ενστάσεις που "
    "απορρέουν από την κυριότητα, μεταβιβάζονται στον αποκτώντα από σήμερα. Από την ίδια ημέρα όλα τα "
    "τέλη, οι φόροι, οι κοινόχρηστες δαπάνες και οι λογαριασμοί κοινής ωφέλειας βαρύνουν τον αποκτώντα, "
    "ενώ οι οφειλές μέχρι σήμερα βαρύνουν τον μεταβιβάζοντα, ο οποίος δηλώνει ότι τις έχει εξοφλήσει.",
    "Ο μεταβιβάζων ευθύνεται για την ύπαρξη του δικαιώματος κυριότητας και για την έλλειψη νομικών "
    "ελαττωμάτων, και υποχρεούται σε αποζημίωση του αποκτώντος σε περίπτωση αποβολής του από τρίτο "
    "που θα προβάλει δικαίωμα επί του ακινήτου, σύμφωνα με τις διατάξεις του Αστικού Κώδικα.",
    "Οι συμβαλλόμενοι δηλώνουν ότι έλαβαν γνώση του κανονισμού της οικοδομής και των όρων "
    "δόμησης της περιοχής, τους αποδέχονται ανεπιφύλακτα και ότι ο αποκτών υπεισέρχεται σε όλα "
    "τα δικαιώματα και τις υποχρεώσεις του μεταβιβάζοντος που απορρέουν από αυτούς.",
    "Δηλώνεται ότι για το ακίνητο έχει υποβληθεί δήλωση στο Εθνικό Κτηματολόγιο, ότι τα στοιχεία "
    "του κτηματολογικού φύλλου συμφωνούν με την περιγραφή του παρόντος, και ότι ο/η συμβολαιογράφος "
    "θα μεριμνήσει για την καταχώριση της παρούσας πράξης στο αρμόδιο Κτηματολογικό Γραφείο.",
    "Οι συμβαλλόμενοι δηλώνουν ότι δεν εκκρεμεί καμία δίκη, διεκδίκηση, αναγκαστική εκτέλεση ή "
    "κατάσχεση για το ακίνητο και ότι δεν έχουν ασκηθεί αγωγές που να αφορούν την κυριότητα, τη "
    "νομή ή τα όριά του, ούτε έχει εγγραφεί προσημείωση ή άλλο εμπράγματο βάρος.",
    "Ο/Η συμβολαιογράφος βεβαιώνει ότι έλεγξε την ταυτότητα των συμβαλλομένων με βάση τα νόμιμα "
    "έγγραφα που επέδειξαν, ότι αυτοί έχουν πλήρη δικαιοπρακτική ικανότητα και ότι τους ενημέρωσε "
    "για τις φορολογικές και αστικές συνέπειες της πράξης, για τις οποίες δήλωσαν ότι έλαβαν γνώση.",
    "Οι συμβαλλόμενοι συναινούν στην επεξεργασία των προσωπικών τους δεδομένων από τον/την "
    "συμβολαιογράφο για τους σκοπούς της κατάρτισης, της καταχώρισης και της φύλαξης της παρούσας "
    "πράξης, και για την υποβολή των νόμιμων δηλώσεων στις αρμόδιες φορολογικές αρχές.",
    "Ο μεταβιβάζων δηλώνει ότι το ακίνητο δεν έχει μισθωθεί σε τρίτους, ότι δεν υφίσταται δικαίωμα "
    "προτίμησης ή προαίρεσης υπέρ οποιουδήποτε, και ότι δεν έχει συνάψει άλλη σύμβαση, προσύμφωνο ή "
    "υπόσχεση μεταβίβασης για το ίδιο ακίνητο.",
    "Όλα τα έξοδα του παρόντος, δηλαδή τα δικαιώματα του/της συμβολαιογράφου, τα τέλη καταχώρισης στο "
    "Κτηματολόγιο, οι αμοιβές των δικηγόρων και ο αναλογών φόρος, βαρύνουν τον αποκτώντα, εκτός αν "
    "ορίζεται διαφορετικά ρητά στο παρόν.",
]


# Generic extracts from a building's regulations (κανονισμός οικοδομής), for apartments and shops
RULES = [
    "Κοινόχρηστα και κοινόκτητα μέρη της οικοδομής είναι το οικόπεδο, τα θεμέλια, οι κύριοι τοίχοι, "
    "η είσοδος, το κλιμακοστάσιο, ο ανελκυστήρας, το δώμα, το λεβητοστάσιο και κάθε χώρος ή εγκατάσταση "
    "που εξυπηρετεί όλους τους ιδιοκτήτες, και ανήκουν σε αυτούς κατά το ποσοστό συνιδιοκτησίας τους.",
    "Οι κοινόχρηστες δαπάνες κατανέμονται μεταξύ των ιδιοκτητών σύμφωνα με τον πίνακα κατανομής "
    "δαπανών που προσαρτάται στον κανονισμό, ενώ οι δαπάνες θέρμανσης κατανέμονται με βάση τις "
    "ενδείξεις των θερμιδομετρητών κάθε ιδιοκτησίας.",
    "Απαγορεύεται η χρήση οποιασδήποτε ιδιοκτησίας για σκοπούς που προκαλούν θόρυβο, οσμές ή "
    "ενόχληση στους λοιπούς ιδιοκτήτες, καθώς και η τοποθέτηση επιγραφών ή κλιματιστικών μηχανημάτων "
    "στις όψεις της οικοδομής χωρίς απόφαση της γενικής συνέλευσης.",
    "Η γενική συνέλευση των ιδιοκτητών συνέρχεται τακτικά μία φορά τον χρόνο και έκτακτα όποτε τη "
    "συγκαλέσει ο διαχειριστής ή ιδιοκτήτες που εκπροσωπούν τουλάχιστον το ένα πέμπτο των ψήφων, "
    "και αποφασίζει με απλή πλειοψηφία, εκτός αν ο κανονισμός ορίζει διαφορετικά.",
    "Κάθε ιδιοκτήτης υποχρεούται να επιτρέπει την είσοδο στην ιδιοκτησία του για την εκτέλεση "
    "επισκευών σε κοινόχρηστες εγκαταστάσεις, με την επιφύλαξη αποκατάστασης κάθε ζημίας που θα "
    "προκληθεί, και να διατηρεί την ιδιοκτησία του σε καλή κατάσταση.",
    "Ο διαχειριστής εκλέγεται από τη γενική συνέλευση για θητεία ενός έτους, εκπροσωπεί τους "
    "ιδιοκτήτες δικαστικά και εξώδικα για κάθε θέμα που αφορά τα κοινόχρηστα, εισπράττει τις "
    "κοινόχρηστες δαπάνες και τηρεί βιβλίο εσόδων και εξόδων.",
]

ATTACHMENTS = [
    "Πιστοποιητικό κτηματολογικής εγγραφής", "Απόσπασμα κτηματολογικού διαγράμματος",
    "Βεβαίωση μηχανικού για τη μη ύπαρξη αυθαιρέτων", "Αποδεικτικό ενημερότητας για ΕΝΦΙΑ",
    "Βεβαίωση του Δήμου για τη μη οφειλή ΤΑΠ", "Δήλωση φόρου και αποδεικτικό καταβολής",
    "Αντίγραφο οικοδομικής άδειας", "Κάτοψη ορόφου θεωρημένη από μηχανικό",
    "Πιστοποιητικό ενεργειακής απόδοσης", "Ηλεκτρονική Ταυτότητα Κτιρίου",
    "Πιστοποιητικό βαρών", "Πιστοποιητικό μη διεκδίκησης",
]


def earlier(rng: random.Random, before: date, min_days: int, max_days: int) -> date:
    return before - timedelta(days=rng.randint(min_days, max_days))


def other_person(rng: random.Random, city: str, taken: set[str]) -> Person:
    """A fictional person whose name is not already used in the deed."""
    while True:
        p = fake_person(rng, city)
        if p.name not in taken:
            taken.add(p.name)
            return p


def add_distractors(spec: DeedSpec, rng: random.Random) -> DeedSpec:
    """Make a deed long and full of values that look like the real ones but are not."""
    real = [*spec.sellers, *spec.buyers, *([spec.representative] if spec.representative else [])]
    taken = {p.name for p in real}
    city = spec.location
    previous = other_person(rng, city, taken)

    # Title history, oldest first; the last owner is the one the sellers acquired from
    years = sorted(rng.sample(range(1978, spec.signed.year), rng.randint(3, 7)))
    owners = [other_person(rng, city, taken).name for _ in years[:-1]] + [previous.name]
    history = []
    for year, owner in zip(years, owners, strict=True):
        if year < 2002:
            price = f"{greek_amount(rng.randrange(2_000_000, 40_000_000, 50_000), 0)} δραχμών"
        else:
            price = f"{greek_amount(rng.randrange(20_000, 400_000, 500))} €"
        history.append(Transfer(
            owner=owner,
            deed_number=f"{rng.randint(1, 30)}.{rng.randint(0, 999):03d}/{year}",
            notary=other_person(rng, city, taken).name.split(" του ")[0],
            signed=date(year, rng.randint(1, 12), rng.randint(1, 28)),
            price=price,
        ))

    # Other units in the building share the ΚΑΕΚ base and differ only in the last part
    base, _, suffix = spec.kaek.rpartition("/")
    units = []
    if spec.property_type in ("διαμέρισμα", "κατάστημα"):
        suffixes = [n for n in range(1, 25) if str(n) != suffix]
        for i, n in enumerate(rng.sample(suffixes, rng.randint(6, 14))):
            floor = rng.choice(UNIT_FLOORS)
            kind = "κατάστημα" if floor == "ισογείου" else "διαμέρισμα"
            units.append(Unit(
                name=f"{kind} {chr(0x391 + i)}{rng.randint(1, 4)}",
                floor=floor,
                area=round(rng.uniform(35, 160), 2),
                kaek=f"{base}/{n}",
                owner=other_person(rng, city, taken).name,
            ))

    # The assessed value is always close to, but never equal to, the price
    objective = round((spec.price or rng.randrange(40_000, 600_000, 500)) * rng.uniform(0.55, 0.95), -2)
    spec.long = Distractors(
        previous_owner=previous,
        history=history,
        lawyers=[(other_person(rng, city, taken), str(rng.randint(1000, 39999))) for _ in range(rng.randint(1, 2))],
        engineer=other_person(rng, city, taken),
        neighbours=[other_person(rng, city, taken).name for _ in range(rng.randint(2, 4))],
        plot_area=round(rng.uniform(250, 900), 2),
        units=units,
        objective_value=int(objective),
        tax_declaration=f"{rng.randint(100_000, 999_999)}/{spec.signed.year}",
        tax_office=rng.choice(TAX_OFFICES),
        declared=earlier(rng, spec.signed, 2, 20),
        mortgage=rng.randrange(20_000, 250_000, 1_000),
        certificate=f"{rng.randint(1000, 99999)}/{spec.signed.year}",
        energy_cert=f"{rng.randint(100_000, 999_999)}/{spec.signed.year - rng.randint(0, 3)}",
        energy_class=rng.choice(["Β+", "Β", "Γ", "Δ", "Ε", "Ζ"]),
        building_id=f"{rng.randint(1000, 9999)}{rng.randint(100000, 999999)}",
        fees=round(spec.price * 0.008 if spec.price else rng.uniform(600, 2500), 2),
        clauses=rng.sample(CLAUSES, rng.randint(8, len(CLAUSES))),
        rules=rng.sample(RULES, rng.randint(4, len(RULES))) if units else [],
        attachments=[
            (doc, f"{rng.randint(100, 99999)}/{spec.signed.year}", earlier(rng, spec.signed, 1, 60))
            for doc in rng.sample(ATTACHMENTS, rng.randint(8, len(ATTACHMENTS)))
        ],
    )
    return spec


GREEK_WEEKDAYS = ["Δευτέρα", "Τρίτη", "Τετάρτη", "Πέμπτη", "Παρασκευή", "Σάββατο", "Κυριακή"]


def vary(spec: DeedSpec, rng: random.Random) -> DeedSpec:
    """Pick a random wording and layout, so a model cannot lean on one template."""
    spec.style = Style(
        heading=rng.choice(["ordinal", "article", "number"]),
        party=rng.choice(["prose", "fields", "formal"]),
        when=rng.choice([None, "weekday", "slash"]),
        amount=rng.choice(["symbol", "words", "prefix"]),
        area=rng.choice(["words", "short", "m2"]),
        intro=rng.choice(["notary_first", "before_me"]),
        shuffle_seed=rng.randrange(1_000_000),
    )
    return spec


PERMIT_OFFICES = [
    "του Πολεοδομικού Γραφείου Δοκιμών",
    "της Υπηρεσίας Δόμησης Δήμου Δοκιμών",
    "της Διεύθυνσης Πολεοδομίας Νομαρχίας Δοκιμών",
]


def reword_permit(spec: DeedSpec, rng: random.Random) -> DeedSpec:
    """Word the permit and name its issuing office differently from every other set (the held-out set)."""
    number = spec.permit.split()[0]
    spec.permit = f"{number} {rng.choice(PERMIT_OFFICES)}"
    spec.style.permit = rng.choice(["default", "building", "plain"])
    return spec


def fmt_date(d: date, genitive: bool = False) -> str:
    """15η Μαρτίου 2024, or 15ης Μαρτίου 2024 after a genitive ("της ...")."""
    return f"{d.day}{'ης' if genitive else 'η'} {GREEK_MONTHS[d.month - 1]} {d.year}"


def long_sections(d: DeedSpec) -> dict:
    """HTML for the extra parts of a long deed, keyed by where they go.

    Names are always set off ("ιδιοκτήτης: Νικόλαος ...") so they can stay in the
    nominative, the form the truth JSON and the extractor use.
    """
    x = d.long
    lawyers = " · ".join(
        f"<b>{p.name}</b>, δικηγόρος, με Α.Μ. Δικηγορικού Συλλόγου {am} και Α.Φ.Μ. {p.afm}"
        for p, am in x.lawyers
    )
    parties = (
        "<p>Στην κατάρτιση του παρόντος παρίστανται, σύμφωνα με τον νόμο, οι πληρεξούσιοι "
        f"δικηγόροι των συμβαλλομένων: {lawyers}, οι οποίοι προσκόμισαν τα νόμιμα γραμμάτια "
        "προείσπραξης αμοιβής.</p>"
    )

    street = d.property_address.split(",")[0].split(" ", 1)[1].rsplit(" ", 1)[0]  # "Οδός Ανύπαρκτης 7" → "Ανύπαρκτης"
    road = "τη λεωφόρο" if d.property_address.startswith("Λεωφόρος") else "την οδό"
    others = ", ".join(x.neighbours[1:]) or x.neighbours[0]
    bounds = (
        f"συνορεύει βόρεια με ιδιοκτησία τρίτου ({gendered(x.neighbours[0], 'ιδιοκτήτης', 'ιδιοκτήτρια')}: "
        f"{x.neighbours[0]}), νότια με {road} "
        f"{street} και ανατολικά και δυτικά με ιδιοκτησίες τρίτων (ιδιοκτήτες: {others})"
    )
    if d.property_type == "οικόπεδο":
        building = f"<p>Το οικόπεδο {bounds}.</p>"
    else:
        building = (
            f"<p>Το ακίνητο βρίσκεται σε οικόπεδο συνολικού εμβαδού {greek_amount(x.plot_area)} τ.μ., "
            f"το οποίο {bounds}.</p>"
        )
    if x.units:
        rows = "".join(
            f"<p>— {u.name} του {u.floor}, εμβαδού {greek_amount(u.area)} τ.μ., με ΚΑΕΚ {u.kaek} "
            f"({gendered(u.owner, 'ιδιοκτήτης', 'ιδιοκτήτρια')}: {u.owner}).</p>"
            for u in x.units
        )
        building += (
            "<p>Με την πράξη σύστασης οριζόντιας ιδιοκτησίας και τον κανονισμό της οικοδομής, "
            "η οικοδομή διαιρέθηκε, πέρα από το ακίνητο του παρόντος, και στις εξής αυτοτελείς "
            f"ιδιοκτησίες, οι οποίες δεν αποτελούν αντικείμενο του παρόντος:</p>{rows}"
        )
    rules = "".join(f"<p>{r}</p>" for r in x.rules)
    if rules:
        rules = "<p>Από τον κανονισμό της οικοδομής, ο οποίος δεσμεύει και τον αποκτώντα, παρατίθενται:</p>" + rules

    titles = "".join(
        f"<p>Με το υπ' αριθμ. {t.deed_number} συμβόλαιο (συμβολαιογράφος: {t.notary}), που "
        f"συντάχθηκε την {fmt_date(t.signed)}, το ακίνητο μεταβιβάστηκε αντί τιμήματος {t.price}. "
        f"{gendered(t.owner, 'Νέος κύριος έγινε ο', 'Νέα κυρία έγινε η')} {t.owner}, και το συμβόλαιο "
        "μεταγράφηκε νόμιμα στα βιβλία μεταγραφών του αρμόδιου Υποθηκοφυλακείου.</p>"
        for t in x.history
    )
    p = x.previous_owner
    titles += (
        f"<p>{gendered(p.name, 'Ο τελευταίος κύριος', 'Η τελευταία κυρία')}, <b>{p.name}</b>, "
        f"κάτοικος {p.address}, με Α.Φ.Μ. {p.afm}, μεταβίβασε το ακίνητο "
        + ("στον μεταβιβάζοντα του παρόντος, ο οποίος έκτοτε το νέμεται" if len(d.sellers) == 1
           else "στους μεταβιβάζοντες του παρόντος, οι οποίοι έκτοτε το νέμονται")
        + " συνεχώς, δημόσια και αδιατάρακτα.</p>"
    )
    encumbrances = (
        f"<p>Σύμφωνα με το υπ' αριθμ. {x.certificate} πιστοποιητικό του αρμόδιου Κτηματολογικού "
        f"Γραφείου, το ακίνητο βαρυνόταν με υποθήκη ποσού {greek_amount(x.mortgage)} € υπέρ της "
        "Τράπεζας Δοκιμών Α.Ε., η οποία έχει εξαλειφθεί πλήρως, και σήμερα είναι ελεύθερο από κάθε "
        "βάρος, κατάσχεση, διεκδίκηση ή δουλεία.</p>"
    )

    tax = "μεταβίβασης" if d.deed_type == "sale" else "γονικής παροχής"
    taxes = (
        "<p>Η αντικειμενική αξία του ακινήτου, όπως υπολογίστηκε με το σύστημα αντικειμενικού "
        f"προσδιορισμού, ανέρχεται σε {greek_amount(x.objective_value)} €. Για την παρούσα υποβλήθηκε "
        f"η υπ' αριθμ. {x.tax_declaration} δήλωση φόρου {tax} στη Δ.Ο.Υ. {x.tax_office} την "
        f"{fmt_date(x.declared)}, και ο φόρος καταβλήθηκε εμπρόθεσμα, όπως αποδεικνύεται από το "
        "προσαρτώμενο αποδεικτικό πληρωμής.</p>"
    )
    e = x.engineer
    certificates = (
        "<p>Προσαρτώνται στο παρόν: (α) πιστοποιητικό ενεργειακής απόδοσης με αριθμό "
        f"{x.energy_cert}, κατηγορίας {x.energy_class} "
        f"({gendered(e.name, 'ενεργειακός επιθεωρητής', 'ενεργειακή επιθεωρήτρια')}: <b>{e.name}</b>, "
        f"με Α.Φ.Μ. {e.afm})· (β) Ηλεκτρονική Ταυτότητα Κτιρίου με αριθμό {x.building_id}, "
        f"συνταγμένη από {gendered(e.name, 'τον ίδιο', 'την ίδια')} μηχανικό· (γ) βεβαίωση της αρμόδιας "
        "Δ.Ο.Υ. για την καταβολή του φόρου ακίνητης περιουσίας των τελευταίων πέντε ετών· (δ) "
        "βεβαίωση του Δήμου για τη μη οφειλή τέλους ακίνητης περιουσίας.</p>"
    )
    fees = (
        f"<p>Τα δικαιώματα του/της συμβολαιογράφου για το παρόν ανέρχονται σε {greek_amount(x.fees)} € "
        "πλέον Φ.Π.Α., και τα τέλη καταχώρισης θα καταβληθούν κατά την υποβολή της αίτησης "
        "καταχώρισης στο Κτηματολογικό Γραφείο.</p>"
    )
    return {
        "parties": parties,
        "after_property": [
            ("ΤΑ ΟΡΙΑ" if d.property_type == "οικόπεδο" else "Η ΟΙΚΟΔΟΜΗ ΚΑΙ ΤΟ ΟΙΚΟΠΕΔΟ", building),
            ("ΤΙΤΛΟΙ ΚΤΗΣΗΣ", titles),
            ("ΒΑΡΗ", encumbrances),
            *([("Ο ΚΑΝΟΝΙΣΜΟΣ ΤΗΣ ΟΙΚΟΔΟΜΗΣ", rules)] if rules else []),
        ],
        "after_deal": [
            ("ΦΟΡΟΛΟΓΙΚΑ", taxes),
            ("ΠΙΣΤΟΠΟΙΗΤΙΚΑ", certificates),
            ("ΔΗΛΩΣΕΙΣ ΤΩΝ ΣΥΜΒΑΛΛΟΜΕΝΩΝ", "".join(f"<p>{c}</p>" for c in x.clauses)),
            ("ΕΞΟΔΑ", fees),
            ("ΠΡΟΣΑΡΤΩΜΕΝΑ ΕΓΓΡΑΦΑ", "<p>Στο παρόν προσαρτώνται τα εξής έγγραφα:</p>" + "".join(
                f"<p>{i}. {doc}, με αριθμό {number}, της {fmt_date(issued, genitive=True)}.</p>"
                for i, (doc, number, issued) in enumerate(x.attachments, start=1)
            )),
        ],
    }


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
# Real deeds are typed larger and more widely spaced
LONG_CSS = CSS + "body { font-size: 12pt; line-height: 1.75; }"


ORDINALS = [
    "ΠΡΩΤΟ", "ΔΕΥΤΕΡΟ", "ΤΡΙΤΟ", "ΤΕΤΑΡΤΟ", "ΠΕΜΠΤΟ", "ΕΚΤΟ", "ΕΒΔΟΜΟ", "ΟΓΔΟΟ", "ΕΝΑΤΟ", "ΔΕΚΑΤΟ",
    "ΕΝΔΕΚΑΤΟ", "ΔΩΔΕΚΑΤΟ",
]


def greek_amount(value: float, decimals: int = 2) -> str:
    """185000 → 185.000,00"""
    return f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def deed_html(d: DeedSpec) -> str:
    st = d.style
    month = GREEK_MONTHS[d.signed.month - 1]
    if st.when == "weekday":
        when = f"σήμερα, {GREEK_WEEKDAYS[d.signed.weekday()]} {d.signed.day} {month} {d.signed.year}"
    elif st.when == "slash":
        when = f"σήμερα, {d.signed.day}/{d.signed.month}/{d.signed.year}"
    elif d.date_style == "words":
        when = f"σήμερα, την {d.signed.day}η {month} του έτους {d.signed.year}"
    else:
        when = f"σήμερα, {d.signed:%d.%m.%Y}"

    def party(p: Person) -> str:
        if st.party == "fields":
            text = f"<b>{p.name}</b> — κάτοικος: {p.address} · Α.Φ.Μ.: {p.afm} · Δ.Α.Τ.: {p.id_doc}"
        elif st.party == "formal":
            # Birth year and tax office follow from the tax ID, so they need no extra randomness
            born, office = 1940 + int(p.afm[:2]) % 60, TAX_OFFICES[int(p.afm[-1]) % len(TAX_OFFICES)]
            text = (
                f"<b>{p.name}</b>, που γεννήθηκε το {born}, κάτοικος {p.address}, κάτοχος του υπ' αριθμ. "
                f"{p.id_doc} δελτίου αστυνομικής ταυτότητας, με Α.Φ.Μ. {p.afm} (Δ.Ο.Υ. {office})"
            )
        else:
            text = f"<b>{p.name}</b>, κάτοικος {p.address}, με Α.Φ.Μ. {p.afm} και αριθμό δελτίου ταυτότητας {p.id_doc}"
        if d.representative and d.represents is p:
            r = d.representative
            if st.party == "fields":
                text += (
                    f" · εκπροσωπείται από πληρεξούσιο: <b>{r.name}</b> (Α.Φ.Μ.: {r.afm}, Δ.Α.Τ.: {r.id_doc}), "
                    f"δυνάμει του υπ' αριθμ. 678/{d.signed.year} πληρεξουσίου του Συμβολαιογράφου Δοκιμών"
                )
            else:
                text += (
                    f", που εκπροσωπείται στο παρόν από πληρεξούσιο: <b>{r.name}</b>, "
                    f"με Α.Φ.Μ. {r.afm} και αριθμό δελτίου ταυτότητας {r.id_doc}, δυνάμει του "
                    f"υπ' αριθμ. 678/{d.signed.year} πληρεξουσίου του Συμβολαιογράφου Δοκιμών"
                )
        return text + "."

    def word(people: list[Person], male: str, female: str, plural: str) -> str:
        """Pick the form that agrees with the people: one man, one woman, or several."""
        return plural if len(people) > 1 else gendered(people[0].name, male, female)

    sale = d.deed_type == "sale"
    title = "ΣΥΜΒΟΛΑΙΟ ΠΩΛΗΣΗΣ ΑΚΙΝΗΤΟΥ" if sale else "ΣΥΜΒΟΛΑΙΟ ΓΟΝΙΚΗΣ ΠΑΡΟΧΗΣ"
    if sale:
        side_a = word(d.sellers, "ως πωλητής", "ως πωλήτρια", "ως πωλητές")
        side_b = word(d.buyers, "ως αγοραστής", "ως αγοράστρια", "ως αγοραστές")
        owner = word(d.sellers, "Ο πωλητής είναι κύριος", "Η πωλήτρια είναι κυρία", "Οι πωλητές είναι συγκύριοι")
    else:
        side_a = word(d.sellers, "ως παρέχων γονέας", "ως παρέχουσα γονέας", "ως παρέχοντες γονείς")
        side_b = word(d.buyers, "ως τέκνο που αποδέχεται", "ως τέκνο που αποδέχεται", "ως τέκνα που αποδέχονται")
        owner = word(d.sellers, "Ο γονέας είναι κύριος", "Η γονέας είναι κυρία", "Οι γονείς είναι συγκύριοι")
    n = iter(range(1, 20))
    sellers = "".join(f"<p>{next(n)}) {party(p)}</p>" for p in d.sellers)
    buyers = "".join(f"<p>{next(n)}) {party(p)}</p>" for p in d.buyers)

    extra = long_sections(d) if d.long else {"parties": "", "after_property": [], "after_deal": []}
    if st.shuffle_seed is not None and d.long:
        # Same sections, another order; some may now come between the property and the deal
        pool = extra["after_property"] + extra["after_deal"]
        order = random.Random(st.shuffle_seed)
        order.shuffle(pool)
        cut = order.randint(0, len(pool))
        extra = {**extra, "after_property": pool[:cut], "after_deal": pool[cut:]}
    numbers = iter(range(1, 100))

    def heading(title: str) -> str:
        n = next(numbers)
        if st.heading == "article":
            return f"<b>Άρθρο {n} — {title}.</b>"
        if st.heading == "number":
            return f"<b>{n}. {title}.</b>"
        return f"<b>{ORDINALS[n - 1]} — {title}.</b>"

    def sections(items: list[tuple[str, str]]) -> str:
        # The heading goes inside the first paragraph, like the short deed's sections
        return "".join(html.replace("<p>", f"<p>{heading(title)} ", 1) for title, html in items)

    area = {
        "short": f"εμβαδού {greek_amount(d.area)} τ.μ.",
        "m2": f"επιφάνειας {greek_amount(d.area)} m²",
    }.get(st.area, f"εμβαδού {greek_amount(d.area)} τετραγωνικών μέτρων (τ.μ.)")
    floor = f", {d.floor}" if d.floor else ""
    prop = (
        f"<p>{heading('ΤΟ ΑΚΙΝΗΤΟ')} {owner} ενός ακινήτου "
        f"(<b>{d.property_type}</b>){floor}, {area}, "
        f"που βρίσκεται στη διεύθυνση {d.property_address}, στη {d.municipal_unit}, και φέρει Κωδικό Αριθμό "
        f"Εθνικού Κτηματολογίου (ΚΑΕΚ) <b>{d.kaek}</b>. Το ακίνητο ανεγέρθηκε ή οριοθετήθηκε νόμιμα "
        + {
            "building": f"σύμφωνα με την άδεια οικοδομής αριθ. {d.permit}.</p>",
            "plain": f"με βάση την οικοδομική άδεια {d.permit}.</p>",
        }.get(st.permit, f"δυνάμει της υπ' αριθμ. {d.permit} άδειας.</p>")
    ) + sections(extra["after_property"])
    if sale:
        amount = {
            "words": f"{greek_amount(d.price, 0)} ευρώ",
            "prefix": f"ευρώ {greek_amount(d.price)}",
        }.get(st.amount, f"{greek_amount(d.price)} €")
        deal = (
            f"<p>{heading('Η ΠΩΛΗΣΗ')} Με το παρόν "
            + word(d.sellers, "ο πωλητής πωλεί και μεταβιβάζει", "η πωλήτρια πωλεί και μεταβιβάζει",
                   "οι πωλητές πωλούν και μεταβιβάζουν")
            + " " + word(d.buyers, "στον αγοραστή", "στην αγοράστρια", "στους αγοραστές")
            + " την πλήρη κυριότητα του παραπάνω ακινήτου, ελεύθερου από κάθε βάρος.</p>"
            f"<p>{heading('ΤΟ ΤΙΜΗΜΑ')} Το συμφωνημένο τίμημα ανέρχεται στο ποσό των "
            f"<b>{amount}</b>, το οποίο "
            + word(d.sellers, "ο πωλητής δηλώνει ότι εισέπραξε", "η πωλήτρια δηλώνει ότι εισέπραξε",
                   "οι πωλητές δηλώνουν ότι εισέπραξαν")
            + " ολόκληρο μέσω τραπεζικής μεταφοράς πριν από την υπογραφή του παρόντος.</p>"
        )
    else:
        deal = (
            f"<p>{heading('Η ΠΑΡΟΧΗ')} Με το παρόν "
            + word(d.sellers, "ο γονέας παραχωρεί", "η γονέας παραχωρεί", "οι γονείς παραχωρούν")
            + " λόγω γονικής παροχής "
            + word(d.buyers, "στο τέκνο", "στο τέκνο", "στα τέκνα")
            + " " + word(d.sellers, "του", "της", "τους")
            + " την πλήρη κυριότητα του παραπάνω ακινήτου, χωρίς αντάλλαγμα, για τη "
            "δημιουργία αυτοτελούς οικονομικής ζωής.</p>"
        )
    deal += sections(extra["after_deal"])
    in_city, seat = CITY_FORMS[d.location]
    if st.intro == "before_me":
        intro = (
            f"<p>{in_city[0].upper() + in_city[1:]} {when}, ενώπιον εμού (<b>{d.notary}</b>, συμβολαιογράφου "
            f"με έδρα {seat}) εμφανίστηκαν οι παρακάτω συμβαλλόμενοι:</p>"
        )
    else:
        intro = f"""<p>{in_city[0].upper() + in_city[1:]} {when}, στο γραφείο μου, εγώ,
{gendered(d.notary, "ο", "η")} συμβολαιογράφος με έδρα {seat}, <b>{d.notary}</b>, βεβαιώνω ότι
εμφανίστηκαν ενώπιόν μου οι παρακάτω συμβαλλόμενοι:</p>"""
    closing = "<b>ΤΕΛΕΥΤΑΙΟ — ΔΗΛΩΣΕΙΣ.</b>" if st.heading == "ordinal" else heading("ΔΗΛΩΣΕΙΣ")
    return f"""
<p class="banner">ΔΕΙΓΜΑ — ΠΛΑΣΤΑ ΣΤΟΙΧΕΙΑ / SAMPLE — FICTIONAL DATA</p>
<h1>{title}</h1>
<p class="c">Αριθμός {d.registry_number}</p>
{intro}
<p><b>ΑΠΟ ΤΗ ΜΙΑ ΠΛΕΥΡΑ, {side_a}:</b></p>{sellers}
<p><b>ΑΠΟ ΤΗΝ ΑΛΛΗ ΠΛΕΥΡΑ, {side_b}:</b></p>{buyers}
{extra["parties"]}
<p>Οι συμβαλλόμενοι, τους οποίους γνωρίζω προσωπικά, ζήτησαν τη σύνταξη του παρόντος,
με το οποίο συμφώνησαν τα εξής:</p>
{prop}
{deal}
<p>{closing} Οι συμβαλλόμενοι δηλώνουν ότι έχουν καταβληθεί όλοι οι
φόροι και τα τέλη που αφορούν το ακίνητο και ότι προσκομίστηκαν όλα τα νόμιμα
δικαιολογητικά, τα οποία προσαρτώνται στο παρόν.</p>
<p>Σε πίστωση των ανωτέρω συντάχθηκε το παρόν, το οποίο αφού αναγνώστηκε καθαρά και
μεγαλόφωνα σε όλους, βεβαιώθηκε και υπογράφεται νόμιμα.</p>
<p class="c" style="margin-top: 24pt">ΟΙ ΣΥΜΒΑΛΛΟΜΕΝΟΙ &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
{gendered(d.notary, "Ο", "Η")} ΣΥΜΒΟΛΑΙΟΓΡΑΦΟΣ</p>
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
    story = fitz.Story(html=deed_html(spec), user_css=LONG_CSS if spec.long else CSS)
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


def load_font(size: int) -> ImageFont.ImageFont:
    """A font with Greek letters if one is installed, else Pillow's built-in one."""
    for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def ink(img: Image.Image, mark: Image.Image, at: tuple[int, int]) -> None:
    """Print a mark (dark on white) onto the page, like ink: the darker of the two wins."""
    x, y = at
    box = (x, y, x + mark.width, y + mark.height)
    img.paste(ImageChops.darker(img.crop(box), mark), box)


def stamp(rng: random.Random, radius: int) -> Image.Image:
    """A round notary stamp, slightly rotated."""
    size = radius * 2 + 8
    mark = Image.new("L", (size, size), 255)
    draw = ImageDraw.Draw(mark)
    shade = rng.randint(60, 110)
    c = size // 2
    for r, width in ((radius, 4), (radius - 12, 2)):
        draw.ellipse((c - r, c - r, c + r, c + r), outline=shade, width=width)
    font = load_font(max(10, radius // 6))
    for text, dy in (("ΣΥΜΒΟΛΑΙΟΓΡΑΦΟΣ", -radius // 4), ("ΔΟΚΙΜΩΝ", radius // 8)):
        draw.text((c, c + dy), text, fill=shade, font=font, anchor="mm")
    return mark.rotate(rng.uniform(-25, 25), fillcolor=255)


def signature(rng: random.Random, width: int) -> Image.Image:
    """A scribbled signature: a wobbly pen line."""
    height = width // 3
    mark = Image.new("L", (width, height), 255)
    x, y, points = 4.0, height / 2, []
    while x < width - 4:
        points.append((x, y))
        x += rng.uniform(3, 9)
        y = min(height - 4, max(4, y + rng.uniform(-height / 4, height / 4)))
    ImageDraw.Draw(mark).line(points, fill=rng.randint(20, 70), width=rng.randint(2, 3), joint="curve")
    return mark


def margin_note(rng: random.Random, size: int) -> Image.Image:
    """A handwritten-looking number in the margin: a look-alike value that belongs to nothing."""
    text = rng.choice([f"{rng.randint(100, 9999)}/{rng.randint(1, 12)}", f"Αρ. {rng.randint(1000, 99999)}",
                       f"{rng.randint(10, 99)}.{rng.randint(100, 999)}"])
    font = load_font(size)
    left, top, right, bottom = font.getbbox(text)
    mark = Image.new("L", (right - left + 10, bottom - top + 10), 255)
    ImageDraw.Draw(mark).text((5 - left, 5 - top), text, fill=rng.randint(40, 90), font=font)
    return mark.rotate(rng.uniform(-10, 10), expand=True, fillcolor=255)


def office_marks(img: Image.Image, rng: random.Random, first: bool, last: bool) -> None:
    """What real scanned deeds carry on top of the text."""
    w, h = img.size
    if last:
        ink(img, stamp(rng, w // 11), (int(w * rng.uniform(0.55, 0.72)), int(h * rng.uniform(0.70, 0.80))))
        for i in range(rng.randint(2, 4)):
            ink(img, signature(rng, w // 5), (int(w * rng.uniform(0.08, 0.6)), int(h * (0.82 + 0.035 * i))))
    if rng.random() < 0.5:  # a stamp right over the text
        ink(img, stamp(rng, w // 12), (int(w * rng.uniform(0.15, 0.65)), int(h * rng.uniform(0.25, 0.6))))
    if first:  # in the top margin, where it hides no text
        ink(img, margin_note(rng, h // 60), (int(w * rng.uniform(0.55, 0.75)), int(h * rng.uniform(0.012, 0.025))))
    if rng.random() < 0.6:  # a photocopier streak
        x = rng.randint(w // 10, w - w // 10)
        ImageDraw.Draw(img).line((x, 0, x + rng.randint(-6, 6), h), fill=rng.randint(150, 200), width=rng.randint(2, 4))


def scan(src: Path, dest: Path, rng: random.Random, harsh: bool = False) -> None:
    """Turn a clean PDF into an image-only one that looks like a cheap office scan.

    harsh adds stamps, signatures, a margin note and streaks, and degrades the
    image more: lower resolution, more rotation, blur, grain and compression.
    """
    pages = []
    with fitz.open(src) as doc:
        for i, page in enumerate(doc):
            pix = page.get_pixmap(dpi=110 if harsh else 130, colorspace=fitz.csGRAY)
            img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            if harsh:
                office_marks(img, rng, first=i == 0, last=i == doc.page_count - 1)
            turn = 3.5 if harsh else 1.8
            img = img.rotate(rng.uniform(-turn, turn), resample=Image.BICUBIC, expand=True, fillcolor=255)
            img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.6, 1.2) if harsh else rng.uniform(0.4, 0.9)))
            grain = Image.effect_noise(img.size, rng.uniform(10, 22))
            img = Image.blend(img, grain, 0.18 if harsh else 0.12)
            img = ImageEnhance.Contrast(img).enhance(rng.uniform(0.6, 0.9) if harsh else rng.uniform(0.75, 1.0))
            img = ImageEnhance.Brightness(img).enhance(rng.uniform(0.92, 1.05))
            buffer = io.BytesIO()
            img.save(buffer, "JPEG", quality=rng.randint(30, 45) if harsh else rng.randint(40, 60))
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
    parser.add_argument("--long", type=int, default=0,
                        help="Also generate N long deeds full of look-alike values in samples/dataset_long/")
    parser.add_argument("--varied", type=int, default=0,
                        help="Also generate N long deeds in varied wording and layout in samples/dataset_varied/")
    parser.add_argument("--harsh", action="store_true",
                        help="Also write harsh scans (stamps, signatures, notes) of the varied deeds "
                             "to samples/dataset_varied_scanned/")
    parser.add_argument("--holdout", type=int, default=0,
                        help="Also generate N varied long deeds in samples/dataset_holdout/, with the building "
                             "permit worded and issued differently: a set no prompt change was tuned on")
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

    if args.long:
        out = ROOT / "dataset_long"
        out.mkdir(exist_ok=True)
        rng = random.Random(args.seed + 1)  # a different set of deeds from samples/dataset
        for i in range(1, args.long + 1):
            render(add_distractors(random_deed(rng), rng), out / f"deed_{i:02d}.pdf")

    if args.varied:
        out = ROOT / "dataset_varied"
        out.mkdir(exist_ok=True)
        rng = random.Random(args.seed + 2)
        for i in range(1, args.varied + 1):
            render(vary(add_distractors(random_deed(rng), rng), rng), out / f"deed_{i:02d}.pdf")

        if args.harsh:
            scanned = ROOT / "dataset_varied_scanned"
            scanned.mkdir(exist_ok=True)
            rng = random.Random(args.seed + 3)
            for i in range(1, args.varied + 1):
                scan(out / f"deed_{i:02d}.pdf", scanned / f"deed_{i:02d}.pdf", rng, harsh=True)

    if args.holdout:
        out = ROOT / "dataset_holdout"
        out.mkdir(exist_ok=True)
        rng = random.Random(args.seed + 4)
        for i in range(1, args.holdout + 1):
            spec = reword_permit(vary(add_distractors(random_deed(rng), rng), rng), rng)
            render(spec, out / f"deed_{i:02d}.pdf")


if __name__ == "__main__":
    main()
