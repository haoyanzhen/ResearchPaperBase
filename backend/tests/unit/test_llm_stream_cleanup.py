"""Cancellation and start-send failures must release acquired SSE leases."""

from contextlib import contextmanager

import anyio
import pytest

from rpb.api.llm import LeasedStreamingResponse


@pytest.mark.parametrize("fail_start", [False, True])
def test_lc19_sse_cancel_or_start_failure_releases_lease(fail_start):
    released = []

    @contextmanager
    def lease():
        try:
            yield
        finally:
            released.append(True)

    async def run():
        acquired = lease()
        acquired.__enter__()

        async def content():
            yield "data: first\n\n"
            await anyio.sleep_forever()

        async def receive():
            await anyio.sleep_forever()

        async with anyio.create_task_group() as group:

            async def send(message):
                if fail_start:
                    raise OSError("disconnected")
                group.cancel_scope.cancel()

            async def serve():
                try:
                    await LeasedStreamingResponse(content(), acquired)(
                        {"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send
                    )
                except Exception:
                    if not fail_start:
                        raise

            group.start_soon(serve)

    anyio.run(run)
    assert released == [True]
