import json
import threading
import time

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
        api_format = normalize_formats(payload.get("api_formats") or payload.get("api_format"))
        with self._lock:
            sort_order = self._next_sort_order("llm_providers")
            cur = self.db().execute(
                "INSERT INTO llm_providers (name, base_url, api_format, sort_order) VALUES (?, ?, ?, ?)",
                (name, base_url, api_format, sort_order),
            )
            provider_id = cur.lastrowid
            self.db().execute("INSERT INTO test_configs (provider_id, test_model) VALUES (?, '')", (provider_id,))
            return self.provider_detail(provider_id)

    def update_provider(self, provider_id, payload):
        name = require_text(payload.get("name"), "供应商名称")
        base_url = validate_url(payload.get("base_url"))
        api_format = normalize_formats(payload.get("api_formats") or payload.get("api_format"))
        with self._lock:
            self._provider(provider_id)
            self.db().execute(
                """
                UPDATE llm_providers
                SET name = ?, base_url = ?, api_format = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (name, base_url, api_format, provider_id),
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
            row.pop("is_active", None)
            row["masked_key"] = mask_secret(row["api_key"])
        return rows

    def add_key(self, provider_id, payload):
        self._provider(provider_id)
        key_name = require_text(payload.get("key_name"), "密钥别名")
        api_key = require_text(payload.get("api_key"), "API密钥")
        sort_order = self._next_sort_order("api_keys", "provider_id", provider_id)
        cur = self.db().execute(
            """
            INSERT INTO api_keys (provider_id, key_name, api_key, is_active, test_status, sort_order)
            VALUES (?, ?, ?, ?, 'untested', ?)
            """,
            (provider_id, key_name, api_key, 1, sort_order),
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

    def generic_categories(self):
        self._sync_generic_categories()
        rows = self.db().query_all(
            """
            SELECT g.*
            FROM generic_keys g
            LEFT JOIN generic_categories c ON c.category = g.category
            ORDER BY COALESCE(c.sort_order, 999999), g.category, g.sort_order, g.id
            """
        )
        categories = {}
        for row in rows:
            row["masked_value"] = mask_secret(row["key_value"])
            categories.setdefault(row["category"], []).append(row)
        return [{"category": category, "items": items} for category, items in categories.items()]

    def add_generic_key(self, payload):
        category = require_text(payload.get("category"), "类别名称")
        key_name = require_text(payload.get("key_name"), "键名")
        key_value = require_text(payload.get("key_value"), "键值")
        description = str(payload.get("description") or "").strip()
        self._ensure_generic_category(category)
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
        self._ensure_generic_category(category)
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
            self._cleanup_generic_category(old["category"])
            self._renumber_table("generic_keys", "category", old["category"])
            self._renumber_table("generic_keys", "category", category)
        return self._generic_key(item_id)

    def delete_generic_key(self, item_id):
        row = self._generic_key(item_id)
        self.db().execute("DELETE FROM generic_keys WHERE id = ?", (item_id,))
        self._renumber_table("generic_keys", "category", row["category"])
        self._cleanup_generic_category(row["category"])

    def delete_generic_category(self, category):
        category = require_text(category, "类别名称")
        self.db().execute("DELETE FROM generic_keys WHERE category = ?", (category,))
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
        row.pop("is_active", None)
        row["masked_key"] = mask_secret(row["api_key"])
        return row

    def _generic_key(self, item_id):
        row = self.db().query_one("SELECT * FROM generic_keys WHERE id = ?", (item_id,))
        if not row:
            raise ValueError("键值对不存在")
        row["masked_value"] = mask_secret(row["key_value"])
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

    def _ensure_generic_category(self, category):
        exists = self.db().query_one("SELECT category FROM generic_categories WHERE category = ?", (category,))
        if exists:
            return
        sort_order = self._next_sort_order("generic_categories")
        self.db().execute(
            "INSERT INTO generic_categories (category, sort_order) VALUES (?, ?)",
            (category, sort_order),
        )

    def _cleanup_generic_category(self, category):
        count = self.db().query_one("SELECT COUNT(*) AS count FROM generic_keys WHERE category = ?", (category,))
        if count and count["count"] == 0:
            self.db().execute("DELETE FROM generic_categories WHERE category = ?", (category,))

    def _sync_generic_categories(self):
        rows = self.db().query_all("SELECT DISTINCT category FROM generic_keys ORDER BY category")
        for row in rows:
            self._ensure_generic_category(row["category"])
