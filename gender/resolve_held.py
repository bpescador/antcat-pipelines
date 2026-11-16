#!/usr/bin/env python3
"""
resolve_held.py -- decides the names gender/propose_all.py holds, from the evidence, without a sheet for Brian
(Brian, 16 Nov 2026 10:40: "I can't review all these names: you have to use insect knowledge: refer to TW ...,
the ocr of the literature ..., the pdfs in Background reading for ICZN ... we may only offer a wiki for the
difficult ones where the issues are presented but not resolved"). Read only.

Order of evidence for each protonym with no part of speech on production:
  1. What the original description says (gender/extract_stated_grammar.py, and the etymology already in AntCat):
     "noun in apposition", "adjective", "arbitrary combination", a dedication with a genitive ending. An author's
     noun is followed unless the form is a Latin adjective that would have to agree (policy Rule 1.1, the Chelaner
     precedent): those go to the wiki list with both readings.
  2. propose_all.py's own proposal (dictionary, compound parser).
  3. For held names, the defaults the Code and AntCat's adopted reading of it give (Art. 31.2.2 as read by David &
     Gosselin 2011, policy Rules 1.5 and 1.6), and word-by-word judgments recorded in the tables below:
       - a compound whose final element is a noun in its own nominative (crassi + spina): noun in apposition by
         default; D&G: a newly derived name is a noun in apposition unless the original work indicates an adjective
       - a Latin word that is an adjective or participle and also spells a noun: the adjective where the noun is
         only the participle's verbal noun or an unrelated homonym (ornatus, latus, striata; birds decline them
         too); noun in apposition by default where the noun is a natural reading (faber, gibber, merula; D&G 2011,
         mercenarius, vicinus, vidua)
       - a noun stem given another gender ending (castaneus, ophthalmica): the adjective where the formation is a
         known one; otherwise unresolved
       - proper nouns (Hector, Pythia, Syria): noun in apposition by default
       - place names used unchanged (mindanao, papua): noun in apposition
  4. A name decided as a noun whose accepted spelling differs from the original is never written: an Art. 33
     question (wiki list). An adjective whose ending changed with its genus is ordinary agreement (Art. 34.2).

Outputs (--out-dir): write_input.tsv (for gender/write_protonym_fields.rb), corrections.tsv (for
gender/correct_protonym_fields.rb: values on production the evidence contradicts), wiki_list.tsv (difficult names,
by issue, with the evidence), unresolved.tsv (no evidence yet), decisions.tsv (everything, with the reason).
"""
import argparse, collections, csv, difflib, os, re, sys, unicodedata

csv.field_size_limit(sys.maxsize)

GEN_END = re.compile(r'(i|ae|orum|arum)$')
RANK_WORD = re.compile(r'\b(var|subsp|st|r|f|ssp|morph|ab|n|natio|forma|subvar)\.')

# ---- word-by-word judgments (16 Nov 2026) --------------------------------------------------------------------
# Latin words that are an adjective or participle and also spell a noun. Listed: the noun is a natural reading, so
# Art. 31.2.2 applies (noun in apposition by default). Not listed: the adjective (reasonably inferred).
BOTH_NOUN = {'aquila', 'belua', 'collare', 'confinium', 'electrum', 'jugum', 'spiculum', 'mina', 'ruta', 'anathema', 'araneolus', 'catella', 'congener', 'cunicularius', 'faber', 'gibber', 'inquilinus',
             'lucifuga', 'ludius', 'merula', 'moera', 'nacta', 'notula', 'parens', 'praefectus', 'rosula', 'umbra',
             'terrigena', 'occasus'}
BOTH_UNRESOLVED = {'liber': 'liber "free" (adjective, libera) or liber "book" (noun): Podomyrma libra, 12 Nov'}
# A Latin noun stem with another ending. A = an adjective formation (castaneus -a -um, ophthalmicus, cryptus from
# Greek kryptos, -arius); N = in fact a proper or non-Latin noun, the Latin match is chance; others unresolved.
ALTERED = {
    'castaneus': 'A', 'castanea': 'A', 'castaneum': 'A', 'cryptus': 'A', 'crypta': 'A', 'retiaria': 'A',
    'cunicularia': 'A', 'ophthalmica': 'A', 'ophthalmicum': 'A', 'ophthalmicus': 'A', 'falcaria': 'A',
    'androgyna': 'A', 'salina': 'A', 'salinus': 'A', 'nanum': 'A', 'callima': 'A', 'melanura': 'A',
    'leucacanthus': 'A', 'decanica': 'A', 'plagiaria': 'A', 'defensus': 'A', 'celata': 'A', 'icterica': 'A',
    'inca': 'N', 'attila': 'N', 'nimba': 'N', 'valerius': 'N',
}
ALTERED_NOTE = {'inca': 'the Inca (a non-Latin proper noun); the Latin incus is chance',
                'attila': 'Attila (a proper noun)', 'nimba': 'Mount Nimba (a place name used unchanged)',
                'valerius': 'Valerius (a Roman name)'}
