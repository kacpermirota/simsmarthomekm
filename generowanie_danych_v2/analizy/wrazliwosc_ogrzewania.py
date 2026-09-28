"""
Analiza wrażliwości modelu ogrzewania: jak wynik główny zmienia się w
zależności od założeń dotyczących pracy grzejnika i długości okna
grzewczego.

Nie modyfikuje generator.py/profile_urzadzen.py/logika_automatyzacji.py/
model_obecnosci.py. Importuje istniejące funkcje, przelicza energię per
urządzenie z gotowych próbek i stosuje mnożniki k (współczynnik pracy
grzejnika) i f (udział energii "oszczędzonej" zużywany na ponowne
nagrzanie) poza generatorem, na wynikowej energii grzejników.

Uruchomienie: python analizy/wrazliwosc_ogrzewania.py
"""
from __future__ import annotations
import sys, os, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import generator as g
import profile_urzadzen as pu

GRZEJNIKI = ("grzejnik_salon", "grzejnik_korytarz_pietro")


def energie_per_urzadzenie(seed=42, parametry=None):
    b, a = g.generuj_serie(parametry=parametry, seed=seed)
    h = g.INTERWAL_MIN / 60 / 1000  # W*probka -> kWh
    nazwy = list(b[0][1].keys())
    e_przed = {n: sum(d[n] for _, d in b) * h for n in nazwy}
    e_po = {n: sum(d[n] for _, d in a) * h for n in nazwy}
    return e_przed, e_po


def asercja_bazowa(e_przed, e_po):
    tot_przed = sum(e_przed.values())
    tot_po = sum(e_po.values())
    assert abs(tot_przed - 968.07) < 0.01, f"ASERCJA NIEUDANA: przed={tot_przed:.2f}"
    assert abs(tot_po - 585.89) < 0.01, f"ASERCJA NIEUDANA: po={tot_po:.2f}"
    return tot_przed, tot_po


def wariant(e_przed, e_po, k, f, laptopy_bez_oszczednosci=False):
    """Zwraca (energia_przed, energia_po, redukcja_kwh, redukcja_pct) dla danego
    (k, f), stosowanych WYŁĄCZNIE do grzejników; reszta urządzeń bez zmian."""
    przed = dict(e_przed)
    po = dict(e_po)

    for n in GRZEJNIKI:
        przed[n] = e_przed[n] * k
        po_bazowe = e_po[n] * k
        oszczedzone = przed[n] - po_bazowe
        po[n] = po_bazowe + f * oszczedzone

    if laptopy_bez_oszczednosci:
        po["komputery_pokoj_dzieci"] = przed["komputery_pokoj_dzieci"]

    tot_przed = sum(przed.values())
    tot_po = sum(po.values())
    red_kwh = tot_przed - tot_po
    red_pct = red_kwh / tot_przed * 100
    return tot_przed, tot_po, red_kwh, red_pct


