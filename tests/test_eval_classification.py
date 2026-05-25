from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from evals.datasets.classification.schema import load_dataset
from evals.runners.classification import (
    aggregate_classification_metrics,
    score_classification_prediction,
)


class ClassificationFixtureSchemaTest(unittest.TestCase):
    def test_loads_mapping_dataset_with_content_or_url(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixtures.yaml"
            path.write_text(
                """
profile_folders:
  - Development
profile_notes:
  - title: Existing Python Note
    folder: Development
    tags: [python]
cases:
  - id: python-cli
    content_or_url: Python command line tools
    expected_folder: Development
    expected_type: article
    expected_tags: [development, python]
""".strip(),
                encoding="utf-8",
            )

            dataset = load_dataset(path)

        self.assertEqual(dataset.profile_folders, ("Development",))
        self.assertEqual(len(dataset.profile_notes), 1)
        self.assertEqual(len(dataset.cases), 1)
        case = dataset.cases[0]
        self.assertEqual(case.case_id, "python-cli")
        self.assertEqual(case.content, "Python command line tools")
        self.assertEqual(case.expected_tags, frozenset({"development", "python"}))

    def test_loads_top_level_list_dataset(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixtures.yaml"
            path.write_text(
                """
- id: url-case
  content_or_url: https://example.com/page
  expected_folder: Development
  expected_type: article
  expected_tags: [development]
""".strip(),
                encoding="utf-8",
            )

            dataset = load_dataset(path)

        self.assertEqual(len(dataset.cases), 1)
        self.assertEqual(dataset.cases[0].url, "https://example.com/page")

    def test_rejects_case_without_source(self) -> None:
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "fixtures.yaml"
            path.write_text(
                """
cases:
  - id: missing-source
    expected_folder: Development
    expected_type: article
    expected_tags: [development]
""".strip(),
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                load_dataset(path)


class ClassificationScoringTest(unittest.TestCase):
    def test_scores_exact_folder_type_and_tag_overlap(self) -> None:
        score = score_classification_prediction(
            predicted_folder="Development",
            predicted_type="article",
            predicted_tags={"development", "python", "cli"},
            expected_folder="Development",
            expected_type="article",
            expected_tags={"development", "python"},
        )

        self.assertEqual(score["folder_accuracy"], 1.0)
        self.assertEqual(score["type_accuracy"], 1.0)
        self.assertAlmostEqual(score["tag_precision"], 2 / 3)
        self.assertAlmostEqual(score["tag_recall"], 1.0)
        self.assertAlmostEqual(score["tag_f1"], 0.8)

    def test_aggregates_scores(self) -> None:
        metrics = aggregate_classification_metrics(
            [
                {
                    "folder_accuracy": 1.0,
                    "type_accuracy": 1.0,
                    "tag_precision": 1.0,
                    "tag_recall": 0.5,
                    "tag_f1": 2 / 3,
                },
                {
                    "folder_accuracy": 0.0,
                    "type_accuracy": 1.0,
                    "tag_precision": 0.0,
                    "tag_recall": 0.0,
                    "tag_f1": 0.0,
                },
            ]
        )

        self.assertAlmostEqual(metrics["folder_accuracy"], 0.5)
        self.assertAlmostEqual(metrics["type_accuracy"], 1.0)
        self.assertAlmostEqual(metrics["tag_precision"], 0.5)


if __name__ == "__main__":
    unittest.main()
