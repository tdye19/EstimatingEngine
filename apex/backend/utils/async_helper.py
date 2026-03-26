"""Shared async-to-sync bridge used by pipeline agents."""

import asyncio
import concurrent.futures


def run_async(coro):
    """Run an async coroutine from a synchronous context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Running inside an existing event loop (e.g. Jupyter / some test runners)
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)
