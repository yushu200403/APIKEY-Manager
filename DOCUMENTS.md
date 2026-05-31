APIKEY管理器项目规划文档

### 1.1 项目简介

APIKEY管理器是一个基于本地加密数据库的密钥管理工具，主要用于管理和测试**大模型API密钥**，同时支持其他类型API接口的存储。

### 1.2 核心功能

- 大模型API端点和密钥的安全存储
- 多种API格式支持（OpenAI、Anthropic等）
- API密钥有效性测试
- 模型列表获取与缓存
- 通用键值对存储（支持其他类型API）
- 一键复制功能

### 1.3 技术特点

- 本地运行，无需网络服务
- SQLite加密数据库，基于用户密码保护
- 跨平台支持（Windows/macOS/Linux）

---

## 2. 技术架构

### 2.1 技术栈选择

#### 主方案：Tauri

- **前端**: HTML + CSS + JavaScript (Vanilla JS 或轻量框架)
- **后端**: Rust (Tauri)
- **数据库**: SQLite + SQLCipher
- **打包**: Tauri 原生打包

#### 备选方案：Flask (如Tauri不可行)

- **前端**: HTML + CSS + JavaScript
- **后端**: Python + Flask
- **数据库**: SQLite + SQLCipher (pysqlcipher3)
- **打包**: PyInstaller

### 2.2 架构设计

```
┌─────────────────────────────────────┐
│         用户界面层 (UI)              │
│   - 密码输入界面                     │
│   - 主管理界面                       │
│   - 测试结果展示                     │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│       业务逻辑层 (Backend)           │
│   - 密钥管理服务                     │
│   - API测试服务                      │
│   - 加密/解密服务                    │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│       数据持久层 (Database)          │
│   - SQLite + SQLCipher               │
│   - 加密存储                         │
└─────────────────────────────────────┘
```

---

## 3. 数据库设计

### 3.1 加密方案

**选用方案**: SQLCipher

- **加密算法**: AES-256
- **密钥派生**: PBKDF2-HMAC-SHA512
- **密钥来源**: 用户密码直接派生
- **实现方式**:
  - Tauri方案: 使用 `rusqlite` + `sqlcipher` crate
  - Flask方案: 使用 `pysqlcipher3` 库

**密码处理流程**:

1. 用户首次创建数据库时输入密码
2. 使用PBKDF2对密码进行派生（迭代次数: 256000）
3. 派生密钥用于SQLCipher加密
4. 每次打开应用需重新输入密码解密数据库

### 3.2 数据表结构

#### 表1: llm_providers (大模型供应商)

