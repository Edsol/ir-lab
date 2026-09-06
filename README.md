# IR Lab

[![CI](https://github.com/Edsol/ir-lab/actions/workflows/ci.yaml/badge.svg)](https://github.com/Edsol/ir-lab/actions/workflows/ci.yaml)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)

A local Python workbench for capturing, storing, replaying and analysing IR
codes learned through an IR blaster managed by Zigbee2MQTT/MQTT.

## What it is for

Most IR solutions for home automation are **archives**: you capture or import
one code per state, and for an air conditioner that means hundreds of codes
(mode x temperature x fan x swing).

IR Lab takes the opposite route. It exists to understand a protocol well enough
to **generate** any code on the fly, without ever having seen it. The output of
that work are the generators in [`ir_lab/generators/`](ir_lab/generators/),
which are then ported to [IRBridge](https://github.com/Edsol/irbridge), the
Home Assistant integration that uses them in production.

```
physical remote
      |  ir-lab capture / learn      (acquisition over MQTT)
      v
data/remotes.json                    (samples: tuya + raw + analysis)
      |  ir-lab compare / analyze    (which bits move?)
      v
ir_lab/generators/<protocol>.py      (the protocol, in Python)
      |  port
      v
IRBridge                             (Home Assistant, codes generated on the fly)
```

## Philosophy

IR Lab is not the finished remote. It is the workbench for:

1. putting the blaster into learning mode;
2. reading several codes in sequence;
3. attaching a name and functional metadata to each code;
4. storing the original Tuya code;
5. converting it to raw timings;
6. analysing header, bits, frames and hex;
7. comparing samples and similar commands;
8. replaying a code to test it;
9. preparing the work for Home Assistant.

## Current state

- `ir-lab` CLI;
- interactive wizard with Inquirer-style prompts via `InquirerPy`;
- MQTT configuration through `config.yaml`;
- single acquisition (`learn`);
- sequential acquisition from YAML (`capture`);
- local JSON storage (`data/remotes.json`);
- code replay (`send`);
- Tuya base64 -> raw conversion;
- raw -> Tuya base64 conversion using uncompressed literal blocks;
- generic raw -> frame/bit/hex analysis;
- command comparison (`compare`);
- protocol generators (`generate`) for Midea/Ferroli and Electra/AUX/Beko;
- Tuya Cloud client for querying the official IR library.

There is no web UI and no Home Assistant integration here: that is
[IRBridge](https://github.com/Edsol/irbridge), a separate project.

### Reverse-engineered protocols

| Protocol | Devices | Temp | Fan | Swing |
|---|---|---|---|---|
| `midea` | Ferroli, Midea | 16-30 C | auto only | not yet |
| `electra` | Beko, AUX, Electrolux, Frigidaire | 16-32 C | auto/high/mid/low | vertical |

Midea fan speed has not been isolated yet: it needs samples with mode and
temperature held fixed and only the fan speed changing.

## Installation

```bash
cd ir-lab
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
pytest
```

## Configuration

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml`:

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

For the Tuya iH-F8260 over Zigbee2MQTT, learning goes through `learn_ir_code`
and sending through `ir_code_to_send` on the `/set` topic.

## Quick start

### Interactive wizard

```bash
ir-lab wizard
```

The wizard asks for the MQTT emitter, remote, brand, device type, command name,
tags and sample count. For every sample it puts the blaster into learning mode,
waits for `learned_ir_code`, converts the Tuya code to raw, analyses it and
stores everything in `data/remotes.json`.

### Single acquisition

```bash
ir-lab learn \
  --remote midea_bedroom \
  --command cool_22_auto \
  --brand Midea \
  --device-type climate \
  --tags mode=cool,temperature=22,fan=auto \
  --samples 2
```

### Sequential acquisition

```bash
ir-lab capture --session sessions/midea_cool_sweep.yaml --samples 2
```

This is the recommended mode for studying a protocol: change one variable at a
time and capture several samples of the same command.

### List, send, analyse

```bash
ir-lab list
ir-lab send --remote midea_bedroom --command cool_22_auto
ir-lab analyze --remote midea_bedroom
ir-lab compare --remote midea_bedroom --commands cool_21_auto cool_22_auto cool_23_auto
```

### Generating without a remote

Once a protocol is understood, codes are produced without the physical remote:

```bash
ir-lab generate --protocol midea --mode cool --temp 22
ir-lab generate --protocol electra --mode heat --temp 20 --fan high
```

### Offline decoding

```bash
ir-lab decode --tuya "CUsjhRFhApgG..."
ir-lab encode --raw "9000,4500,600,600,600,1680"
```

Note: the current encoder uses uncompressed literal blocks. The resulting code
is longer than the learned one, but useful for experiments and controlled
round-trips.

## Storage format

The main file is:

```text
data/remotes.json
```

A command can hold several samples. Every sample keeps `tuya`, `raw`,
`analysis`, a timestamp and any decoding errors.

## Layout

```text
config.example.yaml              Example MQTT config
config.yaml                      Local config, git-ignored
sessions/                        Sequential acquisition sessions
data/remotes.json                Local database, git-ignored
ir_lab/cli.py                    CLI commands
ir_lab/mqtt_client.py            MQTT bridge to Zigbee2MQTT
ir_lab/tuya_codec.py             Tuya base64 <-> raw timings codec
ir_lab/raw_analyzer.py           Header/bit/frame/hex analysis
ir_lab/storage.py                JSON storage
ir_lab/prompts.py                InquirerPy prompt wrapper
ir_lab/generators/               Reverse-engineered protocols
ir_lab/tuya_cloud.py             Tuya Cloud IR library client
docs/protocol_midea.md           Midea protocol analysis
SKILL.md                         Guide for analysing captures with an LLM
```

## Analysing captures with an LLM

Reading diffs between frames to find the temperature field and the checksum is
work a language model does well, given the right framing.
[`SKILL.md`](SKILL.md) is a tool-agnostic guide for exactly that: point any LLM
at it along with your `ir-lab compare` output.

## Tuya Cloud (optional)

`ir_lab/tuya_cloud.py` queries Tuya's official IR library, useful for comparing
your own samples against a brand's known codes. It needs credentials from a
project on [iot.tuya.com](https://iot.tuya.com), in a `.env` file that is
**never committed**:

```bash
ACCESS_ID=...
ACCESS_SECRET=...
```

## Relationship with IRBridge

IR Lab is the workbench; [IRBridge](https://github.com/Edsol/irbridge) is the
product. A new protocol always follows the same path: captured and analysed
here, and once the generator is verified, ported to IRBridge as a
`ClimateGenerator`.

The two projects stay separate on purpose. Reverse-engineering is a rare,
terminal-bound activity; the integration has to be installable through HACS
without dragging the lab tooling along.

## Roadmap

- [x] Verified Midea/Ferroli generator
- [x] Electra/AUX/Beko generator
- [ ] Midea fan and swing (needs samples)
- [ ] More protocols: LG, Daikin, Samsung, Panasonic
- [ ] FastLZ compression in the Tuya encoder
- [ ] Home Assistant add-on, to capture without a PC on the same network

## Notes on the Tuya codec

The bundled codec is written for the lab and aims to be readable. It decodes
learned Tuya codes into raw timings. The encoder produces valid payloads using
uncompressed literal blocks, useful for experiments.

Useful references:

- IRTuya: https://github.com/pasthev/irtuya
- Sensus: https://pasthev.github.io/sensus/
- mildsunrise's Tuya IR format notes: https://gist.github.com/mildsunrise/1d576669b63a260d2cff35fda63ec0b5
- InquirerPy: https://inquirerpy.readthedocs.io/

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The most useful contribution is a new
protocol: if you own an unsupported air conditioner, capturing the samples and
opening an issue with the JSON file is already half the work.

## License

GPL-3.0-or-later — see [LICENSE](LICENSE) and [NOTICE.md](NOTICE.md).
