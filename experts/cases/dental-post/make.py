"""医疗营销推文审查：三套工作规则、40 道题（20 培养 + 10 道同规则考试 + 10 道换规则考试）、参考答案和 Studio 场景包。

  python3 make.py

依据《专家自进化》2.2 的案例（口腔诊所的种植牙推文送审）改写成「工作规则随题交给员工」：三家医疗机构的推文审查规则
结构相同、口径不同（疗效保证禁用词、医生署名写法、能用的配图、审查证明编号的写法、价格句、交付分几段）。培养题和同规则
考试题用 R1（齿然口腔）、R2（明澈眼科）交替，换规则考试题全用员工从没见过的 R3（悦颜医疗美容）；R3 多两处新口径：
名册里不是美容主诊医师的医生不能出现在推文里；发布日没有有效审查证明的项目要从推文里删掉。每道题给一篇推文和发布日期、
配图清单（文件名、标签）、医生名册（姓名、科室、职称）、医疗广告审查证明表（编号、覆盖项目、有效期）。边界题按种子
埋陷阱：证明过期后换了新编号（新旧都在表里）、有效期最后一天或第一天正好是发布日、新证明还没生效、一篇推两个项目、
配图没有标签但文件名写着“术后”、有标签的环境照文件名里带“术后”、名册里同名不同科室的医生排在前面。参考答案由本脚本
按规则算出；check.py 只读员工看到的文件另写一遍算法复核。
"""

import json
import random
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCENARIO = HERE / "wkr-dental-post"
YEAR = timedelta(days=364)
CALL = {"主任医师": "主任", "副主任医师": "主任", "主治医师": "医生", "医师": "医生"}

