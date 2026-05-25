from __future__ import annotations

import base64
from struct import pack, unpack_from
from typing import Iterable

from .errors import CodecError

MAX_DURATION_US = 65535


def decode_tuya_ir(code: str) -> list[int]:
    """Decode a Tuya IR base64 string into raw microsecond timings."""
    normalized = "".join(str(code).split())
    if not normalized:
        raise CodecError("Codice Tuya vuoto")
    try:
        compressed = base64.b64decode(normalized.encode("ascii"), validate=True)
    except Exception as exc:  # noqa: BLE001
        raise CodecError(f"Base64 Tuya non valido: {exc}") from exc
    try:
        payload = decompress_tuya_stream(compressed)
    except Exception as exc:  # noqa: BLE001
        raise CodecError(f"Impossibile decomprimere il payload Tuya: {exc}") from exc
    if len(payload) % 2:
        raise CodecError(f"Payload decompresso di lunghezza dispari: {len(payload)} byte")
    return [unpack_from("<H", payload, offset)[0] for offset in range(0, len(payload), 2)]


def encode_tuya_ir(raw: Iterable[int], compression_level: int = 0) -> str:
    """Encode raw microsecond timings into a Tuya IR base64 string.

    The first milestone intentionally emits literal blocks only. This is larger
    than captures produced by the device, but deterministic and easy to inspect.
    """
    if compression_level != 0:
        raise CodecError("L'encoder supporta per ora solo compression_level=0")
    timings = [_sanitize_duration(value) for value in raw]
    if not timings:
        raise CodecError("Raw vuoto")
    payload = b"".join(pack("<H", value) for value in timings)
    return base64.b64encode(emit_literal_stream(payload)).decode("ascii")


def _sanitize_duration(value: int | str) -> int:
    try:
        duration = int(value)
    except Exception as exc:  # noqa: BLE001
        raise CodecError(f"Durata raw non numerica: {value!r}") from exc
    if duration < 0:
        raise CodecError(f"Durata raw negativa: {duration}")
    return min(duration, MAX_DURATION_US)


def decompress_tuya_stream(data: bytes) -> bytes:
    """Decompress the Tuya/FastLZ-like stream used by many Tuya IR blasters."""
    out = bytearray()
    pos = 0
    while pos < len(data):
        header = data[pos]
        pos += 1
        length_tag = header >> 5
        distance_high = header & 0b00011111
        if length_tag == 0:
            length = distance_high + 1
            if pos + length > len(data):
                raise CodecError("Literal block oltre fine payload")
            out.extend(data[pos : pos + length])
            pos += length
            continue
        length = length_tag
        if length == 7:
            if pos >= len(data):
                raise CodecError("Length-distance block esteso senza byte length")
            length += data[pos]
            pos += 1
        length += 2
        if pos >= len(data):
            raise CodecError("Length-distance block senza byte distance")
        distance = ((distance_high << 8) | data[pos]) + 1
        pos += 1
        if distance > len(out):
            raise CodecError(f"Distance non valida: {distance} byte, output {len(out)} byte")
        for _ in range(length):
            out.append(out[-distance])
    return bytes(out)


def emit_literal_stream(data: bytes) -> bytes:
    """Emit an uncompressed Tuya stream using literal blocks of max 32 bytes."""
    out = bytearray()
    for start in range(0, len(data), 32):
        chunk = data[start : start + 32]
        out.append(len(chunk) - 1)
        out.extend(chunk)
    return bytes(out)


def raw_to_text(raw: Iterable[int]) -> str:
    return ", ".join(str(int(value)) for value in raw)


def parse_raw_text(text: str) -> list[int]:
    cleaned = text.replace("[", " ").replace("]", " ").replace("\n", " ")
    raw: list[int] = []
    for part in cleaned.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        raw.append(_sanitize_duration(part))
    if not raw:
        raise CodecError("Nessuna durata raw trovata")
    return raw
