class IrLabError(Exception):
    """Base exception for IR Lab."""


class ConfigError(IrLabError):
    """Raised when configuration is missing or invalid."""


class StorageError(IrLabError):
    """Raised when the local JSON database cannot be read or written."""


class CodecError(IrLabError):
    """Raised when an IR code cannot be decoded or encoded."""


class MqttError(IrLabError):
    """Raised when MQTT operations fail."""