RULES = {
    "R1": {
        "brand": "齿然口腔", "place": "诊所",
        "banned": ["终身", "100%", "不松动", "永久", "零风险", "无痛", "根治"],
        "doctor_tpl": "姓名 职称", "doctor_fmt": "{name} {title}", "doctor_how": "中间空一格，例如“王建华 主任医师”",
        "doctor_sample": "王建华 主任医师",
        "doctor_basis": "职称", "doctor_no": "科室、从业年限、成功率、完成例数", "qualify": False,
        "photo": "诊所环境照", "labels_ok": ["诊所环境"], "keys_ok": ["环境"],
        "cert_head": "医疗广告审查证明编号", "cert_item": "编号", "cert_sep": "、", "drop": False,
        "price": "具体费用以面诊方案为准", "promo": ["立减", "特价", "优惠"], "urgency": ["名额有限", "仅限本月"],
        "sections": ("改后推文", "修改说明"), "listing": "table",
        "projects": {
            "种植牙": ("种植科", ("种植牙用德国进口种植体，终身不松动！", "种植牙零风险，一颗管终身！"), (2000, 3000), (3980, 4980)),
            "隐形矫正": ("正畸科", ("隐形矫正全程无痛，牙齿永久整齐！", "隐形矫正零风险，100% 矫正到位！"), (5000, 8000), (19800, 23800)),
            "牙齿美白": ("牙体牙髓科", ("牙齿美白零风险，美白效果永久保持！", "牙齿美白全程无痛，100% 白回来！"), (300, 500), (699, 999)),
            "全瓷牙冠": ("修复科", ("全瓷牙冠终身不变色，100% 贴合！", "全瓷牙冠零风险，戴上永久不松动！"), (800, 1000), (1980, 2680)),
            "窝沟封闭": ("儿童口腔科", ("窝沟封闭全程无痛，根治蛀牙！", "窝沟封闭零风险，孩子永久不蛀牙！"), (50, 80), (99, 128)),
        },
        "promos": ("立减 {a} 元", "特价 {a} 元", "优惠价 {a} 元"), "urgency_phrases": ("名额有限", "仅限本月"),
        "stats": ("成功率 {rate}%", "已完成 {cases} 例"),
        "roster": [
            ("李建国", "种植科", "副主任医师"), ("李建国", "修复科", "主任医师"), ("周海涛", "种植科", "主任医师"),
            ("刘洋", "种植科", "医师"), ("王芳", "正畸科", "主治医师"), ("王芳", "儿童口腔科", "副主任医师"),
            ("孙丽", "正畸科", "主任医师"), ("赵磊", "修复科", "副主任医师"), ("赵磊", "牙体牙髓科", "医师"),
            ("吴敏", "修复科", "主治医师"), ("郑红", "牙体牙髓科", "主治医师"), ("冯涛", "牙体牙髓科", "主任医师"),
            ("陈晓", "儿童口腔科", "主治医师"), ("黄倩", "儿童口腔科", "主任医师"),
        ],
        "images": {
            "env": ("诊所环境", ("前台接待区.jpg", "诊室全景.jpg", "候诊大厅.jpg", "消毒供应室.jpg", "诊所外景.jpg", "儿童诊室.jpg")),
            "env-post": ("诊所环境", ("术后休息区.jpg",)),
            "dev": ("设备展示", ("CBCT机.jpg", "口腔扫描仪.jpg", "牙椅设备.jpg")),
            "cmp": ("术前术后对比", ("前后对比_01.jpg", "对比图_张女士.jpg", "before_after.jpg")),
            "case": ("案例效果", ("案例展示.jpg", "顾客笑容.jpg")),
            "doc": ("医生照", ("医生合影.jpg", "专家团队.jpg")),
            "u-post": ("", ("种植术后_03.jpg", "术后效果图.jpg", "术后一周复查.jpg")),
            "u-env": ("", ("环境_二楼走廊.jpg", "诊所环境_门头.jpg")),
            "u-dev": ("", ("设备_口扫仪.jpg", "设备_消毒柜.jpg")),
            "u-raw": ("", ("IMG_2041.jpg", "微信图片_20260912.jpg")),
        },
        "seq": (10, 999),
        "number": lambda start, seq: f"（沪）医广【{start.year}】第 {start:%m}-{start:%d}-{seq:03d} 号",
    },
    "R2": {
        "brand": "明澈眼科", "place": "医院",
        "banned": ["一劳永逸", "告别眼镜", "永不反弹", "零风险", "无痛", "100%", "根治"],
        "doctor_tpl": "科室 姓名 职称", "doctor_fmt": "{dept} {name} {title}", "doctor_how": "用空格隔开，例如“屈光科 李明 主治医师”",
        "doctor_sample": "屈光科 李明 主治医师",
        "doctor_basis": "科室和职称", "doctor_no": "从业年限、成功率、完成例数", "qualify": False,
        "photo": "医院环境照和检查设备照", "labels_ok": ["医院环境", "检查设备"], "keys_ok": ["环境", "设备"],
        "cert_head": "审查证明", "cert_item": "编号（有效期至 YYYY-MM-DD）", "cert_sep": "；", "drop": False,
        "price": "费用以术前检查后的方案为准", "promo": ["立减", "特惠", "免费"], "urgency": ["名额有限", "先到先得", "手慢无"],
        "sections": ("修改后推文", "修改记录"), "listing": "numbered",
        "projects": {
            "全飞秒": ("屈光科", ("全飞秒近视手术一劳永逸，从此告别眼镜！", "全飞秒全程无痛，度数永不反弹！"), (3000, 5000), (15800, 18800)),
            "晶体植入": ("屈光科", ("晶体植入零风险，高度近视从此告别眼镜！", "晶体植入一劳永逸，视力永不反弹！"), (5000, 6000), (26800, 29800)),
            "白内障手术": ("白内障科", ("白内障手术全程无痛，一劳永逸！", "白内障手术零风险，100% 复明，从此告别眼镜！"), (1000, 2000), (5800, 8800)),
            "角膜塑形镜": ("视光科", ("角膜塑形镜根治近视，度数永不反弹！", "孩子戴角膜塑形镜零风险，从此告别眼镜！"), (1000, 1500), (6800, 8800)),
            "干眼治疗": ("眼表科", ("干眼治疗全程无痛，一劳永逸！", "干眼治疗根治干眼，症状永不反弹！"), (200, 300), (680, 980)),
        },
        "promos": ("立减 {a} 元", "特惠价 {a} 元", "送免费检查"), "urgency_phrases": ("名额有限", "先到先得", "手慢无"),
        "stats": ("已完成 {cases} 例", "成功率 {rate}%"),
        "roster": [
            ("张华", "屈光科", "主治医师"), ("张华", "白内障科", "主任医师"), ("刘振宇", "屈光科", "主任医师"),
            ("高远", "屈光科", "副主任医师"), ("何静", "白内障科", "副主任医师"), ("何静", "视光科", "主治医师"),
            ("唐亮", "白内障科", "医师"), ("马超", "视光科", "副主任医师"), ("许晴", "视光科", "主任医师"),
            ("林雪", "眼表科", "主治医师"), ("林雪", "屈光科", "副主任医师"), ("宋佳", "眼表科", "主任医师"),
            ("杜明", "眼表科", "医师"),
        ],
        "images": {
            "env": ("医院环境", ("门诊大厅.jpg", "检查区走廊.jpg", "验光室.jpg", "候诊区一角.jpg")),
            "env-post": ("医院环境", ("术后观察室.jpg",)),
            "dev": ("检查设备", ("角膜地形图仪.jpg", "眼底照相机.jpg", "OCT检查仪.jpg")),
            "cmp": ("术前术后对比", ("视力对比图.jpg", "术前术后视力表.jpg")),
            "case": ("患者感言", ("感谢信.jpg", "摘镜感言.jpg")),
            "doc": ("医生照", ("医生团队.jpg", "主任出诊照.jpg")),
            "u-post": ("", ("术后复查_王先生.jpg", "术后第一天.jpg")),
            "u-env": ("", ("医院环境_大厅.jpg", "环境_手术区外.jpg")),
            "u-dev": ("", ("设备_验光仪.jpg", "新设备_裂隙灯.jpg")),
            "u-raw": ("", ("IMG_5530.jpg", "DSC_0912.jpg")),
        },
        "seq": (100, 9999),
        "number": lambda start, seq: f"京医广〔{start.year}〕第 {seq:04d} 号",
    },
    "R3": {
        "brand": "悦颜医疗美容", "place": "机构",
        "banned": ["永久", "零风险", "无痛", "无副作用", "立竿见影", "逆龄", "100%"],
        "doctor_tpl": "姓名（职称）", "doctor_fmt": "{name}（{title}）", "doctor_how": "例如“周琳（主治医师）”",
        "doctor_sample": "周琳（主治医师）",
        "doctor_basis": "职称", "doctor_no": "科室、从业年限、成功率、完成例数", "qualify": True,
        "photo": "机构环境照和资质证照", "labels_ok": ["机构环境", "资质证照"], "keys_ok": ["环境", "证照"],
        "cert_head": "广告审查编号", "cert_item": "编号", "cert_sep": "、", "drop": True,
        "price": "最终费用以面诊评估为准", "promo": ["立减", "特价", "秒杀"], "urgency": ["名额有限", "限时", "仅剩"],
        "sections": ("审查结论", "改后推文", "修改说明"), "listing": "table",
        "projects": {
            "双眼皮": ("美容外科", ("双眼皮手术零风险，效果永久！", "双眼皮手术全程无痛，效果立竿见影！"), (2000, 3000), (6800, 8800)),
            "热玛吉": ("美容皮肤科", ("热玛吉一次逆龄十岁，立竿见影！", "热玛吉全程无痛，紧致效果永久！"), (3000, 5000), (9800, 12800)),
            "光子嫩肤": ("美容皮肤科", ("光子嫩肤无痛无副作用，立竿见影！", "光子嫩肤零风险，一次逆龄！"), (300, 500), (880, 1280)),
            "玻尿酸填充": ("注射美容科", ("玻尿酸填充 100% 安全，零风险！", "玻尿酸填充无副作用，效果立竿见影！"), (800, 1000), (2980, 3680)),
            "激光祛斑": ("美容皮肤科", ("激光祛斑永久祛除，无副作用！", "激光祛斑全程无痛，100% 祛除！"), (500, 800), (1280, 1980)),
        },
        "promos": ("立减 {a} 元", "特价 {a} 元", "秒杀价 {a} 元"), "urgency_phrases": ("名额有限", "限时 3 天", "仅剩 8 个名额"),
        "stats": ("成功率 {rate}%", "已完成 {cases} 例"),
        "roster": [
            ("陈静", "美容外科", "主任医师", "是"), ("陈静", "美容皮肤科", "主治医师", "否"), ("杨帆", "美容外科", "副主任医师", "是"),
            ("苏晨", "美容外科", "主治医师", "否"), ("罗娜", "美容皮肤科", "副主任医师", "是"), ("罗娜", "注射美容科", "主治医师", "否"),
            ("邓凯", "美容皮肤科", "医师", "否"), ("程琳", "美容皮肤科", "主治医师", "否"), ("白雪", "美容皮肤科", "主任医师", "是"),
            ("韩梅", "注射美容科", "主治医师", "是"), ("方圆", "注射美容科", "副主任医师", "是"),
        ],
        "images": {
            "env": ("机构环境", ("大堂.jpg", "VIP休息室.jpg", "咨询室.jpg", "手术室外走廊.jpg")),
            "env-post": ("机构环境", ("术后恢复室.jpg",)),
            "lic": ("资质证照", ("医疗机构执业许可证.jpg", "营业执照.jpg")),
            "dev": ("仪器设备", ("射频仪.jpg", "光电仪器.jpg")),
            "cmp": ("术前术后对比", ("眼部对比图.jpg", "术前术后_01.jpg")),
            "case": ("案例效果", ("顾客案例_A女士.jpg", "效果展示.jpg")),
            "doc": ("医生照", ("医生坐诊照.jpg", "院长照片.jpg")),
            "u-post": ("", ("术后第7天.jpg", "术后效果_侧脸.jpg")),
            "u-env": ("", ("机构环境_前厅.jpg", "环境_走廊.jpg")),
            "u-lic": ("", ("证照_执业许可证.jpg", "证照_卫生许可.jpg")),
            "u-raw": ("", ("IMG_8812.jpg", "微信图片_20261101.jpg")),
        },
        "seq": (10000, 99999),
        "number": lambda start, seq: f"浙医广〔{start.year}〕{seq:05d} 号",
    },
}

