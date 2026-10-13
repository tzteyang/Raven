# 22 个专家：v0 与训练后策略产物对照

核对时间：2026-10-11 21:32 UTC。本文只读比较两个 Raven 宿主目录中的 `harness.json → artifact.files / artifact.values`，依据文件正文及代码差异描述变化；没有运行这些策略、重判答卷或调用模型 API。验收仍在产生新记录，文末效果旁证只是注明时点的快照。

22 个最终产物的文件正文均较 v0 有变化：共改写 24 个已有文件、新增 20 个文件、删除 0 个文件；没有“产物完全未变”的专家。按专家数分，15 个新增了 Skill/方法文件，2 个扩写已有方法文件，5 个仅改原有 capability 指导正文。

22 个 `artifact.values` 均与各自 v0 完全相同，内容仍是指向原模块的 `capability.strategy.factory`。这表示入口配置未换，不能据此说策略正文没变。共同的变化载体是工作指引和 Skill 方法供给；本文没有权重参数训练或泛化能力已经学会的证据。

下文“v0已有”指当时产物已写入的指导，不代表已经通过性能验证。“训练变化”指两份保存产物之间可直接观察的文本/供给变化，不把原有通用指导全部算作训练新学到的能力。

<a id="refund-desk"></a>
## 1.1 网课退款客服（refund-desk）

- v0 已有：已要求读取当次规则、退款政策和订单，按当次日期核算；不沿用其他机构口径，只交一条学员回复。
- 训练后的新增/改写：改写指引，并新增 refund_single_reply.SKILL.md：先把称呼、退法、实际金额、到账及适用工单/分期事项组成最短完整正文；全文禁词覆盖纠错与日期解释；修改后重新核对实际发送文字的长度。方法还区分“已有正文”与误走附件路径，要求回到直接回复。
- 变化类型：新增方法正文；不是原策略原样保留。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-refund-desk/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-refund-desk/harness.json)，最终 revision `098fe127cd2d`。

<a id="complaint-desk"></a>
## 1.2 电商售后投诉处理（complaint-desk）

- v0 已有：已要求结合当次订单、CRM、分类表处理投诉，区分客户陈述与已确认事实，不虚称操作完成。
- 训练后的新增/改写：改写 complaint_capability.py；新增两份方法：补券和独立索赔分开，以总额度−历史补偿−本次计入券额判断权限；同款范围、空分类、按订单去重、跨月排除及本次是否已计入使用同一计数。指引另明确客户回复与内部处理复用有证据的办理状态，并从规定标题直接交付。
- 变化类型：新增补偿/计数方法；原有“不虚报完成”被展开为具体状态对照，不能把它全算作新概念。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-complaint-desk/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-complaint-desk/harness.json)，最终 revision `50bd665135f2`。

<a id="poster-review"></a>
## 2.1 营销海报审查（poster-review）

- v0 已有：已要求读取规则、成交记录、赠品价表与极限词表，实际改稿，并让修改清单与正文一致。
- 训练后的新增/改写：只改写 poster_capability.py 的指导：保留活动售价，参考价均值由同一组逐笔值计算；多笔同价不去重，按当次口径使用 ROUND_HALF_UP；赠品分项与总额共用一组结果；完整保留截止句式和规定清单字段，新增/删除也给对应原文及依据；两段交付不加核算前言。
- 变化类型：同一供给机制内有实质内容改写；没有新建 Skill 文件，不能因此说没有变化。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-poster-review/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-poster-review/harness.json)，最终 revision `8ab6e08e3fe1`。

<a id="dental-post"></a>
## 2.2 医疗推文合规审查（dental-post）

