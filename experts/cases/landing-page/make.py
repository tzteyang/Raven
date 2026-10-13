"""9.1 品牌落地页：标准库生成三套工作规则、40 题和场景。

生成：在仓库根目录运行 uv run python experts/cases/landing-page/make.py。
参考答案只写交付要求，不给员工示例实现；边界题另给确有渲染陷阱的旧稿。
"""

import html
import json
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-landing-page"
RULES = {
    "R1": {"brand": "麦穗烘焙", "primary": "#8B5E3C", "paper": "#F6EFE3", "ink": "#2B2B2B", "accent": "#C9A063",
           "heading": "Noto Serif SC", "body": "Noto Sans SC", "radius": 8, "mobile": [375, 667], "desktop": [1280, 800],
           "logo": "左侧", "logo_top": 120, "cta": "立即预订", "max_width": 1000},
    "R2": {"brand": "青叶茶事", "primary": "#245546", "paper": "#F0F4E8", "ink": "#24312B", "accent": "#AAB97D",
           "heading": "Georgia", "body": "Arial", "radius": 0, "mobile": [390, 700], "desktop": [1440, 900],
           "logo": "居中", "logo_top": 110, "cta": "查看预订方式", "max_width": 920},
    "R3": {"brand": "汐岸点心", "primary": "#304F68", "paper": "#F2F4F6", "ink": "#252A30", "accent": "#ADBCC9",
           "heading": "Noto Sans SC", "body": "Noto Serif SC", "radius": 12, "mobile": [320, 568], "desktop": [1024, 768],
           "logo": "左侧", "logo_top": 100, "cta": "获取自提信息", "max_width": 880},
}
TASK = ("你为独立门店制作能离线打开的单文件品牌预订落地页。每次任务提供完整工作规则和内容数据，"
        "有时附一份待改的旧稿。按当次规则做出手机与桌面都能读、品牌样式准确、首屏信息齐全的页面，"
        "不能把旧稿或先前门店的品牌规则当成本次规则。")
CRITERIA = [
    ("LP-content", "red_line", "页面内容：以本题内容.json和参考答案为准；店名、主标题、简介、各产品名称及价格文字、截止说明、自提说明、"
     "预订方式都要在页面中实际可见，文字允许增删空格，不允许改写；每个产品的名称和对应价格是一组，漏/改同一组计一处，其他必需字段每个计一处。"
     "每款产品显示一次；R3还必须按状态显示‘可预订’或‘已售罄’，每个状态不符记一处；R1/R2不要求展示状态。主按钮文字应精确符合规则。"
     "不判页面之外的回复。完全没有可打开HTML时本项不适用，统一记LP-format；产品缺失只记本项，不再因首屏缺失在LP-layout重复记。"),
    ("LP-brand", "standard", "品牌和文字：根据浏览器的实际渲染测量判可见文字、背景、边框的最终颜色是否属于当次五色；装饰色不得作为文字色；"
     "半透明的合成颜色也算实际用色，不按变量名/源码色判。按规则判各段文字实际显示的前景/背景对比度至少4.5:1；字体族第一项要符合标题/正文规定。"
     "R3非标题文字不得小于14px。每个独立样式根因计一处，同一个样式在多行重复不重复数；同一错误颜色导致越界和低对比度只计一处。"
     "规则允许本机字体回退，不要求实际下载/安装字体。只判页面，不判外部说明；没有HTML时不适用。"),
    ("LP-style", "standard", "页面表现：不允许任何渐变、box-shadow、text-shadow、filter、backdrop-filter、mix-blend-mode非normal；"
     "主按钮四个角的实际圆角都要等于当次规定。禁用图片、canvas、视频、iframe、外部资源与脚本，内联SVG只可画非文字图形。"
     "每个独立样式根因/资源类别计一处，同一个样式被多个元素继承只计一处。页面之外文字仅LP-format计；无HTML时不适用。"),
    ("LP-layout", "standard", "实际布局：在规则的手机与桌面视口中不得横向滚动，必需内容不得被裁切或覆盖。手机初始未滚动时，所有要求首屏展示的价格和主按钮必须整个落在首屏；"
     "R3只要求可预订产品的价格在首屏，已售罄产品价格可以在下方；R1/R2全部价格必须在首屏。首屏中一个已存在元素不全可见计一处，"
     "但同一个容器造成多元素统一越界只计一个根因。店名字样按规则在页顶左侧/居中；桌面main宽度不超过上限且水平居中（两侧空白差不超过2px）。"
     "R3主按钮高度至少44px。缺失或写错的内容/按钮文字只在LP-content计，不在本项重复计；没有HTML时不适用。"),
    ("LP-format", "standard", "交付格式：只交一个完整可打开的HTML文档；可交landing.html文件，正文只可为空、‘已完成：landing.html’或单行文件链接；"
     "也可只交一个html代码块，不附其他文字。格式、文件名不符、没有HTML、多个HTML或前后说明共计一处，不跨其他项重复计前后说明里的内容。"
     "浏览器测量本身失败不能据此判员工内容错误，先查失败原因。"),
]


