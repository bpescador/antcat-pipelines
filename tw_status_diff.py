#!/usr/bin/env python3
"""
tw_status_diff.py -- status differences between AntCat and TaxonWorks, name by name.

Inputs
  --antcat  antcat_names.tsv from export_antcat_names.py (one row per species-group protonym)
  --tw      the TW project's protonym export (one row per TW Protonym): tw_taxon_name_id,
            protonym_key, key_from, cached, original_combination, author_year, year, rank, ...,
            is_valid, valid_taxon_name_id, valid_name, classifications, status_relationships
  --out     folder for the output files

Join (as the TW project specified, 2026-11-11)
  1. protonym_key, against TW rows whose key came from the original combination;
     if a key has several TW rows, keep the one whose first author matches.
  2. for AntCat names still unmatched: current name + author + year, against TW rows whose
     key came from the current name (no original combination in TW).
  TW "[sic]" spelling records (Usage::Misspelling, IncorrectOriginalSpelling) have no
  AntCat row of their own: AntCat folds misspellings into the protonym.

Status, AntCat vocabulary -> what TW must show to agree
  valid                     is_valid, no NomenDubium
  synonym                   a Synonym relationship (plain, Subjective, Objective::*);
                            same final valid name (AntCat valid_name_id vs TW valid_taxon_name_id)
  homonym                   ReplacedHomonym, a Homonym relationship or the Homonym classification;
                            if both sides name the replacement, the same replacement
  unavailable               Iczn::Unavailable or NomenNudum
  unidentifiable            NomenDubium (TW's UncertainPlacement on a valid name is reported
                            apart, as vocabulary: it is how TW mostly records these)
  excluded from Formicidae  Unavailable::Excluded
  unavailable misspelling   Usage::Misspelling, same correct spelling
Targets are compared through the join (TW id -> AntCat protonym), so spelling and subgenus
differences in the target's name do not count. A target TW has no match for is compared by
genus and terminal epithet, allowing the gender endings.

Outputs
  tw_status_differences.tsv  the differences, one row per name, grouped in summary.txt into
                             status or target differences, TW record gaps, and vocabulary
  antcat_not_matched.tsv     AntCat names with no TW Protonym under either join
  summary.txt                counts
Read-only. Standard library only.
"""
import argparse, collections, csv, os, re, sys, unicodedata

csv.field_size_limit(sys.maxsize)

SYN = ('Iczn::Invalidating::Synonym',)                       # prefix: plain, Subjective, Objective::*
REPLACED = 'Iczn::Invalidating::Synonym::Objective::ReplacedHomonym'
HOMONYM_REL = 'Iczn::Invalidating::Homonym'
MISSPELLING = 'Iczn::Invalidating::Usage::Misspelling'
IOS = 'Iczn::Invalidating::Usage::IncorrectOriginalSpelling'
REL_RE = re.compile(r'\s*(Iczn::[A-Za-z0-9:]+)\s*->\s*(\d+)\s*(.*)')


def fold(s):
    s = unicodedata.normalize('NFKD', s or '')
    return ''.join(c for c in s if not unicodedata.combining(c))


def strip_html(s):
    return re.sub(r'<[^>]+>', '', s or '')


def first_author(s):
    """'(Chen <i>et al.</i>, 2022)' -> 'chen'; 'Dalla Torre, 1893' -> 'dallatorre'"""
    s = fold(strip_html(s)).lower()
    s = re.sub(r'[()\[\]]', '', s).split(',')[0]
    s = re.split(r'\s(?:&|and|et al\.?)\s|\set al', s)[0]
    return re.sub(r'[^a-z]', '', s)


def plain_name(s):
    """drop subgenus, [sic], rank words and placeholders; lower-case words"""
    s = re.sub(r'\([^)]*\)', ' ', fold(s or ''))
    s = re.sub(r'\[[^\]]*\]', ' ', s)
    s = re.sub(r'\b(?:var|subsp|st|r|n|stirps|race|morpha|ab)\.', ' ', s)
    return ' '.join(s.lower().split())


