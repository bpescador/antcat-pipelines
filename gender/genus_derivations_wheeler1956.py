#!/usr/bin/env python3
# genus_derivations_wheeler1956.py -- builds the wheeler1956_genus_derivation input for write_protonym_fields.rb (21 Nov 2026).
# Inputs (not in git): the corrected Wheeler 1956 transcription (wheeler1956_entries.json, wheeler_gender.json) and
# the read-only export of gender/genus_protonym_export.rb. Every text was read before staging.
import json, csv, re, sys
from collections import defaultdict
W = json.load(open('../wh/wheeler_gender.json'))
ENTRY = {e['name']: e for e in json.load(open('../wh/wheeler1956_entries.json'))}
X = list(csv.DictReader(open('/mnt/user-data/uploads/snapshots/genus-provenance-20261121/genus_protonyms.tsv'), delimiter='\t'))
CORR = {'429737':'neuter','429174':'neuter','429947':'neuter','430135':'feminine','429270':'feminine','429748':'masculine',
        '429625':'feminine','508809':'feminine','430120':'feminine'}     # 21 Nov site edits
for x in X:
    if x['taxon_id'] in CORR: x['gender'] = CORR[x['taxon_id']]
PAGE = {r['name']: int(r['col'][:2]) + 2 for r in W}
NO_DERIV = {'LEPISIOTA','MYRMOPIROMIS','MYRMOMALIS','NEAPHOMUS','RENEA','SEMONIUS','SOMMIMYRMA'}
# open on the wiki list: derivation only, no gender sentence
OPEN = {'ACANTHIDRIS','ANCYRIDRIS','ANILLIDRIS','ARNOLDIDRIS','ASPIDIDRIS','AXINIDRIS','CYPHOIDRIS','DORISIDRIS','HYLIDRIS',
        'IRENEIDRIS','PROSOPIDRIS','TALARIDRIS','MYOPIAS','PROMYOPIAS','HARPEGNATHOS','LEPTANILLOIDES','STIGMACROS'}
G = {'masculine':'masculine','feminine':'feminine','neuter':'neuter'}

def it(s):
    s = s.replace('engramma*', '*engramma')
    s = re.sub(r"\*([a-z]+)", r"\1 (a hypothetical form, so marked by Wheeler)", s)
    s = re.sub(r"\b(Late Gr\.|Gr\.|L\.)( combining form)? ((?:[a-z][a-z\-]*)(?: \([a-z]+\))?(?: from [a-z]+)?)",
               lambda m: {'Gr.':'Greek','L.':'Latin','Late Gr.':'Late Greek'}[m.group(1)] + (m.group(2) or '') + ' <i>' + m.group(3) + '</i>', s)
    s = re.sub(r"<i>([a-z\-]+) from ([a-z]+)</i>", r"<i>\1</i> from <i>\2</i>", s)
    s = re.sub(r"<i>([a-z\-]+) \(([a-z]+)\)</i>", r"<i>\1</i> (<i>\2</i>)", s)
    s = re.sub(r"\b([A-Z][a-z]{3,})(?= \((?:q\. v\.|Greek|Latin|see above))", r"<i>\1</i>", s)
    s = s.replace(' (q. v.)', '').replace('(see above)', 'as above')
    s = re.sub(r"\bdim\. of\b", 'diminutive of', s)
    s = s.replace('Gr. ', 'Greek ')
    s = re.sub(r"\bL\. (?=[a-z\-])", 'Latin ', s)
    return s

