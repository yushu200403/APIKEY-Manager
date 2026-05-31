import ctypes
import os
import threading
import webbrowser

from app import create_app


HOST = "127.0.0.1"
PORT = 5157
URL = f"http://{HOST}:{PORT}"


app = create_app()


def enable_ansi_colors():
    if os.name != "nt":
        return
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-11)
    mode = ctypes.c_uint32()
    if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)


def color(text, code):
    return f"\033[{code}m{text}\033[0m"


def print_startup_message():
    enable_ansi_colors()
    print()
    print(color("APIKEY Manager 已启动", "1;36"))
    print(color("功能：", "1;32") + "本地保存、管理、复制和测试大模型 API Key，也支持通用密钥键值管理。")
    print(color("地址：", "1;34") + URL)
    print(color("注意：", "1;33") + "数据保存在本机 SQLCipher 加密数据库中；忘记主密码无法找回。")
    print(color("关闭：", "1;31") + "关闭此控制台窗口或按 Ctrl+C 即可停止服务。")
    print()


def open_browser():
    webbrowser.open(URL)


if __name__ == "__main__":
    print_startup_message()
    threading.Timer(1.0, open_browser).start()
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)
