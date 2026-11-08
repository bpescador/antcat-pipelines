"""Classify AntCat history lines into kinds; derive the canonical order of kinds."""
import csv, collections, re, itertools, json, sys
csv.field_size_limit(10**7)

REL = {  # structured types -> kind
    'CombinationIn': 'Combination in', 'FormDescriptions': 'Form descriptions',
    'TypeSpecimenDesignation': 'Lecto/neotype designation', 'JuniorSynonymOf': 'Junior synonym of',
    'SeniorSynonymOf': 'Senior synonym of', 'StatusAsSpecies': 'Status as species',
    'SubspeciesOf': 'Subspecies of', 'ReplacementNameFor': 'Replacement name for',
    'HomonymReplacedBy': 'Replacement name (homonym replaced by)',
    'JuniorPrimaryHomonymOf': 'Junior homonym', 'JuniorPrimaryHomonymOfHardcodedGenus': 'Junior homonym',
    'JuniorSecondaryHomonymOf': 'Junior homonym', 'UnavailableName': 'Unavailable name / nomen nudum',
}
RULES = [  # (kind, regex on text with tags replaced by X and leading '[' removed)
    ('OTHER', r'\((error|errors)\)'),
    ('Form descriptions', r'^X: [^;()]*\((?:(?:ergatoid |putative )?[wqmlkseda]+\.(?:[wqmlkseda]+\.)* ?)+\)'),
    ('Lecto/neotype designation', r'^(Lectotype|Neotype) designation'),
    ('Combination in', r'^Combination in'),
    ('Subspecies of', r'^Subspecies of'),
    ('Status as species', r'^Status as species'),
    ('Revived status / raised to species', r'^(Revived (from synonymy|status)|Raised to species)'),
    ('Junior synonym of', r'^(Junior synonym of|X as junior synonym)'),
    ('Senior synonym of', r'^(Senior synonym of|X as senior synonym)'),
    ('Misspelling / incorrect spelling', r'^(Misspelled as|X: incorrect (subsequent|original) spelling)'),
    ('Emendation', r'^((Justified|Unjustified) emendation|X: (un)?justified emendation)'),
    ('First available use', r'^First available use'),
    ('Unavailable infrasubspecific', r'(^As unavailable \(infrasubspecific\)|^Declared as unavailable|unavailable \(infrasubspecific\))'),
    ('Also described as new', r'^(Also described as new|X also described as new)'),
    ('Replacement name for', r'^Replacement name for'),
    ('Replacement name (homonym replaced by)', r'^Replacement name:'),
    ('Unnecessary replacement name', r'^Unnecessary'),
    ('Junior homonym', r'(^Junior (primary |secondary )?homonym|^Unresolved junior|^X junior (primary |secondary )?homonym)'),
    ('Material referred', r'^Material (referred|of the)'),
    ('Unavailable name / nomen nudum', r'(^<i>Nomen nudum|^Unavailable name|^Unavailable replacement)'),
    ('Unidentifiable / incertae sedis', r'(^Unidentifiable|incertae sedis</i>|^<i>Incertae sedis)'),
    ('Excluded', r'(excluded from|^Excluded from)'),
    ('Higher placement (X in X, X as genus...)', r'^X (in X|as (genus|subgenus|tribe|subtribe|subfamily|family|group))'),
    ('Type-species', r'^Type-species'),
    ('Note', r'^Note'),
    ('Transferred to', r'^Transferred to'),
]
RULES = [(k, re.compile(p)) for k, p in RULES]

def kind_of(row):
    if row['type'] != 'Taxt':
        k = REL.get(row['type'])
        if row['type'] == 'TypeSpecimenDesignation':
            return 'Lecto/neotype designation'
        return k or 'REL:' + row['type']
    t = re.sub(r'\{[a-z]+\d? [^}]*\}', 'X', row['text']).lstrip('[ ')
    for k, rx in RULES:
        if rx.search(t):
            return k
    return 'OTHER'

def group_of(rank):
    if rank in ('SpeciesName', 'SubspeciesName', 'InfrasubspeciesName'): return 'species-group'
    if rank in ('GenusName', 'SubgenusName'): return 'genus-group'
    return 'family-group'

rows = list(csv.DictReader(open('/tmp/ho/lines.tsv'), delimiter='\t', quoting=csv.QUOTE_NONE))
for r in rows:
    r['kind'] = kind_of(r); r['group'] = group_of(r['protonym_rank']); r['pos'] = int(r['position'] or 0); r['iid'] = int(r['id'])
json.dump(rows, open('/tmp/ho/rows.json', 'w'))

kinds = collections.Counter((r['group'], r['kind']) for r in rows)
for g in ('species-group', 'genus-group', 'family-group'):
    tot = sum(v for (gg, _), v in kinds.items() if gg == g)
    print(f'\n== {g}: {tot} lines')
    for (gg, k), v in sorted(kinds.items(), key=lambda x: -x[1]):
        if gg == g: print(f'  {v:6d}  {k}')
other = collections.Counter(' '.join(re.sub(r'\{[a-z]+\d? [^}]*\}', 'X', r['text']).lstrip('[ ').split()[:4])
                            for r in rows if r['kind'] == 'OTHER')
print('\nTop OTHER openings:')
for k, v in other.most_common(25): print(f'  {v:5d}  {k}')
