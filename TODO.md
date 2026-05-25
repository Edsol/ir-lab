# TODO

## Subito dopo la prima prova reale

- Verificare che `learn_ir_code` e `learned_ir_code` funzionino con il topic configurato.
- Verificare che `send` reinvii correttamente il codice appreso.
- Testare `decode` su 3-5 codici Tuya gia' noti.
- Verificare se i codici literal-only generati da `encode` vengono accettati dal blaster.

## Acquisizione

- Resume sessione interrotta.
- Skip comando gia' acquisito.
- Acquisizione multipla con ripetizione automatica dello stesso nome.
- Campo note per sample.
- Validazione nomi comando (`snake_case`).

## Analisi

- Normalizzazione raw con tolleranza.
- Report differenze byte/nibble tra comandi.
- Rilevamento frame duplicati.
- NEC-like decoder.
- Output LIRC/Pronto/Broadlink in futuro.

## Home Assistant

- Export script YAML.
- Export dashboard YAML provvisorio.
- API HTTP locale.
- MQTT Discovery.
- Custom integration/add-on solo dopo dataset stabile.
