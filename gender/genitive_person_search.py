#!/usr/bin/env python3
"""Read only. For each genitive epithet, look in its original description (library.sqlite) for the person's or
place's name written with a capital letter. Prints JSON lines: pid, found variant, ref, page, snippet."""
import json, re, sqlite3, sys
lib, qfile, out = sys.argv[1], sys.argv[2], sys.argv[3]
c = sqlite3.connect(lib)
Q = json.load(open(qfile))
with open(out, 'w') as fh:
    for q in Q:
        hit = None
        for ref in q['refs']:
            rows = c.execute('select c2, c0 from pages_fts_content where cast(c1 as integer) = ?', (int(ref),)).fetchall()
            for page, text in rows:
                for v in q['variants']:
                    m = re.search(r'(?<![A-Za-z])' + re.escape(v[0].upper() + v[1:]) + r'(?![a-z])', text or '')
                    if m:
                        s = (text[max(0, m.start() - 80): m.end() + 80]).replace('\n', ' ')
                        hit = dict(pid=q['pid'], variant=v[0].upper() + v[1:], ref=ref, page=page, snippet=s); break
                if hit: break
            if hit: break
        fh.write(json.dumps(hit or dict(pid=q['pid']), ensure_ascii=False) + '\n')
