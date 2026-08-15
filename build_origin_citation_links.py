#!/usr/bin/env python3
"""
build_origin_citation_links.py -- join AntCat names to TaxonWorks records to produce
the origin-citation link file (taxon_name_id -> source_id -> pages).

WHAT THIS PRODUCES
    origin_citation_links.tsv, one row per TW name that resolves to an AntCat reference:
        taxon_name_id        TW Protonym id (the name to cite)
        source_id            TW Source id (the reference, as loaded from the BibTeX)
        pages                original-description page (from AntCat, DOI-safe)
        antcat_reference_id  the AntCat reference id -- the STABLE key across instances
        protonym_key         genus|epithet|author|year (identity, for auditing)

THE JOIN CHAIN
    TW name --(protonym identity)--> AntCat name row --reference_id--> antcatNNNN
           --(antcatNNNN identifier on the Source)--> TW source_id
           AntCat name row --reference_pages--> pages

    Nothing is matched on author-string spelling. Names join on protonym identity
    (original genus, terminal epithet, first-author surname, 4-digit year), which is
    genus-independent and survives recombination and gender agreement.

INPUTS (all read-only)
    --antcat-names   antcat_names.tsv          the AntCat name export (has reference_id,
                                               reference_pages, protonym_key)
    --tw-taxa        taxon1.csv,taxon2.csv,...  TW Filter Nomenclature CSV export(s)
                                               (Protonyms; the 10k clamp forces multiple
                                               parts -- pass them comma-separated)
    --tw-sources     ref1.csv,ref2.csv,...      TW Filter Sources CSV export(s). NOTE: the
                                               TW Source CSV export DROPS the identifier
                                               column, so the antcat_id is recovered from
                                               the '[antcat_id: NNNN]' substring embedded
                                               in the `cached` string of every row.

WHY THE SOURCE CSV IS PARSED FOR [antcat_id: N]
    We loaded the references with the BibTeX label stored as an Identifier
    (namespace antcat_ref). The Source CSV export doesn't emit identifiers, but it does
    emit `cached`, which contains the note we carried on every entry: "[antcat_id: NNNN]".
    That is the only place the AntCat id survives a Source CSV export, so it's the join
    anchor. (In a server-side build, read the Identifier directly instead.)

PRODUCTION NOTE
    The source_id column here is only valid for the instance the tw-sources export came
    from. For a different instance (e.g. production loaded fresh), re-resolve source_id
    from antcat_reference_id against that instance's Source identifiers -- the
    antcat_reference_id column is stable, source_id is not.
"""
import csv, sys, re, argparse
csv.field_size_limit(sys.maxsize)


def load_sources(paths):
    """antcat_id -> tw_source_id, recovered from the [antcat_id: N] note in `cached`."""
    src = {}
    for p in paths:
        for r in csv.DictReader(open(p, encoding='utf-8')):
            m = re.search(r'antcat_id[:=]\s*(\d+)', r.get('cached', '') or '')
            if m:
                src[m.group(1)] = r['id']
    return src


def load_tw_protonyms(paths):
    """the TW names to cite: species-group Protonyms only."""
    rows = []
    for p in paths:
        for r in csv.DictReader(open(p, encoding='utf-8')):
            # global_id like gid://taxon-works/Protonym/385077
            parts = r['global_id'].split('/')
            kind = parts[-2] if len(parts) >= 2 else ''
            if kind == 'Protonym' and r.get('rank', '') in ('species', 'subspecies'):
                rows.append(r)
    return rows