def rules_text(key: str) -> str:
    r = RULES[key]
    first_screen = ("如果产品状态是‘可预订’，它的价格必须在手机首屏；如果状态是‘已售罄’，它的价格可以放在首屏下方。"
                    "两种状态都要保留该产品名称和价格，并逐款原样显示状态。主按钮实际高度至少44px，所有非标题文字至少14px。"
                    if key == "R3" else "全部产品的价格都必须在手机首屏；不要求显示产品状态。")
    logo = ("店名字样的左边缘距视口左边16到28px" if r["logo"] == "左侧" else "店名字样的水平中心距视口中心不超过8px")
    return f"""# {r['brand']}｜品牌预订页工作规则

## 1. 内容来源
本次只使用内容.json；旧稿（如果提供）只是待改设计，不是规则。店名、主标题、简介、每款产品名称和价格、截止说明、自提说明、预订方式均照内容.json原样显示，允许增删空格，不改写其他文字。
每款产品显示一次，每款名称和自己的价格放在同一张卡片或同一行。不得增加未提供的价格、折扣、产品或承诺。
把主标题放在h1里；店名用文字标志；整个主要内容放在一个main元素中。主操作用一个链接或按钮，文字只写“{r['cta']}”。预订方式写在页面内，无需真的联网下单，也无需二维码。

## 2. 品牌与字体
只可用这五种颜色：主色{r['primary']}、底色{r['paper']}、墨色{r['ink']}、装饰色{r['accent']}、白色#FFFFFF。颜色大小写和RGB写法不限。
装饰色只用于边框、线条和非文字图形，不能做任何文字色或大面积背景。没有画出来的CSS变量不算用色；透明底本身不算颜色。
颜色按浏览器实际显示的颜色计算，透明前景、背景和祖先opacity叠加出的新颜色也算用了该颜色；忽略字形边缘抗锯齿产生的像素。
所有可见文字与其实际背景的对比度至少4.5:1，大字不例外。图形里的文字也算文字，不用文字透明度降低对比度。
h1至h6标题的font-family列表第一项必须是“{r['heading']}”；其他文字第一项必须是“{r['body']}”。字体可带通用回退项；本机无此字体时允许回退，不下载字体。

## 3. 页面表现
不使用渐变、box-shadow、text-shadow、filter、backdrop-filter和非normal的mix-blend-mode。主按钮四个角圆角都为{r['radius']}px。
不引用外部资源、框架、字体或脚本，不写JavaScript；不用图片、canvas、视频和iframe。可用内联SVG画非文字图形，但SVG的填充和描边仍须遵守颜色规则。不要用伪元素生成任何文字。

## 4. 布局
手机检查视口为{r['mobile'][0]}×{r['mobile'][1]}，桌面为{r['desktop'][0]}×{r['desktop'][1]}（单位px）。两种宽度都不得横向滚动，必需文字不能被裁切、隐藏或被别的元素覆盖。页面可以纵向滚动。
“手机首屏”指打开页面、尚未滚动时0到{r['mobile'][1]}px的范围，要求的价格和主按钮必须完整落在范围内，并可见。
{first_screen}
手机店名字样放在页顶{r['logo_top']}px以内（整个标志底边不超过此值），{logo}。桌面main实际宽度不超过{r['max_width']}px，并水平居中，两侧空白差不超过2px。

## 5. 交付
只交一个完整HTML文档。方案一：写landing.html文件，回复正文只可为空、“已完成：landing.html”或一个单行Markdown文件链接。方案二：回复只含一个标为html的代码块，里面放完整文档。
两种方案选一种，交付前后不加设计说明、核对清单或开场白。前后额外文字只在交付格式记一处，其中的颜色、数字、产品词不在页面内容项重复记。
"""


