#!/usr/bin/env python3
"""
diff_history.py -- content-level ("taxonomic acts") diff, Bolton NGC vs AntCat.

The name-level diff (diff_catalogue.py) answers "what NAMES is AntCat missing".
This answers the deeper question: for names BOTH catalogues have, what taxonomic
ACTS has Bolton recorded that AntCat has not -- a synonymy, a status change, a
new combination -- and what REFERENCES does Bolton cite for an act AntCat holds
but does not cite.

IDENTITY, NOT SPELLING
Bolton records a non-valid name (junior synonym, variety, subspecies) under the
spelling it was PUBLISHED with, in its original combination. AntCat stores it
gender-agreed to the current genus:

    Bolton : propinqua.  Melophorus fieldi var. propinqua Viehmeyer, 1925a
    AntCat : name fields Melophorus fieldi propinquus
             history     Melophorus fieldi var. propinqua Viehmeyer, 1925a

Matching those as strings -- even gender-stemmed, even with an edit-distance
tolerance -- is guesswork, and it is guesswork on exactly the names Bolton
treats as non-valid. But the FIRST LINE of AntCat's `taxonomic history html` is
the protonym as published (it IS the Bolton view), so both catalogues can be
keyed on the same identity:

    PROTONYM KEY = (original genus, original terminal epithet, 4-digit year)

Every spelling AntCat holds for a name (the original, the gender-corrected
current one, misspellings, one row per obsolete combination) resolves back to
that key, so an act's TARGET is compared by identity rather than by string.

Inputs:
  bolton_out/bolton_species_blocks.jsonl   (from parse_bolton.py)
  worldants.txt                            (AntCat dump)

Outputs (diff_out/):
  history_recent_acts_to_check.csv   acts Bolton asserts that AntCat lacks (recent)
  history_all_acts_to_check.csv      the same without the recency filter
  history_by_species.csv             one row per name with a gap
  history_added_refs_to_check.csv    refs Bolton cites on an act AntCat holds
  history_suppressed_acts.csv        recent acts AntCat already encodes (audit trail)
  HISTORY_SUMMARY.txt
"""
import csv, sys, json, os, re
from collections import defaultdict
from protonym import parse_protonym, strip_html, fold, year4, authorkey
from parse_antcat import gstem, norm_genus

csv.field_size_limit(sys.maxsize)

YEARTOK = re.compile(r'(1[6789]\d\d|20\d\d)([a-z]?)\b')
SURTOK = re.compile(r"[A-Z\u00C0-\u00DE\u0100-\u017F][a-z\u00C0-\u00FF\u0100-\u017F][\w\u00C0-\u024F'’-]*")

# ---------------------------------------------------------------- citations
# Bolton cites a name published inside another author's work as "X, in Y, Z, 2024"
# (X described the taxon; Y[, Z] is the publication's authorship). AntCat renders the
# same reference by its publication author -- usually "Y et al., 2024" or just the
# first publication author. So key such a citation on the author right AFTER "in"
# (the publication's first author), which is what both catalogues share; otherwise
# Bolton's key lands on the describer or a co-author AntCat collapses into "et al."
# and every such act reports a phantom added reference (Bradley: the 33 Boudinot,
# in Boudinot ... 2024 combinations, and 600+ others of this form).
IN_CITE = re.compile(r'\b[A-Z][A-Za-z\u00C0-\u024F\'\-]+,\s+in\s+([A-Z][A-Za-z\u00C0-\u024F\'\-]+)')
# "Boudinot, Bock, et al. 2024" / "Boudinot, Bock & Jouault, 2024" -- Bolton spells the
# co-authors; AntCat writes "Boudinot et al." So collapse a run of "Surname, Surname,
# [Surname,] et al." to just the first author, matching AntCat's rendering. Requires an
# "et al." (3+ authors) so ordinary two-author "A & B" citations are left intact.
ETAL_LIST = re.compile(
    r'\b([A-Z][A-Za-z\u00C0-\u024F\'\-]+)'
    r'(?:,\s+[A-Z]\.?)*'                                 # optional initials: "Huang, Y.,"
    r'(?:,\s+[A-Z][A-Za-z\u00C0-\u024F\'\-]+\.?)*'       # zero+ spelled-out co-authors
    r',?\s+et\s+al\.')

def _canon_in(text):
    # "Emery, in Dalla Torre, 1893" -> "Dalla Torre, 1893" (keep the publication author)
    text = IN_CITE.sub(r'\1', text)
    # "Boudinot, Bock, et al." -> "Boudinot et al." (drop the spelled-out co-authors)
    text = ETAL_LIST.sub(r'\1 et al.', text)
    return text

