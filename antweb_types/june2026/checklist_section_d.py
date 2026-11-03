# checklist_section_d.py -- rebuilds Section D of checklist.json from the corrected fix list (fix_type labels).
# Recovered verbatim on 2026-11-03 from the chat "Automating type specimen linking between
# Antcat and Antweb" (claude.ai chat 7b114e80, 8 Jun 2026, turn 40), where it ran as an inline step.
# One-off: paths and file names are the June chat's (/tmp/work, /mnt/user-data/outputs, prot.jsonl).
# Kept for the record; not maintained. See antweb_types/README.md.

import json
# update Section D in checklist.json to show fix_type, from refreshed fixes
import csv
fx=list(csv.DictReader(open('antweb_typestatus_fixes.csv')))
d=json.load(open('checklist.json'))
# rebuild section D (last section)
secD={"title":"D. ANTWEB NAME FIXES — correct in AntWeb",
      "intro":"Specimen correctly linked; AntWeb type_status name needs fixing. current_combination = AntWeb used a current genus instead of the protonym; spelling = epithet typo.",
      "entries":[]}
# take 3 current_combination + 3 spelling for variety
cc=[r for r in fx if r['fix_type']=='current_combination'][:3]
sp=[r for r in fx if r['fix_type']=='spelling'][:3]
for r in cc+sp:
    secD["entries"].append({
        "head":f"{r['code']} — [{r['fix_type']}]  AntWeb: {r['antweb_typestatus']}",
        "lines":[f"AntCat protonym (correct): {r['antcat_protonym_name']}"],
        "links":[{"label":"AntWeb (edit)","url":r['antweb_url']},
                 {"label":"AntCat (ref)","url":r['antcat_protonym_url']}],
        "verdict":"Verdict:  [ ] fixed in AntWeb   [ ] AntWeb right — notes:"})
d["sections"][-1]=secD
json.dump(d,open('checklist.json','w'))
print("Section D rebuilt:",len(secD["entries"]),"entries (3 current_combination + 3 spelling)")
