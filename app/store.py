import json
import threading
import time
from datetime import datetime, timedelta, timezone

from .api_client import fetch_model_ids, test_chat_endpoint
from .db import EncryptedDatabase, database_path
from .validators import (
    mask_secret,
    normalize_formats,
    require_text,
    validate_password,
    validate_url,
)


DEFAULT_SYSTEM_PROMPT = "你是一个有帮助的助手。"
DEFAULT_USER_PROMPT = "你是什么模型？请用一句话回答。"
EXPORT_SCHEMA = "apikey-manager-export"
EXPORT_VERSION = 1
BEIJING_TIMEZONE = timezone(timedelta(hours=8))


class Store:
    def __init__(self):
        self._db = None
        self._lock = threading.RLock()
        self._failed_attempts = 0
        self._blocked_until = 0

    @property
    def unlocked(self):
        return self._db is not None

    def status(self):
        return {
            "database_exists": database_path().exists(),
            "unlocked": self.unlocked,
            "database_path": str(database_path()),
            "blocked_seconds": max(0, int(self._blocked_until - time.time())),
        }

    def create_database(self, password, confirm_password):
        validate_password(password)
        if password != confirm_password:
            raise ValueError("两次输入的主密码不一致")
        with self._lock:
            if database_path().exists():
                raise ValueError("数据库已存在，请直接解锁")
            db = EncryptedDatabase(password).connect()
            db.initialize()
            self._db = db
            self._failed_attempts = 0
            self._blocked_until = 0
            return self.status()

    def unlock(self, password):
        now = time.time()
        if now < self._blocked_until:
            raise ValueError(f"密码错误次数过多，请等待 {int(self._blocked_until - now)} 秒后重试")
        validate_password(password)
        with self._lock:
            try:
                db = EncryptedDatabase(password).connect()
                db.initialize()
            except Exception:
                self._failed_attempts += 1
                if self._failed_attempts >= 3:
                    self._blocked_until = time.time() + 5
                    self._failed_attempts = 0
                raise
            if self._db:
                self._db.close()
            self._db = db
            self._failed_attempts = 0
            self._blocked_until = 0
            return self.status()

    def lock(self):
        with self._lock:
            if self._db:
                self._db.close()
            self._db = None

    def db(self):
        if self._db is None:
            raise ValueError("数据库未解锁")
        return self._db

    def providers(self):
        rows = self.db().query_all("SELECT * FROM llm_providers ORDER BY sort_order, id")
        for row in rows:
            row["api_formats"] = row["api_format"].split(",")
        return rows

    def provider_detail(self, provider_id):
        provider = self._provider(provider_id)
        provider["api_formats"] = provider["api_format"].split(",")
        provider["keys"] = self.keys(provider_id)
        provider["test_config"] = self.provider_test_config(provider_id)
        provider["model_cache"] = self.model_cache(provider_id)
        return provider

    def add_provider(self, payload):
        name = require_text(payload.get("name"), "供应商名称")
        base_url = validate_url(payload.get("base_url"))
        website_url = self._optional_url(payload.get("website_url"))
        api_format = normalize_formats(payload.get("api_formats") or payload.get("api_format"))
        with self._lock:
            sort_order = self._next_sort_order("llm_providers")
            cur = self.db().execute(
                "INSERT INTO llm_providers (name, base_url, website_url, api_format, sort_order) VALUES (?, ?, ?, ?, ?)",
                (name, base_url, website_url, api_format, sort_order),
            )
            provider_id = cur.lastrowid
            self.db().execute("INSERT INTO test_configs (provider_id, test_model) VALUES (?, '')", (provider_id,))
            return self.provider_detail(provider_id)

    def update_provider(self, provider_id, payload):
        name = require_text(payload.get("name"), "供应商名称")
        base_url = validate_url(payload.get("base_url"))
        website_url = self._optional_url(payload.get("website_url"))
        api_format = normalize_formats(payload.get("api_formats") or payload.get("api_format"))
        with self._lock:
            self._provider(provider_id)
            self.db().execute(
                """
                UPDATE llm_providers
                SET name = ?, base_url = ?, website_url = ?, api_format = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (name, base_url, website_url, api_format, provider_id),
            )
            return self.provider_detail(provider_id)

    def delete_provider(self, provider_id):
        with self._lock:
            self._provider(provider_id)
            self.db().execute("DELETE FROM llm_providers WHERE id = ?", (provider_id,))
            self._renumber_table("llm_providers")

    def keys(self, provider_id):
        self._provider(provider_id)
        rows = self.db().query_all(
            "SELECT * FROM api_keys WHERE provider_id = ? ORDER BY sort_order, id",
            (provider_id,),
        )
        for row in rows:
            row["masked_key"] = mask_secret(row["api_key"])
        return rows

    def add_key(self, provider_id, payload):
        self._provider(provider_id)
        key_name = require_text(payload.get("key_name"), "密钥别名")
        api_key = require_text(payload.get("api_key"), "API密钥")
        sort_order = self._next_sort_order("api_keys", "provider_id", provider_id)
        cur = self.db().execute(
            """
            INSERT INTO api_keys (provider_id, key_name, api_key, test_status, sort_order)
            VALUES (?, ?, ?, 'untested', ?)
            """,
            (provider_id, key_name, api_key, sort_order),
        )
        key = self._key(cur.lastrowid)
        provider = self._provider(provider_id)
        if not provider.get("test_key_id"):
            self.set_provider_test_key(provider_id, key["id"])
            key = self._key(cur.lastrowid)
        return key

    def update_key(self, key_id, payload):
        key = self._key(key_id)
        key_name = require_text(payload.get("key_name"), "密钥别名")
        api_key = require_text(payload.get("api_key"), "API密钥")
        self.db().execute(
            "UPDATE api_keys SET key_name = ?, api_key = ? WHERE id = ?",
            (key_name, api_key, key_id),
        )
        return self._key(key["id"])

    def delete_key(self, key_id):
        key = self._key(key_id)
        self.db().execute("DELETE FROM api_keys WHERE id = ?", (key_id,))
        self._renumber_table("api_keys", "provider_id", key["provider_id"])

    def test_settings(self):
        row = self.db().query_one("SELECT * FROM app_settings WHERE id = 1")
        if row:
            return self._prompt_settings(row)
        self.db().execute(
            "INSERT INTO app_settings (id, system_prompt, user_prompt) VALUES (1, ?, ?)",
            (DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_PROMPT),
        )
        return self._prompt_settings(self.db().query_one("SELECT * FROM app_settings WHERE id = 1"))

    def save_test_settings(self, payload):
        system_prompt = require_text(payload.get("system_prompt") or DEFAULT_SYSTEM_PROMPT, "System Prompt")
        user_prompt = require_text(payload.get("user_prompt") or DEFAULT_USER_PROMPT, "User Prompt")
        self.test_settings()
        self.db().execute(
            """
            UPDATE app_settings
            SET system_prompt = ?, user_prompt = ?
            WHERE id = 1
            """,
            (system_prompt, user_prompt),
        )
        return self.test_settings()

    def provider_test_config(self, provider_id):
        self._provider(provider_id)
        row = self.db().query_one("SELECT * FROM test_configs WHERE provider_id = ?", (provider_id,))
        if row:
            return row
        self.db().execute("INSERT INTO test_configs (provider_id, test_model) VALUES (?, '')", (provider_id,))
        return self.db().query_one("SELECT * FROM test_configs WHERE provider_id = ?", (provider_id,))

    def save_provider_test_config(self, provider_id, payload):
        self._provider(provider_id)
        test_model = str(payload.get("test_model") or "").strip()
        self.provider_test_config(provider_id)
        self.db().execute("UPDATE test_configs SET test_model = ? WHERE provider_id = ?", (test_model, provider_id))
        return self.provider_test_config(provider_id)

    def set_provider_test_key(self, provider_id, key_id):
        provider = self._provider(provider_id)
        key = self._key(key_id)
        if key["provider_id"] != provider["id"]:
            raise ValueError("密钥不属于当前供应商")
        self.db().execute(
            "UPDATE llm_providers SET test_key_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (key_id, provider_id),
        )
        return self.provider_detail(provider_id)

    def test_key(self, provider_id, key_id=None):
        provider = self._provider(provider_id)
        key_id = key_id or provider.get("test_key_id")
        if not key_id:
            raise ValueError("请先选择一个测试密钥")
        key = self._key(key_id)
        if key["provider_id"] != provider_id:
            raise ValueError("密钥不属于当前供应商")
        prompt_settings = self.test_settings()
        provider_config = self.provider_test_config(provider_id)
        config = {
            "test_model": provider_config.get("test_model") or "",
            "system_prompt": prompt_settings["system_prompt"],
            "user_prompt": prompt_settings["user_prompt"],
        }
        try:
            message = test_chat_endpoint(provider, key["api_key"], config)
            status = "success"
        except Exception as exc:
            message = str(exc)
            status = "failed"
        self.db().execute(
            """
            UPDATE api_keys
            SET test_status = ?, test_message = ?, last_tested = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, message, key_id),
        )
        result = self._key(key_id)
        result["test_message"] = message
        return result

    def refresh_models(self, provider_id):
        provider = self._provider(provider_id)
        if not provider.get("test_key_id"):
            raise ValueError("请先选择一个测试密钥")
        key = self._key(provider["test_key_id"])
        if key["provider_id"] != provider_id:
            raise ValueError("测试密钥不属于当前供应商")
        model_ids = fetch_model_ids(provider, key["api_key"])
        self.db().upsert_model_cache(provider_id, model_ids)
        return self.model_cache(provider_id)

    def model_cache(self, provider_id):
        self._provider(provider_id)
        row = self.db().query_one("SELECT * FROM model_cache WHERE provider_id = ?", (provider_id,))
        if not row:
            return {"model_ids": [], "last_fetched": None}
        row["model_ids"] = json.loads(row["model_ids"])
        return row

    def database_file_path(self):
        self.db()
        return database_path()

    def export_data(self, include_tests=False):
        providers = []
        provider_rows = self.db().query_all("SELECT * FROM llm_providers ORDER BY sort_order, id")
        for provider in provider_rows:
            key_rows = self.db().query_all(
                "SELECT * FROM api_keys WHERE provider_id = ? ORDER BY sort_order, id",
                (provider["id"],),
            )
            provider_data = {
                "name": provider["name"],
                "base_url": provider["base_url"],
                "website_url": provider.get("website_url") or "",
                "api_formats": provider["api_format"].split(","),
                "keys": [
                    {
                        "key_name": key["key_name"],
                        "api_key": key["api_key"],
                    }
                    for key in key_rows
                ],
            }
            if include_tests:
                test_config = self.provider_test_config(provider["id"])
                cache = self.model_cache(provider["id"])
                test_key_name = ""
                for key in key_rows:
                    if key["id"] == provider.get("test_key_id"):
                        test_key_name = key["key_name"]
                        break
                provider_data["test_key_name"] = test_key_name
                provider_data["test_model"] = test_config.get("test_model") or ""
                provider_data["model_cache"] = {
                    "model_ids": cache.get("model_ids") or [],
                    "last_fetched": cache.get("last_fetched"),
                }
                for key_data, key in zip(provider_data["keys"], key_rows):
                    key_data["test_status"] = key.get("test_status") or "untested"
                    key_data["test_message"] = key.get("test_message") or ""
            providers.append(provider_data)
        data = {
            "schema": EXPORT_SCHEMA,
            "version": EXPORT_VERSION,
            "exported_at": self._export_time(),
            "include_tests": include_tests,
            "providers": providers,
            "generic_categories": self._export_generic_categories(),
        }
        if include_tests:
            data["test_settings"] = self.test_settings()
        return data

    def export_json_text(self, include_tests=False):
        return json.dumps(self.export_data(include_tests), ensure_ascii=False, indent=2)

    def export_markdown_text(self, include_tests=False):
        data = self.export_data(include_tests)
        lines = [
            "# APIKEY Manager 导出",
            "",
            f"- 导出时间：{data['exported_at']}",
            "",
        ]
        if include_tests:
            lines.extend([
                "## 测试 Prompt 设置",
                "",
                f"- System Prompt：{data['test_settings']['system_prompt']}",
                f"- User Prompt：{data['test_settings']['user_prompt']}",
                "",
            ])
        lines.extend(["## 大模型供应商", ""])
        if data["providers"]:
            for provider in data["providers"]:
                provider_lines = [
                    f"### {provider['name']}",
                    "",
                    f"- API 端点：`{provider['base_url']}`",
                    f"- 官网地址：{provider['website_url'] or '-'}",
                ]
                if include_tests:
                    provider_lines.extend([
                        f"- 接口格式：{', '.join(provider['api_formats'])}",
                        f"- 测试密钥：{provider['test_key_name'] or '-'}",
                        f"- 测试模型：{provider['test_model'] or '-'}",
                    ])
                provider_lines.append("")
                if include_tests:
                    provider_lines.extend(["| 密钥别名 | API Key | 测试状态 | 测试消息 |", "| --- | --- | --- | --- |"])
                else:
                    provider_lines.extend(["| 密钥别名 | API Key |", "| --- | --- |"])
                lines.extend(provider_lines)
                if provider["keys"]:
                    for key in provider["keys"]:
                        if include_tests:
                            lines.append(
                                f"| {self._markdown_cell(key['key_name'])} | `{self._markdown_cell(key['api_key'])}` | "
                                f"{self._markdown_cell(key['test_status'])} | {self._markdown_cell(key['test_message'] or '-')} |"
                            )
                        else:
                            lines.append(f"| {self._markdown_cell(key['key_name'])} | `{self._markdown_cell(key['api_key'])}` |")
                else:
                    lines.append("| - | - | - | - |" if include_tests else "| - | - |")
                lines.append("")
        else:
            lines.extend(["暂无大模型供应商。", ""])
        lines.extend(["## 通用密钥", ""])
        if data["generic_categories"]:
            for group in data["generic_categories"]:
                lines.extend([
                    f"### {group['category']}",
                    "",
                    f"- 描述：{group['description'] or '-'}",
                    "",
                    "| 键名 | 键值 | 描述 |",
                    "| --- | --- | --- |",
                ])
                if group["items"]:
                    for item in group["items"]:
                        lines.append(
                            f"| {self._markdown_cell(item['key_name'])} | `{self._markdown_cell(item['key_value'])}` | "
                            f"{self._markdown_cell(item['description'] or '-')} |"
                        )
                else:
                    lines.append("| - | - | - |")
                lines.append("")
        else:
            lines.extend(["暂无通用密钥。", ""])
        return "\n".join(lines).rstrip() + "\n"

    def import_json_data(self, payload):
        data = self._normalize_import_payload(payload)
        with self._lock:
            conn = self.db().conn
            try:
                conn.execute("BEGIN")
                self._clear_importable_tables(conn)
                self._insert_import_data(conn, data)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return {
            "providers": len(data["providers"]),
            "generic_categories": len(data["generic_categories"]),
        }

    def generic_categories(self):
        category_rows = self.db().query_all(
            "SELECT * FROM generic_categories ORDER BY sort_order, category"
        )
        key_rows = self.db().query_all("SELECT * FROM generic_keys ORDER BY category, sort_order, id")
        categories = {}
        for row in category_rows:
            categories[row["category"]] = {
                "category": row["category"],
                "description": row.get("description") or "",
                "items": [],
            }
        for row in key_rows:
            row["masked_value"] = mask_secret(row["key_value"])
            categories[row["category"]]["items"].append(row)
        return list(categories.values())

    def add_generic_category(self, payload):
        category = require_text(payload.get("category") or payload.get("name"), "类别名称")
        description = str(payload.get("description") or "").strip()
        if self.db().query_one("SELECT category FROM generic_categories WHERE category = ?", (category,)):
            raise ValueError("类别名称已存在")
        sort_order = self._next_sort_order("generic_categories")
        self.db().execute(
            "INSERT INTO generic_categories (category, description, sort_order) VALUES (?, ?, ?)",
            (category, description, sort_order),
        )
        return self._generic_category(category)

    def update_generic_category(self, category, payload):
        old_category = require_text(category, "类别名称")
        new_category = require_text(payload.get("category") or payload.get("name"), "类别名称")
        description = str(payload.get("description") or "").strip()
        self._generic_category(old_category)
        if old_category != new_category:
            exists = self.db().query_one("SELECT category FROM generic_categories WHERE category = ?", (new_category,))
            if exists:
                raise ValueError("类别名称已存在")
        self.db().execute(
            "UPDATE generic_categories SET category = ?, description = ? WHERE category = ?",
            (new_category, description, old_category),
        )
        return self._generic_category(new_category)

    def add_generic_key(self, payload):
        category = require_text(payload.get("category"), "类别名称")
        key_name = require_text(payload.get("key_name"), "键名")
        key_value = require_text(payload.get("key_value"), "键值")
        description = str(payload.get("description") or "").strip()
        self._generic_category(category)
        sort_order = self._next_sort_order("generic_keys", "category", category)
        cur = self.db().execute(
            """
            INSERT INTO generic_keys (category, key_name, key_value, description, sort_order)
            VALUES (?, ?, ?, ?, ?)
            """,
            (category, key_name, key_value, description, sort_order),
        )
        return self._generic_key(cur.lastrowid)

    def update_generic_key(self, item_id, payload):
        old = self._generic_key(item_id)
        category = require_text(payload.get("category"), "类别名称")
        key_name = require_text(payload.get("key_name"), "键名")
        key_value = require_text(payload.get("key_value"), "键值")
        description = str(payload.get("description") or "").strip()
        self._generic_category(category)
        sort_order = old["sort_order"] if old["category"] == category else self._next_sort_order("generic_keys", "category", category)
        self.db().execute(
            """
            UPDATE generic_keys
            SET category = ?, key_name = ?, key_value = ?, description = ?, sort_order = ?
            WHERE id = ?
            """,
            (category, key_name, key_value, description, sort_order, item_id),
        )
        if old["category"] != category:
            self._renumber_table("generic_keys", "category", old["category"])
            self._renumber_table("generic_keys", "category", category)
        return self._generic_key(item_id)

    def delete_generic_key(self, item_id):
        row = self._generic_key(item_id)
        self.db().execute("DELETE FROM generic_keys WHERE id = ?", (item_id,))
        self._renumber_table("generic_keys", "category", row["category"])

    def delete_generic_category(self, category):
        category = require_text(category, "类别名称")
        self.db().execute("DELETE FROM generic_categories WHERE category = ?", (category,))

    def reorder_providers(self, ordered_ids):
        ids = self._validate_id_list(ordered_ids, "供应商排序")
        existing = [row["id"] for row in self.providers()]
        if set(ids) != set(existing):
            raise ValueError("供应商排序列表与现有供应商不一致")
        for index, provider_id in enumerate(ids, start=1):
            self.db().execute("UPDATE llm_providers SET sort_order = ? WHERE id = ?", (index, provider_id))
        return self.providers()

    def reorder_keys(self, provider_id, ordered_ids):
        self._provider(provider_id)
        ids = self._validate_id_list(ordered_ids, "密钥排序")
        existing = [
            row["id"]
            for row in self.db().query_all(
                "SELECT id FROM api_keys WHERE provider_id = ? ORDER BY sort_order, id",
                (provider_id,),
            )
        ]
        if set(ids) != set(existing):
            raise ValueError("密钥排序列表与当前供应商不一致")
        for index, key_id in enumerate(ids, start=1):
            self.db().execute("UPDATE api_keys SET sort_order = ? WHERE id = ?", (index, key_id))
        return self.provider_detail(provider_id)

    def reorder_generic_categories(self, categories):
        if not isinstance(categories, list) or not categories:
            raise ValueError("类别排序不能为空")
        existing = [group["category"] for group in self.generic_categories()]
        names = [require_text(str(category), "类别名称") for category in categories]
        if set(names) != set(existing):
            raise ValueError("类别排序列表与现有类别不一致")
        for index, category in enumerate(names, start=1):
            row = self.db().query_one("SELECT category FROM generic_categories WHERE category = ?", (category,))
            if row:
                self.db().execute("UPDATE generic_categories SET sort_order = ? WHERE category = ?", (index, category))
            else:
                self.db().execute("INSERT INTO generic_categories (category, sort_order) VALUES (?, ?)", (category, index))
        return self.generic_categories()

    def reorder_generic_keys(self, category, ordered_ids):
        category = require_text(category, "类别名称")
        ids = self._validate_id_list(ordered_ids, "键值排序")
        existing = [row["id"] for row in self.db().query_all("SELECT id FROM generic_keys WHERE category = ? ORDER BY sort_order, id", (category,))]
        if set(ids) != set(existing):
            raise ValueError("键值排序列表与当前类别不一致")
        for index, item_id in enumerate(ids, start=1):
            self.db().execute("UPDATE generic_keys SET sort_order = ? WHERE id = ?", (index, item_id))
        return self.generic_categories()

    def _provider(self, provider_id):
        row = self.db().query_one("SELECT * FROM llm_providers WHERE id = ?", (provider_id,))
        if not row:
            raise ValueError("供应商不存在")
        return row

    def _key(self, key_id):
        row = self.db().query_one("SELECT * FROM api_keys WHERE id = ?", (key_id,))
        if not row:
            raise ValueError("密钥不存在")
        row["masked_key"] = mask_secret(row["api_key"])
        return row

    def _generic_key(self, item_id):
        row = self.db().query_one("SELECT * FROM generic_keys WHERE id = ?", (item_id,))
        if not row:
            raise ValueError("键值对不存在")
        row["masked_value"] = mask_secret(row["key_value"])
        return row

    def _generic_category(self, category):
        row = self.db().query_one("SELECT * FROM generic_categories WHERE category = ?", (category,))
        if not row:
            raise ValueError("类别不存在，请先创建类别")
        row["description"] = row.get("description") or ""
        return row

    def _prompt_settings(self, row):
        return {
            "id": row["id"],
            "system_prompt": row["system_prompt"],
            "user_prompt": row["user_prompt"],
        }

    def _next_sort_order(self, table, group_column=None, group_value=None):
        if group_column:
            row = self.db().query_one(f"SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM {table} WHERE {group_column} = ?", (group_value,))
        else:
            row = self.db().query_one(f"SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM {table}")
        return row["next_order"]

    def _renumber_table(self, table, group_column=None, group_value=None):
        if group_column:
            rows = self.db().query_all(f"SELECT id FROM {table} WHERE {group_column} = ? ORDER BY sort_order, id", (group_value,))
        else:
            rows = self.db().query_all(f"SELECT id FROM {table} ORDER BY sort_order, id")
        for index, row in enumerate(rows, start=1):
            self.db().execute(f"UPDATE {table} SET sort_order = ? WHERE id = ?", (index, row["id"]))

    def _validate_id_list(self, value, field_name):
        if not isinstance(value, list) or not value:
            raise ValueError(f"{field_name}不能为空")
        try:
            return [int(item) for item in value]
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{field_name}必须是ID列表") from exc

    def _optional_url(self, value):
        text = str(value or "").strip()
        if not text:
            return ""
        return validate_url(text)

    def _export_generic_categories(self):
        groups = []
        category_rows = self.db().query_all("SELECT * FROM generic_categories ORDER BY sort_order, category")
        for category in category_rows:
            item_rows = self.db().query_all(
                "SELECT * FROM generic_keys WHERE category = ? ORDER BY sort_order, id",
                (category["category"],),
            )
            groups.append({
                "category": category["category"],
                "description": category.get("description") or "",
                "items": [
                    {
                        "key_name": item["key_name"],
                        "key_value": item["key_value"],
                        "description": item.get("description") or "",
                    }
                    for item in item_rows
                ],
            })
        return groups

    def _normalize_import_payload(self, payload):
        if not isinstance(payload, dict):
            raise ValueError("导入内容必须是JSON对象")
        if payload.get("schema") != EXPORT_SCHEMA:
            raise ValueError("JSON格式不匹配，请导入本应用导出的文件")
        try:
            version = int(payload.get("version") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("导入文件版本号不正确") from exc
        if version > EXPORT_VERSION:
            raise ValueError("导入文件版本高于当前应用支持版本")
        settings = payload.get("test_settings") or {}
        providers = payload.get("providers") or []
        generic_categories = payload.get("generic_categories") or []
        if not isinstance(providers, list) or not isinstance(generic_categories, list):
            raise ValueError("导入数据结构不完整")
        normalized = {
            "test_settings": {
                "system_prompt": require_text(settings.get("system_prompt") or DEFAULT_SYSTEM_PROMPT, "System Prompt"),
                "user_prompt": require_text(settings.get("user_prompt") or DEFAULT_USER_PROMPT, "User Prompt"),
            },
            "providers": [],
            "generic_categories": [],
        }
        seen_providers = set()
        for provider in providers:
            if not isinstance(provider, dict):
                raise ValueError("供应商数据必须是对象")
            name = require_text(provider.get("name"), "供应商名称")
            if name in seen_providers:
                raise ValueError(f"供应商名称重复：{name}")
            seen_providers.add(name)
            keys = provider.get("keys") or []
            if not isinstance(keys, list):
                raise ValueError(f"{name} 的密钥列表格式不正确")
            normalized["providers"].append({
                "name": name,
                "base_url": validate_url(provider.get("base_url")),
                "website_url": self._optional_url(provider.get("website_url")),
                "api_format": normalize_formats(provider.get("api_formats") or provider.get("api_format")),
                "test_key_name": str(provider.get("test_key_name") or "").strip(),
                "test_model": str(provider.get("test_model") or "").strip(),
                "model_cache": self._normalize_model_cache(provider.get("model_cache")),
                "keys": self._normalize_import_keys(keys, name),
            })
        seen_categories = set()
        for group in generic_categories:
            if not isinstance(group, dict):
                raise ValueError("通用密钥类别数据必须是对象")
            category = require_text(group.get("category"), "类别名称")
            if category in seen_categories:
                raise ValueError(f"类别名称重复：{category}")
            seen_categories.add(category)
            items = group.get("items") or []
            if not isinstance(items, list):
                raise ValueError(f"{category} 的键值列表格式不正确")
            normalized["generic_categories"].append({
                "category": category,
                "description": str(group.get("description") or "").strip(),
                "items": self._normalize_import_generic_items(items, category),
            })
        return normalized

    def _normalize_import_keys(self, keys, provider_name):
        normalized = []
        seen = set()
        for key in keys:
            if not isinstance(key, dict):
                raise ValueError(f"{provider_name} 的密钥数据必须是对象")
            key_name = require_text(key.get("key_name"), "密钥别名")
            if key_name in seen:
                raise ValueError(f"{provider_name} 下密钥别名重复：{key_name}")
            seen.add(key_name)
            normalized.append({
                "key_name": key_name,
                "api_key": require_text(key.get("api_key"), "API密钥"),
                "test_status": str(key.get("test_status") or "untested").strip() or "untested",
                "test_message": str(key.get("test_message") or "").strip(),
            })
        return normalized

    def _normalize_import_generic_items(self, items, category):
        normalized = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{category} 的键值数据必须是对象")
            key_name = require_text(item.get("key_name"), "键名")
            if key_name in seen:
                raise ValueError(f"{category} 下键名重复：{key_name}")
            seen.add(key_name)
            normalized.append({
                "key_name": key_name,
                "key_value": require_text(item.get("key_value"), "键值"),
                "description": str(item.get("description") or "").strip(),
            })
        return normalized

    def _normalize_model_cache(self, value):
        if not isinstance(value, dict):
            return {"model_ids": [], "last_fetched": None}
        model_ids = value.get("model_ids") or []
        if not isinstance(model_ids, list):
            model_ids = []
        return {
            "model_ids": [str(item).strip() for item in model_ids if str(item).strip()],
            "last_fetched": str(value.get("last_fetched") or "").strip() or None,
        }

    def _clear_importable_tables(self, conn):
        for table in ("model_cache", "test_configs", "api_keys", "llm_providers", "generic_keys", "generic_categories", "app_settings"):
            conn.execute(f"DELETE FROM {table}")

    def _insert_import_data(self, conn, data):
        conn.execute(
            "INSERT INTO app_settings (id, system_prompt, user_prompt) VALUES (1, ?, ?)",
            (data["test_settings"]["system_prompt"], data["test_settings"]["user_prompt"]),
        )
        for provider_index, provider in enumerate(data["providers"], start=1):
            cur = conn.execute(
                """
                INSERT INTO llm_providers (name, base_url, website_url, api_format, sort_order)
                VALUES (?, ?, ?, ?, ?)
                """,
                (provider["name"], provider["base_url"], provider["website_url"], provider["api_format"], provider_index),
            )
            provider_id = cur.lastrowid
            test_key_id = None
            for key_index, key in enumerate(provider["keys"], start=1):
                key_cur = conn.execute(
                    """
                    INSERT INTO api_keys (provider_id, key_name, api_key, test_status, test_message, sort_order)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (provider_id, key["key_name"], key["api_key"], key["test_status"], key["test_message"], key_index),
                )
                if provider["test_key_name"] and key["key_name"] == provider["test_key_name"]:
                    test_key_id = key_cur.lastrowid
            if test_key_id is None and provider["keys"]:
                row = conn.execute(
                    "SELECT id FROM api_keys WHERE provider_id = ? ORDER BY sort_order, id LIMIT 1",
                    (provider_id,),
                ).fetchone()
                test_key_id = row["id"] if row else None
            conn.execute("INSERT INTO test_configs (provider_id, test_model) VALUES (?, ?)", (provider_id, provider["test_model"]))
            if test_key_id:
                conn.execute("UPDATE llm_providers SET test_key_id = ? WHERE id = ?", (test_key_id, provider_id))
            if provider["model_cache"]["model_ids"]:
                conn.execute(
                    "INSERT INTO model_cache (provider_id, model_ids, last_fetched) VALUES (?, ?, ?)",
                    (
                        provider_id,
                        json.dumps(provider["model_cache"]["model_ids"], ensure_ascii=False),
                        provider["model_cache"]["last_fetched"],
                    ),
                )
        for category_index, group in enumerate(data["generic_categories"], start=1):
            conn.execute(
                "INSERT INTO generic_categories (category, description, sort_order) VALUES (?, ?, ?)",
                (group["category"], group["description"], category_index),
            )
            for item_index, item in enumerate(group["items"], start=1):
                conn.execute(
                    """
                    INSERT INTO generic_keys (category, key_name, key_value, description, sort_order)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (group["category"], item["key_name"], item["key_value"], item["description"], item_index),
                )

    def _markdown_cell(self, value):
        return str(value or "").replace("|", "\\|").replace("\n", "<br>")

    def _export_time(self):
        return datetime.now(BEIJING_TIMEZONE).strftime("%Y-%m-%d %H:%M")
