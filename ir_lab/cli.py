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
from . import midea_generator


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nOperazione annullata.", file=sys.stderr)
        raise SystemExit(130) from None
    except IrLabError as exc:
        print(f"Errore: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ir-lab",
        description="Laboratorio locale per codici IR Tuya/Zigbee2MQTT via MQTT.",
    )
    parser.add_argument("--version", action="version", version=f"ir-lab {__version__}")
    sub = parser.add_subparsers(dest="command_name", required=True)

    p_init = sub.add_parser("init", help="Crea config.yaml e cartelle di lavoro")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_decode = sub.add_parser("decode", help="Converte codice Tuya in raw e analisi")
    p_decode.add_argument("--tuya", required=True)
    p_decode.add_argument("--json", action="store_true")
    p_decode.set_defaults(func=cmd_decode)

    p_encode = sub.add_parser("encode", help="Converte raw timings in codice Tuya")
    p_encode.add_argument("--raw", required=True)
    p_encode.set_defaults(func=cmd_encode)

    p_learn = sub.add_parser("learn", help="Acquisisce sample per un comando")
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

    p_capture = sub.add_parser("capture", help="Esegue una sessione sequenziale da YAML")
    add_common_args(p_capture)
    p_capture.add_argument("--session", required=True)
    p_capture.add_argument("--samples", type=int, default=None)
    p_capture.add_argument("--timeout", type=int, default=45)
    p_capture.add_argument("--no-test", action="store_true")
    p_capture.set_defaults(func=cmd_capture)

    p_wizard = sub.add_parser("wizard", help="Wizard interattivo stile Inquirer")
    add_common_args(p_wizard)
    p_wizard.add_argument("--timeout", type=int, default=45)
    p_wizard.set_defaults(func=cmd_wizard)

    p_send = sub.add_parser("send", help="Invia un comando salvato")
    add_common_args(p_send)
    p_send.add_argument("--remote", required=True)
    p_send.add_argument("--command", required=True)
    p_send.add_argument("--emitter", default=None)
    p_send.add_argument("--sample", default="active")
    p_send.set_defaults(func=cmd_send)

    p_list = sub.add_parser("list", help="Lista telecomandi e comandi salvati")
    p_list.add_argument("--data", default=str(DEFAULT_DATA_PATH))
    p_list.add_argument("--remote", default=None)
    p_list.set_defaults(func=cmd_list)

    p_analyze = sub.add_parser("analyze", help="Analizza codici salvati")
    p_analyze.add_argument("--data", default=str(DEFAULT_DATA_PATH))
    p_analyze.add_argument("--remote", required=True)
    p_analyze.add_argument("--command", default=None)
    p_analyze.add_argument("--sample", default="active")
    p_analyze.add_argument("--json", action="store_true")
    p_analyze.set_defaults(func=cmd_analyze)

    p_compare = sub.add_parser("compare", help="Confronta frame/hex tra comandi")
    p_compare.add_argument("--data", default=str(DEFAULT_DATA_PATH))
    p_compare.add_argument("--remote", required=True)
    p_compare.add_argument("--commands", nargs="+", required=True)
    p_compare.add_argument("--sample", default="active")
    p_compare.set_defaults(func=cmd_compare)

    p_delete = sub.add_parser("delete", help="Elimina un comando o un singolo sample")
    p_delete.add_argument("--data", default=str(DEFAULT_DATA_PATH))
    p_delete.add_argument("--remote", default=None)
    p_delete.add_argument("--command", default=None)
    p_delete.add_argument("--sample", default=None, type=int, help="Indice sample (0-based). Ometti per eliminare l'intero comando.")
    p_delete.set_defaults(func=cmd_delete)

    p_generate = sub.add_parser("generate", help="Genera codice IR Midea senza telecomando fisico")
    p_generate.add_argument("--mode", required=True, choices=["cool", "heat", "dry", "auto", "fan"],
                            help="Modalità: cool | heat | dry | auto | fan")
    p_generate.add_argument("--temp", type=int, default=22,
                            help="Temperatura in °C (16-30, ignorata per fan). Default: 22")
    p_generate.add_argument("--format", choices=["tuya", "raw", "both"], default="tuya",
                            help="Formato output: tuya (default) | raw | both")
    p_generate.add_argument("--send", action="store_true", help="Invia il codice generato via MQTT")
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
        raise ConfigError("config.yaml esiste gia'. Usa --force per sovrascrivere")
    if not source.exists():
        raise ConfigError("config.example.yaml non trovato")
    shutil.copyfile(source, target)
    Path("data").mkdir(exist_ok=True)
    Path("sessions").mkdir(exist_ok=True)
    print("Creato config.yaml. Modifica host MQTT e friendly name del blaster.")