POST = [
 ("Greek <i>a-</i>, an- 'without'", "Greek <i>a-</i>, <i>an-</i> 'without'"),
 ("'ant (Hesiod's 'knowing or provident one')'", "'ant' (Hesiod's word for the ant, \"knowing or provident one\")"),
 ("<i>Atta</i> (Latin <i>surname</i> 'for persons who walk on the tips of their shoes')", "<i>Atta</i> (a Latin surname, 'for persons who walk on the tips of their shoes')"),
 ("(Greek <i>krema</i>(s)tos 'hung, suspended' + gaster 'belly')", "(Greek <i>krema(s)tos</i> 'hung, suspended' + <i>gaster</i> 'belly')"),
 ("(Greek <i>kolobos</i> 'docked, clipped' + opsis 'face')", "(Greek <i>kolobos</i> 'docked, clipped' + <i>opsis</i> 'face')"),
 ("(Greek <i>kryptos</i> 'hidden' + keras 'horn')", "(Greek <i>kryptos</i> 'hidden' + <i>keras</i> 'horn')"),
 ("Latin <i>diminutive</i> -ula", "the Latin diminutive suffix -ula"),
 ("<i>aulaks</i>", "<i>aulax</i>"),
]
def fix(s):
    for a, b in POST: s = s.replace(a, b)
    # an unmarked word with its gloss: italicise it
    s = re.sub(r"(?<![>\w])([a-z][a-z\-]{2,})(?= '[^']+')", lambda m: m.group(1) if m.group(1) in ('from','the','and','or') else '<i>' + m.group(1) + '</i>', s)
    return s

BODY = {
 'EMERYOPONE': "From Carlo Emery (1848-1925), Italian myrmecologist, + <i>Ponera</i> (Greek <i>poneros</i> 'wretched; laborious')",
 'FORELOMYRMEX': "From Auguste Forel (1848-1931), Swiss psychiatrist and myrmecologist, + Greek <i>myrmex</i> (<i>myrmekos</i>) 'ant'",
 'FORELOPHILUS': "From Auguste Forel (1848-1931), Swiss psychiatrist and myrmecologist, + Greek <i>philos</i> 'friend'",
 'HOLCOPONERA': "From Greek <i>holkos</i> 'attractive; track, furrow; coiling (of a serpent); a kind of spider' + <i>Ponera</i> (Greek <i>poneros</i> 'wretched; laborious')",
 'HOLCOMYRMEX': "From Greek <i>holkos</i> 'attractive; track, furrow; coiling (of a serpent); a kind of spider' + Greek <i>myrmex</i> (<i>myrmekos</i>) 'ant'",
 'IRENEA': "From the given name Irene, or Greek <i>eirenaia</i>, feminine of <i>eirenaios</i> 'peaceful'",
 'IRENEELLA': "From the given name Irene, or Greek <i>eirenaia</i> 'peaceful' (as <i>Irenea</i>), + Latin -<i>ella</i> 'little'",
 'IRENEIDRIS': "From the given name Irene, or Greek <i>eirenaia</i> 'peaceful' (as <i>Irenea</i>), + Greek <i>idris</i> 'ant' (Hesiod's word for the ant, \"knowing or provident one\")",
 'IRENEOPONE': "From the given name Irene, or Greek <i>eirenaia</i> 'peaceful' (as <i>Irenea</i>), + <i>Ponera</i> (Greek <i>poneros</i> 'wretched; laborious')",
 'OPISTHOSCYPHUS': "From Greek <i>opistho-</i> from <i>opisthe</i> 'behind, at the back' + Greek <i>skyphos</i> 'cup'",
 'WEBERISTRUMA': "From N. A. Weber (1908- ), American myrmecologist, + Latin <i>struma</i> 'a scrofulous tumor'",
 'WHEELERIMYRMEX': "From William Morton Wheeler (1865-1937), American myrmecologist, + Greek <i>myrmex</i> (<i>myrmekos</i>) 'ant'",
 'WHEELERIPONE': "From William Morton Wheeler (1865-1937), American myrmecologist, + <i>Ponera</i> (Greek <i>poneros</i> 'wretched; laborious')",
 'AZTECA': "From Spanish <i>Azteca</i> 'Aztec'",
 'WADEURA': "From an Arawak Indian name for the genus",
 'SIFOLINIA': "From Italian Sifolini, a girl's nickname",
 'DORYLUS': "Perhaps from Greek <i>dorylos</i> (queried by Wheeler)",
 'MANNIELLA': "From a hypothetical <i>Mannia</i>, from W. M. Mann (1886- ), American myrmecologist, + Latin -<i>ella</i> 'little'",
 'KYIDRIS': "From the initials of K. Yasumatsu, Japanese myrmecologist, + Greek <i>idris</i> 'ant' (Hesiod's word for the ant, \"knowing or provident one\")",
 'MIANEURETUS': "From Miocene (shortened) + <i>Aneuretus</i>",
}
def derivation(name):
    e = ENTRY[name]
    if name in BODY:
        return BODY[name] + f" (Wheeler, 1956: {PAGE[name]})."
    body = fix(it(e['full']).strip().rstrip('.'))
    if re.match(r'(Greek|Latin|Late Greek|<i>)', body) or ' + ' in body:
        body = 'From ' + body
    elif re.search(r'ologist|collector|naturalist|explorer|entomologist|^[A-Z]\. |^[A-Z][a-z]+ [A-Z]', body) and not re.match(r'(Probably|Possibly|Anagram|Given)', body):
        body = ('From ' if ' + ' in body else 'Named for ') + body
    elif re.match(r'(Probably|Possibly|possibly|presumably|Presumably|Anagram|anagram|Given|given|Initials)', body):
        body = body[0].upper() + body[1:]
    else:
        body = 'From ' + body
    return body + f" (Wheeler, 1956: {PAGE[name]})."

