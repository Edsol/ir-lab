# 
# _generator.py — generatore codici IR Midea camera
#
# Protocollo decodificato tramite reverse engineering su campioni acquisiti
# con blaster Tuya ZS05 via Zigbee2MQTT. Vedere docs/protocol_midea.md.
#
# LIMITAZIONI ATTUALI:
# - Fan speed non ancora mappato (richiede sweep fan taggato)
# - Dry e auto coperti solo a 22° — le basi F2 per altre temperature
#   sono estrapolate dalla formula, non verificate empiricamente
# - Power on/off non usa questo generatore (codici fissi acquisiti)

from __future__ import annotations

import struct
from ..tuya_codec import encode_tuya_ir

# ── Costanti di protocollo ──────────────────────────────────────────────────

TEMP_MIN = 16
TEMP_MAX = 30  # da verificare empiricamente oltre i 25°

# F1: byte fissi per modalità (B0 con rolling counter=1, B2)
# Rolling counter (bit4 di B0) deve essere 1 — verificato empiricamente:
# il condizionatore non risponde con rc=0.
# Valori B0 derivati dai campioni acquisiti (tutti con rc=1).
_MODE_F1 = {
    #           B0      B2
    "cool":  (0x96, 0x07),
    "heat":  (0x3C, 0x06),
    "dry":   (0x5A, 0x07),
    "auto":  (0xD0, 0x06),
    "fan":   (0x18, 0x06),
}

_F1_B3 = 0x0A  # device address, fisso su tutti i campioni

# F2: base LSB per modalità — F2_LSB = base + (temp-15) * 0x10
# Ricavata empiricamente da sweep cool 16°-25° e heat 16°-25°.
# Per dry e auto verificata solo a 22° — estrapolata per altri valori.
_MODE_F2_BASE = {
    "cool": 0x01200050,
    "heat": 0x06200080,
    "dry":  0x01200050,  # stessa base LSB di cool — verificato su campione dry_22
    "auto": 0x00200060,  # verificato su campione auto_22
    "fan":  0x00200040,  # fan_only, nessuna temperatura
}

_F1_TAIL = [0, 1, 0]  # 3 bit tail fissi

# Base dell'encoding temperatura per modalità: B1 = rev_bits(temp - base) << 4
# cool/heat/auto/fan usano base 15, dry usa base 16 (verificato su campione dry_22)
_TEMP_BASE = {
    "cool": 15,
    "heat": 15,
    "dry":  16,
    "auto": 16,
    "fan":  15,
}


# ── Funzioni interne ────────────────────────────────────────────────────────

def _rev_byte(b: int) -> int:
    return int(f"{b:08b}"[::-1], 2)


def _encode_temp_b1(mode: str, temp: int) -> int:
    """Codifica la temperatura in B1: rev_bits(temp - base) << 4.

    La base varia per modalità (cool/heat=15, dry=16).
    Esempio cool 22°: temp-15=7 → 0111 → reversed=1110 → B1=0xE0
    Esempio dry  22°: temp-16=6 → 0110 → reversed=0110 → B1=0x60
    """
    return int(f"{temp - _TEMP_BASE[mode]:04b}"[::-1], 2) << 4


def _f2_b3(mode: str, temp: int) -> int:
    """Calcola F2.B3 dalla formula lineare LSB.

    F2_LSB = F2_BASE[mode] + (temp-15) * 0x10
    F2.B3 = rev_bits(F2_LSB & 0xFF)
    """
    b1r = temp - 15
    f2_lsb = (_MODE_F2_BASE[mode] + b1r * 0x10) & 0xFFFFFFFF
    return _rev_byte(f2_lsb & 0xFF)


def _f2_b0(mode: str) -> int:
    """F2.B0 dipende dalla macro-famiglia di modalità."""
    if mode in ("cool", "dry"):
        return 0x80
    if mode in ("heat",):
        return 0x60
    return 0x00  # auto, fan


def _build_raw(f1: list[int], f2: list[int]) -> list[int]:
    """Costruisce i raw timings NEC-like da F1 (35 bit) e F2 (32 bit)."""
    HEADER_MARK  = 9000
    HEADER_SPACE = 4500
    BIT_MARK     = 650
    ZERO_SPACE   = 560
    ONE_SPACE    = 1670
    GAP          = 20000

    def bits_of(byte_list: list[int], tail: list[int] | None = None) -> list[int]:
        bits: list[int] = []
        for b in byte_list:
            for i in range(7, -1, -1):
                bits.append((b >> i) & 1)
        if tail:
            bits.extend(tail)
        return bits

    raw = [HEADER_MARK, HEADER_SPACE]

    for bit in bits_of(f1, _F1_TAIL):
        raw.append(BIT_MARK)
        raw.append(ONE_SPACE if bit else ZERO_SPACE)

    raw.append(BIT_MARK)  # mark finale F1 prima del gap
    raw.append(GAP)

    for bit in bits_of(f2):
        raw.append(BIT_MARK)
        raw.append(ONE_SPACE if bit else ZERO_SPACE)

    raw.append(BIT_MARK)  # trailing mark
    return raw


