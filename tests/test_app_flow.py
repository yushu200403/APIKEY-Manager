import os
import tempfile
import unittest


class AppFlowTests(unittest.TestCase):
    def setUp(self):
        try:
            from app import create_app
        except ImportError as exc:
            self.skipTest(f"缺少运行依赖：{exc}")
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["APIKEY_MANAGER_DATA_DIR"] = self.temp_dir.name
        self.app = create_app()
        self.client = self.app.test_client()

    def tearDown(self):
        self.app.store.lock()
        self.temp_dir.cleanup()
        os.environ.pop("APIKEY_MANAGER_DATA_DIR", None)

    def test_create_database_and_manage_records(self):
        created = self.client.post(
            "/api/create",
            json={"password": "StrongPass123!", "confirm_password": "StrongPass123!"},
        ).get_json()
        self.assertTrue(created["ok"])
        self.assertTrue(created["data"]["unlocked"])

        provider = self.client.post(
            "/api/providers",
            json={
                "name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "api_formats": ["openai_response"],
            },
        ).get_json()
        self.assertTrue(provider["ok"])
        provider_id = provider["data"]["id"]

        key = self.client.post(
            f"/api/providers/{provider_id}/keys",
            json={"key_name": "主账号", "api_key": "sk-test-123456"},
        ).get_json()
        self.assertTrue(key["ok"])
        self.assertEqual(key["data"]["test_status"], "untested")
        provider_detail = self.client.get(f"/api/providers/{provider_id}").get_json()
        self.assertEqual(provider_detail["data"]["test_key_id"], key["data"]["id"])

        default_settings = self.client.get("/api/settings/test").get_json()
        self.assertEqual(default_settings["data"]["user_prompt"], "你是什么模型？请用一句话回答。")

        settings = self.client.put(
            "/api/settings/test",
            json={
                "system_prompt": "你是一个有帮助的助手。",
                "user_prompt": "你是什么模型？",
            },
        ).get_json()
        self.assertTrue(settings["ok"])
        self.assertEqual(settings["data"]["user_prompt"], "你是什么模型？")
        self.assertNotIn("test_model", settings["data"])

        test_config = self.client.put(
            f"/api/providers/{provider_id}/test-config",
            json={"test_model": "gpt-test"},
        ).get_json()
        self.assertTrue(test_config["ok"])
        self.assertEqual(test_config["data"]["test_model"], "gpt-test")

        generic = self.client.post(
            "/api/generic",
            json={
                "category": "Tavily",
                "key_name": "api_key",
                "key_value": "tvly-test-123456",
                "description": "搜索服务",
            },
        ).get_json()
        self.assertTrue(generic["ok"])

        categories = self.client.get("/api/generic").get_json()
        self.assertEqual(categories["data"][0]["category"], "Tavily")

    def test_reorder_providers_and_generic_categories(self):
        self.client.post(
            "/api/create",
            json={"password": "StrongPass123!", "confirm_password": "StrongPass123!"},
        )
        first = self.client.post(
            "/api/providers",
            json={"name": "B", "base_url": "https://b.example.com", "api_formats": ["openai_response"]},
        ).get_json()["data"]
        second = self.client.post(
            "/api/providers",
            json={"name": "A", "base_url": "https://a.example.com", "api_formats": ["openai_completion"]},
        ).get_json()["data"]
        reordered = self.client.put("/api/providers/order", json={"ids": [second["id"], first["id"]]}).get_json()
        self.assertEqual([item["name"] for item in reordered["data"]], ["A", "B"])

        one = self.client.post("/api/generic", json={"category": "后", "key_name": "k", "key_value": "v"}).get_json()["data"]
        two = self.client.post("/api/generic", json={"category": "前", "key_name": "k", "key_value": "v"}).get_json()["data"]
        categories = self.client.put("/api/generic/categories/order", json={"categories": ["前", "后"]}).get_json()
        self.assertEqual([item["category"] for item in categories["data"]], ["前", "后"])
        self.assertNotEqual(one["id"], two["id"])


if __name__ == "__main__":
    unittest.main()
