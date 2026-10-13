"""独立复核参考与可实现性；不导入make的规则、算法和模板。

从每道题员工可读规则/内容重建要求，再在Chromium打开40个正确页逐项核对事实。
另外渲染5份探测答卷与真实坏例，证明浏览器可抓透明色、祖先透明度、窄屏溢出、首屏越界。
调用：uv run python ../experts/cases/landing-page/check.py
用--probes-only只生成本目录probes.json；模型评审另跑，所有pass/fail仍由模型裁判。
"""

import argparse
import html
import json
import re
from pathlib import Path

from measure import extract, measure, request_for

HERE = Path(__file__).resolve().parent


def read_rules(question: dict) -> dict:
    rules = question["files"]["工作规则.md"]
    colors = re.search(r"主色(#[A-F0-9]{6})、底色(#[A-F0-9]{6})、墨色(#[A-F0-9]{6})、装饰色(#[A-F0-9]{6})", rules).groups()
    fonts = re.search(r"第一项必须是“(.+?)”；其他文字第一项必须是“(.+?)”", rules).groups()
    views = tuple(map(int, re.search(r"手机检查视口为(\d+)×(\d+)，桌面为(\d+)×(\d+)", rules).groups()))
    return {"colors": colors + ("#FFFFFF",), "heading": fonts[0], "body": fonts[1], "views": [list(views[:2]), list(views[2:])],
            "radius": int(re.search(r"四个角圆角都为(\d+)px", rules).group(1)),
            "cta": re.search(r"文字只写“(.+?)”", rules).group(1),
            "left": "店名字样的左边缘" in rules, "logo_top": int(re.search(r"放在页顶(\d+)px以内", rules).group(1)),
            "max_width": int(re.search(r"main实际宽度不超过(\d+)px", rules).group(1)),
            "stock": "逐款原样显示状态" in rules}


