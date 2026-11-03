# checklist_json.py -- builds checklist.json, the 30-row validation sample, from primary_adds.csv, review_mismatches.csv and antweb_typestatus_fixes.csv.
# Recovered verbatim on 2026-11-03 from the chat "Automating type specimen linking between
# Antcat and Antweb" (claude.ai chat 7b114e80, 8 Jun 2026, turn 37), where it ran as an inline step.
# One-off: paths and file names are the June chat's (/tmp/work, /mnt/user-data/outputs, prot.jsonl).
# Kept for the record; not maintained. See antweb_types/README.md.

import csv, json
def rd(p):
    with open(p) as f: return list(csv.DictReader(f))
padds=rd('primary_adds.csv'); mm=rd('review_mismatches.csv'); fx=rd('antweb_typestatus_fixes.csv')
prot={}
import json as J
for line in open('prot.jsonl'):
    p=J.loads(line); prot[str(p['protonym_id'])]=p

# pick varied Section A rows
def take(case,n,flagged=None):
    out=[]
    for r in padds:
        if r['case']!=case: continue
        if flagged is True and not r['material_flag']: continue
        if flagged is False and r['material_flag']: continue
        out.append(r)
        if len(out)>=n: break
    return out
A = take('specimen_addline',2,flagged=False)+take('specimen_append',1,flagged=False)+\
    take('add_depository',1)+take('full_block',2)+take('specimen_addline',2,flagged=True)

def aw_url_for(r):
    # first antweb url
    u=r.get('antweb_urls','').split(' ')[0]
    return u or ''

secA={"title":"A. AUTO — primary types to ADD to AntCat",
      "intro":"Open the AntCat link, Edit, apply the ADD text in the Primary type field, Save. Bare uppercase codes auto-hyperlink. WARNING rows have a material conflict to verify first.",
      "entries":[]}
for i,r in enumerate(A,1):
    cur=(prot.get(r['protonym_id'],{}).get('primary_type_taxt') or '(no primary type text on record)')[:240]
    lines=[f"AntCat current primary text: {cur}",
           f"Case: {r['case']}"+(f"   |   needs locality: {r['needs_locality']}" if r['needs_locality'] else ""),
           f"ADD: {r['add_text']}"]
    if r['material_flag']:
        lines.insert(0, f"\u26a0 MATERIAL CHECK: {r['material_flag']} — verify before adding")
    secA["entries"].append({
        "head":f"A{i}. {r['protonym']}  —  {r['specimen_codes']}",
        "lines":lines,
        "links":[{"label":"AntCat (open and Edit)","url":r['antcat_url']},
                 {"label":"AntWeb (check specimen)","url":aw_url_for(r)}],
        "verdict":"Verdict:  [ ] correct, added   [ ] wrong — notes:"})

def msec(title,intro,rows,verdict):
    s={"title":title,"intro":intro,"entries":[]}
    for r in rows:
        s["entries"].append({
            "head":f"{r['code']} — {r['antweb_typestatus']}",
            "lines":[f"AntCat protonym holding it: {r['antcat_protonym_holding']}"],
            "links":[{"label":"AntWeb specimen","url":r['antweb_url']},
                     {"label":"AntCat protonym","url":r['antcat_url']}],
            "verdict":verdict})
    return s

rank=[r for r in mm if r['type']=='rank'][:6]
misp=[r for r in mm if r['type']=='misplacement'][:6]
secB=msec("B. RANK — holotype/paratype disagreements","Decide which database is right; fix the wrong one.",rank,
          "Verdict:  [ ] AntWeb right   [ ] AntCat right   [ ] other — notes:")
secC=msec("C. MISPLACEMENT — specimen under the wrong protonym","Decide which is correct.",misp,
          "Verdict:  [ ] AntWeb right   [ ] AntCat right   [ ] other — notes:")
secD={"title":"D. ANTWEB NAME FIXES — correct in AntWeb",
      "intro":"Specimen correctly linked; AntWeb type_status name differs from AntCat's validated name.",
      "entries":[]}
for r in fx[:6]:
    secD["entries"].append({
        "head":f"{r['code']} — AntWeb: {r['antweb_typestatus']}",
        "lines":[f"AntCat validated protonym: {r['antcat_protonym_name']}"],
        "links":[{"label":"AntWeb (edit)","url":r['antweb_url']},
                 {"label":"AntCat (ref)","url":r['antcat_protonym_url']}],
        "verdict":"Verdict:  [ ] fixed in AntWeb   [ ] AntWeb right — notes:"})

doc={"title":"AntCat \u21c4 AntWeb Type Reconciliation — Validation Worksheet",
     "subtitle":"Click the links to open each record. Mark a verdict per row. Generated 2026-06-08.",
     "sections":[secA,secB,secC,secD]}
json.dump(doc,open('/tmp/work/checklist.json','w'))
print("checklist.json built; section A entries:",len(secA['entries']))
