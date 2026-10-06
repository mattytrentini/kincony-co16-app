"""Read-only HTTP interface for a CO16 hardware provider.

Only fixed static files and status/readback snapshots are exposed. This server
is unauthenticated and intended for a trusted LAN, not direct Internet access.
"""

from microdot import Microdot, Response


def _json_response(body, status_code=200):
    return Response(body, status_code, {"Cache-Control": "no-store"})


def _api_error(code, message, status_code):
    return _json_response(
        {"error": {"code": code, "message": message}}, status_code
    )


def _is_api_request(request):
    return request is not None and (
        request.path == "/api" or request.path.startswith("/api/")
    )


def create_app(board, static_dir=None):
    """Return an async Microdot app without starting the server.

    ``board.status()`` and ``board.io()`` are synchronous, short read-only
    snapshots. The async handlers keep dispatch on the event loop on both
    MicroPython and CPython; no hardware operation runs in a worker thread.
    ``static_dir`` defaults to the co16_static directory beside this module.
    """
    if static_dir is None:
        separator = __file__.rfind("/")
        static_dir = (
            __file__[: separator + 1] + "co16_static"
            if separator >= 0
            else "co16_static"
        )
    static_dir = static_dir.rstrip("/")

    app = Microdot()
    # Microdot otherwise answers OPTIONS automatically. This app exposes only
    # GET, with the framework's automatic HEAD support.
    app.options_handler = None

    @app.get("/")
    async def index(request):
        return Response.send_file(
            static_dir + "/index.html", content_type="text/html; charset=UTF-8"
        )

    @app.get("/assets/app.css")
    async def stylesheet(request):
        return Response.send_file(
            static_dir + "/app.css", content_type="text/css; charset=UTF-8"
        )

    @app.get("/assets/app.js")
    async def script(request):
        return Response.send_file(
            static_dir + "/app.js",
            content_type="application/javascript; charset=UTF-8",
        )

    @app.get("/api/v1/status")
    async def status(request):
        return _json_response(board.status())

    @app.get("/api/v1/io")
    async def io_snapshot(request):
        try:
            snapshot = board.io()
        except OSError:
            return _api_error(
                "io_unavailable", "IO snapshot is unavailable.", 503
            )
        return _json_response(snapshot)

    @app.errorhandler(404)
    async def not_found(request):
        if _is_api_request(request):
            return _api_error("not_found", "API endpoint not found.", 404)
        return Response("Not found.\n", 404)

    @app.errorhandler(405)
    async def method_not_allowed(request):
        if _is_api_request(request):
            response = _api_error(
                "method_not_allowed", "Only GET and HEAD are allowed.", 405
            )
        else:
            response = Response("Method not allowed.\n", 405)
        response.headers["Allow"] = "GET, HEAD"
        return response

    @app.errorhandler(500)
    async def internal_error(request):
        # Microdot logs unexpected exceptions before invoking this handler.
        # Never expose exception text or hardware paths in an HTTP response.
        if _is_api_request(request):
            return _api_error("internal_error", "Internal server error.", 500)
        return Response("Internal server error.\n", 500)

    return app