# Proper nouns beside a Greek or Latin adjective. A = the adjective is the reading (the proper noun is an obscure
# homonym); everything else: noun in apposition by default (Art. 31.2.1, 31.2.2).
PROPER_ADJ = {'badia': 'badius, chestnut-brown; Badia is an obscure town', 'aquilonia': 'aquilonius, northern',
              'varia': 'varius, variegated'}
# Place names: the feminine of a Latin geographical adjective (Corsicus, argentinus; D&G 2011 on martinica,
# senegallus) against place names used unchanged.
PLACE_ADJ = {'corsica', 'argentina'}
# Compound finals the parser reads as nouns but that are not, or cannot be read (left unresolved).
FINAL_UNRESOLVED = {'culus', 'stenus', 'melus', 'menus', 'lenus', 'theria', 'gonia', 'genus', 'idalis', 'nastes',
                    'moschus', 'laeum', 'telis', 'cratis', 'cerea', 'acula', 'xenus', 'epixenus'}
EPITHET = {  # epithet: (part of speech, basis, status, reason)
    'aristotelis': ('noun_in_genitive_case', 'grammatical_form', 'reasonably_inferred', 'genitive of Aristoteles'),
    'cleopatra': ('noun_in_apposition', 'noun_by_default', 'reasonably_inferred', 'Cleopatra (a proper noun)'),
    'andromache': ('noun_in_apposition', 'noun_by_default', 'reasonably_inferred', 'Andromache (a proper noun)'),
    'monomorium': ('noun_in_apposition', 'noun_by_default', 'reasonably_inferred', 'the genus name Monomorium'),
    'crassiculus': ('adjective', 'grammatical_form', 'reasonably_inferred', 'diminutive of the adjective crassus'),
    'imberbiculus': ('adjective', 'grammatical_form', 'reasonably_inferred', 'diminutive of the adjective imberbis'),
    'soriculus': ('noun_in_apposition', 'noun_by_default', 'reasonably_inferred', 'diminutive of sorex, a shrew'),
    'discoidalis': ('adjective', 'grammatical_form', 'reasonably_inferred', 'adjective in -alis'),
    'haemorrhoidalis': ('adjective', 'grammatical_form', 'reasonably_inferred', 'adjective in -alis'),
    'sphenoidalis': ('adjective', 'grammatical_form', 'reasonably_inferred', 'adjective in -alis'),
    'nigrocerea': ('adjective', 'grammatical_form', 'reasonably_inferred', 'nigro + cereus, waxen'),
    'atticola': ('noun_in_apposition', 'noun_by_default', 'reasonably_inferred', 'Atta + -cola, a dweller with Atta'),
    'andinus': ('adjective', 'grammatical_form', 'reasonably_inferred', 'of the Andes, with the suffix -inus'),
    'atrocastanea': ('adjective', 'grammatical_form', 'reasonably_inferred', 'atro + castaneus, chestnut-brown'),
    'hemipsila': ('adjective', 'grammatical_form', 'reasonably_inferred', 'hemi + Greek psilos, bare'),
    'desupra': ('noun_in_apposition', 'noun_by_default', 'reasonably_inferred',
                'a Latin adverb ("from above"): treated as a noun in apposition (Art. 11.9.1)'),
    # 16 Nov, read before production: finals the parser took for nouns (Greek phora "an act", oura, chyma, cheima)
    # are the feminines of Latinized Greek adjectives; spongia, bilis and Molossus are nouns in their own right.
    'eriophora': ('adjective', 'grammatical_form', 'reasonably_inferred',
                  'Greek eriophoros, wool-bearing (LSJ), Latinized -phorus, -a, -um (as -ferus)'),
    'selenophora': ('adjective', 'grammatical_form', 'reasonably_inferred',
                    'seleno + -phora, moon-bearing: the feminine of a Latinized Greek adjective in -phorus (as -ferus)'),
    'micrura': ('adjective', 'grammatical_form', 'reasonably_inferred',
                'micr + -ura, small-tailed: the feminine of a Latinized Greek adjective in -urus (as melanura, chrysurus)'),
    'cacochyma': ('adjective', 'grammatical_form', 'reasonably_inferred',
                  'Greek kakochymos, with bad juices (as eu-, dys-, polychymos in LSJ), Latinized -us, -a, -um'),
    'dyschima': ('adjective', 'grammatical_form', 'reasonably_inferred',
                 'Greek dyschimos, troublesome, fearful (LSJ), Latinized -us, -a, -um'),
    'clasmospongia': ('noun_in_apposition', 'noun_by_default', 'reasonably_inferred',
                      'clasmo + spongia, a sponge: a noun in its own nominative (spongius is a rare late adjective)'),
    'subspongia': ('noun_in_apposition', 'noun_by_default', 'reasonably_inferred',
                   'sub + spongia, a sponge: a noun in its own nominative (spongius is a rare late adjective)'),
    'atrabilis': ('noun_in_apposition', 'noun_by_default', 'reasonably_inferred',
                  'atra bilis, black bile: a noun with its adjective'),
    'molossus': ('noun_in_apposition', 'noun_by_default', 'reasonably_inferred',
                 'Molossus, the Molossian hound: a noun beside the adjective (Rule 1.5)'),
}
# Names where the parser's adjective is a chance match and the author's noun is right (kava the plant, not cavus;
# Tinogasta the town; iso + electrum, the epithet of T. electrum).
AUTHOR_RIGHT = {'kava', 'tinogasta', 'isoelectrum'}
# The author calls it an adjective, but the word is not a Latin adjective: both readings go to the wiki list.
AUTHOR_ADJ_DOUBT = {'marmar': 'Old Irish, not Latinized: indeclinable under Art. 31.2.3',
                    'solitudinis': 'the genitive of the Latin noun solitudo'}
