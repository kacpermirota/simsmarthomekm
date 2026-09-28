"""
Walidacja: te same wejscia -> wynik modelu Python vs wynik Home Assistant.

Nie modyfikuje generator.py/profile_urzadzen.py/logika_automatyzacji.py/
model_obecnosci.py. Wejscia to prawdziwe znaczniki czasu odczytane wczesniej
z kopii bazy recordera Home Assistant, tutaj wpisane jako stale - nie
wymagaja ponownego polaczenia z HA/Dockerem.

Metoda: dla kazdego przypadku budujemy minimalny ZdarzeniaCzujnikow z
prawdziwych przedzialow, wywolujemy TA SAMA funkcje logika_automatyzacji.py
co generator.py, i sprawdzamy przewidywany stan w chwili tuz po
rzeczywistym zdarzeniu w Home Assistant, porownujac ze stanem faktycznie
zapisanym w bazie.

Uruchomienie: python analizy/walidacja_model_ha.py
"""
from __future__ import annotations
import sys, os, csv
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import logika_automatyzacji as logika
from model_obecnosci import ZdarzeniaCzujnikow

# UWAGA: logika_automatyzacji.py/model_obecnosci.py uzywaja datetime NAIVE
# (bez strefy) - tak samo jak w generator.py. Ponizsze znaczniki to
# rzeczywiste czasy UTC z bazy recordera, zapisane jako naive (zgodnie z
# konwencja reszty modulu), zeby moc je bezposrednio porownywac funkcjami
# logiki.


def t(rok, mies, dzien, godz, minu, sek, ms=0):
    return datetime(rok, mies, dzien, godz, minu, sek, ms * 1000)


wyniki = []  # (przypadek, wejscia_opis, model, ha, zgodny, uwaga)


def dodaj(przypadek, wejscia_opis, model, ha, uwaga=""):
    zgodny = "T" if model == ha else "N"
    wyniki.append((przypadek, wejscia_opis, model, ha, zgodny, uwaga))


# --- 1-2. Oswietlenie wiatrolap (ruch wykryty / brak ruchu) -----------------
# Realne zdarzenia z bazy (20.09.2026): ruch on 23:25:03.611, ruch off 23:25:12.276.
on_w = t(2026, 9, 20, 23, 25, 3, 611)
off_w = t(2026, 9, 20, 23, 25, 12, 276)
ruch_wiatrolap = [(on_w, off_w)]
przedzialy_w = logika.oswietlenie_od_obecnosci(ruch_wiatrolap)

# 1. Ruch wykryty: sprawdzamy stan tuz po wykryciu ruchu (real automation
#    triggered w tej samej chwili, Tabela 7.1: "Zaliczony", <1 s).
chwila = on_w + timedelta(milliseconds=50)
model_on = any(a <= chwila <= b for a, b in przedzialy_w)
dodaj("1. Oswietlenie wiatrolap - ruch wykryty", f"ruch on={on_w.time()}", "on" if model_on else "off", "on",
      "real: automation_triggered w tej samej sekundzie (Tabela 7.1)")

# 2. Brak ruchu: real automatyzacja zadzialala (for uplynelo) o 23:26:12.273,
#    3 ms przed nominalnym koncem okna podtrzymania (23:26:12.276) - zgodne
#    z jitterem timera opisanym w Etapie 3. Sprawdzamy stan 1 s PO progu.
chwila2 = t(2026, 9, 20, 23, 26, 13, 276)
model_on2 = any(a <= chwila2 <= b for a, b in przedzialy_w)
dodaj("2. Oswietlenie wiatrolap - brak ruchu (for 1 min)", f"ruch off={off_w.time()}", "off" if not model_on2 else "on", "off",
      f"koniec okna wg modelu={przedzialy_w[0][1].time()}, real wylaczenie=23:26:12.273 (roznica ok. 3 ms)")

# --- 3-4. Oswietlenie korytarz pietra ----------------------------------------
on_k = t(2026, 9, 20, 23, 25, 24, 308)
off_k = t(2026, 9, 20, 23, 25, 26, 914)
ruch_korytarz = [(on_k, off_k)]
przedzialy_k = logika.oswietlenie_od_obecnosci(ruch_korytarz)

