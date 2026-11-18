# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini

import asyncio

from co16 import CO16
from co16_lcd import run as run_lcd
from co16_web import create_app


async def main(board=None, app=None, *, host="0.0.0.0", port=80, serve=None):
    """Run the original workers with default hardware or explicit resources."""
    if board is None:
        board = CO16()
    board.start_network()
    if app is None:
        app = create_app(board)
    print("KinCony CO16: Ethernet enabled; HTTP port %d." % port)
    print(
        "Web interface: /; REST API: /api/v1/status, /api/v1/io, "
        "/api/v1/relays/{channel}, /api/v1/time"
    )
    display_task = asyncio.create_task(run_lcd(board))
    try:
        if serve is None:
            await app.start_server(host=host, port=port)
        else:
            await serve()
    finally:
        display_task.cancel()
        try:
            await display_task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
