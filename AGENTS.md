# AGENTS.md — APIKEY-Manager

> 致所有AI Agent：对代码进行任何修改后，一定注意同步维护本上下文。

## 项目概述

本地 API Key 管理工具（Flask 桌面应用），使用 SQLCipher 加密数据库存储大模型 API Key 与通用密钥对，支持密钥测试、模型列表获取、数据导出导入。

- **语言**: Python 3
- **框架**: Flask 3.0
- **数据库**: SQLCipher（通过 `pysqlcipher3` / `sqlcipher3`）
- **打包**: PyInstaller（`python build_pyinstaller.py`）

---

## 构建 / 检查 / 测试命令

```bash
# 安装依赖
pip install -r requirements.txt

# 运行开发服务器（控制台模式，自动打开浏览器）
python run.py

# 运行全部测试
python -m unittest discover -s tests -v

# 运行单个测试文件
python -m unittest tests.test_validators -v

# 运行单个测试类
python -m unittest tests.test_validators.ValidatorTests -v

# 运行单个测试方法
python -m unittest tests.test_validators.ValidatorTests.test_mask_secret_keeps_edges -v

# PyInstaller 打包（输出到项目根目录）
python build_pyinstaller.py

# 打包为隐藏控制台窗口的模式
python build_pyinstaller.py --windowed

# 自定义产物名称
python build_pyinstaller.py --name MyAPIKEY-Manager
```

> **说明**: 项目没有 `pyproject.toml`、`setup.py`、`Makefile` 或 `tox.ini`；测试框架为标准库 `unittest`，无额外 linter/formatter 配置。

---

## 项目结构

```
APIKEY-Manager/
├── run.py                  # 应用入口，启动 Flask + 打开浏览器
├── build_pyinstaller.py    # PyInstaller 打包脚本
├── requirements.txt        # Flask==3.0.3 / sqlcipher3==0.6.2 / requests==2.32.3
├── app/
│   ├── __init__.py         # create_app() 工厂，注册蓝图 + Store
│   ├── routes.py           # Flask Blueprint API 路由（/api/*）
│   ├── store.py            # 核心业务逻辑（Store 类，线程安全）
│   ├── db.py               # EncryptedDatabase，SQLCipher 封装 + Schema
│   ├── api_client.py       # HTTP 客户端：密钥测试 + 模型列表获取
│   ├── validators.py       # 校验与格式化工具函数
│   ├── templates/          # Jinja2 前端模板
│   └── static/             # 静态资源（含图标字体）
└── tests/
    ├── test_validators.py  # 校验函数单元测试
    ├── test_api_client.py  # API 客户端单元测试（mock HTTP）
    └── test_app_flow.py    # Flask 集成测试（test_client）
```

---

## 代码风格

### 导入规范

遵从 Python 标准：标准库 → 第三方库 → 本地模块，每组之间换行。

```python
# 正确
import json
import threading
from datetime import datetime

from .api_client import fetch_model_ids
from .db import EncryptedDatabase
from .validators import require_text, validate_url
```

### 命名约定

| 类型 | 风格 | 示例 |
|------|------|------|
| 模块 / 文件 | snake_case | `api_client.py`, `build_pyinstaller.py` |
| 函数 / 方法 | snake_case | `create_app()`, `test_chat_endpoint()` |
| 类 | PascalCase | `Store`, `EncryptedDatabase`, `TestResult` |
| 私有函数 | `_` 前缀 snake_case | `_headers()`, `_next_sort_order()` |
| 常量 | UPPER_SNAKE_CASE | `TIMEOUT_SECONDS`, `SUPPORTED_FORMATS` |
| 模块级变量 | 可读 snake_case | `api_bp = Blueprint(...)` |
| 数据库字段 | 蛇形命名 | `provider_id`, `test_key_id`, `last_fetched` |

### 格式化

- 缩进: 4 空格，无 Tab
- 行长: 无硬性限制，但建议保持合理长度
- 字符串: 优先使用双引号 `"..."`；SQL 用三引号 `"""..."""`
- f-string 用于插值；模板文本用 Jinja2
- 末尾无空格，文件末尾保留一个换行符
- `dict` / `list` 逗号后空格，操作符两侧空格

### 类型注解

当前项目未使用类型注解，遵循现有风格即可——如需添加，使用内置类型：

```python
from typing import Optional

def mask_secret(value: str) -> str:
    ...
```

### 异常处理

- **用户可见错误** → `raise ValueError("中文提示")`，`routes.py` 中的 `@handle_errors` 装饰器将 `ValueError` 映射为 400 响应
- **系统级错误** → `raise RuntimeError(...)` 或自定义异常（如 `DatabaseDependencyError`），装饰器映射为 500 响应
- 外部调用用 `try/except` 包装后转为 `ValueError`：
  ```python
  try:
      response = requests.request(...)
  except requests.Timeout as exc:
      raise ValueError("网络请求超时") from exc
  except requests.RequestException as exc:
      raise ValueError(f"网络请求失败：{exc}") from exc
  ```
- **链式异常**: 始终使用 `from exc`，保留完整 traceback

### 错误处理架构

`routes.py:21` 中的 `@handle_errors` 装饰器是统一的 API 错误处理层，所有路由函数均使用该装饰器：

```python
@api_bp.post("/create")
@handle_errors
def create_database():
    ...
```

响应格式：
- 成功: `{"ok": true, "data": ...}`
- 失败: `{"ok": false, "error": "..."}`，状态码 400 或 500

### 数据库操作模式

- 使用 `contextlib` 风格的 `with self._lock:` 包裹写操作（`store.py` 中 `threading.RLock`）
- CRUD 通过 `Store.db().query_one()` / `query_all()` / `execute()` 进行
- 导入使用显式事务 `BEGIN` / `COMMIT` / `ROLLBACK`
- 删除后调用 `_renumber_table()` 重排 `sort_order`

### 其他约定

- **dataclass**: 用于数据传输对象，如 `TestResult`（`api_client.py:12`）
- **Flask Blueprint**: 所有 API 路由以 `/api` 为前缀，在 `__init__.py:10` 注册
- **Store 单例**: 通过 `current_app.store` 访问，路由中使用 `store()` 便捷函数
- **密钥掩码**: 所有需要脱敏的字段通过 `mask_secret()` 处理（显示前4后4字符）
- **配置驱动**: 数据目录通过 `APIKEY_MANAGER_DATA_DIR` 环境变量自定义
- **中文界面**: 所有面向用户的字符串（异常消息、响应文本）均使用中文
- **无注释**: 代码不写注释，以可读的函数/变量命名代替
