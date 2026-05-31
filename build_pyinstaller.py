import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENTRYPOINT = ROOT / "run.py"
ICON = ROOT / "favicon.ico"
APP_DIR = ROOT / "app"
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
SPEC_DIR = ROOT / "build-spec"


def data_arg(source, target):
    separator = ";" if sys.platform.startswith("win") else ":"
    return f"{source}{separator}{target}"


def module_exists(name):
    return importlib.util.find_spec(name) is not None


def build_command(args):
    if not ENTRYPOINT.exists():
        raise FileNotFoundError(f"入口文件不存在：{ENTRYPOINT}")
    if not ICON.exists():
        raise FileNotFoundError(f"图标文件不存在：{ICON}")
    if not APP_DIR.exists():
        raise FileNotFoundError(f"应用目录不存在：{APP_DIR}")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        args.name,
        "--icon",
        str(ICON),
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR),
        "--specpath",
        str(SPEC_DIR),
        "--onefile",
        "--add-data",
        data_arg(APP_DIR / "templates", "app/templates"),
        "--add-data",
        data_arg(APP_DIR / "static", "app/static"),
        "--add-data",
        data_arg(ICON, "favicon.ico"),
    ]

    if args.windowed:
        command.append("--windowed")

    for module_name in ("sqlcipher3", "pysqlcipher3"):
        if module_exists(module_name):
            command.extend(["--collect-all", module_name])
            command.extend(["--hidden-import", f"{module_name}.dbapi2"])

    command.append(str(ENTRYPOINT))
    return command


def ensure_inside_root(path):
    resolved = path.resolve()
    root = ROOT.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError(f"拒绝清理项目目录外的路径：{resolved}")
    return resolved


def move_executable_to_root(name):
    extension = ".exe" if sys.platform.startswith("win") else ""
    source = DIST_DIR / f"{name}{extension}"
    if not source.exists():
        raise FileNotFoundError(f"未找到打包产物：{source}")

    target = ROOT / source.name
    if target.exists():
        target.unlink()
    shutil.move(str(source), str(target))
    return target


def cleanup_pyinstaller_outputs():
    for path in (DIST_DIR, BUILD_DIR, SPEC_DIR):
        if path.exists():
            shutil.rmtree(ensure_inside_root(path))


def main():
    parser = argparse.ArgumentParser(description="使用 PyInstaller 打包 APIKEY 管理器。")
    parser.add_argument("--name", default="APIKEY-Manager", help="输出程序名称。")
    parser.add_argument("--windowed", action="store_true", help="Windows/macOS 下隐藏控制台窗口。")
    args = parser.parse_args()

    if module_exists("PyInstaller") is False:
        raise RuntimeError("未安装 PyInstaller。请先运行：python -m pip install pyinstaller")

    SPEC_DIR.mkdir(exist_ok=True)
    command = build_command(args)
    print("运行打包命令：")
    print(" ".join(f'"{item}"' if " " in item else item for item in command))
    subprocess.run(command, cwd=ROOT, check=True)

    output = move_executable_to_root(args.name)
    cleanup_pyinstaller_outputs()
    print(f"打包完成：{output}")
    print("已清理 PyInstaller 临时目录：dist、build、build-spec")

    if args.windowed and sys.platform.startswith("win"):
        print("提示：当前为隐藏控制台模式，应用启动后仍需在浏览器打开 http://127.0.0.1:5157")


if __name__ == "__main__":
    main()