def citations(text):
    """citekey -> (surname, 'year+letter').

    Emits, for each year, keys under BOTH the first author and the nearest surname of
    that citation, because the two catalogues are shaped differently and neither anchor
    alone is safe for both:

      * Bolton is ';'-delimited, one citation per segment: the FIRST surname is the
        author ("Ye, Ran & Gao, 2025" -> ye). Nearest-surname wrongly gives Gao.
      * AntCat's history is one long run with no ';': walking back to bound a citation
        catches stray capitalised words (the genus, a locality), so FIRST-surname gives
        junk ("... Camponotus ambon Zhang, 1989 ... Boudinot et al., 2024" -> Camponotus).
        Nearest-surname-before-year correctly gives Boudinot.

    Emitting both keys per year means a citation matches if EITHER anchor agrees, which
    is what makes Bolton's "Ye, Ran & Gao 2025" match AntCat's "Ye et al., 2025" (both
    share ye|2025) without either side's prose shape defeating it. Over-generating keys
    is safe here: the sets are only ever compared for intersection, never counted.
    """
    text = _canon_in(text)
    out = {}
    prev_end = 0
    for m in YEARTOK.finditer(text):
        if m.start() > 0 and text[m.start() - 1] == '.':
            continue                              # a date like "viii.1894"
        yr, lt = m.group(1), m.group(2)
        if int(yr) > 2026:
            continue                              # page number / specimen code / DOI
        yl = yr + lt

        # (a) nearest surname before the year -- correct for AntCat's running prose
        pre = text[max(0, m.start() - 45):m.start()]
        near = None
        for sm in SURTOK.finditer(pre):
            near = sm.group(0)
        if near:
            out[f"{authorkey(near)}|{yl}"] = (near, yl)

        # (b) first surname of this citation -- correct for Bolton's ';'-delimited list
        span_start = max(prev_end, text.rfind(';', 0, m.start()) + 1)
        fm = SURTOK.search(text[span_start:m.start()])
        if fm:
            out.setdefault(f"{authorkey(fm.group(0))}|{yl}", (fm.group(0), yl))
        prev_end = m.end()
    return out

def loose(citekey):
    ak, yl = citekey.split('|')
    return f"{ak}|{yl[:4]}"

def display_cites(text, limit=5):
    """FIRST author of each ';'-separated citation, for the CSV columns."""
    out = []
    for seg in text.split(';'):
        ym = re.search(r'(1[6789]\d\d|20\d\d)([a-z]?)', seg)
        if not ym or int(ym.group(1)) > 2026:
            continue
        sm = SURTOK.search(seg)
        if sm:
            etal = ' et al.' if (' et al' in seg or seg.count('&')) else ''
            out.append(f'{sm.group(0)}{etal}, {ym.group(1)}{ym.group(2)}')
    return '; '.join(out[:limit])

def first_author_cite(region, yearletter):
    for seg in region.split(';'):
        if re.search(r'\b' + re.escape(yearletter) + r'\b', seg):
            sm = SURTOK.search(seg)
            if sm:
                etal = ' et al.' if (' et al' in seg or seg.count('&')) else ''
                return f'{sm.group(0)}{etal}, {yearletter}'
    return yearletter

# ---------------------------------------------------------------- act lines
# Bolton writes act labels mid-sentence in lower case ("...; hence combination in
# *Camponotites: Boudinot ... 2024"), 5,131 times for `combination in` alone, so the
# labels must be matched case-insensitively or those acts are never seen. 'synonyn' is
# a recurring typo in the NGC.
ACTLABELS = (r'(Junior synonym of|Senior synonym of|Junior synonyn of|Senior synonyn of|'
             r'Combination in|Subspecies of|Replacement name for|Variety or race of|'
             r'Unjustified emendation of)')
# The target is bounded (<= 60 chars). Unbounded, "[^:]+?" runs across sentence
# boundaries to a distant colon -- e.g. "Replacement name for Camponotus hova luteolus
# Emery, 1925. [Unnecessary ...]" swallowed the "Combination in ..." line that followed.
ACT = re.compile(ACTLABELS + r'\s+([^:;]{1,60}?)\s*:', re.I)

# A Bolton act line often carries SEVERAL clauses:
#   "Senior synonym of defensor: Forel, 1894c: 403; ...; incertae sedis in
#    rufibarbis group: Schultz & Seifert, 2026: 82."
# Only the citations before the next clause label belong to the act. A clause label
# is a ';'-introduced phrase ending in ':' that contains NO digits -- which is what
# distinguishes it from a citation, since a citation always carries a year.
CLAUSE_BOUNDARY = re.compile(r';\s*[A-Za-z][^;:0-9]{2,79}:')