- v0 已有：已指导按当篇规则核对推文、配图、医生名册、证明与发布日期，交付完整改稿和修改说明，保留合规内容。
- 训练后的新增/改写：改写 review_capability.py，新增 post-review-delivery 方法：姓名＋原科室匹配完整职称，以允许字段重组整个医生介绍，避免留下禁用科室前缀；修改说明从最终正文取文，原句组合并后应记真实改写，不能都记删除；新增连接语、证明与每张弃图均对应当次格式；规定结构前后不另加解释。
- 变化类型：新增交付方法，细化医生字段和改动记录；不是只把原文件改名。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-dental-post/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-dental-post/harness.json)，最终 revision `f220b0b0f4f5`。

<a id="store-ticket"></a>
## 3.1 门店客单价分析（store-ticket）

- v0 已有：已指导从当次规则和CSV确定字段、范围与公式，实际核算数字，区分事实与推断。
- 训练后的新增/改写：改写 store_capability.py，新增 store-result-handoff 方法：目标年月按记录日期筛选，不能把整份文件当一期；排名、原因及辅助值共用两份限定数据；转述数字保留渠道/年月/单位；分组客单仅在可加总时做订单权重核对；缺少分组金额的机制解释带条件、缺口和当次标记；首句直接交完整结果。
- 变化类型：新增分析到交付的具体案例；不代表最终轮或所有新规则成绩一定优于前版。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-store-ticket/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-store-ticket/harness.json)，最终 revision `a3a9e4ad8ac5`。

<a id="saas-metric"></a>
## 3.2 SaaS 指标取数（saas-metric）

- v0 已有：已指导读取当次口径、DDL和数据说明，将时间、粒度、关联与过滤落实到SQL，实际执行并交付查询和结果。
- 训练后的新增/改写：改写 capability_impl.py，新增时间、企业粒度、最终交付三份方法：北京时间与UTC分支分别处理，登录侧显式限定月份；按归并后的合格企业集合计数，防多条订阅放大连接行；按条数判活跃时不错误预去重；最终回复本身包含执行过的完整SQL、唯一结果和规定说明，过程中的SQL不能替代。
- 变化类型：新增三份方法；改进意图具体，但SQL方法被写入不等于每次执行均正确。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-saas-metric/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-saas-metric/harness.json)，最终 revision `1aa568cda685`。

<a id="meeting-actions"></a>
## 4.1 会议待办整理（meeting-actions）

- v0 已有：已要求依据当场规则、转写、名单和日历整理事项、负责人、截止日期和需确认内容。
- 训练后的新增/改写：改写 meeting_capability.py，新增 meeting-workday-counting：先确定当天/次日起算，再按当次规则允许的日历类型逐日编号；调休上班是否计入不能凭名称判断；同时核对日期资格与第N个序号，不仅检查截止日是工作日。方法含只允许工作日、允许调休、起算日不同三组对照。
- 变化类型：新增日期计数方法；原有会议提取与身份核对指导继续保留。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-meeting-actions/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-meeting-actions/harness.json)，最终 revision `51921603a07c`。

<a id="weekly-report"></a>
## 4.2 运营周报（weekly-report）

- v0 已有：已指导用本周记录、上周周报和口径表写当次周报，区分本周事实与上周参照，只交周报本身。
- 训练后的新增/改写：改写 weekly_capability.py，新增指标表达与收尾两份方法：先形成标准名、展示数值、数量级、标准单位和变化的明细，再供首句及全文复用；“万”不替代人/元，变化按原始值算；全文含首行和标题实计字符，修稿后重计；核验报告不能替代或包裹已核对正文。
- 变化类型：新增方法正文，细化指标命名、单位和最终交付；并非新加了原先不存在的“读取材料”能力。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-weekly-report/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-weekly-report/harness.json)，最终 revision `899b5d2ca313`。

<a id="cafe-copy"></a>
## 5.1 咖啡新品文案（cafe-copy）

- v0 已有：已区分杯测事实与风味词总表，要求只写当批有据内容，交一份介绍；真实发布与正文生成分开。
- 训练后的新增/改写：改写 coffee_copy_capability.py，新增 coffee-copy-delivery：同一份含实际换行和完整冲煮结尾的正文用于核算与发送；按当次字数/逐段句数比较，合格分支只返回原样正文，失败诊断用于修稿；修改后重计，固定末句/末行是否保留前缀由当次模板决定。
- 变化类型：新增文案核算与交付方法；其中机械计数明确不替代风味和事实判断。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-cafe-copy/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-cafe-copy/harness.json)，最终 revision `64aecc43de91`。

