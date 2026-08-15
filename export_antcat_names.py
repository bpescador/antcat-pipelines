#!/usr/bin/env python3
"""
export_antcat_names.py -- the AntCat side of an AntCat -> TaxonWorks name sync.

Emits ONE ROW PER NAME (protonym identity), not one row per database record.
That distinction matters: worldants.txt carries ~34,600 rows but only ~23,000
names, because AntCat stores a separate row for every COMBINATION a name has
ever been placed in ('obsolete combination'). Those are not names -- in
TaxonWorks they are Combination objects, not TaxonNames -- so importing them as
names would corrupt the target project.

TARGET NAME FOR EVERY INVALID STATUS
For the DwC-A Checklist importer to build the right nomenclatural relationship,
every invalid name needs the name that supersedes it. AntCat records this in
different places depending on status:

  synonym                -> `current valid name` column (the senior name)
  unavailable misspelling-> `current valid name` column (the correct spelling)
  homonym                -> NOT in the column. The replacement is stated in the
                            history prose, in one of two places:
                              * on the REPLACEMENT's row: "Replacement name for <homonym> ..."
                              * on the HOMONYM's own row:  "Replacement name: <replacement> ..."
                            Resolved here by protonym identity (epithet+author+year),
                            which is genus-independent and so survives recombination.
  unavailable            -> AntCat genuinely records no senior/replacement.
  unidentifiable         -> genuinely none.
  excluded from Formicidae-> genuinely none.

So a BLANK target now means "AntCat has none", not "the export didn't select it".
Both the target NAME and its antcat_id are emitted, so the reconciliation can
join on identity -- essential for homonyms, which by definition share spellings.

Output columns
    protonym_key            original_genus|original_epithet|year  (identity key)
    antcat_id               AntCat's id for the name record
    scientific_name         current combination, as AntCat spells it (gender-agreed)
    genus, species, subspecies, rank
    authorship              AntCat's `author date`, e.g. "(Mayr, 1862)"
    year
    status                  AntCat's status vocabulary
    valid_name              senior / valid / replacement name; blank iff AntCat has none
    valid_name_id           antcat_id of valid_name  (join on identity, not string)
    target_kind             how valid_name was derived: current_valid_name |
                            replacement_name | '' (none)
    original_combination    the protonym line's name, as PUBLISHED
    original_epithet        terminal epithet as PUBLISHED (may differ from `species`)
    spelling_differs        TRUE when the published spelling != the current spelling
    fossil

Read-only. Consumes the same worldants.txt as the Bolton diff.
"""
import csv, sys, os, re, argparse
from collections import defaultdict
from protonym import parse_protonym, strip_html, fold, year4, authorkey

csv.field_size_limit(sys.maxsize)

# which row best describes the NAME when several share one protonym
STATUS_RANK = {'valid': 0, 'synonym': 1, 'homonym': 2, 'unavailable': 3,
               'unidentifiable': 4, 'excluded from Formicidae': 5,
               'unavailable misspelling': 6, 'obsolete combination': 7}

FIELDS = ['protonym_key', 'antcat_id', 'scientific_name', 'genus', 'species', 'subspecies',
          'rank', 'authorship', 'year', 'status', 'valid_name', 'valid_name_id',
          'target_kind', 'original_combination', 'original_epithet', 'spelling_differs',
          'fossil', 'reference_id', 'reference_pages']

REPL_FOR = re.compile(r'Replacement name for\s+(.+?)(?:\.|\[|\(date|$)')
REPL_BY = re.compile(r'Replacement name:\s+(.+?)(?:\.|\[|$)')
GENUS_TOK = re.compile(r'^\s*([A-Z][a-z\u00C0-\u024F]+)')
# original-description page: after the year come optional DOI token(s) and/or PDF
# link text, then a colon, then the page. Requiring the colon stops a DOI's leading
# "10" from being taken as the page (bug found in the TaxonWorks sync, Aug 2026);
# (?:PDF|DOI)* keeps the common "year PDF: page" form parsing, in either token order.
PAGE_RE = re.compile(
    r'\b(?:1[6789]\d\d|20\d\d)[a-z]?\b'   # year (+ optional disambiguation letter)
    r'(?:\s*(?:PDF|\d+\.\S+))*'           # optional PDF link text / DOI token, any order
    r'\s*:\s*'                            # the colon before the page
    r'(\d+)(?!\.\d)'                      # page number, not followed by .digit (DOI-shaped)
)


