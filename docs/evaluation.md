# Evaluation

How accuracy is measured, on what, and what the numbers show. [Back to the README](../README.md)

## Method

Real deeds cannot be shared, so [`samples/make_sample_deed.py`](../samples/make_sample_deed.py) generates fictional deeds together with a JSON file of the correct values. That makes three measurements possible:

- **Accuracy**: every field in the ground truth is compared with the extraction, including fields that should be null, so an invented value counts as wrong. An invented party (for example a lawyer listed as a legal representative) is wrong in every one of its fields, like a missed one. Comparison ignores formatting only: accents, case, spacing, Latin look-alike letters in ID numbers, a name with or without the patronymic (names only: an address without its city is wrong), and a municipal unit with or without the "Δημοτική Ενότητα" label. When both models score the same, the faster one is named the winner and the report marks it as a tie.
- **Completeness**: the share of fields that are filled in. Used when no ground truth exists (any uploaded PDF). It rewards invented values, so it is a weak proxy.
- **Disagreement**: fields where the two models return different values, a consistency signal that needs no ground truth.

Latency is measured with `time.perf_counter()`. In a model evaluation both models run in parallel, so it takes as long as the slower one.

## Datasets

All in [`samples/`](../samples/), ten deeds each, every PDF with a `.json` of its correct values.

| Folder | What it tests |
|---|---|
| `dataset/` | Short deeds that state each value once |
| `dataset_scanned/` | The same, as simulated scans: grayscale images with slight rotation, blur, grain, uneven contrast and heavy JPEG compression, no text layer |
| `dataset_long/` | Long deeds (6–8 pages, in larger, widely spaced type like real deeds) full of look-alike values |
| `dataset_varied/` | Long deeds in varied wording and layout |
| `dataset_varied_scanned/` | The varied deeds as harsh scans |
| `dataset_holdout/` | New varied deeds for checking a prompt fix on wording it was not written against |

**Short deeds** state each value once, so strong and weak models score alike.

**Long deeds** keep the same kind of correct answers but surround them with look-alike values: a title history of earlier owners, deed numbers, notaries, dates and prices; other units in the building with their own areas and ΚΑΕΚ; lawyers and an engineer with tax IDs; the assessed value next to the price; tax, mortgage and fee amounts; and a list of attached documents with their own numbers and dates. A model that picks up a look-alike value is marked wrong.

**Varied deeds**: all of the above share one template, so a model could do well by learning its wording. These change it: headings (ΠΡΩΤΟ / Άρθρο 1 / 1.), parties as prose or as «Α.Φ.Μ.: …» fields or with birth year and tax office, dates with the weekday or as 15/3/2024, amounts as «185.000 ευρώ» or «ευρώ 185.000,00», and the sections in another order. Their **harsh scans** add what real scans carry: a notary stamp over the text, signatures, a handwritten number in the margin, photocopier streaks, more rotation and lower resolution.

**Held-out deeds**: a fix found on one set and measured on the same set can simply be fitted to it. These are ten new varied deeds whose building permit is also worded three new ways («άδεια οικοδομής αριθ. …», «οικοδομική άδεια …») and issued by three different offices.

The tax IDs in every deed deliberately fail the official check-digit test, so they cannot belong to a real person. That is also why the app flags all of them.

Regenerate everything with `python samples/make_sample_deed.py --dataset 10 --scanned --long 10 --varied 10 --harsh --holdout 10`. Run a set with `python -m deed_extractor.benchmark --dataset samples/<folder>` (see [Development](development.md#command-line)).

## Results

`gemini-3.8-flash`, final prompt, one run per set:

| Set | Accuracy | Perfect deeds | Median time |
|---|---|---|---|
| Long deeds full of look-alike values (digital) | **100%** | 10/10 | 29 s |
| Varied wording and layout (digital) | **100%** | 10/10 | 27 s |
| Held-out: new deeds, permit worded and issued differently | **100%** | 10/10 | 29 s |
| Varied, harsh scans (stamps, signatures, no text layer) | **99.3%** | 9/10 | 26 s |

Raw outputs and scores are in [`results/`](results/): `long.json`, `varied.json`, `holdout.json` and `varied_scanned.json` for the table above, and the `history_*.json` files for the runs before each fix.

### How it got there

Each step was measured, fixed, and measured again:

| Step | Before | After |
|---|---|---|
| **Lawyers listed as representatives.** In the 4 long deeds with no real representative, Flash listed the lawyers attending the signing. One sentence in the schema and prompt | 92.3%, 5 invented people | 98.6%, none; real representatives still 5/5 |
| **Misread ΚΑΕΚ digits** (one pair swapped, one digit dropped) that still looked valid. The PDF's text now goes with each page image, and every copied value is looked up in it | 98.8% on the same 8 deeds, 2 misreads, ~39 s | 99.6%, 0 misreads, ~27 s |
| **Building permit without its issuing office** («1728/1990»): all 3 errors on the varied deeds, 6 of 7 on their scans. The field now asks for the issuing authority | varied 98.8%, scans 97.5% | varied 100%, scans 99.3% |

The permit fix was found on the varied deeds, so it was also measured on the held-out set: 100%, with every issuing office copied correctly.

The text check raised no false alarms on the correct values of any digital deed.

### What is left

- **Scans have no text to check against.** The two remaining errors are both on one harsh scan: a ΚΑΕΚ that lost a digit (flagged by the format check) and a representative's ΑΦΜ with one digit misread (0 → 8). On a real deed the ΑΦΜ check digit would usually flag it; the fictional tax IDs fail that test on purpose, so here it cannot be told apart.
- **Flash-Lite**, measured earlier with the first prompt: 95.0% on short deeds, 95.7% on their scans and 79.5% on long ones, with systematic errors (cities dropped from addresses, rare surnames "corrected", representatives invented in every long deed). About 2–3× faster, but not accurate enough to use without review.

## Limits of these numbers

- The deeds come from one generator. Real deeds vary more, and real handwriting is not simulated, so accuracy on real documents will likely be lower.
- Ten deeds per set and one run each. Results vary between runs (the ΚΑΕΚ misreads appeared in one run and not another), so a difference of a point or two is not meaningful.
- The held-out set guards against fitting the permit fix to its wording, not against everything the generator shares across sets.