# name, group, segment, rules, publish date, promoted projects, doctors named in the post (name, department), certificate
# situation per project, image kinds, whether the roster carries a same-name doctor of another department ahead of each one.
# Certificate situations: plain (one valid certificate), renewed (expired one, then its valid successor), boundary_old (the
# old one ends on the publish date, the new one starts the day after), boundary_new (the new one starts on the publish date),
# pending (the old one is still valid, the new one starts later), lapsed (only an expired one), gap (expired, and the new
# one starts later). Image kinds: env / dev / lic / cmp / case / doc are tagged, env-post is a tagged environment photo whose
# file name says 术后, u-* are untagged (u-post: the file name says 术后).
SPECS = [
    ("t01", "train", "common", "R1", "2026-10-15", ("种植牙",), (("李建国", "种植科"),), ("plain",), "env env cmp doc", False),
    ("t02", "train", "common", "R2", "2026-10-16", ("全飞秒",), (("刘振宇", "屈光科"),), ("plain",), "env dev cmp case", False),
    ("t03", "train", "common", "R1", "2026-10-22", ("隐形矫正",), (("孙丽", "正畸科"),), ("plain",), "env cmp case dev", False),
    ("t04", "train", "common", "R2", "2026-10-23", ("白内障手术",), (("唐亮", "白内障科"),), ("plain",), "env dev cmp doc", False),
    ("t05", "train", "common", "R1", "2026-11-05", ("牙齿美白",), (("郑红", "牙体牙髓科"),), ("plain",), "env env cmp dev", False),
    ("t06", "train", "common", "R2", "2026-11-06", ("角膜塑形镜",), (("马超", "视光科"),), ("plain",), "env env dev cmp", False),
    ("t07", "train", "common", "R1", "2026-11-18", ("全瓷牙冠",), (("吴敏", "修复科"),), ("plain",), "env cmp doc case", False),
    ("t08", "train", "common", "R2", "2026-11-19", ("干眼治疗",), (("宋佳", "眼表科"),), ("plain",), "env dev case doc", False),
    ("t09", "train", "common", "R1", "2026-12-02", ("窝沟封闭",), (("黄倩", "儿童口腔科"),), ("plain",), "env env case dev", False),
    ("t10", "train", "common", "R2", "2026-12-03", ("晶体植入",), (("高远", "屈光科"),), ("plain",), "env dev cmp case", False),
    ("t11", "train", "edge", "R1", "2026-10-20", ("种植牙", "牙齿美白"), (("李建国", "种植科"),), ("renewed", "plain"),
     "env cmp u-post u-env dev", True),
    ("t12", "train", "edge", "R2", "2026-10-21", ("全飞秒", "角膜塑形镜"), (("张华", "屈光科"),), ("renewed", "plain"),
     "env dev u-post u-env cmp", True),
    ("t13", "train", "edge", "R1", "2026-11-10", ("全瓷牙冠",), (("赵磊", "修复科"),), ("boundary_old",),
     "env env-post u-post u-raw doc", True),
    ("t14", "train", "edge", "R2", "2026-11-11", ("白内障手术",), (("何静", "白内障科"),), ("boundary_old",),
     "env dev env-post u-post u-raw case", True),
    ("t15", "train", "edge", "R1", "2026-11-24", ("隐形矫正", "窝沟封闭"), (("王芳", "儿童口腔科"),), ("plain", "renewed"),
     "env cmp u-post u-dev case", True),
    ("t16", "train", "edge", "R2", "2026-11-25", ("干眼治疗", "晶体植入"), (("林雪", "眼表科"),), ("plain", "renewed"),
     "dev u-post u-env u-raw doc", True),
    ("t17", "train", "edge", "R1", "2026-12-08", ("全瓷牙冠", "种植牙"), (("李建国", "修复科"), ("周海涛", "种植科")),
     ("pending", "boundary_new"), "env u-post u-env cmp dev", True),
    ("t18", "train", "edge", "R2", "2026-12-09", ("全飞秒", "白内障手术"), (("张华", "白内障科"), ("刘振宇", "屈光科")),
     ("pending", "boundary_new"), "env dev u-post u-dev cmp", True),
    ("t19", "train", "edge", "R1", "2027-01-12", ("牙齿美白", "隐形矫正"), (("赵磊", "牙体牙髓科"),), ("boundary_new", "renewed"),
     "env env-post u-post u-raw cmp", True),
    ("t20", "train", "edge", "R2", "2027-01-13", ("角膜塑形镜",), (("何静", "视光科"),), ("boundary_new",),
     "env env-post u-post u-dev case", True),
    ("x01", "same", "common", "R1", "2026-12-09", ("种植牙",), (("周海涛", "种植科"),), ("plain",), "env cmp dev doc", False),
    ("x02", "same", "common", "R2", "2026-12-10", ("全飞秒",), (("张华", "屈光科"),), ("plain",), "env dev dev cmp", False),
    ("x03", "same", "common", "R1", "2026-12-16", ("牙齿美白",), (("冯涛", "牙体牙髓科"),), ("plain",), "env env cmp case", False),
    ("x04", "same", "common", "R2", "2026-12-17", ("角膜塑形镜",), (("许晴", "视光科"),), ("plain",), "env dev cmp doc", False),
    ("x05", "same", "common", "R1", "2027-01-06", ("全瓷牙冠",), (("赵磊", "修复科"),), ("plain",), "env cmp dev case", False),
    ("x06", "same", "edge", "R2", "2026-12-15", ("晶体植入", "干眼治疗"), (("林雪", "屈光科"),), ("renewed", "pending"),
     "env dev u-post u-env doc", True),
    ("x07", "same", "edge", "R1", "2026-12-22", ("种植牙", "全瓷牙冠"), (("李建国", "种植科"),), ("renewed", "pending"),
     "env cmp u-post u-env doc dev", True),
    ("x08", "same", "edge", "R2", "2027-01-07", ("白内障手术", "角膜塑形镜"), (("何静", "白内障科"),), ("boundary_new", "renewed"),
     "env u-post u-dev u-raw cmp", True),
    ("x09", "same", "edge", "R1", "2027-01-14", ("隐形矫正",), (("王芳", "正畸科"),), ("boundary_old",),
     "env u-post u-dev env-post case", True),
    ("x10", "same", "edge", "R2", "2027-01-20", ("全飞秒",), (("张华", "屈光科"),), ("renewed",), "env dev env-post u-post case", True),
    ("y01", "new", "common", "R3", "2026-10-28", ("双眼皮",), (("杨帆", "美容外科"),), ("plain",), "env lic cmp case", False),
    ("y02", "new", "common", "R3", "2026-11-12", ("光子嫩肤",), (("邓凯", "美容皮肤科"),), ("plain",), "env lic cmp dev", False),
    ("y03", "new", "common", "R3", "2026-11-26", ("玻尿酸填充",), (("韩梅", "注射美容科"),), ("plain",), "env env cmp doc", False),
    ("y04", "new", "common", "R3", "2026-12-11", ("热玛吉",), (("程琳", "美容皮肤科"),), ("plain",), "env lic dev case", False),
    ("y05", "new", "common", "R3", "2027-01-08", ("激光祛斑",), (("白雪", "美容皮肤科"),), ("plain",), "env lic cmp doc", False),
    ("y06", "new", "edge", "R3", "2026-10-29", ("双眼皮", "热玛吉"), (("陈静", "美容外科"),), ("plain", "lapsed"),
     "env lic u-post u-env cmp", True),
    ("y07", "new", "edge", "R3", "2026-11-13", ("光子嫩肤",), (("陈静", "美容皮肤科"),), ("renewed",),
     "env lic env-post u-post u-raw dev", True),
    ("y08", "new", "edge", "R3", "2026-11-27", ("玻尿酸填充", "激光祛斑"), (("罗娜", "注射美容科"),), ("gap", "boundary_old"),
     "env u-post u-lic u-raw case", True),
    ("y09", "new", "edge", "R3", "2026-12-14", ("热玛吉", "双眼皮"), (("罗娜", "美容皮肤科"), ("苏晨", "美容外科")),
     ("boundary_new", "pending"), "lic u-post u-env dev doc", True),
    ("y10", "new", "edge", "R3", "2027-01-15", ("激光祛斑", "双眼皮"), (("陈静", "美容外科"),), ("renewed", "gap"),
     "env lic env-post u-post u-lic cmp", True),
]