def original_page(history_text):
    m = PAGE_RE.search(strip_html(history_text)[:200])
    return m.group(1) if m else ''


def build_replacement_map(rows, ix, TH):
    """homonym antcat_id -> replacement antcat_id, from the history prose.

    Species names resolve on protonym identity (epithet, author, year), which is
    genus-independent; genus-group homonyms resolve on the genus name + year."""
    def term(r):
        return (r[ix['subspecies']].strip() or r[ix['species']].strip())

    by_eay = defaultdict(list)      # (epithet, authorkey, year) -> ids   (species)
    by_ty = defaultdict(list)       # (terminal, year) -> ids            (fallback)
    by_genus_y = defaultdict(list)  # (genus, year) -> ids               (genus-group)
    homonym_ids = set()
    for r in rows:
        if len(r) <= TH:
            continue
        rid = r[ix['antcat id']].strip()
        if r[ix['status']].strip() == 'homonym':
            homonym_ids.add(rid)
        yr = year4(r[ix['year']])
        t = term(r)
        if t:
            p = parse_protonym(strip_html(r[TH]))
            if p:
                by_eay[(p[1], p[2], p[3])].append(rid)
            if yr:
                by_ty[(fold(t).lower(), yr)].append(rid)
        elif yr:                                       # genus-group row (no epithet)
            by_genus_y[(fold(r[ix['genus']].strip()).lower(), yr)].append(rid)

    def resolve(named):
        s = named.strip()
        p = parse_protonym(s)
        if p:
            hit = by_eay.get((p[1], p[2], p[3])) or by_ty.get((p[1], p[3]))
            if hit:
                return hit
        gm = GENUS_TOK.match(s)                         # genus-group name
        ym = re.search(r'(1[6789]\d\d|20\d\d)', s)
        if gm and ym:
            return by_genus_y.get((fold(gm.group(1)).lower(), ym.group(1)), [])
        return []

    repl = {}
    # channel 1: the replacement row names the homonym
    for r in rows:
        if len(r) <= TH:
            continue
        rid = r[ix['antcat id']].strip()
        m = REPL_FOR.search(strip_html(r[TH]))
        if m:
            for hid in resolve(m.group(1)):
                if hid in homonym_ids and hid != rid:
                    repl.setdefault(hid, rid)
    # channel 2: the homonym row names its replacement
    for r in rows:
        if len(r) <= TH:
            continue
        hid = r[ix['antcat id']].strip()
        if hid not in homonym_ids or hid in repl:
            continue
        m = REPL_BY.search(strip_html(r[TH]))
        if m:
            for x in resolve(m.group(1)):
                if x != hid:
                    repl[hid] = x
                    break
    return repl, homonym_ids


