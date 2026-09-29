import json
import os
import tempfile
import unittest

import field_mapper
from field_mapper import compatible, should_review_mapping


class CompatibleTests(unittest.TestCase):
    def test_numeric_strings_are_compatible_with_numeric_values(self):
        self.assertTrue(compatible([123, 456], ["123", "456"]))

    def test_similar_names_without_overlap_are_sent_for_review(self):
        self.assertTrue(should_review_mapping(0.78, set(), 0))

    def test_weak_name_without_overlap_is_not_sent_for_review(self):
        self.assertFalse(should_review_mapping(0.54, set(), 0))

    def test_automatic_matches_are_not_saved_as_user_decisions(self):
        original_cache = field_mapper.CACHE
        with tempfile.TemporaryDirectory() as temp_dir:
            field_mapper.CACHE = os.path.join(temp_dir, "cache.json")
            try:
                field_mapper.map_fields([{"fields": {"ride_id": "RD-12345", "rideid": "RD-12345"}}])
                with open(field_mapper.CACHE) as cache_file:
                    self.assertEqual(json.load(cache_file), {})
            finally:
                field_mapper.CACHE = original_cache


if __name__ == '__main__':
    unittest.main()