```sql
CREATE TABLE llm_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,              -- 供应商名称 (如 "OpenAI", "Anthropic")
    base_url TEXT NOT NULL,                 -- API端点 (如 "https://api.openai.com/v1")
    api_format TEXT NOT NULL,               -- API格式 (多选，逗号分隔: "openai_chat,openai_completion,anthropic_message")
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### 表2: api_keys (API密钥)

```sql
CREATE TABLE api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL,           -- 关联供应商ID
    key_name TEXT NOT NULL,                 -- 密钥别名 (如 "主账号Key1")
    api_key TEXT NOT NULL,                  -- API密钥
    is_active BOOLEAN DEFAULT 1,            -- 是否启用
    last_tested TIMESTAMP,                  -- 上次测试时间
    test_status TEXT,                       -- 测试状态 (success/failed/untested)
    test_message TEXT,                      -- 测试结果消息
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (provider_id) REFERENCES llm_providers(id) ON DELETE CASCADE
);
```

#### 表3: test_configs (测试配置)

```sql
CREATE TABLE test_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL,           -- 关联供应商ID
    test_model TEXT,                        -- 用于测试的模型名称
    system_prompt TEXT DEFAULT 'You are a helpful assistant.',
    user_prompt TEXT DEFAULT 'Say "Hello, World!" in one sentence.',
    FOREIGN KEY (provider_id) REFERENCES llm_providers(id) ON DELETE CASCADE
);
```

#### 表4: model_cache (模型列表缓存)

```sql
CREATE TABLE model_cache (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider_id INTEGER NOT NULL,           -- 关联供应商ID
    model_ids TEXT NOT NULL,                -- 模型ID列表 (JSON数组格式)
    last_fetched TIMESTAMP,                 -- 上次获取时间
    FOREIGN KEY (provider_id) REFERENCES llm_providers(id) ON DELETE CASCADE
);
```

#### 表5: generic_keys (通用键值对存储)

```sql
CREATE TABLE generic_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,                 -- 类别名称 (如 "Tavily", "QQ机器人")
    key_name TEXT NOT NULL,                 -- 键名 (如 "api_key", "app_id", "app_secret")
    key_value TEXT NOT NULL,                -- 键值
    description TEXT,                       -- 描述信息
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(category, key_name)
);
```

### 3.3 索引设计

```sql
CREATE INDEX idx_api_keys_provider ON api_keys(provider_id);
CREATE INDEX idx_test_configs_provider ON test_configs(provider_id);
CREATE INDEX idx_model_cache_provider ON model_cache(provider_id);
CREATE INDEX idx_generic_keys_category ON generic_keys(category);
```

---

## 4. 功能模块设计

### 4.1 认证模块

#### 4.1.1 首次启动流程

1. 检测数据库文件是否存在
2. 不存在则显示"创建密码"界面
3. 用户输入密码（需二次确认）
4. 使用密码创建加密数据库
5. 初始化数据表结构

#### 4.1.2 后续启动流程

1. 显示"输入密码"界面
2. 用户输入密码
3. 尝试使用密码打开数据库
4. 成功则进入主界面，失败则提示错误

#### 4.1.3 密码验证

- 密码最小长度: 8字符
- 建议包含大小写字母、数字、特殊字符
- 密码错误3次后延迟5秒再允许重试

### 4.2 大模型管理模块

#### 4.2.1 供应商管理

**功能**:

- 添加新供应商（名称、端点、API格式）
- 编辑供应商信息
- 删除供应商（级联删除关联数据）
- 查看供应商列表
- 页面左侧边栏为模型供应商列表，右侧为具体参数配置

**API格式支持**:

- `openai_chat`: OpenAI Chat Completions API
- `openai_completion`: OpenAI Completions API (legacy)
- `anthropic_message`: Anthropic Messages API

**界面元素**:

- 供应商列表（左侧边栏）
- 添加/编辑表单
- API格式多选框

#### 4.2.2 密钥管理

**功能**:

- 为供应商添加多个API密钥
- 为密钥设置别名
- 启用/禁用密钥
- 删除密钥
- 一键复制密钥

**界面元素**:

- 密钥列表（表格形式）
- 复制按钮（点击复制到剪贴板）
- 状态指示器（启用/禁用/测试状态）

#### 4.2.3 测试配置

**功能**:

- 为每个供应商配置测试参数
- 自定义system prompt和user prompt
- 选择测试用模型

**默认配置**:

```json
{
  "system_prompt": "You are a helpful assistant.",
  "user_prompt": "Say 'Hello, World!' in one sentence.",
  "test_model": "" // 用户需手动指定
}
```

### 4.3 API测试模块

#### 4.3.1 聊天端点测试

**测试流程**:

1. 用户选择要测试的密钥
2. 系统读取测试配置
3. 根据API格式构造请求
4. 发送测试请求
5. 记录测试结果和时间戳
6. 更新密钥测试状态

**请求构造示例**:

**OpenAI Chat格式**:

```json
POST {base_url}/chat/completions
Headers: {
  "Authorization": "Bearer {api_key}",
  "Content-Type": "application/json"
}
Body: {
  "model": "{test_model}",
  "messages": [
    {"role": "system", "content": "{system_prompt}"},
    {"role": "user", "content": "{user_prompt}"}
  ],
  "max_tokens": 50
}
```

**Anthropic Messages格式**:

```json
POST {base_url}/messages
Headers: {
  "x-api-key": "{api_key}",
  "anthropic-version": "2023-06-01",
  "Content-Type": "application/json"
}
Body: {
  "model": "{test_model}",
  "system": "{system_prompt}",
  "messages": [
    {"role": "user", "content": "{user_prompt}"}
  ],
  "max_tokens": 50
}
```

**测试结果**:

- 成功: 显示响应内容摘要
- 失败: 显示错误信息（HTTP状态码、错误消息）

#### 4.3.2 模型列表获取

**测试流程**:

1. 用户点击"刷新模型列表"
2. 系统选择一个有效密钥
3. 根据API格式发送请求
4. 解析响应获取模型ID列表
5. 存储到model_cache表
6. 更新last_fetched时间戳
7. 在界面显示模型列表

**请求构造示例**:

**OpenAI格式**:

```
GET {base_url}/models
Headers: {
  "Authorization": "Bearer {api_key}"
}
```

**Anthropic格式**:

```
GET {base_url}/models
Headers: {
  "x-api-key": "{api_key}",
  "anthropic-version": "2023-06-01"
}
```

**界面展示**:

- 模型ID列表（可滚动）
- 每个模型ID旁边有复制按钮
- 显示上次获取时间
- 手动刷新按钮

### 4.4 通用键值对模块

#### 4.4.1 类别管理

**功能**:

- 创建新类别（如"Tavily"、"QQ机器人"）
- 删除类别（级联删除所有键值对）
- 查看类别列表
- 页面的左侧边栏为类别，右侧为键值对管理

#### 4.4.2 键值对管理

**功能**:

- 在类别下添加键值对
- 编辑键值对
- 删除键值对
- 一键复制键值

**示例数据**:

```
类别: Tavily
  - api_key: tvly-xxxxxxxxxxxxx

