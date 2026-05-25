from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from typing import Any

from .config import EmitterSettings, MqttSettings
from .errors import MqttError

# Model ID noti per blaster IR Tuya/Zigbee2MQTT.
# Aggiungi qui altri model_id se usi hardware diverso.
_IR_BLASTER_MODEL_IDS = {
    "TS1201",   # Tuya iH-F8260 e compatibili
    "TS1001",
    "UFO-R11",
}


def discover_ir_blasters(settings: MqttSettings, *, timeout: int = 5) -> list[EmitterSettings]:
    """Scopre i blaster IR disponibili ascoltando zigbee2mqtt/bridge/devices.

    Si connette al broker, attende il messaggio di inventory di Zigbee2MQTT
    e filtra i device il cui model_id è nella lista _IR_BLASTER_MODEL_IDS
    oppure il cui type è 'EndDevice' e il definition contiene 'ir' nel nome.

    Restituisce una lista di EmitterSettings costruita dai friendly_name Z2M,
    compatibile con il resto del progetto.
    """
    if mqtt is None:
        raise MqttError("Dipendenza mancante: installa paho-mqtt")

    event = threading.Event()
    found: list[EmitterSettings] = []

    def on_message(client, userdata, message):  # noqa: ANN001
        del client, userdata
        if not message.topic.endswith("/bridge/devices"):
            return
        try:
            devices = json.loads(message.payload.decode("utf-8"))
        except Exception:
            return
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            if not _is_ir_blaster(dev):
                continue
            fn = dev.get("friendly_name") or dev.get("ieee_address", "unknown")
            base = f"zigbee2mqtt/{fn}"
            found.append(EmitterSettings(
                name=fn,
                friendly_name=fn,
                topic_state=base,
                topic_set=f"{base}/set",
            ))
        event.set()

    def on_connect(client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
        del userdata, flags, reason_code, properties
        client.subscribe("zigbee2mqtt/bridge/devices")

    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{settings.client_id}-discovery",
        )
    else:  # pragma: no cover
        client = mqtt.Client(client_id=f"{settings.client_id}-discovery")

    if settings.username:
        client.username_pw_set(settings.username, settings.password)

    client.on_message = on_message
    client.on_connect = on_connect

    try:
        client.connect(settings.host, settings.port, settings.keepalive)
    except Exception as exc:  # noqa: BLE001
        raise MqttError(f"Connessione MQTT fallita durante discovery: {exc}") from exc

    client.loop_start()
    try:
        event.wait(timeout=timeout)
    finally:
        client.loop_stop()
        try:
            client.disconnect()
        except Exception:
            pass

    return found


def _is_ir_blaster(dev: dict[str, Any]) -> bool:
    model_id = str(dev.get("model_id") or "")
    if model_id in _IR_BLASTER_MODEL_IDS:
        return True
    definition = dev.get("definition") or {}
    if isinstance(definition, dict):
        model = str(definition.get("model") or "")
        description = str(definition.get("description") or "").lower()
        if model in _IR_BLASTER_MODEL_IDS:
            return True
        if "ir" in description and dev.get("type") == "EndDevice":
            return True
    return False

try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
    mqtt = None  # type: ignore[assignment]


@dataclass
class LearnedCode:
    code: str
    payload: dict[str, Any]
    topic: str


class MqttIrClient:
    def __init__(self, settings: MqttSettings):
        if mqtt is None:
            raise MqttError("Dipendenza mancante: installa paho-mqtt")
        self.settings = settings
        self.client = self._new_client()

    def _new_client(self):
        if hasattr(mqtt, "CallbackAPIVersion"):
            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=self.settings.client_id,
            )
        else:  # pragma: no cover
            client = mqtt.Client(client_id=self.settings.client_id)
        if self.settings.username:
            client.username_pw_set(self.settings.username, self.settings.password)
        return client

    def connect(self) -> None:
        try:
            self.client.connect(self.settings.host, self.settings.port, self.settings.keepalive)
        except Exception as exc:  # noqa: BLE001
            raise MqttError(f"Connessione MQTT fallita: {exc}") from exc

    def disconnect(self) -> None:
        try:
            self.client.disconnect()
        except Exception:
            pass

    def publish_json(self, topic: str, payload: dict[str, Any], *, retain: bool = False) -> None:
        data = json.dumps(payload, separators=(",", ":"))
        result = self.client.publish(topic, data, qos=0, retain=retain)
        result.wait_for_publish(timeout=5)
        if result.rc != 0:
            raise MqttError(f"Publish MQTT fallita su {topic}: rc={result.rc}")

    def send_tuya_code(self, emitter: EmitterSettings, code: str) -> None:
        connected = threading.Event()
        published = threading.Event()

        def on_connect(client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
            del userdata, flags, properties
            if reason_code == 0:
                connected.set()

        def on_publish(client, userdata, mid, *args):  # noqa: ANN001
            del client, userdata, mid, args
            published.set()

        self.client.on_connect = on_connect
        self.client.on_publish = on_publish
        self.client.loop_start()
        try:
            self.connect()
            if not connected.wait(timeout=10):
                raise MqttError("Timeout connessione MQTT")
            self.publish_json(emitter.topic_set, {"ir_code_to_send": code})
            published.wait(timeout=5)
        finally:
            self.client.loop_stop()
            self.disconnect()

    def learn_once(self, emitter: EmitterSettings, *, timeout: int = 45) -> LearnedCode:
        event = threading.Event()
        learned: list[LearnedCode] = []

        def on_message(client, userdata, message):  # noqa: ANN001
            del client, userdata
            try:
                payload = json.loads(message.payload.decode("utf-8"))
            except Exception:
                return
            code = payload.get("learned_ir_code")
            if isinstance(code, str) and code.strip():
                learned.append(LearnedCode(code=code.strip(), payload=payload, topic=message.topic))
                event.set()

        def on_connect(client, userdata, flags, reason_code, properties=None):  # noqa: ANN001
            del userdata, flags, reason_code, properties
            client.subscribe(emitter.topic_state)

        self.client.on_message = on_message
        self.client.on_connect = on_connect
        self.connect()
        self.client.loop_start()
        try:
            self.publish_json(emitter.topic_set, {"learn_ir_code": True})
            print(f"In ascolto su {emitter.topic_state} (timeout {timeout}s)...")
            if not event.wait(timeout=timeout):
                raise MqttError(
                    f"Timeout: nessun learned_ir_code ricevuto da {emitter.topic_state} "
                    f"entro {timeout}s. Verifica che il blaster sia raggiungibile e "
                    f"supporti learn_ir_code."
                )
            return learned[-1]
        finally:
            self.client.loop_stop()
            self.disconnect()
