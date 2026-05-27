"""Ref ↔ backendNodeId mapping per tab for stable element references."""

from dataclasses import dataclass, field


@dataclass
class ElementRef:
    """An indexed element reference.

    Maps a stable ref string (e.g., '@e1') to CDP node identifiers
    and semantic metadata for interaction.
    """

    ref: str
    backend_node_id: int
    node_id: int | None = None
    tag: str = ""
    role: str = ""
    name: str = ""
    text: str = ""
    placeholder: str = ""
    value: str = ""
    disabled: bool = False
    bounds: dict | None = None
    attributes: dict = field(default_factory=dict)


class ElementStore:
    """Maintains ref-to-element mappings per tab.

    Ref format: '@e1', '@e2', ... — sequential 1-based indices
    assigned by the state engine when building page snapshots.
    """

    def __init__(self) -> None:
        self._stores: dict[int, dict[str, ElementRef]] = {}

    def set_elements(self, tab_id: int, elements: list[ElementRef]) -> None:
        """Store indexed elements for a tab. Overwrites previous."""
        self._stores[tab_id] = {e.ref: e for e in elements}

    def get_element(self, tab_id: int, ref: str) -> ElementRef | None:
        """Resolve a ref to its ElementRef."""
        return self._stores.get(tab_id, {}).get(ref)

    def invalidate(self, tab_id: int) -> None:
        """Clear stored elements for a tab (page changed)."""
        self._stores.pop(tab_id, None)

    def list_refs(self, tab_id: int) -> list[str]:
        """List all refs for a tab."""
        return list(self._stores.get(tab_id, {}).keys())
