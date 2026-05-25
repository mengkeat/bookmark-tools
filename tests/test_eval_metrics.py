from __future__ import annotations

import math
import unittest

from evals.metrics import (
    aggregate_metrics,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    score_query,
)


class PrecisionAtKTest(unittest.TestCase):
    def test_all_relevant(self) -> None:
        ranked = ["a", "b", "c"]
        self.assertAlmostEqual(precision_at_k(ranked, {"a", "b", "c"}, 3), 1.0)

    def test_none_relevant(self) -> None:
        self.assertAlmostEqual(precision_at_k(["a", "b"], {"x"}, 2), 0.0)

    def test_half_relevant(self) -> None:
        self.assertAlmostEqual(precision_at_k(["a", "b", "c", "d"], {"a", "c"}, 4), 0.5)

    def test_k_larger_than_list(self) -> None:
        # Only 2 results returned but k=5; missing slots count as irrelevant
        self.assertAlmostEqual(precision_at_k(["a", "b"], {"a"}, 5), 0.2)

    def test_k_zero(self) -> None:
        self.assertAlmostEqual(precision_at_k(["a"], {"a"}, 0), 0.0)

    def test_truncates_to_k(self) -> None:
        # Third result "c" is relevant but outside k=2
        self.assertAlmostEqual(precision_at_k(["a", "b", "c"], {"c"}, 2), 0.0)


class RecallAtKTest(unittest.TestCase):
    def test_all_found(self) -> None:
        self.assertAlmostEqual(recall_at_k(["a", "b"], {"a", "b"}, 2), 1.0)

    def test_none_found(self) -> None:
        self.assertAlmostEqual(recall_at_k(["x", "y"], {"a", "b"}, 2), 0.0)

    def test_partial(self) -> None:
        self.assertAlmostEqual(recall_at_k(["a", "x"], {"a", "b"}, 2), 0.5)

    def test_empty_relevant(self) -> None:
        self.assertAlmostEqual(recall_at_k(["a", "b"], set(), 5), 0.0)


class ReciprocalRankTest(unittest.TestCase):
    def test_first_position(self) -> None:
        self.assertAlmostEqual(reciprocal_rank(["a", "b", "c"], {"a"}), 1.0)

    def test_second_position(self) -> None:
        self.assertAlmostEqual(reciprocal_rank(["x", "a", "b"], {"a"}), 0.5)

    def test_third_position(self) -> None:
        self.assertAlmostEqual(reciprocal_rank(["x", "y", "a"], {"a"}), 1 / 3)

    def test_not_found(self) -> None:
        self.assertAlmostEqual(reciprocal_rank(["x", "y"], {"a"}), 0.0)

    def test_empty_list(self) -> None:
        self.assertAlmostEqual(reciprocal_rank([], {"a"}), 0.0)

    def test_multiple_relevant_returns_first(self) -> None:
        self.assertAlmostEqual(reciprocal_rank(["x", "a", "b"], {"a", "b"}), 0.5)


class NdcgAtKTest(unittest.TestCase):
    def test_perfect_ranking(self) -> None:
        # Single relevant doc at rank 1 → ideal
        self.assertAlmostEqual(ndcg_at_k(["a", "b"], {"a"}, 5), 1.0)

    def test_not_found(self) -> None:
        self.assertAlmostEqual(ndcg_at_k(["x", "y"], {"a"}, 5), 0.0)

    def test_empty_relevant(self) -> None:
        self.assertAlmostEqual(ndcg_at_k(["a", "b"], set(), 5), 0.0)

    def test_rank2_vs_rank1(self) -> None:
        # Relevant doc at rank 2: DCG = 1/log2(3) ≈ 0.631
        # Ideal DCG = 1/log2(2) = 1.0
        expected = (1.0 / math.log2(3)) / (1.0 / math.log2(2))
        self.assertAlmostEqual(ndcg_at_k(["x", "a"], {"a"}, 5), expected, places=6)

    def test_two_relevant_both_in_top2(self) -> None:
        # DCG = 1/log2(2) + 1/log2(3); ideal = same → 1.0
        self.assertAlmostEqual(ndcg_at_k(["a", "b"], {"a", "b"}, 5), 1.0)

    def test_k_limits_gain(self) -> None:
        # Relevant doc beyond k should not contribute
        self.assertAlmostEqual(ndcg_at_k(["x", "y", "a"], {"a"}, 2), 0.0)


class ScoreQueryTest(unittest.TestCase):
    def test_structure(self) -> None:
        result = score_query(["a", "b", "c"], {"a"}, [5, 10])
        self.assertIn("mrr", result)
        self.assertIn("p@5", result)
        self.assertIn("p@10", result)
        self.assertIn("recall@5", result)
        self.assertIn("recall@10", result)
        self.assertIn("ndcg@5", result)
        self.assertIn("ndcg@10", result)

    def test_values(self) -> None:
        result = score_query(["a", "b"], {"a"}, [5])
        self.assertAlmostEqual(result["mrr"], 1.0)
        self.assertAlmostEqual(result["p@5"], 0.2)
        self.assertAlmostEqual(result["recall@5"], 1.0)
        self.assertAlmostEqual(result["ndcg@5"], 1.0)


class AggregateMetricsTest(unittest.TestCase):
    def test_empty(self) -> None:
        self.assertEqual(aggregate_metrics([], [5]), {})

    def test_single_query(self) -> None:
        m = score_query(["a"], {"a"}, [5])
        agg = aggregate_metrics([m], [5])
        self.assertAlmostEqual(agg["mrr"], m["mrr"])
        self.assertAlmostEqual(agg["p@5"], m["p@5"])

    def test_averaging(self) -> None:
        m1 = {"mrr": 1.0, "p@5": 0.4, "recall@5": 1.0, "ndcg@5": 1.0}
        m2 = {"mrr": 0.5, "p@5": 0.2, "recall@5": 0.5, "ndcg@5": 0.5}
        agg = aggregate_metrics([m1, m2], [5])
        self.assertAlmostEqual(agg["mrr"], 0.75)
        self.assertAlmostEqual(agg["p@5"], 0.3)
        self.assertAlmostEqual(agg["recall@5"], 0.75)
        self.assertAlmostEqual(agg["ndcg@5"], 0.75)


if __name__ == "__main__":
    unittest.main()
