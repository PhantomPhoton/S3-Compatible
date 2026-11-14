"""Stub the Home Assistant modules the integration imports, so unit tests run without HA."""

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _module(name: str, **attrs) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module
    return module


try:
    import homeassistant  # noqa: F401
except ImportError:

    class BackupAgentError(Exception):
        pass

    class BackupNotFound(BackupAgentError):
        pass

    class BackupAgent:
        pass

    class AgentBackup:
        def __init__(self, backup_id: str, size: int) -> None:
            self.backup_id = backup_id
            self.size = size

        def as_dict(self) -> dict:
            return {"backup_id": self.backup_id, "size": self.size}

    class HassKey(str):
        def __class_getitem__(cls, _item):
            return cls

    _module("homeassistant")
    _module("homeassistant.components")
    _module(
        "homeassistant.components.backup",
        AgentBackup=AgentBackup,
        BackupAgent=BackupAgent,
        BackupAgentError=BackupAgentError,
        BackupNotFound=BackupNotFound,
        suggested_filename=lambda backup: f"{backup.backup_id}.tar",
    )
    _module("homeassistant.core", HomeAssistant=object, callback=lambda func: func)
    _module("homeassistant.config_entries", ConfigEntry=object)
    _module(
        "homeassistant.exceptions",
        ConfigEntryError=Exception,
        ConfigEntryNotReady=Exception,
    )
    _module("homeassistant.util")
    _module("homeassistant.util.hass_dict", HassKey=HassKey)
