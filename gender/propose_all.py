#!/usr/bin/env python3
"""
propose_all.py -- one proposal per species-group protonym for the combined write (Brian, 15 Nov 2026 07:47: do it
all at once once the skill is complete). Read only. Runbook: gender/ETYMOLOGY_GRAMMAR_RUNBOOK.md.

Each protonym gets one primary queue, in this order:
  Q2 toponym / -ensis    rows of propose_part_of_speech_by_form.py (--pos-form)
  Q3 genitive            rows of propose_patronym_genitives.py (--patronyms), unless "not this queue"
  Q4 Latin or Greek word Lewis & Short readings as spelled or as a nominative form (lexicon.py), else LSJ
  Q5 compound            compounds.py (final element under policy Rule 1.6)
and is proposed, or held with the reason (the held rows are the sheet for Brian).

Q4/Q5 rules (all only where no part of speech is recorded, or the recorded one is the same):
  latin_form_pos            adjective or participle only                     -> that, demonstrated
  latin_noun_pos            common noun only, as spelled                     -> noun_in_apposition, demonstrated
  latin_proper_noun_pos     proper noun only (Diana: Art. 31.2.1 example)    -> noun_in_apposition, demonstrated
  latin_ambiguous_default_pos  adjective and noun (policy Rule 1.5)          -> noun_in_apposition, noun_by_default,
                                                                                reasonably_inferred
  compound_adjective_pos    adjective-final, adjectival-from-noun, one-termination -> adjective, demonstrated;
                            derived adjective (-osus, -atus, -alis...)       -> adjective, reasonably_inferred
  place_adjective_pos       -anus, -icus, -acus, -inus on a place in the locality (A&G 249) -> adjective, demonstrated
  suffix_form_pos           no dictionary word, but an adjectival suffix: -icus/-icum demonstrated; -anus, -inus,
                            -osus, -ica reasonably inferred; -escens a participle
  greek_form_pos            a Latinized Greek adjective (Art. 31.2.3, melaena) -> adjective; a Greek noun -> noun
Held: a noun whose ending was changed (globus -> globa); a noun-final compound (Rule 1.6); not identified; a
published etymology that calls a Latin adjective form a noun (needs a public note first); a part of speech
recorded that differs from the proposal (never overwritten); interpretation disputed or unresolved.
"""
import argparse, collections, csv, hashlib, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lexicon import load, lookup, fold  # noqa: E402
from compounds import Parser  # noqa: E402

csv.field_size_limit(sys.maxsize)
NOUN_STATEMENT = re.compile(r'\bnoun\b|apposition|substantiv', re.I)
ADJ_STATEMENT = re.compile(r'adjectiv', re.I)


def read_tsv(path, quoting=csv.QUOTE_MINIMAL):
    with open(path, encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh, delimiter='\t', quoting=quoting))


PLACE_ADJ = re.compile(r'(i?anus|i?ana|i?anum|icus|ica|icum|acus|aca|acum|inus|ina|inum)$')


def place_adjective(epithet, locality):
    """-anus, -icus, -acus, -inus on a stem that is a place in the AntCat locality (A&G 249; Manara 1992)."""
    e = fold(epithet)
    m = PLACE_ADJ.search(e)
    if not m:
        return None
    st = e[: m.start()]
    words = re.sub(r'[^a-z ]', ' ', fold(locality)).split()
    for w in words:
        if len(st) >= 4 and len(w) >= 4 and (w.startswith(st) or st.startswith(w)):
            return f'-{m.group(1)} on the place {w} in the type locality'
    return None


