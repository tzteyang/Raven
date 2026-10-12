---
name: retired-page
description: 信息化组与财务部《外包报价页停用说明及源码存档》：7 月底起试用、8 月停用的外包报价页 v0.9 的八处问题（税率、拆旧、门槛、逐项取整、外链白屏、源码带成本、输入框、缺编号和有效期）、对应的现行规定、影响处理，以及存档源码（仅供对照，不得沿用）。
---

# 外包报价页停用说明及源码存档

| 项目 | 内容 |
|---|---|
| 文件编号 | AJ-YY-XX-2026-04 |
| 发布部门 | 运营管理部（信息化组）、财务部（成本核算组） |
| 停用日期 | 2026-08-22 |
| 本说明发布日期 | 2026-10-08（随《销售工具开发与变更管理规范》V2.0 一并发布） |
| 涉及版本 | 外包报价页 v0.9（2026-07-20 起在园区星湖店试用） |
| 用途 | 开发和核对报价页时对照，避免同类问题再出现 |

## 1 停用经过

7 月 20 日起，园区星湖店试用外包公司做的"装修报价计算器"（v0.9）。8 月 10 日财务月中抽查发现报价合计普遍偏低，8 月 18 日门店反馈客户家没网时页面打不开，8 月 20 日有顾问把文件转给客户后，客户在源码里看到了成本价。8 月 22 日起停用，门店改回手工报价；财务部随后把计价口径修订为 2026-09 版。

## 2 问题清单

| 序号 | 问题 | 后果 | 现行规定 |
|---|---|---|---|
| 1 | 税金按 6% 计 | 税金少算三个百分点，含税 10 万元左右的单子少约 2,750 元 | 计价口径第 3.6 节：9% |
| 2 | 拆旧费按建筑面积计 | 不足 60㎡ 的拆旧单少算 | 计价口径第 3.3 节：按计价面积 |
| 3 | 活动门槛按税前金额判断 | 税前不到 10 万、含税超过 10 万的单子漏减 | 计价口径第 3.8 节：按含税合计，含正好等于 |
| 4 | 每一分项先四舍五入到元再相加 | 合计和财务核算差几元 | 计价口径第 3.9 节：分项到分，只在最后取整到元 |
| 5 | 引用在线字体和在线脚本库 | 客户家没网时页面白屏、点了没反应 | 页面要求第 3.1、3.2 节：单文件，离线可用 |
| 6 | 源码隐藏字段里带各档成本价，结果里还显示"毛利参考" | 文件转给客户后成本泄露 | 页面要求第 5.1 节；价目表密级说明 |
| 7 | 面积框只能输数字；空白按 0 算出 60㎡ 的报价；1000 以上只弹"面积太大" | "89㎡"、全角数字粘贴不进；空白也出报价 | 计价口径第 4 节 |
| 8 | 没有报价单编号、有效期、"以量房实测面积为准" | 客户拿截图来签约时无法核对是哪一版报价 | 计价口径第 5.1 节 |

此外，价目和活动写死在页面里，没有版本号和发布记录，8 月 1 日活动换版后门店手机上同时存在三个版本。现行做法见《销售工具开发与变更管理规范》。

## 3 影响与处理

1. 试用期间出具的 37 张报价单由财务逐张复核：37 张全部有误，其中 34 张偏低、3 张因门槛按税前判断而漏减。
2. 门店已向相关客户说明，按正确口径重新出单；已签约的 4 单差额由公司承担。
3. 外包合同已终止，后续报价页由信息化组自行开发维护。

## 4 源码存档（v0.9，仅供对照，不得沿用）

存档源码中的单价、活动和成本数字均为 2026 年 7 月至 8 月的数据，已经失效。

```html
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>装修报价计算器</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700&display=swap">
<script src="https://cdn.jsdelivr.net/npm/dayjs@1.11.10/dayjs.min.js"></script>
<style>
  body { font-family: "Noto Sans SC", sans-serif; background: linear-gradient(135deg, #fdf6ec, #f3e7d6); margin: 0; }
  .box { width: 420px; margin: 24px auto; background: #fff; border-radius: 16px; padding: 24px;
         box-shadow: 0 8px 24px rgba(0,0,0,.08); }
  .item { margin: 14px 0; } .item span { display: inline-block; width: 90px; }
  input, select { width: 260px; padding: 8px; font-size: 15px; }
  .btn { width: 100%; padding: 12px; background: #e67e22; color: #fff; border: 0; border-radius: 24px; font-size: 16px; }
  .result { margin-top: 18px; font-size: 15px; line-height: 2; } .big { font-size: 26px; color: #e67e22; font-weight: 700; }
</style>
</head>
<body>
<div class="box">
  <h3>装修报价计算器</h3>
  <div class="item"><span>房屋面积</span><input id="mj" type="number" placeholder="请输入面积"></div>
  <div class="item"><span>装修档次</span>
    <select id="dc"><option value="660">简装</option><option value="950">标准</option><option value="1350">精装</option></select></div>
  <div class="item"><span>是否拆旧</span><select id="cj"><option value="0">否</option><option value="1">是</option></select></div>
  <div class="item"><span>全屋定制</span><select id="dz"><option value="0">否</option><option value="1">是</option></select></div>
  <input type="hidden" id="cb-jz" value="448"><input type="hidden" id="cb-bz" value="641"><input type="hidden" id="cb-jzh" value="892">
  <input type="hidden" id="cb-cj" value="30"><input type="hidden" id="cb-dz" value="18760">
  <button class="btn" onclick="calc()">立即计算</button>
  <div class="result" id="res"></div>
</div>
<script>
  function calc() {
    var mj = Number(document.getElementById('mj').value);
    if (mj > 1000) { alert('面积太大'); return; }
    var jf = Math.max(mj, 60);
    var dj = Number(document.getElementById('dc').value);
    var jc = Math.round(jf * dj);
    var cj = document.getElementById('cj').value === '1' ? Math.round(mj * 45) : 0;
    var dz = document.getElementById('dz').value === '1' ? 26800 : 0;
    var gl = Math.round((jc + cj + dz) * 0.08);
    var sf = Math.round((jc + cj + dz + gl) * 0.06);
    var jm = (jc + cj + dz + gl) >= 100000 ? 2000 : 0;
    var zj = jc + cj + dz + gl + sf - jm;
    document.getElementById('res').innerHTML =
      '基础费用：' + jc + ' 元<br>拆旧：' + cj + ' 元<br>定制：' + dz + ' 元<br>管理费：' + gl + ' 元<br>税费：' + sf +
      ' 元<br>夏日焕新立减：' + jm + ' 元<br>总价：<span class="big">' + zj + '</span> 元<br>' +
      '<small>' + dayjs().format('YYYY-MM-DD') + ' · 毛利参考：' +
      Math.round((dj - Number(document.getElementById(dj === 660 ? 'cb-jz' : dj === 950 ? 'cb-bz' : 'cb-jzh').value)) / dj * 100) +
      '%</small>';
  }
</script>
</body>
</html>
```
