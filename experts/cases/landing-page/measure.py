"""提取员工交付HTML，另起Playwright进程量实际渲染；只提供事实，不作评审判定。

子进程使用仓库根目录的 .venv；因此可由asyncio评审循环安全调用。
"""

import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
PYTHON = HERE.parents[2] / ".venv" / "bin" / "python"
FILE = re.compile(r"【交付文件 ([^\n】]+)】\n(.*?)(?=\n【交付文件 |\Z)", re.S)
BLOCK = re.compile(r"```html\s*\n(.*?)\n```", re.S | re.I)


def extract(product: str) -> tuple[str | None, dict]:
    found = [(name, content) for name, content in FILE.findall(product) if name.lower().endswith((".html", ".htm"))]
    outside = FILE.sub("", product).strip() if found else product.strip()
    blocks = BLOCK.findall(outside)
    extra = BLOCK.sub("", outside).strip() if blocks else outside
    chosen = next(((name, text) for name, text in found if name == "landing.html"), found[0] if found else (None, None))
    text = chosen[1] if found else blocks[0] if blocks else None
    return text, {"HTML文件名": [name for name, _ in found], "正文HTML代码块个数": len(blocks),
                  "交付之外的正文": extra[:1500], "选取的HTML来源": chosen[0] if found else "html代码块" if blocks else "没有"}


def request_for(question: dict, html: str) -> dict:
    """视口和主按钮按员工拿到的规则读出，不依赖reference。"""
    rules = question["files"]["工作规则.md"]
    view = re.search(r"手机检查视口为(\d+)×(\d+)，桌面为(\d+)×(\d+)", rules)
    data = json.loads(question["files"]["内容.json"])
    targets = {k: v for k, v in data.items() if isinstance(v, str)}
    targets["主按钮"] = re.search(r"文字只写“(.+?)”", rules).group(1)
    return {"html": html, "views": [[int(view[1]), int(view[2])], [int(view[3]), int(view[4])]],
            "targets": targets, "products": data["产品"]}


def measure(question: dict, product: str) -> dict:
    html, delivery = extract(product)
    result = {"交付格式事实": delivery}
    if html is None:
        result["浏览器测量"] = "没有可读取的HTML交付"
        return result
    payload = request_for(question, html)
    try:
        proc = subprocess.run([str(PYTHON), str(HERE / "browser_measure.py")], input=json.dumps(payload, ensure_ascii=False),
                              text=True, capture_output=True, timeout=70, check=False)
        if proc.returncode:
            result["测量错误（非员工判定）"] = (proc.stdout or proc.stderr)[-1200:]
        else:
            result["浏览器实际测量"] = json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, OSError, json.JSONDecodeError) as exc:
        result["测量错误（非员工判定）"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    return result


if __name__ == "__main__":
    import sys
    qname, product = sys.argv[1], Path(sys.argv[2]).read_text()
    q = next(q for q in json.loads((HERE / "questions.json").read_text()) if q["name"] == qname)
    print(json.dumps(measure(q, product), ensure_ascii=False, indent=2))
