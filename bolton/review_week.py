#!/usr/bin/env python3
"""
review_week.py -- assemble a reviewer's week as one workbook: a Read me and one tab per day.

Each day is a CSV of rows plus a short spec (title, minutes per row, what to do, which
columns the reviewer fills in). The estimate printed on each tab is the sum of each
row's minutes (its "min" field, else the day's minutes_per_row), so the returned
workbook and the AntCat activity log can be checked against it.

  python3 bolton/review_week.py --spec week.json --xlsx out.xlsx

week.json:
  {"title": "...", "intro": ["line", ...], "assumptions": ["line", ...],
   "days": [{"tab": "Day 1", "title": "...", "csv": "path.csv", "minutes_per_row": 3,
             "extra_minutes": 0, "what": ["line", ...],
             "columns": [["csv_field", "Header", width], ...],
             "inputs": [["Header", width, ["choice", ...] or null], ...],
             "link": "csv_field holding a URL for the first column (optional)"}]}
"""
import argparse, csv, json, math
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

FONT = 'Arial'
YELLOW = PatternFill('solid', start_color='FFFF99')


def minutes(day, rows):
    """a row's own "min" field wins over the day's minutes_per_row"""
    return sum(float(r.get('min') or day.get('minutes_per_row', 0)) for r in rows) + day.get('extra_minutes', 0)


def hm(m):
    h, r = divmod(int(math.ceil(m / 15.0) * 15), 60)
    return f"{h} h {r:02d} min" if h else f"{r} min"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--spec', required=True)
    ap.add_argument('--xlsx', required=True)
    a = ap.parse_args()
    spec = json.load(open(a.spec, encoding='utf-8'))
    days = []
    for d in spec['days']:
        rows = list(csv.DictReader(open(d['csv'], encoding='utf-8')))
        days.append((d, rows))

    wb = Workbook()
    rd = wb.active; rd.title = 'Read me'
    lines = [(spec['title'], 'h1')] + [(t, '') for t in spec.get('intro', [])] + [('', '')]
    lines.append(('The week', 'h2'))
    total = 0
    for d, rows in days:
        m = minutes(d, rows); total += m
        lines.append((f"{d['tab']}: {d['title']} ({len(rows)} items, about {hm(m)})", ''))
    lines.append((f"Total: about {hm(total)}.", ''))
    lines += [('', ''), ('How the estimates were made', 'h2')] + [(t, '') for t in spec.get('assumptions', [])]
    lines += [('', ''), ('What to fill in', 'h2'),
              ('Only the yellow columns. Where a column has a list, pick from it. Each first-column number links to the record in AntCat.', ''),
              ('Each day is independent: finish a day before starting the next, and send the workbook back at the end of the week.', '')]
    for i, (t, kind) in enumerate(lines, 1):
        c = rd.cell(row=i, column=1, value=t)
        c.font = Font(name=FONT, bold=bool(kind), size=12 if kind == 'h1' else 10)
        c.alignment = Alignment(wrap_text=True, vertical='top')
    rd.column_dimensions['A'].width = 125

    for d, rows in days:
        ws = wb.create_sheet(d['tab'])
        head = [f"{d['title']} -- {len(rows)} items, about {hm(minutes(d, rows))}"] + d.get('what', [])
        for i, t in enumerate(head, 1):
            c = ws.cell(row=i, column=1, value=t)
            c.font = Font(name=FONT, bold=(i == 1), size=11 if i == 1 else 10)
        hr = len(head) + 2
        cols = d['columns']; ins = d.get('inputs', [])
        for j, (_, h, w) in enumerate(cols, 1):
            c = ws.cell(row=hr, column=j, value=h); c.font = Font(name=FONT, bold=True)
            c.alignment = Alignment(wrap_text=True, vertical='top')
            ws.column_dimensions[c.column_letter].width = w
        dvs = []
        for k, (h, w, choices) in enumerate(ins, len(cols) + 1):
            c = ws.cell(row=hr, column=k, value=h); c.font = Font(name=FONT, bold=True); c.fill = YELLOW
            ws.column_dimensions[c.column_letter].width = w
            if choices:
                dv = DataValidation(type='list', formula1='"' + ','.join(choices) + '"', allow_blank=True)
                ws.add_data_validation(dv); dvs.append((k, dv))
        for r in rows:
            vals = [r.get(f, '') for f, _, _ in cols]
            if vals and str(vals[0]).isdigit():
                vals[0] = int(vals[0])
            ws.append(vals + [''] * len(ins))
            n = ws.max_row
            for j in range(1, len(cols) + len(ins) + 1):
                c = ws.cell(row=n, column=j)
                c.font = Font(name=FONT, size=10)
                c.alignment = Alignment(wrap_text=True, vertical='top')
                if j > len(cols):
                    c.fill = YELLOW
            if d.get('link') and r.get(d['link']):
                c = ws.cell(row=n, column=1); c.hyperlink = r[d['link']]
                c.font = Font(name=FONT, size=10, color='0000EE', underline='single')
            for k, dv in dvs:
                dv.add(ws.cell(row=n, column=k))
        ws.freeze_panes = f'A{hr + 1}'   # after the rows: touching row hr+1 earlier makes append skip it
    wb.save(a.xlsx)
    print(f"wrote {a.xlsx}: " + ', '.join(f"{d['tab']} {len(r)} ({hm(minutes(d, r))})" for d, r in days)
          + f"; total {hm(total)}")


if __name__ == '__main__':
    main()
