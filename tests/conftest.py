import os
import sys
import types
from dataclasses import dataclass, field


ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


# Create package hierarchy for custom_components stubs
custom_components = types.ModuleType("custom_components")
aurora_pkg = types.ModuleType("custom_components.aurora_llm_assistant")
tools_pkg = types.ModuleType("custom_components.aurora_llm_assistant.tools")
core_pkg = types.ModuleType("custom_components.aurora_llm_assistant.tools.core")

sys.modules.setdefault("custom_components", custom_components)
setattr(custom_components, "aurora_llm_assistant", aurora_pkg)
sys.modules.setdefault("custom_components.aurora_llm_assistant", aurora_pkg)
setattr(aurora_pkg, "tools", tools_pkg)
sys.modules.setdefault("custom_components.aurora_llm_assistant.tools", tools_pkg)
setattr(tools_pkg, "core", core_pkg)
sys.modules.setdefault("custom_components.aurora_llm_assistant.tools.core", core_pkg)


# Stub for base_tool
base_tool_module = types.ModuleType(
    "custom_components.aurora_llm_assistant.tools.core.base_tool"
)


class SimpleBaseTool:
    """Minimal stand-in for the Aurora SimpleBaseTool."""

    def __init__(self, hass, config=None):
        self.hass = hass
        if config is None:
            config = {}
        elif not isinstance(config, dict):
            config = dict(config)
        self.config = config
        self.database_manager = getattr(hass, "database_manager")
        self.event_manager = getattr(hass, "event_manager")
        self._logger = getattr(hass, "logger")

    def get_localized_text(self, _key: str, fallback: str, **kwargs):
        try:
            return fallback.format(**kwargs)
        except Exception:  # pragma: no cover - formatting failure should not break tests
            return fallback


setattr(base_tool_module, "SimpleBaseTool", SimpleBaseTool)
sys.modules[
    "custom_components.aurora_llm_assistant.tools.core.base_tool"
] = base_tool_module


# Stub for database_manager
class DatabaseError(Exception):
    """Placeholder database error used by the plugin under test."""


database_manager_module = types.ModuleType(
    "custom_components.aurora_llm_assistant.tools.core.database_manager"
)
setattr(database_manager_module, "DatabaseError", DatabaseError)
sys.modules[
    "custom_components.aurora_llm_assistant.tools.core.database_manager"
] = database_manager_module


# Stub for schema_manager
@dataclass
class FieldSpec:
    type: type = str
    description: str = ""
    widget: str = "text"
    validation: object = None
    widget_options: dict = field(default_factory=dict)


@dataclass
class ActionSpec:
    required: list
    optional: list
    hidden: list
    description: str


class CommonFieldSpecs:
    ACTION = FieldSpec(widget_options={"options": []})
    NAME = FieldSpec()
    AGE = FieldSpec()


class BaseSchema:
    def __init__(self):
        self.fields = {}
        self.actions = {}

    def register_field(self, name, spec):
        self.fields[name] = spec

    def register_action(self, name, spec):
        self.actions[name] = spec

    def set_friendly_name(self, _name: str) -> None:  # pragma: no cover - no behaviour needed
        return None


schema_manager_module = types.ModuleType(
    "custom_components.aurora_llm_assistant.tools.core.schema_manager"
)
schema_manager_module.BaseSchema = BaseSchema
schema_manager_module.FieldSpec = FieldSpec
schema_manager_module.ActionSpec = ActionSpec
schema_manager_module.CommonFieldSpecs = CommonFieldSpecs


def register_schema(_name: str):
    def decorator(cls):
        return cls

    return decorator


def register_tool(_name: str):  # pragma: no cover - compatibility hook if needed
    def decorator(cls):
        return cls

    return decorator


schema_manager_module.register_schema = register_schema
schema_manager_module.register_tool = register_tool
sys.modules[
    "custom_components.aurora_llm_assistant.tools.core.schema_manager"
] = schema_manager_module


# Stub out voluptuous dependency used for validation definitions.
voluptuous_module = types.ModuleType("voluptuous")


class _Length:
    def __init__(self, *args, **kwargs):  # noqa: D401 - simple stub
        self.args = args
        self.kwargs = kwargs


def _all(*_validators, **_kwargs):  # pragma: no cover - no runtime behaviour required
    return None


voluptuous_module.All = _all
voluptuous_module.Length = _Length
sys.modules["voluptuous"] = voluptuous_module