类别: QQ机器人
  - app_id: 123456789
  - app_secret: abcdef123456
```

### 4.5 复制功能实现

**技术实现**:

- Tauri: 使用 `tauri::api::clipboard` API
- Flask: 使用前端 `navigator.clipboard.writeText()` API

**用户体验**:

- 点击复制按钮后显示"已复制"提示
- 提示2秒后自动消失
- 支持键盘快捷键（Ctrl+C）

---

## 5. 用户界面设计

### 5.1 设计风格

- **风格参考**: Windows 10 系统应用
- **色彩方案**: 
  - 主色: #0078D4 (Windows蓝)
  - 背景: #F3F3F3 (浅灰)
  - 文字: #000000 / #666666
  - 边框: #E1E1E1
- **字体**: Segoe UI (Windows) / San Francisco (macOS) / Ubuntu (Linux)
- **布局**: 左侧导航栏 + 右侧内容区

### 5.2 界面结构

```
┌─────────────────────────────────────────────────┐
│  APIKEY管理器                          [_][□][×] │
├──────────┬──────────────────────────────────────┤
│          │                                      │
│  导航栏   │           内容区域                    │
│          │                                      │
│ 大模型    │  ┌────────────────────────────┐     │
│ 通用密钥  │  │                            │     │
│ 设置      │  │                            │     │
│          │  │                            │     │
│          │  │                            │     │
│          │  └────────────────────────────┘     │
│          │                                      │
└──────────┴──────────────────────────────────────┘
```

### 5.3 主要界面

#### 5.3.1 登录界面

```
┌─────────────────────────────┐
│                             │
│      APIKEY管理器            │
│                             │
│   ┌─────────────────────┐   │
│   │ 密码: [__________]  │   │
│   └─────────────────────┘   │
│                             │
│        [  解锁  ]           │
│                             │
└─────────────────────────────┘
```

#### 5.3.2 大模型管理界面

```
┌─────────────────────────────────────────────┐
│ 供应商列表                    [+ 添加供应商]  │
├─────────────────────────────────────────────┤
│ ▼ OpenAI                                    │
│   端点: https://api.openai.com/v1  [复制]   │
│   格式: OpenAI Chat, OpenAI Completion      │
│                                             │
│   API密钥:                                  │
│   ┌───────────────────────────────────┐    │
│   │ 名称      │ 密钥          │ 状态  │    │
│   ├───────────────────────────────────┤    │
│   │ 主账号Key1│ sk-xxx... [复制] │ ✓  │    │
│   │ 备用Key2  │ sk-yyy... [复制] │ ✗  │    │
│   └───────────────────────────────────┘    │
│   [+ 添加密钥] [测试选中密钥]               │
│                                             │
│   测试配置:                                 │
│   测试模型: [gpt-4o-mini        ▼]         │
│   System: [You are a helpful...  ]         │
│   User:   [Say "Hello, World!"   ]         │
│   [保存配置]                                │
│                                             │
│   模型列表: (上次获取: 2025-01-15 10:30)    │
│   ┌───────────────────────────────────┐    │
│   │ gpt-4o              [复制]        │    │
│   │ gpt-4o-mini         [复制]        │    │
│   │ gpt-3.5-turbo       [复制]        │    │
│   └───────────────────────────────────┘    │
│   [刷新模型列表]                            │
└─────────────────────────────────────────────┘
```

#### 5.3.3 通用密钥界面

```
┌─────────────────────────────────────────────┐
│ 类别列表                      [+ 添加类别]   │
├─────────────────────────────────────────────┤
│ ▼ Tavily                                    │
│   ┌───────────────────────────────────┐    │
│   │ 键名      │ 键值          │       │    │
│   ├───────────────────────────────────┤    │
│   │ api_key   │ tvly-xxx... [复制]    │    │
│   └───────────────────────────────────┘    │
│   [+ 添加键值对]                            │
│                                             │
│ ▼ QQ机器人                                  │
│   ┌───────────────────────────────────┐    │
│   │ 键名        │ 键值        │       │    │
│   ├───────────────────────────────────┤    │
│   │ app_id      │ 123456... [复制]    │    │
│   │ app_secret  │ abcdef... [复制]    │    │
│   └───────────────────────────────────┘    │
│   [+ 添加键值对]                            │
└─────────────────────────────────────────────┘
```

### 6.1 Tauri实现方案

#### 6.1.1 项目结构

```
apikey-manager/
├── src-tauri/
│   ├── src/
│   │   ├── main.rs              # 主入口
│   │   ├── db.rs                # 数据库操作
│   │   ├── crypto.rs            # 加密解密
│   │   ├── api_test.rs          # API测试
│   │   └── commands.rs          # Tauri命令
│   ├── Cargo.toml
│   └── tauri.conf.json
├── src/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   └── components/
│       ├── login.js
│       ├── llm-manager.js
│       └── generic-keys.js
└── package.json
```

#### 6.1.2 核心依赖 (Cargo.toml)

```toml
[dependencies]
tauri = { version = "1.5", features = ["clipboard-all", "dialog-all"] }
rusqlite = { version = "0.30", features = ["bundled-sqlcipher"] }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
reqwest = { version = "0.11", features = ["json"] }
tokio = { version = "1", features = ["full"] }
```

#### 6.1.3 数据库初始化 (db.rs)

```rust
use rusqlite::{Connection, Result};