<a id="xhs-note"></a>
## 5.2 小红书种草笔记（xhs-note）

- v0 已有：已要求按产品线取话题，按当次参数与规则写标题、正文和合作标注，不把参数扩写成无依据功效或亲测经历。
- 训练后的新增/改写：改写 note_capability.py，新增 note-finalization：逐处检查已有标题和正文的效果断言，真实容量/自重不替相邻体验承诺背书；不足依据时写读者需要核对的条件；完整正文单独实计，改文后全量重计，emoji按实际完整序列处理；纠正核对错误后只交规定各段。
- 变化类型：新增事实边界与定稿案例；不是从v0完全没有“事实核对”开始。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-xhs-note/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-xhs-note/harness.json)，最终 revision `f2d14854e9a6`。

<a id="taobao-title"></a>
## 6.1 电商标题和卖点（taobao-title）

- v0 已有：已指导按当次规则解释必含词、禁词、品牌名单和长度，所有规格/功效需参数依据，名单不默认白/黑名单。
- 训练后的新增/改写：只改写 listing_capability.py：禁词检查扩展到整条最终文字，包括【参数名】；名称必须原样但含禁词时换用其他合规参数；每条卖点对应不同参数，避免混入其他值；最终整行重新分段逐字符计数，不沿用旧稿累计，并区分不同半角/汉字口径和必含词嵌套重复。
- 变化类型：供给机制未改，指导内容已改写；没有新增方法文件。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-taobao-title/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-taobao-title/harness.json)，最终 revision `42a572b356cd`。

<a id="amazon-listing"></a>
## 6.2 亚马逊英文 Listing（amazon-listing）

- v0 已有：已要求从SKU、认证、拼写与换算表取得依据，草稿不能证明事实；最终检查长度、拼写、单位、精度和认证适用范围。
- 训练后的新增/改写：改写 listing_capability.py，新增 listing-final-copy：参数上限限定随标题及每处提及保留；要点主题短语使用当次词数的纯大写英文单词，数值与范围放正文；容量先统一单位，再用当次换算关系和Decimal舍入，将实际结果直接入稿；最终沿用同一候选，不另加核对报告。
- 变化类型：新增成稿方法；目前文件内容只能证明这些约束被写入。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-amazon-listing/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-amazon-listing/harness.json)，最终 revision `a6acd033c4b6`。

<a id="resume-screen"></a>
## 7.1 简历初筛（resume-screen）

- v0 已有：已要求逐条将岗位硬条件与简历依据对应，按当次缺失规则和格式下结论，不加历史门槛或额外建议。
- 训练后的新增/改写：改写 recruitment_capability.py，新增 screening_followups.md：用月份集合核实经历，重叠全职/兼职按当次口径合并、折算，保留来源与字段标签，比较使用未舍入值；追问只指具体未知项，不从“助理”推成协助、不重问已写系统、不把相邻月份当空档；完成三段后独立计全文字符，超限必须压缩再计。
- 变化类型：新增追问方法及更具体的计算步骤；示意集合算法以当次规则分支为条件，不是固定招聘标准。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-resume-screen/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-resume-screen/harness.json)，最终 revision `44acc1a36688`。

<a id="resume-rewrite"></a>
## 7.2 简历优化（resume-rewrite）

- v0 已有：已要求改前忠于原简历，改后依据事实表，保留参与程度和团队边界；JD只用于选有据表达，不能补经历。
- 训练后的新增/改写：只改写 resume_capability.py：精确值、概数、区间和未核实状态随指标一起保留，不能凭润色加“约”或删限定；岗位关键词逐个与本人实际动作配对，有据原词只在改写列计覆盖，固定职责说法不能替代关键词；保留全部可用结果和规定出处，只交标题与表格。
- 变化类型：同一机制中的内容改写，无新增Skill；事实来源边界本来已在v0。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-resume-rewrite/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-resume-rewrite/harness.json)，最终 revision `0b2cb375ce04`。

