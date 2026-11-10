from __future__ import annotations

import base64
import json
import tempfile
import unittest
import urllib.error
from io import BytesIO
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import ai
from api.errors import install_exception_handlers
from services import openai_backend_api
from services.config import config
from services.account_service import AccountService
from services.image_task_service import ImageTaskService
from services.protocol import conversation, openai_v1_models
from utils.helper import VERSIONED_IMAGE_MODELS, image_tool_model, is_codex_image_model, split_image_model


IMAGE = base64.b64encode(b"test-image-bytes").decode()
MODEL = "gpt-image-2.6-flare"
CODEX_MODEL = "codex-" + MODEL
USAGE = {"input_tokens": 7, "output_tokens": 11, "input_tokens_details": {"text_tokens": 3, "image_tokens": 4}}


class ImageModelInterfaceTests(unittest.TestCase):
    """Exercise HTTP adapters, account routing and the actual upstream request builder offline."""

    def setUp(self):
        self.sent = []
        self.tool_usage = dict(USAGE)
        self.backend = openai_backend_api.OpenAIBackendAPI.__new__(openai_backend_api.OpenAIBackendAPI)
        self.backend.access_token = "test-token"
        self.backend.base_url = "https://chatgpt.com"
        self.backend.close = mock.Mock()
        self.backend._ensure_codex_source_account = mock.Mock()
        self.backend._codex_responses_headers = lambda: {"Content-Type": "application/json"}
        self.accounts = mock.Mock()
        self.accounts.get_account.return_value = {"type": "Team", "source_type": "codex"}
        self.accounts.get_available_access_token.return_value = "test-token"
        self.accounts._decode_jwt_payload.return_value = {}

        def urlopen(request, **_kwargs):
            payload = json.loads(request.data)
            self.sent.append(payload)
            item = {"id": "ig-one", "type": "image_generation_call", "result": IMAGE}
            if self.tool_usage is not None:
                item["usage"] = self.tool_usage
            events = [
                {"type": "response.output_item.done", "item": item},
                {"type": "response.completed", "response": {"output": [item]}},
            ]
            raw = mock.MagicMock()
            raw.headers = {"content-type": "text/event-stream"}
            raw.status = 200
            raw.read.return_value = "".join(f"data: {json.dumps(event)}\n\n" for event in events).encode()
            raw.__enter__.return_value = raw
            return raw

        patches = [
            mock.patch.object(conversation, "account_service", self.accounts),
            mock.patch.object(openai_backend_api, "account_service", self.accounts),
            mock.patch.object(conversation, "OpenAIBackendAPI", return_value=self.backend),
            mock.patch.object(openai_backend_api.urllib.request, "urlopen", side_effect=urlopen),
            mock.patch.object(conversation, "save_image_bytes", return_value="http://test/image.png"),
            mock.patch.object(conversation, "encoding_for_model", return_value=mock.Mock(encode=lambda text: list(text.encode()))),
            mock.patch.object(ai, "require_identity", return_value={"id": "test", "role": "admin"}),
            mock.patch.object(ai, "check_request"),
            mock.patch.object(ai.LoggedCall, "log"),
            mock.patch.object(openai_backend_api, "logger"),
            mock.patch.object(conversation, "logger"),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)
        app = FastAPI()
        install_exception_handlers(app)
        app.include_router(ai.create_router())
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_generations_keep_every_model_and_quality_in_upstream_tool(self):
        for model in sorted(VERSIONED_IMAGE_MODELS):
            for prefix in ("codex-", "team-codex-"):
                with self.subTest(model=model, prefix=prefix):
                    response = self.client.post("/v1/images/generations", json={
                        "model": prefix + model, "prompt": "draw", "quality": "max", "size": "1536x1024",
                    })
                    self.assertEqual(response.status_code, 200, response.text)
                    result = response.json()
                    self.assertEqual(len(result["data"]), 1)
                    self.assertEqual(result["usage"]["output_tokens"], 11)
                    self.assertEqual(result["usage"]["total_tokens"], 18)
                    self.assertEqual(self.sent[-1]["tools"][0], {
                        "type": "image_generation", "model": model, "action": "generate",
                        "size": "1536x1024", "quality": "max", "output_format": "png",
                    })
                    selection = self.accounts.get_available_access_token.call_args.kwargs
                    self.assertEqual(selection["source_type"], "codex")
                    self.assertEqual(selection["plan_type"], "team" if prefix.startswith("team-") else None)

    def test_json_and_multipart_edits_keep_image_model_and_complexity(self):
        requests = [
            {"json": {"model": CODEX_MODEL, "prompt": "edit", "quality": "xhigh", "complexity": "low",
                      "image": f"data:image/png;base64,{IMAGE}"}},
            {"data": {"model": CODEX_MODEL, "prompt": "edit", "quality": "xhigh", "complexity": "low"},
             "files": {"image": ("input.png", b"test-image-bytes", "image/png")}},
        ]
        for request in requests:
            with self.subTest(request_type=next(iter(request))):
                response = self.client.post("/v1/images/edits", **request)
                self.assertEqual(response.status_code, 200, response.text)
                tool = self.sent[-1]["tools"][0]
                self.assertEqual((tool["model"], tool["action"], tool["quality"], tool["complexity"]),
                                 (MODEL, "edit", "xhigh", "low"))
                self.assertEqual(self.sent[-1]["input"][0]["content"][1]["type"], "input_image")

    def test_responses_tool_model_wins_over_conversational_model(self):
        for stream in (False, True):
            response = self.client.post("/v1/responses", json={
                "model": "gpt-5.5", "input": "draw", "stream": stream,
                "tools": [{"type": "image_generation", "model": CODEX_MODEL, "quality": "max", "complexity": "medium"}],
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.sent[-1]["tools"][0]["model"], MODEL)
            self.assertEqual(self.sent[-1]["tools"][0]["complexity"], "medium")
            if not stream:
                self.assertEqual(response.json()["model"], "gpt-5.5")
                self.assertEqual(len(response.json()["output"]), 1)
                self.assertEqual(response.json()["usage"]["output_tokens"], 11)
            else:
                self.assertIn('"type": "response.completed"', response.text)

    def test_responses_accepts_image_model_without_tool(self):
        response = self.client.post("/v1/responses", json={"model": CODEX_MODEL, "input": "draw"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.sent[-1]["tools"][0]["model"], MODEL)

    def test_chat_stream_and_nonstream_pass_image_settings(self):
        for stream in (False, True):
            response = self.client.post("/v1/chat/completions", json={
                "model": CODEX_MODEL, "messages": [{"role": "user", "content": "draw"}],
                "quality": "xhigh", "complexity": "high", "size": "1024x1536", "stream": stream,
            })
            self.assertEqual(response.status_code, 200, response.text)
            tool = self.sent[-1]["tools"][0]
            self.assertEqual((tool["model"], tool["quality"], tool["complexity"], tool["size"]),
                             (MODEL, "xhigh", "high", "1024x1536"))

    def test_generation_stream_deduplicates_result_and_preserves_usage(self):
        response = self.client.post("/v1/images/generations", json={
            "model": CODEX_MODEL, "prompt": "draw", "stream": True,
        })
        self.assertEqual(response.status_code, 200)
        chunks = [json.loads(line[6:]) for line in response.text.splitlines()
                  if line.startswith("data: ") and line != "data: [DONE]"]
        results = [chunk for chunk in chunks if chunk.get("object") == "image.generation.result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(len(results[0]["data"]), 1)
        self.assertEqual(results[0]["usage"]["output_tokens"], 11)

    def test_missing_new_model_usage_is_not_estimated_using_old_model(self):
        self.tool_usage = None
        for endpoint, body in [
            ("/v1/images/generations", {"prompt": "draw"}),
            ("/v1/chat/completions", {"messages": [{"role": "user", "content": "draw"}]}),
            ("/v1/responses", {"input": "draw"}),
        ]:
            with self.subTest(endpoint=endpoint):
                response = self.client.post(endpoint, json={"model": CODEX_MODEL, **body})
                self.assertEqual(response.status_code, 200, response.text)
                self.assertNotIn("usage", response.json())

    def test_invalid_model_and_options_fail_before_selecting_account(self):
        for model, options, param in [
            ("gpt-image-2.6", {}, "model"),
            ("gpt-image-2.7-flare", {}, "model"),
            ("gpt-image-2", {"quality": "max"}, "quality"),
            (MODEL, {"quality": "ultra"}, "quality"),
            ("gpt-image-2.5-flare", {"complexity": "low"}, "complexity"),
            (MODEL, {"complexity": "invalid"}, "complexity"),
        ]:
            with self.subTest(model=model, options=options):
                response = self.client.post("/v1/images/generations", json={"model": model, "prompt": "draw", **options})
                self.assertEqual(response.status_code, 400, response.text)
                self.assertEqual(response.json()["error"]["param"], param)
        self.accounts.get_available_access_token.assert_not_called()
        self.assertEqual(self.sent, [])

    def test_upstream_model_rejection_does_not_fall_back(self):
        error = urllib.error.HTTPError("https://chatgpt.com", 400, "bad request", {},
                                      BytesIO(b'{"error":{"code":"model_not_found"}}'))
        with mock.patch.object(openai_backend_api.urllib.request, "urlopen", side_effect=error) as transport:
            response = self.client.post("/v1/images/generations", json={"model": CODEX_MODEL, "prompt": "draw"})
        self.assertGreaterEqual(response.status_code, 400)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(json.loads(transport.call_args.args[0].data)["tools"][0]["model"], MODEL)

    def test_legacy_codex_model_still_targets_image_2(self):
        response = self.client.post("/v1/images/generations", json={"model": "codex-gpt-image-2", "prompt": "draw"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.sent[-1]["tools"][0]["model"], "gpt-image-2")

    def test_multiple_generations_sum_usage_without_dropping_identical_images(self):
        with mock.patch.dict(config.data, {"image_parallel_generation": False}):
            response = self.client.post("/v1/images/generations", json={"model": CODEX_MODEL, "prompt": "draw", "n": 2})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(len(response.json()["data"]), 2)
        self.assertEqual(response.json()["usage"]["output_tokens"], 22)
        self.assertEqual(response.json()["usage"]["total_tokens"], 36)

    def test_legacy_web_model_still_uses_web_stream(self):
        output = conversation.ImageOutput(kind="result", model="gpt-image-2", index=1, total=1,
                                          data=[{"b64_json": IMAGE}])
        with mock.patch.object(conversation, "stream_image_outputs", return_value=iter([output])) as web_stream:
            response = self.client.post("/v1/images/generations", json={"model": "gpt-image-2", "prompt": "draw"})
        self.assertEqual(response.status_code, 200, response.text)
        web_stream.assert_called_once()
        self.assertEqual(self.sent, [])
        self.assertIsNone(self.accounts.get_available_access_token.call_args.kwargs["source_type"])


class ImageModelCatalogTests(unittest.TestCase):
    def test_aliases_keep_exact_tool_version_and_plan(self):
        for model in VERSIONED_IMAGE_MODELS:
            self.assertFalse(is_codex_image_model(model))
            self.assertTrue(is_codex_image_model("codex-" + model))
            self.assertEqual(image_tool_model("pro-codex-" + model), model)
            self.assertEqual(split_image_model("pro-codex-" + model), ("pro", "codex-" + model))
        self.assertFalse(is_codex_image_model("gpt-image-2"))
        self.assertEqual(split_image_model("plus-gpt-image-2"), (None, None))

    def test_catalog_separates_web_and_paid_codex_models(self):
        for source, plan, status, web, codex in [
            ("web", "Plus", "正常", True, False), ("password", "free", "正常", True, False),
            ("web", "free", "禁用", False, False), ("codex", "free", "正常", False, False),
            ("codex", "Team", "禁用", False, False), ("codex", "Pro", "异常", False, False),
            ("codex", "Team", "正常", False, True),
        ]:
            with (
                self.subTest(source=source, plan=plan, status=status),
                mock.patch.object(openai_v1_models.model_catalog_service, "list_models", return_value={"object": "list", "data": []}),
                mock.patch.object(openai_v1_models.account_service, "list_accounts", return_value=[
                    {"access_token": "test-token", "source_type": source, "type": plan, "status": status}
                ]),
            ):
                ids = {item["id"] for item in openai_v1_models.list_models()["data"]}
                self.assertEqual(MODEL in ids, web)
                self.assertEqual("team-codex-" + MODEL in ids, codex)

    def test_web_account_filter_accepts_password_login_and_rejects_codex(self):
        for source in (None, "web", "password"):
            self.assertTrue(AccountService._account_matches_source_type({"source_type": source}, "web"))
        self.assertFalse(AccountService._account_matches_source_type({"source_type": "codex"}, "web"))
        self.assertFalse(AccountService._account_matches_source_type({"source_type": "web"}, "codex"))

    def test_task_service_preserves_complexity_and_model(self):
        with tempfile.TemporaryDirectory() as directory:
            service = ImageTaskService(Path(directory) / "tasks.json")
            with mock.patch("services.image_task_service.threading.Thread") as thread:
                result = service.submit_generation({"id": "test", "role": "admin"}, client_task_id="one",
                                                   prompt="draw", model=MODEL, size=None, quality="max", complexity="low")
            self.assertEqual(result["complexity"], "low")
            payload = thread.call_args.kwargs["args"][2]
            self.assertEqual((payload["model"], payload["quality"], payload["complexity"]), (MODEL, "max", "low"))
            restored = ImageTaskService(Path(directory) / "tasks.json")
            self.assertEqual(next(iter(restored._tasks.values()))["complexity"], "low")


if __name__ == "__main__":
    unittest.main()
