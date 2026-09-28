"""
Profile bazowe urządzeń - moc znamionowa i okna typowego użytkowania
("baseline", czyli scenariusz bez badanej automatyzacji). Wartości mocy
przyjęte na podstawie kart katalogowych reprezentatywnych urządzeń - ten
plik nie ustala tych wartości, tylko nazywa je jawnie jako wejście modelu,
nie wynik.

Model dwustanowy (włączone/wyłączone), bez odwzorowania poboru w trybie
czuwania - świadome uproszczenie.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProfilUrzadzenia:
    moc_w: float  # moc znamionowa w watach, w stanie włączonym
    okna_bazowe: list[tuple[float, float]]  # godziny [start, koniec) typowego użytkowania w baseline


# Numery [n] odpowiadają oznaczeniom urządzeń na rzucie domu.
PROFILE: dict[str, ProfilUrzadzenia] = {
    "oswietlenie_wiatrolap": ProfilUrzadzenia(8, [(6, 23)]),           # [3]
    "tv_salon": ProfilUrzadzenia(118, [(17, 22)]),                     # [5]
    "grzejnik_salon": ProfilUrzadzenia(2000, [(6, 22)]),               # [6]
    "oswietlenie_salon": ProfilUrzadzenia(24, [(16, 23)]),             # [7]
    "ekspres_kuchnia": ProfilUrzadzenia(1250, [(6, 6.25), (19, 19.25)]),   # [10]
    "oswietlenie_kuchnia": ProfilUrzadzenia(16, [(6, 9), (16, 22)]),   # [11]
    "grzejnik_korytarz_pietro": ProfilUrzadzenia(2000, [(6, 22)]),     # [13]
    "oswietlenie_korytarz_pietro": ProfilUrzadzenia(8, [(6, 23)]),     # [14]
    "komputery_pokoj_dzieci": ProfilUrzadzenia(130, [(14, 22)]),       # [15]
    "tv_sypialnia_rodzicow": ProfilUrzadzenia(118, [(20, 22.5)]),      # [16]
}

# Urządzenie nieobjęte żadnym scenariuszem automatyzacji (nie "grupa
# kontrolna") - identyczne w baseline i w scenariuszu z automatyzacją.
CZAJNIK_MOC_W = 2000
CZAJNIK_OKNA = [(6, 6.17), (18, 18.17)]  # krótkie użycie, niezależne od obecności - świadome uproszczenie

# Lodówka: cykl pracy sprężarki liczony względem osi czasu symulacji, nie
# prawdziwego zegara - zapewnia odtwarzalność wyniku między uruchomieniami.
LODOWKA_MOC_W = 150
LODOWKA_CYKL_MIN = 45  # długość pełnego cyklu sprężarki (włącz + wyłącz)
LODOWKA_DUTY = 0.30  # udział czasu ON w cyklu - dolna granica typowego zakresu dla lodówek domowych (ok. 30-80% zależnie od modelu/wieku/temperatury otoczenia), przyjęta konserwatywnie
