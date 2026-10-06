# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Matt Trentini

import asyncio

from co16 import CO16
from co16_web import create_app


async def main():
    board = CO16()
    board.start_network()
    app = create_app(board)
    print("KinCony CO16: Ethernet DHCP enabled; HTTP server listening on port 80.")
    print(
        "Web interface: /; REST API: /api/v1/status, /api/v1/io, "
        "/api/v1/relays/{channel}, /api/v1/time"
    )
    await app.start_server(host="0.0.0.0", port=80)


if __name__ == "__main__":
    asyncio.run(main())
