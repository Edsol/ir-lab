from __future__ import annotations

from typing import Any, Iterable

try:
    from InquirerPy import inquirer
except ImportError:  # pragma: no cover
    inquirer = None  # type: ignore[assignment]


def text(message: str, *, default: str = "") -> str:
    if inquirer:
        return str(inquirer.text(message=message, default=default).execute()).strip()
    value = input(f"{message} [{default}]: ").strip()
    return value or default


def confirm(message: str, *, default: bool = False) -> bool:
    if inquirer:
        return bool(inquirer.confirm(message=message, default=default).execute())
    suffix = "Y/n" if default else "y/N"
    value = input(f"{message} [{suffix}]: ").strip().lower()
    if not value:
        return default
    return value in {"y", "yes", "s", "si", "sì"}


def select(message: str, choices: Iterable[str], *, default: str | None = None) -> str:
    choices_list = list(choices)
    if not choices_list:
        raise ValueError("select() called with no choices")
    if inquirer:
        return str(inquirer.select(message=message, choices=choices_list, default=default).execute())
    print(message)
    for index, choice in enumerate(choices_list, start=1):
        marker = "*" if choice == default else " "
        print(f"  {index}) {choice} {marker}")
    raw = input("Choice number: ").strip()
    if not raw and default:
        return default
    return choices_list[int(raw) - 1]


def press_enter(message: str = "Press ENTER to continue") -> None:
    input(f"{message}...")


def key_value_tags(raw: str) -> dict[str, Any]:
    tags: dict[str, Any] = {}
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            tags[item] = True
            continue
        key, value = item.split("=", 1)
        tags[key.strip()] = coerce_value(value.strip())
    return tags


def coerce_value(value: str) -> Any:
    lowered = value.lower()
    if lowered in {"true", "yes", "on", "sì", "si"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value