# Byte fissi per power on/off — comandi speciali, non legati a modalità/temperatura
_POWER_ON_F1  = [0x3C, 0x30, 0x06, _F1_B3]
_POWER_ON_F2  = [0x60, 0x04, 0x00, 0x02]
_POWER_OFF_F1 = [0x2C, 0x30, 0x04, _F1_B3]
_POWER_OFF_F2 = [0x60, 0x04, 0x00, 0x03]


# ── API pubblica ────────────────────────────────────────────────────────────

def generate_power_on() -> list[int]:
    """Genera raw timings per il comando power on."""
    return _build_raw(_POWER_ON_F1, _POWER_ON_F2)


def generate_power_off() -> list[int]:
    """Genera raw timings per il comando power off."""
    return _build_raw(_POWER_OFF_F1, _POWER_OFF_F2)


def generate_raw(mode: str, temp: int) -> list[int]:
    """Genera raw timings IR per climatizzatore Midea camera.

    Args:
        mode: "cool" | "heat" | "dry" | "auto" | "fan"
        temp: temperatura in gradi Celsius (16-30).
              Ignorata per mode="fan".

    Returns:
        Lista di durate microsecondo alternanti mark/space.

    Raises:
        ValueError: se mode o temp non sono validi.
    """
    if mode not in _MODE_F1:
        raise ValueError(f"Modalità non supportata: {mode!r}. Valide: {list(_MODE_F1)}")
    if mode != "fan" and not (TEMP_MIN <= temp <= TEMP_MAX):
        raise ValueError(f"Temperatura {temp}° fuori range ({TEMP_MIN}-{TEMP_MAX}°C)")

    b0, b2 = _MODE_F1[mode]
    b1 = _encode_temp_b1(mode, temp) if mode != "fan" else 0x90  # fan: B1 fisso da campione
    f1 = [b0, b1, b2, _F1_B3]

    f2b0 = _f2_b0(mode)
    f2b3 = _f2_b3(mode, temp) if mode != "fan" else 0x0B  # fan: F2.B3 fisso da campione
    f2 = [f2b0, 0x04, 0x00, f2b3]

    return _build_raw(f1, f2)


def generate_tuya(mode: str, temp: int) -> str:
    """Genera il codice Tuya base64 per il comando dato.

    Il codice prodotto è compatibile con il payload MQTT
    {"ir_code_to_send": "<codice>"} di Zigbee2MQTT.
    """
    return encode_tuya_ir(generate_raw(mode, temp))


def verify_against_db(db_path: str = "data/remotes.json") -> dict[str, list[str]]:
    """Confronta i codici generati con i campioni acquisiti nel database.

    Restituisce un dict con chiavi "ok" e "fail" contenenti le etichette
    dei campioni verificati.
    """
    import json
    from pathlib import Path
    from ..raw_analyzer import analyze_raw

    with Path(db_path).open() as f:
        db = json.load(f)

    commands = db["remotes"]["midea_camera"]["commands"]
    results: dict[str, list[str]] = {"ok": [], "fail": []}

    checks = [
        ("cool_temp", "cool", range(16, 26)),
        ("heat temp", "heat", range(16, 26)),
    ]

    for cmd_name, mode, temps in checks:
        for i, temp in enumerate(temps):
            label = f"{mode}_{temp}"
            try:
                sample = commands[cmd_name]["samples"][i]
                real_frames = sample["analysis"]["frames"]
                real_f1 = real_frames[0]["bytes_msb"]
                real_f2 = real_frames[1]["bytes_msb"]

                b0, b2 = _MODE_F1[mode]
                b1 = _encode_temp_b1(mode, temp)
                gen_f1 = [b0, b1, b2, _F1_B3]
                gen_f2 = [_f2_b0(mode), 0x04, 0x00, _f2_b3(mode, temp)]

                # Confronto diretto — il generatore usa rc=1 come i campioni reali
                if gen_f1 == list(real_f1) and gen_f2 == list(real_f2):
                    results["ok"].append(label)
                else:
                    results["fail"].append(
                        f"{label}: F1 gen={[hex(b) for b in gen_f1]} "
                        f"real={[hex(b) for b in real_f1]} | "
                        f"F2 gen={[hex(b) for b in gen_f2]} "
                        f"real={[hex(b) for b in real_f2]}"
                    )
            except Exception as e:
                results["fail"].append(f"{label}: errore={e}")

    return results
