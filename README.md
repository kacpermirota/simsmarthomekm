# Smart home automation & energy monitoring

Prototypowy system automatyki domowej z monitorowaniem zużycia energii i analizą danych w chmurze — projekt inżynierski. Emuluje dom jednorodzinny (16 encji: czujniki, oświetlenie, ogrzewanie, sprzęt AGD) sterowany automatyzacjami Home Assistant, z pełnym potokiem danych od czujnika do wykresu w chmurze.

![image alt](https://github.com/kacpermirota/smarthomesim/blob/a0c3311513a60f52d7257377fcb85d6bd1832289/urzadzenia_naprawione.png)

## Architektura

```
Home Assistant → Mosquitto (MQTT) → Node-RED → InfluxDB (lokalnie)
                                        ↓
                                  AWS IoT Core → Amazon S3 → Athena → QuickSight
```

- **Home Assistant** — warstwa urządzeń (encje `input_boolean` + warstwa domenowa `light`/`switch`) i automatyzacje sterujące energią.
- **Mosquitto** — lokalny broker MQTT.
- **Node-RED** — agreguje bieżącą moc urządzeń i publikuje ją lokalnie oraz do chmury.
- **InfluxDB** — lokalna baza szeregów czasowych.
- **AWS (IoT Core / S3 / Athena / QuickSight)** — odbiór danych w chmurze, archiwizacja i wizualizacja.

## Uruchomienie

Wymaga Dockera i pliku `.env` z hasłami (patrz zmienne w `docker-compose.yml`, np. `INFLUXDB_ADMIN_PASSWORD`).

```bash
docker compose up -d
```

Usługi po starcie:
- Home Assistant: http://127.0.0.1:8123
- Node-RED: http://127.0.0.1:1880
- InfluxDB: http://127.0.0.1:8086

## Generator danych porównawczych

Osobny moduł (`generowanie_danych_v2/`) symuluje 14-dniowy okres zużycia energii przed i po wdrożeniu automatyzacji, do porównania w chmurze — patrz `generowanie_danych_v2/README.md`.

## Struktura repozytorium

- `ha-config/` — konfiguracja Home Assistant (automatyzacje, scenariusze).
- `nodered-data/flows.json` — przepływy Node-RED.
- `mosquitto/config/` — konfiguracja brokera MQTT.
- `generowanie_danych_v2/` — generator i analizy danych porównawczych (Python).
- `docker-compose.yml` — definicja usług.
