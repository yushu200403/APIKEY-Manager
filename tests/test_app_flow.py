import os
import json
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
                "website_url": "https://openai.com",
                "api_formats": ["openai_chat_completion", "openai_response"],
            },
        ).get_json()
        self.assertTrue(provider["ok"])
        provider_id = provider["data"]["id"]
        self.assertEqual(provider["data"]["website_url"], "https://openai.com")

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

        category = self.client.post(
            "/api/generic/categories",
            json={"category": "Tavily", "description": "搜索服务"},
        ).get_json()
        self.assertTrue(category["ok"])
        self.assertEqual(category["data"]["description"], "搜索服务")

        first_generic = self.client.post(
            "/api/generic",
            json={"category": "Tavily", "key_name": "api_key", "key_value": "tvly-test-123456"},
        ).get_json()
        second_generic = self.client.post(
            "/api/generic",
            json={"category": "Tavily", "key_name": "backup_key", "key_value": "tvly-test-654321"},
        ).get_json()
        self.assertTrue(first_generic["ok"])
        self.assertTrue(second_generic["ok"])

        categories = self.client.get("/api/generic").get_json()
        self.assertEqual(categories["data"][0]["category"], "Tavily")
        self.assertEqual(len(categories["data"][0]["items"]), 2)

        renamed = self.client.put(
            "/api/generic/category/Tavily",
            json={"category": "Tavily搜索", "description": "搜索服务配置"},
        ).get_json()
        self.assertTrue(renamed["ok"])
        categories = self.client.get("/api/generic").get_json()
        self.assertEqual(categories["data"][0]["category"], "Tavily搜索")
        self.assertEqual(categories["data"][0]["description"], "搜索服务配置")
        self.assertEqual(len(categories["data"][0]["items"]), 2)

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
            json={"name": "A", "base_url": "https://a.example.com", "api_formats": ["openai_chat_completion"]},
        ).get_json()["data"]
        reordered = self.client.put("/api/providers/order", json={"ids": [second["id"], first["id"]]}).get_json()
        self.assertEqual([item["name"] for item in reordered["data"]], ["A", "B"])

        one = self.client.post("/api/generic/categories", json={"category": "后"}).get_json()["data"]
        two = self.client.post("/api/generic/categories", json={"category": "前"}).get_json()["data"]
        categories = self.client.put("/api/generic/categories/order", json={"categories": ["前", "后"]}).get_json()
        self.assertEqual([item["category"] for item in categories["data"]], ["前", "后"])
        self.assertNotEqual(one["category"], two["category"])

    def test_export_and_import_json_data(self):
        self.client.post(
            "/api/create",
            json={"password": "StrongPass123!", "confirm_password": "StrongPass123!"},
        )
        provider = self.client.post(
            "/api/providers",
            json={
                "name": "OpenAI",
                "base_url": "https://api.openai.com/v1",
                "website_url": "https://openai.com",
                "api_formats": ["openai_chat_completion"],
            },
        ).get_json()["data"]
        self.client.post(
            f"/api/providers/{provider['id']}/keys",
            json={"key_name": "主账号", "api_key": "sk-test-123456"},
        )
        self.client.put(
            f"/api/providers/{provider['id']}/test-config",
            json={"test_model": "gpt-test"},
        )
        self.client.post("/api/generic/categories", json={"category": "Tavily", "description": "搜索服务"})
        self.client.post(
            "/api/generic",
            json={"category": "Tavily", "key_name": "api_key", "key_value": "tvly-test-123456", "description": "主密钥"},
        )

        exported_json = self.client.get("/api/data/export/json").get_json()
        self.assertTrue(exported_json["ok"])
        payload = json.loads(exported_json["data"]["content"])
        self.assertEqual(payload["schema"], "apikey-manager-export")
        self.assertRegex(payload["exported_at"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        self.assertFalse(payload["include_tests"])
        self.assertNotIn("test_settings", payload)
        self.assertNotIn("test_key_name", payload["providers"][0])
        self.assertNotIn("test_model", payload["providers"][0])
        self.assertNotIn("model_cache", payload["providers"][0])
        self.assertEqual(payload["providers"][0]["keys"][0]["api_key"], "sk-test-123456")
        self.assertNotIn("test_status", payload["providers"][0]["keys"][0])

        exported_markdown = self.client.get("/api/data/export/markdown").get_json()
        self.assertTrue(exported_markdown["ok"])
        self.assertIn("# APIKEY Manager 导出", exported_markdown["data"]["content"])
        self.assertIn("sk-test-123456", exported_markdown["data"]["content"])
        self.assertNotIn("供应商数量", exported_markdown["data"]["content"])
        self.assertNotIn("通用密钥类别数量", exported_markdown["data"]["content"])
        self.assertNotIn("接口格式", exported_markdown["data"]["content"])
        self.assertNotIn("测试 Prompt 设置", exported_markdown["data"]["content"])

        full_json = self.client.get("/api/data/export/json?include_tests=1").get_json()
        full_payload = json.loads(full_json["data"]["content"])
        self.assertTrue(full_payload["include_tests"])
        self.assertIn("test_settings", full_payload)
        self.assertEqual(full_payload["providers"][0]["test_model"], "gpt-test")
        self.assertIn("test_status", full_payload["providers"][0]["keys"][0])

        full_markdown = self.client.get("/api/data/export/markdown?include_tests=1").get_json()["data"]["content"]
        self.assertIn("测试 Prompt 设置", full_markdown)
        self.assertIn("接口格式", full_markdown)
        self.assertNotIn("供应商数量", full_markdown)

        self.client.post(
            "/api/providers",
            json={"name": "临时供应商", "base_url": "https://temp.example.com", "api_formats": ["openai_response"]},
        )
        imported = self.client.post("/api/data/import/json", json={"data": payload}).get_json()
        self.assertTrue(imported["ok"])
        self.assertEqual(imported["data"]["providers"], 1)
        self.assertEqual(imported["data"]["generic_categories"], 1)

        providers = self.client.get("/api/providers").get_json()["data"]
        self.assertEqual([item["name"] for item in providers], ["OpenAI"])
        detail = self.client.get(f"/api/providers/{providers[0]['id']}").get_json()["data"]
        self.assertEqual(detail["keys"][0]["api_key"], "sk-test-123456")
        self.assertEqual(detail["test_config"]["test_model"], "")
        generic = self.client.get("/api/generic").get_json()["data"]
        self.assertEqual(generic[0]["items"][0]["key_value"], "tvly-test-123456")

        database = self.client.get("/api/data/export/database")
        self.assertEqual(database.status_code, 200)
        self.assertIn("attachment", database.headers["Content-Disposition"])
        self.assertGreater(len(database.data), 0)
        database.close()

    def test_import_rejects_unknown_json_schema(self):
        self.client.post(
            "/api/create",
            json={"password": "StrongPass123!", "confirm_password": "StrongPass123!"},
        )
        response = self.client.post("/api/data/import/json", json={"data": {"schema": "other"}}).get_json()
        self.assertFalse(response["ok"])
        self.assertIn("格式不匹配", response["error"])


if __name__ == "__main__":
    unittest.main()