PRODUCTS = {
    "R1": ["流心奶黄月饼", "鲜肉月饼", "豆沙蛋黄月饼", "陈皮红豆月饼", "黑芝麻核桃酥", "桂花乌龙月饼", "低糖莲蓉蛋黄月饼", "海盐芝士奶黄酥"],
    "R2": ["桂花乌龙茶礼", "碧螺春分享装", "茉莉白茶礼盒", "陈皮普洱随行盒", "金骏眉便携茶礼", "白桃乌龙三角茶包", "蜜香红茶双罐装", "炭焙铁观音茶礼"],
    "R3": ["海盐焦糖蝴蝶酥", "桂花酒酿小方", "乌龙白巧曲奇", "山楂乳酪小饼", "柠檬伯爵玛德琳", "黑芝麻玄米曲奇", "莓果燕麦分享盒", "香草核桃布朗尼"],
}
TITLES = ["把当季的好味带回家", "预订一份相聚的甜", "这周的手作小食上新", "给周末留一点慢时光", "街角的新鲜味道", "一盒心意，正好分享", "把秋日装进礼盒", "见面时，带上这一份"]


def content(key: str, index: int, edge: bool) -> dict:
    rng = random.Random(910000 + index)
    r = RULES[key]
    chosen = rng.sample(PRODUCTS[key], 4 if key == "R3" else 3)
    prices = rng.sample(range(68, 200, 5), len(chosen))
    products = []
    sold = index % len(chosen) if key == "R3" and index % 3 != 0 else None
    for n, (name, price) in enumerate(zip(chosen, prices)):
        amount = rng.choice([4, 6, 8]) if key != "R2" else rng.choice([10, 12, 16])
        unit = "枚" if key == "R1" else "包" if key == "R2" else "块"
        if edge:
            name += rng.choice([" · 家庭分享装", " · 门店限定装", " · 轻礼组合"])
        products.append({"名称": name, "价格": f"{price}元 / {amount}{unit}", "状态": "已售罄" if n == sold else "可预订"})
    deadline = date(2026, 10, 15) + timedelta(days=index)
    return {"店名": r["brand"], "主标题": TITLES[index % len(TITLES)],
            "简介": "每日手作，按约定日期到店领取。" if not edge else "把熟悉的味道做得认真，也为忙碌的日子留一份可以分享的小心意。",
            "产品": products, "截止说明": f"预订截止：{deadline.month}月{deadline.day}日18:00。",
            "自提说明": f"到店自提：{['梧桐街18号','清河路26号','花园巷9号','滨河路32号'][index % 4]}，10:00—19:00。",
            "预订方式": f"添加店长企业微信 {['maisui','qingye','xian'][int(key[-1])-1]}{index:03d} 预订。"}


def old_draft(data: dict, index: int) -> str:
    """真实可打开的旧稿；浅色半透明文字、桌面固定宽、超高hero轮换。

    所有问题都来自实际可见CSS，不塞提示注释或隐藏答案。
    """
    mode = index % 3
    trick = [".prices{min-width:720px}.hero{min-height:260px}",
             ".prices{opacity:.65}.hero{min-height:440px}",
             ".price{color:rgb(36 85 70 / 60%)}.hero{padding-block:130px}"][mode]
    rows = "".join(f"<article><h2>{html.escape(p['名称'])}</h2><p class=price>{p['价格']}</p></article>" for p in data["产品"])
    return f"""<!doctype html><html lang=zh-CN><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>{html.escape(data['主标题'])}</title><style>:root{{--primary:#3b82f6;--paper:#fff;--text:#1f2937}}*{{box-sizing:border-box}}body{{margin:0;font-family:Inter,Arial,sans-serif;color:var(--text);background:var(--paper)}}main{{max-width:1080px;margin:auto;padding:24px}}.hero{{padding:36px 0}}h1{{font-size:44px}}.prices{{display:flex;gap:24px}}article{{flex:1;background:rgba(59,130,246,.08);padding:20px}}a{{display:inline-block;background:var(--primary);color:#fff;padding:14px 24px;border-radius:24px;box-shadow:0 6px 24px #ddd}}{trick}</style>
<main><header>{data['店名']}</header><section class=hero><h1>{data['主标题']}</h1><p>{data['简介']}</p></section><section class=prices>{rows}</section><p><a href=#order-info>马上下单</a></p><section id=order-info><p>{data['截止说明']}</p><p>{data['自提说明']}</p><p>{data['预订方式']}</p></section></main></html>"""


