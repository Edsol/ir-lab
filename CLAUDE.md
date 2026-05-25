# CLAUDE.md

La documentazione principale per agenti AI è in [AGENTS.md](AGENTS.md). Leggila prima di tutto.

## Istruzioni specifiche per Claude

- Usa `InquirerPy` per i prompt interattivi (wrapper in `ir_lab/prompts.py`).
- Aggiorna AGENTS.md (non CLAUDE.md) quando aggiungi feature o cambi architettura.
- Mantieni funzioni testabili senza MQTT reale.
- Gli errori CLI devono essere comprensibili, in italiano se possibile.
- Non chiedere all'utente di reinserire dati già disponibili nel database.
