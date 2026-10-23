#!/usr/bin/env python3
"""
draft_type_text.py -- draft AntCat type-field text from an NGC type block, for a reviewer
to check and paste. A DRAFT only: collector names are not italicised (NGC italics are
lost in block_text) and citations are plain text, not {ref} links.

  from draft_type_text import draft
  primary, secondary, notes = draft(ngc_type_block_lines)
"""
import re

PRIMARY = re.compile(r'\b(holotype|lectotype|neotype|syntype|syntypes)\b', re.I)


def split_top(s, sep=','):
    """split on sep outside parentheses"""
    out, depth, cur = [], 0, ''
    for ch in s:
        depth += ch == '('
        depth -= ch == ')'
        if ch == sep and depth == 0:
            out.append(cur.strip()); cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _label(kind, tier, plural):
    names = {'material': ('type material', 'type material'), 'locality': ('type locality', 'type localities'),
             'depository': ('type depository', 'type depositories')}
    return f"{tier} {names[kind][1 if plural else 0]}:"


def draft(lines):
    prim, seco, notes = [], [], []
    for line in lines:
        line = line.strip()
        if line.startswith('['):
            body = re.sub(r'^\[Notes?\s*(\(i\))?\s*:?\s*', '', line).rstrip(']').strip()
            notes += [x.strip().rstrip(';') for x in re.split(r';?\s*\((?:i|ii|iii|iv|v|vi)\)\s*', body) if x.strip()]
            continue
        m = re.match(r'^(Type-material|Type-localit(?:y|ies)|Type-depositor(?:y|ies))\s*:\s*(.*)$', line, re.I)
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2).strip().rstrip('.]').rstrip('.')
        if key == 'type-material':
            parts = split_top(val)
            p = [x for x in parts if PRIMARY.search(x) and not re.search(r'\bpara', x, re.I)]
            s = [x for x in parts if x not in p]
            if p: prim.append(f"{_label('material', 'Primary', False)} {', '.join(p)}.")
            if s: seco.append(f"{_label('material', 'Secondary', False)} {', '.join(s)}.")
        elif key.startswith('type-localit'):
            mm = re.split(r';\s*(?:paratypes?|paralectotypes?)\s*:?\s*', val, maxsplit=1, flags=re.I)
            p = re.sub(r'^\s*(holotype|lectotype|neotype)\s+', '', mm[0], flags=re.I).strip()
            prim.append(f"{_label('locality', 'Primary', key.endswith('ies') and len(mm) == 1)} {p}.")
            if len(mm) > 1:
                sl = re.sub(r'^with same data\b', 'same as for holotype', mm[1].strip(), flags=re.I)
                seco.append(f"{_label('locality', 'Secondary', False)} {sl}.")
        else:
            pp, ss = [], []
            for seg in split_top(val, ';'):
                role = re.search(r'\(([^)]*)\)\s*$', seg)
                codes = re.sub(r'\s*\((?:holotype|lectotype|neotype|syntypes?|paratypes?|paralectotypes?)\)\s*$', '', seg, flags=re.I).strip()
                tag = role.group(1).lower() if role else ''
                (ss if 'para' in tag else pp).append(codes)
            if pp:
                n = sum(len(split_top(x)) for x in pp)
                prim.append(f"{_label('depository', 'Primary', n > 1)} {', '.join(pp)}.")
            if ss:
                n = sum(len(split_top(x)) for x in ss)
                seco.append(f"{_label('depository', 'Secondary', n > 1)} {', '.join(ss)}.")
    notes = [n[:1].upper() + n[1:] for n in notes]
    if len(notes) > 1:
        note_txt = ' '.join(f"{i}) {n.rstrip('.')}." for i, n in enumerate(notes, 1))
    else:
        note_txt = (notes[0].rstrip('.') + '.') if notes else ''
    return ' '.join(prim), ' '.join(seco), note_txt
