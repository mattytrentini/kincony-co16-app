"""HTTP relay controls, RTC and snapshots for a CO16 hardware provider.

This server is unauthenticated and intended for a trusted LAN, not direct
Internet access.
"""

import json

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


def _json_payload(request):
    content_type = (request.content_type or "").split(";", 1)[0].strip().lower()
    if content_type != "application/json":
        return None, _api_error(
            "unsupported_media_type", "Content-Type must be application/json.", 415
        )
    try:
        payload = json.loads(request.body.decode())
    except ValueError:
        return None, _api_error("invalid_request", "Malformed JSON body.", 400)
    if not isinstance(payload, dict):
        return None, _api_error("invalid_request", "JSON body must be an object.", 400)
    return payload, None


def create_app(board, static_dir=None):
    """Return an async Microdot app without starting the server.

    The board's methods perform short synchronous hardware operations. Async
    handlers keep dispatch on the event loop on both MicroPython and CPython;
    no hardware operation runs in a worker thread.
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
    # Disable automatic OPTIONS; each route reports its supported methods.
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

    @app.route("/api/v1/relays/<int:channel>", methods=["GET", "POST"])
    async def relay(request, channel):
        if not 1 <= channel <= 16:
            return _api_error("not_found", "Relay channel not found.", 404)
        on = None
        if request.method == "POST":
            payload, error = _json_payload(request)
            if error is not None:
                return error
            if "on" not in payload or type(payload["on"]) is not bool:
                return _api_error(
                    "invalid_request", "Field 'on' must be a boolean.", 400
                )
            on = payload["on"]
        try:
            state = board.relay(channel, on)
        except OSError:
            return _api_error("io_unavailable", "Relay is unavailable.", 503)
        return _json_response(state)

    @app.route("/api/v1/time", methods=["GET", "POST"])
    async def clock(request):
        datetime = None
        if request.method == "POST":
            payload, error = _json_payload(request)
            if error is not None:
                return error
            if "datetime" not in payload or type(payload["datetime"]) is not str:
                return _api_error(
                    "invalid_request",
                    "Field 'datetime' must be YYYY-MM-DDTHH:MM:SS.", 400
                )
            datetime = payload["datetime"]
        try:
            state = board.clock(datetime)
        except ValueError:
            return _api_error(
                "invalid_request",
                "Invalid datetime; use YYYY-MM-DDTHH:MM:SS in years 2000..2099.",
                400,
            )
        except OSError:
            return _api_error("rtc_unavailable", "RTC is unavailable.", 503)
        return _json_response(state)

    @app.after_error_request
    async def prevent_api_error_caching(request, response):
        if _is_api_request(request):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(404)
    async def not_found(request):
        if _is_api_request(request):
            return _api_error("not_found", "API endpoint not found.", 404)
        return Response("Not found.\n", 404)

    @app.errorhandler(405)
    async def method_not_allowed(request):
        allow = "GET, HEAD"
        # Match the registered routes, not a broad writable URL prefix.
        for methods, pattern, _, _, _ in app.url_map:
            if pattern.match(request.path) is not None and "POST" in methods:
                allow = "GET, HEAD, POST"
                break
        if _is_api_request(request):
            response = _api_error(
                "method_not_allowed", "Allowed methods: " + allow + ".", 405
            )
        else:
            response = Response("Method not allowed.\n", 405)
        response.headers["Allow"] = allow
        return response

    @app.errorhandler(500)
    async def internal_error(request):
        # Microdot logs unexpected exceptions before invoking this handler.
        # Never expose exception text or hardware paths in an HTTP response.
        if _is_api_request(request):
            return _api_error("internal_error", "Internal server error.", 500)
        return Response("Internal server error.\n", 500)

    return app
