#!/usr/bin/env python3
"""The 25 AntCat genus-group names explained in Wheeler & Wheeler 1984b and not in Wheeler 1956: input for
write_protonym_fields.rb (rule wheeler1956_genus_derivation, which accepts either citation). Texts read from
the page images of the second edition (AntCat reference 129916). Printed page = PDF page - 2."""
C = lambda p: f" (Wheeler & Wheeler, 1984b: {p})."
G = lambda g, s, a: f" Gender {g}: {s} (ICZN Art. {a})."
MYRMA = ("feminine", "the final component, -<i>myrma</i>, is Greek <i>myrmos</i> latinized with the ending -a, whose gender it takes", "30.1.3")
MYRMEX = ("masculine", "the final component, Greek <i>myrmex</i>, is masculine", "30.1.2")
GENYS = ("feminine", "the final component, Greek <i>genys</i>, is feminine", "30.1.2")
PONERA = ("feminine", "the final component is <i>Ponera</i> (feminine), Greek <i>poneros</i> latinized with the ending -a", "30.1.3")
ROWS = [
 (155621, "Ankylomyrma", "From Greek <i>ankylos</i> 'bent, hooked, crooked' + Greek <i>myrmos</i> 'ant'", 5, MYRMA),
 (155473, "Antichthonidris", "From Greek <i>antichthon</i> 'Southern Hemisphere' + Greek <i>idris</i> 'ant'", 5, None),
 (155763, "Apomyrma", "From Greek <i>apo-</i> 'separate, without, away from, off' + Greek <i>myrmos</i> 'ant'", 5, MYRMA),
 (155317, "Asketogenys", "From Greek <i>asketos</i> 'curiously wrought, ornamental' + Greek <i>genys</i> 'jaw'", 5, GENYS),
 (155674, "Brownidris", "From a latinization of the surname of W. L. Brown, American myrmecologist, + Greek <i>idris</i> 'ant'", 6, None),
 (154742, "Calyptites", "From Greek <i>kalyptos</i> 'covered, hidden' + Greek -<i>ites</i> 'like'", 6, None),
 (155318, "Cladarogenys", "From Greek <i>kladaros</i> 'fragile' + Greek <i>genys</i> 'jaw'", 7, GENYS),
 (155767, "Concoctio", "From Latin <i>concoctus</i> 'cooked together'", 7, ("feminine", "the name has the form of the Latin feminine noun <i>concoctio</i>, and the author combined it with the feminine <i>concenta</i>", "30.1.1")),
 (155379, "Dacetinops", "From <i>Daceton</i> + Greek <i>ops</i> 'like'", 7, ("masculine", "names ending in -ops are masculine", "30.1.4.3")),
 (155811, "Dolioponera", "From Greek <i>dolios</i> 'crafty, deceitful' + <i>Ponera</i>", 8, PONERA),
 (155933, "Eoponera", "From Greek <i>eos</i> 'dawn' + <i>Ponera</i>", 9, PONERA),
 (155265, "Eurhopalothrix", "From Greek <i>eu-</i> 'good, well' + <i>Rhopalothrix</i>", 9, ("feminine", "the final component, Greek <i>thrix</i>, is feminine", "30.1.2")),
 (155743, "Myrmicites", "From <i>Myrmica</i> + Greek -<i>ites</i> 'like'", 13, ("masculine", "names ending in -ites are masculine unless the author treated them otherwise", "30.1.4.4")),
 (154833, "Neoforelius", "From Greek <i>neos</i> 'new' (i.e., New World) + <i>Forelius</i>", 13, ("masculine", "the name ends in the genus-group name <i>Forelius</i>, formed from a personal name with the ending -us; a name ending in -us is masculine", "30.2.4")),
 (154751, "Noonilla", "From the Noona Dan Expedition + <i>Leptanilla</i>", 13, ("feminine", "it ends in -illa, as <i>Leptanilla</i>, the Latin feminine diminutive suffix", "30.1.1")),
 (155471, "Nothidris", "From Greek <i>nothos</i> 'spurious, counterfeit' + Greek <i>idris</i> 'ant'", 13, None),
 (155511, "Paramyrmica", "From Greek <i>para-</i> 'beside, near' + <i>Myrmica</i>", 14, ("feminine", "the name ends in the genus-group name <i>Myrmica</i>, which is feminine: it ends in -ica, taken from Latin <i>formica</i>, feminine", "30.1.1")),
 (154934, "Petalomyrmex", "From Greek <i>petalos</i> 'flattened' + Greek <i>myrmex</i> 'ant'", 15, MYRMEX),
 (155321, "Phalacromyrmex", "From Greek <i>phalakros</i> 'bald, smooth' + Greek <i>myrmex</i> 'ant'", 15, MYRMEX),
 (155322, "Pilotrochus", "From Greek <i>pilos</i> 'hair' + Greek <i>trochos</i> 'wheel'", 15, ("masculine", "the final component, Greek <i>trochos</i>, is latinized with the ending -us, whose gender it takes", "30.1.3")),
 (155267, "Protalaridris", "From Greek <i>pro-</i> 'before' + Greek <i>talaros</i> 'wicker basket' + Greek <i>idris</i> 'ant' (<i>Talaridris</i>, a synonym of <i>Rhopalothrix</i>)", 16, ("feminine", "the final component, Greek <i>idris</i>, is of common gender, and the author combined the name with an adjective in the feminine", "30.1.4.2")),
 (154760, "Scyphodon", "From Greek <i>skyphos</i> 'cup' + Greek -<i>odon</i> 'tooth'", 17, ("masculine", "the final component, Greek <i>odon</i> (<i>odous</i>), is masculine", "30.1.2")),
 (155924, "Sphecomyrma", "From Greek <i>sphex</i> (<i>sphekos</i>) 'wasp' + Greek <i>myrmos</i> 'ant'", 17, MYRMA),
 (155749, "Tatuidris", "From Tupi and Brazilian <i>tatu</i> 'armadillo' + Greek <i>idris</i> 'ant'", 18, None),
 (154910, "Teratomyrmex", "From Greek <i>teras</i> (<i>teratos</i>) 'wonder, marvel, monstrosity' + Greek <i>myrmex</i> 'ant'", 18, MYRMEX),
]
with open('genus_derivations_1984_input.tsv', 'w') as f:
    f.write('protonym_id\tprotonym_name\trule\tfield\tvalue\tlocality_md5\n')
    for pid, name, body, page, g in ROWS:
        text = body + C(page) + (G(*g) if g else '')
        f.write(f"{pid}\t{name}\twheeler1956_genus_derivation\tetymology_derivation\t{text}\t\n")
print(len(ROWS))