def run(worldants, out_path, include_combinations=False):
    with open(worldants, encoding='utf-8', errors='replace', newline='') as fh:
        rd = csv.reader(fh, delimiter='\t')
        hdr = next(rd)
        ix = {h: i for i, h in enumerate(hdr)}
        rows = [r for r in rd if len(r) > ix['taxonomic history html']]
    TH = ix['taxonomic history html']
    RID = ix['reference id']

    # id -> current combination string + protonym key, for filling valid_name/_id
    id_name, id_protokey, name_to_id = {}, {}, {}
    for r in rows:
        rid = r[ix['antcat id']].strip()
        nm = ' '.join(x for x in (r[ix['genus']].strip(),
                                  r[ix['species']].strip(),
                                  r[ix['subspecies']].strip()) if x)
        id_name[rid] = nm
        # first valid row for a given binomial wins; else any row
        if nm and (nm not in name_to_id or r[ix['status']].strip() == 'valid'):
            name_to_id[nm] = rid
        p = parse_protonym(strip_html(r[TH]))
        if p:
            id_protokey[rid] = f'{p[0]}|{p[1]}|{p[3]}'

    replacement_of, _homonyms = build_replacement_map(rows, ix, TH)

    def valid_id_from_cvn(cvn_parts, year):
        """resolve a 'current valid name' string to an antcat_id (name -> id index)"""
        if len(cvn_parts) < 2:
            return ''
        body = ' '.join(cvn_parts[1:])                 # drop leading subfamily
        return name_to_id.get(body, '')

    names, n_rows, n_comb, n_noproto = {}, 0, 0, 0
    for r in rows:
        n_rows += 1
        status = r[ix['status']].strip()
        if status == 'obsolete combination' and not include_combinations:
            n_comb += 1
            continue
        term = (r[ix['subspecies']].strip() or r[ix['species']].strip())
        if not term:
            continue
        p = parse_protonym(strip_html(r[TH]))
        if not p:
            n_noproto += 1
            continue
        ogen, oepi, _au, yr = p
        key = f'{ogen}|{oepi}|{yr}'
        rid = r[ix['antcat id']].strip()
        genus = r[ix['genus']].strip()
        cvn = r[ix['current valid name']].strip().split()

        valid_name, valid_id, kind = '', '', ''
        if status == 'homonym':
            rep = replacement_of.get(rid, '')
            if rep:
                valid_name, valid_id, kind = id_name.get(rep, ''), rep, 'replacement_name'
        elif len(cvn) > 1:                              # synonym, unavailable misspelling, ...
            valid_name = ' '.join(cvn[1:])
            valid_id = valid_id_from_cvn(cvn, yr)
            kind = 'current_valid_name'

        rec = dict(
            protonym_key=key, antcat_id=rid,
            scientific_name=' '.join(x for x in (genus, r[ix['species']].strip(),
                                                 r[ix['subspecies']].strip()) if x),
            genus=genus, species=r[ix['species']].strip(), subspecies=r[ix['subspecies']].strip(),
            rank=r[ix['current valid rank']].strip(),
            authorship=r[ix['author date']].strip(), year=year4(r[ix['year']]),
            status=status, valid_name=valid_name, valid_name_id=valid_id, target_kind=kind,
            original_combination=f'{ogen.title()} {oepi}', original_epithet=oepi,
            spelling_differs=str(fold(oepi).lower() != fold(term).lower()).upper(),
            fossil=r[ix['fossil']].strip(),
            reference_id=r[RID].strip(),                # the reference that ORIGINALLY published the name
            reference_pages=original_page(r[TH]))       # page of the original description
        prev = names.get(key)
        if prev is None or STATUS_RANK.get(status, 99) < STATUS_RANK.get(prev['status'], 99):
            names[key] = rec

    out_rows = sorted(names.values(),
                      key=lambda r: (r['genus'], r['species'], r['subspecies']))
    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, delimiter='\t',
                           extrasaction='ignore', lineterminator='\n')
        w.writeheader()
        w.writerows(out_rows)

    # ---- report + sanity check ----
    from collections import Counter
    st = Counter(r['status'] for r in out_rows)
    diff = sum(r['spelling_differs'] == 'TRUE' for r in out_rows)
    print(f'worldants rows read:            {n_rows}')
    print(f'  skipped, obsolete combination: {n_comb}   (Combinations in TW, not TaxonNames)')
    print(f'  skipped, no protonym parsed:   {n_noproto}')
    print(f'names written:                  {len(out_rows)}   -> {out_path}')
    print(f'  published spelling != current: {diff} ({100*diff/max(1,len(out_rows)):.1f}%)')
    print()
    print('status / count / have target / blank target:')
    for s in sorted(st):
        grp = [r for r in out_rows if r['status'] == s]
        have = sum(1 for r in grp if r['valid_name'])
        print(f'   {s:26} {len(grp):6}  target={have:5}  blank={len(grp)-have:5}')
    print()
    # sanity: synonym + homonym should not be blank unless AntCat truly lacks a target
    for s in ('synonym', 'homonym'):
        blank = [r for r in out_rows if r['status'] == s and not r['valid_name']]
        print(f'SANITY {s}: {len(blank)} blank target(s)')
        for r in blank[:4]:
            print(f'   {r["antcat_id"]} {r["scientific_name"]}')
    # id coverage
    withid = sum(1 for r in out_rows if r['valid_name'] and r['valid_name_id'])
    withname = sum(1 for r in out_rows if r['valid_name'])
    print()
    print(f'valid_name populated: {withname}; of those with valid_name_id: {withid} '
          f'({100*withid/max(1,withname):.1f}%)')
    with_ref = sum(1 for r in out_rows if r['reference_id'])
    with_pg = sum(1 for r in out_rows if r['reference_pages'])
    print(f'reference_id populated:  {with_ref} ({100*with_ref/max(1,len(out_rows)):.1f}%)')
    print(f'reference_pages parsed:  {with_pg} ({100*with_pg/max(1,len(out_rows)):.1f}%)')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--worldants', required=True)
    ap.add_argument('--out', default='antcat_names.tsv')
    ap.add_argument('--include-combinations', action='store_true')
    a = ap.parse_args()
    run(a.worldants, a.out, a.include_combinations)
