# AGENTS.md

Questo file guida gli agenti AI che lavorano su IR Lab.

## Scopo del progetto

IR Lab e' un laboratorio locale Python per indagare, apprendere e capire la comunicazione IR tramite un blaster Tuya/Zigbee2MQTT controllato via MQTT.

Non e' ancora l'integrazione Home Assistant finale. Il progetto serve a produrre un dataset ordinato e analizzabile di codici IR, raw timings, frame e metadati, cosi' da poter poi generare script, servizi o integrazioni HA.

## Obiettivo finale

Portare i telecomandi in Home Assistant, possibilmente in modo progressivo:

1. dataset codici appresi;
2. script HA generati;
3. servizio Python locale per invio;
4. MQTT Discovery;
5. custom integration/add-on;
6. entita' remote/climate/media_player;
7. generazione dinamica del protocollo quando possibile.

## Principio guida

Prima laboratorio, poi integrazione. Non saltare subito a custom component HA se mancano dati.

Ogni miglioramento dovrebbe aiutare una di queste attivita': acquisire campioni, ridurre errori manuali, conservare il codice originale, confrontare raw/bit/hex, identificare pattern, esportare verso HA.

## Percorsi principali

```text
README.md                       documentazione utente
AGENTS.md                       istruzioni per agenti AI generici
CLAUDE.md                       istruzioni specifiche per Claude
config.example.yaml             esempio config MQTT
sessions/                       sessioni YAML di acquisizione
data/remotes.json               database generato, ignorato da git
ir_lab/cli.py                   CLI principale
ir_lab/config.py                parsing config
ir_lab/mqtt_client.py           bridge MQTT
ir_lab/storage.py               storage JSON
ir_lab/tuya_codec.py            Tuya base64 <-> raw timings
ir_lab/raw_analyzer.py          analisi raw/frame/hex
ir_lab/prompts.py               prompt interattivi stile Inquirer
```

## Comandi utili

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

Uso laboratorio:

```bash
ir-lab wizard
ir-lab capture --session sessions/midea_cool_sweep.yaml --samples 2
ir-lab learn --remote midea_camera --command cool_22_auto --tags mode=cool,temperature=22
ir-lab send --remote midea_camera --command cool_22_auto
ir-lab analyze --remote midea_camera
ir-lab compare --remote midea_camera --commands cool_21_auto cool_22_auto cool_23_auto
```

## Stile di sviluppo

- Python 3.11+.
- Preferire dipendenze leggere.
- Non introdurre database complessi finche' JSON basta.
- Mantenere il codice leggibile: questo progetto serve anche a capire il protocollo.
- Separare bene MQTT, codec, analisi e storage.
- Non nascondere il dato originale: salvare sempre `tuya` e `raw`.
- Non eliminare sample: aggiungere nuovi campioni e confrontarli.
- Gli errori CLI devono essere comprensibili, in italiano se possibile.

## Prompt interattivi

Il progetto usa `InquirerPy`, scelto per avere un'esperienza simile a `@inquirer/prompts` del mondo npm. Il wrapper sta in `ir_lab/prompts.py`.

Se in futuro si cambia libreria prompt, mantenere invariata l'interfaccia del wrapper quanto piu' possibile.

## Codec Tuya

`ir_lab/tuya_codec.py` contiene una implementazione leggibile del formato Tuya IR:

- decode: Tuya base64 -> stream Tuya/FastLZ-like -> bytes -> uint16 little-endian -> raw timings;
- encode: raw timings -> uint16 little-endian -> literal blocks -> base64.

L'encoder attuale non comprime. Questo e' intenzionale per una prima milestone: meno magia, piu' ispezionabilita'. Aggiungere compressione solo dopo test con dispositivi reali.

## Licenza

IR Lab è GPL-3.0-or-later perché usa irtuya (GPL-3.0) come dipendenza opzionale.

irtuya è usato SOLO in `ir_lab/nec_codec.py` per NEC decode/encode, Broadlink e
auto-rilevamento formato. Il codec Tuya principale (`tuya_codec.py`) è una
reimplementazione originale, scritta da zero, e non dipende da irtuya.

### Strategia dipendenza (opzione C)

- irtuya è in `[project.optional-dependencies] nec`: va installato esplicitamente
  con `pip install -e ".[nec]"` o `pip install -e ".[dev,nec]"`.
- Se irtuya non è installato, `nec_codec.py` solleva `CodecError` con istruzioni.
- Il resto del progetto funziona senza irtuya.

### Migrazione futura (se necessaria)

Se in futuro si vuole usare irtuya anche per il codec Tuya (es. per la compressione
FastLZ in encoding), il percorso è:
1. spostare irtuya da optional a dipendenza principale in `pyproject.toml`;
2. in `tuya_codec.py`, sostituire `decode_tuya_ir`/`encode_tuya_ir` con wrapper
   su `irtuya.decode_tuya_to_raw` / `irtuya.encode_raw_to_tuya`;
3. rimuovere `decompress_tuya_stream` ed `emit_literal_stream` interni.

Non farlo prima che irtuya sia su PyPI o che la compressione diventi necessaria.

## TODO prioritari

### Milestone 1: acquisizione migliore

- Aggiungere comando `ir-lab session-create --type climate` (e altri tipi):
  wizard interattivo che raccoglie il profilo del dispositivo prima di generare
  la sessione YAML. Per i climatizzatori chiedere:
    - quante modalità ha il telecomando e quali (cool/heat/dry/auto/fan_only)
    - sequenza ciclica del tasto MODE (es. fan→cool→dry→auto→heat)
    - icone display per ogni modalità (per documentare il riconoscimento visivo)
    - temperatura minima e massima impostabile
    - velocità fan disponibili (auto/low/mid/high/turbo)
    - presenza swing, turbo, sleep, led
  Il wizard genera la sessione YAML con tutti i comandi necessari già taggati
  e le istruzioni di acquisizione corrette (es. partire dalla temp minima).
- Aggiungere resume sessione se interrotta.
- Aggiungere controllo duplicati: stesso comando, stesso raw normalizzato.
- Aggiungere `notes` per sample.
- Aggiungere export CSV/Markdown dei frame.

### Milestone 2: analisi migliore

- Normalizzare raw con tolleranza temporale.
- Rilevare ripetizioni dello stesso frame.
- Rilevare protocolli NEC-like.
- Supportare bit order MSB/LSB nella visualizzazione.
- Evidenziare byte/nibble che cambiano tra comandi.
- Generare report diff tra sweep di temperatura.

### Milestone 3: ponte verso HA

- Export script YAML HA.
- Export dashboard card YAML provvisoria.
- Mini servizio HTTP locale `/send` e `/remotes`.
- MQTT Discovery per pulsanti.
- Integrazione con `rest_command` HA.

### Milestone 4: profili dispositivi

- Profilo `climate_mapping`: stato -> comando appreso.
- Profilo `midea_candidate`: inferenza campi temperatura/mode/fan.
- Profilo `tv_nec`: comandi singoli con NEC-like decoding.

## Come ragionare sui climatizzatori

Per i climatizzatori IR, ogni trasmissione spesso rappresenta lo stato completo, non un semplice tasto. Quindi i tag sono importanti:

```yaml
tags:
  power: on
  mode: cool
  temperature: 22
  fan: auto
  swing: off
  led: unchanged
  turbo: off
  sleep: off
```

Acquisire sweep controllati cambiando una sola variabile alla volta.
