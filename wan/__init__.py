# Copyright 2024-2025 The Alibaba Wan Team Authors. All rights reserved.
from importlib import import_module

from . import configs, distributed, modules


__all__ = (
    "WanI2V",
    "WanS2V",
    "WanT2V",
    "WanTI2V",
    "WanAnimate",
)

_LAZY_EXPORTS = {
    "WanI2V": (".image2video", "WanI2V"),
    "WanS2V": (".speech2video", "WanS2V"),
    "WanT2V": (".text2video", "WanT2V"),
    "WanTI2V": (".textimage2video", "WanTI2V"),
    "WanAnimate": (".animate", "WanAnimate"),
}


def __getattr__(name):
    """Lazily import model entry points on first attribute access.

    In particular, importing :mod:`wan` must not pull in the optional S2V
    audio stack.  Caching the resolved class in the module globals preserves
    normal module attribute semantics and makes repeated access inexpensive.
    """

    try:
        module_name, attribute_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc

    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value


def __dir__():
    """Expose eagerly available names together with lazy model exports."""

    return sorted(set(globals()) | set(__all__))