pub fn init_database(password: &str) -> Result<Connection> {
    let conn = Connection::open("apikeys.db")?;

    // 设置加密密钥
    conn.execute(&format!("PRAGMA key = '{}'", password), [])?;
    conn.execute("PRAGMA cipher_page_size = 4096", [])?;
    conn.execute("PRAGMA kdf_iter = 256000", [])?;

    // 创建表结构
    conn.execute_batch(
        "CREATE TABLE IF NOT EXISTS llm_providers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            base_url TEXT NOT NULL,
            api_format TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_id INTEGER NOT NULL,
            key_name TEXT NOT NULL,
            api_key TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 1,
            last_tested TIMESTAMP,
            test_status TEXT,
            test_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (provider_id) REFERENCES llm_providers(id) ON DELETE CASCADE
        );

        -- 其他表创建语句...
        "
    )?;

    Ok(conn)
}
```

#### 6.1.4 Tauri命令示例 (commands.rs)

```rust
use tauri::State;
use std::sync::Mutex;

#[tauri::command]
pub async fn unlock_database(password: String, state: State<'_, Mutex<Option<Connection>>>) -> Result<bool, String> {
    match init_database(&password) {
        Ok(conn) => {
            *state.lock().unwrap() = Some(conn);
            Ok(true)
        }
        Err(e) => Err(format!("密码错误: {}", e))
    }
}

