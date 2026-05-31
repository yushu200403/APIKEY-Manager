import unittest
from unittest.mock import patch

from app.api_client import test_chat_endpoint


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class ApiClientTests(unittest.TestCase):
    def test_openai_chat_completion_uses_chat_completions_path(self):
        provider = {
            "base_url": "https://api-inference.modelscope.cn/v1",
            "api_format": "openai_chat_completion",
        }
        config = {
            "test_model": "MiniMax/MiniMax-M2.5",
            "system_prompt": "你是一个有帮助的助手。",
            "user_prompt": "你是什么模型？",
        }
        response = FakeResponse({"choices": [{"message": {"content": "ok"}}]})

        with patch("app.api_client.requests.request", return_value=response) as mocked:
            self.assertEqual(test_chat_endpoint(provider, "test-key", config), "ok")

        method, url = mocked.call_args.args
        request_body = mocked.call_args.kwargs["json"]
        self.assertEqual(method, "post")
        self.assertEqual(url, "https://api-inference.modelscope.cn/v1/chat/completions")
        self.assertEqual(request_body["model"], "MiniMax/MiniMax-M2.5")
        self.assertEqual(request_body["messages"][0]["role"], "system")
        self.assertEqual(request_body["messages"][1]["content"], "你是什么模型？")
        self.assertNotIn("prompt", request_body)

if __name__ == "__main__":
    unittest.main()
