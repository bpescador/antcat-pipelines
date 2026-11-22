# -*- coding: utf-8 -*-
# Builds the derivation texts for the 411 genus-group protonyms from deriv_data.py and checks them.
import csv, re, sys, collections
sys.path.insert(0, '.')
from deriv_data import D

rows = {r['protonym_id']: r for r in csv.DictReader(open('remaining_411.tsv'), delimiter='\t')}
PERSON_US = {'154803', '154854', '154878', '200928'}
GREEK_A = {'gnathos', 'pelte', 'ophthalmos', 'sphinktos', 'morphe'}
LATIN_A = {'nodus', 'petiolus'}
GEN_ART = {'Aneuretus': '30.1.3', 'Leptothorax': '30.1.2', 'Ectatomma': '30.1.2', 'Leptanilla': '30.1.1', 'Acantholepis': '30.1.2',
           'Lasius': '30.1.3', 'Pheidole': '30.1.3', 'Tapinoma': '30.1.2', 'Cerapachys': '30.1.2'}
NOT_LG = "not formed from a Latin or Greek word, and its author indicated no gender; a name so formed is feminine when it ends in -a (ICZN Art. 30.2.4)."

def gender_sentence(pid, key):
    if key is None: return None
    if key.startswith('Gender '): return key
    k, _, arg = key.partition(':')
    if k in ('MYRMA', 'MYRMA_STATED'):
        return "Gender feminine: the final component, -myrma, is Greek <i>myrmos</i> latinized with the ending -a, whose gender it takes (ICZN Art. 30.1.3)."
    if k == 'MYRMEX': return "Gender masculine: the final component, Greek <i>myrmex</i>, is masculine (ICZN Art. 30.1.2)."
    if k == 'PONE': return "Gender feminine: the final component, -pone, is a shortened Ponera (feminine) (ICZN Art. 30.1.3)."
    if k == 'PONERA': return "Gender feminine: the final component is Ponera (feminine), Greek <i>poneros</i> latinized with the ending -a (ICZN Art. 30.1.3)."
    if k == 'FORMICA': return "Gender feminine: the final component, Latin <i>formica</i>, is feminine (ICZN Art. 30.1.1)."
    if k == 'MYRMICA': return "Gender feminine: the name ends in the genus-group name Myrmica, Greek <i>myrmex</i> latinized with the ending -a, whose gender it takes (ICZN Art. 30.1.3)."
    if k == 'MECIA': return "Gender feminine: it ends in -mecia, from Myrmecia, Greek <i>myrmekia</i> 'ant-hill', which is feminine (ICZN Art. 30.1.2)."
    if k == 'ITES': return "Gender masculine: names ending in -ites are masculine unless the author treated them otherwise (ICZN Art. 30.1.4.4)."
    if k == 'ODES': return "Gender masculine: names ending in -odes or -oides are masculine unless the author treated them otherwise (ICZN Art. 30.1.4.4)."
    if k == 'ELLA': return "Gender feminine: it ends in the Latin feminine diminutive suffix -ella (ICZN Art. 30.1.1)."
    if k == 'OPSIS': return "Gender feminine: the final component, Greek <i>opsis</i>, is feminine (ICZN Art. 30.1.2)."
    if k == 'GASTER': return "Gender feminine: the final component, Greek <i>gaster</i>, is feminine (ICZN Art. 30.1.2)."
    if k == 'US': return f"Gender masculine: the final component, Greek <i>{arg}</i>, is latinized with the ending -us, whose gender it takes (ICZN Art. 30.1.3)."
    if k == 'US_LATIN':
        if pid in PERSON_US:
            return "Gender masculine: not formed from a Latin or Greek word, and its author indicated no gender; a name so formed is masculine unless it ends in -a, -um, -on or -u (ICZN Art. 30.2.4)."
        return "Gender masculine: it ends in the Latin masculine ending -us (ICZN Art. 30.1.3)."
    if k == 'A':
        if arg == 'struma': return "Gender feminine: the final component, Latin <i>struma</i>, is feminine (ICZN Art. 30.1.1)."
        lang = 'Greek' if arg in GREEK_A else 'Latin'
        return f"Gender feminine: the final component, {lang} <i>{arg}</i>, is latinized with the ending -a, whose gender it takes (ICZN Art. 30.1.3)."
    if k == 'GENUS':
        g, gen = arg.split(':')[1], arg.split(':')[0]
        return f"Gender {g}: the name ends in the genus-group name {gen}, which is {g} (ICZN Art. {GEN_ART[gen]})."
    if k in ('IA_PLACE', 'IA_PERSON', 'IA_ARBITRARY'):
        if pid == '155912':
            return "Gender feminine: not formed from a Latin or Greek word; its authors stated that it is feminine (ICZN Art. 30.2.2)."
        return "Gender feminine: " + NOT_LG
    if k == 'IA_MASC':
        return "Gender masculine: not formed from a Latin or Greek word, and its author indicated no gender; a name so formed is masculine unless it ends in -a, -um, -on or -u (ICZN Art. 30.2.4)."
    if k == 'IA_GREEK': return "Gender feminine: it is formed from Greek and latinized with the ending -a, whose gender it takes (ICZN Art. 30.1.3)."
    if k == 'IA_LATIN': return "Gender feminine: it is formed from Latin with the ending -a, whose gender it takes (ICZN Art. 30.1.3)."
    if k == 'IDRIS_FEM_ADJ':
        return ("Gender feminine: Greek <i>idris</i> is a word of masculine and feminine gender (Liddell-Scott-Jones: ὁ, ἡ), used as an adjective, "
                "'knowing, skilful', and of the ant; a genus-group name ending in it is masculine unless its author treated it as feminine, and the "
                f"original work combines it with the feminine adjective <i>{arg}</i> (ICZN Art. 30.1.4.2).")
    if k == 'IDRIS_FEM_STATED':
        return ("Gender feminine: Greek <i>idris</i> is a word of masculine and feminine gender (Liddell-Scott-Jones: ὁ, ἡ), used as an adjective, "
                "'knowing, skilful', and of the ant; a genus-group name ending in it is masculine unless its author treated it as feminine, and "
                f"{arg} stated that it is feminine (ICZN Art. 30.1.4.2).")
    raise KeyError(key)

