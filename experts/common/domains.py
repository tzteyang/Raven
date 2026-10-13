"""The experts by domain, in the order the pipeline launches them and the summary lists them.

A new case joins one domain here (and gets a free Studio port in pipeline.PORTS) before `pipeline.py --all` runs it.
"""

DOMAINS = [
    ("客服与投诉", [("refund-desk", "网课退款客服"), ("complaint-desk", "电商售后投诉处理")]),
    ("营销文案合规", [("poster-review", "营销海报审查"), ("dental-post", "医疗推文合规审查")]),
    ("数据问答", [("store-ticket", "门店客单价分析"), ("saas-metric", "SaaS 指标取数")]),
    ("办公汇报", [("meeting-actions", "会议待办整理"), ("weekly-report", "运营周报")]),
    ("品牌内容", [("cafe-copy", "咖啡新品文案"), ("xhs-note", "小红书种草笔记")]),
    ("电商文案", [("taobao-title", "电商标题和卖点"), ("amazon-listing", "亚马逊 Listing")]),
    ("招聘求职", [("resume-screen", "简历初筛"), ("resume-rewrite", "简历优化")]),
    ("合同审阅", [("contract-review", "合同留痕审稿"), ("contract-sheet", "采购合同风险清单")]),
    ("网页与小工具", [("landing-page", "品牌落地页"), ("booking-page", "预约交互页面")]),
    ("销售话术", [("call-debrief", "销售通话复盘"), ("discovery-coach", "需求追问清单")]),
    ("产品市场", [("compete-table", "竞品对比表"), ("review-digest", "评价周报")]),
]
