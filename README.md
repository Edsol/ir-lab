# IR Lab

Laboratorio locale Python per acquisire, salvare, reinviare e analizzare codici IR appresi tramite un IR blaster gestito da Zigbee2MQTT/MQTT.

Il progetto nasce per studiare telecomandi diversi, a partire da un condizionatore Midea, senza trasformarsi subito in una integrazione Home Assistant. L'obiettivo a medio termine e' produrre dati puliti e script/servizi riutilizzabili in Home Assistant.

## Filosofia

IR Lab non e' ancora il telecomando finale. E' il banco di lavoro per:

1. mettere il blaster in modalita' apprendimento;
2. leggere vari codici in sequenza;
3. associare ogni codice a un nome e a metadati funzionali;
4. salvare il codice Tuya originale;
5. convertirlo in raw timings;
6. analizzare header, bit, frame e hex;
7. confrontare campioni e comandi simili;
8. reinviare un codice per test;
9. preparare il lavoro per Home Assistant.

## Stato attuale

Milestone 0 inclusa in questo zip:

- CLI `ir-lab`;
- wizard interattivo con prompt stile Inquirer tramite `InquirerPy`;
- configurazione MQTT via `config.yaml`;
- acquisizione singola (`learn`);
- acquisizione sequenziale da YAML (`capture`);
- storage JSON locale (`data/remotes.json`);
- reinvio codice (`send`);
- conversione Tuya base64 -> raw;
- conversione raw -> Tuya base64 con literal blocks non compressi;
- analisi generica raw -> frame/bit/hex;
- confronto tra comandi (`compare`).

Non include ancora UI web, integrazione Home Assistant, MQTT Discovery o generatore dinamico Midea.

## Installazione locale

```bash
cd ir-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Per sviluppo/test:

```bash
pip install -e ".[dev]"
pytest
```

## Configurazione

```bash
cp config.example.yaml config.yaml
```

Modifica `config.yaml`:

```yaml
mqtt:
  host: 192.168.1.10
  port: 1883

emitters:
  ir_blaster_battery:
    friendly_name: "IR Blaster (Battery)"
    topic_state: "zigbee2mqtt/IR Blaster (Battery)"
    topic_set: "zigbee2mqtt/IR Blaster (Battery)/set"
```

Per il Tuya iH-F8260 via Zigbee2MQTT, l'apprendimento passa da `learn_ir_code` e l'invio da `ir_code_to_send` sul topic `/set`.

## Uso rapido

### Wizard interattivo

```bash
ir-lab wizard
```

Il wizard chiede emitter MQTT, telecomando, marca, tipo dispositivo, nome comando, tag e numero di sample. Per ogni sample mette il blaster in apprendimento, aspetta `learned_ir_code`, converte il codice Tuya in raw, analizza e salva tutto in `data/remotes.json`.

### Acquisizione singola

```bash
ir-lab learn \
  --remote midea_camera \
  --command cool_22_auto \
  --brand Midea \
  --device-type climate \
  --tags mode=cool,temperature=22,fan=auto \
  --samples 2
```

### Acquisizione sequenziale

```bash
ir-lab capture --session sessions/midea_cool_sweep.yaml --samples 2
```

Questa e' la modalita' consigliata per studiare un protocollo: cambia una sola variabile alla volta e acquisisci piu' sample dello stesso comando.

### Lista, invio, analisi

```bash
ir-lab list
ir-lab send --remote midea_camera --command cool_22_auto
ir-lab analyze --remote midea_camera
ir-lab compare --remote midea_camera --commands cool_21_auto cool_22_auto cool_23_auto
```

### Decodifica offline

```bash
ir-lab decode --tuya "CUsjhRFhApgG..."
ir-lab encode --raw "9000,4500,600,600,600,1680"
```

Nota: l'encoder attuale usa literal blocks non compressi. Il codice e' piu' lungo di quello appreso, ma utile per esperimenti e roundtrip controllati.

## Formato storage

Il file principale e':

```text
data/remotes.json
```

Ogni comando puo' avere piu' sample. Ogni sample conserva `tuya`, `raw`, `analysis`, timestamp ed eventuali errori di decodifica.

## Percorsi importanti

```text
config.example.yaml              Config MQTT di esempio
config.yaml                      Config locale, ignorato da git
sessions/                        Sessioni di acquisizione sequenziale
data/remotes.json                Database locale, ignorato da git
ir_lab/cli.py                    Comandi CLI
ir_lab/mqtt_client.py            Bridge MQTT verso Zigbee2MQTT
ir_lab/tuya_codec.py             Codec Tuya base64 <-> raw timings
ir_lab/raw_analyzer.py           Analisi header/bit/frame/hex
ir_lab/storage.py                Storage JSON
ir_lab/prompts.py                Wrapper prompt stile InquirerPy
```

## Roadmap Home Assistant

Quando il dataset e' stabile, il passo successivo sara' generare asset per HA:

1. script YAML `mqtt.publish` per ogni comando;
2. servizio Python locale richiamabile da `rest_command` o `shell_command`;
3. MQTT Discovery per creare pulsanti automaticamente;
4. custom integration o add-on;
5. climate template basato su mapping;
6. climate/generatore dinamico quando il protocollo e' capito davvero.

## Note sul codec Tuya

Il codec incluso e' implementato per il laboratorio e punta a essere leggibile. Decodifica i codici Tuya appresi in raw timings. L'encoder genera payload validi usando blocchi letterali non compressi, utili per esperimenti.

Riferimenti utili:

- IRTuya: https://github.com/pasthev/irtuya
- Sensus: https://pasthev.github.io/sensus/
- Documentazione formato Tuya IR di mildsunrise: https://gist.github.com/mildsunrise/1d576669b63a260d2cff35fda63ec0b5
- InquirerPy: https://inquirerpy.readthedocs.io/
