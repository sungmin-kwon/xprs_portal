from __future__ import annotations

import unittest
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "static"


def read_repo(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def read_static(filename: str) -> str:
    return (STATIC / filename).read_text(encoding="utf-8")


class ContractTestCase(unittest.TestCase):
    """Run related source contracts as labeled subtests."""

    def run_contract_checks(self, method_names: Iterable[str]) -> None:
        for method_name in method_names:
            with self.subTest(contract=method_name.removeprefix("_check_")):
                getattr(self, method_name)()