def final_word(name):
    parts = [p for p in re.findall(r"(Late Gr\.|Gr\.|L\.) \*?([a-z\-]+)", ENTRY[name]['full'])]
    return parts[-1] if parts else None

def sentence(r, g):
    comp, art = r['comp'], r['art']
    n = r['name'].capitalize()
    m = re.match(r"(Greek|Latin) ([a-z]+) \((m|f|n)\.\)(?:,? .*)?$", comp)
    if m and 'latinized' not in comp and 'ending' not in comp: return f"the final component, {m.group(1)} <i>{m.group(2)}</i>, is {g}", art
    m = re.match(r"Greek ([a-z]+) \((m|f|n)\.\)(?:, [^,]+)? latinized with (-[a-z]+)$", comp) or re.match(r"Greek ([a-z]+) \((m|f|n)\.\) (?:latinized )?with the ending (-[a-z]+)$", comp)
    if m: return f"the final component, Greek <i>{m.group(1)}</i>, is latinized with the ending {m.group(3)}, whose gender it takes", art
    fixed = {
     'Myrma, Greek myrmos (m.), ant, latinized with -a': ("the final component, -<i>myrma</i>, is Greek <i>myrmos</i> latinized with the ending -a, whose gender it takes", '30.1.3'),
     'Ponera, Greek poneros latinized with -a': ("the final component is <i>Ponera</i> (feminine), Greek <i>poneros</i> latinized with the ending -a", '30.1.3'),
     'a shortened Ponera (f.)': ("the final component, -<i>pone</i>, is a shortened <i>Ponera</i> (feminine)", '30.1.3'),
     'a shortened Crematogaster (f.)': ("the final component, -<i>crema</i>, is a shortened <i>Crematogaster</i> (Greek <i>gaster</i>, feminine)", '30.1.2'),
     'Pheidole, Greek pheidolos with the feminine ending -e': ("the final component is <i>Pheidole</i>, Greek <i>pheidolos</i> with the feminine ending -e", '30.1.3'),
     'Latin feminine diminutive -ella': ("it ends in the Latin feminine diminutive suffix -ella", '30.1.1'),
     'Latin feminine diminutive -ula': ("it ends in the Latin feminine diminutive suffix -ula", '30.1.1'),
     'Latin adjectival ending -ina, feminine': ("it ends in the Latin suffix -ina, feminine", '30.1.1'),
     'Latin feminine adjectival suffix -aria': ("it ends in the Latin suffix -aria, feminine", '30.1.1'),
     'Latin struma (f.), tumor': ("the final component, Latin <i>struma</i>, is feminine", '30.1.1'),
     'Latin formica (f.), ant': ("the final component, Latin <i>formica</i>, is feminine", '30.1.1'),
     'Latin messor (m.), reaper': ("the final component, Latin <i>messor</i>, is masculine", '30.1.1'),
     'Latin manica (f.), sleeve': ("the final component, Latin <i>manica</i>, is feminine", '30.1.1'),
     'Atta, ending -a': ("<i>Atta</i> is a Latin surname, not a word of the language; a name ending in -a is feminine", '30.2.4'),
     'Lasius, Greek lasios latinized with -us': ("the final component, Greek <i>lasios</i>, is latinized with the ending -us, whose gender it takes", '30.1.3'),
     'Greek keras (n.) latinized with -us': ("the final component, Greek <i>keras</i>, is latinized with the ending -us, whose gender it takes", '30.1.3'),
     'Greek gnathos (f.) latinized with -us': ("the final component, Greek <i>gnathos</i>, is latinized with the ending -us, whose gender it takes", '30.1.3'),
     'Greek morion (n.), part, latinized with -um': ("the final component, Greek <i>morion</i>, is latinized with the ending -um, whose gender it takes", '30.1.3'),
     'Myrmecia; Greek myrmekia (f.), ant-hill': ("the final component, Greek <i>myrmekia</i>, is feminine", '30.1.2'),
     'Greek idris, an adjective of one form for masculine and feminine (Wheeler: Hesiod\'s word for the ant)': (None, None),
     'ending -oides / -ides: masculine unless the author treated it otherwise': ("names ending in -oides or -ides are masculine unless the author treated them otherwise", '30.1.4.4'),
     'ending -ites: masculine unless the author treated it otherwise': ("names ending in -ites are masculine unless the author treated them otherwise", '30.1.4.4'),
     'a Greek adjective in its masculine form': ("the final component is a Greek adjective in its masculine form", '30.1.2'),
     'Greek adjective pachys in its masculine form': ("the final component, Greek <i>pachys</i>, is an adjective in its masculine form", '30.1.2'),
     'ending -ops': ("names ending in -ops are masculine", '30.1.4.3'),
     'ending -a (from klino, I bend)': ("it is formed from Greek <i>klino</i> with the ending -a, whose gender it takes", '30.1.3'),
     'a Greek neuter in -on': ("the final component is a Greek neuter noun in -on, unchanged", '30.1.2'),
     'a Greek neuter in -on latinized with -um': ("the final component, a Greek neuter in -on, is latinized with the ending -um", '30.1.3'),
     'Myrmica, ending -a': ("it ends in -ica, taken from Latin <i>formica</i>, feminine", '30.1.1'),
     'Greek geiton, neighbor, a word of common gender': ("the final component, Greek <i>geiton</i>, is of common gender, so masculine unless the author treated it as feminine", '30.1.4.2'),
     'Greek -keros, horned, an adjectival form of common gender': ("the final component, Greek -<i>keros</i>, is of common gender, so masculine unless the author treated it as feminine", '30.1.4.2'),
     'Greek -phanes, an adjectival ending of one form for masculine and feminine': ("the final component, Greek -<i>phanes</i>, is of common gender, so masculine unless the author treated it as feminine", '30.1.4.2'),
     'Latin -cola, inhabitant, a word of common gender': ("the final component, Latin -<i>cola</i>, is of common gender, so masculine unless the author treated it as feminine", '30.1.4.2'),
     'Greek kephalotos; ending -es, no feminine or neuter ending': ("formed from Greek <i>kephalotos</i> with the ending -es, which is not feminine or neuter", '30.1.3'),
     'ending -ma as a Greek neuter in -ma (from diakampto)': ("formed as a Greek neuter in -ma", '30.1.3'),
     'Greek glyphis (f.); or kataglyphe (f.)': ("the final component, Greek <i>glyphis</i> (or <i>kataglyphe</i>), is feminine", '30.1.2'),
     'Greek odon, odous (m.), tooth': ("the final component, Greek <i>odon</i> (<i>odous</i>), is masculine", '30.1.2'),
     'Greek Soritis (f.), a name of Ceres (Demeter)': ("the final component, Greek <i>Soritis</i>, a name of Demeter, is feminine", '30.1.2'),
     'Greek idris': (None, None),
     'Greek akros in its masculine form': (None, None),
     'an anagram; ending -on': ("it is an anagram, not a word of Latin or Greek; a name ending in -on is neuter", '30.2.4'),
     'an arbitrary or anagram name with no gender ending': ("it is not formed from a Latin or Greek word and has no ending of a gender", '30.2.4'),
     'Greek pelte (f.), shield, latinized with -a': ("the final component, Greek <i>pelte</i>, is latinized with the ending -a, whose gender it takes", '30.1.3'),
     'Greek pyge (f.), rump, latinized with -a': ("the final component, Greek <i>pyge</i>, is latinized with the ending -a, whose gender it takes", '30.1.3'),
     'Greek keraia (f.), antenna': ("the final component, Greek <i>keraia</i>, is feminine", '30.1.3'),
     'Greek xenos (m.) latinized with -us': ("the final component, Greek <i>xenos</i>, is latinized with the ending -us, whose gender it takes", '30.1.3'),
     'Greek xenos with the feminine ending -a': ("the final component, Greek <i>xenos</i>, is given the ending -a, whose gender it takes", '30.1.3'),
     'Greek notos (m.), back, latinized with -us': ("the final component, Greek <i>notos</i>, is latinized with the ending -us, whose gender it takes", '30.1.3'),
     'Greek kondylos (m.) with the ending -a': ("the final component, Greek <i>kondylos</i>, is given the ending -a, whose gender it takes", '30.1.3'),
    }
    if comp in fixed: return fixed[comp]
    return None, None