# AntCat's prose is not always colon-terminated ("Junior synonym of Tapinoma domesticum
# (Smith, 1871) (first replacement name), and hence of Tapinoma melanocephalum ..."), so
# the bounded ACT regex above misses it. This looser form reads the binomial straight
# after the label. It is used ONLY on the AntCat side, where an extra match can suppress
# a row but never create one.
ACT_LOOSE = re.compile(ACTLABELS + r"\s+([A-Z][A-Za-z\u00C0-\u024F]+(?:\s+[a-z][a-z\-]+){1,2})", re.I)

def _lev(a, b):
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]

def norm_act(label):
    """lower-case, and fold Bolton's recurring 'synonyn' typo onto 'synonym'"""
    return label.lower().replace('synonyn', 'synonym')

def clause_region(line, m):
    rest = line[m.end():]
    b = CLAUSE_BOUNDARY.search(rest)
    return rest[:b.start()] if b else rest

_TGT_STOP = {'the', 'of', 'in', 'and', 'var', 'subsp', 'st', 'nr', 'sp', 'group', 'complex'}

def target_year(s):
    """Bolton often prints the target's authority ("of rossi (Donisthorpe, 1947d)"),
    which disambiguates homonymous epithets inside one genus."""
    return year4(s)

_ANAPHORA = {'latter', 'former', 'same'}
_LABEL_WORDS = {'unnecessary', 'replacement', 'name', 'for', 'hence', 'junior', 'senior',
                'synonym', 'synonyn', 'combination', 'subspecies', 'variety', 'race',
                'unjustified', 'emendation', 'the', 'and', 'of', 'in', 'primary',
                'secondary', 'homonym', 'first', 'available', 'use'}

def deanaphor(line, start, epithet):
    """Bolton and AntCat both refer back rather than repeating a name:
       "Unnecessary replacement name for herculeanopennsylvanicus; hence junior
        synonym of THE LATTER: Emery, 1925b: 72."
    Resolve to the last epithet named earlier in the same passage. Do NOT lower-case
    the window first: epithets are lower-case, author surnames are capitalised, and
    folding the case makes 'Dalla Torre' look like an epithet."""
    if epithet not in _ANAPHORA:
        return epithet
    window = line[max(0, start - 250):start]
    toks = [t for t in re.findall(r"\b[a-z][a-z\-]{3,}\b", window)
            if t not in _LABEL_WORDS]
    return toks[-1] if toks else epithet

def parse_target(s, act):
    """An act's target -> (genus_or_None, epithet); for combinations, (None, genus).

    Bolton names the target by bare epithet ("Junior synonym of minutior"); AntCat by
    binomial ("Junior synonym of Formica clara"). A target may trail its own authority
    when Bolton omits the colon ("of ilgii Forel, 1910c"), a parenthetical gloss ("of
    crawleyi (unnecessary replacement name)"), or -- in AntCat's run-on prose -- a
    second clause ("... and hence of Tapinoma melanocephalum"). Cut all three off."""
    s = s.replace('*', ' ').replace('†', ' ')
    if act.startswith('combination'):
        toks = re.findall(r"[A-Za-z\u00C0-\u024F'\-]+", s)
        toks = [t for t in toks if t.lower() not in _TGT_STOP]
        caps = [t for t in toks if t[:1].isupper()]
        if caps:
            return (None, fold(caps[-1]).lower())
        return (None, fold(toks[-1]).lower() if toks else '')

    s = re.sub(r'\([^)]*\)', ' ', s)               # drop "(unnecessary replacement name)"
    s = re.split(r'[,(]', s)[0]                    # stop before the authority / next clause
    toks = re.findall(r"[A-Za-z\u00C0-\u024F'\-]+", s)
    toks = [t for t in toks if t.lower() not in _TGT_STOP]
    genus, eps = None, []
    for t in toks:
        if t[:1].isupper():
            if eps:
                break                              # author surname
            genus = fold(t).lower()
        else:
            eps.append(fold(t).lower())
    if not eps:
        return (genus, genus or '')
    return (genus, eps[-1])

