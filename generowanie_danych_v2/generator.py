"""
Generator danych porównawczych.

Liczy dwie serie mocy łącznej obiektu (baseline i z automatyzacją) z jednej,
wspólnej realizacji zachowania (model_obecnosci.py), przepuszczonej przez
odwzorowaną logikę automatyzacji (logika_automatyzacji.py). Zapisuje wynik
do InfluxDB (measurement energy_consumption, tag zrodlo=backfill) oraz do
Amazon S3 (profil AWS smarthome-backfill), w formacie JSON Lines
partycjonowanym po fazie.

Uruchomienie: python generator.py
"""

from __future__ import annotations

import json
import os
import random
from datetime import date, datetime, timedelta, timezone

import logika_automatyzacji as logika
import model_obecnosci as obecnosc
import profile_urzadzen as profile
from model_obecnosci import Przedzial

INTERWAL_MIN = 10
LICZBA_DNI = 14
START = date(2026, 2, 1)  # sezon grzewczy
BUCKET_S3 = "dom-jednorodzinny-energia-km2026"
KATALOG_WYJSCIOWY = "wyjscie"

# Profil szumu okien bazowych - dwa niezależne dzienne przesunięcia
# Δ_poczatek(i,d), Δ_koniec(i,d) ~ N(0, SZUM_OKNA_ODCHYLENIE_MIN) per
# urządzenie, współdzielone przez serię baseline i "po". Niezależność
# konieczna - patrz docstring _losuj_przesuniecia_okien poniżej.
SZUM_OKNA_ODCHYLENIE_MIN = 15.0

# Urządzenia objęte szumem okna bazowego - wszystkie z okien w PROFILE plus
# czajnik. Lodówka wyłączona świadomie - jej zmienność wynika z
# niezależnego cyklu duty-cycle, nie z pojęcia okna bazowego.
URZADZENIA_Z_OKNEM = list(profile.PROFILE.keys()) + ["czajnik_kuchnia"]


def _losuj_przesuniecia_okien(start: date, dni: int, seed: int | None) -> dict[str, dict[date, tuple[float, float]]]:
    """Losuje (Δ_poczatek(i,d), Δ_koniec(i,d)) dla każdego urządzenia i dnia -
    DWA niezależne rozkłady N(0, sigma), tak samo jak model obecności traktuje
    wyjście i powrót jako niezależne zmienne, a nie jeden przesuwany blok.
    Niezależność jest konieczna: przesunięcie całego okna jako sztywnego bloku
    (obie granice o tę samą wartość) z definicji NIE zmienia czasu trwania
    (koniec-poczatek), więc dzienna energia wychodziłaby identyczna każdego
    dnia niezależnie od losowania - błąd wykryty empirycznie przy pierwszym
    uruchomieniu. Osobny generator liczb losowych od modelu obecności (seed
    przesunięty o stałą), żeby dodanie szumu nie zmieniło realizacji
    zachowania domowników wylosowanej wcześniej."""
    rng = random.Random(None if seed is None else seed + 1000)
    przesuniecia: dict[str, dict[date, tuple[float, float]]] = {}
    for nazwa in URZADZENIA_Z_OKNEM:
        przesuniecia[nazwa] = {
            start + timedelta(days=d): (rng.gauss(0, SZUM_OKNA_ODCHYLENIE_MIN), rng.gauss(0, SZUM_OKNA_ODCHYLENIE_MIN))
            for d in range(dni)
        }
    return przesuniecia


def _aktywny(przedzialy: list[Przedzial], t: datetime) -> bool:
    return any(start <= t < koniec for start, koniec in przedzialy)


def _udzial_okna_bazowego(
    okna: list[tuple[float, float]], t: datetime, przesuniecie: tuple[float, float] = (0.0, 0.0)
) -> float:
    """Ułamek [0,1] próbki o długości INTERWAL_MIN pokryty oknem bazowym, którego
    początek i koniec przesunięto NIEZALEŻNIE o przesuniecie=(Δ_poczatek, Δ_koniec)
    (w minutach) - patrz uzasadnienie niezależności w _losuj_przesuniecia_okien.
    Interpolacja liniowa (nie 0/1 punktowe) dla dokładności na granicy próbki."""
    dp, dk = przesuniecie
    start_probki = t.hour * 60 + t.minute
    koniec_probki = start_probki + INTERWAL_MIN
    pokrycie = 0.0
    for a, b in okna:
        pokrycie += max(0.0, min(koniec_probki, b * 60 + dk) - max(start_probki, a * 60 + dp))
    return min(pokrycie / INTERWAL_MIN, 1.0)


