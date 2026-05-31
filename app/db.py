import json
import os
import platform
from pathlib import Path


class DatabaseDependencyError(RuntimeError):
    pass


def _load_sqlcipher():
    try:
        from pysqlcipher3 import dbapi2 as sqlite
        return sqlite
    except ImportError:
        pass
    try:
        from sqlcipher3 import dbapi2 as sqlite
        return sqlite
    except ImportError as exc:
        raise DatabaseDependencyError(
            "缺少 SQLCipher 依赖 pysqlcipher3 或 sqlcipher3，数据库无法加密打开。请先运行：pip install -r requirements.txt"
        ) from exc


def app_data_dir():
    custom_dir = os.environ.get("APIKEY_MANAGER_DATA_DIR")
    if custom_dir:
        path = Path(custom_dir)
    elif platform.system() == "Windows":
        path = Path(os.environ.get("APPDATA", Path.home())) / "APIKEY-Manager"
    elif platform.system() == "Darwin":
        path = Path.home() / "Library" / "Application Support" / "APIKEY-Manager"
    else:
        path = Path.home() / ".apikey-manager"
    path.mkdir(parents=True, exist_ok=True)
    return path


def database_path():
    return app_data_dir() / "apikeys.db"


def _quote_pragma_value(value):
    return "'" + value.replace("'", "''") + "'"


class EncryptedDatabase:
    def __init__(self, password, path=None):
        self.password = password
        self.path = Path(path) if path else database_path()
        self.sqlite = _load_sqlcipher()
        self.conn = None

    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self.sqlite.connect(str(self.path), check_same_thread=False)
        conn.row_factory = self.sqlite.Row
        conn.execute(f"PRAGMA key = {_quote_pragma_value(self.password)}")
        conn.execute("PRAGMA cipher_page_size = 4096")
        conn.execute("PRAGMA kdf_iter = 256000")
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        except Exception as exc:
            conn.close()
            raise ValueError("主密码错误，或数据库文件已损坏") from exc
        self.conn = conn
        return self

    def initialize(self):
        self.conn.executescript(SCHEMA_SQL)
        self._migrate()
        self.conn.commit()

    def _migrate(self):
        self._add_column_if_missing("llm_providers", "sort_order", "INTEGER DEFAULT 0")
        self._add_column_if_missing("llm_providers", "test_key_id", "INTEGER")
        self._add_column_if_missing("api_keys", "sort_order", "INTEGER DEFAULT 0")
        self._add_column_if_missing("generic_keys", "sort_order", "INTEGER DEFAULT 0")
        self.conn.execute("UPDATE llm_providers SET api_format = REPLACE(api_format, 'openai_chat', 'openai_response')")
        self.conn.execute(
            """
            INSERT OR IGNORE INTO app_settings (id, system_prompt, user_prompt)
            VALUES (1, '你是一个有帮助的助手。', '你是什么模型？请用一句话回答。')
            """
        )
        app_setting_columns = self._column_names("app_settings")
        if "test_model" in app_setting_columns:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO test_configs (provider_id, test_model)
                SELECT id, COALESCE((SELECT test_model FROM app_settings WHERE id = 1), '')
                FROM llm_providers
                """
            )
        else:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO test_configs (provider_id, test_model)
                SELECT id, ''
                FROM llm_providers
                """
            )
        self._normalize_sort_order("llm_providers", "id", None)
        self._normalize_sort_order("api_keys", "id", "provider_id")
        self._normalize_sort_order("generic_keys", "id", "category")
        self._sync_generic_categories()

    def _add_column_if_missing(self, table, column, definition):
        if column not in self._column_names(table):
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

    def _column_names(self, table):
        rows = self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row["name"] for row in rows}

    def _normalize_sort_order(self, table, id_column, group_column):
        if group_column:
            groups = self.conn.execute(f"SELECT DISTINCT {group_column} AS group_value FROM {table}").fetchall()
            for group in groups:
                rows = self.conn.execute(
                    f"SELECT {id_column} AS item_id FROM {table} WHERE {group_column} = ? ORDER BY sort_order, {id_column}",
                    (group["group_value"],),
                ).fetchall()
                for index, row in enumerate(rows, start=1):
                    self.conn.execute(f"UPDATE {table} SET sort_order = ? WHERE {id_column} = ?", (index, row["item_id"]))
            return
        rows = self.conn.execute(f"SELECT {id_column} AS item_id FROM {table} ORDER BY sort_order, {id_column}").fetchall()
        for index, row in enumerate(rows, start=1):
            self.conn.execute(f"UPDATE {table} SET sort_order = ? WHERE {id_column} = ?", (index, row["item_id"]))

    def _sync_generic_categories(self):
        rows = self.conn.execute(
            """
            SELECT category, MIN(sort_order) AS first_order
            FROM generic_keys
            GROUP BY category
            ORDER BY first_order, category
            """
        ).fetchall()
        for index, row in enumerate(rows, start=1):
            self.conn.execute(
                "INSERT OR IGNORE INTO generic_categories (category, sort_order) VALUES (?, ?)",
                (row["category"], index),
            )

    def close(self):
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def execute(self, sql, params=()):
        cur = self.conn.execute(sql, params)
        self.conn.commit()
        return cur

    def query_one(self, sql, params=()):
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def query_all(self, sql, params=()):
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def upsert_model_cache(self, provider_id, model_ids):
        payload = json.dumps(model_ids, ensure_ascii=False)
        existing = self.query_one("SELECT id FROM model_cache WHERE provider_id = ?", (provider_id,))
        if existing:
            self.execute(
                "UPDATE model_cache SET model_ids = ?, last_fetched = CURRENT_TIMESTAMP WHERE provider_id = ?",
                (payload, provider_id),
            )
        else:
            self.execute(
                "INSERT INTO model_cache (provider_id, model_ids, last_fetched) VALUES (?, ?, CURRENT_TIMESTAMP)",
                (provider_id, payload),
            )


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS llm_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    base_url TEXT NOT NULL,
    api_format TEXT NOT NULL,
    test_key_id INTEGER,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (test_key_id) REFERENCES api_keys(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL,
    key_name TEXT NOT NULL,
    api_key TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    last_tested TIMESTAMP,
    test_status TEXT DEFAULT 'untested',
    test_message TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (provider_id) REFERENCES llm_providers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    system_prompt TEXT DEFAULT '你是一个有帮助的助手。',
    user_prompt TEXT DEFAULT '你是什么模型？请用一句话回答。'
);

CREATE TABLE IF NOT EXISTS test_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL UNIQUE,
    test_model TEXT,
    FOREIGN KEY (provider_id) REFERENCES llm_providers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS model_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL UNIQUE,
    model_ids TEXT NOT NULL,
    last_fetched TIMESTAMP,
    FOREIGN KEY (provider_id) REFERENCES llm_providers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS generic_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    key_name TEXT NOT NULL,
    key_value TEXT NOT NULL,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key_name)
);

CREATE TABLE IF NOT EXISTS generic_categories (
    category TEXT PRIMARY KEY,
    sort_order INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_api_keys_provider ON api_keys(provider_id);
CREATE INDEX IF NOT EXISTS idx_test_configs_provider ON test_configs(provider_id);
CREATE INDEX IF NOT EXISTS idx_model_cache_provider ON model_cache(provider_id);
CREATE INDEX IF NOT EXISTS idx_generic_keys_category ON generic_keys(category);
"""