<a id="contract-review"></a>
## 8.1 合同留痕审稿（contract-review）

- v0 已有：v0已含 contract-review-current-rules 方法：在原包副本就地做真实Word修订批注，保留结构和既有记录，维护OOXML关系，重开核验后真实交付。
- 训练后的新增/改写：改写原有 capability 和 contract_review_method.md：直接核实指定原包的合同身份、页眉和旧记录；使用独占临时目录与不编辑基线，摘要不能替代身份；查清全部批注归属，区分真旧记录与工作残留；比较未改部件和编辑区域的格式/内容，读取中断不算通过；从最终实际变化算本次修订/新增批注数量，只给当次要求的一句收尾。
- 变化类型：扩写已有方法文件，没有新增文件；核心留痕方法早在v0，本轮差异主要是来源隔离、保真证据和准确报数。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-contract-review/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-contract-review/harness.json)，最终 revision `cd2deb00398e`。

<a id="contract-sheet"></a>
## 8.2 采购合同风险清单（contract-sheet）

- v0 已有：已要求按当次规则逐项审合同，两份成果共用结论，生成真正xlsx风险表和docx批注副本，批注锚定原文并重开核验交付。
- 训练后的新增/改写：只改写 procurement_capability.py：风险等级按当次编号指定值取，不因缺失自行升高；批注必须覆盖条款非空原文，缺失项按规则锚定标题；保存后逐ID读取真实起止范围内的w:t，空范围不能用段落或目标文字填补；最终回读Excel核等级，从真实风险行重新数总数和高风险数，回复不沿用早期摘要。
- 变化类型：供给机制未变，批注范围和风险数量的核验步骤有实质改写；无新增Skill。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-contract-sheet/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-contract-sheet/harness.json)，最终 revision `0f2eaf8f25a4`。

<a id="landing-page"></a>
## 9.1 品牌落地页（landing-page）

- v0 已有：v0已含 brand-booking-page：读取当前品牌/旧稿，制作自包含单HTML，手机/桌面实际浏览并看截图，检查离线资源和首屏，真实交付。
- 训练后的新增/改写：改写原有 capability 与同一Skill：按实际h1–h6/其他文字类别设置font-family首项，醒目店名或产品名不自动变标题；检查局部覆盖、继承和媒体查询，将getComputedStyle核对并入双端检查；不下载字体或改标签规避。收尾改为只在当次格式允许时说明未验证项，不额外交检查报告或写进顾客页面。
- 变化类型：已有网页制作/双端检查框架上的定向改写，未新增Skill文件；字体取样证据本身也不保证页面全项通过。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-landing-page/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-landing-page/harness.json)，最终 revision `d1d627d32b26`。

<a id="booking-page"></a>
## 9.2 预约交互页面（booking-page）

- v0 已有：已要求离线自包含页面，依据当期课表实现筛选、名额、冲突、持久化、键盘操作并核验正常/拒绝/边界情形。
- 训练后的新增/改写：改写 capability_impl.py 的收尾指引，新增 booking-delivery-contract：文件交付和最终回复分开；成功交付后只用当期允许的文件名/空回复/真实链接；不能交文件且允许兜底时才只给一个完整html代码块，两分支互斥；不附实现介绍、自测报告或内部脚本。
- 变化类型：训练差异主要在交付形式；文件中未新增一套预约冲突或存储算法，不能据此声称那些逻辑被专门增强。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-booking-page/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-booking-page/harness.json)，最终 revision `8f4bd586e294`。

<a id="call-debrief"></a>
## 10.1 销售通话复盘（call-debrief）

