"""
Odwzorowanie logiki automatyzacji - Część 2 koncepcji v2.

Każda funkcja odpowiada dokładnie jednej regule (lub parze reguł) z
`ha-config/automations.yaml`, z komentarzem wskazującym `id`. Progi czasowe
(30 min, 1 min, godziny 22:00/6:00/16:00/20:00) są PRZEJĘTE wprost z
aktualnej, przetestowanej konfiguracji - nie są osobno dobierane dla tego
modelu. Funkcje operują wyłącznie na zdarzeniach czujników z
model_obecnosci.py - nie mają dostępu do żadnej "prawdy" o tym, czy dom
faktycznie jest pusty (tak jak prawdziwe automatyzacje Home Assistant).

Wynik każdej funkcji to lista przedziałów (start, koniec), w których dany
efekt jest aktywny - np. "oświetlenie wiatrołapu włączone" albo "grzejniki
wyłączone przez automatyzację". Te przedziały są później nakładane na
profile bazowe urządzeń w generator.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from model_obecnosci import Przedzial, ZdarzeniaCzujnikow

PROG_CISZY_MIN = 30  # automations.yaml id 13/14 - "for: minutes: 30"
PODTRZYMANIE_OSWIETLENIA_MIN = 1  # automations.yaml id 5-8 - "for: minutes: 1"
GODZ_OGRZEWANIE_WYL = 22
GODZ_OGRZEWANIE_WLA = 6
GODZ_LAPTOPY_WLA = 16
GODZ_LAPTOPY_WYL = 20


def wyzwalacz_a_wychodze(zd: ZdarzeniaCzujnikow) -> list[Przedzial]:
    """automations.yaml id: '3' i '4' - potwierdzenie ręczne (przełącznik [4]).
    Dowód bezpośredni, bez opóźnienia - aktywne dokładnie w przedziałach,
    w których model zdecydował, że przełącznik został użyty."""
    return list(zd.wychodze_aktywne)


def oswietlenie_od_obecnosci(ruch: list[Przedzial]) -> list[Przedzial]:
    """automations.yaml id: '5'/'6' (wiatrołap) i '7'/'8' (korytarz piętra).
    Światło włącza się na czas pulsu ruchu + 1 minuta podtrzymania."""
    podtrzymanie = timedelta(minutes=PODTRZYMANIE_OSWIETLENIA_MIN)
    return [(start, koniec + podtrzymanie) for start, koniec in ruch]


def wyzwalacz_b_wnioskowanie(zd: ZdarzeniaCzujnikow, poczatek: datetime, koniec: datetime) -> list[Przedzial]:
    """automations.yaml id: '13' i '14' - wnioskowanie automatyczne.
    Wyzwalacz: drzwi zamknięte nieprzerwanie przez 30 min. Warunek (sprawdzany
    DOKŁADNIE w chwili wyzwolenia, tak jak w Home Assistant): brak ruchu w
    wiatrołapie i korytarzu piętra w tej właśnie chwili.

    Zwraca przedziały, w których automatyzacja jest "aktywna" (wyłącza
    oświetlenie wiatrołapu/korytarza i oba grzejniki), aż do najbliższego
    kolejnego ruchu w którejkolwiek z tych stref lub godziny 6:00 - w
    rzeczywistym automations.yaml nie ma reguły przywracającej te urządzenia
    po powrocie, więc przyjęto to jako jawne założenie modelu: w praktyce
    wracający domownik zauważyłby zimny dom/ciemny korytarz i włączyłby je
    ręcznie, albo zadziała harmonogram poranny.
    """
    okresy_zamkniete = _okresy_ciszy(zd.drzwi_otwarte, poczatek, koniec, PROG_CISZY_MIN)
    wszelki_ruch = sorted(zd.ruch_wiatrolap + zd.ruch_korytarz, key=lambda x: x[0])

    aktywne: list[Przedzial] = []
    for czas_wyzwolenia in okresy_zamkniete:
        if _aktywny_w_chwili(zd.ruch_wiatrolap, czas_wyzwolenia) or _aktywny_w_chwili(zd.ruch_korytarz, czas_wyzwolenia):
            continue  # warunek niespełniony w chwili wyzwolenia - automatyzacja się nie uruchamia

        reset = _najblizsze_zdarzenie_po(wszelki_ruch, czas_wyzwolenia)
        reset = min(reset, _najblizsza_godzina(czas_wyzwolenia, GODZ_OGRZEWANIE_WLA))
        aktywne.append((czas_wyzwolenia, reset))

    return aktywne


def harmonogram_ogrzewania(poczatek: datetime, koniec: datetime) -> list[Przedzial]:
    """automations.yaml id: '9' (22:00 wyłącz) i '10' (6:00 włącz) -
    grzejniki wyłączone w oknie nocnym, niezależnie od obecności."""
    return _codzienne_okno(poczatek, koniec, GODZ_OGRZEWANIE_WYL, GODZ_OGRZEWANIE_WLA)


def kontrola_rodzicielska(poczatek: datetime, koniec: datetime) -> list[Przedzial]:
    """automations.yaml id: '11' (16:00 włącz) i '12' (20:00 wyłącz) -
    obwód laptopów aktywny wyłącznie w tym oknie, niezależnie od obecności."""
    return _codzienne_okno(poczatek, koniec, GODZ_LAPTOPY_WLA, GODZ_LAPTOPY_WYL, aktywne_wewnatrz=True)


# --- funkcje pomocnicze -----------------------------------------------------

def _aktywny_w_chwili(przedzialy: list[Przedzial], t: datetime) -> bool:
    return any(start <= t <= koniec for start, koniec in przedzialy)


def _najblizsze_zdarzenie_po(przedzialy_posortowane: list[Przedzial], t: datetime) -> datetime:
    for start, _ in przedzialy_posortowane:
        if start > t:
            return start
    return t + timedelta(days=365)  # brak kolejnego zdarzenia w horyzoncie symulacji


def _najblizsza_godzina(t: datetime, godzina: float) -> datetime:
    kandydat = datetime.combine(t.date(), datetime.min.time()) + timedelta(hours=godzina)
    if kandydat <= t:
        kandydat += timedelta(days=1)
    return kandydat


def _okresy_ciszy(zdarzenia_otwarcia: list[Przedzial], poczatek: datetime, koniec: datetime,
                   prog_min: int) -> list[datetime]:
    """Zwraca momenty, w których drzwi były zamknięte NIEPRZERWANIE przez co
    najmniej `prog_min` minut - odpowiednik wyzwalacza `for:` w Home Assistant
    (wyzwala się raz, w chwili upłynięcia progu, nie ciągle)."""
    zdarzenia = sorted(zdarzenia_otwarcia, key=lambda x: x[0])
    granice = [poczatek] + [koniec_otw for _, koniec_otw in zdarzenia]
    momenty = []
    for i, granica in enumerate(granice):
        nastepne_otwarcie = zdarzenia[i][0] if i < len(zdarzenia) else koniec
        if (nastepne_otwarcie - granica) >= timedelta(minutes=prog_min):
            momenty.append(granica + timedelta(minutes=prog_min))
    return momenty


def _codzienne_okno(poczatek: datetime, koniec: datetime, godz_od: float, godz_do: float,
                     aktywne_wewnatrz: bool = False) -> list[Przedzial]:
    """Buduje listę przedziałów dla harmonogramu powtarzanego codziennie.
    `aktywne_wewnatrz=False` (domyślne, np. ogrzewanie): przedział [godz_od, godz_do]
    to okno WYŁĄCZENIA. `aktywne_wewnatrz=True` (kontrola rodzicielska): przedział
    to okno WŁĄCZENIA - poza nim urządzenie jest wyłączone, co reprezentujemy
    zwracając dopełnienie (okna wyłączenia)."""
    wyniki: list[Przedzial] = []
    dzien = poczatek.date()
    while datetime.combine(dzien, datetime.min.time()) < koniec:
        a = datetime.combine(dzien, datetime.min.time()) + timedelta(hours=godz_od)
        b = datetime.combine(dzien, datetime.min.time()) + timedelta(hours=godz_do)
        if godz_od > godz_do:  # okno przechodzi przez północ (np. ogrzewanie 22:00-6:00)
            b += timedelta(days=1)
        if aktywne_wewnatrz:
            # zwracamy okna WYŁĄCZENIA, czyli dopełnienie [a, b]
            wyniki.append((datetime.combine(dzien, datetime.min.time()), a))
            wyniki.append((b, datetime.combine(dzien, datetime.min.time()) + timedelta(days=1)))
        else:
            wyniki.append((a, b))
        dzien += timedelta(days=1)
    return wyniki
