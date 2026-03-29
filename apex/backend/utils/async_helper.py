"""Shared async-to-sync bridge used by pipeline agents."""

import asyncio
import concurrent.futures


def run_async(coro):
    """Run an async coroutine from a synchronous context.

    Safe to call from any thread, including AnyIO worker threads that have
    no current event loop (e.g. FastAPI background tasks).
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Already inside a running event loop (e.g. Jupyter / some test runners)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        if loop.is_closed():
            raise RuntimeError("loop is closed")
    except RuntimeError:
        # No event loop in this thread (common in AnyIO worker threads) or the
        # existing loop is closed — create a fresh one and register it so that
        # any asyncio calls inside the coroutine can find it via get_event_loop().
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)
