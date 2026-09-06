# Analysing IR captures with an LLM

A guide for using any language model to reverse-engineer an IR protocol from
[IR Lab](https://github.com/Edsol/ir-lab) captures. Tool-agnostic: paste it into
Claude, ChatGPT, a local model, or drop it in as a skill file.

The goal is never "decode this code". It is to find **the rule** that maps a
device state (mode, temperature, fan, swing) to a frame — so the frame can be
generated for states you never captured.

## What to give the model

Two things, and the second matters more than the first.

**1. The frames**, from `ir-lab compare`:

```
command | frame_1
--------+---------------------------
cool_20 | C3E60700050004000004000057
cool_22 | C3EE070005000400000400005F
cool_24 | C3E10700050004000004000050
```

**2. What each frame means.** The command names are the labels of a supervised
problem. Without them the hex is unlabelled data and the model can only guess.
State plainly: "these are the same air conditioner, cooling mode, fan auto, only
the temperature differs — 20C and 22C."

Add `ir-lab analyze` output when the timings matter (they do for writing a
generator, not for finding fields):

```
header: [8997, 4530]
bit: mark~554 zero~554 one~1706 threshold~1130.0
frame 1: 104 bit hex=C3EE070005000400000400005F
```

## The prompt that works

> Here are IR frames captured from a Beko air conditioner. All are cooling mode,
> fan auto; only the target temperature differs. Each byte is hex, MSB first.
>
> ```
> cool_16  C3E207000500040000040080D3
> cool_18  C3EA070005000400000400005B
> cool_20  C3E60700050004000004000057
> cool_22  C3EE070005000400000400005F
> cool_24  C3E10700050004000004000050
> ```
>
> Work out:
> 1. which bytes are constant (header/footer);
> 2. which byte or nibble encodes the temperature, and the exact mapping;
> 3. whether there is a checksum, and its formula.
>
> Show the reasoning per byte position. Where a hypothesis fits some frames but
> not all, say so instead of forcing it.

That last sentence earns its place. Without it models tend to state a clean rule
that fits two frames and breaks on the third.

## What to ask for, in order

**Byte-position diff first.** Ask the model to line the frames up and report,
per position, whether it is constant or varying. This is mechanical and
verifiable, and it constrains everything after it.

**Then the varying fields.** For each varying position, ask how it relates to
the state that changed. This is where the real captures above get instructive.
Byte 1 reads `E2, EA, E6, EE, E1` for 16, 18, 20, 22, 24C — not monotonic, and
no obvious arithmetic. A model asked to force a rule onto that will invent one.

The frames are LSB-first. Reverse each byte's bits and the field falls out:

| Temp | byte 1 | reversed | high nibble |
|---|---|---|---|
| 16C | E2 | 47 | 4 |
| 18C | EA | 57 | 5 |
| 20C | E6 | 67 | 6 |
| 22C | EE | 77 | 7 |
| 24C | E1 | 87 | 8 |

Now it is linear: high nibble = `(temp - 8) / 2`, low nibble constant at 7. This
is why bit order is worth asking about early, not last.

**Then the checksum.** Common shapes, worth naming explicitly in the prompt:

- sum of all preceding bytes, mod 256;
- XOR of all preceding bytes;
- sum of nibbles, mod 16;
- one of the above, then inverted or offset by a constant.

Ask for the formula *and* the verification against every captured frame. In the
Beko frames above it is XOR of all preceding bytes, plus `0x30`:

| Temp | XOR of bytes 0..n-1 | last byte |
|---|---|---|
| 16C | A3 | D3 |
| 18C | 2B | 5B |
| 20C | 27 | 57 |
| 22C | 2F | 5F |
| 24C | 20 | 50 |

A constant offset like that `0x30` is easy to miss: a model checking only "is it
the plain XOR?" reports no checksum found. Ask for the difference between the
candidate and the actual byte, not just a yes/no.

**Bit order, whenever a field resists explanation.** As the temperature field
above shows, IR protocols frequently send LSB-first while the analyser prints
MSB-first, which makes a clean field look scrambled. Asking the model to retry
with each byte's bits reversed resolves a surprising share of dead ends.

## Guardrails that matter

**Demand verification, not assertion.** Every claim should come with the check
against all frames. "Byte 1 is the temperature" is worthless; "byte 1 is
`(temp-16)<<3`, which gives E6 for 20C, EE for 22C, F6 for 24C — matching all
three captures" is a result.

**Watch for the two-frame trap.** Any rule fits two data points. Three is the
minimum for a linear field; more for anything else. If you only have two
captures, capture more before trusting the answer.

**Separate what changed from what should have.** If you captured `cool_22` and
`heat_22` and *three* bytes differ, one of them may be a repeat counter or a
toggle bit, not the mode. Ask the model to flag positions that vary
inconsistently with the stated state change.

**Distrust round numbers.** A model that reports "the checksum is the sum mod
256" without showing arithmetic has often pattern-matched a common protocol
rather than read your data. Ask for the sums.

**Two frames per code is normal.** Many AC protocols send the state twice, the
second frame inverted or repeated. If `analyze` reports two frames, ask whether
frame 2 is the bitwise complement of frame 1 — that is a common integrity scheme
and it confirms field boundaries for free.

## From analysis to generator

Once the fields hold across every capture, the generator is mechanical. Ask for
it directly:

> Write a Python function `generate_bytes(mode, temp, fan)` returning the frame
> bytes for this protocol, following the fields established above. Then a
> `_build_raw(frame_bytes)` that expands them into raw timings using
> header [8997, 4530], mark 554us, zero-space 554us, one-space 1706us.

Then verify against the captured raw, not just against the model's word for it:

```bash
ir-lab generate --protocol my_protocol --mode cool --temp 22 --format raw
```

Compare with the captured raw for the same state. They should match within
receiver tolerance (tens of microseconds). If they match, try the code on the
actual unit — the only test that fully counts.

## What LLMs are bad at here

Be aware of where to keep your own hands on the wheel:

- **Timing tolerance.** Captured timings jitter; a model comparing exact values
  will report a mismatch where a human sees a match. Compare structure, not
  microseconds.
- **Long hex strings.** Transcription errors happen mid-string. If a conclusion
  looks strange, verify the model is reading the bytes you actually sent.
- **Confident checksum guesses.** This is the single most common failure. The
  checksum is where you should demand arithmetic every time.
- **Protocols it half-remembers.** A model that recognises "this looks like the
  Gree protocol" may start filling in details from memory rather than from your
  captures. Useful as a hypothesis, dangerous as a conclusion.

## Capture quality decides everything

No prompt rescues bad data. Before the analysis:

- **change one variable at a time** — a sweep of temperature at fixed mode and
  fan is worth more than twenty scattered commands;
- **capture at least three points per field**, ideally the extremes and a middle
  value;
- **take two samples of each command** — if they differ, the capture was
  disturbed and the frame is not trustworthy;
- **include power off** — it is often a distinct frame shape, and it reveals
  which bits are the power flag.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the capture workflow.
