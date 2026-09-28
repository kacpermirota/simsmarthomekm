"""
Analiza ablacyjna scenariuszy automatyzacji: wklad kazdego z czterech
scenariuszy osobno w wynikowa redukcje energii.

Nie modyfikuje generator.py/profile_urzadzen.py/logika_automatyzacji.py/
model_obecnosci.py. Odtwarza petle generuj_serie() z generator.py, ale
pozwala wylaczyc wybrane wyzwalacze (podstawiajac puste listy przedzialow
zamiast wynikow funkcji logiki), zeby zmierzyc wklad KAZDEGO scenariusza
z osobna, przy tej samej, wspoldzielonej realizacji zachowania domownikow
(ten sam seed=42, te same zdarzenia czujnikow i przesuniecia okien).

Mapowanie scenariusz -> wyzwalacz (wg automations.yaml / generator.py):
  scenariusz 1 (tryb nieobecnosci)      -> wyzwalacz_a, wyzwalacz_b
  scenariusz 2 (oswietlenie od obecnosci)-> oswietlenie_wiatrolap_on, oswietlenie_korytarz_on
  scenariusz 3 (harmonogram ogrzewania) -> ogrzewanie_wyl
  scenariusz 4 (kontrola rodzicielska)  -> laptopy_wyl

Uwaga: grzejniki sa wylaczane przez SUME warunkow scenariusza 1 i 3
(ogrzewanie_wyl LUB wyzwalacz_a LUB wyzwalacz_b) - to jest zrodlo mozliwej
interakcji (nakladania sie) miedzy tymi dwoma scenariuszami.

Uruchomienie: python analizy/ablacja_scenariuszy.py
"""
from __future__ import annotations
import sys, os, csv
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import generator as g
import logika_automatyzacji as logika
import model_obecnosci as obecnosc


def energia(probki):
    h = g.INTERWAL_MIN / 60 / 1000
    return sum(sum(d.values()) for _, d in probki) * h


def generuj_z_wybranymi_scenariuszami(scenariusze_wl: set[int], seed=42):
    """Kopia petli generuj_serie(), z mozliwoscia wylaczenia scenariuszy 1-4."""
    poczatek = datetime.combine(g.START, datetime.min.time())
    koniec = poczatek + timedelta(days=g.LICZBA_DNI)

    zd = obecnosc.generuj_zdarzenia(g.START, g.LICZBA_DNI, None, seed)

    wyzwalacz_a = logika.wyzwalacz_a_wychodze(zd) if 1 in scenariusze_wl else []
    wyzwalacz_b = logika.wyzwalacz_b_wnioskowanie(zd, poczatek, koniec) if 1 in scenariusze_wl else []
    ogrzewanie_wyl = logika.harmonogram_ogrzewania(poczatek, koniec) if 3 in scenariusze_wl else []
    laptopy_wyl = logika.kontrola_rodzicielska(poczatek, koniec) if 4 in scenariusze_wl else []
    oswietlenie_wiatrolap_on = logika.oswietlenie_od_obecnosci(zd.ruch_wiatrolap) if 2 in scenariusze_wl else []
    oswietlenie_korytarz_on = logika.oswietlenie_od_obecnosci(zd.ruch_korytarz) if 2 in scenariusze_wl else []
    przesuniecia = g._losuj_przesuniecia_okien(g.START, g.LICZBA_DNI, seed)

    probki_baseline = []
    probki_po = []
    t = poczatek
    krok = timedelta(minutes=g.INTERWAL_MIN)
    while t < koniec:
        baseline, po = g.oblicz_moc_urzadzen(
            t, poczatek, wyzwalacz_a, wyzwalacz_b, ogrzewanie_wyl,
            oswietlenie_wiatrolap_on, oswietlenie_korytarz_on, laptopy_wyl,
            przesuniecia,
        )
        if 2 not in scenariusze_wl:
            # Poprawka WYLACZNIE w tym skrypcie analizy (nie w generator.py):
            # oblicz_moc_urzadzen() dla tych dwoch punktow oswietlenia liczy
            # "po" ZAWSZE z listy zdarzen obecnosci, bez trybu awaryjnego
            # "scenariusz 2 nieaktywny -> wroc do profilu bazowego" (w
            # odroznieniu od pozostalych urzadzen). Przy scenariuszu 2
            # wylaczonym ta wartosc bylaby wiec zawsze 0 W, co sztucznie
            # zawyzalo redukcje w wariantach bez scenariusza 2 (patrz
            # RAPORT_ANALIZ.md, Etap D). Tutaj podmieniamy ja na wartosc
            # baseline, odtwarzajac "brak jakiejkolwiek automatyzacji" dla
            # tych dwoch urzadzen.
            po["oswietlenie_wiatrolap"] = baseline["oswietlenie_wiatrolap"]
            po["oswietlenie_korytarz_pietro"] = baseline["oswietlenie_korytarz_pietro"]
        probki_baseline.append((t, baseline))
        probki_po.append((t, po))
        t += krok

    return probki_baseline, probki_po


