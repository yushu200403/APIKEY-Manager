import unittest

from app.validators import mask_secret, normalize_formats, validate_password, validate_url


class ValidatorTests(unittest.TestCase):
    def test_validate_password_requires_non_empty_value(self):
        with self.assertRaises(ValueError):
            validate_password("")
        self.assertEqual(validate_password("1"), "1")

    def test_validate_url_allows_http_and_https_only(self):
        self.assertEqual(validate_url("https://api.example.com/v1"), "https://api.example.com/v1")
        with self.assertRaises(ValueError):
            validate_url("ftp://api.example.com")

    def test_normalize_formats_deduplicates_and_rejects_unknown(self):
        self.assertEqual(
            normalize_formats(["openai_chat", "openai_response", "anthropic_message"]),
            "openai_response,anthropic_message",
        )
        self.assertEqual(normalize_formats(["openai_completion"]), "openai_completion")
        with self.assertRaises(ValueError):
            normalize_formats(["unknown"])

    def test_mask_secret_keeps_edges(self):
        self.assertEqual(mask_secret("sk-abcdef123456"), "sk-a...3456")
        self.assertEqual(mask_secret("abc"), "ab***")


if __name__ == "__main__":
    unittest.main()
