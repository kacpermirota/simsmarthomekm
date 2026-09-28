"""
Model obecności domowników.

Generuje wyłącznie surowe zdarzenia czujników (drzwi, ruch w wiatrołapie,
ruch w korytarzu piętra, użycie przełącznika trybu nieobecności) dla zadanej
liczby dni. Ten moduł nie wie nic o automatyzacjach, mocy ani energii - to
wspólna podstawa, którą dwukrotnie przepuszcza się przez
logika_automatyzacji.py (raz jako baseline, raz z automatyzacją), żeby
różnica energetyczna wynikała wyłącznie z automatyzacji, a nie z dwóch
niezależnie wylosowanych realizacji dnia.

Model traktuje gospodarstwo domowe jako jedną jednostkę (dom jest albo pusty,
albo zajęty) - zgodnie z tym, jak same automatyzacje widzą świat: nie
rozróżniają liczby domowników, tylko stan czujników.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

Przedzial = tuple[datetime, datetime]

# Parametry wejściowe modelu - jawnie nazwane i wydzielone od wyników.
# Zmiana tych wartości to właśnie analiza wrażliwości (patrz analizy/).
PARAMETRY_DOMYSLNE: dict = dict(
    p_przelacznik=0.8,  # prawdopodobieństwo użycia przełącznika [4] przy wyjściu
    wyjscie_srednia_godz=7.75,  # 7:45
    wyjscie_odchylenie_min=20,
    powrot_srednia_godz=16.5,  # 16:30
    powrot_odchylenie_min=30,
    p_krotkie_wyjscie_weekend=0.5,
    dlugosc_krotkiego_wyjscia_min=90,
    dlugosc_pulsu_ruchu_min=2,  # jak długo trwa wykryty ruch przy przejściu
    srednia_przerwa_ruchu_korytarz_min=30,  # średni odstęp między "przejściami" korytarzem piętra
    godzina_pobudki=6.0,
    godzina_snu=23.0,
)


@dataclass
class ZdarzeniaCzujnikow:
    """Przedziały czasu, w których dany sygnał jest aktywny (odpowiednik
    stanu "on" encji `input_boolean` w rzeczywistym systemie)."""

    ruch_wiatrolap: list[Przedzial] = field(default_factory=list)
    ruch_korytarz: list[Przedzial] = field(default_factory=list)
    drzwi_otwarte: list[Przedzial] = field(default_factory=list)
    wychodze_aktywne: list[Przedzial] = field(default_factory=list)
    nieobecnosci: list[Przedzial] = field(default_factory=list)  # do wewnętrznego użytku (generowanie ruchu), NIE trafia do automatyzacji


def generuj_zdarzenia(
    start: date,
    liczba_dni: int = 14,
    parametry: dict | None = None,
    seed: int | None = None,
) -> ZdarzeniaCzujnikow:
    """Generuje surowe zdarzenia czujników dla `liczba_dni` kolejnych dni od `start`."""
    p = {**PARAMETRY_DOMYSLNE, **(parametry or {})}
    rng = random.Random(seed)
    zd = ZdarzeniaCzujnikow()

    # Przebieg 1: wyjścia/powroty (dni robocze) i ewentualne krótkie wyjścia (weekendy)
    for i in range(liczba_dni):
        dzien = start + timedelta(days=i)
        roboczy = dzien.weekday() < 5  # 0=poniedziałek ... 4=piątek

        if roboczy:
            wyjscie = _losowa_godzina(dzien, p["wyjscie_srednia_godz"], p["wyjscie_odchylenie_min"], rng)
            powrot = _losowa_godzina(dzien, p["powrot_srednia_godz"], p["powrot_odchylenie_min"], rng)
            _dodaj_wyjscie_powrot(zd, wyjscie, powrot, p, rng)
        elif rng.random() < p["p_krotkie_wyjscie_weekend"]:
            godz_wyjscia = rng.uniform(10, 17)
            wyjscie = _losowa_godzina(dzien, godz_wyjscia, 15, rng)
            powrot = wyjscie + timedelta(minutes=p["dlugosc_krotkiego_wyjscia_min"] + rng.gauss(0, 15))
            _dodaj_wyjscie_powrot(zd, wyjscie, powrot, p, rng)

    # Przebieg 2: losowy ruch w korytarzu piętra w godzinach czuwania, ale
    # TYLKO gdy dom jest faktycznie zajęty (drugi przebieg, bo potrzebujemy
    # już znać wszystkie nieobecności z przebiegu 1).
    for i in range(liczba_dni):
        dzien = start + timedelta(days=i)
        _dodaj_ruch_dzienny(zd, dzien, p, rng)

    return zd


def _losowa_godzina(dzien: date, srednia_godz: float, odchylenie_min: float, rng: random.Random) -> datetime:
    minuty = srednia_godz * 60 + rng.gauss(0, odchylenie_min)
    minuty = max(0, min(24 * 60 - 1, minuty))
    return datetime.combine(dzien, datetime.min.time()) + timedelta(minutes=minuty)


def _dodaj_wyjscie_powrot(zd: ZdarzeniaCzujnikow, wyjscie: datetime, powrot: datetime,
                           p: dict, rng: random.Random) -> None:
    puls = timedelta(minutes=p["dlugosc_pulsu_ruchu_min"])
    # Przejście przez wiatrołap (jedyna droga na zewnątrz) - krótki puls ruchu
    # i chwilowe otwarcie drzwi, przy wyjściu i przy powrocie.
    zd.ruch_wiatrolap.append((wyjscie, wyjscie + puls))
    zd.drzwi_otwarte.append((wyjscie, wyjscie + timedelta(minutes=1)))
    zd.ruch_wiatrolap.append((powrot, powrot + puls))
    zd.drzwi_otwarte.append((powrot, powrot + timedelta(minutes=1)))

    zd.nieobecnosci.append((wyjscie, powrot))

    if rng.random() < p["p_przelacznik"]:
        zd.wychodze_aktywne.append((wyjscie + puls, powrot))


def _w_ktorejs_nieobecnosci(t: datetime, zd: ZdarzeniaCzujnikow) -> bool:
    return any(a <= t <= b for a, b in zd.nieobecnosci)


def _dodaj_ruch_dzienny(zd: ZdarzeniaCzujnikow, dzien: date, p: dict, rng: random.Random) -> None:
    """Losowe 'przejścia' korytarzem piętra w godzinach czuwania - proces
    Poissona o zadanym średnim odstępie, pomijany w porze nocnej i podczas
    nieobecności (nikt nie generuje ruchu, gdy nikogo nie ma w domu)."""
    puls = timedelta(minutes=p["dlugosc_pulsu_ruchu_min"])
    t = datetime.combine(dzien, datetime.min.time()) + timedelta(hours=p["godzina_pobudki"])
    koniec_dnia = datetime.combine(dzien, datetime.min.time()) + timedelta(hours=p["godzina_snu"])

    while t < koniec_dnia:
        odstep_min = rng.expovariate(1.0 / p["srednia_przerwa_ruchu_korytarz_min"])
        t = t + timedelta(minutes=odstep_min)
        if t >= koniec_dnia:
            break
        if not _w_ktorejs_nieobecnosci(t, zd):
            zd.ruch_korytarz.append((t, t + puls))
