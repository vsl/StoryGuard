import asyncio
import json
import os
import unittest
import uuid
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from langsmith import tracing_context

from app.ai.coreference import load_coreference
from app.ai.tracing import annotate_trace
from app.ai.entity_resolution import (
    EntityResolutionError, ResolutionOutput, ResolutionResult, _trace_inputs,
    normalize_name, resolve_pair,
)
from app.db.models.entity_resolution import Entity, ResolutionCandidate
from app.entity_resolution import ResolutionConflict, candidate_pairs, canonical_id, needs_evaluation, resolution_config
from scripts.entity_resolution_experiment import case_input, load_cases, metrics
from tests.test_retrieval import FakeTraceClient


def completion(decision, ids):
    return {"model": "ollama_chat/gemma4:e4b", "choices": [{"message": {
        "content": json.dumps({"decision": decision, "evidence_ids": ids})}}]}


class ResolutionTest(unittest.IsolatedAsyncioTestCase):
    async def test_comparison_trace_metadata_privacy_and_outage(self):
        pair, _ = case_input(load_cases("dev")[0])
        ids = [item["id"] for item in pair.evidence]
        diagnostics = {"job_id": str(uuid.uuid4()), "run_attempt": 7, "candidate_id": str(uuid.uuid4()),
                       "pair_attempt": 2, "batch_trace_id": str(uuid.uuid4()), "resolver": "gemma",
                       "provider_api_key": "private-provider-credential"}
        for mode in ("minimal", "redacted", "full"):
            client = FakeTraceClient()
            with tracing_context(enabled=True, client=client), patch(
                "app.ai.entity_resolution.trace_content_mode", return_value=mode
            ), patch("app.ai.entity_resolution._completion", new=AsyncMock(return_value=completion("merge", ids))):
                result = await resolve_pair(pair, diagnostics=diagnostics)
            self.assertEqual(result.output.decision, "merge")
            metadata = client.updated[0]["extra"]["metadata"]
            self.assertEqual((metadata["job_id"], metadata["run_attempt"], metadata["pair_attempt"]), (diagnostics["job_id"], 7, 2))
            serialized = json.dumps(client.created + client.updated, default=str)
            self.assertNotIn("private-provider-credential", serialized)
            self.assertEqual("pair" in client.created[0]["inputs"], mode == "full")
            if mode != "full":
                self.assertNotIn(pair.left.surface_text, serialized)
        for enabled, client in ((False, FakeTraceClient()), (True, FakeTraceClient(fail=True))):
            with tracing_context(enabled=enabled, client=client), patch(
                "app.ai.entity_resolution._completion", new=AsyncMock(return_value=completion("merge", ids))
            ):
                self.assertEqual((await resolve_pair(pair, diagnostics=diagnostics)).output.decision, "merge")
        with patch("app.ai.tracing.get_current_run_tree", side_effect=RuntimeError("private-error")):
            self.assertIsNone(annotate_trace(outputs={"outcome": "completed"}))

    def test_automatic_application_is_enabled_by_default(self):
        config = resolution_config()
        self.assertIs(config["auto_apply"], True)
        self.assertEqual((config["provider_model"], config["max_output_tokens"]), ("gemini-3.5-flash-lite", 1536))

    def test_saved_attempt_count_limits_automatic_retries(self):
        candidate = ResolutionCandidate(error_code="MODEL_TIMEOUT", model_metadata={})
        self.assertTrue(needs_evaluation(candidate))  # Legacy failure without a count.
        for attempt in (1, 2, 3):
            candidate.model_metadata = {"attempt": attempt}
            self.assertEqual(needs_evaluation(candidate), attempt < 2)
        candidate.error_code = "INVALID_MODEL_OUTPUT"
        candidate.model_metadata = {"attempt": 1}
        self.assertFalse(needs_evaluation(candidate))
        candidate.error_code = None
        self.assertTrue(needs_evaluation(candidate))
        candidate.applied_decision = "merge"
        self.assertFalse(needs_evaluation(candidate))

    async def test_three_decisions_and_strict_evidence(self):
        pair, _ = case_input(load_cases("dev")[0])
        ids = [item["id"] for item in pair.evidence]
        for decision in ("merge", "keep_separate", "needs_review"):
            with patch("app.ai.entity_resolution._completion", new=AsyncMock(return_value=completion(decision, ids))) as call:
                result = await resolve_pair(pair)
            self.assertEqual(result.output.decision, decision)
            self.assertEqual(call.await_args.kwargs["max_tokens"], 1536)
            self.assertEqual(call.await_args.kwargs["schema_name"], "entity_resolution")

    async def test_model_alias_and_token_limit_come_from_model_config(self):
        pair, _ = case_input(load_cases("dev")[0])
        ids = [item["id"] for item in pair.evidence]
        config = {"litellm_alias": "storyguard-test-resolution", "max_output_tokens": 999}
        with patch("app.ai.entity_resolution.resolution_model_config", return_value=config), patch(
            "app.ai.entity_resolution._completion", new=AsyncMock(return_value=completion("merge", ids))
        ) as call:
            result = await resolve_pair(pair)
        self.assertEqual(result.output.decision, "merge")
        self.assertEqual(call.await_args.args[2], "storyguard-test-resolution")
        self.assertEqual(call.await_args.kwargs["max_tokens"], 999)

    async def test_invalid_ids_repair_once_or_fail_without_raw_text(self):
        pair, _ = case_input(load_cases("dev")[0])
        ids = [item["id"] for item in pair.evidence]
        with patch("app.ai.entity_resolution._completion", new=AsyncMock(side_effect=[completion("merge", ["forged"]), completion("needs_review", ids)])) as call:
            result = await resolve_pair(pair)
        self.assertEqual((call.await_count, result.repair_count), (2, 1))
        for payload in (completion("merge", []), completion("wrong", ids), completion("merge", ["forged"]), []):
            with patch("app.ai.entity_resolution._completion", new=AsyncMock(return_value=payload)) as call:
                with self.assertRaisesRegex(EntityResolutionError, "after one repair") as caught:
                    await resolve_pair(pair)
            self.assertEqual(call.await_count, 2)
            self.assertNotIn(pair.left.surface_text, str(caught.exception))

    async def test_scope_type_validation_happens_before_inference(self):
        pair, _ = case_input(load_cases("dev")[0])
        with patch("app.ai.entity_resolution._completion", new=AsyncMock()) as call:
            with self.assertRaises(ValueError):
                await resolve_pair(replace(pair, right=replace(pair.right, entity_type="location")))
            with self.assertRaises(ValueError):
                await resolve_pair(replace(pair, left=replace(pair.left, entity_type="object"),
                                          right=replace(pair.right, entity_type="object")))
        call.assert_not_awaited()

    async def test_repair_has_its_own_timeout_and_failure_has_trace_metadata(self):
        pair, _ = case_input(load_cases("dev")[0])
        ids = [item["id"] for item in pair.evidence]
        replies = iter([completion("wrong", ids), completion("merge", ids)])
        async def delayed(*args, **kwargs):
            self.assertEqual(kwargs["request_timeout"], .1)
            await asyncio.sleep(.06)
            return next(replies)
        diagnostics = {}
        with patch("app.ai.entity_resolution._completion", new=AsyncMock(side_effect=delayed)):
            result = await resolve_pair(pair, request_timeout=.1, diagnostics=diagnostics)
        self.assertEqual(result.repair_count, 1)
        self.assertEqual(diagnostics["repair_count"], 1)
        self.assertIn("trace_id", diagnostics)

    def test_fixture_offsets_candidate_ceiling_and_trace_privacy(self):
        self.assertEqual(normalize_name("  Dr. ÉVA  "), "dr éva")
        for case in load_cases("dev") + load_cases("test"):
            pair, found = case_input(case)
            self.assertEqual(found, case["id"] != "candidate-distance-miss")
            with patch("app.ai.entity_resolution.trace_content_mode", return_value="minimal"):
                traced = json.dumps(_trace_inputs({"pair": pair}))
            self.assertNotIn(pair.left.surface_text, traced)
            self.assertNotIn(pair.evidence[0]["text"], traced)
        from app.db.models.entity_mention import EntityMention
        chapter_id = uuid.uuid4()
        mentions = [EntityMention(id=uuid.uuid4(), chapter_id=chapter_id, entity_type="character",
                                 surface_text="Alex", start_offset=i * 10, end_offset=i * 10 + 4) for i in range(20)]
        with patch("app.entity_resolution.MAX_CANDIDATES", 5):
            self.assertEqual(len(candidate_pairs(mentions)), 5)

    def test_cycles_and_undefined_baseline_precision(self):
        a, b = uuid.uuid4(), uuid.uuid4()
        with self.assertRaises(ResolutionConflict):
            canonical_id(a, {a: Entity(id=a, merged_into_id=b), b: Entity(id=b, merged_into_id=a)})
        row = {"baseline": "needs_review", "expected": "merge", "latency_ms": 0, "error": None}
        self.assertIsNone(metrics([row], "baseline")["merge_precision"])


