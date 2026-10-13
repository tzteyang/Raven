"""提取交付HTML并启动真实浏览器；仅记录可复现观察，不输出pass/fail。

使用仓库根目录 .venv 里的 Playwright 环境，不安装依赖，不接触员工工作目录。
"""

import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
VENV_PYTHON = HERE.parents[2] / ".venv" / "bin" / "python"
FILES = re.compile(r"【交付文件 ([^\n]+?)】\n(.*?)(?=\n【交付文件 |\Z)", re.S)
CODE = re.compile(r"```html\s*\n(.*?)\n```", re.S | re.I)


def extract(product):
    files = FILES.findall(product)
    htmls = [(name, content) for name, content in files if name.lower().endswith(".html")]
    if htmls:
        name, html = next(((n, t) for n, t in htmls if n == "booking.html"), htmls[0])
        reply = FILES.sub("", product).strip()
        allowed = not reply or reply == "booking.html" or bool(re.fullmatch(r"\[[^\]\n]+\]\([^\n)]*booking\.html\)", reply))
        return html, dict(mode="file", name=name, delivered=[n for n, _ in files], reply=reply[:1200], reply_is_permitted_link_or_name=allowed)
    matches = list(CODE.finditer(product))
    if matches:
        reply = CODE.sub("", product).strip()
        return matches[0].group(1), dict(mode="codeblock", blocks=len(matches), reply=reply[:1200], reply_is_permitted_link_or_name=not reply)
    return None, dict(mode="missing", reply=product[:1600], delivered=[n for n, _ in files])


def measure(question, product):
    html, delivery = extract(product)
    result = {"交付提取": delivery}
    if html is None:
        return result
    result["HTML字符数"] = len(html)
    # Source-only observations are limited to declared resources/frameworks, never behavior.
    result["源码声明资源"] = re.findall(r"<(?:script|link|img|iframe|source)\b[^>]*(?:src|href)=[\"']([^\"']+)", html, re.I)
    result["源码框架标识"] = sorted(set(re.findall(r"\b(?:ReactDOM|React\.createElement|createApp|Vue\.createApp|angular\.module|import\s+.+?from\s*['\"](?:react|vue|svelte))", html)))
    try:
        completed = subprocess.run([str(VENV_PYTHON), str(HERE / "browser_probe.py")],
                                   input=json.dumps(dict(question=question, html=html), ensure_ascii=False),
                                   text=True, capture_output=True, timeout=100)
        try:
            result["浏览器实测"] = json.loads(completed.stdout)
        except json.JSONDecodeError:
            result["浏览器工具异常"] = {"exit": completed.returncode, "stderr": completed.stderr[-1500:], "stdout": completed.stdout[-500:]}
    except subprocess.TimeoutExpired:
        result["浏览器工具异常"] = "浏览器测量超过100秒，不能据此推断具体交互结果。"
    except OSError as exc:
        result["浏览器工具异常"] = str(exc)
    return result


if __name__ == "__main__":
    for product in ["", "说明", "```html\n<p>“预约？”（**提示**）</p>\n```", "说明\n```html\n<p>字</p>\n```\n尾声"]:
        html, got = extract(product)
        assert isinstance(got, dict)
    assert extract("【交付文件 booking.html】\n<p>字</p>")[1]["reply_is_permitted_link_or_name"]
    assert not extract("前言\n```html\n<p>字</p>\n```\n尾声")[1]["reply_is_permitted_link_or_name"]
    print("extract ok")
