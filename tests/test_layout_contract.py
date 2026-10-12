"""Check the layout/import contract independently of business implementation."""

import ast
import contextlib
import io
import unittest
from unittest.mock import patch

from scripts import selftest


class LayoutContractTests(unittest.TestCase):
    def test_absolute_from_import_resolves_children(self) -> None:
        node = ast.parse("from packages import app").body[0]
        path = selftest.REPO / "packages/core/models.py"
        self.assertIn("packages.app", selftest._imported_modules(node, path))

    def test_relative_import_in_module_resolves_sibling(self) -> None:
        node = ast.parse("from ..app import cli").body[0]
        path = selftest.REPO / "packages/core/models.py"
        self.assertIn("packages.app", selftest._imported_modules(node, path))

    def test_relative_import_in_package_init_resolves_sibling(self) -> None:
        node = ast.parse("from .. import llm").body[0]
        path = selftest.REPO / "packages/core/__init__.py"
        self.assertIn("packages.llm", selftest._imported_modules(node, path))

    def test_valid_default_stage_has_no_layout_failures(self) -> None:
        with patch.object(selftest, "results", []):
            selftest.check_layout("V1")
            failures = [r for r in selftest.results if r[0] == "FAIL"]
        self.assertEqual(failures, [])

    def test_main_resets_results_between_invocations(self) -> None:
        with (
            patch.object(selftest, "results", []),
            patch("sys.argv", ["selftest", "--stage", "V1"]),
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                first_code = selftest.main()
                first_count = len(selftest.results)
                second_code = selftest.main()
            self.assertEqual(first_code, 0)
            self.assertEqual(second_code, 0)
            self.assertEqual(len(selftest.results), first_count)


if __name__ == "__main__":
    unittest.main()
