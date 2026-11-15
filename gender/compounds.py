#!/usr/bin/env python3
"""
compounds.py -- parse a compound epithet into its elements and read its final element (queues Q4 and Q5; AntCat
policy on name grammar and spelling, Rule 1.6: "A compound's part of speech cannot be assigned by a blanket
suffix rule. The final element, the actual word formed, its grammatical ending, and the original evidence are
evaluated together.").

Elements come from Lewis & Short and Liddell-Scott-Jones (gender/lexicon.py indexes) plus the prefixes and
combining forms below. For the final element the parser reports one of:
  adjective-final      the final element is itself an adjective or participle form (basi + spinosus, rufi + pes?
                       no: pes is a noun) -> the compound is an adjective
  adjectival-from-noun the final element is a noun stem with an adjectival ending that is not the noun's own
                       nominative (longi + cornis from cornu; crassi + noda from nodus; lati + ceps from caput) ->
                       adjective (Rule 1.6: an ending that can only be adjectival in the identified construction)
  noun-final           the ending is the noun's own nominative (crassi + spina; rufi + nodus): not evidence of an
                       adjective by itself (Rule 1.6) -> Brian, with the evidence, unless a decision is on record
  one-termination      -pes, -dens, -color, -frons, -ceps: Latin adjectives of one termination (bipes, bidens,
                       bicolor, bifrons, anceps); spelling invariable either way
  derived-adjective    no dictionary form, but a Latin stem with an adjective-forming suffix (-osus, -atus,
                       -alis, -aris, -ilis, -ivus, -eus, -aceus; A&G sect. 241-249) -> adjective, reasonably inferred
  not parsed
Poultney 1953 (AJP 74: 367): Latin compound adjectives from noun stems take -us/-a/-um (Type A) or -is/-e (Type B).
"""
import os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lexicon import fold, load, lookup  # noqa: E402

PREFIXES = ['sub', 'super', 'semi', 'prae', 'pro', 'post', 'ante', 'inter', 'intra', 'extra', 'trans', 'circum',
            'uni', 'bi', 'tri', 'quadri', 'quinque', 'sex', 'multi', 'pluri', 'omni', 'per', 'ob', 'in', 'con', 'dis',
            'ex', 'de', 'ad', 're', 'hemi', 'poly', 'oligo', 'eu', 'dys', 'pseudo', 'para', 'meta', 'epi', 'hypo',
            'hyper', 'pan', 'iso', 'homo', 'hetero', 'mono', 'di', 'a', 'an', 'micro', 'macro', 'mega', 'megalo']
# final elements formed from a noun, with the noun and its own nominative endings (Latin, or Latinized Greek)
NOUN_FINALS = {
    'cornis': ('cornu', 'horn', ()), 'cornus': ('cornu', 'horn', ()), 'ceps': ('caput', 'head', ()),
    'pes': ('pes', 'foot', ('pes',)), 'dens': ('dens', 'tooth', ('dens',)), 'color': ('color', 'colour', ('color',)),
    'formis': ('forma', 'shape', ()), 'frons': ('frons', 'forehead', ('frons',)),
    'nodis': ('nodus', 'knot, node', ()), 'nodus': ('nodus', 'knot, node', ('nodus',)),
    'noda': ('nodus', 'knot, node', ()), 'nodum': ('nodus', 'knot, node', ()),
    'spinis': ('spina', 'thorn, spine', ()), 'spina': ('spina', 'thorn, spine', ('spina',)),
    'spinus': ('spina', 'thorn, spine', ()), 'spinum': ('spina', 'thorn, spine', ()),
    'scapus': ('scapus', 'shaft', ('scapus',)), 'scapa': ('scapus', 'shaft', ()), 'scapum': ('scapus', 'shaft', ()),
    'cephalus': ('kephale (Greek)', 'head', ()), 'cephala': ('kephale (Greek)', 'head', ()),
    'cephalum': ('kephale (Greek)', 'head', ()), 'gnathus': ('gnathos (Greek)', 'jaw', ('gnathus',)),
    'gnatha': ('gnathos (Greek)', 'jaw', ()), 'gnathum': ('gnathos (Greek)', 'jaw', ()),
    'notus': ('notos/notum', 'back', ('notus', 'notum')), 'nota': ('nota', 'mark', ('nota',)),
    'notum': ('notum', 'back', ('notum',)), 'ura': ('oura (Greek)', 'tail', ('ura',)), 'urus': ('oura (Greek)', 'tail', ()),
    'gaster': ('gaster (Greek)', 'belly', ('gaster',)), 'gastra': ('gaster (Greek)', 'belly', ()),
    'gastrum': ('gaster (Greek)', 'belly', ()), 'gastrus': ('gaster (Greek)', 'belly', ()),
    'ventris': ('venter', 'belly', ()), 'ventre': ('venter', 'belly', ()), 'ops': ('ops (Greek)', 'eye, face', ('ops',)),
    'oides': ('eidos (Greek)', 'form', ()), 'pterus': ('pteron (Greek)', 'wing', ()), 'ptera': ('pteron (Greek)', 'wing', ()),
    'soma': ('soma (Greek)', 'body', ('soma',)), 'cola': ('colo (verb)', 'dweller', ('cola',)), 'colus': ('colo (verb)', 'dweller', ()),
    'fer': ('fero (verb)', 'bearing', ()), 'fera': ('fero (verb)', 'bearing', ()), 'ferum': ('fero (verb)', 'bearing', ()),
    'ger': ('gero (verb)', 'bearing', ()), 'gera': ('gero (verb)', 'bearing', ()), 'gerum': ('gero (verb)', 'bearing', ()),
}
# Latin compounds in -pes, -dens, -color, -frons, -ceps are one-termination adjectives (bipes, bidens, bicolor,
# bifrons, anceps in Lewis & Short): the spelling never changes, whatever the reading
ONE_TERMINATION = {'pes', 'dens', 'color', 'frons', 'ceps'}
ENDINGS = r'(us|a|um|is|e|er|ra|rum|os|on|es|ys|x|s)$'


