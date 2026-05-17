"""Panel registry for canonical IDs, aliases, and enhancer dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from reportgen.panels.loader import PanelPackage


class UnknownPanelError(ValueError):
    """Raised when a caller explicitly requests an unregistered panel."""


@dataclass(frozen=True)
class PanelRegistration:
    """Runtime registration for one canonical panel id."""

    panel_id: str
    enhancer: Any
    aliases: tuple[str, ...] = ()
    package: Optional[PanelPackage] = None


class PanelRegistry:
    """Registry that owns panel aliases and runtime enhancer lookup."""

    def __init__(self) -> None:
        self._registrations: Dict[str, PanelRegistration] = {}
        self._aliases: Dict[str, str] = {}

    def register(
        self,
        panel_id: str,
        enhancer: Any,
        *,
        aliases: Iterable[str] = (),
        package: Optional[PanelPackage] = None,
        replace: bool = True,
    ) -> None:
        """Register one canonical panel id and optional aliases."""
        canonical = self._clean_panel_id(panel_id)
        if not canonical:
            raise ValueError("panel_id is required")
        if not replace and canonical in self._registrations:
            raise ValueError(f"Panel {canonical!r} is already registered")

        alias_tuple = tuple(
            alias
            for alias in (self._clean_panel_id(item) for item in aliases)
            if alias and alias != canonical
        )
        self._registrations[canonical] = PanelRegistration(
            panel_id=canonical,
            enhancer=enhancer,
            aliases=alias_tuple,
            package=package,
        )
        self._aliases[canonical] = canonical
        for alias in alias_tuple:
            self._aliases[alias] = canonical

    def normalize(self, panel_id: Optional[str], *, strict: bool = True) -> Optional[str]:
        """Return the canonical panel id for an alias."""
        cleaned = self._clean_panel_id(panel_id)
        if not cleaned:
            return None
        canonical = self._aliases.get(cleaned)
        if canonical:
            return canonical
        if strict:
            raise UnknownPanelError(
                f"未注册的Panel项目类型: {panel_id!r}。"
                f"已注册: {', '.join(self.panel_ids()) or '无'}"
            )
        return cleaned

    def get(self, panel_id: Optional[str]) -> Optional[PanelRegistration]:
        """Return a registration by canonical id or alias."""
        canonical = self.normalize(panel_id, strict=True)
        if canonical is None:
            return None
        return self._registrations[canonical]

    def get_enhancer(self, panel_id: Optional[str]) -> Any:
        """Return the enhancer for a canonical panel id or alias."""
        registration = self.get(panel_id)
        return registration.enhancer if registration is not None else None

    def is_registered(self, panel_id: Optional[str]) -> bool:
        """Whether a canonical panel id or alias is registered."""
        try:
            return self.normalize(panel_id, strict=True) is not None
        except UnknownPanelError:
            return False

    def panel_ids(self) -> List[str]:
        """Registered canonical panel ids."""
        return sorted(self._registrations)

    def aliases(self) -> Dict[str, str]:
        """Alias-to-canonical mapping, including canonical self-aliases."""
        return dict(sorted(self._aliases.items()))

    @staticmethod
    def _clean_panel_id(panel_id: Optional[str]) -> str:
        return str(panel_id or "").strip().lower()

