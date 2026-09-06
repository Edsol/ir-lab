from __future__ import annotations

from ..tuya_codec import encode_tuya_ir

# Protocollo Electra/AUX — 13 byte, singolo frame, 104 bit
# Usato da: Beko (YKR-H/102E), AUX, Electrolux, Frigidaire e altri OEM
# Riferimento: IRremoteESP8266 ir_Electra.h / ir_Electra.cpp
#
# TRASMISSIONE: LSB first — ogni byte viene trasmesso dal bit0 al bit7.
# Il raw_analyzer legge MSB first, quindi i byte nel database appaiono invertiti
# rispetto ai valori Electra reali. Il generatore produce i byte Electra corretti
# e li inverte prima di costruire i raw timings.

TEMP_MIN = 16
TEMP_MAX = 32

_TEMP_DELTA = 8  # kElectraAcTempDelta

_MODE = {
    "auto": 0b000,
    "cool": 0b001,
    "dry":  0b010,
    "heat": 0b100,
    "fan":  0b110,
}

_FAN = {
    "auto": 0b101,
    "high": 0b001,
    "mid":  0b010,
    "low":  0b011,
}

# Byte fissi (valori Electra, prima dell'inversione LSB)
_B0  = 0xC3  # protocol identifier, fisso
_B2  = 0xE0  # swing H off (0b111 << 5) — valore Electra: rev8(0x07) = 0xE0
_B3  = 0x00
_B5  = 0x00  # turbo=0, quiet=0
_B7  = 0x00  # sensor temp (IFeel disabilitato)
_B8  = 0x00
_B10 = 0x00


# ── Funzioni interne ────────────────────────────────────────────────────────

def _rev8(b: int) -> int:
    return int(f"{b:08b}"[::-1], 2)


def _build_electra_bytes(mode: str, temp: int, fan: str = "auto",
                         power: bool = True, swing_v: bool = False) -> list[int]:
    """Costruisce i 13 byte Electra (valori logici, LSB first prima dell'inversione)."""
    # B1: SwingV[2:0] + Temp[7:3]
    swing_v_bits = 0b000 if swing_v else 0b111
    temp_enc = temp - _TEMP_DELTA
    b1 = (swing_v_bits & 0x7) | ((temp_enc & 0x1F) << 3)

    # B4: Fan[2:0] in bits[7:5]; dry mode forces low speed (Electra protocol)
    effective_fan = "low" if mode == "dry" else fan
    b4 = (_FAN[effective_fan] & 0x7) << 5

    # B6: Mode[2:0] in bits[7:5] (Electra logical byte)
    b6 = (_MODE[mode] & 0x7) << 5

    # B9: Power in bit[5]; heat mode also sets bit[4] (UseFahrenheit quirk Beko)
    b9 = (0x1 << 5) if power else 0x00
    if mode == "heat":
        b9 |= (0x1 << 4)

    # B11: light toggle (0x00 = invariato)
    b11 = 0x00

    state = [_B0, b1, _B2, _B3, b4, _B5, b6, _B7, _B8, b9, _B10, b11]

    # B12: checksum = sum(state) & 0xFF
    b12 = sum(state) & 0xFF
    state.append(b12)
    return state


def _build_raw(electra_bytes: list[int]) -> list[int]:
    """Costruisce raw timings NEC-like dai byte Electra.

    I byte vengono invertiti (LSB first) prima di serializzare i bit.
    """
    HEADER_MARK  = 9000
    HEADER_SPACE = 4500
    BIT_MARK     = 500
    ZERO_SPACE   = 560
    ONE_SPACE    = 1700
    TRAIL_MARK   = 500

    raw = [HEADER_MARK, HEADER_SPACE]
    for byte in electra_bytes:
        lsb_byte = _rev8(byte)  # inverte per trasmissione LSB first
        for i in range(7, -1, -1):
            bit = (lsb_byte >> i) & 1
            raw.append(BIT_MARK)
            raw.append(ONE_SPACE if bit else ZERO_SPACE)
    raw.append(TRAIL_MARK)
    return raw


# ── API pubblica ────────────────────────────────────────────────────────────

def generate_raw(mode: str, temp: int, fan: str = "auto",
                 power: bool = True, swing_v: bool = False) -> list[int]:
    """Genera raw timings IR per climatizzatore con protocollo Electra/AUX.

    Args:
        mode:    "cool" | "heat" | "dry" | "auto" | "fan"
        temp:    temperatura in °C (16-32). Ignorata per mode="fan".
        fan:     "auto" | "high" | "mid" | "low". Default "auto".
        power:   True = acceso. Default True.
        swing_v: True = swing verticale attivo. Default False.

    Returns:
        Lista di durate in microsecondi alternanti mark/space.

    Raises:
        ValueError: se mode, fan o temp non sono validi.
    """
    if mode not in _MODE:
        raise ValueError(f"Modalità non supportata: {mode!r}. Valide: {list(_MODE)}")
    if fan not in _FAN:
        raise ValueError(f"Fan speed non supportata: {fan!r}. Valide: {list(_FAN)}")
    if mode != "fan" and not (TEMP_MIN <= temp <= TEMP_MAX):
        raise ValueError(f"Temperatura {temp}° fuori range ({TEMP_MIN}-{TEMP_MAX}°C)")

    if mode == "fan":
        temp = TEMP_MIN  # valore placeholder, non significativo

    state = _build_electra_bytes(mode, temp, fan=fan, power=power, swing_v=swing_v)
    return _build_raw(state)


def generate_tuya(mode: str, temp: int, fan: str = "auto",
                  power: bool = True, swing_v: bool = False) -> str:
    """Genera il codice Tuya base64 per il comando dato."""
    return encode_tuya_ir(generate_raw(mode, temp, fan=fan, power=power, swing_v=swing_v))


def verify_against_db(db_path: str = "data/remotes.json",
                      remote: str = "beko_cucina") -> dict[str, list[str]]:
    """Confronta i codici generati con i campioni acquisiti nel database."""
    import json
    from pathlib import Path
    from ..raw_analyzer import analyze_raw

    with Path(db_path).open() as f:
        db = json.load(f)

    commands = db["remotes"][remote]["commands"]
    results: dict[str, list[str]] = {"ok": [], "fail": []}

    checks = [
        ("cool_18", "cool", 18),
        ("cool_20", "cool", 20),
        ("cool_22", "cool", 22),
        ("cool_24", "cool", 24),
        ("heat_22", "heat", 22),
        ("dry_22",  "dry",  22),
    ]

    for cmd_name, mode, temp in checks:
        if cmd_name not in commands:
            results["fail"].append(f"{cmd_name}: non trovato nel db")
            continue
        try:
            sample = commands[cmd_name]["samples"][0]
            real_hex = sample["analysis"]["frames"][0]["hex_msb"]
            real_bytes = [int(real_hex[i:i+2], 16) for i in range(0, len(real_hex), 2)]

            gen_raw = generate_raw(mode, temp)
            gen_analysis = analyze_raw(gen_raw)
            gen_hex = gen_analysis["frames"][0]["hex_msb"]
            gen_bytes = [int(gen_hex[i:i+2], 16) for i in range(0, len(gen_hex), 2)]

            if gen_bytes == real_bytes:
                results["ok"].append(cmd_name)
            else:
                results["fail"].append(
                    f"{cmd_name}: gen={gen_hex} real={real_hex}"
                )
        except Exception as e:
            results["fail"].append(f"{cmd_name}: errore={e}")

    return results