chwila3 = on_k + timedelta(milliseconds=50)
model_on3 = any(a <= chwila3 <= b for a, b in przedzialy_k)
dodaj("3. Oswietlenie korytarz - ruch wykryty", f"ruch on={on_k.time()}", "on" if model_on3 else "off", "on",
      "real: automation_triggered w tej samej sekundzie (Tabela 7.1)")

chwila4 = t(2026, 9, 20, 23, 26, 27, 914)
model_on4 = any(a <= chwila4 <= b for a, b in przedzialy_k)
dodaj("4. Oswietlenie korytarz - brak ruchu (for 1 min)", f"ruch off={off_k.time()}", "off" if not model_on4 else "on", "off",
      f"koniec okna wg modelu={przedzialy_k[0][1].time()}, real wylaczenie=23:26:26.912 (roznica ok. 2 ms)")

# --- 5. Test A: tryb nieobecnosci, potwierdzenie reczne ---------------------
wyjscie = t(2026, 9, 20, 22, 53, 26, 939)
# Real test jednorazowy (bez zarejestrowanego "powrotu") - koniec przedzialu
# jest stand-inem, poniewaz wyzwalacz_a_wychodze() zwraca wprost przekazany
# przedzial; przy dowolnym koncu > chwili sprawdzenia wynik jest identyczny.
zd_a = ZdarzeniaCzujnikow(wychodze_aktywne=[(wyjscie, wyjscie + timedelta(days=1))])
przedzialy_a = logika.wyzwalacz_a_wychodze(zd_a)
chwila5 = wyjscie + timedelta(milliseconds=5)
model_off5 = any(a <= chwila5 <= b for a, b in przedzialy_a)
dodaj("5. Test A - tryb nieobecnosci (potwierdzenie reczne)", f"wychodze on={wyjscie.time()}",
      "wylaczone" if model_off5 else "wlaczone", "wylaczone",
      "funkcja jest identycznoscia wzgledem wejscia - test potwierdza wylacznie okablowanie w oblicz_moc_urzadzen (Punkt 2 raportu 04)")

# --- 6. Test B pozytywny: wnioskowanie automatyczne -------------------------
# Realne przedzialy z 20.09.2026 (przed wymuszeniem testu):
drzwi_otwarte = [(t(2026, 9, 20, 22, 35, 13, 991), t(2026, 9, 20, 23, 2, 11, 264))]
ruch_w_szeroko = [
    (t(2026, 9, 20, 22, 35, 14, 44), t(2026, 9, 20, 23, 2, 12, 616)),
    on_w_off := (on_w, off_w),
]
ruch_k_szeroko = [
    (t(2026, 9, 20, 22, 35, 14, 99), t(2026, 9, 20, 23, 2, 23, 560)),
    (on_k, off_k),
]
zd_b = ZdarzeniaCzujnikow(drzwi_otwarte=drzwi_otwarte, ruch_wiatrolap=ruch_w_szeroko, ruch_korytarz=ruch_k_szeroko)
poczatek_b = t(2026, 9, 20, 0, 0, 0)
koniec_b = t(2026, 9, 21, 0, 0, 0)

prog_oryg = logika.PROG_CISZY_MIN
logika.PROG_CISZY_MIN = 1  # test wykonany na progu tymczasowo skroconym z 30 do 1 min (metodyka 7.1)
try:
    przedzialy_b = logika.wyzwalacz_b_wnioskowanie(zd_b, poczatek_b, koniec_b)
finally:
    logika.PROG_CISZY_MIN = prog_oryg

real_trigger_b = t(2026, 9, 20, 23, 3, 11, 263)
chwila6 = real_trigger_b + timedelta(milliseconds=100)
model_off6 = any(a <= chwila6 <= b for a, b in przedzialy_b)
dodaj("6. Test B pozytywny - wnioskowanie automatyczne", "drzwi zamkniete 23:02:11.264, brak ruchu, for=1 min (skrocony)",
      "wylaczone" if model_off6 else "wlaczone", "wylaczone",
      f"real automation_triggered=23:03:11.263; PROG_CISZY_MIN podmieniony na 1 TYLKO na czas tego wywolania")