def tw_key3(r):
    """3-part protonym key (genus|epithet|year) from a TW name row's original_combination.

    The TW export gives `original_combination` as the published binomial/trinomial and
    `cached_nomenclature_date`/year. We key on (original genus, terminal epithet, year),
    lowercased and accent-folded, to match antcat_names.tsv's 3-part key.
    """
    oc = re.sub(r'<[^>]+>', '', r.get('original_combination', '')).strip()
    if not oc:
        return None
    # original_combination includes the author/year tail, e.g.
    #   "Calyptites Scudder, 1877"  or  "Aphaenogaster radchenkoi Kiran & Tezcan, 2008"
    # Strip everything from the author onward: cut at the first token that begins with an
    # uppercase letter AND is followed (eventually) by a 4-digit year, or simply cut at the
    # year. Simplest robust rule: take the name tokens BEFORE the author/year, where the
    # name part is the leading run of capitalized-genus + lowercase-epithet tokens.
    m_year = re.search(r'(1[6789]\d\d|20\d\d)', r.get('cached_author_year', '') or r.get('cached_nomenclature_date', '') or '')
    yr = m_year.group(1) if m_year else ''
    # name = tokens up to the author: drop tokens once we hit the author surname.
    # Heuristic: the epithet is the last LOWERCASE token; the genus is the first token.
    toks = oc.split()
    genus = fold(toks[0]).lower()
    lower_toks = [t for t in toks if t[:1].islower() and re.match(r'^[a-z\u00C0-\u024F-]+$', fold(t) if fold(t) else t)]
    # epithet is the last purely-lowercase alpha token (species/subspecies epithet)
    epithet = ''
    for t in reversed(toks):
        ft = fold(t)
        if ft and t[:1].islower():
            epithet = ft.lower(); break
    if genus and epithet and yr:
        return f'{genus}|{epithet}|{yr}'
    return None


def fold(s):
    """accent-fold + strip non-letters, matching the AntCat exporter's fold()."""
    import unicodedata
    s = unicodedata.normalize('NFKD', s)
    s = ''.join(c for c in s if not unicodedata.combining(c))
    return re.sub(r'[^A-Za-z]', '', s)


def antcat_key3(k4):
    """AntCat links use a 4-part key (genus|epithet|author|year); 3-part-ify to match TW."""
    p = k4.split('|')
    return f'{p[0]}|{p[1]}|{p[-1]}' if len(p) >= 3 else k4


def run(antcat_names, tw_taxa, tw_sources, out_path):
    src = load_sources(tw_sources)                       # antcat_id -> tw_source_id
    print(f'sources: {len(src)} antcat_id -> tw_source_id')

    # AntCat names keyed 3-part -> its row (reference_id, reference_pages)
    ac = {}
    for r in csv.DictReader(open(antcat_names, encoding='utf-8'), delimiter='\t'):
        ac.setdefault(antcat_key3(r['protonym_key']), r)   # 3-part collapse; first wins
    print(f'antcat names keyed (3-part): {len(ac)}')

    tw = load_tw_protonyms(tw_taxa)
    print(f'TW species-group protonyms: {len(tw)}')

    triples = []
    no_key = no_ac = no_ref = no_src = 0
    for r in tw:
        k = tw_key3(r)
        if not k:
            no_key += 1; continue
        a = ac.get(k)
        if not a:
            no_ac += 1; continue
        rid = a['reference_id'].strip()
        if not rid:
            no_ref += 1; continue
        sid = src.get(rid)
        if not sid:
            no_src += 1; continue
        triples.append((r['id'], sid, a['reference_pages'].strip(), rid, a['protonym_key']))

    with open(out_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter='\t')
        w.writerow(['taxon_name_id', 'source_id', 'pages', 'antcat_reference_id', 'protonym_key'])
        w.writerows(triples)

    print(f'\ntriples written: {len(triples)}  -> {out_path}')
    print(f'  no protonym key (TW):        {no_key}')
    print(f'  key not in AntCat:           {no_ac}')
    print(f'  AntCat row had no ref id:    {no_ref}')
    print(f'  ref id not loaded as Source: {no_src}')
    withpg = sum(1 for t in triples if t[2])
    print(f'  with pages: {withpg} ({100*withpg/max(1,len(triples)):.1f}%)')
    print(f'  distinct sources: {len({t[1] for t in triples})}')
    print(f'  duplicate taxon_name_ids: {len(triples) - len({t[0] for t in triples})}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--antcat-names', required=True)
    ap.add_argument('--tw-taxa', required=True, help='comma-separated TW Filter Nomenclature CSV parts')
    ap.add_argument('--tw-sources', required=True, help='comma-separated TW Filter Sources CSV parts')
    ap.add_argument('--out', default='origin_citation_links.tsv')
    a = ap.parse_args()
    run(a.antcat_names, a.tw_taxa.split(','), a.tw_sources.split(','), a.out)
