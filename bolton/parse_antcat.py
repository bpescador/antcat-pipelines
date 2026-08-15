#!/usr/bin/env python3
"""
parse_antcat.py  -- AntCat side of the Bolton-vs-AntCat catalogue diff.

Reads the worldants.txt dump and writes:
  antcat_species.csv   one row per species-group name (all statuses)
  antcat_genera.csv    one row per genus-group name  (all statuses)

Also exposes load_keys() used by diff_catalogue.py to build the match-key sets.

The dump already contains every species-group and genus-group name with its
status, so no Rails export is needed for these two categories.  (References are
NOT in the dump -- see export_references.rb.)

Matching key = (genus, gstem(terminal_epithet)).  Each AntCat row contributes
keys for BOTH its own combination and its current-valid combination, because
AntCat stores every historical/obsolete combination as a separate row.
"""
import csv, sys, re, os, json

csv.field_size_limit(sys.maxsize)

# ---- gender / spelling normaliser for terminal epithets -------------------
# Latin species epithets vary by the gender of the genus (-us/-a/-um, -is/-e,
# -er, etc.) and by genitive doubling (smithi/smithii).  We strip the variable
# tail to a stem so that legitimate gender variants compare equal.
_GENDER_SUFFIXES = ('iensis', 'ensis', 'icus', 'ica', 'icum',
                    'inus', 'ina', 'inum',
                    'osus', 'osa', 'osum',
                    'eus', 'ea', 'eum',
                    'us', 'um', 'is', 'es', 'os', 'as',
                    'er', 'or', 'ra', 'rum',
                    'a', 'e', 'i', 'o')

def gstem(ep: str) -> str:
    e = re.sub(r'[^a-z]', '', (ep or '').lower())
    if not e:
        return ''
    e = re.sub(r'ii$', 'i', e)            # smithii -> smithi
    for suf in _GENDER_SUFFIXES:          # longest first (tuple ordered)
        if len(e) - len(suf) >= 3 and e.endswith(suf):
            return e[:-len(suf)]
    return e

def norm_genus(g: str) -> str:
    return re.sub(r'[^a-z]', '', (g or '').lower())

# ---- worldants.txt parsing ------------------------------------------------
def split_current_valid(cvn: str):
    """current valid name field is 'Subfamily Genus species [subspecies]'.
    Drop the leading subfamily token. Return (genus, terminal_epithet)."""
    if not cvn:
        return ('', '')
    toks = cvn.split()
    if len(toks) < 2:
        return ('', '')
    body = toks[1:]                       # drop subfamily
    genus = body[0]
    terminal = body[-1] if len(body) > 1 else ''
    return (genus, terminal)

def col_getter(header):
    idx = {h: i for i, h in enumerate(header)}
    def g(row, c):
        return row[idx[c]] if c in idx and idx[c] < len(row) else ''
    return g

def read_rows(path):
    with open(path, encoding='utf-8', errors='replace', newline='') as fh:
        r = csv.reader(fh, delimiter='\t')
        header = next(r)
        g = col_getter(header)
        for row in r:
            yield row, g

def build(path, outdir):
    os.makedirs(outdir, exist_ok=True)
    sp_rows, gn_rows = [], []
    sp_keys, gn_keys = set(), set()

    for row, g in read_rows(path):
        genus   = g(row, 'genus')
        subg    = g(row, 'subgenus')
        species = g(row, 'species')
        subsp   = g(row, 'subspecies')
        status  = g(row, 'status')
        avail   = g(row, 'available')
        cvn     = g(row, 'current valid name')
        rank    = g(row, 'current valid rank')
        acid    = g(row, 'antcat id')
        ad      = g(row, 'author date')
        year    = g(row, 'year')
        fossil  = str(g(row, 'fossil')).strip().lower() in ('t', 'true', '1', 'yes')

        is_genus_group = bool(genus) and not species and not subsp
        # higher taxa (family / subfamily / tribe) carry no genus and no epithet
        if not genus and not species and not subsp:
            continue
        if is_genus_group:
            name = subg if subg else genus          # subgenus name lives in subgenus col
            gn_rows.append(dict(antcat_id=acid, name=name, rank=rank,
                                status=status, available=avail, fossil=fossil,
                                author_date=ad, current_valid_name=cvn))
            gn_keys.add(norm_genus(name))
            cg, _ = split_current_valid(cvn)
            if cg:
                gn_keys.add(norm_genus(cg))
            continue

        # species-group name
        terminal = subsp if subsp else species
        sp_rows.append(dict(antcat_id=acid, genus=genus, species=species,
                            subspecies=subsp, terminal=terminal,
                            gstem=gstem(terminal), status=status,
                            available=avail, fossil=fossil,
                            author_date=ad, year=year,
                            current_valid_name=cvn))
        # key from own combination
        sp_keys.add((norm_genus(genus), gstem(terminal)))
        # key from current-valid combination (catches obsolete combos)
        if cvn:
            cg, ct = split_current_valid(cvn)
            if cg and ct:
                sp_keys.add((norm_genus(cg), gstem(ct)))

    # write CSVs
    with open(os.path.join(outdir, 'antcat_species.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(sp_rows[0].keys()))
        w.writeheader(); w.writerows(sp_rows)
    with open(os.path.join(outdir, 'antcat_genera.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=list(gn_rows[0].keys()))
        w.writeheader(); w.writerows(gn_rows)

    # persist key sets for the differ
    with open(os.path.join(outdir, 'antcat_species_keys.json'), 'w') as f:
        json.dump(sorted('%s|%s' % k for k in sp_keys), f)
    with open(os.path.join(outdir, 'antcat_genera_keys.json'), 'w') as f:
        json.dump(sorted(gn_keys), f)

    print(f"AntCat species-group rows: {len(sp_rows):>6}  | distinct match keys: {len(sp_keys)}")
    print(f"AntCat genus-group   rows: {len(gn_rows):>6}  | distinct match keys: {len(gn_keys)}")
    return sp_keys, gn_keys

if __name__ == '__main__':
    src = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else '.'
    build(src, out)
