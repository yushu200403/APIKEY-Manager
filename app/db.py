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
        self.conn.commit()

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
    website_url TEXT DEFAULT '',
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

CREATE TABLE IF NOT EXISTS generic_categories (
    category TEXT PRIMARY KEY,
    description TEXT DEFAULT '',
    sort_order INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS generic_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    key_name TEXT NOT NULL,
    key_value TEXT NOT NULL,
    description TEXT,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key_name),
    FOREIGN KEY (category) REFERENCES generic_categories(category) ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_api_keys_provider ON api_keys(provider_id);
CREATE INDEX IF NOT EXISTS idx_test_configs_provider ON test_configs(provider_id);
CREATE INDEX IF NOT EXISTS idx_model_cache_provider ON model_cache(provider_id);
CREATE INDEX IF NOT EXISTS idx_generic_keys_category ON generic_keys(category);
"""