EXPLICIT_NOUN = re.compile(r'(?i)apposition|aposici|aposi[cç]|invaria|indeclin|treated as (?:a |an )?noun|must be treated as a noun')
ARBITRARY = re.compile(r'(?i)arbitrary (?:combination|arrangement|name)|random combination|combination of letters|'
                       r'nonsense|anagram')
PERSON = re.compile(r"(?:named (?:after|for|in hono[u]?r of)|dedicated to|hono[u]?r of|memory of|dedicad\w+ a|"
                    r"homenagem (?:a|à|ao)|zu ehren|patronym \w+ to|hono[u]?rs)\s+(?:[a-zà-ÿ’'.,-]+\s+){0,7}[A-Z]")
OTHER_NAME = re.compile(r'^\W*[A-Z]\.\s+([a-z]{4,})\b')
SAYS_GENITIVE = re.compile(r'(?i)genitiv|patronym|matronym')
# Matches that are chance (a Malagasy or Spanish word, a place): left unresolved.
CHANCE = {'insutura', 'anjara', 'sisypha', 'chamela', 'palta', 'theia', 'megalocola', 'euryscopa'}
ONE_TERMINATION = re.compile(r'(ceps|pes|dens|color|frons|ax|ex|ix|ox|ops|ans|ens)$')

ADJ_STATEMENT = re.compile(
    r'(?i)\b(is|as|are|being|treated as|used as|regarded as)\s+(?:an?\s+)?(?:\w+\s+){0,2}adjectiv|adjectival|'
    r'\(adjective\)|adjective\s+(?:in|agree)|adjetivo\b|adjektiv\b')
NOUN_WORD = re.compile(r'(?i)\bnoun|\bsubstantiv|\bsustantiv|apposition')


def fold(s):
    s = unicodedata.normalize('NFKD', s)
    return ''.join(c for c in s if not unicodedata.combining(c)).lower()


def read(path, quoting=csv.QUOTE_MINIMAL):
    with open(path, encoding='utf-8', newline='') as fh:
        return list(csv.DictReader(fh, delimiter='\t', quoting=quoting))