SENT_OVERRIDE = {
 'OPISTHOPSIS': ("the name ends in -opsis (Greek <i>opsis</i>, feminine)", '30.1.2'),
 'OPHTHALMOPONE': ("it ends in -pone, as do the shortened forms of <i>Ponera</i> (feminine)", '30.1.3'),
 'IRENEA': ("on either derivation the name ends in -ea, feminine", '30.1.3'),
 'LABIDUS': ("the final component, Latin <i>labidus</i> (or Greek <i>labidos</i>), has the masculine ending -us", '30.1.1'),
 'DORYLUS': ("a name ending in -us is masculine", '30.2.4'),
 'XYMMER': None,
 'CYPHOMANNIA': ("the final component is a personal name (Mann) with the ending -ia; a name ending in -ia is feminine", '30.2.4'),
}
def genus_final(r):
    """the derivation ends in another genus-group name: that name's own gender basis"""
    full = ENTRY[r['name']]['full']
    m = re.search(r"\+ ([A-Z][a-z]{3,})(?: \(q\. v\.\))?\s*$", full) or re.match(r"^[a-z][a-z\- ]*\([^)]*\) \+ ([A-Z][a-z]{3,})(?: \(q\. v\.\))?\s*$", full)
    if not m: return None
    G = m.group(1).upper()
    if G not in byname or G == r['name']: return None
    return G

