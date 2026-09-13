from .base import Reading, Recognizer, normalise_digits
from .cascade import CascadeRecognizer, CascadeStats

__all__ = [
    "Reading",
    "Recognizer",
    "normalise_digits",
    "CascadeRecognizer",
    "CascadeStats",
    "build",
    "build_cascade",
]


def build(name: str, **kwargs) -> Recognizer:
    """Instantiate a recognizer by name, importing its backend lazily."""
    from .engines import REGISTRY

    if name not in REGISTRY:
        raise KeyError(f"unknown recognizer {name!r}; have {sorted(REGISTRY)}")
    return REGISTRY[name](**kwargs)


def build_cascade(
    primary: str = "easyocr",
    fallback: str | None = "vlm",
    threshold: float = 0.4,
    primary_kwargs: dict | None = None,
    fallback_kwargs: dict | None = None,
) -> CascadeRecognizer:
    """The production configuration: a fast local primary, escalating only the
    crops it is unsure about. See ``scripts/calibrate.py`` for choosing
    ``threshold`` against your own pipeline."""
    return CascadeRecognizer(
        primary=build(primary, **(primary_kwargs or {})),
        fallback=build(fallback, **(fallback_kwargs or {})) if fallback else None,
        threshold=threshold,
    )