def _lodowka_moc(t: datetime, poczatek: datetime) -> float:
    minuty_od_startu = (t - poczatek).total_seconds() / 60
    faza = minuty_od_startu % profile.LODOWKA_CYKL_MIN
    return profile.LODOWKA_MOC_W if faza < profile.LODOWKA_CYKL_MIN * profile.LODOWKA_DUTY else 0.0


def _czajnik_moc(t: datetime, przesuniecie: tuple[float, float]) -> float:
    return profile.CZAJNIK_MOC_W * _udzial_okna_bazowego(profile.CZAJNIK_OKNA, t, przesuniecie)


def oblicz_moc_urzadzen(
    t: datetime,
    poczatek: datetime,
    wyzwalacz_a: list[Przedzial],
    wyzwalacz_b: list[Przedzial],
    ogrzewanie_wyl: list[Przedzial],
    oswietlenie_wiatrolap_on: list[Przedzial],
    oswietlenie_korytarz_on: list[Przedzial],
    laptopy_wyl: list[Przedzial],
    przesuniecia: dict[str, dict[date, float]],
) -> tuple[dict[str, float], dict[str, float]]:
    """Zwraca (moc_baseline, moc_po) - słowniki {urzadzenie: waty} dla chwili t.

    `przesuniecia` to Δ(i,d), dzienny szum okna bazowego - ta sama wartość
    wchodzi do obliczenia mocy używanego przez obie serie, co zapewnia
    współdzieloną realizację szumu."""
    p = profile.PROFILE
    dzien = t.date()
    baseline: dict[str, float] = {}
    po: dict[str, float] = {}

    def przesuniecie(nazwa: str) -> float:
        return przesuniecia[nazwa][dzien]

    # Oświetlenie wiatrołapu/korytarza - w "po" W PEŁNI sterowane obecnością
    # (scenariusz 2), bez odniesienia do profilu bazowego.
    baseline["oswietlenie_wiatrolap"] = p["oswietlenie_wiatrolap"].moc_w * _udzial_okna_bazowego(p["oswietlenie_wiatrolap"].okna_bazowe, t, przesuniecie("oswietlenie_wiatrolap"))
    po["oswietlenie_wiatrolap"] = p["oswietlenie_wiatrolap"].moc_w if _aktywny(oswietlenie_wiatrolap_on, t) else 0.0

    baseline["oswietlenie_korytarz_pietro"] = p["oswietlenie_korytarz_pietro"].moc_w * _udzial_okna_bazowego(p["oswietlenie_korytarz_pietro"].okna_bazowe, t, przesuniecie("oswietlenie_korytarz_pietro"))
    po["oswietlenie_korytarz_pietro"] = p["oswietlenie_korytarz_pietro"].moc_w if _aktywny(oswietlenie_korytarz_on, t) else 0.0

    # Urządzenia wyłączane WYŁĄCZNIE przez wyzwalacz A (potwierdzenie ręczne):
    # TV x2, ekspres, oświetlenie salonu/kuchni.
    for nazwa in ("tv_salon", "tv_sypialnia_rodzicow", "ekspres_kuchnia", "oswietlenie_salon", "oswietlenie_kuchnia"):
        prof = p[nazwa]
        udzial = _udzial_okna_bazowego(prof.okna_bazowe, t, przesuniecie(nazwa))
        baseline[nazwa] = prof.moc_w * udzial
        po[nazwa] = prof.moc_w * udzial if not _aktywny(wyzwalacz_a, t) else 0.0

    # Grzejniki - wyłączane przez harmonogram nocny ORAZ oba wyzwalacze trybu
    # nieobecności (id 4 i 14 w automations.yaml).
    for nazwa in ("grzejnik_salon", "grzejnik_korytarz_pietro"):
        prof = p[nazwa]
        udzial = _udzial_okna_bazowego(prof.okna_bazowe, t, przesuniecie(nazwa))
        baseline[nazwa] = prof.moc_w * udzial
        wylaczony = _aktywny(ogrzewanie_wyl, t) or _aktywny(wyzwalacz_a, t) or _aktywny(wyzwalacz_b, t)
        po[nazwa] = prof.moc_w * udzial if not wylaczony else 0.0

    # Laptopy - w pełni sterowane harmonogramem (scenariusz 4), niezależnie od obecności.
    prof = p["komputery_pokoj_dzieci"]
    udzial = _udzial_okna_bazowego(prof.okna_bazowe, t, przesuniecie("komputery_pokoj_dzieci"))
    baseline["komputery_pokoj_dzieci"] = prof.moc_w * udzial
    po["komputery_pokoj_dzieci"] = prof.moc_w * udzial if not _aktywny(laptopy_wyl, t) else 0.0

    # Urządzenia nieautomatyzowane - identyczne w obu seriach.
    lodowka = _lodowka_moc(t, poczatek)
    czajnik = _czajnik_moc(t, przesuniecie("czajnik_kuchnia"))
    baseline["lodowka_kuchnia"] = po["lodowka_kuchnia"] = lodowka
    baseline["czajnik_kuchnia"] = po["czajnik_kuchnia"] = czajnik

    return baseline, po