- v0 已有：已要求按通话、日期、价表和竞品名单写主管复盘与客户邮件，保留事实主体、条件、不确定性，最终不附过程报告。
- 训练后的新增/改写：只改写 call_debrief_capability.py：先把必需动作分配到当次句数上限内，再组织完整话术，改动后按整段标点重核，不能删动作或机械改标点凑数；补充报价主体、客户请求、销售承诺、已完成事项的对照，防把我方价当对方报价、把请求看方案写成方案已完成。
- 变化类型：没有新增Skill或新工具，只改指导正文；验收中仍存在训练阶段新规则回退，见下方旁证。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-call-debrief/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-call-debrief/harness.json)，最终 revision `483e4e1633b1`。

<a id="discovery-coach"></a>
## 10.2 需求追问清单（discovery-coach）

- v0 已有：已指导按当次工作规则与客户线索产出追问清单，数量、分类、问法与格式不套通用销售模板。
- 训练后的新增/改写：改写 capability_impl.py，新增分类与开放追问两份方法：按实际索取的未知信息分类，区分流程、办法不足、额外损失；允许的相关合问不一律拆开；开放主问不能抵消后半句封闭问法，逐个追问改成具体信息请求；修问法后重新核类别数量、必问和总题数。
- 变化类型：新增问句判断方法；问数与分类定义仍取当次材料，不能把例子当固定话术。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-discovery-coach/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-discovery-coach/harness.json)，最终 revision `3c458a40c006`。

<a id="compete-table"></a>
## 11.1 竞品对比表（compete-table）

- v0 已有：已要求按当次规则确定对象、结构、单位、汇率与定位，事实不补造，只交表格和一句定位。
- 训练后的新增/改写：改写 capability_impl.py，新增 comparison-state-fidelity：按产品名×功能名保留对应状态，转置重排不凭旧列号；只做规则允许的状态映射；逐家按当次允许集合判断定位资格，部分支持不自动等于无，未知不擅改无；表格与定位沿用同一组核实状态。
- 变化类型：新增状态保真方法；同规则训练后成绩仍低于v0，策略新增不等于单调提升。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-compete-table/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-compete-table/harness.json)，最终 revision `0150fa86cde9`。

<a id="review-digest"></a>
## 11.2 评价周报（review-digest）

- v0 已有：已指导按当次规则、原评和分类表形成周报，分类和统计有材料依据，只交周报、不臆造发送成功。
- 训练后的新增/改写：改写 weekly_review_capability.py，新增 weekly-review-evidence：先按原编号读完整评价，绑定用户/原星级及各类依据；合并表保留所有原编号与纯好评行，按列直接计成员、低星和当次分母；覆盖核对不能用命中总数替代；按全部并列规则先截取规定类别，再选合格完整原话和团队，只交这些入选行。
- 变化类型：新增归属、合并统计及交付方法；其效果需要完整三版本复测另证。 本专家的 `artifact.values` 完全不变。
- 原文证据：[v0 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host-v0/agents/expert-review-digest/harness.json)；[最终 harness](/Evermind/sh_evermind/share/huchuanrui/gxz_workspace/Project/gtm_rsi/runs/experts/host/agents/expert-review-digest/harness.json)，最终 revision `a7c5b576db31`。

## 策略变化与验收效果分开看

策略正文变化可以逐字核对；效果必须看相同任务、相同规则和评审口径下的 plain / v0 / trained 对照。每次验收仍是同一套 x/y 各10题，重复3次的30份答卷不是30道独立新题；也不能把 trained−plain 的全流程差异都归于 v0 之后的训练。

| 已有完整对照的旁证 | v0 → trained 整题全对数（同规则 x；新规则 y） | 能支持的结论 |
|---|---|---|
| 退款客服，三版本各3次 | 15/30 → 30/30；18/30 → 27/30 | 已保存样本中两组均增加，与策略修改方向相容，但不能逐项归因到某个Skill。 |
| 竞品对比表，三版本各3次 | 28/30 → 25/30；16/30 → 21/30 | 同规则下降、新规则增加，不能说新增方法使两组都提升。 |
| 投诉处理，三版本各3次 | 9/30 → 27/30；18/30 → 22/30 | 相对v0增加，但新规则plain本来也是22/30，不能声称相对原版有净提升。 |
| 销售通话复盘，三版本各3次 | 17/30 → 20/30；20/30 → 17/30 | 指导正文有针对性变化，新规则验收仍下降。 |

