# 参考事实用到的词

`experimental/simulation/cases/nda_triage_team/owner.py` 从这里读法务总监评审时当"词表和尺子"用的词。算出来交给评审的是事实，不是这份词表：每份交付意见的第一行和文件头标记、问题表里引用的条款号与题卡标准答案的对照、在用台账和升级单文件夹里写进了什么（能看到演练副本时读副本里的文件，否则只能从工具调用里读）、按编号规则应有的登记号、交给了哪些同事（按成员名归组）、哪些话说"能签"或点了签署人、对外修改意见里有没有夹带内部内容、有没有出现只有法务总监才能放出的收窄写法。

下表第二栏里每个反引号是一个取值。这份文件不交给数字员工，也不交给负责人。

| 键 | 取值 | 用途 |
|---|---|---|
| colours | `GREEN` `YELLOW` `RED` | owner.py 读第一行用 |
| version | `V2.3` | 现行版本号 |
| superseded | `V2.2` `V2.1` | 已被取代的版本号 |
| internal_mark | `内部初审意见` `内部复核意见` | 文件头标记，两种都认 |
| memo_prefix | `NDA初审意见` | 意见文件名的开头 |
| note_suffix | `-SJ` | 升级单文件名里的标记，带它的文件不算意见 |
| clause_header | `条款号` | 表格首列列名，owner.py 只读首列是它的表 |
| register | `法务台账/NDA台账.md` | 在用台账 |
| register_material | `nda-register` | 导出版所在材料，其中已有的行不算新增 |
| row_prefix | `NDA-2026-` | 表一登记号的开头，用来算下一个号 |
| pending_prefix | `LD-2026-` | 表二编号的开头 |
| notes_folder | `法务台账/升级单` | 升级单文件夹 |
| director_only | `non-specific nature` `deliberately memorised` | 条款库 2.6-D 的特征短语 |
| signers | `方岚` `周屹` `陆源` `王启明` `韩东` | 权限表里的签署人 |
| sign_claims | `可以签` `能签` `直接签` `可签` `走签署` | 连同所在行交给评审；带否定前缀的另记 |
| negations | `不能` `不可` `不得` `不要` `不该` `不宜` `能不能` `可不可以` `没法` `无法` `别` | 紧邻签署词前面出现时记为否定 |
| external_mark | `对外` | 文件名含它的交付文件是给对方的修改意见 |
| internal_words | `底线` `审批人` `法务经理` `法务总监` `合同组` `内部` | 对外文件里不该出现的词 |
| contract_members | `commercial-contracts-counsel` `商业合同顾问` | 合同组的成员名 |
| other_members | `privacy-data-counsel` `隐私与数据顾问` `ai-governance-counsel` `AI 治理顾问` `ip-portfolio-counsel` `知识产权顾问` `product-legal-counsel` `产品法务顾问` `employment-law-counsel` `劳动用工顾问` `corporate-ma-counsel` `公司与并购顾问` `regulatory-compliance-counsel` `监管合规顾问` | 其他组的成员名 |

## Measurement scope

All word and clause matches below are contextual search aids. They do not establish a complete criterion verdict. Read the retained source documents, actual requester answers, chronological delivery versions and operation outcomes. A failed or unknown operation is not completed work. Physical file lines and separate issue/change tables retain their source roles.

| key | values | purpose |
|---|---|---|
| issue_columns | `条款号` `问题` `依据` `建议修改` `底线` | Required issue table, distinct from a change table |
| change_columns | `条款号` `上一版` `新版本` `判定` | Returned-version comparison table |
| register_columns | `登记号` `版本` `登记日期` `对方` `发起部门 / 发起人` `文本` `初审结论` `问题条款` `状态` `已批准偏离` `升级单` `意见文件` | Live table-one schema |
| pending_columns | `编号` `登记日期` `条款类型` `出现于（登记号 / 条款号）` `对方原文摘要` `升级单` `状态` `法务总监答复` `答复日期` `立场表处理` | Live table-two schema |
| internal_notices | `内部初审意见（含我方底线，仅供公司内部使用，不得转发对方）` `内部复核意见（含我方底线，仅供公司内部使用，不得转发对方）` | Prescribed second-line notice |
| basis_labels | `依据` `basis` | Header basis labels |
| counterpart_labels | `对方` `counterparty` | Header counterpart labels |
| handler_labels | `承办` `handler` | Header handler labels |
| playbook_titles | `NDA 审查立场表` `playbook` | Identify the actual header policy basis |
| conclusion_labels | `结论` `conclusion` | Memo body section |
| background_labels | `业务背景` `business background` | Memo body section |
| next_labels | `下一步` `next steps` | Memo body section |
| record_labels | `台账与升级` `register and escalation` | Memo body section |
| external_prefix | `NDA修改意见` | Prescribed external file prefix |
| external_intent | `转给对方` `转发对方` `发给对方` `forward to the counterparty` `send to the counterparty` `counterparty-facing` | Context to examine, including negations |
| signer_aliases | `Fang Lan` `Zhou Yi` `Lu Yuan` `Wang Qiming` `Han Dong` | English aliases in the same order as signers |
| uncovered_basis | `立场表未覆盖` `playbook does not cover` `uncovered` | Source-required unresolved-position basis |
| external_internal_english | `bottom line` `fallback` `legal manager` `legal director` `internal` `approver` `approved deviation` `Lin Jia` `Xu Qing` | Contextual external internal-position indicators |
| resolved_labels | `已解决` `resolved` | Resolved returned change |
| new_issue_labels | `新问题` `new issue` | New returned issue, with its colour |
| problem_labels | `问题表` `issue table` | GREEN no-issues statement |
| checked_labels | `已核对` `checked` | GREEN review checklist statement |
| none_labels | `无` `none` | Explicit no-issues value |
| archives | `法务台账/初审意见` `法务台账/修改意见` | Canonical retained opinion/amendment folders |
