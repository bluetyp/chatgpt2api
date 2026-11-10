"""Run the isolated regression suite without a live ChatGPT account or local API server."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ["CHATGPT2API_AUTH_KEY"] = "chatgpt2api"

from services.config import config

TESTS = [
    "test.test_image_model_versions",
    "test.test_web_image_model_versions",
    "test.test_account_image_capabilities",
    "test.test_multi_image_results",
    "test.test_image_output_tokens",
    "test.test_image_tokens",
    "test.test_text_model_routing",
    "test.test_model_catalog_service",
    "test.test_image_task_service",
    "test.test_image_tasks_api",
    "test.test_v1_images_edits_api",
    "test.test_image_base_url_api",
    "test.test_v1_models.ModelListTests.test_list_models_only_returns_image_models_backed_by_account_types",
    "test.test_v1_models.ModelListTests.test_list_models_does_not_return_codex_models_for_web_plus_accounts",
]


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromNames(TESTS)
    with (
        patch.dict(config.data, {"image_settle_enabled": True, "image_check_before_hit_enabled": True}),
        patch("services.openai_backend_api.logger"),
        patch("services.protocol.conversation.logger"),
    ):
        result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