#[tauri::command]
pub async fn add_provider(
    name: String,
    base_url: String,
    api_format: String,
    state: State<'_, Mutex<Option<Connection>>>
) -> Result<i64, String> {
    let conn = state.lock().unwrap();
    let conn = conn.as_ref().ok_or("数据库未解锁")?;

    conn.execute(
        "INSERT INTO llm_providers (name, base_url, api_format) VALUES (?1, ?2, ?3)",
        [&name, &base_url, &api_format],
    ).map_err(|e| e.to_string())?;

    Ok(conn.last_insert_rowid())
}

#[tauri::command]
pub async fn test_api_key(
    provider_id: i64,
    api_key_id: i64,
    state: State<'_, Mutex<Option<Connection>>>
) -> Result<String, String> {
    // 实现API测试逻辑
    // 1. 从数据库读取配置
    // 2. 构造HTTP请求
    // 3. 发送请求并处理响应
    // 4. 更新测试状态
    Ok("测试成功".to_string())
}
```

#### 6.1.5 前端调用示例 (app.js)

```
const { invoke } = window.__TAURI__.tauri;

async function unlockDatabase() {
    const password = document.getElementById('password').value;
    try {
        const success = await invoke('unlock_database', { password });
        if (success) {
            showMainInterface();
        }
    } catch (error) {
        alert('密码错误: ' + error);
    }
}

async function addProvider() {
    const name = document.getElementById('provider-name').value;
    const baseUrl = document.getElementById('base-url').value;
    const apiFormat = getSelectedFormats(); // 获取多选框值
    
    try {
        const id = await invoke('add_provider', { name, baseUrl, apiFormat });
        alert('供应商添加成功，ID: ' + id);
        refreshProviderList();
    } catch (error) {
        alert('添加失败: ' + error);
    }
}

