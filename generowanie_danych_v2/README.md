# Generator danych porównawczych

Symuluje 14-dniowy okres zużycia energii domu jednorodzinnego w dwóch wariantach: bez automatyzacji (baseline) i z nią, z jednej, wspólnej realizacji zachowania domowników — żeby różnica energetyczna wynikała wyłącznie z automatyzacji.

## Pliki

- `model_obecnosci.py` — generuje surowe zdarzenia czujników (wyjścia, powroty, ruch).
- `logika_automatyzacji.py` — odwzorowanie reguł z `ha-config/automations.yaml`.
- `profile_urzadzen.py` — moc znamionowa i okna typowego użytkowania urządzeń.
- `generator.py` — łączy powyższe, liczy energię, zapisuje do InfluxDB i S3.
- `analizy/` — analizy uzupełniające (wrażliwość modelu, zmienność losowa, ablacja scenariuszy, walidacja względem Home Assistant) — patrz `analizy/RAPORT_ANALIZ.md`.

## Uruchomienie

```bash
export INFLUXDB_TOKEN=<token z uprawnieniem zapisu do bucketu 'energy'>
python generator.py
```

Skrypt wypisze podsumowanie energii, zapisze pliki JSONL do `wyjscie/`, zapisze punkty do InfluxDB (measurement `energy_consumption`, tagi `zrodlo=backfill`, `faza=przed|po`), i na końcu zapyta, czy wgrać pliki do S3 (profil AWS `smarthome-backfill`).

## Analizy uzupełniające

```bash
python analizy/wrazliwosc_ogrzewania.py
python analizy/analiza_zmiennosci_seedow.py
python analizy/ablacja_scenariuszy.py
python analizy/walidacja_model_ha.py
```

Żaden z tych skryptów nie modyfikuje `generator.py` ani pozostałych modułów, nie zapisuje do InfluxDB/S3 — tylko liczy lokalnie i zapisuje wyniki do `analizy/wyniki/`. Pełny opis metodologii i wyników: `analizy/RAPORT_ANALIZ.md`.

Wywołanie `generuj_serie(parametry={"p_przelacznik": 0.6}, seed=42)` z inną wartością parametru (patrz `model_obecnosci.PARAMETRY_DOMYSLNE`) pozwala samodzielnie sprawdzić wynik przy innych założeniach — `seed` ustalony na tę samą wartość zapewnia porównywalność między uruchomieniami.
