# APIKEY Manager

一个本地运行的 API Key 管理器。它主要用来保存、管理和测试大模型 API Key，也可以顺手保存其他服务的密钥、App ID、Secret 之类的键值信息。

数据存在你自己的电脑里，并用 SQLCipher 加密。应用不会上传你的密钥，也不会连接统计或分析服务。

## 能做什么

- 保存多个大模型供应商的 API 地址和密钥。
- 支持 OpenAI Completions、OpenAI Response、Anthropic Messages 三类接口格式。
- 给每个供应商指定一个测试密钥。
- 给每个供应商单独设置测试模型。
- 在设置页统一设置测试用的 System Prompt 和 User Prompt。
- 获取并缓存模型列表。
- 保存通用密钥，比如搜索 API、机器人 App ID、App Secret 等。
- 一键复制密钥、模型 ID、端点地址和键值。
- 通过弹窗调整供应商、密钥、类别和键值的显示顺序。
- 显示时间默认按 UTC+8 展示。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python run.py
```

启动后会自动用默认浏览器打开：

```text
http://127.0.0.1:5157
```

控制台会用彩色文字简单显示功能、访问地址和注意事项。

第一次打开时会让你创建主密码。这个密码不会明文保存，也无法找回。忘记密码就无法打开原来的数据库。

## 数据库放在哪里

默认数据库文件是 `apikeys.db`。

- Windows：`%APPDATA%\APIKEY-Manager\apikeys.db`
- macOS：`~/Library/Application Support/APIKEY-Manager/apikeys.db`
- Linux：`~/.apikey-manager/apikeys.db`

如果你想指定数据目录：

```powershell
$env:APIKEY_MANAGER_DATA_DIR="C:\path\to\data"
python run.py
```

## 基本用法

### 管理大模型密钥

1. 添加供应商，填写名称、API 地址和接口格式。
2. 添加一个或多个 API Key。
3. 选择其中一个作为测试密钥。
4. 填写这个供应商的测试模型。
5. 点击刷新模型列表或测试密钥。

### 管理通用密钥

1. 添加一个类别，比如 `Tavily` 或 `QQ机器人`。
2. 在类别下添加键名、键值和备注。
3. 需要使用时直接点击复制。

## 打包成 exe

项目里提供了 PyInstaller 打包脚本，会使用当前目录下的 `favicon.ico` 作为图标。

先安装 PyInstaller：

```powershell
python -m pip install pyinstaller
```

默认打包成单文件：

```powershell
python build_pyinstaller.py
```

输出位置：

```text
APIKEY-Manager.exe
```

如果想隐藏控制台窗口：

```powershell
python build_pyinstaller.py --windowed
```

构建完成后，脚本会把 exe 移动到项目根目录，并自动删除 `dist/`、`build/`、`build-spec/` 这些 PyInstaller 临时目录。

注意：打包后的程序仍然是本地 Web 应用。启动 exe 后会自动打开默认浏览器访问：

```text
http://127.0.0.1:5157
```

如果你想看到彩色控制台说明和停止服务提示，不要使用 `--windowed`。

## 开发和测试

运行测试：

```powershell
python -m unittest discover -s tests
```

常用命令：

```powershell
python run.py
python -m unittest discover -s tests
python build_pyinstaller.py
```

## 依赖说明

主要依赖：

- Flask
- requests
- SQLCipher Python 绑定：`sqlcipher3`

如果安装 `sqlcipher3` 失败，通常是当前平台没有合适的 wheel，或者缺少 SQLCipher / C++ 编译环境。

## 安全提醒

- 主密码不会明文保存。
- 数据库文件是加密的。
- API Key 只会在你主动测试或刷新模型列表时发送到你配置的 API 地址。
- 复制到剪贴板的内容可能被其他应用读取，用完后可以手动清空剪贴板。
- 项目不自动备份数据库，重要数据请自己备份。