def catchall(r, g):
    fw = final_word(r['name'])
    full = ENTRY[r['name']]['full']
    if fw and '+' in full[full.rfind(fw[1]):]:
        fw = None   # the last Greek or Latin word is not the final component
    end = {'masculine':'-us','feminine':'-a','neuter':'-um or -on'}[g]
    if r['name'].endswith('IA') or r['name'].endswith('EA'): end = '-ia' if r['name'].endswith('IA') else '-ea'
    if fw and fw[0] in ('Gr.','Late Gr.'):
        return f"the final component, Greek <i>{fw[1].replace('aulaks','aulax')}</i>, is latinized with the ending {end}, whose gender it takes", '30.1.3'
    if fw and fw[0] == 'L.':
        return f"the final component is Latin <i>{fw[1]}</i>, with the ending {end}", '30.1.1'
    if derivation(r['name']).startswith('Named for'):
        return f"it is formed from a personal name; a name ending in {end} is {g}", '30.2.4'
    txt = derivation(r['name'])
    m = re.search(r"<i>([a-z][a-z\-]+)</i>(?: \(<i>[a-z]+</i>\))? '[^']*' \(Wheeler", txt)
    if m and '+' not in txt[txt.find(m.group(0)):]:
        return f"the final component, Greek <i>{m.group(1)}</i>, is latinized with the ending {end}, whose gender it takes", '30.1.3'
    return f"the final component is not a Latin or Greek word; a name ending in {end} is {g}", '30.2.4'

