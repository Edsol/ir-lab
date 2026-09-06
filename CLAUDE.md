# CLAUDE.md

La documentazione principale per agenti AI è in [AGENTS.md](AGENTS.md). Leggila prima di tutto.

## Istruzioni specifiche per Claude

- Usa `InquirerPy` per i prompt interattivi (wrapper in `ir_lab/prompts.py`).
- Aggiorna AGENTS.md (non CLAUDE.md) quando aggiungi feature o cambi architettura.
- Mantieni funzioni testabili senza MQTT reale.
- Messaggi CLI, docstring e documentazione in **inglese**: il progetto e' pubblico.
  Le conversazioni con l'utente restano in italiano.
- Non chiedere all'utente di reinserire dati già disponibili nel database.
- I generatori di protocollo stanno in `ir_lab/generators/`. Quando uno e'
  verificato, va portato in [IRBridge](https://github.com/Edsol/irbridge)
  (repo separato) come `ClimateGenerator`.
- Prima di committare: `ruff check ir_lab tests` e `pytest`.
