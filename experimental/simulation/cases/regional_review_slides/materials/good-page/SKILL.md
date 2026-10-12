---
name: good-page
description: 华南区《2026 年 9 月经营分析会》一页纸：9 月经营分析会上 CEO 点名表扬、总经办随会议纪要下发的样张，附总经办对它好在哪里的说明和页面源码。
---

# 样张：华南区 2026 年 9 月经营分析会一页纸

| 项目 | 内容 |
|---|---|
| 来源 | 华南区 9 月经营分析会上会页面（文件名"华南区-2026年9月经营分析会.html"） |
| 下发 | 总经理办公室，随《2026 年 9 月经营分析会纪要》QH-ZJB-JY-2026-09 下发，2026 年 10 月 13 日 |
| 用途 | 各区做 10 月经营分析会材料时参照；数据是华南区 9 月的真实数据，引用时换成本区的 |

## 1. 这页好在哪里（总经办整理）

1.1 标题就是结论："完成 106%"加上好在哪里，CEO 不用往下看就知道华南这个季度怎么样。

1.2 后排看得清：投影全屏时标题 48px，要点 32px，数据块的关键数字 40px，数据块和表格里的其他文字 28px；只有右下角来源一行是 18px。

1.3 有缺口的地方写了原因和补回时间：佛山差 20 万，写明排产推迟、预计 10 月补回，补回按总经办要求 3.6 标了"预计"。

1.4 页面上的数全部和财务部第三季度口径表一致，数据块按总经办要求 3.4 放齐了大区的目标、完成、完成率和各城市的目标、完成、完成率：大区合计按亿元两位小数，城市用口径表的万元数，完成率取整。

1.5 只用 VI 颜色：表头启衡蓝，没完成的佛山 99% 用警示红，超额的数字用启衡蓝；没有渐变、阴影和动画，打开就是最终样子。

1.6 在会议室投影 1280×800 下一屏放下，四周留白，表格把城市横着排，省出了高度。

## 2. 页面源码

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>华南区-2026年9月经营分析会</title>
<style>
  html, body { margin: 0; padding: 0; background: #FFFFFF; }
  body { font-family: "Microsoft YaHei", "PingFang SC", sans-serif; color: #0A1F44; }
  .page { position: relative; width: 1280px; height: 800px; box-sizing: border-box; padding: 24px 56px; }
  .logo { display: block; height: 40px; width: auto; }
  h1 { margin: 18px 0 18px; font-size: 48px; line-height: 1.25; font-weight: 700; }
  .kpi { display: flex; gap: 48px; margin: 0 0 18px; padding: 10px 28px; background: #F2F4F8; font-size: 28px; }
  .kpi b { margin-left: 12px; font-size: 40px; }
  .kpi b.up { color: #0B5FFF; }
  ol.points { margin: 0 0 18px; padding-left: 1.6em; font-size: 32px; line-height: 1.5; }
  table { border-collapse: collapse; font-size: 28px; }
  th, td { padding: 6px 22px; text-align: right; border-bottom: 1px solid #D9DEE7; }
  th:first-child, td:first-child { text-align: left; }
  thead th { background: #0B5FFF; color: #FFFFFF; font-weight: 400; }
  td.warn { color: #E5484D; font-weight: 700; }
  .source { position: absolute; right: 56px; bottom: 20px; font-size: 18px; color: #6B7A90; }
</style>
</head>
<body>
<div class="page">
  <svg class="logo" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 168 40" width="168" height="40" role="img" aria-label="启衡工业">
    <rect x="0" y="0" width="40" height="40" rx="6" fill="#0B5FFF"/>
    <path d="M8 25 L20 12 L32 25" fill="none" stroke="#FFFFFF" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>
    <rect x="8" y="28" width="24" height="4" rx="1" fill="#FFFFFF"/>
    <text x="50" y="28" font-size="22" font-weight="700" fill="#0A1F44" font-family="Microsoft YaHei, PingFang SC, sans-serif">启衡工业</text>
  </svg>
  <h1>华南 Q3 完成 106%，深圳、厦门领跑</h1>
  <div class="kpi">
    <div>目标<b>1.60 亿</b></div>
    <div>完成<b>1.69 亿</b></div>
    <div>完成率<b class="up">106%</b></div>
    <div>超额<b class="up">0.09 亿</b></div>
  </div>
  <ol class="points">
    <li>深圳完成 108%，两家新客户放量</li>
    <li>佛山差 20 万：排产推迟，预计 10 月补回</li>
    <li>Q4 目标 1.70 亿，10 月起按周盯单</li>
  </ol>
  <table>
    <thead><tr><th>万元</th><th>广州</th><th>深圳</th><th>佛山</th><th>东莞</th><th>厦门</th></tr></thead>
    <tbody>
      <tr><td>目标</td><td>5,000</td><td>4,800</td><td>2,600</td><td>2,000</td><td>1,600</td></tr>
      <tr><td>完成</td><td>5,320</td><td>5,186</td><td>2,580</td><td>2,104</td><td>1,722</td></tr>
      <tr><td>完成率</td><td>106%</td><td>108%</td><td class="warn">99%</td><td>105%</td><td>108%</td></tr>
    </tbody>
  </table>
  <div class="source">数据来源：财务部经营口径表，截至 2026 年 9 月 30 日</div>
</div>
</body>
</html>
```