前三项的逐次结果和完整原文件索引见 [成绩口径审查](./scorecard-audit-20261011.md) 与 [旧专家成绩快照](./status-20261011-184453.md)。销售通话复盘的三次 v0 与三次 trained 原文件列在下方，数值是对保存的逐项模型判定求和，不重新判断正文。

- 通话复盘 plain：[第1次](../cases/call-debrief/accept-plain-1011-200027-f8f329e07a.json)、[第2次](../cases/call-debrief/accept-plain-1011-201304-dca256619d.json)、[第3次](../cases/call-debrief/accept-plain-1011-202508-f6875bff2f.json)。
- 通话复盘 v0：[第1次](../cases/call-debrief/accept-v0-1011-204026-ea213aec97.json)、[第2次](../cases/call-debrief/accept-v0-1011-205156-7602e6ce8b.json)、[第3次](../cases/call-debrief/accept-v0-1011-210144-a7938bb60e.json)。
- 通话复盘 trained：[第1次](../cases/call-debrief/accept-483e4e1633b1-1011-193059-ce20ddb647.json)、[第2次](../cases/call-debrief/accept-483e4e1633b1-1011-194011-1a9190f826.json)、[第3次](../cases/call-debrief/accept-483e4e1633b1-1011-195155-72e6b263f0.json)。

截至上述快照，亚马逊 Listing 和预约页面尚无完整宿主验收报告；落地页只有 trained 首份；咖啡文案、简历优化、简历初筛、小红书尚未凑齐三版本；若干其余专家的基线重复次数仍少于 trained。本文不据这些未齐记录断言效果提升。后续成绩单以完整且无错误的三版本记录为准，不能因这里有22条产物说明就计成22个完整验收。

## 产物身份快照

下列 SHA-256 为核对时的整个 harness 文件摘要，便于以后辨别文件是否变化；v0 的短 revision 统一为 `v0`，不能单靠这个字符串辨认各专家初始产物。方法正文的具体内容以上方对应 harness 的 `artifact.files` 为准。

