# core/asgi_logging.py
import logging
import sys
import time
from urllib.parse import unquote

import colorlog
from colorlog.escape_codes import escape_codes

try:
    import colorama
    colorama.just_fix_windows_console()
except Exception:
    pass

logger = logging.getLogger("asgi_traffic")
logger.propagate = False

if not logger.handlers:
    handler = logging.StreamHandler(stream=sys.stdout)
    formatter = colorlog.ColoredFormatter(
        "%(asctime)s %(protocol_color)s%(protocol)s%(reset)s  "
        "%(method)s  %(path)s  %(status)s  %(duration_ms)sms  from %(client)s",
        datefmt="%d/%b/%Y %H:%M:%S",
        reset=True,
    )
    handler.setFormatter(formatter)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

class LogRequestMiddleware:
    def __init__(self, application):
        self.application = application

    async def __call__(self, scope, receive, send):
        print(scope)
        scope_type = scope.get("type")
        raw_path = unquote(scope.get("path", ""))
        query_bytes = scope.get("query_string", b"")
        query = query_bytes.decode("utf-8") if query_bytes else ""
        full_path = f"{raw_path}?{query}" if query else raw_path

        client = scope.get("client")
        client_str = f"{client[0]}:{client[1]}" if client else "-"

        if scope_type == "http":
            method = scope.get("method", "UNKNOWN")
            start = time.perf_counter()
            status_holder = {"status": "-"}

            async def send_wrapper(message):
                if message["type"] == "http.response.start":
                    status_holder["status"] = str(message.get("status", "-"))
                await send(message)

            try:
                await self.application(scope, receive, send_wrapper)
            finally:
                duration_ms = int((time.perf_counter() - start) * 1000)
                logger.info(
                    "",
                    extra={
                        "protocol": "HTTP",
                        "protocol_color": escape_codes["green"],
                        "method": method,
                        "path": full_path,
                        "client": client_str,
                        "status": status_holder["status"],
                        "duration_ms": duration_ms,
                    },
                )
            return

        if scope_type == "websocket":
            logger.info(
                "",
                extra={
                    "protocol": "WEBSOCKET",
                    "protocol_color": escape_codes["yellow"],
                    "method": "CONNECT",
                    "path": full_path,
                    "client": client_str,
                    "status": "-",
                    "duration_ms": "-",
                },
            )
            return await self.application(scope, receive, send)

        return await self.application(scope, receive, send)