def generuj_serie(parametry: dict | None = None, seed: int | None = 42):
    poczatek = datetime.combine(START, datetime.min.time())
    koniec = poczatek + timedelta(days=LICZBA_DNI)

    zd = obecnosc.generuj_zdarzenia(START, LICZBA_DNI, parametry, seed)

    wyzwalacz_a = logika.wyzwalacz_a_wychodze(zd)
    wyzwalacz_b = logika.wyzwalacz_b_wnioskowanie(zd, poczatek, koniec)
    ogrzewanie_wyl = logika.harmonogram_ogrzewania(poczatek, koniec)
    laptopy_wyl = logika.kontrola_rodzicielska(poczatek, koniec)
    oswietlenie_wiatrolap_on = logika.oswietlenie_od_obecnosci(zd.ruch_wiatrolap)
    oswietlenie_korytarz_on = logika.oswietlenie_od_obecnosci(zd.ruch_korytarz)
    przesuniecia = _losuj_przesuniecia_okien(START, LICZBA_DNI, seed)

    probki_baseline = []
    probki_po = []
    t = poczatek
    krok = timedelta(minutes=INTERWAL_MIN)
    while t < koniec:
        baseline, po = oblicz_moc_urzadzen(
            t, poczatek, wyzwalacz_a, wyzwalacz_b, ogrzewanie_wyl,
            oswietlenie_wiatrolap_on, oswietlenie_korytarz_on, laptopy_wyl,
            przesuniecia,
        )
        probki_baseline.append((t, baseline))
        probki_po.append((t, po))
        t += krok

    return probki_baseline, probki_po


def _suma_mocy(urzadzenia: dict[str, float]) -> float:
    return sum(urzadzenia.values())


def zapisz_influxdb(probki_baseline, probki_po) -> None:
    from influxdb_client import InfluxDBClient, Point
    from influxdb_client.client.write_api import SYNCHRONOUS

    url = os.environ.get("INFLUXDB_URL", "http://localhost:8086")
    token = os.environ.get("INFLUXDB_TOKEN")
    org = os.environ.get("INFLUXDB_ORG", "smarthome")
    bucket = os.environ.get("INFLUXDB_BUCKET", "energy")
    if not token:
        print("Brak INFLUXDB_TOKEN w środowisku - pomijam zapis do InfluxDB.")
        return

    client = InfluxDBClient(url=url, token=token, org=org)
    write_api = client.write_api(write_options=SYNCHRONOUS)

    punkty = []
    for faza, probki in (("przed", probki_baseline), ("po", probki_po)):
        for t, urzadzenia in probki:
            punkty.append(
                Point("energy_consumption")
                .tag("zrodlo", "backfill")
                .tag("faza", faza)
                .field("power", round(_suma_mocy(urzadzenia) / 1000, 4))  # kW
                .time(t)
            )
    write_api.write(bucket=bucket, org=org, record=punkty)
    client.close()
    print(f"Zapisano {len(punkty)} punktow do InfluxDB (bucket={bucket}).")


