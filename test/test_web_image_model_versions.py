from __future__ import annotations

import json
import unittest
from unittest import mock

from services.config import config
from services.openai_backend_api import ChatRequirements
from services.protocol import conversation
from test import test_image_model_versions as codex_tests
from utils.helper import VERSIONED_IMAGE_MODELS


class WebImageModelInterfaceTests(unittest.TestCase):
    def setUp(self):
        codex_tests.ImageModelInterfaceTests.setUp(self)
        self.web_sent = []
        self.prepare_reply = {"status": "ok", "conduit_token": None}
        self.reported_model = None
        self.accounts.get_account.return_value = {"type": "free", "source_type": "web"}
        self.backend.progress_callback = None
        self.backend._bootstrap = mock.Mock()
        self.backend._get_chat_requirements = mock.Mock(return_value=ChatRequirements(
            "fixture-requirements", proof_token="fixture-proof", turnstile_token="fixture-turnstile", so_token="fixture-so",
        ))
        self.backend._headers = lambda _path, extra=None: extra or {}
        self.backend._upload_image = mock.Mock(return_value={
            "file_id": "file-input", "width": 32, "height": 32, "file_size": 128,
            "mime_type": "image/png", "file_name": "reference.png",
        })
        self.backend.resolve_conversation_image_urls = mock.Mock(return_value=["https://test/image.png"])
        self.backend.download_image_bytes = mock.Mock(return_value=[b"image-bytes"])

        def post(url, **kwargs):
            self.web_sent.append((url, kwargs))
            response = mock.Mock(status_code=200)
            if url.endswith("/prepare"):
                response.json.return_value = self.prepare_reply
            else:
                # Contract fixture: explicit model, null conduit and image tool result.
                event = {"v": {"conversation_id": "fixture-conversation", "message": {
                    "author": {"role": "tool"},
                    "metadata": {"async_task_type": "image_gen", "model_slug": self.reported_model or kwargs["json"]["model"]},
                    "content": {"content_type": "multimodal_text", "parts": [
                        {"content_type": "image_asset_pointer", "asset_pointer": "file-service://file-output"}
                    ]},
                }}}
                response.iter_lines.return_value = [f"data: {json.dumps(event)}", "data: [DONE]"]
            return response

        self.backend.session = mock.Mock()
        self.backend.session.post.side_effect = post
        patcher = mock.patch.dict(config.data, {
            "image_remove_conversation_after_result": False,
            "image_remove_conversation_always": False,
        })
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_standard_models_use_web_accounts_and_exact_model_without_conduit(self):
        for model in sorted(VERSIONED_IMAGE_MODELS):
            for stream in (False, True):
                with self.subTest(model=model, stream=stream):
                    response = self.client.post("/v1/images/generations", json={
                        "model": model, "prompt": "draw", "quality": "max", "stream": stream,
                    })
                    self.assertEqual(response.status_code, 200, response.text)
                    prepare, generate = self.web_sent[-2:]
                    self.assertTrue(prepare[0].endswith("/backend-api/f/conversation/prepare"))
                    self.assertTrue(generate[0].endswith("/backend-api/f/conversation"))
                    self.assertEqual(prepare[1]["json"]["model"], model)
                    self.assertEqual(generate[1]["json"]["model"], model)
                    self.assertNotIn("X-Conduit-Token", generate[1]["headers"])
                    for _, call in (prepare, generate):
                        self.assertEqual(call["headers"]["OpenAI-Sentinel-Turnstile-Token"], "fixture-turnstile")
                        self.assertEqual(call["headers"]["OpenAI-Sentinel-SO-Token"], "fixture-so")
                    self.assertEqual(generate[1]["json"]["system_hints"], ["picture_v2"])
                    self.assertEqual(self.accounts.get_available_access_token.call_args.kwargs["source_type"], "web")
                    if not stream:
                        self.assertEqual(response.json()["_actual_model"], model)
                        self.assertEqual(len(response.json()["data"]), 1)
                        self.assertNotIn("usage", response.json())
                    else:
                        self.assertIn(f'"_actual_model": "{model}"', response.text)
        self.assertEqual(self.sent, [])
        self.backend._ensure_codex_source_account.assert_not_called()

    def test_web_edits_keep_references_and_express_options_as_prompt_hints(self):
        for form in (False, True):
            body = {"model": codex_tests.MODEL, "prompt": "edit", "quality": "xhigh", "complexity": "low", "size": "1536x1024"}
            if form:
                response = self.client.post("/v1/images/edits", data=body, files={"image": ("input.png", b"image", "image/png")})
            else:
                response = self.client.post("/v1/images/edits", json={**body, "image": f"data:image/png;base64,{codex_tests.IMAGE}"})
            self.assertEqual(response.status_code, 200, response.text)
            payload = self.web_sent[-1][1]["json"]
            parts = payload["messages"][0]["content"]["parts"]
            self.assertEqual(parts[0]["asset_pointer"], "file-service://file-input")
            self.assertIn("1536x1024", parts[-1])
            self.assertIn("xhigh", parts[-1])
            self.assertIn("low", parts[-1])
            self.assertNotIn("complexity", payload)
            self.assertEqual(payload["model"], codex_tests.MODEL)

    def test_web_chat_and_responses_route_standard_image_models(self):
        for stream in (False, True):
            for endpoint, body in [
                ("/v1/chat/completions", {"model": codex_tests.MODEL, "messages": [{"role": "user", "content": "draw"}]}),
                ("/v1/responses", {"model": "gpt-5.5", "input": "draw", "tools": [{"type": "image_generation", "model": codex_tests.MODEL}]}),
            ]:
                with self.subTest(endpoint=endpoint, stream=stream):
                    response = self.client.post(endpoint, json={**body, "stream": stream})
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(self.web_sent[-1][1]["json"]["model"], codex_tests.MODEL)
        self.assertEqual(self.sent, [])

    def test_prepare_errors_are_not_treated_as_optional_token(self):
        for reply in ({"status": "error", "conduit_token": None}, {"status": "ok"},
                      {"status": "ok", "conduit_token": 1}, {"status": "ok", "conduit_token": None, "error": "denied"}):
            with self.subTest(reply=reply):
                self.prepare_reply = reply
                self.web_sent.clear()
                response = self.client.post("/v1/images/generations", json={"model": codex_tests.MODEL, "prompt": "draw"})
                self.assertGreaterEqual(response.status_code, 400)
                self.assertEqual(len(self.web_sent), 1)
        self.backend.download_image_bytes.assert_not_called()

    def test_reported_model_mismatch_fails_without_codex_fallback(self):
        self.reported_model = "gpt-image-2"
        response = self.client.post("/v1/images/generations", json={"model": codex_tests.MODEL, "prompt": "draw"})
        self.assertEqual(response.status_code, 502, response.text)
        self.assertEqual(response.json()["error"]["code"], "model_mismatch")
        self.assertEqual(len(self.web_sent), 2)
        self.assertEqual(self.sent, [])
        self.backend.download_image_bytes.assert_not_called()

    def test_model_slug_patch_is_preserved(self):
        events = list(conversation.iter_conversation_payloads(iter([
            json.dumps({"p": "/message/metadata/model_slug", "o": "add", "v": codex_tests.MODEL}), "[DONE]",
        ])))
        self.assertEqual(events[-1]["model_slug"], codex_tests.MODEL)


if __name__ == "__main__":
    unittest.main()