| 专家 | v0 harness SHA-256 | 最终 harness SHA-256 |
|---|---|---|
| refund-desk | `5c812596d611435aa61957b675f52f8a8a23365dd5874baaf34accbed27f8164` | `90e878e654a80951c17e88a28111f540d5d593e25b5b5b8b9c186e735bb8ae63` |
| complaint-desk | `54aee36efa00c5d037944bfc64303ab1f2ec097c81a809c35498235a99979c6c` | `763fd7056e8a8bc135e7c562a9b59392e615a7b75d3993e249206d6711cdd204` |
| poster-review | `cd0b5f6415425152bf6be15caa10f262ade8237c4cfb73baf2ecf722edfd2ec8` | `3b065638bb45aff746edc0a88c96de72a4784f2b1bb206df2acd0ae12b847b40` |
| dental-post | `645f6db5e6fe4908aad3427a1c69bd3e15f66ab0fcd5cd708590e148e8453abe` | `c7241742dca9ee57f10b9fdae1b829c5455a94227119d955a457138d97bd869f` |
| store-ticket | `ae0dd757a7b76783e6ceafacad9468a6905a5013160f606455abe173a5077082` | `b37009aefb8d2cc5f8c36c16611b7ddaadbd6a4f4877f873a2f5e78314fd231e` |
| saas-metric | `39a5c1ed1506916fd24294e0d9d08572527f40b4ca4dd3ed2d2e8383f71b842b` | `59b1145b22c691b87cec0df3ae3007bca770a9636331bc0d867f3506c123a85a` |
| meeting-actions | `4049da85c16fafc715d623c2eab2ee4e6ecb8e1a90eb88afce2c5bd99b8587c8` | `b25910fc04390bbafb9969f749740416f6dd888bd81c69313b6122b36ed8afc4` |
| weekly-report | `a8621b4b198b5d2c3fcff9f375cf2fa49bd17fa3c03569e18124c95e0cdfd059` | `ee3ccf2c4e9a94a81c252025039dfa6413dfad9f16ec4fac650e5a3928246294` |
| cafe-copy | `15745ff8d0ff55959fb58d992aed3026ef757296d358af6267addc078b4da5d2` | `e8b73f5bd6440d2c0df9f14e26a8d068235bbcee0108872df1467cf41a86c3ba` |
| xhs-note | `f4bf995b8beed99c40f00bdac34b11419550afb9a9c3eb6c57830513494b2376` | `07368cf7c856818a7e7c1c24d6886fb41fb92c728b8f2d05a5e9dbf21604a835` |
| taobao-title | `b107113d3fa846f5d4161268c7a39914897cd70a260a88444cb8685d09c80ddf` | `698fe0fde1431b7f73f2b84af735d9d78077b86584d95a943930d85433d5a77c` |
| amazon-listing | `8022dd7ca5ea6ad68634ac69feb67000e5153f5d25fac3473857125d87ef9a4c` | `cca6cc0778f26bb8fad70fd4afc515dc09908533ddbeeca34bbf618e277dff80` |
| resume-screen | `93b6c3c61613951d53bbfe37f7a7f65c704c7afc3da39228c119122be1e63505` | `60202cd0b3d8af367368ee4cf3c0f241d8e3083ea4c93efe61962a60eb6ccfe5` |
| resume-rewrite | `543581553b6b0a94ede3ed81dc189b43a9912d050747a99aee6a017e36f66c2b` | `d521c24c024a6f79675580f1fc27bc288b5b26b1906cb80ba91dfbafc07ac86a` |
| contract-review | `0be288830901616ee2748ee5493fdb2e17cd2777b162b1f55e090ff4c56ebfd5` | `e43dd3feb1474116bbedc488569326427bdd4ce7b2a15d1976b97d6149ebd570` |
| contract-sheet | `9bcdc16de8811d23848bd53099e0f678722135b4d19f76e490a1943baa8b500b` | `aa89cc9d3bb03f9eec62c3c2a6d6a27936f0e257b9d21f050ff8e4219dc90caa` |
| landing-page | `31ce06f1889f06dd89a4ff23889ac06998a3d08bde9e3d77d268d9a78b73ff42` | `dd355ecf38f29973b2336d11e3de444a39b5152d90da381212a13578be4e0591` |
| booking-page | `851a152bc58c456bb801ed6a6dedb6b71b49f2dcac23a284cff54a446dd1767c` | `93623f3768b8d29e97fbff3b31ddd4ee2ad5818d68df8b5a767b6ce5a3a8f249` |
| call-debrief | `72d4c756e6a83e5e1348ca638928f51b518d50f99d273862166e5beb53fe39c5` | `c7ae4d108dfe3c31157f72aa775ef11609e8b4d1ce02108666254b32bbe71834` |
| discovery-coach | `4be352427a79542de5a418f33542dd6c0ce213ee885effe9eadf942c39d65992` | `586b9df641987842c28e544c6a58cd3b4d5275418a80617019690fb1ebd79b9b` |
| compete-table | `37625d6759a57612e5327012b9894ab7636a14b695926bd152ac879b0cf41e33` | `c26bb22c3a0e4e4b2ce0517340fe91927816ad15563aa4fc24b0a2c362e68030` |
| review-digest | `683df188e174d0704907ae7c0bb5c64ff9f15fb58d501645a96c3a154d81e967` | `fb4be8d3ca7a8af96631f07859b3986ff1e4a25870a7656ef3eb2719f2c0e4fc` |
