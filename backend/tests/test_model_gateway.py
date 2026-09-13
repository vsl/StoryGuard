"""Gateway contracts: no network, production config changes, or external billing."""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
import yaml
from langsmith import tracing_context

from app.ai.entity_extraction import _completion
from app.ai.entity_resolution import EntityResolutionError, resolve_pair
from app.ai.extraction_models import resolution_model_config
from app.db.models.entity_resolution import ResolutionCandidate
from app.entity_resolution import needs_evaluation
from scripts.entity_resolution_experiment import (
    case_input, evaluate_gateway_case, gateway_metrics, load_cases,
    resumable_rows,
)
from tests.test_retrieval import FakeTraceClient


class ModelGatewayTest(unittest.IsolatedAsyncioTestCase):
    def test_resume_repeats_only_transient_failures(self):
        rows = [
            {"id": "done", "error": None},
            {"id": "quota", "error": "MODEL_RATE_LIMITED"},
            {"id": "invalid", "error": "INVALID_MODEL_OUTPUT"},
        ]
        self.assertEqual([row["id"] for row in resumable_rows(rows)], ["done", "invalid"])

    async def test_alias_allowlist_and_promoted_default(self):
        promoted = resolution_model_config()
        self.assertEqual(promoted["litellm_alias"], "storyguard-entity-resolution")
        self.assertEqual((promoted["provider_model"], promoted["fallback"]),
                         ("gemini-3.5-flash-lite", "gemma4-e4b"))
        self.assertEqual(resolution_model_config("gemini")["provider_model"], "gemini-3.5-flash-lite")
        self.assertEqual(
            {name: resolution_model_config(name)["provider_model"] for name in (
                "gemini31-lite",
            )},
            {
                "gemini31-lite": "gemini-3.1-flash-lite",
            },
        )
        for experiment in ("gemini/gemini-3.5-flash-lite", "http://attacker", "unknown"):
            with self.assertRaises(ValueError):
                await resolve_pair(case_input(load_cases("dev")[0])[0], experiment=experiment)

    async def test_repair_telemetry_and_privacy_use_real_http_contract(self):
        pair, _ = case_input(load_cases("dev")[0])
        ids = [item["id"] for item in pair.evidence]
        calls = []
        def reply(request):
            body = json.loads(request.content)
            calls.append(body)
            self.assertEqual(body["model"], "storyguard-resolution-api-eval")
            self.assertEqual(body["response_format"]["type"], "json_schema")
            return httpx.Response(200, headers={
                "x-litellm-attempted-retries": "0", "x-litellm-attempted-fallbacks": "0",
                "x-litellm-response-cost": ".0001", "provider-api-key": "secret-value",
                "x-litellm-model-id": "sg-resolution-gemini35-lite-v1",
            }, json={"model": "storyguard-resolution-api-eval",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "choices": [{"message": {"content": json.dumps({"decision": "merge",
                    "evidence_ids": ["forged"] if len(calls) == 1 else ids})}}]})
        diagnostics = {"experiment_id": "test", "provider_api_key": "secret-value"}
        trace = FakeTraceClient()
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply), base_url="http://gateway") as client:
            with tracing_context(enabled=True, client=trace), patch(
                "app.ai.entity_resolution.trace_content_mode", return_value="minimal"
            ):
                result = await resolve_pair(pair, client, experiment="gemini", diagnostics=diagnostics)
        self.assertEqual((len(calls), result.repair_count, result.usage["total_tokens"]), (2, 1, 30))
        self.assertEqual(diagnostics["output_failures"], ["evidence"])
        self.assertEqual(result.model, "gemini-3.5-flash-lite")
        self.assertEqual(diagnostics["gateway_calls"][0]["model_identity_source"], "deployment_id_mapping")
        self.assertEqual(len(diagnostics["gateway_calls"]), 2)
        logged = json.dumps(trace.created + trace.updated, default=str)
        self.assertNotIn("secret-value", logged)
        self.assertNotIn(pair.evidence[0]["text"], logged)

    async def test_promoted_alias_reports_concrete_local_fallback(self):
        pair, _ = case_input(load_cases("dev")[0])
        diagnostics = {}
        def reply(_request):
            return httpx.Response(200, headers={
                "x-litellm-attempted-retries": "1", "x-litellm-attempted-fallbacks": "1",
                "x-litellm-model-id": "sg-resolution-prod-local-v1",
            }, json={"model": "storyguard-entity-resolution",
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "choices": [{"message": {"content": json.dumps({
                    "decision": "needs_review", "evidence_ids": []})}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply), base_url="http://gateway") as client:
            result = await resolve_pair(pair, client, diagnostics=diagnostics)
        self.assertEqual(result.model, "gemma4:e4b")
        self.assertEqual(diagnostics["gateway_calls"][0]["resolved_provider"], "ollama")
        self.assertEqual(diagnostics["gateway_calls"][0]["fallbacks"], 1)

    async def test_two_schema_failures_exhaust_repair_not_provider_retry(self):
        pair, _ = case_input(load_cases("dev")[0])
        attempts = []
        def reply(request):
            attempts.append(request)
            return httpx.Response(200, json={"model": "gemini-2.5-flash",
                "choices": [{"message": {"content": "not json"}}]})
        diagnostics = {}
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply), base_url="http://gateway") as client:
            with self.assertRaises(EntityResolutionError):
                await resolve_pair(pair, client, experiment="gemini", diagnostics=diagnostics)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(diagnostics["output_failures"], ["schema", "schema"])
        self.assertFalse(needs_evaluation(ResolutionCandidate(error_code="INVALID_MODEL_OUTPUT", model_metadata={"attempt": 1})))

    async def test_outages_have_safe_errors_unknown_cost_and_no_false_accuracy(self):
        case = load_cases("dev")[2]  # Expected needs_review; an outage is still a failure.
        snapshot = {"experiment_id": "test", "fixture_sha256": "fixture", "routing_config_sha256": "routing"}
        for status in (429, 503, 401):
            attempts = []
            def reply(request):
                attempts.append(request)
                return httpx.Response(status, text="private-provider-error")
            async with httpx.AsyncClient(transport=httpx.MockTransport(reply), base_url="http://gateway") as client:
                row = await evaluate_gateway_case(case, "gemini", client, snapshot)
            self.assertEqual(len(attempts), 1)
            self.assertEqual(gateway_metrics([row])["decision_accuracy"], 0)
            self.assertIsNone(row["paid_tier_estimate_usd"])
            self.assertIsNone(row["billed_cost_usd"])
            self.assertNotIn("private-provider-error", json.dumps(row))
        for attempt in (1, 2):
            candidate = ResolutionCandidate(error_code="MODEL_SERVER_ERROR", model_metadata={"attempt": attempt})
            self.assertEqual(needs_evaluation(candidate), attempt == 1)

    async def test_missing_invalid_headers_and_timeout_are_not_zero_telemetry(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200,
                headers={"x-litellm-response-cost": "NaN", "x-litellm-attempted-retries": "-1"},
                json={"model": "fixture", "choices": []})), base_url="http://gateway") as client:
            diagnostics = {}
            await _completion([], client, diagnostics=diagnostics)
        for key in ("gateway_estimated_cost_usd", "fallbacks", "served_deployment_retries"):
            self.assertIsNone(diagnostics["gateway_calls"][0][key])
        def timeout(request):
            raise httpx.ReadTimeout("private-error", request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(timeout), base_url="http://gateway") as client:
            with self.assertRaises(TimeoutError) as caught:
                await _completion([], client, diagnostics={})
        self.assertNotIn("private-error", str(caught.exception))

    def test_production_and_experimental_aliases_have_bounded_fallbacks(self):
        root = Path(__file__).parents[2]
        import os
        config = yaml.safe_load(Path(os.environ.get("STORYGUARD_LITELLM_CONFIG", root / "config/litellm.yaml")).read_text())
        router = config["router_settings"]
        self.assertEqual(router["max_fallbacks"], 1)
        self.assertEqual(router["fallbacks"], [
            {"storyguard-entity-resolution": ["storyguard-entity-resolution-local"]},
            {"storyguard-resolution-failover-eval": ["storyguard-resolution-api-eval"]},
        ])
        models = {item["model_name"]: item["litellm_params"] for item in config["model_list"]}
        production_pool = {
            item["model_info"]["id"]: item["litellm_params"]["model"]
            for item in config["model_list"]
            if item["model_name"] == "storyguard-entity-resolution"
        }
        self.assertEqual(production_pool, {
            "sg-resolution-prod-gemini35-lite-v1": "gemini/gemini-3.5-flash-lite",
            "sg-resolution-prod-gemini31-lite-v1": "gemini/gemini-3.1-flash-lite",
        })
        for alias in (
            "storyguard-resolution-local-eval", "storyguard-resolution-api-eval",
            "storyguard-resolution-gemini31-lite-eval",
        ):
            self.assertEqual(models[alias]["num_retries"], 0)
        self.assertEqual(models["storyguard-resolution-failover-eval"]["num_retries"], 1)
        self.assertEqual(models["storyguard-entity-resolution"]["num_retries"], 1)
        self.assertEqual(models["storyguard-entity-resolution-local"]["num_retries"], 0)


if __name__ == "__main__":
    unittest.main()
