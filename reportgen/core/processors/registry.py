"""Registry for DOCX post-render processors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from reportgen.core.processors.base import RenderProcessor
from reportgen.core.processors.docx import build_default_docx_processors


@dataclass(frozen=True)
class ProcessorRegistryEntry:
    name: str
    processor: RenderProcessor
    order: int
    depends_on: tuple[str, ...] = ()


PROCESSOR_DEPENDENCIES: Mapping[str, tuple[str, ...]] = {
    "signature_layout": ("signature_placeholder",),
    "toc_refresh": ("blank_page_cleanup",),
    "final_refresh_cleanup": ("toc_refresh",),
    "underlines_and_styles": ("final_refresh_cleanup",),
}

# A report must not be returned as successfully rendered when patient-specific
# Part 3 content, its citations, or the final-table-driven drug-brand note fails
# to materialize.
CRITICAL_DOCX_PROCESSOR_NAMES = frozenset(
    {
        "part3_formatted_sections",
        "rebuild_references",
        "targeted_drug_brand_summary",
    }
)


class ProcessorRegistry:
    """Ordered lookup for stateless DOCX processors."""

    def __init__(self, entries: Sequence[ProcessorRegistryEntry]):
        self._entries = {entry.name: entry for entry in entries}
        self._default_names = tuple(
            entry.name for entry in sorted(entries, key=lambda item: item.order)
        )

    @property
    def default_names(self) -> tuple[str, ...]:
        return self._default_names

    @property
    def known_names(self) -> set[str]:
        return set(self._entries)

    def build(
        self,
        names: Sequence[str] | None = None,
    ) -> list[RenderProcessor]:
        selected = self.default_names if names is None else tuple(names)
        processors: list[RenderProcessor] = []
        for name in selected:
            entry = self._entries.get(str(name))
            if entry is None:
                raise KeyError(f"Unknown DOCX processor: {name!r}")
            processors.append(entry.processor)
        return processors

    def validate_sequence(self, names: Sequence[str]) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        positions: dict[str, int] = {}
        previous_order = -1

        for index, name in enumerate(names):
            entry = self._entries.get(name)
            if entry is None:
                issues.append(
                    {
                        "code": "PROCESSOR_UNKNOWN",
                        "message": f"Unknown DOCX processor: {name!r}",
                    }
                )
                continue
            if name in positions:
                issues.append(
                    {
                        "code": "PROCESSOR_DUPLICATED",
                        "message": f"Processor {name!r} is declared more than once",
                    }
                )
            positions[name] = index
            if entry.order < previous_order:
                issues.append(
                    {
                        "code": "PROCESSOR_ORDER_INVALID",
                        "message": (
                            f"Processor {name!r} is out of canonical order; "
                            "keep DOCX processors in registry order."
                        ),
                    }
                )
            previous_order = max(previous_order, entry.order)

        for name in names:
            entry = self._entries.get(name)
            if entry is None:
                continue
            for dependency in entry.depends_on:
                if dependency not in positions:
                    issues.append(
                        {
                            "code": "PROCESSOR_DEPENDENCY_MISSING",
                            "message": (
                                f"Processor {name!r} requires {dependency!r} "
                                "to be declared earlier."
                            ),
                        }
                    )
                    continue
                if positions[dependency] > positions[name]:
                    issues.append(
                        {
                            "code": "PROCESSOR_DEPENDENCY_ORDER",
                            "message": (
                                f"Processor {name!r} requires {dependency!r} "
                                "to run earlier."
                            ),
                        }
                    )
        return issues


def build_docx_processor_registry() -> ProcessorRegistry:
    processors = build_default_docx_processors()
    entries = [
        ProcessorRegistryEntry(
            name=processor.name,
            processor=processor,
            order=index,
            depends_on=PROCESSOR_DEPENDENCIES.get(processor.name, ()),
        )
        for index, processor in enumerate(processors)
    ]
    return ProcessorRegistry(entries)


_REGISTRY = build_docx_processor_registry()


def known_docx_processor_names() -> set[str]:
    return _REGISTRY.known_names


def default_docx_processor_names() -> tuple[str, ...]:
    return _REGISTRY.default_names


def build_docx_processors(
    names: Sequence[str] | None = None,
) -> list[RenderProcessor]:
    return _REGISTRY.build(names)


def validate_docx_processor_sequence(
    names: Iterable[str],
) -> list[dict[str, Any]]:
    return _REGISTRY.validate_sequence(tuple(str(name) for name in names))