def main():
    # Kontrola: wszystkie scenariusze wlaczone musi odtworzyc wynik glowny.
    b_all, a_all = generuj_z_wybranymi_scenariuszami({1, 2, 3, 4})
    e_przed_all, e_po_all = energia(b_all), energia(a_all)
    assert abs(e_przed_all - 968.07) < 0.01, f"ASERCJA NIEUDANA: przed={e_przed_all:.2f}"
    assert abs(e_po_all - 585.89) < 0.01, f"ASERCJA NIEUDANA: po={e_po_all:.2f}"
    print(f"Asercja wyniku glownego OK (wszystkie scenariusze): przed={e_przed_all:.2f} po={e_po_all:.2f}")

    warianty = [
        ("brak automatyzacji", set()),
        ("tylko scenariusz 1 (tryb nieobecnosci)", {1}),
        ("tylko scenariusz 2 (oswietlenie od obecnosci)", {2}),
        ("tylko scenariusz 3 (harmonogram ogrzewania)", {3}),
        ("tylko scenariusz 4 (kontrola rodzicielska)", {4}),
        ("wszystkie scenariusze", {1, 2, 3, 4}),
    ]

    wyniki = []
    e_przed_ref = None
    for nazwa, zestaw in warianty:
        b, a = generuj_z_wybranymi_scenariuszami(zestaw)
        ep, epo = energia(b), energia(a)
        if e_przed_ref is None:
            e_przed_ref = ep
        red_kwh = ep - epo
        red_pct = red_kwh / ep * 100
        wyniki.append((nazwa, ep, epo, red_kwh, red_pct))

    print(f"\n{'Wariant':<45} {'po [kWh]':>10} {'red [kWh]':>10} {'red [%]':>8}")
    for nazwa, ep, epo, red, redp in wyniki:
        print(f"{nazwa:<45} {epo:>10.2f} {red:>10.2f} {redp:>8.2f}")

    wyniki_dir = os.path.join(os.path.dirname(__file__), 'wyniki')
    os.makedirs(wyniki_dir, exist_ok=True)
    with open(os.path.join(wyniki_dir, 'd_ablacja_scenariuszy.csv'), 'w', newline='', encoding='utf-8') as fp:
        w = csv.writer(fp)
        w.writerow(['wariant', 'energia_przed_kwh', 'energia_po_kwh', 'redukcja_kwh', 'redukcja_pct'])
        for nazwa, ep, epo, red, redp in wyniki:
            w.writerow([nazwa, f"{ep:.2f}", f"{epo:.2f}", f"{red:.2f}", f"{redp:.2f}"])

    red_by_name = {n: r for n, _, _, r, _ in wyniki}
    suma_pojedynczych = sum(red_by_name[f"tylko scenariusz {i} ({d})"] for i, d in [
        (1, "tryb nieobecnosci"), (2, "oswietlenie od obecnosci"),
        (3, "harmonogram ogrzewania"), (4, "kontrola rodzicielska"),
    ])
    red_laczna = red_by_name["wszystkie scenariusze"]
    print(f"\nSuma redukcji pojedynczych scenariuszy: {suma_pojedynczych:.2f} kWh")
    print(f"Redukcja przy wszystkich scenariuszach naraz: {red_laczna:.2f} kWh")
    print(f"Roznica (efekt interakcji): {red_laczna - suma_pojedynczych:.2f} kWh")


if __name__ == '__main__':
    main()