EXTRA = {'ANERGATES': ('masculine', "the final component, Greek <i>ergates</i>, is masculine", '30.1.2'),
         'MYRMAPATETES': ('masculine', "the final component, Greek <i>patetes</i>, is masculine", '30.1.2'),
         'MYRMOTHRINAX': ('feminine', "the final component, Greek <i>thrinax</i>, is feminine", '30.1.2'),
         'LINEPITHEMA': ('neuter', "the final component, Greek <i>epithema</i>, is neuter", '30.1.2')}
out, report, held = [], [], []
byname = {r['name']: r for r in W}
prot = defaultdict(list)
for x in X:
    m = re.search(r'\(([^)]+)\)\s*$', x['protonym_name']); key = (m.group(1) if m else x['protonym_name']).upper()
    prot[key].append(x)
for r in W:
    nm = r['name']
    if nm not in prot or nm in NO_DERIV or ENTRY[nm]['full'].strip().startswith('?'): continue
    for pid in sorted({x['protonym_id'] for x in prot[nm]}):
        recs = [x for x in prot[nm] if x['protonym_id'] == pid]
        p0 = recs[0]
        if p0['etymology_taxt'] or p0['etymology_derivation']:
            held.append((nm, pid, 'has an etymology')); continue
        gs = {x['gender'] for x in recs}
        if len(gs) != 1: held.append((nm, pid, 'records differ in gender ' + str(gs))); continue
        g = gs.pop()
        text = derivation(nm)
        if nm in EXTRA:
            if EXTRA[nm][0] != g: held.append((nm, pid, 'EXTRA gender differs')); continue
            text += f" Gender {g}: {EXTRA[nm][1]} (ICZN Art. {EXTRA[nm][2]})."
        elif nm in SENT_OVERRIDE:
            if SENT_OVERRIDE[nm]:
                text += f" Gender {g}: {SENT_OVERRIDE[nm][0]} (ICZN Art. {SENT_OVERRIDE[nm][1]})."
        elif nm not in OPEN and genus_final(r) and byname[genus_final(r)]['wg'] == g:
            G = genus_final(r); rg = byname[G]
            s2, a2 = sentence(rg, g)
            if s2 is None: s2, a2 = catchall(rg, g)
            text += f" Gender {g}: the name ends in the genus-group name <i>{G.capitalize()}</i>, which is {g}: {s2} (ICZN Art. {a2.split(' / ')[0]})."
        elif nm not in OPEN:
            s, art = sentence(r, g)
            if s is None:
                if r['comp'].startswith('ending -') and 'oides' not in r['comp'] and 'ites' not in r['comp'] and 'ops' not in r['comp'] or r['comp'] == 'ending -ia / -ea, feminine':
                    s, art = catchall(r, g)
                elif 'idris' in r['comp']:
                    s, art = ("the final component, Greek <i>idris</i>, is of common gender, and the author combined the name with an adjective in the feminine", '30.1.4.2')
                else:
                    s, art = None, None
            if s is None: held.append((nm, pid, 'no gender sentence: ' + r['comp'])); continue
            if r['wg'] not in ('?', g) : held.append((nm, pid, f"rule {r['wg']} vs AntCat {g}")); continue
            text += f" Gender {g}: {s} (ICZN Art. {art.split(' / ')[0] if ' / ' not in art else art})."
        out.append([pid, p0['protonym_name'], 'wheeler1956_genus_derivation', 'etymology_derivation', text, ''])
with open('genus_derivation_input.tsv', 'w') as f:
    f.write('\t'.join(['protonym_id','protonym_name','rule','field','value','locality_md5']) + '\n')
    for o in out: f.write('\t'.join(o) + '\n')
print('rows', len(out), 'held', len(held))
for h in held: print(' HELD', h)
