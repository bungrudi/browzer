"""Tab lifecycle management — creation, claiming, reuse, cleanup."""

from dataclasses import dataclass, field

from browzer.bridge import CodexBridge


@dataclass
class TabInfo:
    """Information about a browser tab."""

    id: int
    url: str = ""
    title: str = ""
    owned: bool = False
    created: bool = False
    attached: bool = False


class TabManager:
    """Manages tab lifecycle for a Browzer session.

    Tracks owned/created tabs, enforces reuse-first policy,
    and provides safe cleanup (never closes user tabs).
    """

    def __init__(self, bridge: CodexBridge) -> None:
        self.bridge = bridge
        self._tabs: dict[int, TabInfo] = {}

    async def list_tabs(self) -> list[TabInfo]:
        """Refresh and return all open tabs."""
        ...

    async def find_tab(
        self,
        url: str = "",
        url_contains: str = "",
        title_contains: str = "",
    ) -> TabInfo | None:
        """Find best matching existing tab."""
        ...

    async def get_or_open_tab(
        self, url: str, reuse: bool = True
    ) -> TabInfo:
        """Reuse-first: find existing tab or create + navigate a new one."""
        ...

    async def claim_and_attach(self, tab_id: int) -> None:
        """Claim ownership and attach debugger (idempotent)."""
        ...

    async def close_tab(self, tab_id: int) -> bool:
        """Close a tab via CDP. Only closes owned tabs."""
        ...

    async def cleanup(
        self,
        keep_tab_id: int | None = None,
        dry_run: bool = True,
    ) -> dict:
        """Find and optionally close unused owned tabs.

        Returns {dry_run, candidates: [...], closed: [...]}.
        """
        ...

    async def navigate(self, tab_id: int, url: str) -> None:
        """Navigate an existing tab to a new URL."""
        ...