def classify(text):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from extract_stated_grammar import STATED
    return {name for name, rx in STATED if rx.search(text)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--proposals', required=True)
    ap.add_argument('--pages', required=True)
    ap.add_argument('--stated', required=True)
    ap.add_argument('--genus-gender', required=True)
    ap.add_argument('--written', nargs='+', required=True, help='write inputs applied on production')
    ap.add_argument('--corrections', nargs='*', default=[], help='correction inputs applied on production')
    ap.add_argument('--out-dir', required=True)
    a = ap.parse_args()

    P = {r['protonym_id']: r for r in read(a.proposals)}
    PP = {r['protonym_id']: r for r in read(a.pages, csv.QUOTE_NONE)}
    gender = {}
    for r in read(a.genus_gender):
        if r['gender']:
            gender.setdefault(r['name'].split()[-1].strip('()'), r['gender'])
    prod = collections.defaultdict(dict)   # what production holds, by field
    for pid, p in PP.items():
        if p['part_of_speech']:
            prod[pid] = {'gender_agreement_type': p['part_of_speech'], '_entered': True}
    for path in a.written:
        for r in read(path):
            prod[r['protonym_id']].setdefault(r['field'], r['value'])
    for path in a.corrections:
        for r in read(path):
            if r['action'] == 'revert':
                prod[r['protonym_id']].pop(r['field'], None)
            else:
                prod[r['protonym_id']][r['field']] = r['new_value']

    # --- 1. statements in the original description
    by_ref = collections.defaultdict(set)
    for p in PP.values():
        by_ref[p['authorship_reference_id']].add(fold(p['epithet']))
    def later_work(p):
        """the etymology recorded in AntCat cites a work other than the original description (a reviser's table,
        a later catalogue): what it says is not the author's statement. Monomorium kiliani Forel 1902 and leae
        Forel 1913 were read as "author: noun in apposition" from a 2019 table (16 Nov, found before production)."""
        cited = set(re.findall(r'\{ref (\d+)\}', p['etymology_taxt']))
        if p['etymology_reference_id']:
            cited.add(p['etymology_reference_id'])
        return bool(cited - {p['authorship_reference_id']})

    stated = {}
    for r in read(a.stated):
        pid = r['protonym_id']
        flags = set(filter(None, r['stated'].split(';')))
        text = fold(r['passage'])
        ep = fold(r['epithet'])
        sisters = [e for e in by_ref[PP[pid]['authorship_reference_id']] if e != ep and len(e) > 4 and
                   re.search(r'\b' + re.escape(e) + r'\b', text)]
        reliable = bool(r['epithet_in_passage']) or (r['confidence'] in ('A', 'B') and not sisters)
        if sisters and not r['epithet_in_passage']:
            reliable = False
        m = OTHER_NAME.match(r['passage'])
        if m and fold(m.group(1)) != ep:
            reliable = False  # the passage opens with another species' name ("C. flavopectus derives from ...")
        stated[pid] = (flags, r['passage'], reliable, 'original description, PDF page ' + r['passage_page'])
    for pid, p in PP.items():
        if p['etymology_taxt'] and not later_work(p):
            stated[pid] = (classify(p['etymology_taxt']), p['etymology_taxt'], True, 'etymology recorded in AntCat')

    def original_genus(p):
        return p['protonym_name'].split()[0]

    def changed(p):
        cur = p['terminal_taxon_name'].split()[-1] if p['terminal_taxon_name'] else ''
        return cur if cur and fold(cur) != fold(p['epithet']) else ''

    def adjectival_form(r):
        """the proposal reads the form, with good evidence, as a Latin or Latinized adjective or participle that
        must agree. A chance dictionary match (kava for cavus) or a noun stem with another ending (semi + capillum)
        is not good evidence against an author who calls the name a noun."""
        ep = fold(r['epithet'])
        if ep in AUTHOR_RIGHT:
            return False
        if r['rule'] in ('ensis_form_pos', 'toponym_ensis_pos', 'toponym_anus_pos', 'place_adjective_pos',
                         'suffix_form_pos', 'greek_form_pos'):
            return True
        if r['rule'] == 'latin_form_pos':
            head = fold(r['evidence'].split(' (')[0]).replace('j', 'i').replace('v', 'u').replace('-', '')
            return head[:1] == ep.replace('j', 'i').replace('v', 'u')[:1]
        if r['rule'] == 'compound_adjective_pos':
            ev = r['evidence']
            return ev.startswith(('adjective-final', 'derived-adjective')) or \
                (ev.startswith('adjectival-from-noun') and ' with the adjectival ending' not in ev)
        return False

    decisions = []

    def decide(pid, kind, pos='', basis='', status='', rule='', reason=''):
        decisions.append({'protonym_id': pid, 'protonym_name': PP[pid]['protonym_name'], 'epithet': PP[pid]['epithet'],
                          'year': PP[pid]['year'], 'current_name': PP[pid]['terminal_taxon_name'], 'decision': kind,
                          'part_of_speech': pos, 'basis': basis, 'status': status, 'rule': rule, 'reason': reason,
                          'production': prod[pid].get('gender_agreement_type', '')})

    for pid, r in P.items():
        p = PP[pid]
        ep = fold(p['epithet'])
        have = prod[pid].get('gender_agreement_type')
        flags, passage, reliable, where = stated.get(pid, (set(), '', False, ''))
        quote = f'{where}: "{passage[:260]}"' if passage else ''
        # "a noun in the genitive case" (loarelae), "genitive ... standing in apposition" (trinacriae), "a patronymic
        # ... treated as a noun in apposition" (Adetomyrma bressleri): a genitive, whatever else is said
        says_genitive = bool(reliable and GEN_END.search(ep) and SAYS_GENITIVE.search(passage))
        says_noun = reliable and 'noun_in_apposition' in flags and not says_genitive and \
            (EXPLICIT_NOUN.search(passage) or not GEN_END.search(ep))   # "Non-Latin noun" on claveri is no apposition
        says_adj = (reliable and 'adjective' in flags and not says_noun and ADJ_STATEMENT.search(passage) and
                    not NOUN_WORD.search(passage))
        # "arbitrary combination" must be said of the species name, not of the genus in the same paragraph
        says_arbitrary = reliable and 'arbitrary' in flags and not GEN_END.search(ep) and any(
            ARBITRARY.search(x) and not re.search(r'(?i)\bgenus\b|\bgeneric\b', x) for x in re.split(r'(?<=[.;])\s+', passage))
        ch = changed(p)

        # --- names with a value on production: only contradictions are reported
        if have:
            if prod[pid].get('_entered'):
                continue  # entered by a person before this work: never touched
            if says_noun and have not in ('noun_in_apposition', 'indeclinable'):
                if have in ('adjective', 'participle') and adjectival_form(r) and r['rule'] != 'held':
                    decide(pid, 'wiki', have, '', '', '', 'author_noun_form_adjective: recorded ' + have +
                           ' (the form agrees, policy Rule 1.1); the author calls it a noun in apposition. ' + quote)
                else:
                    decide(pid, 'correct', 'noun_in_apposition', 'author_stated', 'demonstrated', '',
                           f'recorded {have}; the author calls it a noun in apposition. ' + quote)
            elif (have in ('adjective', 'participle') and ep in BOTH_NOUN and
                  r['evidence'].startswith('both a Latin adjective and a noun')):
                if ch:
                    decide(pid, 'wiki', have, '', '', '', f'noun_spelling_changed: recorded {have}; a Latin noun in its '
                           f'own right; accepted spelling {ch}: ' + r['evidence'][80:200])
                else:
                    decide(pid, 'correct', 'noun_in_apposition', 'noun_by_default', 'reasonably_inferred', '',
                           'a Latin noun in its own right beside a rare adjective; noun in apposition by default '
                           '(Art. 31.2.2): ' + r['evidence'][80:200])
            elif ep in ('osa', 'tosa', 'hybosa'):
                decide(pid, 'revert', reason='-osa on a stem of three letters or fewer is no evidence of an adjective')
            elif r['rule'] == 'held' and 'a proper noun' in r['evidence'] and have == 'adjective':
                if ep in PROPER_ADJ:
                    if prod[pid].get('interpretation_status') != 'reasonably_inferred':
                        decide(pid, 'correct', 'adjective', 'grammatical_form', 'reasonably_inferred', '',
                               'adjective (' + PROPER_ADJ[ep] + '); the proper noun is a possible alternative')
                elif ch:
                    decide(pid, 'wiki', have, '', '', '', f'proper_noun_or_adjective: recorded adjective; accepted '
                           f'spelling {ch}; also a proper noun: ' + r['evidence'][:120])
                else:
                    decide(pid, 'correct', 'noun_in_apposition', 'noun_by_default', 'reasonably_inferred', '',
                           'a proper noun as spelled; noun in apposition by default (Art. 31.2.2): ' + r['evidence'][:120])
            continue

        # --- 1. the author's statement
        if says_genitive and 'arbitrary' not in flags:
            decide(pid, 'write', 'noun_in_genitive_case',
                   'author_stated' if re.search(r'(?i)genitiv', passage) else 'grammatical_form', 'demonstrated',
                   'patronym_genitive', 'the author calls it a genitive or a patronym. ' + quote)
            continue
        if says_noun:
            if r['rule'] != 'held' and adjectival_form(r) and not ONE_TERMINATION.search(ep):
                decide(pid, 'wiki', r['part_of_speech'], '', '', '', 'author_noun_form_adjective: the form is an adjective '
                       f'({r["evidence"][:90]}); the author calls it a noun in apposition. ' + quote)
            elif ch:
                decide(pid, 'wiki', 'noun_in_apposition', '', '', '', f'noun_spelling_changed: the author calls it a noun '
                       f'in apposition; accepted spelling {ch}. ' + quote)
            else:
                decide(pid, 'write', 'noun_in_apposition', 'author_stated', 'demonstrated', 'author_stated_pos', quote)
            continue
        if says_arbitrary and r['rule'] == 'held':
            decide(pid, 'write', 'indeclinable', 'not_latin', 'demonstrated', 'author_stated_pos',
                   'an arbitrary combination of letters (Art. 31.2.3). ' + quote)
            continue
        if says_adj and r['rule'] == 'held' and (ep in AUTHOR_ADJ_DOUBT or 'genitive case' in r['evidence']):
            decide(pid, 'wiki', '', '', '', '', 'author_adjective_form_not: the author calls it an adjective; ' +
                   AUTHOR_ADJ_DOUBT.get(ep, r['evidence'][:90]) + '. ' + quote)
            continue
        if says_adj and r['rule'] == 'held' and not GEN_END.search(ep):
            decide(pid, 'write', 'adjective', 'author_stated', 'demonstrated', 'author_stated_pos', quote)
            continue
        if (reliable and flags & {'dedication', 'genitive'} and r['rule'] == 'held' and r['queue'] == 'Q3' and
                GEN_END.search(ep) and not flags & {'place'} and PERSON.search(passage)):
            names = set()
            for w in re.findall(r"\b[A-Z][\w'’-]+", passage):
                w = fold(w).replace('ł', 'l').replace('ø', 'o').replace('đ', 'd')
                names |= {w.replace('-', '').replace("'", '').replace('’', '')} | set(w.split('-'))
            stem = GEN_END.sub('', ep).rstrip('i')
            if ep in names:
                # Lasius fuji (Mount Fuji), Tetramorium kali (Kali Ressi), Strumigenys waiwai, Paraparatrechina ali
                if ch:
                    decide(pid, 'wiki', 'noun_in_apposition', '', '', '', 'noun_spelling_changed: a name used '
                           f'unchanged; accepted spelling {ch}. ' + quote)
                else:
                    decide(pid, 'write', 'noun_in_apposition', 'grammatical_form', 'reasonably_inferred',
                           'noun_by_default_pos', 'the name is used unchanged, not in the genitive: a noun in '
                           'apposition (Art. 31.1). ' + quote)
            elif any(stem == n or (len(stem) >= 3 and stem in n) or (len(n) >= 4 and n in stem) or
                     (len(stem) >= 5 and difflib.SequenceMatcher(None, stem, n).ratio() >= 0.7) for n in names):
                # Xu -> xui; T. Suman -> tsumani; Colleen -> coleenae; OCR "Tiilin" for Tülin -> tulinae
                decide(pid, 'write', 'noun_in_genitive_case', 'grammatical_form', 'demonstrated', 'patronym_genitive',
                       'a dedication with a genitive ending. ' + quote)
            else:
                decide(pid, 'unresolved', reason='a dedication, but the name behind the epithet is not in the passage. '
                       + quote)
            continue

        if ep in CHANCE:
            decide(pid, 'unresolved', reason='the dictionary match is chance: ' + r['evidence'][:150])
            continue
        # --- 2. propose_all's proposal, unless a word-by-word judgment exists
        if r['rule'] != 'held' and ep not in EPITHET:
            decide(pid, 'write', r['part_of_speech'], r['basis'], r['status'], r['rule'], r['evidence'][:200])
            continue

        # --- 3. held names
        ev = r['evidence']
        if ep in EPITHET:
            pos, basis, status, why = EPITHET[ep]
            if pos.startswith('noun') and ch:
                decide(pid, 'wiki', pos, '', '', '', f'noun_spelling_changed: {why}; accepted spelling {ch}')
            else:
                decide(pid, 'write', pos, basis, status,
                       'noun_by_default_pos' if pos.startswith('noun') else 'judged_adjective_pos', why)
        elif ev.startswith('noun-final compound'):
            final = (re.search(r'\+ (\S+?);', ev) or [None, ''])[1]
            if final in FINAL_UNRESOLVED or re.search(r'(culus|idalis)$', ep):
                decide(pid, 'unresolved', reason='compound not read with confidence: ' + ev[:150])
            elif ch:
                decide(pid, 'wiki', 'noun_in_apposition', '', '', '', f'noun_spelling_changed: a compound ending in a '
                       f'noun in its own nominative ({ev[20:110]}); accepted spelling {ch}')
            else:
                decide(pid, 'write', 'noun_in_apposition', 'noun_by_default', 'reasonably_inferred',
                       'noun_by_default_pos', 'the final element is a noun in its own nominative; nothing in the '
                       'original description indicates an adjective (Art. 31.2.2; Rule 1.6): ' + ev[20:150])
        elif ev.startswith('both a Latin adjective and a noun'):
            g = gender.get(original_genus(p), '')
            ending = 'masculine' if ep.endswith(('us', 'er')) else 'feminine' if ep.endswith('a') else \
                     'neuter' if ep.endswith('um') else ''
            mismatch = g and ending and g != ending and not RANK_WORD.search(p['protonym_name'])
            if ep in BOTH_UNRESOLVED:
                decide(pid, 'wiki', '', '', '', '', 'noun_or_adjective: ' + BOTH_UNRESOLVED[ep])
            elif mismatch and not ch and ep not in BOTH_NOUN:
                # a genuine adjective with the wrong ending (to correct, Art. 34.2) or a noun: not decided here
                decide(pid, 'wiki', '', '', '', '', f'adjective_not_agreeing: the ending is {ending}, the original '
                       f'genus {original_genus(p)} is {g}, and the spelling was never changed; adjective with an '
                       'uncorrected ending, or a noun: ' + ev[80:200])
            elif ep in BOTH_NOUN:
                why = 'a Latin noun as spelled, and an adjective; no indication in the original description'
                if ch:
                    decide(pid, 'wiki', 'noun_in_apposition', '', '', '', f'noun_spelling_changed: {why}; accepted '
                           f'spelling {ch}: ' + ev[80:200])
                else:
                    decide(pid, 'write', 'noun_in_apposition', 'noun_by_default', 'reasonably_inferred',
                           'noun_by_default_pos', why + ' (Art. 31.2.2; Rule 1.5): ' + ev[80:200])
            else:
                decide(pid, 'write', 'participle' if '(participle' in ev and '(adjective' not in ev else 'adjective',
                       'grammatical_form', 'reasonably_inferred', 'judged_adjective_pos',
                       'a Latin adjective or participle; the noun of the same spelling is its verbal noun or an '
                       'unrelated word: ' + ev[80:220])
        elif ev.startswith('a Latin noun with a changed ending'):
            k = ALTERED.get(ep)
            if k == 'A':
                decide(pid, 'write', 'adjective', 'grammatical_form', 'reasonably_inferred', 'judged_adjective_pos',
                       'an adjective formed on the noun stem (-us, -a, -um): ' + ev[36:150])
            elif k == 'N':
                decide(pid, 'write', 'noun_in_apposition', 'noun_by_default', 'reasonably_inferred',
                       'noun_by_default_pos', ALTERED_NOTE[ep])
            elif ch:
                decide(pid, 'wiki', '', '', '', '', f'noun_stem_other_ending: {ev[36:150]}; accepted spelling {ch}')
            else:
                decide(pid, 'unresolved', reason='a Latin noun stem with another gender ending; adjective or coined '
                       'noun not established: ' + ev[36:150])
        elif 'a proper noun' in ev:
            if ep in PROPER_ADJ:
                decide(pid, 'write', 'adjective', 'grammatical_form', 'reasonably_inferred', 'judged_adjective_pos',
                       'adjective (' + PROPER_ADJ[ep] + '); the proper noun is a possible alternative')
            elif ch:
                decide(pid, 'wiki', 'noun_in_apposition', '', '', '', f'proper_noun_or_adjective: accepted spelling {ch}; '
                       + ev[:140])
            else:
                decide(pid, 'write', 'noun_in_apposition', 'noun_by_default', 'reasonably_inferred',
                       'noun_by_default_pos', 'a proper noun as spelled; noun in apposition by default '
                       '(Arts. 31.2.1, 31.2.2): ' + ev[:140])
        elif 'place name of the type locality' in ev:
            if ep in PLACE_ADJ:
                decide(pid, 'write', 'adjective', 'grammatical_form', 'reasonably_inferred', 'judged_adjective_pos',
                       'the feminine of a Latin geographical adjective (Corsicus, argentinus); the place name is a '
                       'possible alternative')
            elif ch:
                decide(pid, 'wiki', 'noun_in_apposition', '', '', '', f'noun_spelling_changed: a place name; accepted '
                       f'spelling {ch}')
            else:
                decide(pid, 'write', 'noun_in_apposition', 'noun_by_default', 'reasonably_inferred',
                       'noun_by_default_pos', 'a place name used unchanged (' + p['locality'][:60] + ')')
        elif 'published etymology calls it a noun' in ev:
            taxt = f'etymology recorded in AntCat: "{p["etymology_taxt"][:260]}"'
            if later_work(p) and ONE_TERMINATION.search(ep):
                # a reviser's statement is not the author's: the Code's default, with the reviser quoted
                decide(pid, 'write', 'noun_in_apposition', 'noun_by_default', 'reasonably_inferred',
                       'noun_by_default_pos', 'a compound ending in a noun (one termination, the spelling is the same '
                       'either way); noun in apposition by default (Art. 31.2.2); a later work calls it a noun. ' + taxt)
            elif later_work(p):
                decide(pid, 'wiki', '', '', '', '', 'later_work_noun_form_adjective: ' + ev[:120] + '. ' + taxt)
            elif ONE_TERMINATION.search(ep):
                decide(pid, 'write', 'noun_in_apposition', 'author_stated', 'demonstrated', 'author_stated_pos',
                       'the author calls it a noun; an ending of one termination, so the spelling is the same either '
                       'way. ' + quote)
            else:
                decide(pid, 'wiki', '', '', '', '', 'author_noun_form_adjective: ' + ev[:120] + '. ' + quote)
        elif ev.startswith('part of speech recorded'):
            continue
        else:
            decide(pid, 'unresolved', reason=ev[:200])

    os.makedirs(a.out_dir, exist_ok=True)
    cols = ['protonym_id', 'protonym_name', 'epithet', 'year', 'current_name', 'decision', 'part_of_speech', 'basis',
            'status', 'rule', 'production', 'reason']
    def dump(name, rows):
        with open(os.path.join(a.out_dir, name), 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, cols, delimiter='\t', lineterminator='\n')
            w.writeheader()
            w.writerows(rows)
    dump('decisions.tsv', decisions)
    dump('wiki_list.tsv', sorted((d for d in decisions if d['decision'] == 'wiki'),
                                 key=lambda d: (d['reason'].split(':')[0], d['epithet'])))
    dump('unresolved.tsv', sorted((d for d in decisions if d['decision'] == 'unresolved'), key=lambda d: d['epithet']))
    with open(os.path.join(a.out_dir, 'write_input.tsv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['protonym_id', 'protonym_name', 'rule', 'field', 'value', 'locality_md5'])
        for d in decisions:
            if d['decision'] == 'write':
                for field, value in (('gender_agreement_type', d['part_of_speech']), ('part_of_speech_basis', d['basis']),
                                     ('interpretation_status', d['status'])):
                    w.writerow([d['protonym_id'], d['protonym_name'], d['rule'], field, value, ''])
    with open(os.path.join(a.out_dir, 'corrections.tsv'), 'w', newline='', encoding='utf-8') as fh:
        w = csv.writer(fh, delimiter='\t', lineterminator='\n')
        w.writerow(['protonym_id', 'protonym_name', 'action', 'field', 'written_value', 'new_value', 'reason'])
        for d in decisions:
            cur = prod[d['protonym_id']]
            if d['decision'] == 'revert':
                for f in ('gender_agreement_type', 'part_of_speech_basis', 'interpretation_status'):
                    w.writerow([d['protonym_id'], d['protonym_name'], 'revert', f, cur[f], '', d['reason'][:200]])
            elif d['decision'] == 'correct':
                for f, v in (('gender_agreement_type', d['part_of_speech']), ('part_of_speech_basis', d['basis']),
                             ('interpretation_status', d['status'])):
                    if cur.get(f) != v:
                        w.writerow([d['protonym_id'], d['protonym_name'], 'update', f, cur[f], v, d['reason'][:200]])
    c = collections.Counter(d['decision'] for d in decisions)
    print(dict(c))
    print(collections.Counter((d['rule'], d['part_of_speech'], d['status']) for d in decisions if d['decision'] == 'write'))
    print(collections.Counter(d['reason'].split(':')[0] for d in decisions if d['decision'] == 'wiki'))


if __name__ == '__main__':
    main()
