# Protocollo IR Midea — Note di reverse engineering

Dispositivo testato: condizionatore Midea, telecomando modello camera,
blaster Tuya ZS05 (WMUN) via Zigbee2MQTT.

## Formato del segnale

- **Modulazione**: NEC-like, PWM
- **Header**: ~9000 µs mark + ~4500 µs space
- **Bit mark**: ~650 µs fisso
- **Zero space**: ~560 µs
- **One space**: ~1670 µs
- **Gap tra frame**: ~20000 µs
- **Frame per messaggio**: 2
- **Frame 1**: 35 bit (4 byte + 3 bit tail fisso `010`)
- **Frame 2**: 32 bit (4 byte)

## Struttura frame 1 (35 bit)

```
B0[7:0]  B1[7:0]  B2[7:0]  B3[7:0]  tail[2:0]
```

### Campi identificati

| Campo | Posizione | Note |
|---|---|---|
| Modalità | B0, B2 | Vedi tabella modalità |
| Rolling counter | B0 bit 4 | Alterna 0↔1 ad ogni pressione, ignorare per decodifica |
| Temperatura | B1 | `rev_bits(temp-15) << 4`, ignorata per fan |
| Fan speed | B0 bit 3-4 (ipotesi) | Da confermare con sweep fan taggato |
| Device address | B3 = `0x0A` | Fisso su tutti i campioni |
| Tail | bit 32-34 = `010` | Fisso |

### Encoding temperatura in B1

`B1 = rev_bits(temp - base) << 4`

dove `rev_bits` inverte i 4 bit LSB (bit 0-3) e `base` dipende dalla modalità:
- cool / heat / fan: `base = 15`
- dry / auto: `base = 16` (verificato empiricamente)

| Temp | temp-15 | binario | rev | B1 hex |
|------|---------|---------|-----|--------|
| 16°  | 1       | 0001    | 1000 | 0x80  |
| 17°  | 2       | 0010    | 0100 | 0x40  |
| 18°  | 3       | 0011    | 1100 | 0xC0  |
| 19°  | 4       | 0100    | 0010 | 0x20  |
| 20°  | 5       | 0101    | 1010 | 0xA0  |
| 21°  | 6       | 0110    | 0110 | 0x60  |
| 22°  | 7       | 0111    | 1110 | 0xE0  |
| 23°  | 8       | 1000    | 0001 | 0x10  |
| 24°  | 9       | 1001    | 1001 | 0x90  |
| 25°  | 10      | 1010    | 0101 | 0x50  |

Lo stesso encoding vale identicamente in cool e heat.

### Tabella modalità — F1 e F2

Rolling counter in stato 0 (bit4 di B0 = 0).

| Modalità | F1.B0 (clean) | F1.B2 | F2.B0 | Icona display |
|----------|---------------|-------|-------|---------------|
| fan_only | 0x08          | 0x06  | 0x00  | frecce ventola |
| cool     | 0x86          | 0x07  | 0x80  | fiocco di neve |
| dry      | 0x4A          | 0x07  | 0x80  | goccioline |
| auto     | 0xC0          | 0x06  | 0x00  | FAN AUTO |
| heat     | 0x2C          | 0x06  | 0x60  | sole ☀️ |

Sequenza ciclica tasto MODE: fan_only → cool → dry → auto → heat → fan_only → ...

F1.B1 = temperatura (stesso encoding per tutte le modalità con temperatura).
F1.B3 = `0x0A` (device address, fisso).

## Struttura frame 2 (32 bit)

```
B0[7:0]  B1[7:0]  B2[7:0]  B3[7:0]
```

| Campo | Valore | Note |
|---|---|---|
| B0 | dipende da modalità | `0x80` cool/dry, `0x60` heat, `0x00` auto/fan |
| B1 | `0x04` | Fisso su tutti i campioni |
| B2 | `0x00` | Fisso su tutti i campioni |
| B3 | calcolato | Dipende da modalità e temperatura — vedi formula |

### Formula F2.B3

F2.B3 non è un checksum di F1: è derivato da una rappresentazione LSB lineare
specifica per modalità.

```
F2_LSB(mode, temp) = F2_BASE[mode] + (temp - 15) * 0x10
F2.B3 = rev_bits(F2_LSB & 0xFF)
```

dove `rev_bits` inverte tutti e 8 i bit del byte.

Costanti `F2_BASE` per modalità (verificate empiricamente su sweep 16°-25°):

| Modalità | F2_BASE     | Sweep verificato |
|----------|-------------|-----------------|
| cool     | 0x01200050  | ✅ 16°-25°       |
| heat     | 0x06200080  | ✅ 16°-25°       |
| dry      | 0x01200050  | ✅ 22° (stessa base di cool) |
| auto     | 0x00200060  | ✅ 22° (verificato)           |
| fan      | 0x00200040  | ✅ (B3 fisso 0x0B da campione) |

### Sweep temperatura cool (fan=auto) — acquisito e verificato

