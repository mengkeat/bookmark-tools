from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evals.datasets.e2e.schema import load_dataset


class E2ECaseSchemaTest(unittest.TestCase):
    def test_loads_mapping_dataset(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.yaml"
            path.write_text(
                """
cases:
  - id: example
    url: https://example.com/
    html: <html><title>Example Domain</title></html>
    expected_folder: Development
    expected_type: article
    expected_tags: [development, example]
    retrieval_queries:
      - query: example domain
        must_be_in_top_k: 5
""".strip(),
                encoding="utf-8",
            )

            dataset = load_dataset(path)

        self.assertEqual(len(dataset.cases), 1)
        case = dataset.cases[0]
        self.assertEqual(case.case_id, "example")
        self.assertEqual(case.url, "https://example.com/")
        self.assertIn("Example Domain", case.html)
        self.assertEqual(case.expected_tags, frozenset({"development", "example"}))
        self.assertEqual(len(case.retrieval_queries), 1)
        self.assertEqual(case.retrieval_queries[0].must_be_in_top_k, 5)

    def test_loads_top_level_list_dataset(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.yaml"
            path.write_text(
                """
- id: example
  url: https://example.com/
  expected_folder: Development
  expected_type: article
  expected_tags: [development]
  retrieval_queries:
    - query: example
""".strip(),
                encoding="utf-8",
            )

            dataset = load_dataset(path)

        self.assertEqual(len(dataset.cases), 1)
        self.assertEqual(dataset.cases[0].retrieval_queries[0].must_be_in_top_k, 5)

    def test_rejects_invalid_top_k(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.yaml"
            path.write_text(
                """
cases:
  - id: bad
    url: https://example.com/
    expected_folder: Development
    expected_type: article
    expected_tags: [development]
    retrieval_queries:
      - query: example
        must_be_in_top_k: 0
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_dataset(path)


if __name__ == "__main__":
    unittest.main()