async function copyToClipboard(text) {
    await invoke('write_clipboard', { text });
```

## 6. 系统运作逻辑

### 6.1 应用启动流程

#### 6.1.1 首次启动

1. 应用检测本地是否存在数据库文件（apikeys.db）
2. 如果不存在，显示"创建主密码"界面
3. 用户输入密码并确认（两次输入必须一致）
4. 系统验证密码强度（至少8字符）
5. 使用用户密码通过PBKDF2算法派生加密密钥
6. 创建加密的SQLite数据库文件
7. 初始化所有数据表结构和索引
8. 自动进入主界面（无需再次输入密码）

#### 6.1.2 后续启动

1. 应用检测到数据库文件已存在
2. 显示"输入密码"界面
3. 用户输入密码
4. 系统尝试使用该密码解密数据库
5. 如果密码正确，成功打开数据库连接，进入主界面
6. 如果密码错误，显示错误提示，允许重新输入
7. 连续3次密码错误后，强制等待5秒才能再次尝试

#### 6.1.3 数据库连接管理

- 数据库连接在应用运行期间保持打开状态
- 应用关闭时自动关闭数据库连接
- 数据库文件保存在应用数据目录（用户目录下的隐藏文件夹）
- 不支持同时打开多个数据库实例

### 6.2 大模型供应商管理流程

#### 6.2.1 添加供应商

1. 用户点击"添加供应商"按钮
2. 弹出表单对话框，包含以下字段：
   - 供应商名称（必填，唯一）
   - API端点URL（必填）
   - API格式（多选框，至少选一个）
3. 用户填写信息并提交
4. 系统验证：
   - 名称不能与现有供应商重复
   - URL格式必须合法（http/https开头）
   - 至少选择一种API格式
5. 验证通过后，将数据插入llm_providers表
6. 自动为该供应商创建默认测试配置（使用默认的system和user prompt）
7. 刷新供应商列表，新供应商显示在列表中

#### 6.2.2 编辑供应商

1. 用户点击供应商旁的"编辑"按钮
2. 弹出预填充当前信息的表单
3. 用户修改信息并提交
4. 系统执行相同的验证逻辑
5. 更新数据库中的记录，同时更新updated_at时间戳
6. 刷新界面显示

#### 6.2.3 删除供应商

1. 用户点击"删除"按钮
2. 系统弹出确认对话框，提示将同时删除：
   - 该供应商下的所有API密钥
   - 测试配置
   - 模型列表缓存
3. 用户确认后执行删除
4. 数据库通过外键级联删除相关数据
5. 刷新界面，供应商从列表中消失

### 6.3 API密钥管理流程

#### 6.3.1 添加密钥

1. 用户在某个供应商下点击"添加密钥"
2. 弹出表单，包含：
   - 密钥别名（必填，用于区分多个密钥）
   - API密钥内容（必填）
   - 是否启用（默认启用）
3. 用户提交后，系统将密钥插入api_keys表
4. 初始测试状态为"未测试"
5. 密钥显示在该供应商的密钥列表中

#### 6.3.2 复制密钥

1. 用户点击密钥旁的"复制"按钮
2. 系统将密钥内容写入系统剪贴板
3. 按钮旁显示"已复制"提示（2秒后消失）
4. 用户可以在其他应用中粘贴使用

#### 6.3.3 启用/禁用密钥

1. 用户点击密钥的启用开关
2. 系统更新数据库中的is_active字段
3. 禁用的密钥在测试时会被跳过
4. 界面上禁用的密钥显示为灰色或带有禁用标识

#### 6.3.4 删除密钥

1. 用户点击"删除"按钮
2. 系统弹出确认对话框
3. 确认后从数据库删除该密钥记录
4. 刷新密钥列表

### 6.4 API测试流程

#### 6.4.1 聊天端点测试

**测试准备**：

1. 用户选择要测试的密钥（可单选或多选）
2. 系统检查该供应商是否配置了测试参数
3. 如果未配置测试模型，提示用户先配置

**测试执行**：

1. 系统读取供应商的API格式配置
2. 根据格式类型构造HTTP请求：
   - 设置正确的请求头（Authorization或x-api-key）
   - 构造请求体（包含system prompt、user prompt、模型名称）
   - 设置超时时间（30秒）
3. 发送HTTP POST请求到聊天端点
4. 等待响应

**结果处理**：

- **成功情况**：
  
  - 解析响应JSON，提取生成的文本内容
  - 更新数据库：test_status = "success"，test_message = 响应摘要
  - 记录last_tested时间戳
  - 界面显示绿色成功标识和响应内容预览

- **失败情况**：
  
  - 捕获错误信息（网络错误、HTTP错误、JSON解析错误）
  - 更新数据库：test_status = "failed"，test_message = 错误详情
  - 记录last_tested时间戳
  - 界面显示红色失败标识和错误信息

**批量测试**：

- 如果用户选择多个密钥，系统依次测试每个密钥
- 每个测试独立执行，一个失败不影响其他
- 所有测试完成后显示汇总结果

#### 6.4.2 模型列表获取

**触发方式**：

1. 用户点击供应商下的"刷新模型列表"按钮
2. 系统自动选择该供应商下第一个启用且测试成功的密钥
3. 如果没有可用密钥，提示用户先添加并测试密钥

**获取流程**：

1. 根据API格式构造GET请求到模型列表端点
2. 发送请求并等待响应
3. 解析响应JSON，提取模型ID数组
4. 将模型ID列表转换为JSON字符串存储到model_cache表
5. 记录当前时间戳到last_fetched字段
6. 如果该供应商已有缓存记录，则更新；否则插入新记录

**界面展示**：

1. 模型列表以可滚动列表形式显示
2. 每个模型ID占一行，右侧有"复制"按钮
3. 列表上方显示"上次获取时间：YYYY-MM-DD HH:MM:SS"
4. 用户可以随时点击"刷新"重新获取

**错误处理**：

- 如果请求失败，显示错误信息但保留旧的缓存数据
- 如果响应格式不符合预期，提示解析失败
- 不会因为获取失败而清空已有缓存

### 6.5 测试配置管理

#### 6.5.1 配置测试参数

1. 用户在供应商详情页找到"测试配置"区域
2. 可以编辑以下字段：
   - 测试模型名称（文本输入或下拉选择）
   - System Prompt（多行文本框）
   - User Prompt（多行文本框）
3. 点击"保存配置"按钮
4. 系统更新或插入test_configs表中的记录
5. 配置立即生效，下次测试时使用新配置

#### 6.5.2 默认配置

- 新添加的供应商自动创建默认配置：
  - System Prompt: "You are a helpful assistant."
  - User Prompt: "Say 'Hello, World!' in one sentence."
  - 测试模型：空（需要用户手动填写）
- 用户可以随时修改为自定义内容

#### 6.5.3 配置建议

- System Prompt建议简短明确
- User Prompt建议使用简单问题，便于快速验证
- 测试模型应选择该供应商支持的基础模型（响应快、成本低）

### 6.6 通用键值对管理流程

#### 6.6.1 创建类别

1. 用户点击"添加类别"按钮
2. 输入类别名称（如"Tavily"、"QQ机器人"）
3. 系统不会立即在数据库创建记录
4. 类别仅在添加第一个键值对时才真正存在

#### 6.6.2 添加键值对

1. 用户在某个类别下点击"添加键值对"
2. 弹出表单：
   - 键名（必填，如"api_key"、"app_id"）
   - 键值（必填）
   - 描述（可选，用于备注）
3. 提交后插入generic_keys表
4. 同一类别下的键名不能重复
5. 键值对显示在该类别的列表中

#### 6.6.3 编辑和删除

- 编辑：点击编辑按钮，修改键值或描述，保存更新
- 删除：点击删除按钮，确认后从数据库移除
- 如果删除某类别下的最后一个键值对，该类别自动消失

#### 6.6.4 复制键值

- 每个键值旁有"复制"按钮
- 点击后将键值内容复制到剪贴板
- 显示"已复制"提示

### 6.7 数据持久化与同步

#### 6.7.1 实时保存

- 所有用户操作（添加、编辑、删除）立即写入数据库
- 不存在"保存"和"取消"的概念（除了表单内部）
- 数据库自动处理事务和一致性

#### 6.7.2 数据完整性

- 使用外键约束确保关联数据一致性
- 删除供应商时自动级联删除相关密钥和配置
- 数据库文件损坏时，应用启动失败并提示用户

#### 6.7.3 备份建议

- 系统不提供自动备份功能
- 用户可以手动复制数据库文件进行备份
- 数据库文件位置在应用数据目录，用户可以通过"设置"查看路径

### 6.8 安全机制

#### 6.8.1 密码安全

- 密码不以明文存储在任何地方
- 密码仅在内存中短暂存在，用于解密数据库
- 应用关闭后密码从内存清除
- 不支持密码找回，忘记密码意味着数据永久丢失

#### 6.8.2 数据加密

- 整个数据库文件使用AES-256加密
- 加密密钥通过PBKDF2从用户密码派生
- 即使数据库文件被复制，没有密码也无法读取内容

#### 6.8.3 网络安全

- API测试请求使用HTTPS（如果端点支持）
- 不会将密钥发送到除目标API端点外的任何服务器
- 不收集用户数据，不连接任何分析服务

#### 6.8.4 剪贴板安全

- 复制到剪贴板的内容不会被应用记录
- 剪贴板内容可能被其他应用读取（操作系统限制）
- 建议用户在使用完密钥后清空剪贴板

### 6.9 错误处理与用户反馈

#### 6.9.1 错误类型

- **数据库错误**：密码错误、文件损坏、磁盘空间不足
- **网络错误**：连接超时、DNS解析失败、证书错误
- **API错误**：认证失败、配额超限、模型不存在
- **输入错误**：必填字段为空、格式不正确、重复名称

#### 6.9.2 反馈方式

- **错误对话框**：严重错误（如数据库无法打开）
- **提示消息**：一般错误（如网络请求失败）
- **内联提示**：表单验证错误（字段下方红色文字）
- **状态指示器**：测试结果（绿色成功、红色失败）

#### 6.9.3 日志记录

- 应用不生成日志文件
- 错误信息仅在界面显示
- 用户可以手动复制错误信息用于排查

### 6.10 性能优化

#### 6.10.1 数据加载

- 供应商列表按需加载，不一次性加载所有详情
- 展开某个供应商时才加载其密钥和配置
- 模型列表使用缓存，避免频繁请求

#### 6.10.2 界面响应

- 长时间操作（如API测试）显示加载动画
- 批量测试时显示进度条
- 数据库操作异步执行，不阻塞界面

#### 6.10.3 资源占用

- 应用内存占用控制在100MB以内
- 数据库文件大小取决于存储的密钥数量（通常小于10MB）
- 不使用时CPU占用接近0%

---

## 7. 开发实施计划

### 7.1 技术选型最终决策

#### 7.1.1 Tauri方案评估

**优势**：

- 原生性能，资源占用低
- 跨平台支持良好
- 安全性高（Rust后端）
- 打包体积小（约5-10MB）

**风险**：

- Rust学习曲线陡峭
- SQLCipher集成可能存在兼容性问题
- 社区相对较小，遇到问题解决难度较高

**评估建议**：

- 先进行技术验证（2-3天）
- 重点测试SQLCipher集成和剪贴板功能
- 如果验证失败，立即切换到Flask方案

#### 7.1.2 Flask备选方案

**优势**：

- Python生态成熟，库丰富
- 开发速度快
- SQLCipher集成简单（pysqlcipher3）
- 问题排查容易

**劣势**：

- 打包体积较大（约50-80MB）
- 启动速度稍慢
- 资源占用相对较高

### 7.2 开发阶段划分

#### 阶段1：基础框架搭建

- 选择并配置开发环境（Tauri或Flask）
- 实现数据库加密和初始化
- 完成登录界面和密码验证
- 建立前后端通信机制

#### 阶段2：核心功能开发

- 实现供应商管理（增删改查）
- 实现密钥管理（增删改查）
- 实现测试配置管理
- 实现复制到剪贴板功能

#### 阶段3：API测试功能

- 实现OpenAI格式API测试
- 实现Anthropic格式API测试
- 实现模型列表获取
- 实现测试结果展示和存储

#### 阶段4：通用键值对功能

- 实现类别和键值对管理
- 实现复制功能
- 完善界面展示

#### 阶段5：界面优化与测试

- 实现Windows 10风格界面
- 优化用户体验和交互流程
- 进行功能测试和bug修复
- 性能优化

#### 阶段6：打包与发布

- 配置打包参数
- 生成可执行文件
- 测试安装和运行

### 7.3 测试策略

#### 7.3.1 功能测试

- 密码创建和验证
- 数据库加密和解密
- 所有CRUD操作
- API测试功能（使用真实API）
- 剪贴板功能

#### 7.3.2 安全测试

- 密码强度验证
- 数据库文件加密验证
- 内存中密码清除验证
- 网络请求安全性检查

#### 7.3.3 兼容性测试

- Windows 10/11
- macOS（如果Tauri方案）
- 不同屏幕分辨率
- 不同API供应商

#### 7.3.4 性能测试

- 大量密钥存储（100+）
- 批量测试性能
- 内存占用监控
- 启动速度测试


