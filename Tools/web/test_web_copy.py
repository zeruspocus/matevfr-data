import json
import os
import tempfile
import unittest

import web_copy


class WebCopyTests(unittest.TestCase):
    def write(self, text):
        handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def test_valid_json_is_good(self):
        self.assertTrue(web_copy.is_good_json(self.write(json.dumps({"features": [1]}))))

    def test_empty_file_is_bad(self):
        self.assertFalse(web_copy.is_good_json(self.write("")))

    def test_broken_json_is_bad(self):
        self.assertFalse(web_copy.is_good_json(self.write("{ not json")))

    def test_empty_object_or_list_is_bad(self):
        self.assertFalse(web_copy.is_good_json(self.write("{}")))
        self.assertFalse(web_copy.is_good_json(self.write("[]")))
        self.assertFalse(web_copy.is_good_json(self.write("null")))

    def test_missing_file_is_bad(self):
        self.assertFalse(web_copy.is_good_json("/nonexistent/file.json"))


if __name__ == "__main__":
    unittest.main()
