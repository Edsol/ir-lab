# License notes

IR Lab is distributed under **GPL-3.0-or-later** (see [LICENSE](LICENSE)).

Copyright (C) 2026 IR Lab contributors

## Why GPL

IR Lab uses [irtuya](https://github.com/pasthev/irtuya) as an **optional**
dependency, licensed GPL-3.0. That is why IR Lab adopts GPL-3.0-or-later.

irtuya is used only in `ir_lab/nec_codec.py`, for NEC decode/encode, the
Broadlink format and format auto-detection. It installs separately:

```bash
pip install -e ".[nec]"
```

## Original code

The `ir_lab/tuya_codec.py` module is an **original reimplementation** of the
Tuya IR format, written from scratch against the public description of the
format, without copying code from irtuya or any other GPL project. It does not
depend on irtuya and works without the `[nec]` extra.

The same holds for the generators in `ir_lab/generators/`: they are the result
of reverse-engineering done with this tool, starting from samples captured off
physical remotes.

## References

The Tuya IR format is publicly documented in:

- [IRTuya](https://github.com/pasthev/irtuya) — Pasthev
- [Sensus](https://pasthev.github.io/sensus/) — online analyser
- [Tuya IR format](https://gist.github.com/mildsunrise/1d576669b63a260d2cff35fda63ec0b5) — mildsunrise
