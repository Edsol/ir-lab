from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigError


@dataclass(frozen=True)
class MqttSettings:
    host: str
    port: int = 1883
    username: str | None = None
    password: str | None = None
    client_id: str = "ir-lab"
    keepalive: int = 60


@dataclass(frozen=True)
class EmitterSettings:
    name: str
    friendly_name: str
    topic_state: str
    topic_set: str


@dataclass(frozen=True)
class AppConfig:
    path: Path
    mqtt: MqttSettings
    emitters: dict[str, EmitterSettings]

    def get_emitter(self, name: str | None = None) -> EmitterSettings | None:
        """Restituisce un emitter dalla configurazione statica (config.yaml).

        Se gli emitter non sono configurati e name è None, restituisce None —
        resolve_emitter() in cli.py farà la discovery MQTT automaticamente.
        Se name è specificato ma non c'è in config, lo costruisce al volo
        usando la convenzione topic Zigbee2MQTT standard.
        """
        if name is not None:
            if name in self.emitters:
                return self.emitters[name]
            # name non in config: costruisci EmitterSettings con topic standard
            friendly = name
            return EmitterSettings(
                name=name,
                friendly_name=friendly,
                topic_state=f"zigbee2mqtt/{friendly}",
                topic_set=f"zigbee2mqtt/{friendly}/set",
            )
        if not self.emitters:
            return None
        if len(self.emitters) == 1:
            return next(iter(self.emitters.values()))
        choices = ", ".join(sorted(self.emitters))
        raise ConfigError(f"Specifica un emitter. Disponibili: {choices}")


def _none_if_empty(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def load_config(path: str | Path = "config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(
            f"Config non trovata: {config_path}. Copia config.example.yaml in config.yaml e modificalo."
        )
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    mqtt_raw = raw.get("mqtt") or {}
    host = mqtt_raw.get("host")
    if not host:
        raise ConfigError("config.yaml: mqtt.host e' obbligatorio")
    mqtt = MqttSettings(
        host=str(host),
        port=int(mqtt_raw.get("port", 1883)),
        username=_none_if_empty(mqtt_raw.get("username")),
        password=_none_if_empty(mqtt_raw.get("password")),
        client_id=str(mqtt_raw.get("client_id", "ir-lab")),
        keepalive=int(mqtt_raw.get("keepalive", 60)),
    )
    emitters_raw = raw.get("emitters") or {}
    if not isinstance(emitters_raw, dict):
        raise ConfigError("config.yaml: emitters deve essere un dizionario")
    emitters: dict[str, EmitterSettings] = {}
    for name, emitter_raw in emitters_raw.items():
        emitter_raw = emitter_raw or {}
        friendly_name = str(emitter_raw.get("friendly_name") or name)
        topic_state = emitter_raw.get("topic_state") or f"zigbee2mqtt/{friendly_name}"
        topic_set = emitter_raw.get("topic_set") or f"zigbee2mqtt/{friendly_name}/set"
        emitters[str(name)] = EmitterSettings(
            name=str(name),
            friendly_name=friendly_name,
            topic_state=str(topic_state),
            topic_set=str(topic_set),
        )
    return AppConfig(path=config_path, mqtt=mqtt, emitters=emitters)
