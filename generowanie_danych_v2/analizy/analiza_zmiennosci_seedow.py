"""
Zmiennosc stochastyczna wyniku glownego: jak duzo zalezy od losowania
zachowania domownikow, a nie od przyjetych parametrow.

Nie modyfikuje generator.py/profile_urzadzen.py/logika_automatyzacji.py/
model_obecnosci.py. Uruchamia generuj_serie() dla 300 ziaren (0-299),
p_przelacznik=0,8 (wartosc domyslna), pozostale parametry domyslne.

Uruchomienie: python analizy/analiza_zmiennosci_seedow.py
"""
from __future__ import annotations
import sys, os, csv, statistics
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import generator as g

N_SEEDS = 300


def energia_calkowita(probki):
    h = g.INTERWAL_MIN / 60 / 1000
    return sum(sum(d.values()) for _, d in probki) * h


def percentyl(dane_posortowane, p):
    n = len(dane_posortowane)
    idx = p / 100 * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return dane_posortowane[lo] + (dane_posortowane[hi] - dane_posortowane[lo]) * frac


def main():
    wyniki_dir = os.path.join(os.path.dirname(__file__), 'wyniki')
    os.makedirs(wyniki_dir, exist_ok=True)

    b0, a0 = g.generuj_serie(seed=42)
    e_przed0, e_po0 = energia_calkowita(b0), energia_calkowita(a0)
    assert abs(e_przed0 - 968.07) < 0.01, f"ASERCJA NIEUDANA: przed={e_przed0:.2f}"
    assert abs(e_po0 - 585.89) < 0.01, f"ASERCJA NIEUDANA: po={e_po0:.2f}"
    print(f"Asercja wyniku glownego OK: przed={e_przed0:.2f} kWh, po={e_po0:.2f} kWh")

    rows = []
    for seed in range(N_SEEDS):
        b, a = g.generuj_serie(seed=seed)
        ep, epo = energia_calkowita(b), energia_calkowita(a)
        red_pct = (epo - ep) / ep * 100
        rows.append((seed, ep, epo, red_pct))

    csv_path = os.path.join(wyniki_dir, 'b_monte_carlo_300_seedow.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as fp:
        w = csv.writer(fp)
        w.writerow(['seed', 'energia_przed_kwh', 'energia_po_kwh', 'redukcja_pct'])
        for seed, ep, epo, red in rows:
            w.writerow([seed, f"{ep:.2f}", f"{epo:.2f}", f"{red:.2f}"])
    print(f"Zapisano {len(rows)} wierszy do {csv_path}")

    def stats(col):
        vals = sorted(r[col] for r in rows)
        return dict(
            srednia=statistics.mean(vals),
            odch_std=statistics.stdev(vals),
            min=min(vals),
            max=max(vals),
            p5=percentyl(vals, 5),
            p50=percentyl(vals, 50),
            p95=percentyl(vals, 95),
        )

    s_przed = stats(1)
    s_po = stats(2)
    s_red = stats(3)

    print(f"\n{'Metryka':<12} {'srednia':>10} {'odch.std':>10} {'min':>10} {'max':>10} {'P5':>10} {'P50':>10} {'P95':>10}")
    for nazwa, s in (('przed [kWh]', s_przed), ('po [kWh]', s_po), ('redukcja [%]', s_red)):
        print(f"{nazwa:<12} {s['srednia']:>10.2f} {s['odch_std']:>10.2f} {s['min']:>10.2f} {s['max']:>10.2f} {s['p5']:>10.2f} {s['p50']:>10.2f} {s['p95']:>10.2f}")

    red_seed42 = [r[3] for r in rows if r[0] == 42][0]
    posortowane = sorted(r[3] for r in rows)
    rank = sum(1 for v in posortowane if v <= red_seed42)
    percentyl_42 = rank / len(posortowane) * 100
    print(f"\nSeed 42: redukcja={red_seed42:.2f}%, pozycja w rozkladzie = percentyl {percentyl_42:.1f} (rank {rank}/{len(posortowane)})")

    with open(os.path.join(wyniki_dir, 'b_podsumowanie_statystyczne.csv'), 'w', newline='', encoding='utf-8') as fp:
        w = csv.writer(fp)
        w.writerow(['metryka', 'srednia', 'odch_std', 'min', 'max', 'p5', 'p50', 'p95'])
        for nazwa, s in (('energia_przed_kwh', s_przed), ('energia_po_kwh', s_po), ('redukcja_pct', s_red)):
            w.writerow([nazwa] + [f"{s[k]:.2f}" for k in ('srednia', 'odch_std', 'min', 'max', 'p5', 'p50', 'p95')])

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        red_vals = [r[3] for r in rows]
        plt.figure(figsize=(7, 4))
        plt.hist(red_vals, bins=30, edgecolor='black')
        plt.axvline(red_seed42, color='red', linestyle='--', label=f'seed=42 ({red_seed42:.2f}%)')
        plt.xlabel('Redukcja energii [%]')
        plt.ylabel('Liczba realizacji (z 300)')
        plt.title('Rozklad redukcji energii dla 300 ziaren losowych')
        plt.legend()
        plt.tight_layout()
        png_path = os.path.join(wyniki_dir, 'b_histogram_redukcji.png')
        plt.savefig(png_path, dpi=150)
        print(f"\nZapisano histogram: {png_path}")
    except ImportError:
        print("\nmatplotlib niedostepny - histogram PNG pominiety (opcjonalny wg zadania).")


if __name__ == '__main__':
    main()