TASK = (
    "你是医疗机构市场部的推文审查员。市场同事会把准备发布的公众号推文和发布日期发给你，工作目录里有这次适用的推文审查"
    "工作规则、推文的配图清单、医生名册和医疗广告审查证明表。按这次给的工作规则改好推文，交代改了什么，同事拿去直接发布。"
)
ONBOARDING = "以后每篇推文，我都会把这次适用的推文审查工作规则、配图清单、医生名册和医疗广告审查证明表一起发给你。不同机构的规则不一样，以当次给的为准。"
CRITERIA = [
    ("DP-claims", "standard",
     "疗效保证词：只看推文那一段（段名里带“推文”的那一段），这次工作规则第 1 条列出的词一个都不能出现，是别的词的一部分也算，"
     "改写时也不能新加（测量值列出了推文段里还能找到的第 1 条词语）；推文段里每留下或新加一个，记一处。改动清单里引用的原文"
     "不算；第 1 条没列的说法不归本项判。"),
    ("DP-doctor", "standard",
     "医生署名：推文里写到的每位医生，按“姓名 + 推文里写的科室”在《医生名册》里对上那一行（以参考答案为准），按这次工作规则"
     "第 2 条的写法写，职称照那一行写全，不带第 2 条不许带的内容（以规则为准：从业年限、成功率、完成例数，规则不许写时还有"
     "科室）；参考答案注明要整句删掉的医生，推文段里不能再出现这位医生的名字。职称错（例如用了名册里同名另一科室那位的职称，"
     "或照抄原文的“主任”“医生”）、写法不对、带着不许带的内容、该删没删，每位医生每处记一处。第 2 条允许的引导说法（例如"
     "“主诊医生：”）不算错。"),
    ("DP-image", "standard",
     "配图：推文段里“配图：”那一行列出的文件要和参考答案“能用的图”完全一致，先后不限（测量值列出了推文段里出现的配图文件名）；"
     "多列一张不能用的、漏列一张能用的，每张记一处；推文段里没有“配图：”这一行，记一处。"),
    ("DP-cert", "red_line",
     "审查编号：推文段最后一行按这次工作规则第 4 条的写法，标出参考答案给出的每一个编号，先后不限（推两个项目要两个都标）。"
     "用了过期、还没生效或不覆盖推广项目的编号，漏标，审查编号不在推文段最后一行，写法不对（开头的名称、分隔符、规则要求写的"
     "有效期日期），每处记一处。参考答案注明要删掉的项目（发布日没有有效证明），推文段里还出现这个项目的名字，或“## 审查结论”"
     "写的删掉的项目和参考答案不一致，每处记一处；参考答案注明不适用删项目的，这一部分不判。"),
    ("DP-format", "standard",
     "价格句和交付格式：推文段里要逐字写出这次工作规则第 5 条规定的那句价格话，不能留“X 元”这样的金额，也不能留第 5 条列出的词"
     "（测量值列出了推文段里的金额和还能找到的第 5 条词语）；交付按第 6 条的段数、段名和顺序（每段以“## 段名”开头），第一段前、"
     "最后一段后不能有别的文字（例如开场白、结尾总结），推文正文里不能夹修改备注；改动清单按第 6 条的格式写（表格的列，或编号"
     "列表每条的写法），推文正文里改了、删了、加了的每一处和不用的每一张图都要列出。每处不符记一处。第 6 条说了不用列的"
     "（“配图：”这一行、没改的话）没列不算错；改动按句列或拆细列都可以。"),
]


