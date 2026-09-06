from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

from . import __version__
from .config import AppConfig, EmitterSettings, load_config
from .errors import CodecError, ConfigError, IrLabError, StorageError
from .mqtt_client import MqttIrClient, discover_ir_blasters
from .prompts import confirm, key_value_tags, press_enter, select, text
from .raw_analyzer import analyze_raw, format_analysis
from .storage import DEFAULT_DATA_PATH, RemoteStore
from .tuya_codec import decode_tuya_ir, encode_tuya_ir, parse_raw_text, raw_to_text
from .generators import midea as midea_generator
from .generators import electra as electra_generator


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nAborted.", file=sys.stderr)
        raise SystemExit(130) from None
    except IrLabError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ir-lab",
        description="Local workbench for Tuya/Zigbee2MQTT IR codes over MQTT.",
    )
    parser.add_argument("--version", action="version", version=f"ir-lab {__version__}")
    sub = parser.add_subparsers(dest="command_name", required=True)

    p_init = sub.add_parser("init", help="Create config.yaml and working directories")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_decode = sub.add_parser("decode", help="Convert a Tuya code to raw timings and analyse it")
    p_decode.add_argument("--tuya", required=True)
    p_decode.add_argument("--json", action="store_true")
    p_decode.set_defaults(func=cmd_decode)

    p_encode = sub.add_parser("encode", help="Convert raw timings to a Tuya code")
    p_encode.add_argument("--raw", required=True)
    p_encode.set_defaults(func=cmd_encode)

    p_learn = sub.add_parser("learn", help="Capture samples for one command")
    add_common_args(p_learn)
    p_learn.add_argument("--remote", required=True)
    p_learn.add_argument("--command", required=True)
    p_learn.add_argument("--label", default=None)
    p_learn.add_argument("--emitter", default=None)
    p_learn.add_argument("--samples", type=int, default=1)
    p_learn.add_argument("--timeout", type=int, default=45)
    p_learn.add_argument("--brand", default=None)
    p_learn.add_argument("--device-type", default=None)
    p_learn.add_argument("--tags", default="")
    p_learn.add_argument("--test", action="store_true")
    p_learn.set_defaults(func=cmd_learn)

    p_capture = sub.add_parser("capture", help="Run a sequential capture session from YAML")
    add_common_args(p_capture)
    p_capture.add_argument("--session", required=True)
    p_capture.add_argument("--samples", type=int, default=None)
    p_capture.add_argument("--timeout", type=int, default=45)
    p_capture.add_argument("--no-test", action="store_true")
    p_capture.set_defaults(func=cmd_capture)

    p_wizard = sub.add_parser("wizard", help="Interactive Inquirer-style wizard")
    add_common_args(p_wizard)
    p_wizard.add_argument("--timeout", type=int, default=45)
    p_wizard.set_defaults(func=cmd_wizard)

    p_send = sub.add_parser("send", help="Send a stored command")
    add_common_args(p_send)
    p_send.add_argument("--remote", required=True)
    p_send.add_argument("--command", required=True)
    p_send.add_argument("--emitter", default=None)
    p_send.add_argument("--sample", default="active")
    p_send.set_defaults(func=cmd_send)

    p_list = sub.add_parser("list", help="List stored remotes and commands")
    p_list.add_argument("--data", default=str(DEFAULT_DATA_PATH))
    p_list.add_argument("--remote", default=None)
    p_list.set_defaults(func=cmd_list)

    p_analyze = sub.add_parser("analyze", help="Analyse stored codes")
    p_analyze.add_argument("--data", default=str(DEFAULT_DATA_PATH))
    p_analyze.add_argument("--remote", required=True)
    p_analyze.add_argument("--command", default=None)
    p_analyze.add_argument("--sample", default="active")
    p_analyze.add_argument("--json", action="store_true")
    p_analyze.set_defaults(func=cmd_analyze)

    p_compare = sub.add_parser("compare", help="Compare frames/hex across commands")
    p_compare.add_argument("--data", default=str(DEFAULT_DATA_PATH))
    p_compare.add_argument("--remote", required=True)
    p_compare.add_argument("--commands", nargs="+", required=True)
    p_compare.add_argument("--sample", default="active")
    p_compare.set_defaults(func=cmd_compare)

    p_delete = sub.add_parser("delete", help="Delete a command or a single sample")
    p_delete.add_argument("--data", default=str(DEFAULT_DATA_PATH))
    p_delete.add_argument("--remote", default=None)
    p_delete.add_argument("--command", default=None)
    p_delete.add_argument("--sample", default=None, type=int, help="Sample index (0-based). Omit to delete the whole command.")
    p_delete.set_defaults(func=cmd_delete)

    p_generate = sub.add_parser("generate", help="Generate an IR code without the physical remote")
    p_generate.add_argument("--protocol", choices=["midea", "electra"], default="midea",
                            help="Protocol: midea (Ferroli/Midea, default) | electra (Beko/AUX/Electra)")
    p_generate.add_argument("--mode", required=True, choices=["cool", "heat", "dry", "auto", "fan"],
                            help="Mode: cool | heat | dry | auto | fan")
    p_generate.add_argument("--temp", type=int, default=22,
                            help="Target temperature in C (ignored for fan). Default: 22")
    p_generate.add_argument("--fan", choices=["auto", "high", "mid", "low"], default="auto",
                            help="Fan speed (electra only): auto | high | mid | low. Default: auto")
    p_generate.add_argument("--swing", action="store_true", help="Enable vertical swing (electra only)")
    p_generate.add_argument("--power", choices=["on", "off"], default="on",
                            help="Power on or off (electra only). Default: on")
    p_generate.add_argument("--format", choices=["tuya", "raw", "both"], default="tuya",
                            help="Output format: tuya (default) | raw | both")
    p_generate.add_argument("--send", action="store_true", help="Send the generated code over MQTT")
    p_generate.add_argument("--emitter", default=None)
    add_common_args(p_generate)
    p_generate.set_defaults(func=cmd_generate)

    return parser