def cmd_decode(args: argparse.Namespace) -> None:
    raw = decode_tuya_ir(args.tuya)
    analysis = analyze_raw(raw)
    if args.json:
        print(json.dumps({"raw": raw, "analysis": analysis}, ensure_ascii=False, indent=2))
        return
    print("Raw:")
    print(raw_to_text(raw))
    print("\nAnalisi:")
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
        chosen = select("Scegli emitter", list(config.emitters.keys()))
        return config.get_emitter(chosen)
    # Nessun emitter in config.yaml: discovery MQTT
    print("Nessun emitter in config.yaml — ricerca blaster IR su MQTT...")
    blasters = discover_ir_blasters(config.mqtt)
    if not blasters:
        raise ConfigError(
            "Nessun blaster IR trovato su zigbee2mqtt/bridge/devices. "
            "Verifica che Zigbee2MQTT sia attivo e il dispositivo sia accoppiato, "
            "oppure configura manualmente gli emitter in config.yaml."
        )
    if len(blasters) == 1:
        print(f"Blaster trovato: {blasters[0].friendly_name}")
        return blasters[0]
    chosen_name = select("Scegli blaster IR", [e.friendly_name for e in blasters])
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
            press_enter("Premi INVIO per iniziare, poi premi il tasto sul telecomando per ogni sample")
        else:
            print("Premi il tasto sul telecomando...")
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
    if args.test or confirm("Vuoi reinviare l'ultimo sample?", default=False):
        mqtt_client.send_tuya_code(emitter, learned.code)
        print("Codice inviato.")


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
        raise ConfigError(f"Sessione senza commands: {args.session}")
    print(f"Sessione: {remote} | emitter: {emitter.name} | comandi: {len(commands)}")
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
        print(f"\nComando {index}/{len(commands)}: {name}")
        print(f"Tags: {tags}")
        for sample_index in range(samples):
            print(f"Sample {sample_index + 1}/{samples}")
            if sample_index == 0:
                press_enter("Premi INVIO per iniziare, poi premi il tasto sul telecomando per ogni sample")
            else:
                print("Premi il tasto sul telecomando...")
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
            print("Codice inviato.")


def cmd_wizard(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    store = RemoteStore(args.data)
    emitter = resolve_emitter(config, None)
    mqtt_client = MqttIrClient(config.mqtt)
    remote = text("Nome telecomando", default="midea_camera")
    brand = text("Marca", default="")
    device_type = select("Tipo dispositivo", ["climate", "tv", "fan", "audio", "custom"], default="custom")
    default_tags = key_value_tags(text("Tags default key=value,key=value", default=""))
    print("\nInserisci i comandi uno alla volta. Lascia vuoto il nome per terminare.")
    while True:
        command = text("Nome comando", default="")
        if not command:
            break
        label = text("Etichetta", default=command)
        tags = {**default_tags, **key_value_tags(text("Tags comando key=value,key=value", default=""))}
        samples = int(text("Numero sample", default="1") or "1")
        for sample_index in range(samples):
            print(f"\n{remote}/{command} sample {sample_index + 1}/{samples}")
            if sample_index == 0:
                press_enter("Premi INVIO per iniziare, poi premi il tasto sul telecomando per ogni sample")
            else:
                print("Premi il tasto sul telecomando...")
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
            print("Codice inviato.")
        if not confirm("Aggiungere un altro comando?", default=True):
            break
    print(f"\nDatabase salvato in {store.path}")


def cmd_send(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    emitter = resolve_emitter(config, args.emitter)
    store = RemoteStore(args.data)
    sample = store.get_sample(args.remote, args.command, args.sample)
    code = sample.get("tuya")
    if not code:
        raise StorageError(f"Sample '{args.remote}/{args.command}' senza codice Tuya")
    MqttIrClient(config.mqtt).send_tuya_code(emitter, code)
    print(f"Inviato {args.remote}/{args.command} tramite {emitter.name}")


def cmd_delete(args: argparse.Namespace) -> None:
    store = RemoteStore(args.data)

    remote = args.remote or select("Scegli telecomando", store.list_remotes())
    command = args.command or select("Scegli comando", store.list_commands(remote))

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
        choices.append("Elimina tutto il comando")
        chosen = select("Cosa eliminare?", choices)
        if chosen == "Elimina tutto il comando":
            sample_index = None
        else:
            sample_index = int(chosen.split("]")[0].lstrip("["))
    else:
        sample_index = None  # un solo sample: elimina il comando intero

    if sample_index is None:
        if not confirm(f"Eliminare l'intero comando '{remote}/{command}' ({len(samples)} sample)?", default=False):
            print("Annullato.")
            return
        store.delete_command(remote, command)
        store.save()
        print(f"Comando '{remote}/{command}' eliminato.")
    else:
        s = samples[sample_index]
        frames_str = " | ".join(f['hex_msb'] for f in s.get('analysis', {}).get('frames', []))
        if not confirm(f"Eliminare sample [{sample_index}] ({s.get('captured_at', '?')}  {frames_str})?", default=False):
            print("Annullato.")
            return
        store.delete_sample(remote, command, sample_index)
        store.save()
        print(f"Sample [{sample_index}] di '{remote}/{command}' eliminato.")


def cmd_generate(args: argparse.Namespace) -> None:
    try:
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
        print(f"Inviato {args.mode} {args.temp}° tramite {emitter.name}")


def cmd_list(args: argparse.Namespace) -> None:
    store = RemoteStore(args.data)
    rows = store.command_rows(args.remote)
    if not rows:
        print("Nessun comando salvato.")
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
        raise ConfigError(f"Sessione non trovata: {session_path}")
    with session_path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Sessione non valida: {session_path}")
    return data


def require_str(obj: dict[str, Any], key: str) -> str:
    value = obj.get(key)
    if value is None or str(value).strip() == "":
        raise ConfigError(f"Campo obbligatorio mancante: {key}")
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
        raise StorageError("Sample senza raw analizzabile")
    return analyze_raw(raw)


def print_sample_summary(sample: dict[str, Any]) -> None:
    print("Codice Tuya acquisito:")
    print(sample.get("tuya", ""))
    if sample.get("decode_error"):
        print(f"Decode error: {sample['decode_error']}")
        return
    raw = sample.get("raw") or []
    print(f"Raw timings: {len(raw)} durate")
    print(format_analysis(sample.get("analysis") or {}))