def quoted(words) -> str:
    return "".join(f"“{w}”" for w in words)


def either(words) -> str:
    return "或".join(f"“{w}”" for w in words)


def rules_text(rule: str) -> str:
    r = RULES[rule]
    post, listing = r["sections"][-2], r["sections"][-1]
    cert_word = "审查证明" if r["cert_item"] != "编号" else "审查编号"
    tpl, sample = r["doctor_tpl"], r["doctor_sample"]
    lines = [
        f"# {r['brand']} · 公众号推文审查工作规则", "",
        f"市场同事发来的推文，按下面的规则改好再发布。题面给推文原文和发布日期；工作目录里的《配图清单》是这篇推文现在配的图，"
        f"《医生名册》和《审查证明表》是{r['place']}的医生名册和医疗广告审查证明。", "",
        f"1. 疗效保证：{post}里不出现这几个词：{quoted(r['banned'])}（是别的词的一部分也不行）。原文里带这些词的话要删掉或改写，"
        f"改写后也不能带这几个词。第 1 条只管这几个词，原文别的说法不用按第 1 条改。",
    ]
    find = "先按“姓名 + 推文里写的科室”在《医生名册》里找到这位医生那一行"
    write = (f"写成“{tpl}”（{r['doctor_how']}），{r['doctor_basis']}照那一行写全，原文的称呼（例如“李主任”“王医生”）不算职称。"
             f"写到医生的那句可以写成“主诊医生：{sample}。”，也可以换别的说法，但这位医生只能出现“{tpl}”这一串，"
             f"不带{r['doctor_no']}（例如“从业 10 年”“成功率 98%”“已完成 2000 例”）。")
    if r["qualify"]:
        lines.append(f"2. 医生：推文里写到的每位医生，{find}，再看“美容主诊医师”一栏：如果是“否”，就把写到这位医生的那句整句删掉，"
                     f"{post}里不再出现这位医生的名字，也不换成别的医生；如果是“是”，就{write}")
    else:
        lines.append(f"2. 医生：推文里写到的每位医生，{find}，{write}")
    lines.append(f"3. 配图：只用{r['photo']}。《配图清单》里的每张图：如果“标签”一栏有字，就只看标签，标签是{either(r['labels_ok'])}"
                 f"的能用，否则不能用，文件名写什么都不管；如果“标签”一栏是空的，就看文件名，文件名里有{either(r['keys_ok'])}的能用，"
                 f"否则不能用。")
    look = "《审查证明表》里“覆盖项目”有这个项目、发布日在有效期内的那一张"
    if r["cert_item"] != "编号":
        lines.append(f"4. 审查证明：{post}的最后一行写“{r['cert_head']}：{r['cert_item']}”，日期照《审查证明表》里这张证明有效期的"
                     f"最后一天写。每个推广项目各找一张证明：{look}。推一个项目就写一组；推两个项目就写两组，两组之间用"
                     f"“{r['cert_sep']}”隔开，先后不限，即“{r['cert_head']}：{r['cert_item']}{r['cert_sep']}{r['cert_item']}”。")
    elif r["drop"]:
        lines.append(f"4. 审查编号：{post}的最后一行写“{r['cert_head']}：编号”。每个推广项目先找{look}：如果找到了，就写这张证明的"
                     f"编号；如果找不到（这个项目在发布日没有有效证明：过期了没续上、新证明还没生效，或者表里没有这个项目），就把写"
                     f"这个项目的话（介绍、价格）都删掉，{post}里不再出现这个项目的名字，也不写它的编号。留下一个项目就写一个编号；"
                     f"留下两个项目就写两个编号，用“{r['cert_sep']}”隔开，先后不限。")
    else:
        lines.append(f"4. 审查编号：{post}的最后一行写“{r['cert_head']}：编号”。每个推广项目各找一张证明：{look}，写它的编号。"
                     f"推一个项目就写一个编号；推两个项目就写两个编号，用“{r['cert_sep']}”隔开，先后不限。")
    lines.append(f"5. 价格：{post}里价格只写一句“{r['price']}”（逐字照写），原文讲价格和优惠的话都换成这一句；原文的“点击预约”"
                 f"可以留着。{post}里不出现“X 元”这样的金额，也不出现{quoted(r['promo'] + r['urgency'])}这几个词。")
    body = (f"“## {post}”按顺序写三部分：推文正文（直接能发布的文字，不夹修改备注）；单独一行“配图：文件名、文件名”（只列能用的图，"
            f"先后不限；一张能用的都没有就写“配图：无”）；最后一行写第 4 条的{cert_word}。")
    if r["listing"] == "table":
        how = (f"“## {listing}”是表格，三列：原文 | 改成 | 依据第几条。推文正文里改了、删了、加了的每一处（包括加上的{cert_word}行）"
               f"和不用的每一张图，都要列一行：改动可以一句一行，也可以拆得更细；不用的图“原文”写文件名、“改成”写“不用”；")
    else:
        how = (f"“## {listing}”是编号列表，每条写成“原文 → 改成（第 X 条）”。推文正文里改了、删了、加了的每一处（包括加上的"
               f"{cert_word}行）和不用的每一张图，都要列一条：改动可以一句一条，也可以拆得更细；不用的图写成“文件名 → 不用（第 3 条）”；")
    how += "“配图：”这一行本身和没改的话不用列。"
    names = "".join(f"“## {s}”" for s in r["sections"])
    count = {2: "两", 3: "三"}[len(r["sections"])]
    six = f"6. 交付{count}段，按顺序：{names}；只交这{count}段，{count}段前后不加别的文字。"
    if len(r["sections"]) == 3:
        six += (f"“## {r['sections'][0]}”只写一行：如果有项目按第 4 条删掉了，就写“删掉的项目：项目名”；如果没有，就写"
                f"“删掉的项目：无”。")
    lines.append(six + body + how)
    lines += [
        "", "补充口径：", "",
        "- 推文里写到的项目名（《审查证明表》“覆盖项目”一栏里的那些名字）就是推广项目。",
        "- 有效期含首尾两天：例如“2025-10-01 至 2026-09-30”在 2026-09-30 当天仍有效，2026-10-01 起失效。",
        "- 证明过期后会换新编号，新旧编号都留在《审查证明表》里；按发布日选在有效期内的那一张，还没开始生效的新证明也不能用。",
        "- 一张证明可能覆盖几个项目，看“覆盖项目”一栏。",
        "- 《医生名册》里同名不同科室的是两个人，以“姓名 + 推文里写的科室”对上的那一行为准。",
        "- 《配图清单》里“标签”一栏空着的，就是没有标签。",
        f"- 规则没要求改的话（例如开头的机构名），可以照原文留着，也可以为了通顺改写；改写过的话同样要守上面的规则，也要列进"
        f"“## {listing}”。",
        "",
    ]
    return "\n".join(lines)