def reference(key: str, data: dict) -> dict:
    r = RULES[key]
    return {"适用品牌": r["brand"], "必须原样可见": {k: v for k, v in data.items() if k != "产品"},
            "逐款内容": data["产品"], "手机首屏价格": [p["价格"] for p in data["产品"] if key != "R3" or p["状态"] == "可预订"],
            "手机首屏主按钮": r["cta"], "手机视口": r["mobile"], "桌面视口": r["desktop"],
            "允许实际色": [r["primary"], r["paper"], r["ink"], r["accent"], "#FFFFFF"], "不能作文字/底色": r["accent"],
            "标题字体首项": r["heading"], "其他字体首项": r["body"], "按钮四角px": r["radius"],
            "文字最低对比度": 4.5, "桌面main最大宽度px": r["max_width"],
            "手机店名位置": {"对齐": r["logo"], "bottom上限": r["logo_top"], "左对齐时left范围": [16, 28], "居中时中心误差上限": 8},
            "R3新口径": {"主按钮最低高度": 44, "非标题最小字号": 14, "售罄也要名称价格和状态、但不要求首屏": True} if key == "R3" else "不适用",
            "交付": "landing.html文件加允许的简短正文，或单个html代码块；两种选一；没有HTML只在LP-format记",
            "说明": "颜色、尺寸、可见性以浏览器测量为准；可修改旧稿或重写，不要求保留旧稿样式；不以美观偏好判卷。"}


def main() -> None:
    (HERE / "rules").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    bank, scripts = [], []
    for key in RULES:
        (HERE / "rules" / f"{key}.md").write_text(rules_text(key))
    for index in range(40):
        if index < 20:
            name, group, ordinal = f"t{index+1:02}", "train", index + 1
            key, edge = "R1" if ordinal % 2 else "R2", ordinal > 10
        elif index < 30:
            ordinal = index - 19
            name, group, key, edge = f"x{ordinal:02}", "same", "R1" if ordinal % 2 else "R2", ordinal > 5
        else:
            ordinal = index - 29
            name, group, key, edge = f"y{ordinal:02}", "new", "R3", ordinal > 5
        data = content(key, index + 1, edge)
        files = {"工作规则.md": rules_text(key), "内容.json": json.dumps(data, ensure_ascii=False, indent=2)}
        if edge:
            files["旧稿.html"] = old_draft(data, index)
        task = f"为{data['店名']}制作本次品牌预订落地页。工作目录有工作规则.md、内容.json" + (
            "、旧稿.html（可以改，也可以重写；只作设计起点）" if edge else "") + "。按本次工作规则制作并交付landing.html或单个html代码块；浏览器离线打开即可阅读。"
        ref = reference(key, data)
        assert len(set(p["名称"] for p in data["产品"])) == len(data["产品"])
        assert len(set(p["价格"] for p in data["产品"])) == len(data["产品"])
        assert ref["手机首屏价格"] and len(ref["手机首屏价格"]) <= 4
        question = {"name": name, "group": group, "segment": "edge" if edge else "common", "rules": key,
                    "text": task, "files": files, "reference": ref}
        bank.append(question)
        scripts.append({"name": name, "title": f"{name} · {data['店名']} · {'改稿' if edge else '新页'}", "exam": group != "train",
                        "steps": [{"text": task, "files": files}]})
    assert len({json.dumps(q["files"], ensure_ascii=False) for q in bank}) == 40
    assert {p["状态"] for q in bank if q["rules"] == "R3" for p in json.loads(q["files"]["内容.json"])["产品"]} == {"可预订", "已售罄"}
    dump = lambda p, o: p.write_text(json.dumps(o, ensure_ascii=False, indent=2) + "\n")
    dump(HERE / "questions.json", bank)
    dump(HERE / "scripts.json", scripts)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text("每次会提供当次品牌工作规则、内容数据；有时还有旧稿。请逐次读取并按本次规则制作单文件落地页，自己用浏览器检查手机和桌面效果。\n")
    (SCENARIO / "personas" / "owner.md").write_text("你是委托制作门店预订页的店长。把这次工作规则与内容数据交给设计师，要求直接交可离线打开的HTML；不要求联网发布。\n")
    dump(SCENARIO / "scenario.json", {"initial": [], "criteria": [{"id": k, "severity": s, "check": c} for k, s, c in CRITERIA]})
    dump(SCENARIO / "contract.json", {"checks": {k: {"visibility": ["counterpart", "analyst", "curator"]} for k, _, _ in CRITERIA}})
    dump(HERE / "manifest.json", {"name": "品牌落地页", "description": TASK, "owns": "负责根据当次品牌工作规则制作离线可读的单文件预订落地页。"})
    live = json.loads((HERE.parent / "refund-desk" / "live.json").read_text())
    live.update(root="../../../../runs/experts/landing-page", scenario="wkr-landing-page")
    dump(HERE / "live.json", live)
    print("40 questions, 3 rules, 20 common / 20 edge; scenario: wkr-landing-page")


if __name__ == "__main__":
    main()