def q4(parser, lsj_keys, epithet, locality=''):
    """-> (rule, part_of_speech, basis, status, evidence) or ('held', '', '', '', reason)"""
    rs = lookup(parser.ls, epithet)
    common = [r for r in rs if r['kind'] != 'proper noun']
    # a feminine or neuter "noun" that is the adjective itself used as a substantive (frigida 'cold water', aurea
    # 'bridle') is not a second reading of the epithet
    adj_forms = {fold(r['headword']) for r in common if r['kind'] in ('adjective', 'participle')}
    if adj_forms:
        stems = {re.sub(r'(us|is|er)$', '', a) for a in adj_forms}
        common = [r for r in common if not (r['kind'] == 'noun' and r['gen'] in ('f.', 'n.') and
                                            re.sub(r'(a|um|e)$', '', fold(r['headword'])) in stems)]
    kinds = {r['kind'] for r in common}
    # a place in -ia spelled exactly as the epithet beside the feminine of an adjective in -ius (Aeolia and Aeolius,
    # Ionia and Ionius): place name in apposition or the adjective, Rule 1.5 (audit 16 Nov 2026). Surnames from
    # adjectives (Niger, Rufus) are not places and do not count.
    places = [r for r in rs if r['kind'] == 'proper noun' and fold(r['headword']) == fold(epithet) and
              fold(epithet).endswith('ia') and any(fold(c['headword']) == fold(epithet)[:-1] + 'us' for c in common)]
    ev = lambda rr: '; '.join(f"{r['headword']} ({r['kind']}, L&S {r['entry']}: {r['gloss'][:40]})" for r in rr[:3])
    if places and kinds & {'adjective', 'participle'}:
        return 'held', '', '', '', 'a proper noun (' + places[0]['headword'] + ') and an adjective form: Rule 1.5: ' + ev(common)
    if kinds and kinds <= {'adjective', 'participle'}:
        pos = 'participle' if kinds == {'participle'} else 'adjective'
        return 'latin_form_pos', pos, 'grammatical_form', 'demonstrated', ev(common)
    if kinds == {'noun'}:
        return 'latin_noun_pos', 'noun_in_apposition', 'grammatical_form', 'demonstrated', ev(common)
    if kinds == {'noun (altered ending)'}:
        return 'held', '', '', '', 'a Latin noun with a changed ending: ' + ev(common)
    if kinds & {'adjective', 'participle'} and 'noun' in kinds:
        # Rule 1.5 needs a judgment of what is reasonable (faber 'smith' or 'skilful'); held for Brian, grouped
        return 'held', '', '', '', 'both a Latin adjective and a noun (Rule 1.5 default would be noun in apposition): ' + ev(common)
    if kinds:
        return 'held', '', '', '', 'dictionary readings not settled: ' + ev(common)
    e = fold(epithet)
    if e in re.sub(r'[^a-z ]', ' ', fold(locality)).split():
        return 'held', '', '', '', 'the epithet is a place name of the type locality: noun in apposition or adjective'
    pl = place_adjective(epithet, locality)
    if pl:
        return 'place_adjective_pos', 'adjective', 'grammatical_form', 'demonstrated', pl
    c = parser.parse(epithet)
    gr = lsj_keys.get(e, [])
    gkinds = {r['kind'] for r in gr}
    if rs and 'adjective' in gkinds:
        return 'held', '', '', '', f"a proper noun ({rs[0]['headword']}) and a Greek adjective ({gr[0]['headword']}): Rule 1.5"
    if rs and (not c or c[0] == 'derived-adjective'):
        return 'latin_proper_noun_pos', 'noun_in_apposition', 'grammatical_form', 'demonstrated', ev(rs)
    if gkinds == {'adjective'} and re.search(r'(us|a|um)$', e):
        return 'greek_form_pos', 'adjective', 'grammatical_form', 'demonstrated', f"Greek {gr[0]['headword']} (adjective): {gr[0]['gloss'][:40]}"
    if gkinds == {'noun'}:
        # LSJ's labels are not reliable enough for a noun reading (leptothrix is an adjective there): later queue
        return 'held', '', '', '', f"Greek word, reading to confirm: {gr[0]['headword']} ({gr[0]['gloss'][:40]})"
    if c and c[0] == 'genitive':
        # victoris, stipitum: the genitive of a Latin noun (audit 16 Nov 2026); the rule for genitives of common
        # nouns is not written yet, so these wait in the later queue
        return 'held', '', '', '', 'a Latin noun in the genitive case: ' + c[4]
    if c:
        kind, a, b, first, final = c
        evc = f"{kind}: {' + '.join(x for x, _ in first)} + {b}; {final}"
        if kind in ('adjective-final', 'adjectival-from-noun', 'one-termination'):
            return 'compound_adjective_pos', 'adjective', 'grammatical_form', 'demonstrated', evc
        if kind == 'derived-adjective':
            return 'compound_adjective_pos', 'adjective', 'grammatical_form', 'reasonably_inferred', evc
        return 'held', '', '', '', 'noun-final compound (Rule 1.6): ' + evc
    # adjectival suffixes on words no dictionary lists (A&G 249, 241-243): the masculine and neuter forms cannot be
    # personal names; -ica, -ana, -ina can (Monica, Mariana, Christina), so those are only reasonably inferred or held
    if re.search(r'(escens|ascens)$', e):
        return 'suffix_form_pos', 'participle', 'grammatical_form', 'demonstrated', 'present participle of an inchoative verb (-escens)'
    if re.search(r'os(us|a|um)$', e) and len(e) - len(re.search(r'os(us|a|um)$', e).group(0)) <= 3 and not c:
        # -osus forms on noun stems; three letters are no stem (Lycosa is a spider genus): not evidence
        return 'held', '', '', '', 'the suffix -osus on a stem of three letters or fewer (lyc + osa): not evidence'
    if re.search(r'(icus|icum)$', e):
        return 'suffix_form_pos', 'adjective', 'grammatical_form', 'demonstrated', 'adjectival suffix -icus (A&G 249)'
    if re.search(r'(anus|anum|inus|inum|osus|osum|osa|ica)$', e):
        return 'suffix_form_pos', 'adjective', 'grammatical_form', 'reasonably_inferred', f"adjectival suffix -{re.search(r'(anus|anum|inus|inum|osus|osum|osa|ica)$', e).group(1)} (A&G 241-249)"
    return 'held', '', '', '', 'not identified in Lewis & Short or LSJ, and no compound parse'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--protonyms', required=True)
    ap.add_argument('--pos-form', required=True)
    ap.add_argument('--patronyms', required=True)
    ap.add_argument('--ls', required=True)
    ap.add_argument('--lsj', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--write-input')
    ap.add_argument('--sheet', help="held rows that need Brian's decision (spelling, recorded values, compounds)")
    a = ap.parse_args()

    parser = Parser(a.ls, a.lsj)
    lsj_keys = parser.gr_keys
    prot = read_tsv(a.protonyms)
    posf = {r['protonym_id']: r for r in read_tsv(a.pos_form)}
    patr = {r['protonym_id']: r for r in read_tsv(a.patronyms)}

    rows, counts = [], collections.Counter()
    for p in prot:
        pid, ep = p['protonym_id'], p['epithet']
        ety = p['etymology_taxt']
        der = ''
        if pid in posf:
            f = posf[pid]
            queue = 'Q2'
            if f['result'] == 'proposed':
                rule, pos, basis, status, ev = f['rule'], 'adjective', f['basis'], 'demonstrated', f['rule']
            else:
                rule, pos, basis, status, ev = 'held', '', '', '', f['reason']
        elif pid in patr and patr[pid]['level'] != 'not this queue':
            f = patr[pid]
            queue = 'Q3'
            if f['level'] in ('demonstrated', 'reasonably inferred'):
                rule, pos = 'patronym_genitive', 'noun_in_genitive_case'
                basis = 'author_stated' if re.search(r'genitive', ety, re.I) else 'grammatical_form'
                status = 'demonstrated' if f['level'] == 'demonstrated' else 'reasonably_inferred'
                ev = f"{f['formation']}; {f['evidence']}: {f['person']}"
                clean_person = re.fullmatch(r"(?:(?:de|da|del|van|von|der|la|le|d’|d')\s?)*[A-ZÀ-Ý][A-Za-zÀ-ÿ’'\-]+", f['person'] or '')
                # the weakest evidence (a collector elsewhere in AntCat) supports the part of speech, not a public
                # derivation (audit 15 Nov: 5 of 14 such persons named on the description pages, against 76 of 109
                # for the collector of the name's own type material)
                strong = f['evidence'] in ("collector of this name's type material", 'author in AntCat')
                if f['level'] == 'reasonably inferred' and not ety.strip() and clean_person and strong:
                    ending = re.search(r'(orum|arum|ii|ae|i)$', fold(ep)).group(1)
                    der = f"Personal name: formed as the genitive (Latin <i>-{ending}</i>) of the surname {f['person']}."
            else:
                rule, pos, basis, status, ev = 'held', '', '', '', f['reason']
        else:
            queue = 'Q4/Q5'
            rule, pos, basis, status, ev = q4(parser, lsj_keys, ep, p['locality'])
            if rule != 'held' and pos in ('adjective', 'participle') and NOUN_STATEMENT.search(ety) and not ADJ_STATEMENT.search(ety):
                rule, ev = 'held', 'the published etymology calls it a noun; the form is adjectival (note first): ' + ev
        if rule != 'held':
            if p['part_of_speech'] not in ('', pos):
                rule, ev = 'held', f"part of speech recorded as {p['part_of_speech']}, proposal {pos}: " + ev
            elif p['interpretation_status'] in ('disputed', 'unresolved'):
                rule, ev = 'held', f"interpretation is {p['interpretation_status']}"
        if rule == 'held':
            pos = basis = status = der = ''
        counts[(queue, rule, status)] += 1
        rows.append(dict(protonym_id=pid, protonym_name=p['protonym_name'], author_citation=p['author_citation'],
                         year=p['year'], epithet=ep, recorded_pos=p['part_of_speech'], queue=queue, rule=rule,
                         part_of_speech=pos, basis=basis, status=status, derivation=der, evidence=ev,
                         locality=p['locality']))

    cols = list(rows[0].keys())
    with open(a.out, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter='\t', lineterminator='\n')
        w.writeheader()
        w.writerows(rows)
    if a.write_input:
        with open(a.write_input, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh, delimiter='\t', lineterminator='\n', quoting=csv.QUOTE_NONE, escapechar='\\')
            w.writerow(['protonym_id', 'protonym_name', 'rule', 'field', 'value', 'locality_md5'])
            for r in rows:
                if r['rule'] == 'held':
                    continue
                md5 = ''
                if r['rule'] == 'toponym_anus_pos':
                    md5 = hashlib.md5(re.sub(r'[\t\r\n]+', ' ', r['locality']).encode('utf-8')).hexdigest()
                for field, value in [('gender_agreement_type', r['part_of_speech']), ('part_of_speech_basis', r['basis']),
                                     ('interpretation_status', r['status']), ('etymology_derivation', r['derivation'])]:
                    if value:
                        w.writerow([r['protonym_id'], r['protonym_name'], r['rule'], field, value, md5])
    decision = re.compile(r'changed ending|noun-final compound|both a Latin adjective|proper noun \(|calls it a noun|part of speech '
                          r'recorded|place name of the type locality|recorded as')
    if a.sheet:
        with open(a.sheet, 'w', newline='', encoding='utf-8') as fh:
            w = csv.writer(fh, delimiter='\t', lineterminator='\n')
            w.writerow(['protonym_id', 'protonym_name', 'author_citation', 'epithet', 'recorded_pos', 'queue', 'reason',
                        'brian_decision'])
            for r in sorted((r for r in rows if r['rule'] == 'held' and decision.search(r['evidence'])),
                            key=lambda r: (r['evidence'].split(':')[0], r['evidence'].split(';')[-1][-25:], r['epithet'])):
                w.writerow([r['protonym_id'], r['protonym_name'], r['author_citation'], r['epithet'], r['recorded_pos'],
                            r['queue'], r['evidence'], ''])
    for k in sorted(counts):
        print(f'{counts[k]:6d}  {k[0]:5s} {k[1]:30s} {k[2]}')
    print('protonyms', len(rows), 'proposed', sum(1 for r in rows if r['rule'] != 'held'))


if __name__ == '__main__':
    main()