out = []
problems = []
missing = sorted(set(rows) - set(D)); extra = sorted(set(D) - set(rows))
for pid, r in rows.items():
    if pid not in D: continue
    text, cite, gkey = D[pid]
    recorded = r['gender']
    text = text.strip()
    if re.search(r'[<>]', re.sub(r'</?i>', '', text)): problems.append((pid, 'markup'))
    if text.count('<i>') != text.count('</i>'): problems.append((pid, 'unbalanced i'))
    first = r['authorship']
    value = text + (f" ({first}: {cite})." if cite else ".")
    g = gender_sentence(pid, gkey)
    stated = None
    if g:
        stated = re.match(r'Gender (masculine|feminine|neuter):', g).group(1)
        if '/' in recorded or stated != recorded:
            problems.append((pid, f'gender {stated} vs recorded {recorded}'))
            g = None
    if g: value += ' ' + g
    out.append((pid, r['name'], value, stated if g else '', recorded))

print('missing', missing, 'extra', extra)
for p in problems: print('PROBLEM', p[0], rows[p[0]]['name'], p[1])
with open('genus_derivations_other_20261121.tsv', 'w') as f:
    f.write('protonym_id\tprotonym_name\tgender_in_text\trecorded_gender\tvalue\n')
    for o in out: f.write('\t'.join([o[0], o[1], o[3], o[4], o[2]]) + '\n')
print('rows', len(out), 'with gender sentence', sum(1 for o in out if o[3]))
lens = [len(o[2]) for o in out]; print('max len', max(lens))
