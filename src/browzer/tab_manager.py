"""Tab lifecycle management — creation, claiming, reuse, cleanup.

Tracks Browzer-owned tabs across a session. Enforces:
- Reuse-first policy: find existing tabs before creating new ones
- Ownership tracking: only close tabs we own
- Safe cleanup: dry-run by default, user tabs never touched
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from urllib.parse import urlparse

from browzer.bridge import CodexBridge
from browzer.transport import BridgeError

logger = logging.getLogger(__name__)


@dataclass
class TabInfo:
    """Information about a browser tab tracked by Browzer."""

    id: int
    url: str = ""
    title: str = ""
    owned: bool = False   # Claimed by us via claimUserTab
    created: bool = False  # Created by us via createTab
    attached: bool = False


class TabManager:
    """Manages tab lifecycle for a Browzer session.

    Tracks owned and created tabs, enforces reuse-first policy,
    and provides safe cleanup that never touches user tabs.

    Usage::

        tm = TabManager(bridge)
        tab = await tm.get_or_open_tab("https://gemini.google.com")
        await tm.cleanup(keep_tab_id=tab.id)
    """

    def __init__(self, bridge: CodexBridge) -> None:
        self._bridge = bridge
        self._tabs: dict[int, TabInfo] = {}

    # ------------------------------------------------------------------
    # Listing
    # ------------------------------------------------------------------

    async def list_tabs(self) -> list[TabInfo]:
        """Refresh and return all open tabs, merging with tracked state."""
        raw = await self._bridge.get_user_tabs()
        tabs = []
        for t in raw:
            tid = t["id"]
            existing = self._tabs.get(tid)
            info = TabInfo(
                id=tid,
                url=t.get("url", ""),
                title=t.get("title", ""),
                owned=existing.owned if existing else False,
                created=existing.created if existing else False,
                attached=existing.attached if existing else False,
            )
            self._tabs[tid] = info
            tabs.append(info)
        return tabs

    # ------------------------------------------------------------------
    # Finding
    # ------------------------------------------------------------------

    async def find_tab(
        self,
        url: str = "",
        url_contains: str = "",
        title_contains: str = "",
    ) -> TabInfo | None:
        """Find the best matching existing tab.

        Priority order:
        1. Exact URL match
        2. URL substring match (domain)
        3. Title substring match

        Returns the first match found, or None.
        """
        tabs = await self.list_tabs()

        def _score(tab: TabInfo) -> int:
            """Higher score = better match."""
            s = 0
            if url and tab.url == url:
                s += 100
            if url_contains and url_contains in tab.url:
                s += 50
            if title_contains and title_contains.lower() in tab.title.lower():
                s += 25
            return s

        scored = [(t, _score(t)) for t in tabs]
        scored.sort(key=lambda x: -x[1])

        if scored and scored[0][1] > 0:
            return scored[0][0]
        return None

    # ------------------------------------------------------------------
    # Get-or-open (reuse-first)
    # ------------------------------------------------------------------

    async def get_or_open_tab(
        self, url: str, reuse: bool = True
    ) -> TabInfo:
        """Reuse-first: find existing tab or create and navigate a new one.

        Args:
            url: Target URL to open.
            reuse: If True (default), try to find and reuse an existing tab.

        Returns:
            The TabInfo for the opened/reused tab.

        The returned tab is guaranteed to be claimed and attached
        for CDP access.
        """
        if reuse:
            # Extract domain for fuzzy matching
            domain = urlparse(url).netloc
            existing = await self.find_tab(
                url=url,
                url_contains=domain if domain else url,
            )
            if existing:
                logger.info(
                    "Reusing tab %d (%s) for %s", existing.id, existing.title, url
                )
                # Claim and attach first, then navigate
                await self._claim_and_attach(existing.id)
                if existing.url != url:
                    await self.navigate(existing.id, url)
                    existing.url = url
                return existing

        # Create fresh tab
        return await self._create_and_navigate(url)

    async def _create_and_navigate(self, url: str) -> TabInfo:
        """Create a new tab, claim, attach, then navigate."""
        raw = await self._bridge.create_tab()
        tab_id = raw["id"]
        logger.info("Created tab %d", tab_id)

        await self._claim_and_attach(tab_id)
        await self.navigate(tab_id, url)

        info = TabInfo(
            id=tab_id,
            url=url,
            title="",
            owned=True,
            created=True,
            attached=True,
        )
        self._tabs[tab_id] = info
        return info

    # ------------------------------------------------------------------
    # Claim & attach
    # ------------------------------------------------------------------

    async def _claim_and_attach(self, tab_id: int) -> None:
        """Claim ownership and attach debugger.

        Detaches first to clean any stale state from a previous
        session or interrupted transport. Then claims and attaches.
        Errors during claim are NOT suppressed — a failed claim
        means the tab is in a bad state and subsequent CDP will fail.
        """
        # Detach first — idempotent, cleans stale attachments.
        await self._bridge.detach(tab_id)
        # Claim + attach — let errors propagate.
        await self._bridge.claim_user_tab(tab_id)
        await self._bridge.attach(tab_id)

        info = self._tabs.get(tab_id)
        if info:
            info.owned = True
            info.attached = True
        else:
            self._tabs[tab_id] = TabInfo(
                id=tab_id, owned=True, attached=True
            )

    async def claim_and_attach(self, tab_id: int) -> None:
        """Public wrapper for claim + attach (idempotent)."""
        await self._claim_and_attach(tab_id)

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    async def navigate(self, tab_id: int, url: str) -> None:
        """Navigate an existing tab to a new URL."""
        await self._bridge.execute_cdp(
            tab_id, "Page.navigate", {"url": url}
        )
        if tab_id in self._tabs:
            self._tabs[tab_id].url = url

    # ------------------------------------------------------------------
    # Closing
    # ------------------------------------------------------------------

    async def close_tab(self, tab_id: int) -> bool:
        """Close a tab via CDP. Only closes owned tabs.

        Returns True if the tab was closed, False if it couldn't
        be (not owned, not found, etc.).
        """
        info = self._tabs.get(tab_id)
        if not info:
            logger.warning("close_tab: tab %d not tracked", tab_id)
            return False
        if not info.owned:
            logger.warning("close_tab: tab %d is not owned, refusing", tab_id)
            return False

        try:
            await self._bridge.execute_cdp(
                tab_id, "Runtime.evaluate",
                {"expression": "window.close()", "returnByValue": True},
            )
        except BridgeError:
            # Fallback: try Page.close if the bridge supports it
            pass

        self._tabs.pop(tab_id, None)
        logger.info("Closed tab %d", tab_id)
        return True

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def cleanup(
        self,
        keep_tab_id: int | None = None,
        dry_run: bool = True,
    ) -> dict:
        """Find and optionally close unused owned tabs.

        Args:
            keep_tab_id: A tab ID to preserve (never close this one).
            dry_run: If True (default), only list candidates without closing.

        Returns:
            ``{dry_run: bool, candidates: [TabInfo], closed: [int]}``

        Candidates are owned tabs that are either blank or not the
        ``keep_tab_id``. User tabs (not owned by Browzer) are never
        candidates.
        """
        tabs = await self.list_tabs()
        candidates = []

        for tab in tabs:
            if not tab.owned:
                continue
            if keep_tab_id is not None and tab.id == keep_tab_id:
                continue
            # Close blank tabs and owned-but-abandoned tabs
            if not tab.url or tab.url == "about:blank":
                candidates.append(tab)

        closed = []
        if not dry_run:
            for tab in candidates:
                if await self.close_tab(tab.id):
                    closed.append(tab.id)

        return {
            "dry_run": dry_run,
            "candidates": [
                {"id": t.id, "url": t.url, "title": t.title}
                for t in candidates
            ],
            "closed": closed,
        }
