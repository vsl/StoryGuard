"""Run inside the pinned LiteLLM container; synthetic failure injection only.

python /tmp/storyguard-gateway-failover.py --config /app/config.yaml
Add --live-gemini for one real Gemini fallback request (Free Tier project).
Add --live-local for one real production-local fallback request.
The running proxy and its production deployments are never modified.
"""

import argparse
import asyncio
import contextlib
import io
import json
import logging
import hashlib
import time
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml


async def check(config, live_target):
    from litellm import Router
    from litellm.types.router import RetryPolicy
    import litellm

    counts = Counter()
    status = {"primary": 503, "fallback": 503}

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            target = "primary" if self.path.startswith("/primary/") else "fallback"
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            counts[target] += 1
            self.send_response(status[target])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Synthetic provider outage"}).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    primary, fallback = (("storyguard-entity-resolution", "storyguard-entity-resolution-local")
                         if live_target == "local" else
                         ("storyguard-resolution-failover-eval", "storyguard-resolution-api-eval"))
    models = [item for item in config["model_list"] if item["model_name"] in {primary, fallback}]
    models = json.loads(json.dumps(models))
    for item in models:
        if item["model_name"] == primary:
            item["litellm_params"] = {"model": "ollama_chat/gemma4:e4b",
                                      "api_base": base + "/primary", "num_retries": 1, "timeout": 5}
        elif live_target is None:
            item["litellm_params"] = {"model": "ollama_chat/gemma4:e4b",
                                      "api_base": base + "/fallback", "num_retries": 0, "timeout": 5}
    settings = dict(config["router_settings"])
    settings["model_group_retry_policy"] = {
        key: RetryPolicy(**value) for key, value in settings["model_group_retry_policy"].items()
    }
    # Fresh isolated router, no production cooldown/state changes.
    router = Router(model_list=models, disable_cooldowns=True, **settings)
    litellm.suppress_debug_info = True
    schema = {"type": "object", "properties": {
        "decision": {"type": "string", "enum": ["needs_review"]},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    }, "required": ["decision", "evidence_ids"], "additionalProperties": False}
    try:
        try:
            response = await router.acompletion(model=primary,
                messages=[{"role": "user", "content": "Synthetic test: two names, no evidence of identity. Return needs_review with no evidence IDs."}],
                temperature=0, max_tokens=1536 if live_target == "local" else 128,
                response_format={"type": "json_schema", "json_schema": {"name": "resolution_smoke", "strict": True, "schema": schema}})
        except Exception as exc:
            result = {"status": "provider_failure", "error_type": type(exc).__name__, "counts": dict(counts)}
            if live_target is not None:
                raise RuntimeError(json.dumps(result)) from None
            assert counts == {"primary": 2, "fallback": 1}, result
            result["bounded_failure_verified"] = True
        else:
            assert live_target is not None, "Both synthetic providers should fail"
            parsed = json.loads(response.choices[0].message.content)
            assert parsed == {"decision": "needs_review", "evidence_ids": []}, "Invalid fallback output"
            assert counts["primary"] == 2, dict(counts)
            headers = response._hidden_params.get("additional_headers", {})
            assert int(headers.get("x-litellm-attempted-fallbacks", -1)) == 1, "Missing fallback telemetry"
            result = {"status": "fallback_success", "counts": dict(counts), "resolved_model": response.model,
                      "attempted_fallbacks": 1, "usage": response.usage.model_dump(),
                      "billed_cost_usd": None,
                      "pricing_basis": "local" if live_target == "local" else "user_declared_free_tier"}
        return result
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    live = parser.add_mutually_exclusive_group()
    live.add_argument("--live-gemini", action="store_true")
    live.add_argument("--live-local", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    # SDK errors can contain request material; print only explicit safe results.
    logging.disable(logging.CRITICAL)
    started = time.perf_counter()
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            target = "gemini" if args.live_gemini else "local" if args.live_local else None
            result = asyncio.run(check(yaml.safe_load(args.config.read_text()), target))
    except Exception as exc:
        print(json.dumps({"status": "check_failed", "error_type": type(exc).__name__,
                          "detail": str(exc) if isinstance(exc, (AssertionError, RuntimeError)) else "See check implementation"}))
        raise SystemExit(1) from None
    result.update(elapsed_ms=(time.perf_counter() - started) * 1000,
                  routing_config_sha256=hashlib.sha256(args.config.read_bytes()).hexdigest())
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
