import unittest
from backend.extraction.claims import decompose, build_queries
from backend.utils.urls import normalize_url, is_safe_public_url
from backend.analysis.scoring import score
from backend.analysis.contradictions import find


class CoreTests(unittest.TestCase):
    def test_claim_decomposition(self):
        parts = decompose("Is Tesla preparing to launch an affordable EV in India?")
        self.assertEqual(parts["action"], "launch")
        self.assertEqual(parts["location"], "India")

    def test_queries_have_angles_and_limit(self):
        queries = build_queries("Is Tesla preparing a vehicle?", decompose("Is Tesla preparing a vehicle?"), 5)
        self.assertEqual(len(queries), 5)
        self.assertIn("Tesla preparing", " ".join(queries))

    def test_normalize_url_removes_tracking(self):
        self.assertEqual(normalize_url("https://Example.com/path/?utm_source=x&z=1#part"), "https://example.com/path?z=1")

    def test_blocks_private_urls(self):
        self.assertFalse(is_safe_public_url("http://127.0.0.1/admin"))
        self.assertFalse(is_safe_public_url("http://localhost/admin"))

    def test_score_penalizes_contradiction(self):
        evidence = [{"stance":"supporting","strength":.8,"authority":.9,"domain":"official.example"}, {"stance":"contradicting","strength":.9,"authority":.9,"domain":"news.example"}]
        result = score(evidence, 2)
        self.assertLess(result["confidence"], 70)
        self.assertEqual(len(find(evidence)), 1)

if __name__ == "__main__": unittest.main()