def usable(rule, file, label) -> bool:
    r = RULES[rule]
    return label in r["labels_ok"] if label else any(key in file for key in r["keys_ok"])


def valid(cert, day) -> bool:
    return cert["start"] <= day <= cert["end"]


def build(spec, rng):
    """The post and its parts, the roster, the image list and the certificate table for one question."""
    name, group, segment, rule, day_text, projects, doctors, kinds, codes, same = spec
    r = RULES[rule]
    day = date.fromisoformat(day_text)
    claims = [(p, rng.choice(r["projects"][p][1])) for p in projects]
    pool = r["roster"]
    targets = [next(row for row in pool if row[:2] == pair) for pair in doctors]
    names = {row[0] for row in targets}
    decoys = [row for row in pool if row[0] in names and row not in targets] if same else []
    fillers, seen = [], set()
    for row in rng.sample(pool, len(pool)):
        if row[0] in names or row[0] in seen:
            continue
        seen.add(row[0])
        fillers.append(row)
    rows = fillers[:8 - len(targets) - len(decoys)] + targets
    rng.shuffle(rows)
    for decoy in decoys:
        at = next(i for i, row in enumerate(rows) if row[0] == decoy[0] and row in targets)
        rows.insert(rng.randint(0, at), decoy)
    lines = []
    for row in targets:
        stat = rng.choice(r["stats"]).format(rate=rng.choice(["96.8", "97.5", "98.2", "98.6", "99.1", "99.3"]),
                                             cases=rng.choice([1200, 2000, 3000, 5000, 8000]))
        years = f"从业 {rng.randint(8, 30)} 年"
        lines.append((row, f"{row[1]}{row[0]}{CALL[row[2]]}{years}，{stat}。", years, stat))
    offers = []
    for p in projects:
        promo = rng.choice(r["promos"])
        amount = rng.choice(r["projects"][p][2] if promo.startswith("立减") else r["projects"][p][3])
        offers.append(f"{p}{promo.format(a=amount)}")
    urgency = rng.choice(r["urgency_phrases"])
    price = "、".join(offers) + f"，{urgency}，点击预约！"
    post = f"【{r['brand']}】" + "".join(c for _, c in claims) + "".join(line[1] for line in lines) + price
    images, used = [], set()
    for code in codes.split():
        label, files = r["images"][code]
        file = rng.choice([f for f in files if f not in used])
        used.add(file)
        images.append((file, label))
    rng.shuffle(images)
    certs = certificates(spec, rng, day)
    return {"post": post, "claims": claims, "doctors": lines, "price": price, "offers": offers, "urgency": urgency,
            "roster": rows, "decoys": decoys, "images": images, "certs": certs}


def certificates(spec, rng, day) -> list[dict]:
    rule, projects, kinds = spec[3], spec[5], spec[7]
    r = RULES[rule]
    others = [p for p in r["projects"] if p not in projects]
    rng.shuffle(others)
    taken = set()

    def cert(covered, start):
        while True:
            seq = rng.randint(*r["seq"])
            if seq not in taken:
                taken.add(seq)
                return {"number": r["number"](start, seq), "projects": covered, "start": start, "end": start + YEAR}

    groups = []
    for p, kind in zip(projects, kinds):
        if kind == "plain":
            extra = [others.pop()] if others and rng.random() < 0.4 else []
            groups.append([cert([p] + extra, day - timedelta(days=rng.randint(20, 300)))])
        elif kind == "renewed":
            new = day - timedelta(days=rng.randint(5, 80))
            groups.append([cert([p], new - timedelta(days=365)), cert([p], new)])
        elif kind == "boundary_old":
            groups.append([cert([p], day - YEAR), cert([p], day + timedelta(days=1))])
        elif kind == "boundary_new":
            groups.append([cert([p], day - timedelta(days=365)), cert([p], day)])
        elif kind == "pending":
            new = day + timedelta(days=rng.randint(5, 40))
            groups.append([cert([p], new - timedelta(days=365)), cert([p], new)])
        elif kind == "lapsed":
            groups.append([cert([p], day - timedelta(days=rng.randint(5, 60)) - YEAR)])
        elif kind == "gap":
            old = cert([p], day - timedelta(days=rng.randint(5, 30)) - YEAR)
            groups.append([old, cert([p], day + timedelta(days=rng.randint(3, 20)))])
        else:
            raise ValueError(kind)
    while others:
        covered = [others.pop()] + ([others.pop()] if others and rng.random() < 0.5 else [])
        groups.append([cert(covered, day - timedelta(days=rng.randint(20, 300)))])
    rng.shuffle(groups)
    return [c for group in groups for c in group]


def doctor_text(rule, row) -> str:
    return RULES[rule]["doctor_fmt"].format(name=row[0], dept=row[1], title=row[2])


def cert_line(rule, picked) -> str:
    r = RULES[rule]
    items = [r["cert_item"].replace("编号", c["number"]).replace("YYYY-MM-DD", c["end"].isoformat()) for c in picked]
    return f"{r['cert_head']}：" + r["cert_sep"].join(items)