# ---------------------------------------------------------------- AntCat index
class AntCat:
    """AntCat keyed on protonym identity, with a resolver from any spelling."""

    def __init__(self, worldants):
        self.names = {}                       # protokey -> record
        self.by_ey = defaultdict(set)         # (orig_epithet, year) -> {protokey}
        self.variant = defaultdict(set)       # (genus, epithet) -> {protokey}
        self.variant_any = defaultdict(set)   # epithet -> {protokey}
        self.genera = set()                   # every genus / subgenus name AntCat uses
        self.subfamily = {}                   # norm_genus -> subfamily
        self.genus_epithets = defaultdict(set)  # norm_genus -> {(spelling, protokey)}
        self._load(worldants)

    def _add_variant(self, genus, epithet, key):
        if not epithet:
            return
        e = fold(epithet).lower()
        g = norm_genus(genus or '')
        for form in (e, gstem(e)):            # index the gender-corrected stem too, so
            self.variant[(g, form)].add(key)  # 'nupera' and 'nuperus' reach one identity
            self.variant_any[form].add(key)

    def _load(self, worldants):
        with open(worldants, encoding='utf-8', errors='replace', newline='') as fh:
            rd = csv.reader(fh, delimiter='\t')
            hdr = next(rd)
            ix = {h: i for i, h in enumerate(hdr)}
            for row in rd:
                if len(row) <= ix['taxonomic history html']:
                    continue
                sp, sub = row[ix['species']].strip(), row[ix['subspecies']].strip()
                term = sub or sp
                if not term:
                    continue
                text = strip_html(row[ix['taxonomic history html']])
                p = parse_protonym(text)
                if not p:
                    continue
                ogen, oepi, _au, yr = p
                key = (ogen, oepi, yr)
                genus = row[ix['genus']].strip()
                status = row[ix['status']].strip()
                cvn = row[ix['current valid name']].strip().split()
                fields = dict(genus=genus, species=sp, sub=sub, terminal=term, status=status,
                              cvn_genus=cvn[1] if len(cvn) > 2 else '',
                              cvn_term=cvn[-1] if len(cvn) > 1 else '')
                rec = self.names.get(key)
                if rec is None:
                    rec = dict(antcat_id=row[ix['antcat id']].strip(), text=text,
                               len=len(text), **fields)
                    self.names[key] = rec
                else:
                    if len(text) > rec['len']:
                        rec['text'], rec['len'] = text, len(text)
                    # an obsolete-combination row only points at the current combination;
                    # let a valid/synonym row define the name's status and placement
                    if status != 'obsolete combination':
                        rec.update(antcat_id=row[ix['antcat id']].strip(), **fields)
                self.genera.add(norm_genus(genus))
                self.genera.add(ogen)
                subf = row[ix['subfamily']].strip()
                if subf:
                    self.subfamily.setdefault(norm_genus(genus), subf)
                self.genus_epithets[norm_genus(genus)].add((term.lower(), key))
                for gm in re.finditer(r'Combination in\s+([^:]{1,60}?)\s*:', text):
                    for tok in re.findall(r"[A-Z][A-Za-z\u00C0-\u024F'\-]+", gm.group(1)):
                        self.genera.add(norm_genus(tok))
                self.by_ey[(oepi, yr)].add(key)
                self._add_variant(ogen, oepi, key)          # original spelling
                self._add_variant(genus, term, key)         # this row's spelling
                # NB: `current valid name` is NOT indexed as a spelling of this name.
                # For a synonym row the CVN is a DIFFERENT name (the senior), so
                # indexing it makes every junior synonym an alias of its senior and
                # every target lookup ambiguous. Rows that are merely another
                # combination or a misspelling of the same name already share this
                # protonym key, because they share the same protonym line.

    def pair(self, ogen, oepi, yr, cur_genus=''):
        """Bolton headword -> AntCat name, on protonym identity.

        The fallbacks must not cross genera: 'Brachymyrmex coactus robusta' (1923) and
        'Pheidole robusta' (1923) share an epithet and a year but are different names."""
        k = (ogen, oepi, yr)
        if k in self.names:
            return k
        g = norm_genus(cur_genus) if cur_genus else ''
        for k2 in self.by_ey.get((oepi, yr), ()):           # same epithet+year ...
            if k2[0] == ogen or (g and norm_genus(self.names[k2]['genus']) == g):
                return k2                                   # ... and a genus in common
        for (g2, e2, y2) in self.names:                     # gender variance, same orig genus
            if g2 == ogen and y2 == yr and gstem(e2) == gstem(oepi):
                return (g2, e2, y2)
        return None

    def resolve(self, genus_hint, epithet, year='', target_text=''):
        """any spelling of a name -> its protonym key.

        Epithets are homonymous even inside one genus (Acromyrmex gallardoi Santschi
        1936 vs Sericomyrmex gallardoi 1920, both now Acromyrmex). Where Bolton prints
        the target's authority we use it; otherwise an ambiguous target is left
        unresolved and falls back to a string key -- symmetrically on both sides, so
        it degrades to the old behaviour rather than inventing a match."""
        if target_text:                       # "Odontomachus tyrannicus Smith, F. 1861b"
            p = parse_protonym(target_text)
            if p and (p[0], p[1], p[3]) in self.names:
                return (p[0], p[1], p[3])
        e = fold(epithet or '').lower()
        if not e:
            return None

        def pick(cand):
            if not cand:
                return None
            cand = set(cand)
            if len(cand) == 1:
                return next(iter(cand))
            if year:                                  # Bolton printed the authority
                yr = {k for k in cand if k[2] == year}
                if len(yr) == 1:
                    return next(iter(yr))
                if yr:
                    cand = yr
            if genus_hint:                            # the name now bearing that exact
                g = norm_genus(genus_hint)            # binomial, spelled as written
                exact = {k for k in cand
                         if norm_genus(self.names[k]['genus']) == g
                         and fold(self.names[k]['terminal']).lower() == e}
                if len(exact) == 1:
                    return next(iter(exact))
                if exact:
                    cand = exact
            # Do NOT guess between homonyms. Bolton's bare "foreli" and AntCat's
            # "foreli (Menozzi, 1921)" are different names; picking the valid one would
            # silently invent an identity. Leave it unresolved -- comparison then falls
            # back to the epithet stem, symmetrically on both sides.
            return None

        if genus_hint:
            g = norm_genus(genus_hint)
            for form in (e, gstem(e)):
                k = pick(self.variant.get((g, form)))
                if k:
                    return k
        for form in (e, gstem(e)):
            k = pick(self.variant_any.get(form))
            if k:
                return k
        return None

    def candidates(self, genus_hint, epithet):
        e = fold(epithet or '').lower()
        out = set()
        if genus_hint:
            g = norm_genus(genus_hint)
            for form in (e, gstem(e)):
                out |= self.variant.get((g, form), set())
        if not out:
            for form in (e, gstem(e)):
                out |= self.variant_any.get(form, set())
        return out

    def relations(self, text, genus_hint):
        """Acts asserted in an AntCat history, indexed BOTH by resolved protonym key and
        by epithet stem. AntCat often prints the target's authority where Bolton gives a
        bare epithet, so one side may resolve while the other cannot; matching on either
        channel keeps that asymmetry from manufacturing a missing act."""
        keys, stems = set(), set()
        for rx in (ACT, ACT_LOOSE):
            for m in rx.finditer(text):
                act = norm_act(m.group(1))
                g, e = parse_target(m.group(2), act)
                e = deanaphor(text, m.start(), e)     # AntCat writes "of the latter" too
                if not e:
                    continue
                if act == 'combination in':
                    keys.add((act, ('genus', norm_genus(e))))
                    stems.add((act, norm_genus(e)))
                else:
                    k = self.resolve(g or genus_hint, e, target_year(m.group(2)), m.group(2))
                    if k:
                        keys.add((act, k))
                    stems.add((act, gstem(e)))
        return keys, stems

    def encodes(self, act, key, tgt_key, tgt_epi):
        """Does AntCat record this act in its STRUCTURED fields, or on the TARGET's own
        record? AntCat stores a synonymy as status + current-valid-name on the JUNIOR
        name; Bolton asserts it on the SENIOR name's line."""
        me = self.names.get(key)
        if not me:
            return ''
        if act == 'combination in':
            if norm_genus(me['genus']) == norm_genus(tgt_epi) or \
               (me['cvn_genus'] and norm_genus(me['cvn_genus']) == norm_genus(tgt_epi)):
                return 'antcat: already placed in target genus'
            return ''
        tgt = self.names.get(tgt_key) if tgt_key else None

        def points_at(rec, target_key, target_epi):
            """rec's current valid name is `target`, by identity or (if the target is
            homonymous and so unresolved) by epithet stem."""
            if not rec['cvn_term']:
                return False
            if target_key:
                return self.resolve(rec['cvn_genus'] or rec['genus'], rec['cvn_term']) == target_key
            return gstem(fold(rec['cvn_term']).lower()) == gstem(target_epi)

        def asserts(rec, act2, subject_key, subject_epi):
            keys, stems = self.relations(rec['text'], rec['genus'])
            return ((act2, subject_key) in keys) or ((act2, gstem(subject_epi)) in stems)

        my_epi = key[1]
        if act == 'junior synonym of':
            if points_at(me, tgt_key, tgt_epi):
                return f"antcat: current valid name = {me['cvn_genus']} {me['cvn_term']}".strip()
            if tgt and asserts(tgt, 'senior synonym of', key, my_epi):
                return f"antcat: {tgt['genus']} {tgt['terminal']} history has senior synonym"
        elif act == 'senior synonym of':
            if tgt and points_at(tgt, key, my_epi):
                return f"antcat: {tgt['genus']} {tgt['terminal']} current valid name = this name"
            if tgt and asserts(tgt, 'junior synonym of', key, my_epi):
                return f"antcat: {tgt['genus']} {tgt['terminal']} history has junior synonym"
        elif act == 'subspecies of':
            if me['sub'] and (self.resolve(me['genus'], me['species']) == tgt_key if tgt_key
                              else gstem(fold(me['species']).lower()) == gstem(tgt_epi)):
                return 'antcat: recorded as subspecies of target'
        return ''

    def suggest(self, genus_hint, epithet, limit=3):
        """Nearest AntCat name(s) to an unmatched target, for HUMAN review only.

        Edit distance is never used to decide identity (that invents names); it is
        used here to hand the reviewer the likely intended name. Bolton's NGC
        carries real typos -- jonsii/jonesii, variablilis/variabilis, dawinii/darwinii."""
        e = fold(epithet or '').lower()
        if not e:
            return ''
        pool = self.genus_epithets.get(norm_genus(genus_hint or ''), set())
        scored = sorted(((_lev(e, sp), sp) for sp, _k in pool))[:limit]
        near = [f'{sp} (d={d})' for d, sp in scored if d <= 2]
        return '; '.join(near)

    def combination_evidence(self, name_key, target_genus):
        """For a 'combination in' act: where AntCat actually places the name, and
        whether Bolton's target genus even belongs to the same subfamily. Bolton
        writes 'combination in Brachymyrmex' (Formicinae) for a Brachyponera
        (Ponerinae) name -- a typo, obvious once the subfamilies are shown."""
        me = self.names.get(name_key)
        if not me:
            return ''
        g = norm_genus(me['genus'])
        tg = norm_genus(target_genus)
        mine = self.subfamily.get(g, '?')
        theirs = self.subfamily.get(tg, '')
        out = f"antcat places it in {me['genus']} ({mine})"
        if theirs and theirs != mine:
            out += f'; target genus {target_genus.title()} is {theirs} -- different subfamily'
        elif not theirs:
            out += f'; target genus {target_genus.title()} not an AntCat genus'
        return out

    def target_status(self, act, tgt_key):
        if act == 'combination in':
            return ''
        if not tgt_key:
            return 'target not resolved in AntCat'
        t = self.names[tgt_key]
        cv = f" -> {t['cvn_genus']} {t['cvn_term']}".rstrip() if t['cvn_term'] else ''
        return t['status'] + cv