def correct_page(question: dict) -> str:
    """独立按员工工作规则写一张可实现页，不用参考答案。"""
    r = read_rules(question)
    d = json.loads(question["files"]["内容.json"])
    primary, paper, ink, accent, _ = r["colors"]
    rows = []
    # R3先放可预订商品只是一个可行实现，规则不限定顺序。
    products = sorted(d["产品"], key=lambda p: p["状态"] == "已售罄") if r["stock"] else d["产品"]
    for p in products:
        status = f"<span class=status>{p['状态']}</span>" if r["stock"] else ""
        rows.append(f"<article><div class=name><h2>{html.escape(p['名称'])}</h2>{status}</div><p class=price>{html.escape(p['价格'])}</p></article>")
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(d['主标题'])}</title>
<style>
*{{box-sizing:border-box}}body{{margin:0;background:{paper};color:{ink};font-family:"{r['body']}",sans-serif;font-size:14px;line-height:1.45}}
main{{max-width:{r['max_width']}px;margin:0 auto;padding:16px 20px 24px}}header{{text-align:{'left' if r['left'] else 'center'};margin-bottom:12px}}.logo{{display:inline-block;font-size:16px;font-weight:700;color:{primary}}}
h1,h2{{font-family:"{r['heading']}",serif}}h1{{font-size:25px;line-height:1.25;margin:0 0 10px}}.intro{{margin:0 0 12px}}.products{{border-top:1px solid {accent}}}
article{{display:flex;align-items:center;gap:12px;border-bottom:1px solid {accent};padding:8px 0;min-height:47px}}.name{{flex:1;min-width:0}}h2{{font-size:15px;line-height:1.35;margin:0}}.status{{font-size:14px;display:block}}.price{{margin:0;white-space:nowrap;font-size:14px}}
.cta{{display:flex;justify-content:center;align-items:center;margin:12px 0;min-height:44px;border:0;border-radius:{r['radius']}px;background:{primary};color:#FFFFFF;text-decoration:none;font-family:"{r['body']}",sans-serif;font-size:16px;font-weight:700;padding:10px 12px}}
.details p{{margin:8px 0;overflow-wrap:anywhere}}@media(min-width:700px){{main{{padding-top:28px}}h1{{font-size:34px}}article{{min-height:64px}}}}
</style></head><body><main><header><span class=logo>{html.escape(d['店名'])}</span></header><h1>{html.escape(d['主标题'])}</h1><p class=intro>{html.escape(d['简介'])}</p><section class=products>{''.join(rows)}</section>
<a class=cta href="#order-info">{r['cta']}</a><section id=order-info class=details><p>{html.escape(d['截止说明'])}</p><p>{html.escape(d['自提说明'])}</p><p>{html.escape(d['预订方式'])}</p></section></main></body></html>"""


def answer(code: str, file: bool = False) -> str:
    return ("已完成：landing.html\n\n【交付文件 landing.html】\n" + code) if file else "```html\n" + code + "\n```"


def reference_errors(q: dict) -> list:
    r, d, ref = read_rules(q), json.loads(q["files"]["内容.json"]), q["reference"]
    expected = {"适用品牌": d["店名"], "必须原样可见": {k:v for k,v in d.items() if k != "产品"}, "逐款内容": d["产品"],
                "手机首屏价格": [p["价格"] for p in d["产品"] if not r["stock"] or p["状态"] == "可预订"],
                "手机首屏主按钮": r["cta"], "手机视口": r["views"][0], "桌面视口": r["views"][1],
                "允许实际色": list(r["colors"]), "不能作文字/底色": r["colors"][3], "标题字体首项": r["heading"],
                "其他字体首项": r["body"], "按钮四角px": r["radius"], "文字最低对比度": 4.5, "桌面main最大宽度px": r["max_width"]}
    return [(k, ref.get(k), value) for k, value in expected.items() if ref.get(k) != value]


def browser_errors(q: dict, measurements: dict) -> list:
    """自检一份人为构造的正确卷能做到；这些断言不会进入真实员工判分。"""
    if "浏览器实际测量" not in measurements:
        return [measurements]
    r, d = read_rules(q), json.loads(q["files"]["内容.json"])
    browser, wrong = measurements["浏览器实际测量"], []
    for n, v in enumerate(browser["views"]):
        width, height = r["views"][n]
        if v["document"]["width"] > width + 1:
            wrong.append((n, "horizontal overflow", v["document"]))
        for label, hits in v["targets"].items():
            if not hits or not any(h["displayed"] and not h["clipping"] and h["centerCovered"] is not True for h in hits):
                wrong.append((n, "not visible", label, hits))
        for p in v["products"]:
            if len(p["nameOccurrences"]) != 1 or len(p["priceOccurrences"]) != 1:
                wrong.append((n, "product occurrences", p))
            if r["stock"] and (not p["containers"] or p["status"] not in p["containers"][0]["text"]):
                wrong.append((n, "status", p))
        for style in v["styles"]:
            expected_font = r["heading"] if style["heading"] else r["body"]
            if style["fontFamily"].split(",")[0].strip(' "\'') != expected_font:
                wrong.append((n, "font", style))
            if style["actualColor"] not in r["colors"] or style["actualColor"] == r["colors"][3] or style["contrast"] < 4.5:
                wrong.append((n, "text style", style))
            if r["stock"] and not style["heading"] and style["fontSize"] < 14:
                wrong.append((n, "small font", style))
        for paint in v["paints"]:
            if paint["actual"] not in r["colors"] or (paint["kind"] in ("background", "text") and paint["actual"] == r["colors"][3]):
                wrong.append((n, "paint", paint))
        if v["effects"] or v["restrictedElements"]:
            wrong.append((n, "restricted appearance", v["effects"], v["restrictedElements"]))
        cta = [a for a in v["actions"] if a["text"] == r["cta"]]
        if len(cta) != 1 or cta[0]["radii"] != [f"{r['radius']}px"] * 4:
            wrong.append((n, "cta", cta))
        if n == 0:
            first = [p["priceOccurrences"][0] for p in v["products"] if p["priceOccurrences"] and (not r["stock"] or p["status"] == "可预订")] + cta
            if any(h["rect"]["top"] < 0 or h["rect"]["bottom"] > height or h["rect"]["right"] > width or h["rect"]["left"] < 0 for h in first):
                wrong.append((n, "first-screen", first))
            logo = v["targets"]["店名"][0]["rect"]
            if logo["bottom"] > r["logo_top"] or (r["left"] and not 16 <= logo["left"] <= 28) or (not r["left"] and abs((logo["left"]+logo["right"])/2-width/2)>8):
                wrong.append((n, "logo", logo))
            if r["stock"] and cta[0]["rect"]["height"] < 44:
                wrong.append((n, "target height", cta))
        else:
            if len(v["main"]) != 1:
                wrong.append((n, "main count", v["main"]))
            else:
                main = v["main"][0]["rect"]
                if main["width"] > r["max_width"] or abs(main["left"]-(width-main["right"])) > 2:
                    wrong.append((n, "desktop main", main))
    if browser["externalRequests"]:
        wrong.append(("external", browser["externalRequests"]))
    return wrong


def probes(bank: list) -> list:
    b = {q["name"]: q for q in bank}
    a, y = correct_page(b["t12"]), correct_page(b["y07"])
    bad_a = a.replace("</style>", ".price{color:rgba(36,85,70,.60)}main{min-width:700px}.cta{border-radius:24px;box-shadow:0 4px 10px #245546}</style>")
    # R3售罄状态错误、非标题文字变小、按钮触控高度不足；内容本身仍完整。
    bad_y = y.replace("已售罄", "可预订", 1).replace("</style>", ".details{font-size:13px}.cta{height:32px;min-height:32px;padding:0}</style>")
    return [{"name": "t12", "label": "right", "expect": [], "answer": answer(a)},
            {"name": "t12", "label": "wrong", "expect": ["LP-brand", "LP-style", "LP-layout"], "answer": answer(bad_a)},
            {"name": "y07", "label": "right", "expect": [], "answer": answer(y, True)},
            {"name": "y07", "label": "wrong", "expect": ["LP-content", "LP-brand", "LP-layout"], "answer": answer(bad_y, True)},
            {"name": "t12", "label": "correct+wrapper", "expect": ["LP-format"],
             "answer": "已按要求完成，下面是页面。检查了蓝色#3b82f6和19元价格。\n\n" + answer(a) + "\n\n手机桌面都已核对，请查看。"}]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probes-only", action="store_true")
    args = parser.parse_args()
    bank = json.loads((HERE / "questions.json").read_text())
    p = probes(bank)
    (HERE / "probes.json").write_text(json.dumps(p, ensure_ascii=False, indent=2) + "\n")
    if args.probes_only:
        print("5 probes generated")
        return
    wrong, evidence = [], {}
    for q in bank:
        problems = reference_errors(q)
        code = correct_page(q)
        measurement = measure(q, answer(code, int(q["name"][1:]) % 2 == 0))
        problems += browser_errors(q, measurement)
        if problems:
            wrong.append((q["name"], problems))
        evidence[q["name"]] = measurement
        print(q["name"], "ok" if not problems else json.dumps(problems, ensure_ascii=False)[:1000], flush=True)
    # 确认独立复核并非仅检查同一个对象。
    changed = json.loads(json.dumps(bank[0]))
    changed["reference"]["手机视口"][0] += 1
    assert reference_errors(changed)
    byname = {q["name"]: q for q in bank}
    bad_evidence = {}
    for qname, rule in (("t11", ".price{color:rgba(139,94,60,.6)}"),
                        ("t12", ".products{opacity:.6}"),
                        ("t13", "main{min-width:700px}"),
                        ("y06", ".products{padding-top:500px}")):
        q = byname[qname]
        measured = measure(q, answer(correct_page(q).replace("</style>", rule + "</style>")))
        assert browser_errors(q, measured), (qname, "negative control not detected")
        bad_evidence[qname] = measured
    for item in p:
        measured = measure(byname[item["name"]], item["answer"])
        if item["label"] in ("right", "correct+wrapper"):
            assert not browser_errors(byname[item["name"]], measured), (item["label"], measured)
        bad_evidence[item["name"] + "-" + item["label"]] = measured
    evidence["negative-controls-and-probes"] = bad_evidence
    (HERE / "browser-evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    # 括号、引号、Markdown与空文本只影响交付提取，不改变HTML渲染文本。
    good_html = correct_page(bank[0])
    assert extract("“说明？”\n(" + answer(good_html) + ")\n**结束。**")[0] == good_html
    assert extract("")[0] is None
    print("mismatches:", wrong or "none")
    assert not wrong


if __name__ == "__main__":
    main()