def main():
    e_przed, e_po = energie_per_urzadzenie(seed=42)
    tot_przed0, tot_po0 = asercja_bazowa(e_przed, e_po)
    print(f"Asercja wyniku glownego OK: przed={tot_przed0:.2f} kWh, po={tot_po0:.2f} kWh")

    K = (0.3, 0.5, 0.7, 1.0)
    F = (0.0, 0.25, 0.5)

    os.makedirs(os.path.join(os.path.dirname(__file__), 'wyniki'), exist_ok=True)

    # --- A1 ---
    a1 = []
    for k in K:
        for f in F:
            tp, tpo, red, redp = wariant(e_przed, e_po, k, f)
            a1.append((k, f, tp, tpo, red, redp))

    k1f0 = [r for r in a1 if r[0] == 1.0 and r[1] == 0.0][0]
    assert abs(k1f0[2] - 968.07) < 0.01 and abs(k1f0[3] - 585.89) < 0.01, "A1: wariant bazowy sie nie zgadza"
    print(f"A1 wariant bazowy (k=1,0 f=0): przed={k1f0[2]:.2f} po={k1f0[3]:.2f} red={k1f0[5]:.2f}%")

    print("\nTabela A1 (k=wspolczynnik pracy grzejnika, f=udzial ponownego nagrzania):")
    print(f"{'k':>5} {'f':>5} {'przed[kWh]':>12} {'po[kWh]':>10} {'red[kWh]':>10} {'red[%]':>8}")
    for k, f, tp, tpo, red, redp in a1:
        print(f"{k:5.1f} {f:5.2f} {tp:12.2f} {tpo:10.2f} {red:10.2f} {redp:8.2f}")

    with open(os.path.join(os.path.dirname(__file__), 'wyniki', 'a1_wrazliwosc_ogrzewania.csv'), 'w', newline='', encoding='utf-8') as fp:
        w = csv.writer(fp)
        w.writerow(['k', 'f', 'energia_przed_kwh', 'energia_po_kwh', 'redukcja_kwh', 'redukcja_pct'])
        for row in a1:
            w.writerow([f"{row[0]:.2f}", f"{row[1]:.2f}"] + [f"{x:.2f}" for x in row[2:]])

    # --- A2: laptopy bez oszczednosci ---
    a2 = []
    for k in K:
        for f in F:
            tp, tpo, red, redp = wariant(e_przed, e_po, k, f, laptopy_bez_oszczednosci=True)
            a2.append((k, f, tp, tpo, red, redp))

    k1f0_a2 = [r for r in a2 if r[0] == 1.0 and r[1] == 0.0][0]
    print(f"\nA2 wariant bazowy (k=1,0 f=0, laptopy bez oszczednosci): przed={k1f0_a2[2]:.2f} po={k1f0_a2[3]:.2f} red={k1f0_a2[5]:.2f}%")

    print("\nTabela A2 (jak A1, ale energia komputerow w 'po' = energia w 'przed'):")
    print(f"{'k':>5} {'f':>5} {'przed[kWh]':>12} {'po[kWh]':>10} {'red[kWh]':>10} {'red[%]':>8}")
    for k, f, tp, tpo, red, redp in a2:
        print(f"{k:5.1f} {f:5.2f} {tp:12.2f} {tpo:10.2f} {red:10.2f} {redp:8.2f}")

    with open(os.path.join(os.path.dirname(__file__), 'wyniki', 'a2_laptopy_bez_oszczednosci.csv'), 'w', newline='', encoding='utf-8') as fp:
        w = csv.writer(fp)
        w.writerow(['k', 'f', 'energia_przed_kwh', 'energia_po_kwh', 'redukcja_kwh', 'redukcja_pct'])
        for row in a2:
            w.writerow([f"{row[0]:.2f}", f"{row[1]:.2f}"] + [f"{x:.2f}" for x in row[2:]])

    redp_all = [r[5] for r in a1]
    print(f"\nZakres redukcji w siatce A1: {min(redp_all):.2f}% do {max(redp_all):.2f}%")

    # --- A3: dlugosc okna grzewczego (12h/14h/16h), k=1,0 f=0 ---
    # Realizacja: tymczasowa podmiana profilu grzejnikow W PAMIECI procesu
    # (profile_urzadzen.PROFILE), przywrocona zaraz po pomiarze. Plik
    # profile_urzadzen.py NIE jest modyfikowany. Okno domyslne 16h = 6-22,
    # symetrycznie skracane wokol tego samego srodka.
    print("\nTabela A3 (dlugosc okna grzewczego, k=1,0 f=0):")
    print(f"{'okno[h]':>8} {'przed[kWh]':>12} {'po[kWh]':>10} {'red[kWh]':>10} {'red[%]':>8}")
    oryg = {n: pu.PROFILE[n] for n in GRZEJNIKI}
    a3 = []
    try:
        for godz in (12, 14, 16):
            pol = godz / 2
            srodek = 14.0  # srodek okna 6-22
            start = srodek - pol
            koniec = srodek + pol
            for n in GRZEJNIKI:
                stary = oryg[n]
                pu.PROFILE[n] = pu.ProfilUrzadzenia(stary.moc_w, [(start, koniec)])
            ep, epo = energie_per_urzadzenie(seed=42)
            tp, tpo, red, redp = wariant(ep, epo, 1.0, 0.0)
            a3.append((godz, tp, tpo, red, redp))
            print(f"{godz:8d} {tp:12.2f} {tpo:10.2f} {red:10.2f} {redp:8.2f}")
    finally:
        for n in GRZEJNIKI:
            pu.PROFILE[n] = oryg[n]

    with open(os.path.join(os.path.dirname(__file__), 'wyniki', 'a3_dlugosc_okna_grzewczego.csv'), 'w', newline='', encoding='utf-8') as fp:
        w = csv.writer(fp)
        w.writerow(['okno_h', 'energia_przed_kwh', 'energia_po_kwh', 'redukcja_kwh', 'redukcja_pct'])
        for row in a3:
            w.writerow([row[0]] + [f"{x:.2f}" for x in row[1:]])

    a3_16 = [r for r in a3 if r[0] == 16][0]
    assert abs(a3_16[1] - 968.07) < 0.01 and abs(a3_16[2] - 585.89) < 0.01, "A3: wariant 16h (domyslny) nie odtwarza wyniku glownego"
    print(f"\nA3 kontrola: wariant 16h odtwarza wynik glowny (przed={a3_16[1]:.2f}, po={a3_16[2]:.2f}) - OK")


if __name__ == '__main__':
    main()
