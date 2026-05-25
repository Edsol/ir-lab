# nec_codec.py — wrapper NEC attorno a irtuya
#
# STRATEGIA (opzione C):
#   tuya_codec.py  gestisce Tuya base64 <-> raw e resta indipendente.
#   Questo modulo aggiunge NEC e auto-rilevamento usando irtuya come dipendenza.
#
# PERCHÉ NON USARE irtuya ANCHE PER TUYA:
#   tuya_codec.py è già stabile, testato e leggibile. Sostituirlo con irtuya
#   non aggiunge valore concreto nella fase di laboratorio (decode/encode funzionano).
#   L'unica feature mancante è la compressione FastLZ in encode, che non è
#   necessaria finché i codici vengono solo conservati e reinviati 1:1.
#
# MIGRAZIONE FUTURA (se serve):
#   Quando irtuya diventa installabile da PyPI, oppure quando la compressione
#   in encode diventa necessaria (es. integrazione HA con vincoli di lunghezza),
#   si può:
#     1. aggiungere irtuya come dipendenza principale in pyproject.toml;
#     2. sostituire decode_tuya_ir/encode_tuya_ir in tuya_codec.py con wrapper
#        su irtuya.decode_tuya_to_raw / irtuya.encode_raw_to_tuya;
#     3. eliminare decompress_tuya_stream ed emit_literal_stream interni.
#   Fino ad allora, irtuya rimane dipendenza opzionale usata solo qui.
#
# LICENZA:
#   irtuya è GPL-3.0. IR Lab adotta GPL-3.0 di conseguenza (vedi LICENSE).
#
# INSTALLAZIONE (irtuya non è su PyPI):
#   pip install "irtuya @ git+https://github.com/pasthev/irtuya.git"
#   oppure tramite pyproject.toml extras (vedi [project.optional-dependencies]).

from __future__ import annotations

from .errors import CodecError

try:
    import irtuya as _irtuya

    _IRTUYA_AVAILABLE = True
except ImportError:
    _IRTUYA_AVAILABLE = False


def _require_irtuya() -> None:
    if not _IRTUYA_AVAILABLE:
        raise CodecError(
            "irtuya non installato. "
            "Esegui: pip install 'irtuya @ git+https://github.com/pasthev/irtuya.git'"
        )


def detect_ir_format(code: str) -> str:
    """Rileva automaticamente il formato di un codice IR (tuya/broadlink/nec/raw).

    Delega a irtuya.omni_test. Restituisce una stringa tipo 'tuya', 'broadlink_hex',
    'nec', 'raw' oppure 'unknown'.
    """
    _require_irtuya()
    result = _irtuya.omni_test(code)
    if isinstance(result, tuple):
        return result[0]
    return str(result)


def decode_nec(raw: list[int]) -> dict[str, object]:
    """Decodifica raw timings NEC in bytes e indirizzo/comando.

    Restituisce un dict con:
      - sequence: list[int]  (4 byte: addr, ~addr, cmd, ~cmd)
      - short: str           (es. "0x00 0xFF" address+command leggibile)
      - extended: bool       (True se NECx a 2 byte di indirizzo)
    """
    _require_irtuya()
    try:
        sequence = _irtuya.decode_raw_to_nec_sequence(raw)
    except Exception as exc:
        raise CodecError(f"Impossibile decodificare NEC: {exc}") from exc
    try:
        short = _irtuya.decode_nec_sequence_to_short(sequence)
    except Exception as exc:
        raise CodecError(f"Impossibile decodificare NEC short: {exc}") from exc
    extended = len(sequence) >= 4 and sequence[0] != (~sequence[1] & 0xFF)
    return {"sequence": sequence, "short": short, "extended": extended}


def encode_nec(address: int, command: int, *, extended: bool = False, repeats: int = 1) -> list[int]:
    """Codifica indirizzo e comando NEC in raw timings.

    Args:
        address: byte indirizzo (0-255, oppure 0-65535 per NECx).
        command: byte comando (0-255).
        extended: True per NECx (indirizzo a 2 byte).
        repeats: numero di ripetizioni del frame.
    """
    _require_irtuya()
    try:
        short_bytes = [address, command]
        sequence = _irtuya.encode_short_to_nec_sequence(short_bytes, is_nec_extended=extended)
        return _irtuya.encode_nec_sequence_to_raw(sequence, repeats_count=repeats)
    except Exception as exc:
        raise CodecError(f"Impossibile codificare NEC: {exc}") from exc


def decode_broadlink(hex_code: str) -> list[int]:
    """Decodifica un codice Broadlink hex in raw timings."""
    _require_irtuya()
    try:
        return _irtuya.decode_broadlink_hex_to_raw(hex_code)
    except Exception as exc:
        raise CodecError(f"Impossibile decodificare Broadlink: {exc}") from exc


def encode_broadlink(raw: list[int]) -> bytes:
    """Codifica raw timings in formato Broadlink (bytes)."""
    _require_irtuya()
    try:
        return _irtuya.encode_raw_to_broadlink_code(raw)
    except Exception as exc:
        raise CodecError(f"Impossibile codificare Broadlink: {exc}") from exc