# ---------------------------------------------------------------- Bolton side
def bolton_protokey(b):
    """Bolton's headword line gives the original combination verbatim."""
    oc = (b.get('original_combination') or '').split()
    if len(oc) < 2:
        return None
    y = year4(b.get('year', ''))
    return (fold(oc[0]).lower(), fold(oc[-1]).lower(), y) if y else None

def bolton_acts(block):
    """act lines, with citations scoped to each act's own clause."""
    out = []
    for line in block.split('\n'):
        for m in ACT.finditer(line):
            region = clause_region(line, m)
            cites = citations(region)
            yrs = [int(k.split('|')[1][:4]) for k in cites]
            act = norm_act(m.group(1))
            g, e = parse_target(m.group(2), act)
            e = deanaphor(line, m.start(), e)
            out.append(dict(act=act, target_text=m.group(2), target_genus=g, target_epi=e,
                            region=region, newest=max(yrs) if yrs else 0,
                            cites=display_cites(region), line=line.strip()[:200]))
    return out

# ---------------------------------------------------------------- driver
def run(bolton_dir, worldants, out_dir, recent_from=2015):
    os.makedirs(out_dir, exist_ok=True)
    ac = AntCat(worldants)

    act_rows, per_species, addref_rows, suppressed, unresolved = [], [], [], [], []
    n_blocks = n_paired = n_unresolved = 0

    with open(os.path.join(bolton_dir, 'bolton_species_blocks.jsonl'), encoding='utf-8') as f:
        for ln in f:
            b = json.loads(ln)
            n_blocks += 1
            bk = bolton_protokey(b)
            if not bk:
                continue
            key = ac.pair(*bk, cur_genus=b['genus'])
            if not key:
                continue                       # AntCat has no such name -> name-level diff
            n_paired += 1
            me = ac.names[key]
            ac_keys, ac_stems = ac.relations(me['text'], me['genus'])
            ac_cites = set(citations(me['text']))
            ac_loose = {loose(k) for k in ac_cites}

            seen, missing = set(), []
            for a in bolton_acts(b.get('block_text') or ''):
                act, ttext = a['act'], a['target_text']
                g, e = a['target_genus'], a['target_epi']
                if not e:
                    continue
                if act == 'combination in':
                    tgt_key = None
                    rel, stem_rel = (act, ('genus', norm_genus(e))), (act, norm_genus(e))
                else:
                    tgt_key = ac.resolve(g or b['genus'], e, target_year(ttext), ttext)
                    if not tgt_key:
                        n_unresolved += 1
                    rel = (act, tgt_key if tgt_key else ('epi', gstem(e)))
                    stem_rel = (act, gstem(e))
                if rel in seen:
                    continue
                seen.add(rel)

                if (tgt_key and rel in ac_keys) or stem_rel in ac_stems:
                    known = 'antcat: history asserts this act'
                else:
                    known = ac.encodes(act, key, tgt_key, e)

                unknown_genus = (act == 'combination in' and norm_genus(e) not in ac.genera)
                if not known and (unknown_genus or (act != 'combination in' and not tgt_key)):
                    # We could not identify the target name in AntCat, so we cannot say
                    # whether AntCat holds the act. Usually the two catalogues spell the
                    # target differently (Bolton 'jonsii' vs AntCat 'jonesii', or a Bolton
                    # typo like 'dawinii'), or the epithet is homonymous. Not a gap --
                    # a name-level disagreement that blocks the act-level comparison.
                    if a['newest'] >= recent_from:
                        if unknown_genus:
                            reason = 'target genus/subgenus not used anywhere in AntCat'
                        else:
                            n = len(ac.candidates(g or b['genus'], e))
                            reason = ('target not found in AntCat' if not n
                                      else f'target ambiguous ({n} names share the spelling)')
                        unresolved.append(dict(newest=a['newest'], genus=b['genus'],
                                               epithet=b['epithet'], antcat_id=me['antcat_id'],
                                               act=act, target=e, reason=reason,
                                               antcat_suggestion=('' if unknown_genus
                                                                  else ac.suggest(g or b['genus'], e)),
                                               bolton_line=a['line']))
                elif not known:
                    missing.append((a, act, e, tgt_key))
                elif a['newest'] >= recent_from and not known.startswith('antcat: history asserts'):
                    suppressed.append(dict(newest=a['newest'], genus=b['genus'],
                                           epithet=b['epithet'], antcat_id=me['antcat_id'],
                                           act=act, target=e, antcat_evidence=known,
                                           bolton_line=a['line']))

                # ADDITIONAL REFERENCES: a citation Bolton attaches to this act line that
                # AntCat's history does not carry. Only nomenclatural-act lines -- the
                # faunistic "Status as species" dumps are the noise floor (~50k rows).
                ac_author_years = defaultdict(set)    # author -> {years} AntCat cites on THIS name
                for kk in ac_cites:
                    ac_author_years[kk.split('|')[0]].add(kk.split('|')[1][:4])
                # citations() over-generates keys per citation (first author AND nearest
                # surname, to bridge the two catalogues' prose shapes). Group Bolton's keys
                # by year+letter so ONE citation is judged once: it is "already in AntCat"
                # if ANY of its author keys matches, not flagged once per co-author.
                bolton_by_yl = defaultdict(list)
                for k, (sur, yl) in citations(a['region']).items():
                    bolton_by_yl[yl].append((k, sur))
                for yl, group in bolton_by_yl.items():
                    yr = int(yl[:4])
                    if yr < recent_from:
                        continue
                    keys = {k for k, _ in group}
                    if keys & ac_cites or {loose(k) for k in keys} & ac_loose:
                        continue                      # some author of this citation matches
                    # online-early vs formal: AntCat cites one of these authors within a
                    # year on this same name (Bolton "Mera-Rodríguez 2024" == AntCat
                    # "... 2025"). Scoped to this name only, never a global author+year rule.
                    if any(abs(yr - int(y)) <= 1
                           for k, _ in group
                           for y in ac_author_years.get(k.split('|')[0], ())
                           if y.isdigit()):
                        continue
                    addref_rows.append(dict(newest=yr, genus=b['genus'], epithet=b['epithet'],
                                            antcat_id=me['antcat_id'], act=act, target=e,
                                            added_citation=first_author_cite(a['region'], yl),
                                            act_status=('existing' if known else 'new_act'),
                                            bolton_line=a['line']))

            if missing:
                newest = max(a['newest'] for a, _, _, _ in missing)
                per_species.append(dict(genus=b['genus'], epithet=b['epithet'],
                                        year=b.get('year', ''), antcat_id=me['antcat_id'],
                                        missing_acts=len(missing), newest_gap=newest))
                for a, act, e, tgt_key in missing:
                    evidence = (ac.combination_evidence(key, e) if act == 'combination in'
                                else ac.target_status(act, tgt_key))
                    act_rows.append(dict(newest=a['newest'], genus=b['genus'],
                                         epithet=b['epithet'], antcat_id=me['antcat_id'],
                                         act=act, target=e,
                                         antcat_target_status=evidence,
                                         bolton_citations=a['cites'], bolton_line=a['line']))

    recent = [r for r in act_rows if r['newest'] >= recent_from]
    recent.sort(key=lambda r: (-r['newest'], r['genus'], r['epithet']))
    act_rows.sort(key=lambda r: (-r['newest'], r['genus'], r['epithet']))
    per_species.sort(key=lambda r: (-r['newest_gap'], -r['missing_acts']))
    addref_rows.sort(key=lambda r: (r['act_status'] != 'existing', -r['newest'],
                                    r['genus'], r['epithet']))
    suppressed.sort(key=lambda r: (-r['newest'], r['genus'], r['epithet']))
    unresolved.sort(key=lambda r: (-r['newest'], r['genus'], r['epithet']))

    def write(path, rows, fields):
        with open(os.path.join(out_dir, path), 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
            w.writeheader(); w.writerows(rows)

    fields = ['newest', 'genus', 'epithet', 'antcat_id', 'act', 'target',
              'antcat_target_status', 'bolton_citations', 'bolton_line']
    write('history_recent_acts_to_check.csv', recent, fields)
    write('history_all_acts_to_check.csv', act_rows, fields)
    write('history_by_species.csv', per_species,
          ['genus', 'epithet', 'year', 'antcat_id', 'missing_acts', 'newest_gap'])
    write('history_added_refs_to_check.csv', addref_rows,
          ['act_status', 'newest', 'genus', 'epithet', 'antcat_id', 'act', 'target',
           'added_citation', 'bolton_line'])
    write('history_suppressed_acts.csv', suppressed,
          ['newest', 'genus', 'epithet', 'antcat_id', 'act', 'target', 'antcat_evidence',
           'bolton_line'])
    write('history_unresolved_targets.csv', unresolved,
          ['newest', 'genus', 'epithet', 'antcat_id', 'act', 'target', 'reason',
           'antcat_suggestion', 'bolton_line'])

    from collections import Counter
    bytype = Counter(r['act'] for r in recent)
    n_exist = sum(1 for r in addref_rows if r['act_status'] == 'existing')
    L = [
        "CONTENT-LEVEL DIFF -- paired on PROTONYM IDENTITY (original combination + year)",
        f"  Bolton species blocks:                    {n_blocks:>6}",
        f"  paired to an AntCat name:                 {n_paired:>6}",
        f"  AntCat names indexed:                     {len(ac.names):>6}",
        f"  act targets that did not resolve:         {n_unresolved:>6}",
        "",
        f"  names with a placement act AntCat lacks:  {len(per_species):>6}   -> history_by_species.csv",
        f"  total such acts:                          {len(act_rows):>6}   -> history_all_acts_to_check.csv",
        f"  of those, recent (>= {recent_from}):               {len(recent):>6}   -> history_recent_acts_to_check.csv",
        f"  suppressed: recent acts AntCat encodes    {len(suppressed):>6}   -> history_suppressed_acts.csv",
        "    (status / current-valid-name / the target's own record)",
        f"  recent acts whose TARGET could not be identified in AntCat: {len(unresolved):>4}",
        "    -> history_unresolved_targets.csv  (spelling differs, or homonymous epithet;",
        "       a name-level disagreement, not a verified missing act)",
        "",
        "  recent acts by type:",
    ]
    for t, n in bytype.most_common():
        L.append(f"      {t:24} {n:>5}")
    L += [
        "",
        f"ADDITIONAL REFERENCES on nomenclatural-act lines (recent >= {recent_from})   -> history_added_refs_to_check.csv",
        f"  total:                                    {len(addref_rows):>6}",
        f"    act_status=existing (extra ref on an act AntCat has): {n_exist:>6}",
        f"    act_status=new_act  (corroborates the list above):    {len(addref_rows)-n_exist:>6}",
        "  Faunistic 'Status as species' / non-act citations are deliberately excluded.",
        "",
        "  Each row is a disagreement, not a confirmed gap. The original publication",
        "  is the authority -- verify, then enter in AntCat if confirmed.",
        "",
    ]
    txt = "\n".join(L)
    with open(os.path.join(out_dir, 'HISTORY_SUMMARY.txt'), 'w') as f:
        f.write(txt + "\n")
    print(txt)

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--bolton-dir', default='bolton_out')
    ap.add_argument('--worldants', required=True)
    ap.add_argument('--out-dir', default='diff_out')
    ap.add_argument('--recent-from', type=int, default=2015)
    a = ap.parse_args()
    run(a.bolton_dir, a.worldants, a.out_dir, a.recent_from)
