# Genus-group derivations not in Wheeler 1956 or Wheeler & Wheeler 1984b (21 Nov 2026)

`deriv_data.py` holds an AntCat derivation for each of the 411 genus-group protonyms neither Wheeler edition covers:
the author's own statement where the original description (OCR library, or PDFs copied from AntCat) gives one,
cited "(Author, year: page)"; otherwise a derivation from the name's parts, marked "apparently" or "possibly" where
uncertain, under the AntCat policy on derived etymologies (antcat.org/wiki/17). `assemble.py` builds the texts,
adds the gender sentence (ICZN Art. 30) and leaves it out wherever it would differ from the gender AntCat records,
or the gender is an open question. Run in a folder holding `remaining_411.tsv` (the protonym list built from
`genus_protonyms.tsv`); output `genus_derivations_other_20261121.tsv`. Written by `write_protonym_fields.rb`,
rule `genus_derivation_original`.
