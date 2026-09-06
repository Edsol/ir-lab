from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import StorageError

DEFAULT_DATA_PATH = Path("data/remotes.json")
SCHEMA_VERSION = 1


def utc_now_iso() -> str:
    return datetime.now(tz=UTC).replace(microsecond=0).isoformat()


class RemoteStore:
    def __init__(self, path: str | Path = DEFAULT_DATA_PATH):
        self.path = Path(path)
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": SCHEMA_VERSION, "remotes": {}}
        try:
            with self.path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Cannot read {self.path}: {exc}") from exc
        if not isinstance(data, dict):
            raise StorageError(f"{self.path} does not contain a JSON object")
        data.setdefault("schema_version", SCHEMA_VERSION)
        data.setdefault("remotes", {})
        return data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as handle:
                json.dump(self.data, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
            tmp.replace(self.path)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Cannot write {self.path}: {exc}") from exc

    def ensure_remote(
        self,
        remote: str,
        *,
        brand: str | None = None,
        device_type: str | None = None,
        emitter: str | None = None,
        notes: str | None = None,
    ) -> dict[str, Any]:
        remotes = self.data.setdefault("remotes", {})
        remote_obj = remotes.setdefault(
            remote,
            {
                "meta": {
                    "created_at": utc_now_iso(),
                    "brand": brand or "",
                    "device_type": device_type or "custom",
                    "emitter": emitter or "",
                    "notes": notes or "",
                },
                "commands": {},
            },
        )
        meta = remote_obj.setdefault("meta", {})
        if brand is not None:
            meta["brand"] = brand
        if device_type is not None:
            meta["device_type"] = device_type
        if emitter is not None:
            meta["emitter"] = emitter
        if notes is not None:
            meta["notes"] = notes
        meta["updated_at"] = utc_now_iso()
        remote_obj.setdefault("commands", {})
        return remote_obj

    def add_sample(
        self,
        remote: str,
        command: str,
        *,
        label: str | None = None,
        tags: dict[str, Any] | None = None,
        tuya: str,
        raw: list[int] | None = None,
        analysis: dict[str, Any] | None = None,
        decode_error: str | None = None,
        brand: str | None = None,
        device_type: str | None = None,
        emitter: str | None = None,
    ) -> dict[str, Any]:
        remote_obj = self.ensure_remote(remote, brand=brand, device_type=device_type, emitter=emitter)
        commands = remote_obj.setdefault("commands", {})
        command_obj = commands.setdefault(
            command,
            {"label": label or command, "tags": tags or {}, "samples": []},
        )
        if label is not None:
            command_obj["label"] = label
        if tags:
            command_obj.setdefault("tags", {}).update(tags)
        sample = {
            "captured_at": utc_now_iso(),
            "tuya": tuya,
            "raw": raw or [],
            "analysis": analysis or {},
        }
        if decode_error:
            sample["decode_error"] = decode_error
        command_obj.setdefault("samples", []).append(sample)
        command_obj["active_sample_index"] = len(command_obj["samples"]) - 1
        remote_obj.setdefault("meta", {})["updated_at"] = utc_now_iso()
        return sample

    def list_remotes(self) -> list[str]:
        return sorted(self.data.get("remotes", {}))

    def get_remote(self, remote: str) -> dict[str, Any]:
        try:
            return self.data["remotes"][remote]
        except KeyError as exc:
            raise StorageError(f"Remote '{remote}' not found") from exc

    def list_commands(self, remote: str) -> list[str]:
        return sorted(self.get_remote(remote).get("commands", {}))

    def get_command(self, remote: str, command: str) -> dict[str, Any]:
        remote_obj = self.get_remote(remote)
        try:
            return remote_obj["commands"][command]
        except KeyError as exc:
            raise StorageError(f"Command '{remote}/{command}' not found") from exc

    def get_sample(self, remote: str, command: str, sample: str | int = "active") -> dict[str, Any]:
        command_obj = self.get_command(remote, command)
        samples = command_obj.get("samples") or []
        if not samples:
            raise StorageError(f"Command '{remote}/{command}' has no samples")
        if sample == "active":
            index = int(command_obj.get("active_sample_index", len(samples) - 1))
        elif sample == "latest":
            index = len(samples) - 1
        else:
            index = int(sample)
        try:
            return samples[index]
        except IndexError as exc:
            raise StorageError(f"Invalid sample index {index} for '{remote}/{command}'") from exc

    def delete_command(self, remote: str, command: str) -> None:
        remote_obj = self.get_remote(remote)
        if command not in remote_obj.get("commands", {}):
            raise StorageError(f"Command '{remote}/{command}' not found")
        del remote_obj["commands"][command]
        remote_obj.setdefault("meta", {})["updated_at"] = utc_now_iso()

    def delete_sample(self, remote: str, command: str, index: int) -> None:
        command_obj = self.get_command(remote, command)
        samples = command_obj.get("samples") or []
        if index < 0 or index >= len(samples):
            raise StorageError(f"Invalid sample index {index} for '{remote}/{command}' ({len(samples)} samples)")
        samples.pop(index)
        if not samples:
            self.delete_command(remote, command)
            return
        active = int(command_obj.get("active_sample_index", len(samples)))
        if active >= len(samples):
            command_obj["active_sample_index"] = len(samples) - 1
        elif active > index:
            command_obj["active_sample_index"] = active - 1
        self.get_remote(remote).setdefault("meta", {})["updated_at"] = utc_now_iso()

    def command_rows(self, remote: str | None = None) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        remotes = self.data.get("remotes", {})
        selected = {remote: remotes[remote]} if remote else remotes
        for remote_name, remote_obj in selected.items():
            for command_name, command_obj in remote_obj.get("commands", {}).items():
                rows.append(
                    {
                        "remote": remote_name,
                        "command": command_name,
                        "label": command_obj.get("label", command_name),
                        "samples": len(command_obj.get("samples") or []),
                        "tags": command_obj.get("tags", {}),
                    }
                )
        return rows