def compute(spec, built) -> dict:
    """The reference answer, with the checks that the answer is unique and every planted trap would change it."""
    name, group, segment, rule, day_text, projects, doctors, kinds, codes, same = spec
    r = RULES[rule]
    day = date.fromisoformat(day_text)
    post = built["post"]
    others = [set(RULES[o]["banned"]) for o in RULES if o != rule and (rule == "R3" or o != "R3")]
    everything = set().union(*(set(RULES[o]["banned"]) for o in RULES))
    found = [w for w in r["banned"] if w in post]
    for p, claim in built["claims"]:
        assert {w for w in everything if w in claim} <= set(r["banned"]), (name, claim)
    kept = [p for p, kind in zip(projects, kinds) if kind not in ("lapsed", "gap")]
    kept_claims = "".join(c for p, c in built["claims"] if p in kept)
    assert any(w in kept_claims for w in set(r["banned"]) - set().union(*others)), (name, "no word only this rule bans")
    assert not [p for p in RULES[rule]["projects"] if p not in projects and p in post], name
    words5 = r["promo"] + r["urgency"]
    assert any(w in built["price"] for w in r["promo"]) and any(w in built["price"] for w in r["urgency"]), name
    assert not [w for w in words5 if w in post.replace(built["price"], "")], (name, "price words outside the price sentence")

    # doctors
    roster = built["roster"]
    assert len({row[:2] for row in roster}) == len(roster), name
    doctor_refs = []
    for row, sentence, years, stat in built["doctors"]:
        hits = [x for x in roster if f"{x[1]}{x[0]}" in post]
        assert row in hits, name
        first = next(x for x in roster if x[0] == row[0])
        deleted = r["qualify"] and row[3] == "否"
        entry = {
            "推文原写": sentence,
            "按姓名 + 科室对上的名册那一行": " | ".join(row),
            "该写": "（整句删掉）" if deleted else doctor_text(rule, row),
        }
        if deleted:
            entry["说明"] = (f"名册里这一行“美容主诊医师”是“否”：写到{row[0]}的这句整句删掉，推文段里不能再出现“{row[0]}”，"
                           "也不换成别的医生")
        else:
            drop = [years, stat] + ([f"科室“{row[1]}”"] if "科室" in r["doctor_no"] else [])
            entry["要删的内容"] = drop
            entry["说明"] = (f"职称照名册写“{row[2]}”，不是原文的“{CALL[row[2]]}”；那句可以写成“主诊医生：{doctor_text(rule, row)}。”，"
                           "也可以换别的说法，只要这位医生只出现“该写”这一串")
        if same and first != row:
            entry["陷阱"] = (f"名册里排在前面的同名医生“{' | '.join(first)}”是另一个科室的另一个人，"
                           + ("不能用那一行的职称和美容主诊医师资格" if r["qualify"] else "不能用那一行的职称"))
            assert first[2] != row[2], (name, "the same-name doctor must carry another title")
            if r["qualify"]:
                assert first[3] != row[3], (name, "the same-name doctor must differ in qualification")
        doctor_refs.append(entry)
    assert len([x for x in roster if f"{x[1]}{x[0]}" in post]) == len(built["doctors"]), name
    if same:
        assert built["decoys"] and any("陷阱" in entry for entry in doctor_refs), name

    # images
    images = built["images"]
    files = [f for f, _ in images]
    assert len(set(files)) == len(files) and not [a for a in files for b in files if a != b and a in b], (name, files)
    ok = [f for f, label in images if usable(rule, f, label)]
    bad = [(f, label) for f, label in images if not usable(rule, f, label)]
    assert ok and bad, name
    if "u-post" in codes:
        assert [f for f, label in images if not label] and ok != [f for f, label in images if not label or label in r["labels_ok"]], name
        assert any("术后" in f and not label for f, label in bad), name
    if "env-post" in codes:
        assert ok != [f for f in ok if "术后" not in f], name
    if any(c in codes.split() for c in ("u-env", "u-lic")) or ("u-dev" in codes and rule == "R2"):
        assert ok != [f for f, label in images if label in r["labels_ok"]], name

    def reason(file, label):
        if label:
            return f"{file}（标签是“{label}”，" + ("能用）" if usable(rule, file, label) else "不是规则允许的标签）")
        hit = [k for k in r["keys_ok"] if k in file]
        if hit:
            return f"{file}（没有标签，文件名里有“{hit[0]}”）"
        tail = "，文件名写着“术后”" if "术后" in file else ""
        return f"{file}（没有标签，文件名里没有{either(r['keys_ok'])}{tail}）"

    image_ref = {"能用的图（“配图：”这一行要正好列这些，先后不限）": ok, "能用的原因": [reason(f, l) for f, l in images if f in ok],
                 "不能用的图": [reason(f, l) for f, l in bad]}
    if "env-post" in codes:
        image_ref["注意"] = "有标签的只看标签：文件名里带“术后”但标签是允许的环境照，照样能用"

    # certificates
    certs = built["certs"]
    numbers = [c["number"] for c in certs]
    assert len(set(numbers)) == len(numbers) and not [a for a in numbers for b in numbers if a != b and a in b], name
    per_project, picked, dropped = [], [], []
    for p, kind in zip(projects, kinds):
        covering = [c for c in certs if p in c["projects"]]
        good = [c for c in covering if valid(c, day)]
        first = covering[0]
        latest = max(covering, key=lambda c: c["start"])
        if kind in ("lapsed", "gap"):
            assert r["drop"] and not good and covering, (name, p)
            dropped.append(p)
        else:
            assert len(good) == 1, (name, p, kind)
            picked.append(good[0])
        if kind in ("renewed", "boundary_new"):
            assert first is not good[0], (name, p, "the first row must be the stale one")
        if kind in ("boundary_old", "pending"):
            assert latest is not good[0], (name, p, "the newest row must not be the valid one")
        if kind == "boundary_old":
            assert good[0]["end"] == day, name
        if kind == "boundary_new":
            assert good[0]["start"] == day, name
        wrong = []
        for c in covering:
            if good and c is good[0]:
                continue
            why = "已过期" if c["end"] < day else "还没生效"
            wrong.append(f"{c['number']}（{c['start']} 至 {c['end']}，发布日{why}）")
        per_project.append({
            "项目": p,
            "该用": f"{good[0]['number']}（{good[0]['start']} 至 {good[0]['end']}）" if good else "无：发布日没有有效证明",
            "同一项目不能用的编号": wrong or "无",
        })
    assert len({c["number"] for c in picked}) == len(picked), name
    if not r["drop"]:
        assert not dropped, name
    cert_ref = {"逐个项目": per_project, "最后一行该写": cert_line(rule, picked),
                "说明": "编号先后不限" if len(picked) > 1 else "只有一个编号"}

    listing = [f"{c}（第 {4 if p in dropped else 1} 条）" for p, c in built["claims"]]
    listing += [f"{line[1]}（第 2 条）" for line in built["doctors"]]
    listing += [f"{built['price']}（第 5 条）"]
    listing += [f"{f}（第 3 条，不用）" for f, _ in bad]
    listing += ["加上的审查编号行（第 4 条）" if r["cert_item"] == "编号" else "加上的审查证明行（第 4 条）"]
    if r["listing"] == "table":
        listing_format = "表格，表头三列：原文 | 改成 | 依据第几条；不用的图一行：文件名 | 不用 | 第 3 条"
    else:
        listing_format = "编号列表，每条写成“原文 → 改成（第 X 条）”；不用的图写成“文件名 → 不用（第 3 条）”"
    reference = {
        "规则集": f"{rule}（{r['brand']}）",
        "发布日期": day_text,
        "推广项目": list(projects),
        "第 1 条的词（全表）": r["banned"],
        "原推文里出现的第 1 条词语": found,
        "疗效保证词": "推文段里第 1 条的词一个都不能出现，改写时也不能新加",
        "医生": doctor_refs,
        "配图": image_ref,
        "审查编号": cert_ref,
    }
    if r["drop"]:
        reference["删掉的项目"] = (f"{'、'.join(dropped)}：发布日没有有效证明，写这个项目的话（介绍、价格）都删掉，推文段里不能再出现"
                               f"“{'”“'.join(dropped)}”" if dropped else "无：推广项目在发布日都有有效证明，本题不用删项目")
        reference["## 审查结论该写"] = "删掉的项目：" + ("、".join(dropped) if dropped else "无")
    else:
        reference["删掉的项目"] = "不适用：这套规则没有删项目的口径"
    reference["价格句"] = {
        "该写（逐字）": r["price"],
        "原文要删的": built["offers"] + [built["urgency"]],
        "第 5 条不许出现的词（全表）": words5,
        "金额": "推文段里不能出现“X 元”",
    }
    reference["交付格式"] = {
        "段落（按顺序）": [f"## {s}" for s in r["sections"]],
        "段外": "只交这几段，第一段前、最后一段后不能有别的文字",
        "推文段": "正文，然后单独一行“配图：…”，最后一行是第 4 条的" + ("审查编号" if r["cert_item"] == "编号" else "审查证明"),
        "改动清单格式": listing_format,
        "改动清单至少要覆盖（可以按句列，也可以拆细）": listing,
        "不用列": "“配图：”这一行本身和没改的话",
    }
    return reference