def add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--data", default=str(DEFAULT_DATA_PATH))


def cmd_init(args: argparse.Namespace) -> None:
    target = Path("config.yaml")
    source = Path("config.example.yaml")
    if target.exists() and not args.force:
        raise ConfigError("config.yaml already exists. Use --force to overwrite")
    if not source.exists():
        raise ConfigError("config.example.yaml not found")
    shutil.copyfile(source, target)
    Path("data").mkdir(exist_ok=True)
    Path("sessions").mkdir(exist_ok=True)
    print("Created config.yaml. Edit the MQTT host and the blaster friendly name.")


def cmd_decode(args: argparse.Namespace) -> None:
    raw = decode_tuya_ir(args.tuya)
    analysis = analyze_raw(raw)
    if args.json:
        print(json.dumps({"raw": raw, "analysis": analysis}, ensure_ascii=False, indent=2))
        return
    print("Raw:")
    print(raw_to_text(raw))
    print("\nAnalysis:")
    print(format_analysis(analysis))


def cmd_encode(args: argparse.Namespace) -> None:
    raw = parse_raw_text(args.raw)
    print(encode_tuya_ir(raw))


def resolve_emitter(config: AppConfig, name: str | None) -> EmitterSettings:
    """Risolve l'emitter da usare, con fallback alla discovery MQTT.

    Ordine di priorità:
    1. --emitter passato esplicitamente -> cerca in config.yaml
    2. config.yaml ha esattamente un emitter -> usato automaticamente
    3. config.yaml ha più emitter -> select interattivo tra quelli configurati
    4. config.yaml non ha emitter -> discovery su zigbee2mqtt/bridge/devices,
       poi select interattivo tra i blaster IR trovati
    """
    if name is not None:
        return config.get_emitter(name)
    if config.emitters:
        if len(config.emitters) == 1:
            return next(iter(config.emitters.values()))
        chosen = select("Pick an emitter", list(config.emitters.keys()))
        return config.get_emitter(chosen)
    # Nessun emitter in config.yaml: discovery MQTT
    print("No emitter in config.yaml - discovering IR blasters over MQTT...")
    blasters = discover_ir_blasters(config.mqtt)
    if not blasters:
        raise ConfigError(
            "No IR blaster found on zigbee2mqtt/bridge/devices. "
            "Verifica che Zigbee2MQTT sia attivo e il dispositivo sia accoppiato, "
            "oppure configura manualmente gli emitter in config.yaml."
        )
    if len(blasters) == 1:
        print(f"Blaster found: {blasters[0].friendly_name}")
        return blasters[0]
    chosen_name = select("Pick an IR blaster", [e.friendly_name for e in blasters])
    return next(e for e in blasters if e.friendly_name == chosen_name)


