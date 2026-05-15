import socket
import time
from dataclasses import dataclass


@dataclass
class ProxyCheckResult:
    ok: bool
    latency_ms: int | None
    error: str | None


def check_tcp(host: str, port: int, timeout: float = 5.0) -> ProxyCheckResult:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            latency = int((time.perf_counter() - started) * 1000)
            return ProxyCheckResult(ok=True, latency_ms=latency, error=None)
    except OSError as exc:
        return ProxyCheckResult(ok=False, latency_ms=None, error=str(exc))
