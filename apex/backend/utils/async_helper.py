"""Shared async-to-sync bridge used by pipeline agents."""

import asyncio
import concurrent.futures


def run_async(coro):
    """Run an async coroutine from a synchronous context.

    Safe to call from any thread, including AnyIO worker threads that have
    no current event loop (e.g. FastAPI background tasks on Railway).
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Already inside a running event loop (e.g. nested call from async
        # context, Jupyter, or AnyIO worker thread that inherited a loop).
        # Cannot use asyncio.run() here — it would conflict with the running
        # loop.  Offload to a fresh thread that owns its own loop.
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    else:
        # No running loop in this thread — the common case for AnyIO worker
        # threads on Railway.  asyncio.run() creates a fresh, isolated loop,
        # runs the coroutine, then tears the loop down cleanly.
        return asyncio.run(coro)