def cmd_learn(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    emitter = resolve_emitter(config, args.emitter)
    store = RemoteStore(args.data)
    tags = key_value_tags(args.tags)
    mqtt_client = MqttIrClient(config.mqtt)
    for sample_index in range(args.samples):
        print(f"\n[{sample_index + 1}/{args.samples}] {args.remote}/{args.command}")
        if sample_index == 0:
            press_enter("Press ENTER to start, then press the remote button for each sample")
        else:
            print("Press the button on the remote...")
        learned = mqtt_client.learn_once(emitter, timeout=args.timeout)
        sample = save_learned_sample(
            store,
            remote=args.remote,
            command=args.command,
            label=args.label,
            tags=tags,
            tuya=learned.code,
            brand=args.brand,
            device_type=args.device_type,
            emitter=emitter.name,
        )
        store.save()
        print_sample_summary(sample)
    if args.test or confirm("Replay the last sample?", default=False):
        mqtt_client.send_tuya_code(emitter, learned.code)
        print("Code sent.")


def cmd_capture(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    store = RemoteStore(args.data)
    session = load_session(args.session)
    emitter = resolve_emitter(config, session.get("emitter"))
    mqtt_client = MqttIrClient(config.mqtt)
    remote = require_str(session, "remote")
    brand = session.get("brand")
    device_type = session.get("device_type") or "custom"
    defaults = session.get("defaults") or {}
    commands = session.get("commands") or []
    if not commands:
        raise ConfigError(f"Session has no commands: {args.session}")
    print(f"Session: {remote} | emitter: {emitter.name} | commands: {len(commands)}")
    for index, command_obj in enumerate(commands, start=1):
        if isinstance(command_obj, str):
            name = command_obj
            label = command_obj
            command_tags = {}
            samples = args.samples or 1
        else:
            name = require_str(command_obj, "name")
            label = command_obj.get("label") or name
            command_tags = command_obj.get("tags") or {}
            samples = args.samples or int(command_obj.get("samples", session.get("samples", 1)))
        tags = {**defaults, **command_tags}
        print(f"\nCommand {index}/{len(commands)}: {name}")
        print(f"Tags: {tags}")
        for sample_index in range(samples):
            print(f"Sample {sample_index + 1}/{samples}")
            if sample_index == 0:
                press_enter("Press ENTER to start, then press the remote button for each sample")
            else:
                print("Press the button on the remote...")
            learned = mqtt_client.learn_once(emitter, timeout=args.timeout)
            sample = save_learned_sample(
                store,
                remote=remote,
                command=name,
                label=label,
                tags=tags,
                tuya=learned.code,
                brand=brand,
                device_type=device_type,
                emitter=emitter.name,
            )
            store.save()
            print_sample_summary(sample)
        if not args.no_test and confirm("Testare reinvio dell'ultimo sample?", default=False):
            mqtt_client.send_tuya_code(emitter, learned.code)
            print("Code sent.")


def cmd_wizard(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    store = RemoteStore(args.data)
    emitter = resolve_emitter(config, None)
    mqtt_client = MqttIrClient(config.mqtt)
    remote = text("Remote name", default="my_ac")
    brand = text("Brand", default="")
    device_type = select("Device type", ["climate", "tv", "fan", "audio", "custom"], default="custom")
    default_tags = key_value_tags(text("Tags default key=value,key=value", default=""))
    print("\nEnter commands one at a time. Leave the name empty to finish.")
    while True:
        command = text("Command name", default="")
        if not command:
            break
        label = text("Etichetta", default=command)
        tags = {**default_tags, **key_value_tags(text("Command tags key=value,key=value", default=""))}
        samples = int(text("Number of samples", default="1") or "1")
        for sample_index in range(samples):
            print(f"\n{remote}/{command} sample {sample_index + 1}/{samples}")
            if sample_index == 0:
                press_enter("Press ENTER to start, then press the remote button for each sample")
            else:
                print("Press the button on the remote...")
            learned = mqtt_client.learn_once(emitter, timeout=args.timeout)
            sample = save_learned_sample(
                store,
                remote=remote,
                command=command,
                label=label,
                tags=tags,
                tuya=learned.code,
                brand=brand,
                device_type=device_type,
                emitter=emitter.name,
            )
            store.save()
            print_sample_summary(sample)
        if confirm("Testare reinvio dell'ultimo sample?", default=False):
            mqtt_client.send_tuya_code(emitter, learned.code)
            print("Code sent.")
        if not confirm("Add another command?", default=True):
            break
    print(f"\nDatabase saved to {store.path}")


def cmd_send(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    emitter = resolve_emitter(config, args.emitter)
    store = RemoteStore(args.data)
    sample = store.get_sample(args.remote, args.command, args.sample)
    code = sample.get("tuya")
    if not code:
        raise StorageError(f"Sample '{args.remote}/{args.command}' has no Tuya code")
    MqttIrClient(config.mqtt).send_tuya_code(emitter, code)
    print(f"Sent {args.remote}/{args.command} via {emitter.name}")


def cmd_delete(args: argparse.Namespace) -> None:
    store = RemoteStore(args.data)

    remote = args.remote or select("Pick a remote", store.list_remotes())
    command = args.command or select("Pick a command", store.list_commands(remote))

    command_obj = store.get_command(remote, command)
    samples = command_obj.get("samples") or []

    if args.sample is not None:
        # eliminazione singolo sample passato via --sample
        sample_index = args.sample
    elif len(samples) > 1:
        # selezione interattiva: mostra i sample con data e frame hex
        choices = [
            f"[{i}] {s.get('captured_at', '?')}  {' | '.join(f['hex_msb'] for f in s.get('analysis', {}).get('frames', []))}"
            for i, s in enumerate(samples)
        ]
        choices.append("Delete the whole command")
        chosen = select("What to delete?", choices)
        if chosen == "Delete the whole command":
            sample_index = None
        else:
            sample_index = int(chosen.split("]")[0].lstrip("["))
    else:
        sample_index = None  # un solo sample: elimina il comando intero

    if sample_index is None:
        if not confirm(f"Delete the whole command '{remote}/{command}' ({len(samples)} samples)?", default=False):
            print("Aborted.")
            return
        store.delete_command(remote, command)
        store.save()
        print(f"Command '{remote}/{command}' deleted.")
    else:
        s = samples[sample_index]
        frames_str = " | ".join(f['hex_msb'] for f in s.get('analysis', {}).get('frames', []))
        if not confirm(f"Delete sample [{sample_index}] ({s.get('captured_at', '?')}  {frames_str})?", default=False):
            print("Aborted.")
            return
        store.delete_sample(remote, command, sample_index)
        store.save()
        print(f"Sample [{sample_index}] of '{remote}/{command}' deleted.")


def cmd_generate(args: argparse.Namespace) -> None:
    try:
        if args.protocol == "electra":
            power_on = args.power != "off"
            raw = electra_generator.generate_raw(args.mode, args.temp, fan=args.fan, power=power_on, swing_v=args.swing)
            tuya = electra_generator.generate_tuya(args.mode, args.temp, fan=args.fan, power=power_on, swing_v=args.swing)
        else:
            raw = midea_generator.generate_raw(args.mode, args.temp)
            tuya = midea_generator.generate_tuya(args.mode, args.temp)
    except ValueError as exc:
        raise IrLabError(str(exc)) from exc

    if args.format in ("tuya", "both"):
        print(f"Tuya: {tuya}")
    if args.format in ("raw", "both"):
        print(f"Raw:  {raw_to_text(raw)}")

    if args.send:
        config = load_config(args.config)
        emitter = resolve_emitter(config, args.emitter)
        MqttIrClient(config.mqtt).send_tuya_code(emitter, tuya)
        print(f"Sent {args.mode} {args.temp}C ({args.protocol}) via {emitter.name}")


def cmd_list(args: argparse.Namespace) -> None:
    store = RemoteStore(args.data)
    rows = store.command_rows(args.remote)
    if not rows:
        print("No commands stored.")
        return
    for row in rows:
        tags = ",".join(f"{k}={v}" for k, v in row["tags"].items())
        print(
            f"{row['remote']}/{row['command']} | samples={row['samples']} | "
            f"label={row['label']} | tags={tags}"
        )


def cmd_analyze(args: argparse.Namespace) -> None:
    store = RemoteStore(args.data)
    if args.command:
        sample = store.get_sample(args.remote, args.command, args.sample)
        analysis = ensure_analysis(sample)
        if args.json:
            print(json.dumps(analysis, ensure_ascii=False, indent=2))
        else:
            print(f"{args.remote}/{args.command}")
            print(format_analysis(analysis))
        return
    for command in store.list_commands(args.remote):
        sample = store.get_sample(args.remote, command, args.sample)
        print(f"\n{args.remote}/{command}")
        print(format_analysis(ensure_analysis(sample)))


def cmd_compare(args: argparse.Namespace) -> None:
    store = RemoteStore(args.data)
    rows = []
    for command in args.commands:
        sample = store.get_sample(args.remote, command, args.sample)
        frames = ensure_analysis(sample).get("frames", [])
        row = [command]
        for frame in frames:
            tail = f"+{frame.get('tail_bits')}" if frame.get("tail_bits") else ""
            row.append(f"{frame.get('hex_msb', '')}{tail}")
        rows.append(row)
    max_frames = max((len(row) - 1 for row in rows), default=0)
    headers = ["command"] + [f"frame_{index}" for index in range(1, max_frames + 1)]
    widths = [len(header) for header in headers]
    for row in rows:
        while len(row) < len(headers):
            row.append("")
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    print(" | ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("-+-".join("-" * width for width in widths))
    for row in rows:
        print(" | ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def load_session(path: str | Path) -> dict[str, Any]:
    session_path = Path(path)
    if not session_path.exists():
        raise ConfigError(f"Session not found: {session_path}")
    with session_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Invalid session file: {session_path}")
    return data


def require_str(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    if value is None or str(value).strip() == "":
        raise ConfigError(f"Missing required field: {key}")
    return str(value)


def save_learned_sample(
    store: RemoteStore,
    *,
    remote: str,
    command: str,
    label: str | None,
    tags: dict[str, Any],
    tuya: str,
    brand: str | None,
    device_type: str | None,
    emitter: str,
) -> dict[str, Any]:
    raw: list[int] | None = None
    analysis: dict[str, Any] | None = None
    decode_error: str | None = None
    try:
        raw = decode_tuya_ir(tuya)
        analysis = analyze_raw(raw)
    except CodecError as exc:
        decode_error = str(exc)
    return store.add_sample(
        remote,
        command,
        label=label,
        tags=tags,
        tuya=tuya,
        raw=raw,
        analysis=analysis,
        decode_error=decode_error,
        brand=brand,
        device_type=device_type,
        emitter=emitter,
    )


def ensure_analysis(sample: dict[str, Any]) -> dict[str, Any]:
    analysis = sample.get("analysis") or {}
    if analysis:
        return analysis
    raw = sample.get("raw") or []
    if not raw and sample.get("tuya"):
        raw = decode_tuya_ir(sample["tuya"])
    if not raw:
        raise StorageError("Sample has no analysable raw timings")
    return analyze_raw(raw)


def print_sample_summary(sample: dict[str, Any]) -> None:
    print("Captured Tuya code:")
    print(sample.get("tuya", ""))
    if sample.get("decode_error"):
        print(f"Decode error: {sample['decode_error']}")
        return
    raw = sample.get("raw") or []
    print(f"Raw timings: {len(raw)} durations")
    print(format_analysis(sample.get("analysis") or {}))