| Temp | F1 hex   | F2 hex   | B0   | B1   | B2   |
|------|----------|----------|------|------|------|
| 16°  | 8680070A | 80040006 | 0x86 | 0x80 | 0x07 |
| 17°  | 8640070A | 8004000E | 0x86 | 0x40 | 0x07 |
| 18°  | 86C0070A | 80040001 | 0x86 | 0xC0 | 0x07 |
| 19°  | 8620070A | 80040009 | 0x86 | 0x20 | 0x07 |
| 20°  | 86A0070A | 80040005 | 0x86 | 0xA0 | 0x07 |
| 21°  | 8660070A | 8004000D | 0x86 | 0x60 | 0x07 |
| 22°  | 86E0070A | 80040003 | 0x86 | 0xE0 | 0x07 |
| 23°  | 8610070A | 8004000B | 0x86 | 0x10 | 0x07 |
| 24°  | 8690070A | 80040007 | 0x86 | 0x90 | 0x07 |
| 25°  | 8650070A | 8004000F | 0x86 | 0x50 | 0x07 |

Nota: i campioni reali mostrano B0=`0x96` (rolling counter=1) o `0x86` (=0).
La tabella sopra usa rolling counter=0. Il generatore usa sempre 0.

### Sweep temperatura heat (fan=auto) — acquisito e verificato

| Temp | F1 hex   | F2 hex   | B0   | B1   | B2   |
|------|----------|----------|------|------|------|
| 16°  | 2C80060A | 60040009 | 0x2C | 0x80 | 0x06 |
| 17°  | 2C40060A | 60040005 | 0x2C | 0x40 | 0x06 |
| 18°  | 2CC0060A | 6004000D | 0x2C | 0xC0 | 0x06 |
| 19°  | 2C20060A | 60040003 | 0x2C | 0x20 | 0x06 |
| 20°  | 2CA0060A | 6004000B | 0x2C | 0xA0 | 0x06 |
| 21°  | 2C60060A | 60040007 | 0x2C | 0x60 | 0x06 |
| 22°  | 2CE0060A | 6004000F | 0x2C | 0xE0 | 0x06 |
| 23°  | 2C10060A | 60040000 | 0x2C | 0x10 | 0x06 |
| 24°  | 2C90060A | 60040008 | 0x2C | 0x90 | 0x06 |
| 25°  | 2C50060A | 60040004 | 0x2C | 0x50 | 0x06 |

## Dataset raccolta dati

Vedi `sessions/midea_protocol_decode.yaml` per la procedura dettagliata.

| Blocco | Comandi | Serve a | Stato |
|---|---|---|---|
| 1 — sweep temperatura cool | cool 16°→25°, fan=auto | byte temperatura | ✅ acquisito — generatore verificato 10/10 |
| 2 — sweep temperatura heat | heat 16°→25°, fan=auto | confronto modalità | ✅ acquisito — generatore verificato 10/10 |
| 3 — sweep modalità | dry/auto/fan_only a 22° | byte modalità completo | ✅ acquisito |
| 4 — sweep fan speed | cool 22°, fan=auto/low/mid/high | byte fan | ⬜ da acquisire con tag espliciti |
| 5 — power on/off per modalità | power on cool/heat | se power include stato | ⬜ da acquisire |

## Generatore codici

Il generatore è implementato in `ir_lab/midea_generator.py`.

```bash
# Genera codice Tuya per cool 22°
ir-lab generate --mode cool --temp 22

# Genera raw timings
ir-lab generate --mode heat --temp 20 --format raw

# Genera e invia direttamente
ir-lab generate --mode cool --temp 22 --send
```

Modalità supportate: `cool`, `heat`, `dry`, `auto`, `fan`.
Temperatura: 16-30°C (ignorata per `fan`).

## Procedura raccolta dati — sweep temperatura

> **IMPORTANTE per chiunque replichi questa acquisizione:**
> partire SEMPRE dalla temperatura minima supportata (di solito 16°C).

1. Accendere il condizionatore nella modalità desiderata (cool o heat), fan=auto.
2. Portare la temperatura al **minimo** (16°C) con il telecomando fisico.
3. Verificare sul display che mostri 16°C.
4. Acquisire il primo comando (es. `cool_16_auto`), 3 sample.
5. Premere **una volta** il tasto `+` → display mostra 17°C.
6. Acquisire il comando successivo. Ripetere fino a 25°C.

Se si sbaglia un passo: aggiungere `skip: true` nei tag del sample errato
e riacquisire. Non eliminare il sample — serve per capire l'errore.

## Nota sul rolling counter

Il bit 4 di B0 alterna 0↔1 ad ogni pressione del telecomando, indipendentemente
dal comando. Per confrontare due acquisizioni dello stesso tasto: ignorare bit 4
(sostituirlo con 0). Con 3+ sample dello stesso stato si identifica il valore stabile.

**Il condizionatore richiede rolling counter=1 (bit4=1).** Verificato empiricamente:
con rc=0 il condizionatore non risponde. Il generatore usa sempre rc=1.

I campioni acquisiti nel dataset hanno tutti rc=1 perché il telecomando fisico
era in quello stato durante l'acquisizione.

## Comandi già utilizzabili in HA

Tutti i codici Tuya acquisiti sono reinviabili 1:1 senza decodifica completa:

```bash
ir-lab send --remote midea_camera --command cool_22_auto
```

oppure direttamente via MQTT:

```json
{"ir_code_to_send": "<codice_tuya>"}
```

su topic `zigbee2mqtt/<friendly_name_blaster>/set`.