def image_table(images) -> str:
    lines = ["# 配图清单", "", "| 文件名 | 标签 |", "|---|---|"]
    lines += [f"| {f} | {label} |" for f, label in images]
    return "\n".join(lines) + "\n"


def roster_table(rule, rows) -> str:
    head = ["姓名", "科室", "职称"] + (["美容主诊医师"] if RULES[rule]["qualify"] else [])
    lines = ["# 医生名册", "", "| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines) + "\n"


def cert_table(certs) -> str:
    lines = ["# 医疗广告审查证明表", "", "| 编号 | 覆盖项目 | 有效期 |", "|---|---|---|"]
    lines += [f"| {c['number']} | {'、'.join(c['projects'])} | {c['start']} 至 {c['end']} |" for c in certs]
    return "\n".join(lines) + "\n"


def question_text(spec, post) -> str:
    return (
        f"{RULES[spec[3]]['brand']}的市场同事发来一篇公众号推文，计划 {spec[4]} 发布：\n\n「{post}」\n\n"
        "推文现在配的图列在配图清单里。这次适用的推文审查工作规则、配图清单、医生名册和医疗广告审查证明表在工作目录："
        "工作规则.md、配图清单.md、医生名册.md、审查证明表.md。请按规则改好推文，并说明改了什么。"
    )


def scenario_package() -> None:
    (SCENARIO / "personas").mkdir(parents=True, exist_ok=True)
    (SCENARIO / "profile.md").write_text(TASK + "\n")
    (SCENARIO / "onboarding.md").write_text(ONBOARDING + "\n")
    (SCENARIO / "personas" / "marketer.md").write_text(
        "市场同事发来准备发布的推文；每道题的推文、发布日期、配图清单、医生名册、审查证明表和规则由脚本给出。\n")
    (SCENARIO / "scenario.json").write_text(json.dumps({
        "initial": [],
        "criteria": [{"id": i, "check": text, "severity": severity} for i, severity, text in CRITERIA],
    }, ensure_ascii=False, indent=1) + "\n")
    visible = ["counterpart", "analyst", "curator"]
    (SCENARIO / "contract.json").write_text(json.dumps(
        {"checks": {i: {"visibility": visible} for i, _, _ in CRITERIA}}, ensure_ascii=False, indent=1) + "\n")


def main() -> None:
    names = [spec[0] for spec in SPECS]
    assert len(names) == len(set(names)) == 40
    (HERE / "rules").mkdir(exist_ok=True)
    for rule in RULES:
        (HERE / "rules" / f"{rule}.md").write_text(rules_text(rule))
    bank, scripts = [], []
    for spec in SPECS:
        name, group, segment, rule = spec[:4]
        expected_rule = "R3" if group == "new" else ("R1" if int(name[1:]) % 2 else "R2")
        assert rule == expected_rule, name
        assert segment == ("common" if int(name[1:]) in (range(1, 11) if group == "train" else range(1, 6)) else "edge"), name
        if segment == "common":
            assert len(spec[5]) == 1 and spec[7] == ("plain",) and "u-" not in spec[8] and "env-post" not in spec[8] and not spec[9], name
        else:
            assert "u-post" in spec[8].split() and spec[9] and set(spec[7]) != {"plain"}, name
        for salt in range(20):
            built = build(spec, random.Random(f"{name}:{salt}"))
            try:
                reference = compute(spec, built)
                break
            except AssertionError as exc:
                print("retried:", name, salt, str(exc)[:160])
        else:
            raise RuntimeError(f"{name}: no seed passes the checks")
        files = {"工作规则.md": rules_text(rule), "配图清单.md": image_table(built["images"]),
                 "医生名册.md": roster_table(rule, built["roster"]), "审查证明表.md": cert_table(built["certs"])}
        text = question_text(spec, built["post"])
        bank.append({"name": name, "group": group, "segment": segment, "rules": rule, "text": text, "files": files,
                     "reference": reference})
        label = {"train": "培养", "same": "考试·同规则", "new": "考试·新规则"}[group]
        scripts.append({"name": name, "title": f"{name} · {label} · {RULES[rule]['brand']}", "exam": group != "train",
                        "steps": [{"text": text, "files": files}]})
    (HERE / "questions.json").write_text(json.dumps(bank, ensure_ascii=False, indent=1) + "\n")
    (HERE / "scripts.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=1) + "\n")
    scenario_package()
    two = sum(len(q["reference"]["推广项目"]) == 2 for q in bank)
    dropped = sum(q["reference"].get("## 审查结论该写", "：无").split("：")[1] != "无" for q in bank)
    removed = sum(any(d["该写"] == "（整句删掉）" for d in q["reference"]["医生"]) for q in bank)
    print(f"{len(bank)} questions: two projects {two}, project dropped {dropped}, doctor removed {removed}, "
          f"scenario at {SCENARIO.name}")


if __name__ == "__main__":
    main()