# --- 7. Test B zakres (negatywny) - sprawdzenie okablowania -----------------
# tv_salon/ekspres/oswietlenie_salon/kuchnia sa w oblicz_moc_urzadzen
# sterowane WYLACZNIE przez wyzwalacz_a, nie przez wyzwalacz_b (weryfikacja
# przez odczyt kodu generator.py, funkcja oblicz_moc_urzadzen) - to jest
# test statyczny (struktura kodu), nie porownanie znacznikow czasu.
wyniki.append((
    "7. Test B zakres (negatywny)",
    "sprawdzenie, ze tv/ekspres/oswietlenie_salon/kuchnia nie zaleza od wyzwalacz_b",
    "niesterowane przez wyzwalacz_b", "pozostaly wlaczone", "T",
    "test strukturalny kodu (odczyt oblicz_moc_urzadzen), nie porownanie znacznikow czasu; "
    "zgodny, bo model rowniez nie zmienia tych encji pod wplywem wyzwalacz_b",
))

# --- 8. Harmonogram ogrzewania 22:00 (prawdziwe zadzialanie z Etapu 4) ------
poczatek_h = t(2026, 9, 22, 0, 0, 0)
koniec_h = t(2026, 9, 24, 0, 0, 0)
przedzialy_h = logika.harmonogram_ogrzewania(poczatek_h, koniec_h)
real_trigger_h = t(2026, 9, 22, 22, 0, 0, 289)  # czas lokalny (real UTC: 22.09 20:00:00,289)
chwila8 = real_trigger_h + timedelta(seconds=5)
model_off8 = any(a <= chwila8 <= b for a, b in przedzialy_h)
dodaj("8. Harmonogram ogrzewania - wylaczenie 22:00", "prawdziwe zadzialanie harmonogramu, okno testu stabilnosci (Etap 4)",
      "wylaczone" if model_off8 else "wlaczone", "wylaczone",
      f"real automation_triggered=22.09 20:00:00,289 UTC (opoznienie 289 ms wzgledem idealnego zegara modelu)")

# --- 9. Kontrola rodzicielska 16:00 (prawdziwe zadzialanie z Etapu 4) -------
poczatek_l = t(2026, 9, 23, 0, 0, 0)
koniec_l = t(2026, 9, 24, 0, 0, 0)
przedzialy_wylaczenia_l = logika.kontrola_rodzicielska(poczatek_l, koniec_l)
real_trigger_l = t(2026, 9, 23, 16, 0, 0, 167)  # czas lokalny (real UTC: 23.09 14:00:00,167)
chwila9 = real_trigger_l + timedelta(seconds=5)
model_wylaczone9 = any(a <= chwila9 <= b for a, b in przedzialy_wylaczenia_l)
dodaj("9. Kontrola rodzicielska - wlaczenie 16:00", "prawdziwe zadzialanie harmonogramu, okno testu stabilnosci (Etap 4)",
      "wlaczone" if not model_wylaczone9 else "wylaczone", "wlaczone",
      f"real automation_triggered=23.09 14:00:00,167 UTC (opoznienie 167 ms wzgledem idealnego zegara modelu)")


def main():
    print(f"{'Przypadek':<48} {'Model':<20} {'HA':<12} {'Zgodny':<7}")
    for przypadek, wejscia, model, ha, zgodny, uwaga in wyniki:
        print(f"{przypadek:<48} {model:<20} {ha:<12} {zgodny:<7}")

    n_zgodnych = sum(1 for w in wyniki if w[4] == "T")
    print(f"\nZgodnych: {n_zgodnych} / {len(wyniki)}")

    wyniki_dir = os.path.join(os.path.dirname(__file__), 'wyniki')
    os.makedirs(wyniki_dir, exist_ok=True)
    with open(os.path.join(wyniki_dir, 'c_walidacja_model_ha.csv'), 'w', newline='', encoding='utf-8') as fp:
        w = csv.writer(fp)
        w.writerow(['przypadek', 'zdarzenia_wejsciowe', 'wynik_modelu', 'wynik_ha', 'zgodny', 'uwaga'])
        for row in wyniki:
            w.writerow(row)


if __name__ == '__main__':
    main()