RUN_DATABASE_TESTS = os.environ.get("RUN_DATABASE_TESTS") == "1"
if RUN_DATABASE_TESTS:
    import httpx
    from sqlalchemy import func, select
    from app.db.models.entity_mention import EntityMention
    from app.db.models.entity_resolution import ResolutionCandidate, ResolutionDecision
    from app.db.models.job_run import JobRun
    from app.db.models.manuscript_version import ManuscriptVersion
    from app.db.models.narrative import Chapter, Chunk
    from app.db.models.project import Project
    from app.db.session import SessionLocal, engine
    from app.entity_resolution import (
        apply_automatic_predictions, apply_decision, candidates_for, current_scope,
        entity_map, make_pair, prepare_candidates, source_rows,
    )
    from app.main import app
    from app.queue.tasks.entity_resolution import run_resolution_job


@unittest.skipUnless(RUN_DATABASE_TESTS, "set RUN_DATABASE_TESTS=1")
class ResolutionDatabaseTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.addAsyncCleanup(engine.dispose)
        # Inference is mocked here; only workers need a real proxy credential.
        environment = patch.dict(os.environ, {"LITELLM_URL": "http://litellm:4000", "LITELLM_API_KEY": "test"})
        environment.start()
        self.addCleanup(environment.stop)
        # Existing Gemma lifecycle tests should not load the real coreference model.
        coreference = patch("app.queue.tasks.entity_resolution.load_coreference", new=AsyncMock(side_effect=RuntimeError("test runtime unavailable")))
        self.coreference = coreference.start()
        self.addCleanup(coreference.stop)
        # Exercise the real DB lifecycle without delivering test jobs to live workers.
        dispatch = patch("app.queue.tasks.entity_resolution.resolve_manuscript_entities.kiq", new=AsyncMock())
        self.dispatch = dispatch.start()
        self.addCleanup(dispatch.stop)
        retry_delay = patch("app.queue.tasks.entity_resolution.PROVIDER_RETRY_DELAY_SECONDS", 0)
        retry_delay.start()
        self.addCleanup(retry_delay.stop)
        self.project_id, self.other_id = uuid.uuid4(), uuid.uuid4()
        self.version_id, self.old_version_id = uuid.uuid4(), uuid.uuid4()
        self.chapter_id, self.chunk_id = uuid.uuid4(), uuid.uuid4()
        self.text = "Nora Vale, called Nori, greeted Nora Cross."
        self.mention_ids = [uuid.uuid4() for _ in range(3)]
        async with SessionLocal() as session, session.begin():
            session.add_all([Project(id=self.project_id, title="Resolution test"), Project(id=self.other_id, title="Other test")])
            await session.flush()
            for number, version_id in enumerate((self.old_version_id, self.version_id), 1):
                session.add(ManuscriptVersion(id=version_id, project_id=self.project_id, version_number=number,
                    status="ready", object_key=f"resolution-test/{version_id}", original_filename="test.txt", mime_type="text/plain", file_size=len(self.text), content_hash="a" * 64))
            await session.flush()
            project = await session.get(Project, self.project_id)
            project.current_manuscript_version_id = self.version_id
            other_version_id = uuid.uuid4()
            session.add(ManuscriptVersion(id=other_version_id, project_id=self.other_id, version_number=1,
                status="ready", object_key=f"resolution-test/{other_version_id}", original_filename="other.txt",
                mime_type="text/plain", file_size=1, content_hash="b" * 64))
            await session.flush()
            other = await session.get(Project, self.other_id)
            other.current_manuscript_version_id = other_version_id
            session.add(Chapter(id=self.chapter_id, manuscript_version_id=self.version_id, ordinal=1, title="Test", text=self.text, content_hash="a" * 64))
            await session.flush()
            session.add(Chunk(id=self.chunk_id, manuscript_version_id=self.version_id, chapter_id=self.chapter_id, ordinal=1,
                              text=self.text, start_offset=0, end_offset=len(self.text), content_hash="a" * 64))
            await session.flush()
            for mention_id, name in zip(self.mention_ids, ("Nora Vale", "Nori", "Nora Cross"), strict=True):
                start = self.text.index(name)
                session.add(EntityMention(id=mention_id, manuscript_version_id=self.version_id, chapter_id=self.chapter_id,
                    chunk_id=self.chunk_id, entity_type="character", surface_text=name, start_offset=start,
                    end_offset=start + len(name), prompt_version="fixture", model_alias="fixture"))
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        async with SessionLocal() as session, session.begin():
            for project_id in (self.project_id, self.other_id):
                project = await session.get(Project, project_id)
                await session.delete(project)

    async def start_job(self):
        with patch("app.api.entity_resolution.resolve_manuscript_entities.kiq", new=AsyncMock()):
            response = await self.client.post(f"/api/projects/{self.project_id}/entity-resolution/run", json={"manuscript_version_id": str(self.version_id)})
        self.assertEqual(response.status_code, 202, response.text)
        return uuid.UUID(response.json()["job_id"])

    async def test_entity_category_api_scope_and_invalid_category(self):
        from app.ai.entity_extraction import EntityType
        async with SessionLocal() as session, session.begin():
            await prepare_candidates(session, self.version_id)
            for category in EntityType:
                session.add(Entity(manuscript_version_id=self.version_id, entity_type=category,
                                   canonical_name=f"Named {category}", status="active"))
        for category in EntityType:
            response = await self.client.get(f"/api/projects/{self.project_id}/entities?type={category}")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertTrue(response.json())
            self.assertTrue(all(item["type"] == category for item in response.json()))
            entity_id = response.json()[0]["id"]
            self.assertEqual((await self.client.get(f"/api/projects/{self.project_id}/entities/{entity_id}")).status_code, 200)
            self.assertEqual((await self.client.get(f"/api/projects/{self.other_id}/entities/{entity_id}")).status_code, 404)
        for category in ("object", "other"):
            self.assertEqual((await self.client.get(f"/api/projects/{self.project_id}/entities?type={category}")).status_code, 422)
            from sqlalchemy.exc import IntegrityError
            with self.assertRaises(IntegrityError):
                async with SessionLocal() as session, session.begin():
                    session.add(Entity(manuscript_version_id=self.version_id, entity_type=category,
                                       canonical_name="Rejected", status="active"))
                    await session.flush()
        self.assertEqual((await self.client.get(f"/api/projects/{self.project_id}/objects")).status_code, 404)

    async def fake_resolve(self, pair, _client, **kwargs):
        return ResolutionResult(ResolutionOutput(decision="merge", evidence_ids=[item["id"] for item in pair.evidence]), "fixture", 1, 0, {})

    def linked_coreference(self):
        import hashlib
        from app.ai.coreference import MODEL, REVISION, PIPELINE
        spans = [[self.text.index(name), self.text.index(name) + len(name)] for name in ("Nora Vale", "Nori")]
        return {"model": MODEL, "revision": REVISION, "pipeline": PIPELINE, "trace_id": "coreference-test-trace",
                "documents": [{"id": str(self.chapter_id), "text_sha256": hashlib.sha256(self.text.encode()).hexdigest(),
                               "windows": [{"clusters": [spans]}]}]}

    async def test_coreference_merges_skip_gemma_and_have_distinct_audit(self):
        self.coreference.side_effect = None
        self.coreference.return_value = self.linked_coreference()
        job_id = await self.start_job()
        # A coreference merge must not use up the one-Gemma-comparison batch budget.
        with patch("app.queue.tasks.entity_resolution.MAX_CALLS_PER_RUN", 1), patch(
            "app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=self.fake_resolve)
        ) as model:
            await run_resolution_job(job_id)
        self.assertEqual(model.await_count, 1)
        self.assertNotEqual({model.call_args.args[0].left.surface_text, model.call_args.args[0].right.surface_text}, {"Nora Vale", "Nori"})
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual(payload["pipeline"], "coreference_gemma")
        self.assertEqual((payload["coreference_merge_count"], payload["gemma_comparison_count"], payload["applied_count"]), (1, 1, 2))
        async with SessionLocal() as session:
            events = list(await session.scalars(select(ResolutionDecision).where(ResolutionDecision.manuscript_version_id == self.version_id)))
            coreference = [event for event in events if event.model_metadata.get("resolver") == "coreference"]
            self.assertEqual(len(coreference), 2)
            self.assertTrue(all(event.evidence and event.model_metadata["prompt_hash"] is None for event in coreference))
            self.assertTrue(all(event.model_metadata["trace_id"] == "coreference-test-trace" for event in coreference))

    async def test_coreference_failure_falls_back_and_is_visible(self):
        job_id = await self.start_job()
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=self.fake_resolve)) as model:
            await run_resolution_job(job_id)
        self.assertEqual(model.await_count, 3)
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual(payload["coreference_merge_count"], 0)
        self.assertEqual(payload["job"]["status"], "completed")
        self.assertEqual(payload["job"]["error_code"], "COREFERENCE_FAILED")
        self.assertIn("continuing with Gemma", payload["job"]["error_message_safe"])

    async def test_stop_during_coreference_cannot_apply_late_groups(self):
        job_id = await self.start_job()
        async def stop_then_return(*args):
            response = await self.client.post(
                f"/api/projects/{self.project_id}/entity-resolution/jobs/{job_id}/stop",
                json={"manuscript_version_id": str(self.version_id)},
            )
            self.assertEqual(response.status_code, 200)
            return self.linked_coreference()
        self.coreference.side_effect = stop_then_return
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock()) as model:
            await run_resolution_job(job_id)
        model.assert_not_awaited()
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual((payload["job"]["status"], payload["applied_count"]), ("cancelled", 0))

    async def test_coreference_respects_existing_separation(self):
        async with SessionLocal() as session, session.begin():
            await prepare_candidates(session, self.version_id)
            candidates = await candidates_for(session, self.version_id)
            separate = next(item for item in candidates if {item.left_mention_id, item.right_mention_id} == {self.mention_ids[0], self.mention_ids[2]})
            await apply_decision(session, separate, "keep_separate")
        cache = self.linked_coreference()
        cache["documents"][0]["windows"][0]["clusters"][0].append([self.text.index("Nora Cross"), self.text.index("Nora Cross") + len("Nora Cross")])
        self.coreference.side_effect = None
        self.coreference.return_value = cache
        job_id = await self.start_job()
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock()) as model:
            await run_resolution_job(job_id)
        model.assert_not_awaited()
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual(payload["coreference_merge_count"], 1)
        self.assertEqual(payload["items"][0]["error_code"], "CLUSTER_CONFLICT")
        self.assertEqual(len((await self.client.get(f"/api/projects/{self.project_id}/characters")).json()), 2)

    @patch("app.entity_resolution.resolution_config")
    @patch("app.api.entity_resolution.resolution_config")
    async def test_review_mode_real_api_idempotent_merge_and_audit_reversal(self, api_config, worker_config):
        api_config.return_value = worker_config.return_value = {**resolution_config(), "auto_apply": False}
        job_id = await self.start_job()
        self.assertEqual(await self.start_job(), job_id)
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=self.fake_resolve)) as model:
            await asyncio.gather(run_resolution_job(job_id), run_resolution_job(job_id))
            await run_resolution_job(job_id)
        self.assertEqual(model.await_count, 3)
        response = await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")
        payload = response.json()
        self.assertEqual((payload["review_count"], payload["applied_count"], payload["job"]["status"]), (3, 0, "completed"), payload)
        self.assertFalse(payload["auto_apply"])
        chosen = next(item for item in payload["items"] if {item["left"]["name"], item["right"]["name"]} == {"Nora Vale", "Nori"})
        route = f"/api/projects/{self.project_id}/entity-resolution/{chosen['id']}/resolve"
        for _ in range(2):
            self.assertEqual((await self.client.post(route, json={"decision": "merge"})).status_code, 204)
        self.assertEqual((await self.client.post(route, json={"decision": "keep_separate"})).status_code, 409)
        chars = (await self.client.get(f"/api/projects/{self.project_id}/characters")).json()
        self.assertEqual(len(chars), 2)
        nora = next(item for item in chars if item["name"] == "Nora Vale")
        self.assertEqual(nora["aliases"], ["Nori"])
        detail = (await self.client.get(f"/api/projects/{self.project_id}/characters/{nora['id']}")).json()
        self.assertEqual(detail["evidence"][0]["text"], self.text)
        async with SessionLocal() as session, session.begin():
            events = list(await session.scalars(select(ResolutionDecision).where(ResolutionDecision.manuscript_version_id == self.version_id, ResolutionDecision.source == "human")))
            self.assertEqual(len(events), 1)
            entities = await entity_map(session, self.version_id)
            original = list(await session.scalars(select(EntityMention).where(EntityMention.manuscript_version_id == self.version_id)))
            self.assertTrue(all(mention.entity_id == mention.id for mention in original))
            for entity_id, values in events[0].before["entities"].items():
                entities[uuid.UUID(entity_id)].merged_into_id = uuid.UUID(values["merged_into_id"]) if values["merged_into_id"] else None
                entities[uuid.UUID(entity_id)].status = values["status"]
            self.assertEqual(len({canonical_id(item.id, entities) for item in original}), 3)

    async def test_default_applies_merge_and_separation_but_not_review_or_errors(self):
        job_id = await self.start_job()
        async def classified(pair, client, **kwargs):
            names = {pair.left.surface_text, pair.right.surface_text}
            decision = ("merge" if names == {"Nora Vale", "Nori"} else
                        "keep_separate" if names == {"Nora Vale", "Nora Cross"} else "needs_review")
            result = await self.fake_resolve(pair, client)
            return replace(result, output=result.output.model_copy(update={"decision": decision}))
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=classified)) as model:
            await run_resolution_job(job_id)
            await run_resolution_job(job_id)
        self.assertEqual(model.await_count, 3)
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertTrue(payload["auto_apply"])
        self.assertEqual((payload["applied_count"], payload["review_count"], payload["remaining"]), (2, 1, 0))
        self.assertEqual(payload["job"]["status"], "completed")
        self.assertEqual(payload["items"][0]["llm_decision"], "needs_review")
        chars = (await self.client.get(f"/api/projects/{self.project_id}/characters")).json()
        self.assertEqual(len(chars), 2)
        self.assertIn({"Nori"}, [set(item["aliases"]) for item in chars])
        self.assertTrue(all(item["name"] not in item["aliases"] for item in chars))
        async with SessionLocal() as session, session.begin():
            events = list(await session.scalars(select(ResolutionDecision).where(
                ResolutionDecision.manuscript_version_id == self.version_id,
                ResolutionDecision.source == "automatic")))
            self.assertEqual({event.decision for event in events}, {"merge", "keep_separate"})
            self.assertEqual(len(events), 2)
            self.assertTrue(all(event.evidence and event.before and event.after for event in events))
            candidates = await candidates_for(session, self.version_id)
            pending = next(item for item in candidates if item.applied_decision is None)
            pending.llm_decision, pending.error_code = "merge", "INVALID_MODEL_OUTPUT"
            await apply_automatic_predictions(session, self.version_id)
            self.assertIsNone(pending.applied_decision)
            self.assertEqual((await session.get(ManuscriptVersion, self.version_id)).status, "ready")

    async def test_conflicting_chains_are_not_auto_merged(self):
        async with SessionLocal() as session, session.begin():
            await current_scope(session, self.project_id, self.version_id, lock=True)
            await prepare_candidates(session, self.version_id)
            candidates = await candidates_for(session, self.version_id)
            negative = set((self.mention_ids[0], self.mention_ids[2]))
            for item in candidates:
                item.llm_decision = "keep_separate" if {item.left_mention_id, item.right_mention_id} == negative else "merge"
            await apply_automatic_predictions(session, self.version_id)
            entities = await entity_map(session, self.version_id)
            self.assertEqual(len({canonical_id(key, entities) for key in entities}), 3)
            self.assertEqual(sum(item.error_code == "CLUSTER_CONFLICT" for item in candidates), 2)
            positive = next(item for item in candidates if item.llm_decision == "merge")
            await apply_decision(session, positive, "merge")
            other = next(item for item in candidates if item.llm_decision == "merge" and item.id != positive.id)
            with self.assertRaises(ResolutionConflict):
                await apply_decision(session, other, "merge")

    async def test_isolation_and_provider_failure_do_not_fail_the_manuscript(self):
        job_id = await self.start_job()
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=ConnectionError("provider-secret"))) as model:
            await run_resolution_job(job_id)
            async with SessionLocal() as session:
                self.assertEqual((await session.get(JobRun, job_id)).status, "queued")
            await run_resolution_job(job_id)
        self.assertEqual(model.await_count, 6)  # Three pairs, one deferred retry each.
        response = await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")
        self.assertNotIn("provider-secret", response.text)
        payload = response.json()
        self.assertEqual(payload["job"]["status"], "completed")
        candidate_id = payload["items"][0]["id"]
        self.assertEqual(payload["job"]["error_code"], "RESOLUTION_PAIR_ERRORS")
        self.assertEqual((payload["error_count"], payload["review_count"], payload["remaining"]), (3, 0, 0))
        self.assertTrue(all(item["llm_decision"] is None for item in payload["items"]))
        self.assertEqual((await self.client.post(f"/api/projects/{self.other_id}/entity-resolution/{candidate_id}/resolve", json={"decision": "merge"})).status_code, 404)
        self.assertEqual((await self.client.post(f"/api/projects/{self.project_id}/entity-resolution/run", json={"manuscript_version_id": str(self.version_id), "model": "attacker"})).status_code, 422)
        async with SessionLocal() as session, session.begin():
            self.assertEqual((await session.get(ManuscriptVersion, self.version_id)).status, "ready")
            project = await session.get(Project, self.project_id)
            project.current_manuscript_version_id = self.old_version_id
        self.assertEqual((await self.client.post(f"/api/projects/{self.project_id}/entity-resolution/{candidate_id}/resolve", json={"decision": "merge"})).status_code, 404)
        self.assertEqual((await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()["items"], [])

    async def test_queue_failure_and_changed_source_are_safe(self):
        with patch("app.api.entity_resolution.resolve_manuscript_entities.kiq", new=AsyncMock(side_effect=RuntimeError("amqp-secret"))):
            response = await self.client.post(f"/api/projects/{self.project_id}/entity-resolution/run", json={"manuscript_version_id": str(self.version_id)})
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("amqp-secret", response.text)
        job_id = await self.start_job()
        async def changed(pair, client, **kwargs):
            async with SessionLocal() as session, session.begin():
                chapter = await session.get(Chapter, self.chapter_id)
                chapter.text = "Changed manuscript"
            return await self.fake_resolve(pair, client)
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=changed)) as model:
            await run_resolution_job(job_id)
        model.assert_awaited_once()
        async with SessionLocal() as session:
            job = await session.get(JobRun, job_id)
            self.assertEqual(job.error_code, "RESOLUTION_SCOPE_CHANGED")
            self.assertEqual((await session.get(ManuscriptVersion, self.version_id)).status, "ready")
            self.assertEqual(await session.scalar(select(func.count()).select_from(ResolutionDecision).where(ResolutionDecision.manuscript_version_id == self.version_id)), 0)

    async def test_batch_continues_without_another_start_and_preserves_human_decision(self):
        job_id = await self.start_job()
        async def human_first(pair, client, **kwargs):
            payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
            chosen = next(item for item in payload["items"] if {item["left"]["id"], item["right"]["id"]} == {pair.left.id, pair.right.id})
            response = await self.client.post(f"/api/projects/{self.project_id}/entity-resolution/{chosen['id']}/resolve", json={"decision": "keep_separate"})
            self.assertEqual(response.status_code, 204)
            return await self.fake_resolve(pair, client)
        with patch("app.queue.tasks.entity_resolution.MAX_CALLS_PER_RUN", 1), patch(
            "app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=human_first)
        ) as model:
            await run_resolution_job(job_id)
        model.assert_awaited_once()
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual((payload["remaining"], payload["applied_count"], payload["job"]["status"]), (2, 1, "queued"))
        self.dispatch.assert_awaited_once_with(str(job_id))
        async with SessionLocal() as session:
            job = await session.get(JobRun, job_id)
            self.assertIsNone(job.completed_at)
            self.assertIsNotNone(job.stage_started_at)
        # Simulate delivery of the queued task, without another UI/API start.
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=self.fake_resolve)) as model:
            await run_resolution_job(job_id)
        self.assertEqual(model.await_count, 2)
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual((payload["remaining"], payload["applied_count"], payload["job"]["stage"]), (0, 2, "completed"))
        async with SessionLocal() as session:
            decisions = list(await session.scalars(select(ResolutionDecision).where(ResolutionDecision.manuscript_version_id == self.version_id)))
            self.assertEqual(len(decisions), 4)
            self.assertEqual(sum(item.source == "human" and item.decision == "keep_separate" for item in decisions), 1)
            entities = await entity_map(session, self.version_id)
            self.assertEqual(len({canonical_id(key, entities) for key in entities}), 2)

    async def test_batch_traces_link_comparisons_and_committed_counts(self):
        job_id = await self.start_job()
        client = FakeTraceClient()
        cache = {**self.linked_coreference(), "cache_hit": True, "cache_key": "test-cache"}
        self.coreference.side_effect = load_coreference  # Use the real tracing wrapper.
        async def valid_completion(messages, *args, **kwargs):
            evidence = json.loads(messages[1]["content"])["evidence"]
            return completion("merge", [item["id"] for item in evidence])
        with tracing_context(enabled=True, client=client), patch(
            "app.ai.coreference._load_coreference", new=AsyncMock(return_value=cache)
        ), patch("app.ai.entity_resolution.trace_content_mode", return_value="minimal"), patch(
            "app.ai.entity_resolution._completion", new=AsyncMock(side_effect=valid_completion)
        ), patch("app.queue.tasks.entity_resolution.MAX_CALLS_PER_RUN", 1):
            await run_resolution_job(job_id)
            await run_resolution_job(job_id)
        roots = [run for run in client.created if run["name"] == "entity_resolution_batch"]
        self.assertEqual(len(roots), 2)
        updates = {run["run_id"]: run for run in client.updated}
        first, second = (updates[root["id"]] for root in roots)
        for index, root in enumerate(roots, 1):
            self.assertIsNone(root.get("parent_run_id"))
            metadata = updates[root["id"]]["extra"]["metadata"]
            self.assertEqual((metadata["job_id"], metadata["batch_number"]), (str(job_id), index))
            self.assertGreaterEqual(updates[root["id"]]["outputs"]["duration_ms"], 0)
        out = first["outputs"]
        self.assertEqual((out["outcome"], out["end_reason"], out["continuation_queued"]), ("continuing", "call_budget", True))
        self.assertEqual((out["coreference_shortcuts"], out["gemma_attempts"], out["version_totals"]["merge_decisions_applied"]), (1, 1, 2))
        self.assertEqual((second["outputs"]["outcome"], second["outputs"]["version_totals"]["remaining"]), ("completed", 0))
        children = [run for run in client.created if run["name"] != "entity_resolution_batch"]
        self.assertEqual([run["name"] for run in children].count("entity_resolution"), 2)
        self.assertEqual([run["name"] for run in children].count("resolution_coreference"), 2)
        self.assertTrue(all(run["parent_run_id"] in {root["id"] for root in roots} for run in children))
        for run in children:
            final = updates[run["id"]]
            if run["name"] == "resolution_coreference":
                self.assertTrue(final["outputs"]["cache_hit"])
                self.assertEqual(final["outputs"]["source_scan_trace_id"], "coreference-test-trace")
            else:
                self.assertEqual(final["extra"]["metadata"]["batch_trace_id"], str(run["parent_run_id"]))
        self.assertNotIn(self.text, json.dumps(client.created + client.updated, default=str))
        async with SessionLocal() as session:
            candidates = await candidates_for(session, self.version_id)
            self.assertTrue(all(item.model_metadata["batch_trace_id"] in {str(root["id"]) for root in roots} for item in candidates))

    async def test_batch_tracing_outage_does_not_change_resolution(self):
        job_id = await self.start_job()
        with tracing_context(enabled=True, client=FakeTraceClient(fail=True)), patch(
            "app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=self.fake_resolve)
        ):
            await run_resolution_job(job_id)
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual((payload["job"]["status"], payload["applied_count"], payload["remaining"]), ("completed", 3, 0))

    async def test_retry_limit_survives_automatic_batch_boundaries(self):
        job_id = await self.start_job()
        calls = []
        async def unavailable(pair, client, **kwargs):
            calls.append((pair.left.id, pair.right.id))
            raise ConnectionError("private-provider-error")
        with patch("app.queue.tasks.entity_resolution.MAX_CALLS_PER_RUN", 1), patch(
            "app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=unavailable)
        ):
            for _ in range(7):  # Six attempts, then an extra delivery must do nothing.
                await run_resolution_job(job_id)
        self.assertEqual(len(calls), 6)
        self.assertEqual(len(set(calls[:3])), 3)
        self.assertEqual(set(calls[:3]), set(calls[3:]))
        self.assertEqual(self.dispatch.await_count, 5)
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual((payload["job"]["status"], payload["error_count"], payload["remaining"]), ("completed", 3, 0))
        self.assertTrue(all(item["attempt"] == 2 for item in payload["items"]))

    async def test_automatic_dispatch_failure_preserves_merges_and_can_resume(self):
        job_id = await self.start_job()
        self.dispatch.side_effect = ConnectionError("private-queue-error")
        trace_client = FakeTraceClient()
        with tracing_context(enabled=True, client=trace_client), patch("app.queue.tasks.entity_resolution.MAX_CALLS_PER_RUN", 1), patch(
            "app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=self.fake_resolve)
        ):
            await run_resolution_job(job_id)
        response = await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")
        payload = response.json()
        self.assertEqual((payload["job"]["status"], payload["job"]["error_code"], payload["applied_count"]), ("failed", "QUEUE_UNAVAILABLE", 1))
        self.assertNotIn("private-queue-error", response.text)
        traced = trace_client.updated[-1]
        self.assertEqual(traced["outputs"]["end_reason"], "QUEUE_UNAVAILABLE")
        self.assertEqual(traced["error"], "QUEUE_UNAVAILABLE")
        self.assertEqual(traced["outputs"]["version_totals"]["merge_decisions_applied"], 1)
        self.assertNotIn("private-queue-error", json.dumps(trace_client.created + trace_client.updated, default=str))
        self.assertEqual(await self.start_job(), job_id)
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=self.fake_resolve)) as model:
            await run_resolution_job(job_id)
        self.assertEqual(model.await_count, 2)

    async def test_late_automatic_dispatch_failure_cannot_overwrite_stop_and_resume(self):
        job_id = await self.start_job()
        async def stop_and_resume(*args):
            response = await self.client.post(
                f"/api/projects/{self.project_id}/entity-resolution/jobs/{job_id}/stop",
                json={"manuscript_version_id": str(self.version_id)},
            )
            self.assertEqual(response.json()["status"], "cancelled")
            # A delivered task after Stop must perform no more comparisons.
            await run_resolution_job(job_id)
            await self.start_job()
            raise ConnectionError("late-private-queue-error")
        self.dispatch.side_effect = stop_and_resume
        with patch("app.queue.tasks.entity_resolution.MAX_CALLS_PER_RUN", 1), patch(
            "app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=self.fake_resolve)
        ) as model:
            await run_resolution_job(job_id)
        model.assert_awaited_once()
        async with SessionLocal() as session:
            job = await session.get(JobRun, job_id)
            self.assertEqual((job.status, job.attempts), ("queued", 1))
            self.assertIsNone(job.error_code)
            self.assertIsNone(job.completed_at)

    async def test_timeout_continues_then_retries_and_preserves_audit(self):
        job_id = await self.start_job()
        calls = []
        async def fail_first(pair, client, **kwargs):
            calls.append((pair.left.id, pair.right.id))
            if len(calls) == 1:
                kwargs["diagnostics"]["trace_id"] = str(uuid.uuid4())
                raise TimeoutError("secret-provider-detail")
            return await self.fake_resolve(pair, client)
        trace_client = FakeTraceClient()
        with tracing_context(enabled=True, client=trace_client), patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=fail_first)):
            await run_resolution_job(job_id)
            async with SessionLocal() as session:
                self.assertEqual((await session.get(JobRun, job_id)).status, "queued")
            await run_resolution_job(job_id)
        batches = [item["outputs"] for item in trace_client.updated
                   if "gemma_attempts" in item.get("outputs", {})]
        self.assertEqual([(item["gemma_attempts"], item["retry_attempts"], item["failed_attempts"])
                          for item in batches], [(3, 0, 1), (1, 1, 0)])
        self.assertEqual(batches[-1]["version_totals"]["error_count"], 0)
        self.assertEqual(len(calls), 4)
        self.assertEqual(calls[0], calls[-1])
        self.assertEqual(len(set(calls[:3])), 3)
        self.dispatch.assert_awaited_once_with(str(job_id))
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual((payload["successful_count"], payload["applied_count"], payload["error_count"]), (3, 3, 0))
        async with SessionLocal() as session:
            events = list(await session.scalars(select(ResolutionDecision).where(
                ResolutionDecision.manuscript_version_id == self.version_id, ResolutionDecision.source == "model",
            ).order_by(ResolutionDecision.created_at)))
            self.assertEqual(len(events), 4)
            self.assertIsNone(events[0].decision)
            self.assertEqual(events[0].model_metadata["error_code"], "MODEL_TIMEOUT")
            self.assertIsNotNone(events[0].model_metadata["latency_ms"])
            self.assertIsNotNone(events[0].model_metadata["trace_id"])
            self.assertEqual(events[-1].attempt, 2)

    async def test_merge_is_committed_before_next_pair_and_survives_stop(self):
        job_id = await self.start_job()
        first_pair = None
        calls = 0
        async def stop_after_merge(pair, client, **kwargs):
            nonlocal first_pair, calls
            calls += 1
            if calls == 1:
                first_pair = {pair.left.id, pair.right.id}
                return await self.fake_resolve(pair, client)
            # Observe through a different API session while the worker is still running.
            payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
            self.assertEqual((payload["job"]["status"], payload["applied_count"]), ("running", 1))
            self.assertTrue(all({item["left"]["id"], item["right"]["id"]} != first_pair for item in payload["items"]))
            self.assertEqual(len((await self.client.get(f"/api/projects/{self.project_id}/characters")).json()), 2)
            response = await self.client.post(
                f"/api/projects/{self.project_id}/entity-resolution/jobs/{job_id}/stop",
                json={"manuscript_version_id": str(self.version_id)},
            )
            self.assertEqual(response.status_code, 200)
            return await self.fake_resolve(pair, client)  # Must be discarded after Stop.
        trace_client = FakeTraceClient()
        with tracing_context(enabled=True, client=trace_client), patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=stop_after_merge)):
            await run_resolution_job(job_id)
        traced = trace_client.updated[-1]["outputs"]
        self.assertEqual((traced["outcome"], traced["end_reason"], traced["gemma_attempts"]), ("stopped", "user_stopped", 2))
        self.assertEqual(traced["version_totals"]["merge_decisions_applied"], 1)
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual((calls, payload["job"]["status"], payload["applied_count"], payload["remaining"]), (2, "cancelled", 1, 2))
        async with SessionLocal() as session:
            events = list(await session.scalars(select(ResolutionDecision).where(
                ResolutionDecision.manuscript_version_id == self.version_id)))
            self.assertEqual(len(events), 2)
            self.assertEqual({event.source for event in events}, {"model", "automatic"})

    async def test_merge_survives_later_job_failure(self):
        job_id = await self.start_job()
        calls = 0
        async def fail_after_merge(pair, client, **kwargs):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise RuntimeError("unexpected worker failure")
            return await self.fake_resolve(pair, client)
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=fail_after_merge)):
            await run_resolution_job(job_id)
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual((payload["job"]["status"], payload["applied_count"]), ("failed", 1))

    async def test_later_separation_conflict_does_not_undo_committed_merges(self):
        job_id = await self.start_job()
        decisions = iter(["merge", "merge", "keep_separate"])
        async def conflicting(pair, client, **kwargs):
            result = await self.fake_resolve(pair, client)
            return replace(result, output=result.output.model_copy(update={"decision": next(decisions)}))
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=conflicting)):
            await run_resolution_job(job_id)
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual((payload["applied_count"], payload["review_count"]), (2, 1))
        self.assertEqual(payload["items"][0]["error_code"], "CLUSTER_CONFLICT")
        self.assertIsNone(payload["items"][0]["applied_decision"])
        self.assertEqual(len((await self.client.get(f"/api/projects/{self.project_id}/characters")).json()), 1)

    async def test_terminal_pair_error_does_not_block_other_automatic_merges(self):
        job_id = await self.start_job()
        calls = 0
        async def invalid_first(pair, client, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise EntityResolutionError("invalid after repair")
            return await self.fake_resolve(pair, client)
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=invalid_first)):
            await run_resolution_job(job_id)
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual(calls, 3)
        self.assertEqual((payload["applied_count"], payload["error_count"], payload["remaining"], payload["review_count"]), (2, 1, 0, 0))
        self.assertEqual(payload["job"]["stage"], "completed_with_errors")
        self.assertIsNone(payload["items"][0]["llm_decision"])

    async def test_http_errors_are_classified_without_exposing_provider_body(self):
        job_id = await self.start_job()
        statuses = iter([429, 503, 400])
        async def http_error(pair, client, **kwargs):
            status = next(statuses, None)
            if status:
                response = httpx.Response(status, request=httpx.Request("POST", "http://model"), text="private-provider-body")
                response.raise_for_status()
            return await self.fake_resolve(pair, client)
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=http_error)) as model:
            await run_resolution_job(job_id)
            async with SessionLocal() as session:
                self.assertEqual((await session.get(JobRun, job_id)).status, "queued")
            await run_resolution_job(job_id)
        self.assertEqual(model.await_count, 5)
        response = await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")
        self.assertNotIn("private-provider-body", response.text)
        payload = response.json()
        self.assertEqual((payload["successful_count"], payload["error_count"]), (2, 1))
        self.assertEqual((payload["items"][0]["error_code"], payload["items"][0]["http_status"]), ("MODEL_REQUEST_REJECTED", 400))
        async with SessionLocal() as session:
            events = list(await session.scalars(select(ResolutionDecision).where(
                ResolutionDecision.manuscript_version_id == self.version_id, ResolutionDecision.source == "model")))
            self.assertEqual({event.model_metadata["error_code"] for event in events if event.model_metadata["error_code"]},
                             {"MODEL_RATE_LIMITED", "MODEL_SERVER_ERROR", "MODEL_REQUEST_REJECTED"})

    async def test_legacy_failure_can_resume_without_repeating_human_decision(self):
        job_id = await self.start_job()
        async with SessionLocal() as session, session.begin():
            await prepare_candidates(session, self.version_id)
            candidates = await candidates_for(session, self.version_id)
            candidates[0].llm_decision, candidates[0].error_code = "needs_review", "MODEL_UNAVAILABLE"
            await apply_decision(session, candidates[1], "merge")
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=self.fake_resolve)) as model:
            await run_resolution_job(job_id)
        self.assertEqual(model.await_count, 2)
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual((payload["remaining"], payload["error_count"], payload["applied_count"]), (0, 0, 3))

    async def test_stop_queued_is_idempotent_scoped_and_resume_works(self):
        job_id = await self.start_job()
        path = f"/api/projects/{self.project_id}/entity-resolution/jobs/{job_id}/stop"
        body = {"manuscript_version_id": str(self.version_id)}
        self.assertEqual((await self.client.post(path.replace(str(self.project_id), str(self.other_id)), json=body)).status_code, 404)
        self.assertEqual((await self.client.post(path, json={"manuscript_version_id": str(self.old_version_id)})).status_code, 404)
        for _ in range(2):
            response = await self.client.post(path, json=body)
            self.assertEqual((response.status_code, response.json()["status"]), (200, "cancelled"))
        with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=self.fake_resolve)) as model:
            await run_resolution_job(job_id)
            model.assert_not_awaited()
            await self.start_job()
            await run_resolution_job(job_id)
        self.assertEqual(model.await_count, 3)
        self.assertEqual((await self.client.post(path, json=body)).status_code, 409)
        async with SessionLocal() as session:
            self.assertEqual((await session.get(ManuscriptVersion, self.version_id)).status, "ready")

    async def test_stop_during_inference_fences_late_result_after_resume(self):
        job_id = await self.start_job()
        entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
        async def late_model(pair, client, **kwargs):
            entered.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
                await release.wait()  # Simulate a provider finishing despite cancellation.
            return await self.fake_resolve(pair, client)
        with patch("app.queue.tasks.entity_resolution.CANCEL_POLL_SECONDS", .01), patch(
            "app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=late_model)
        ):
            old_worker = asyncio.create_task(run_resolution_job(job_id))
            try:
                await asyncio.wait_for(entered.wait(), 5)
                response = await self.client.post(
                    f"/api/projects/{self.project_id}/entity-resolution/jobs/{job_id}/stop",
                    json={"manuscript_version_id": str(self.version_id)},
                )
                self.assertEqual(response.status_code, 200)
                await asyncio.wait_for(cancelled.wait(), 5)
                await self.start_job()
                with patch("app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=self.fake_resolve)):
                    await run_resolution_job(job_id)
            finally:
                release.set()
                await asyncio.wait_for(old_worker, 5)
        async with SessionLocal() as session:
            job = await session.get(JobRun, job_id)
            self.assertEqual((job.status, job.attempts), ("completed", 2))
            events = list(await session.scalars(select(ResolutionDecision).where(
                ResolutionDecision.manuscript_version_id == self.version_id, ResolutionDecision.source == "model")))
            self.assertEqual(len(events), 3)
            self.assertTrue(all(event.model_metadata["run_attempt"] == 2 for event in events))

    async def test_late_queue_failure_cannot_undo_stop_or_resume(self):
        entered, release = asyncio.Event(), asyncio.Event()
        async def unavailable(*args, **kwargs):
            entered.set()
            await release.wait()
            raise ConnectionError("private-queue-error")
        with patch("app.api.entity_resolution.resolve_manuscript_entities.kiq", new=AsyncMock(side_effect=unavailable)):
            dispatch = asyncio.create_task(self.client.post(
                f"/api/projects/{self.project_id}/entity-resolution/run",
                json={"manuscript_version_id": str(self.version_id)},
            ))
            try:
                await asyncio.wait_for(entered.wait(), 5)
                async with SessionLocal() as session:
                    job_id = await session.scalar(select(JobRun.id).where(JobRun.project_id == self.project_id))
                response = await self.client.post(
                    f"/api/projects/{self.project_id}/entity-resolution/jobs/{job_id}/stop",
                    json={"manuscript_version_id": str(self.version_id)},
                )
                self.assertEqual(response.status_code, 200)
                await self.start_job()
            finally:
                release.set()
                response = await asyncio.wait_for(dispatch, 5)
        self.assertEqual((response.status_code, response.json()["status"]), (202, "queued"))
        async with SessionLocal() as session:
            self.assertIsNone((await session.get(JobRun, job_id)).error_code)

    @unittest.skipUnless(os.environ.get("RUN_SLOW_RESOLUTION_TESTS") == "1", "61-second deadline regression")
    async def test_pair_can_take_more_than_a_minute_and_outlive_batch_budget(self):
        job_id = await self.start_job()
        async def slow(pair, client, **kwargs):
            self.assertEqual(kwargs["request_timeout"], 180)
            self.assertEqual(client.timeout.read, 180)
            await asyncio.sleep(61)
            return await self.fake_resolve(pair, client)
        with patch("app.queue.tasks.entity_resolution.RUN_BUDGET_SECONDS", 1), patch(
            "app.queue.tasks.entity_resolution.resolve_pair", new=AsyncMock(side_effect=slow)
        ) as model:
            await run_resolution_job(job_id)
        model.assert_awaited_once()
        payload = (await self.client.get(f"/api/projects/{self.project_id}/entity-resolution/candidates")).json()
        self.assertEqual((payload["successful_count"], payload["error_count"], payload["remaining"]), (1, 0, 2))
        self.assertEqual(payload["job"]["status"], "queued")