GENDER = re.compile(r'(?:us|a|um|is|e|er|ra|rum|ior|ius|os|on)$')


def stem(w):
    return GENDER.sub('', w) if len(w) > 4 else w


def loose_name(s):
    w = plain_name(s).split()
    return (w[0], stem(w[-1])) if len(w) >= 2 else tuple(w)


def tw_status(r):
    """TW row -> (label, note, flags). The label is AntCat's word where one fits. TW's own
    computed validity (is_valid) decides valid vs invalid; relationships and classifications
    say which kind of invalid."""
    cls = [c.strip() for c in r['classifications'].split(';') if c.strip()]
    rels = []
    for part in r['status_relationships'].split(';'):
        m = REL_RE.match(part)
        if m:
            rels.append((m.group(1), m.group(2), m.group(3).strip()))
    types = [t for t, _, _ in rels]
    replaced = [o for t, o, _ in rels if t == REPLACED]
    f = dict(
        homonym=bool(replaced) or any(t.startswith(HOMONYM_REL) for t in types)
        or 'Iczn::Available::Invalid::Homonym' in cls,
        replacement=replaced[0] if replaced else '',
        synonym=any(t.startswith(SYN) and t != REPLACED for t in types),
        uncertain='Iczn::Validating::UncertainPlacement' in types,
        valid_id=r['valid_taxon_name_id'])
    if MISSPELLING in types or IOS in types:
        return 'spelling record', '', f
    if r['is_valid'] == 'true':
        extra = [w for w, on in (('synonym', f['synonym']), ('homonym', f['homonym'])) if on]
        note = f'TW also holds a {" and ".join(extra)} relationship' if extra else ''
        if 'Iczn::Available::Valid::NomenDubium' in cls:
            return 'unidentifiable', note, f
        return 'valid', note, f
    if f['homonym']:
        return 'homonym', 'also a synonym' if f['synonym'] else '', f
    if f['synonym']:
        return 'synonym', '', f
    if 'Iczn::Unavailable::Excluded' in cls:
        return 'excluded from Formicidae', '', f
    if any(c in ('Iczn::Unavailable', 'Iczn::Unavailable::NomenNudum') for c in cls):
        return 'unavailable', 'nomen nudum' if 'Iczn::Unavailable::NomenNudum' in cls else '', f
    if 'Iczn::Fossil::Ichnotaxon' in cls:
        return 'invalid, no relationship', 'ichnotaxon', f
    return 'invalid, no relationship', '', f


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[1])
    ap.add_argument('--antcat', required=True)
    ap.add_argument('--tw', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    A = list(csv.DictReader(open(a.antcat, encoding='utf-8'), delimiter='\t'))
    T = [r for r in csv.DictReader(open(a.tw, encoding='utf-8'), delimiter='\t')
         if r['rank'] in ('species', 'subspecies')]
    tw_by_id = {r['tw_taxon_name_id']: r for r in T}
    a_by_id = {r['antcat_id']: r for r in A}
    a_by_name = collections.defaultdict(list)
    for r in A:
        a_by_name[plain_name(r['scientific_name'])].append(r)

    def is_sic(r):                                   # not the key: Forel named a variety "sic"
        return '[sic]' in r['cached']

    def stem_key(k):
        g, e, y = (k.split('|') + ['', '', ''])[:3]
        return (g, stem(e), y)

    by_key = collections.defaultdict(list)          # 1. protonym_key
    by_current = collections.defaultdict(list)      # 2. current name, TW rows keyed on it
    by_stem = collections.defaultdict(list)         # 3. protonym_key, endings allowed
    by_loose = collections.defaultdict(list)        # 4. current genus + epithet, endings allowed
    by_sic = collections.defaultdict(list)          # 5. AntCat misspellings: TW [sic] records
    for r in T:
        if is_sic(r):
            by_sic[(plain_name(r['cached']), r['year'])].append(r)
            continue
        if r['key_from'] == 'original_combination':
            by_key[r['protonym_key']].append(r)
            by_stem[stem_key(r['protonym_key'])].append(r)
        else:
            by_current[(plain_name(r['cached']), r['year'])].append(r)
        by_loose[loose_name(r['cached']) + (r['year'],)].append(r)

    STEPS = [
        ('protonym_key', lambda r: by_key.get(r['protonym_key'], [])),
        ('current name + author + year',
         lambda r: by_current.get((plain_name(r['scientific_name']), r['year']), [])),
        ('protonym_key, endings allowed', lambda r: by_stem.get(stem_key(r['protonym_key']), [])),
        ('current genus + epithet + author + year, endings allowed',
         lambda r: by_loose.get(loose_name(r['scientific_name']) + (r['year'],), [])),
        ('[sic] record, current name + author + year',
         lambda r: by_sic.get((plain_name(r['scientific_name']), r['year']), [])
         if r['status'] == 'unavailable misspelling' else [])]

    pairs, unmatched, how = [], [], collections.Counter()
    for r in A:
        hit, why = None, 'no TW Protonym by any join'
        for label, find in STEPS:
            c = find(r)
            if len(c) > 1 or label != 'protonym_key':     # a unique exact key needs no author check
                c = [t for t in c if first_author(t['author_year']) == first_author(r['authorship'])]
            for same in (lambda t: plain_name(t['cached']) == plain_name(r['scientific_name']),
                         lambda t: plain_name(t['original_combination']) == plain_name(r['original_combination']),
                         lambda t: loose_name(t['cached']) == loose_name(r['scientific_name'])):
                if len(c) > 1:                            # homonyms sharing a key: the names decide
                    c = [t for t in c if same(t)] or c
            if len(c) == 1:
                hit = (r, c[0], label)
                break
            if len(c) > 1:
                why = f'{len(c)} TW Protonyms match ({label})'
                break
        if hit:
            pairs.append(hit); how[hit[2]] += 1
        else:
            unmatched.append((r, why))

    tw_to_a = {}
    for ar, tr, _ in pairs:
        tw_to_a.setdefault(tr['tw_taxon_name_id'], ar['antcat_id'])

    def antcat_target_key(ar):
        t = a_by_id.get(ar['valid_name_id'])
        if t is None and ar['valid_name']:
            c = a_by_name.get(plain_name(ar['valid_name']), [])
            t = c[0] if len(c) == 1 else None
        return t['protonym_key'] if t else ''

    def same_target(ar, tw_target):
        if not ar['valid_name'] or not tw_target:
            return None                                  # one side names none: not compared
        mapped = tw_to_a.get(tw_target)
        if mapped:
            return a_by_id[mapped]['protonym_key'] == antcat_target_key(ar)
        tn = tw_by_id.get(tw_target, {}).get('cached', '')
        return bool(tn) and loose_name(tn) == loose_name(ar['valid_name'])

    def compare(ast, st, note, f, ar):
        """-> (kind or '' when they agree, TW target id shown in the row)"""
        if ast == 'synonym':
            if f['synonym'] and st in ('synonym', 'homonym'):
                return ('' if same_target(ar, f['valid_id']) is not False else 'target differs'), f['valid_id']
            if st == 'invalid, no relationship' and note != 'ichnotaxon':
                agrees = same_target(ar, f['valid_id']) is not False
                return ('TW: invalid with no synonym relationship; its valid name '
                        + ('agrees' if agrees else 'differs')), f['valid_id']
        elif ast == 'homonym':
            if f['homonym'] and st == 'homonym':
                return ('' if same_target(ar, f['replacement']) is not False else 'target differs'), f['replacement']
        elif ast == 'unavailable misspelling':
            if st == 'spelling record':
                return ('' if same_target(ar, f['valid_id']) is not False else 'target differs'), f['valid_id']
        elif st == ast:
            return ('TW record conflict: ' + note if note.startswith('TW also') else ''), ''
        elif ast == 'unidentifiable' and st == 'valid' and f['uncertain']:
            return 'vocabulary: AntCat unidentifiable, TW valid with UncertainPlacement', ''
        tgt = f['replacement'] if st == 'homonym' else (f['valid_id'] if st != 'valid' else '')
        return f'status: AntCat {ast}, TW {st}', tgt

    out, kinds, agree = [], collections.Counter(), collections.Counter()
    for ar, tr, joined in pairs:
        st, note, f = tw_status(tr)
        ast = ar['status']
        kind, tgt = compare(ast, st, note, f, ar)
        if tgt == tr['tw_taxon_name_id']:
            tgt = ''
        if not kind:
            agree[ast] += 1
            continue
        kinds[kind] += 1
        tt = tw_by_id.get(tgt, {})
        out.append(dict(
            difference=kind, antcat_id=ar['antcat_id'], antcat_name=ar['scientific_name'],
            antcat_authorship=strip_html(ar['authorship']), antcat_status=ast,
            antcat_target=ar['valid_name'], antcat_target_id=ar['valid_name_id'],
            tw_taxon_name_id=tr['tw_taxon_name_id'], tw_name=tr['cached'],
            tw_status=st + (f' ({note})' if note else ''),
            tw_target=tt.get('cached', tr['valid_name'] if tgt else ''), tw_target_id=tgt,
            tw_target_antcat_id=tw_to_a.get(tgt, ''),
            tw_classifications=tr['classifications'], tw_relationships=tr['status_relationships'],
            joined_on=joined))

    out.sort(key=lambda d: (d['difference'], d['antcat_name']))
    cols = list(out[0].keys()) if out else ['difference']
    with open(os.path.join(a.out, 'tw_status_differences.tsv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter='\t', lineterminator='\n')
        w.writeheader(); w.writerows(out)
    with open(os.path.join(a.out, 'antcat_not_matched.tsv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f, delimiter='\t', lineterminator='\n')
        w.writerow(['antcat_id', 'antcat_name', 'antcat_authorship', 'antcat_status',
                    'protonym_key', 'reason'])
        for r, why in sorted(unmatched, key=lambda x: x[0]['scientific_name']):
            w.writerow([r['antcat_id'], r['scientific_name'], strip_html(r['authorship']),
                        r['status'], r['protonym_key'], why])

    matched_tw = {tr['tw_taxon_name_id'] for _, tr, _ in pairs}
    tw_left = [r for r in T if r['tw_taxon_name_id'] not in matched_tw]
    spelling = sum(1 for r in tw_left if tw_status(r)[0] == 'spelling record')
    lines = [
        f'AntCat names (species group): {len(A)}',
        f'TW Protonyms (species, subspecies): {len(T)}',
        f'matched: {len(pairs)}  ' + ', '.join(f'{k} {v}' for k, v in how.items()),
        f'AntCat names not matched: {len(unmatched)}  (antcat_not_matched.tsv)',
        f'TW Protonyms not matched: {len(tw_left)}  of which [sic] spelling records {spelling}',
        f'agree: {sum(agree.values())}  ' + ', '.join(f'{k} {v}' for k, v in agree.most_common()),
        f'rows in tw_status_differences.tsv: {len(out)}',
    ]
    groups = (('status or target differs', lambda k: k.startswith(('status:', 'target'))),
              ('TW record gaps (the status agrees)', lambda k: k.startswith('TW')),
              ('vocabulary, not data', lambda k: k.startswith('vocabulary')))
    for title, test in groups:
        ks = [(k, v) for k, v in kinds.most_common() if test(k)]
        lines.append(f'{title}: {sum(v for _, v in ks)}')
        lines += [f'  {v:6d}  {k}' for k, v in ks]
    open(os.path.join(a.out, 'summary.txt'), 'w').write('\n'.join(lines) + '\n')
    print('\n'.join(lines))


if __name__ == '__main__':
    main()
