from playwright.async_api import Browser, BrowserContext, async_playwright


class BrowserManager:
    """One Chromium process for the whole app; one cheap context per job."""

    def __init__(self) -> None:
        self._pw = None
        self._browser: Browser | None = None

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def new_context(self, **kwargs) -> BrowserContext:
        assert self._browser, "BrowserManager.start() was not called"
        return await self._browser.new_context(**kwargs)
