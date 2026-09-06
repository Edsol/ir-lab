# Contributing to IR Lab

The most useful contribution to this project is **a new protocol**. Everything
else — refactoring, tests, documentation — is welcome, but the generators are
the reason IR Lab exists.

## Adding a protocol

You do not need to know how to read IR frame bits to start. The hard part is
having the right samples, and for that the physical remote is enough.

### 1. Capture single-variable samples

The rule that makes analysis possible: **change one thing at a time**. Comparing
`cool 22C auto` against `heat 25C high` moves three fields plus the checksum,
and tells you nothing. Comparing `cool 21C auto` against `cool 22C auto` moves
the temperature and the checksum, and nothing else.

```bash
ir-lab capture --session sessions/my_protocol.yaml --samples 2
```

Start from [`sessions/generic_remote_template.yaml`](sessions/generic_remote_template.yaml).
A good first session:

- a temperature sweep at fixed mode and fan (16, 17, 18… C);
- a mode sweep at fixed temperature (cool, heat, dry, auto);
- a fan sweep at fixed mode and temperature;
- power on and power off.

Two samples per command: if they differ, the capture was disturbed.

### 2. See what changes

```bash
ir-lab compare --remote my_ac --commands cool_21_auto cool_22_auto cool_23_auto
ir-lab analyze --remote my_ac
```

`compare` highlights the bytes that differ. Look for:

- **the temperature field** — usually a nibble incrementing by 1 per degree,
  often with an offset (16C = 0x0, 17C = 0x1…) and sometimes bit-reversed;
- **the checksum** — nearly always the last byte, often the sum of the others
  modulo 256, or an XOR;
- **the constant bytes** — header and footer, identical in every frame.

[`docs/protocol_midea.md`](docs/protocol_midea.md) is the full analysis of a
real protocol: use it as a reference for the level of detail needed.

An LLM is good at this step. [`SKILL.md`](SKILL.md) is a guide you can hand to
any model along with your `compare` output.

### 3. Write the generator

A generator in `ir_lab/generators/<name>.py` exposes:

```python
def generate_raw(mode: str, temp: int, **kwargs) -> list[int]:
    """Timings in microseconds, alternating mark/space."""
```

The pattern is always the same: build the frame bytes, compute the checksum,
then expand the bits into timings following the protocol's header and
durations. See [`ir_lab/generators/midea.py`](ir_lab/generators/midea.py) for
the two-subframe case, and [`electra.py`](ir_lab/generators/electra.py) for one
with fan and swing.

### 4. Verify against real samples

This is the step that separates a working generator from a plausible one:

```bash
ir-lab generate --protocol my_protocol --mode cool --temp 22 --format raw
```

The generated raw must match the captured one, within receiver tolerance.
`midea.py` has a `verify_against_db()` function that runs the comparison across
the whole database: replicate it.

Then try it on the actual air conditioner. If it turns on, the temperature is
right and the mode matches, the generator is good.

### 5. Port it to IRBridge

Once verified, the generator goes to
[IRBridge](https://github.com/Edsol/irbridge) as a `ClimateGenerator`: a class
declaring its `ClimateCapabilities` and calling `generate_raw()`. IRBridge's
README has the procedure.

## Don't feel like writing code?

Open an issue with your captured samples anyway, using the
[New protocol](.github/ISSUE_TEMPLATE/new-protocol.yaml) template. A clean
dataset is half the work, and someone else can do the analysis.

## Style

- Python 3.11+, light dependencies.
- `ruff check ir_lab tests` and `pytest` must pass (CI enforces both).
- Error messages in English, understandable by someone who did not write the code.
- The code is also there to *explain* the protocol: prefer a readable function
  over a compact one.
- Never hide the original data: a sample always keeps both `tuya` and `raw`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```
