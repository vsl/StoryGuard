from collections.abc import Mapping


def readiness_payload(checks: Mapping[str, bool]) -> tuple[dict[str, object], int]:
    ready = all(checks.values())
    return {
        "status": "ready" if ready else "not_ready",
        "checks": {name: "up" if passed else "down" for name, passed in checks.items()},
    }, 200 if ready else 503
