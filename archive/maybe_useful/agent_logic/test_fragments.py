"""v1.0 — 纯标准库、离线片段验证。"""
import json
import unittest

from fragments import decode_json_text, semantic_scholar_fields, filter_citation_markers, render_paper_email


class JsonTests(unittest.TestCase):
    def test_plain_arrays_and_outer_fence(self):
        for text in (' [1, 2] ', '```json\n[1, 2]\n```', '```\r\n[1, 2]\r\n```'):
            self.assertEqual(decode_json_text(text), [1, 2])

    def test_body_fence_unchanged(self):
        value = {"body": "```json\ntext\n```"}
        self.assertEqual(decode_json_text(json.dumps(value)), value)

    def test_invalid_and_partial_fence_rejected(self):
        for text in ('no json', '```json\n{}', '{}\n```', 'prefix\n```json\n{}\n```', 'NaN', 'Infinity'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                decode_json_text(text)


class MappingTests(unittest.TestCase):
    def test_provenance_and_year_precision(self):
        raw = {"paperId": "id-1", "title": " Title ", "year": 2020,
               "externalIds": {"DOI": "d", "ArXiv": "hep-th/9901001v2"},
               "authors": [{"name": " Author "}], "abstract": " Text ", "venue": " V "}
        result = semantic_scholar_fields(raw, "batch-1")
        self.assertEqual(result["provider_id"], "id-1")
        self.assertEqual(result["retrieval_batch"], "batch-1")
        self.assertEqual(result["publication_date"], "2020")
        self.assertEqual(result["date_precision"], "year")
        self.assertEqual(result["authors"], ["Author"])
        self.assertEqual(result["arxiv_id"], "hep-th/9901001v2")
        self.assertEqual(result["warnings"], [])
        raw["externalIds"]["DOI"] = "changed"
        self.assertEqual(result["raw_record"]["externalIds"]["DOI"], "d")

    def test_null_and_bad_types(self):
        result = semantic_scholar_fields({"title": 42, "authors": {}, "externalIds": [],
                                         "year": True, "abstract": [], "venue": None}, "batch")
        self.assertIsNone(result["title"])
        self.assertIsNone(result["publication_date"])
        self.assertEqual(result["authors"], [])
        self.assertGreaterEqual(len(result["warnings"]), 5)
        result = semantic_scholar_fields({"title": None, "authors": None, "externalIds": None}, "batch")
        self.assertIsNone(result["doi"])

    def test_author_shapes(self):
        result = semantic_scholar_fields({"title": "t", "authors": [None, {"name": 1}, {"name": "A"}]}, "b")
        self.assertEqual(result["authors"], ["A"])
        self.assertEqual(len(result["warnings"]), 2)

    def test_date_validation_and_conflict(self):
        result = semantic_scholar_fields({"title": "t", "publicationDate": "2020-02-29", "year": 2021}, "b")
        self.assertEqual(result["date_precision"], "day")
        self.assertIn("year: conflicts with publicationDate", result["warnings"])
        result = semantic_scholar_fields({"title": "t", "publicationDate": "2021-02-29", "year": 2021}, "b")
        self.assertEqual(result["publication_date"], "2021")
        self.assertIn("publicationDate: invalid date", result["warnings"])

    def test_input_contract(self):
        with self.assertRaises(TypeError):
            semantic_scholar_fields([], "batch")
        with self.assertRaises(ValueError):
            semantic_scholar_fields({}, " ")


class CitationTests(unittest.TestCase):
    def test_order_uniqueness_and_unknown(self):
        self.assertEqual(filter_citation_markers('[b][x][a][b][x][z]', {'a', 'b'}),
                         {"allowed": ['b', 'a'], "unknown": ['x', 'z']})

    def test_exact_ids_and_empty(self):
        self.assertEqual(filter_citation_markers('[ a ][a]', {'a'}), {"allowed": ['a'], "unknown": [' a ']})
        self.assertEqual(filter_citation_markers('', set()), {"allowed": [], "unknown": []})


class EmailTests(unittest.TestCase):
    def test_all_interpolated_fields_escaped(self):
        dangerous = '<script>"&\'</script>'
        result = render_paper_email(dangerous, [{"title": dangerous, "authors": [dangerous],
                    "venue": dangerous, "publication_date": dangerous, "summary": dangerous}])
        self.assertNotIn('<script>', result)
        self.assertEqual(result.count('&lt;script&gt;&quot;&amp;&#x27;&lt;/script&gt;'), 6)

    def test_empty_and_long(self):
        self.assertIn('<tbody></tbody>', render_paper_email('Project', []))
        long_text = '论文' * 10000
        rendered = render_paper_email('Project', [{"title": long_text}])
        self.assertIn(long_text, rendered)
        self.assertIn('overflow-wrap:anywhere', rendered)


if __name__ == '__main__':
    unittest.main()
