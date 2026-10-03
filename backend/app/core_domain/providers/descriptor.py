from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class ProviderDescriptor:
    provider_type: str
    capability: str
    model: str
    base_url: str | None = None
    dimension: int | None = None
    options: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "options", _freeze(self.options))

    def options_dict(self) -> dict[str, object]:
        """A fresh mutable copy for vendor request payloads."""
        return _thaw(self.options)
