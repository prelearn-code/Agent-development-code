"""Entry adapter tests; no model, crypto operation, or Agent Loop is implemented here."""

import contextlib
import io
import json
import unittest
from unittest.mock import patch

from packages.app import cli


class EntryTests(unittest.TestCase):
    def invoke(self, args: list[str]) -> tuple[int, dict[str, object]]:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = cli.main(args)
        return code, json.loads(output.getvalue())

    def test_status_does_not_import_the_learner_or_use_the_network(self) -> None:
        with patch.object(cli, "_load_runner", side_effect=AssertionError("Unexpected import")):
            code, result = self.invoke(["status"])
        self.assertEqual(code, 0)
        self.assertTrue(result["entry_ready"])
        self.assertFalse(result["business_verified"])
        self.assertEqual(result["network_requests"], 0)

    def test_missing_learner_is_explicit_and_not_a_success(self) -> None:
        missing = ModuleNotFoundError(name=cli.LEARNER_MODULE)
        with patch.object(cli, "_load_runner", side_effect=missing):
            code, result = self.invoke(["run", "--question", "检查教学证书"])
        self.assertEqual(code, 2)
        self.assertEqual(result["error"], "learner_entry_missing")

    def test_missing_dependency_is_distinct_from_missing_runner(self) -> None:
        with patch.object(cli, "_load_runner", side_effect=ModuleNotFoundError(name="dependency")):
            code, result = self.invoke(["run", "--question", "检查教学证书"])
        self.assertEqual(code, 3)
        self.assertEqual(result["error"], "learner_dependency_missing")

    def test_missing_learner_package_is_reported_as_missing_entry(self) -> None:
        with patch.object(
            cli, "_load_runner", side_effect=ModuleNotFoundError(name="minimal_agent")
        ):
            code, result = self.invoke(["run", "--question", "检查教学证书"])
        self.assertEqual(code, 2)
        self.assertEqual(result["error"], "learner_entry_missing")

    def test_one_invocation_passes_question_and_preserves_result(self) -> None:
        seen: list[str] = []

        async def stub(*, question: str) -> dict[str, object]:
            seen.append(question)
            return {"status": "completed", "answer": "教学测试响应"}

        with patch.object(cli, "_load_runner", return_value=stub):
            code, result = self.invoke(["run", "--question", "检查教学证书"])
        self.assertEqual(code, 0)
        self.assertEqual(seen, ["检查教学证书"])
        self.assertEqual(result, {"status": "completed", "answer": "教学测试响应"})

    def test_entry_failure_does_not_print_raw_exception(self) -> None:
        async def stub(*, question: str) -> dict[str, object]:
            raise RuntimeError("private diagnostic value")

        with patch.object(cli, "_load_runner", return_value=stub):
            code, result = self.invoke(["run", "--question", "检查教学证书"])
        self.assertEqual(code, 3)
        self.assertEqual(result, {"error": "learner_execution_failed"})

    def test_non_json_result_is_rejected(self) -> None:
        async def stub(*, question: str) -> dict[str, object]:
            return {"value": float("nan")}

        with patch.object(cli, "_load_runner", return_value=stub):
            code, result = self.invoke(["run", "--question", "检查教学证书"])
        self.assertEqual(code, 3)
        self.assertEqual(result["error"], "learner_execution_failed")

    def test_sync_hook_is_rejected(self) -> None:
        class StubModule:
            @staticmethod
            def run(*, question: str) -> dict[str, object]:
                return {}

        with patch.object(cli.importlib, "import_module", return_value=StubModule):
            code, result = self.invoke(["run", "--question", "检查教学证书"])
        self.assertEqual(code, 3)
        self.assertEqual(result["error"], "learner_entry_load_failed")


if __name__ == "__main__":
    unittest.main()