class Parser:
    def __init__(self, ls_index, lsj_index):
        self.ls = load(ls_index)
        self.gr_stems, self.gr_keys, self.gr_noun_stems = {}, {}, {}
        import csv
        with open(lsj_index, encoding='utf-8', newline='') as fh:
            for r in csv.DictReader(fh, delimiter='\t'):
                if len(r['stem']) >= 3:
                    self.gr_stems.setdefault(r['stem'], r)
                    if r['kind'] == 'noun':
                        self.gr_noun_stems.setdefault(r['stem'], r)
                self.gr_keys.setdefault(r['key'], []).append(r)
        self.la_stems, self.noun_stems = {}, {}
        for key, rs in self.ls.items():
            for r in rs:
                if r['kind'] in ('adjective', 'noun', 'participle', 'verb'):
                    st = re.sub(ENDINGS, '', key)
                    stems = {st}
                    if r['kind'] == 'adjective' and key.endswith('er'):
                        stems.add(key[:-2] + 'r')  # niger -> nigr, ruber -> rubr (nigricornis)
                    gen = (fold(r['itype']).split() or [''])[0].strip(' ,.;')
                    # oblique stem from the genitive (femur, oris -> femor; pecten, inis -> pectin; pes, pedis -> ped)
                    if r['kind'] == 'noun' and re.fullmatch(r'[a-z]{2,7}is', gen):
                        stems.add(gen[:-2] if gen[0] == key[0] and len(gen) > 4 else key[:-2] + gen[:-2])
                    for st in stems:
                        if len(st) >= 3 and (st not in self.la_stems or
                                             (r['kind'] == 'adjective' and self.la_stems[st]['kind'] != 'adjective')):
                            self.la_stems[st] = r
                        if r['kind'] == 'noun':
                            self.noun_stems.setdefault(st, r)

    def first_part(self, a):
        """Identify a combining form (with its connecting vowel), or a prefix, possibly two."""
        if a in PREFIXES:
            return [(a, 'prefix')]
        for core in (a[:-1] if a.endswith(('i', 'o')) else None, a):
            if core and len(core) >= 3:
                if core in self.la_stems:
                    r = self.la_stems[core]
                    return [(a, f"Latin {r['headword']} ({r['kind']}): {r['gloss'][:40]}")]
                if core in self.gr_stems:
                    r = self.gr_stems[core]
                    return [(a, f"Greek {r['headword']} ({r['kind']}): {r['gloss'][:40]}")]
        for p in sorted(PREFIXES, key=len, reverse=True):
            if a.startswith(p) and len(a) - len(p) >= 3:
                rest = self.first_part(a[len(p):])
                if rest:
                    return [(p, 'prefix')] + rest
        return []

    def parse(self, epithet):
        e = fold(epithet)
        for v in (e, e.replace('y', 'i'), re.sub(r'([^a])e', r'\1ae', e, count=1) if 'se' in e else e):
            res = self._parse(v)
            if res:
                return res
        return None

    def _parse(self, e):
        best = None
        for i in range(2, len(e) - 2):
            a, b = e[:i], e[i:]
            if b in NOUN_FINALS:
                noun, gloss, own = NOUN_FINALS[b]
                if b in ONE_TERMINATION:
                    kind = 'one-termination'
                else:
                    kind = 'noun-final' if b in own else 'adjectival-from-noun'
                final = f'{b} from {noun}, {gloss!r}'
            elif len(b) < 5:
                continue  # short Latin words (anus, ana) give false splits: cub + anus
            elif any(g['kind'] == 'noun' for g in self.gr_keys.get(b, [])):
                g = next(g for g in self.gr_keys[b] if g['kind'] == 'noun')
                kind, final = 'noun-final', f"Greek {g['headword']} (noun, Latinized nominative): {g['gloss'][:40]}"
            elif self.noun_formation(b):
                kind, final = self.noun_formation(b)
            else:
                rs = [r for r in lookup(self.ls, b) if r['kind'] in ('adjective', 'participle')]
                gr = [r for r in self.gr_keys.get(b, []) if r['kind'] == 'adjective']
                if rs:
                    kind, final = 'adjective-final', f"Latin {rs[0]['headword']} ({rs[0]['kind']}): {rs[0]['gloss'][:40]}"
                elif gr:
                    kind, final = 'adjective-final', f"Greek {gr[0]['headword']} (adjective): {gr[0]['gloss'][:40]}"
                else:
                    continue
            first = self.first_part(a)
            if not first:
                continue
            cand = (kind, a, b, first, final)
            if best is None or len(b) > len(best[2]):
                best = cand
        if best is None:
            best = self.derived_adjective(e)
        return best

    def noun_formation(self, b):
        """A final element built on a Latin noun: Type B -is/-e (fusci + pennis from penna) or Type A -us/-a/-um
        with an ending other than the noun's own (crassi + noda from nodus): adjectival; the noun's own nominative:
        noun-final."""
        for end in ('is', 'e', 'us', 'a', 'um'):
            if b.endswith(end) and len(b) - len(end) >= 3:
                st = b[: -len(end)]
                r = self.noun_stems.get(st)
                if not r and st in self.gr_noun_stems and end in ('is', 'us', 'a', 'um'):
                    g = self.gr_noun_stems[st]  # Greek noun stem with a Latin adjectival ending (longi + tarsis)
                    if g['key'] == b:
                        return 'noun-final', f"Greek {g['headword']} (noun, Latinized nominative): {g['gloss'][:40]}"
                    return 'adjectival-from-noun', f"Greek {g['headword']} (noun) with the adjectival ending -{end}: {g['gloss'][:40]}"
                if not r:
                    continue
                own = fold(r['headword'])
                if own == b:
                    return 'noun-final', f"Latin {r['headword']} (noun, its own nominative): {r['gloss'][:40]}"
                if not self.ls.get(b):
                    return 'adjectival-from-noun', f"Latin {r['headword']} (noun) with the adjectival ending -{end}: {r['gloss'][:40]}"
        return None

    DERIVING = ['iformis', 'aceus', 'osus', 'osa', 'osum', 'atus', 'ata', 'atum', 'itus', 'ita', 'itum', 'alis', 'ale',
                'aris', 'are', 'ilis', 'ile', 'ivus', 'iva', 'ivum', 'eus', 'ea', 'eum', 'ulatus', 'ellus', 'ella']

    def derived_adjective(self, e):
        """A Latin noun or adjective stem with an adjective-forming suffix (A&G sect. 241-249): rugul + osus."""
        for suf in sorted(self.DERIVING, key=len, reverse=True):
            if e.endswith(suf) and len(e) - len(suf) >= 3:
                stem = e[: -len(suf)]
                for core in (stem, stem.rstrip('i'), stem + 'a', stem + 'u'):
                    r = self.la_stems.get(core) or self.la_stems.get(core.rstrip('e'))
                    if r and r['kind'] in ('noun', 'adjective'):
                        return ('derived-adjective', stem, suf, [(stem, f"Latin {r['headword']} ({r['kind']}): {r['gloss'][:40]}")],
                                f'-{suf}, adjective-forming suffix')
                first = self.first_part(stem)
                if first:
                    return ('derived-adjective', stem, suf, first, f'-{suf}, adjective-forming suffix')
        return None


if __name__ == '__main__':
    p = Parser(sys.argv[1], sys.argv[2])
    for w in sys.argv[3:]:
        print(w, p.parse(w))