def eksportuj_jsonl(probki_baseline, probki_po) -> dict[str, list[str]]:
    """Zapisuje pliki dzień-po-dniu, zwraca mapę {faza: [ścieżki lokalne]}."""
    os.makedirs(KATALOG_WYJSCIOWY, exist_ok=True)
    sciezki: dict[str, list[str]] = {"przed": [], "po": []}

    for faza, probki in (("przed", probki_baseline), ("po", probki_po)):
        dzien_obecny = None
        plik = None
        numer_dnia = 0
        for t, urzadzenia in probki:
            if t.date() != dzien_obecny:
                if plik:
                    plik.close()
                dzien_obecny = t.date()
                numer_dnia += 1
                sciezka = os.path.join(KATALOG_WYJSCIOWY, f"{faza}_day_{numer_dnia:02d}.jsonl")
                plik = open(sciezka, "w", encoding="utf-8")
                sciezki[faza].append(sciezka)
            rekord = {
                "power": round(_suma_mocy(urzadzenia) / 1000, 4),
                "location": "dom",
                "ts": int(t.replace(tzinfo=timezone.utc).timestamp() * 1000),  # epoka w ms, zgodnie z formatem rekordu z IoT Core
            }
            plik.write(json.dumps(rekord, ensure_ascii=False) + "\n")
        if plik:
            plik.close()

    return sciezki


def wgraj_do_s3(sciezki: dict[str, list[str]]) -> None:
    import boto3

    session = boto3.Session(profile_name=os.environ.get("AWS_PROFILE", "smarthome-backfill"))
    s3 = session.client("s3", region_name="eu-central-1")

    for faza, pliki in sciezki.items():
        for i, sciezka in enumerate(pliki, start=1):
            klucz = f"backfill/faza={faza}/day_{i:02d}.jsonl"
            s3.upload_file(sciezka, BUCKET_S3, klucz)
            print(f"Wgrano {sciezka} -> s3://{BUCKET_S3}/{klucz}")


def raport_energii(probki_baseline, probki_po) -> None:
    """Podsumowanie tekstowe do szybkiej weryfikacji lokalnej - wyłącznie
    wynik zbiorczy (moc łączna obiektu). Pełna analiza per urządzenie i
    wykresy liczone są w chmurze (Amazon Athena/QuickSight), nie tutaj."""
    godz_na_probke = INTERWAL_MIN / 60

    def moce(probki):
        return [_suma_mocy(u) for _, u in probki]

    def energia_calkowita(moce_probek):
        return sum(moce_probek) * godz_na_probke / 1000  # kWh

    moce_przed = moce(probki_baseline)
    moce_po = moce(probki_po)
    e_przed = energia_calkowita(moce_przed)
    e_po = energia_calkowita(moce_po)
    zmiana = (e_po - e_przed) / e_przed * 100

    print(f"\nEnergia calkowita - przed: {e_przed:.2f} kWh, po: {e_po:.2f} kWh, zmiana: {zmiana:+.1f}%")
    print(f"Moc srednia [W]  - przed: {sum(moce_przed)/len(moce_przed):.0f}, po: {sum(moce_po)/len(moce_po):.0f}")
    print(f"Moc maks. [W]    - przed: {max(moce_przed):.0f}, po: {max(moce_po):.0f}")


if __name__ == "__main__":
    probki_baseline, probki_po = generuj_serie()
    raport_energii(probki_baseline, probki_po)

    sciezki = eksportuj_jsonl(probki_baseline, probki_po)
    zapisz_influxdb(probki_baseline, probki_po)

    odpowiedz = input("\nWgrac pliki do S3 (profil smarthome-backfill)? [t/N]: ")
    if odpowiedz.strip().lower() == "t":
        wgraj_do_s3(sciezki)
    else:
        print("Pominieto wgrywanie do S3 - pliki JSONL zostaly w katalogu 'wyjscie/'.")
