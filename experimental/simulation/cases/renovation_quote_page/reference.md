# 参考事实用到的材料、词和输入

`owner.py` 用这里的取值算运营负责人评审时的"计算器和尺子"：`quote.py` 按财务口径和材料里的价目、活动算出每组输入在某一天应得的报价合计；`page.py` 用无头浏览器像顾问一样打开交付的报价页（手机屏宽、手机日期设为那一天、断网），按下表的输入逐组填进去，读出页面显示的报价合计或提示；再从页面源码和执行记录里读出外链、成本数据、报价单要素、核对记录和发布登记。判定仍由负责人自己做。

下表第二栏里每个反引号是一个取值。这份文件不交给数字员工，也不交给负责人。

## 材料和表格

| 键 | 取值 | 说明 |
|---|---|---|
| price_lists | `price-list-2026q4` `price-list-2027` | 价目表材料，按生效日期取当天有效的一版 |
| promotions | `promo-october` `promo-november` | 活动政策材料，按活动期取当天有效的一期 |
| samples | `sample-quotes` | 财务核对过的历史报价单，从中取报价单编号 |
| code_label | `文件编号` | 文件头表格里的文件编号行 |
| effective_label | `生效日期` | 价目表的生效日期行 |
| period_label | `活动期` | 活动政策的活动期行 |
| item_column | `项目` | 价目明细表的项目列 |
| price_column | `销售单价` | 价目明细表的销售单价列（成本列不用） |
| threshold_column | `含税合计满` | 活动档位表的门槛列 |
| cut_column | `立减` | 活动档位表的立减列 |

## 计价口径的数

| 键 | 取值 | 说明 |
|---|---|---|
| rates | `0.08` `0.09` | 管理费率、税率（计价口径第 3.5、3.6 节） |
| minimum_area | `60` | 最低计价面积（第 3.1 节） |
| area_bounds | `1` `1000` | 面积有效范围（第 4.1 节） |
| validity_days | `7` | 有效期至 = 报价日期后第几天（第 5.1 节） |
| area_units | `平方米` `平米` `平方` `㎡` `m²` `平` | 面积末尾可去掉的单位，长的在前（第 4.2 节） |

## 页面上的字

| 键 | 取值 | 说明 |
|---|---|---|
| tier_names | `简装` `标准` `精装` | 档次 |
| area_label | `面积` | 面积框旁边的字 |
| demolition_label | `拆旧` | 拆旧选项 |
| custom_label | `定制` | 全屋定制选项 |
| negations | `不` `否` `无` `没` | 选项里表示"不要"的字 |
| placeholders | `请选择` | 下拉框的占位选项 |
| compute_buttons | `生成报价` `计算` `生成` `报价` `算` `确定` `确认` `提交` `出单` | 出报价的按钮，按次序找 |
| skip_buttons | `重置` `清空` `清除` `复制` `截图` `保存` `分享` `下载` | 不按的按钮 |
| total_labels | `报价合计` `应付` `实付` `总价` `合计` | 报价单合计行的名称，按次序找；单写"合计"时跳过含税合计那一行 |
| gross_label | `含税合计` | 含税合计行 |
| error_prompt | `请输入 1 到 1000 之间的面积` | 面积无效时的提示（第 4.4 节），比较时不计空格 |
| measure_note | `以量房实测面积为准` | 报价单说明（第 5.1 节） |
| sheet_title | `安居家装 整装报价单` | 报价单抬头（第 5.1 节） |
| sheet_fields | `报价日期` `建筑面积` `计价面积` `档次` `拆旧` `全屋定制` `基础装修费` `拆旧费` `全屋定制费` `管理费` `税金` `含税合计` `活动立减` `报价合计` | 报价单必备项目的常用标签；其他同义标签由负责人读单据确认 |
| validity_note | `本报价自报价日起 7 天内有效` | 报价单有效期说明（第 5.1 节） |
| reproduction_heading | `复现` | 核对记录里旧版页面的复现一节，不拿它和新版页面比较 |
| validity_labels | `有效期至` `有效期` | 有效期那一行 |
| until_word | `至` | 有效期一行里到哪天的字，取它后面的日期 |
| money_marks | `元` `¥` `￥` | 金额旁边的字，金额单独成行时靠它认 |
| phone_words | `手机` `电话` | 文本框旁出现这些字就按手机号填 |
| neutral_text | `顾问` | 页面另有空文本框（如顾问姓名）时填的中性值 |
| neutral_phone | `13900000000` | 页面另有手机号框时填的中性值 |
| version_word | `版本` | 页面上版本号不带 v 时的写法（版本 1.0） |
| record_columns | `面积输入` `页面显示` `报价日期` `档次` `拆旧` `定制` | 核对记录表的列（规范第 5.1 节表头），用来对照页面实测 |
| quote_prefix | `AJ` | 报价单编号开头（第 5.1 节） |
| cost_words | `成本` `毛利` | 源码里不该出现的词（否定句里的不算，由负责人看行内容） |
| cost_figures | `462` `655` `908` `19320` `19,320` `470` `688` `915` `19450` `19,450` `448` `641` `892` `18760` `18,760` `32.1%` `33.2%` `34.2%` `33.3%` `31.0%` `30.9%` `32.5%` `33.7%` `34.0%` `30.5%` | 各版价目表和外包页里的成本参考价和毛利率（拆旧成本太短，不查） |
| check_record | `核对记录` | 核对记录文件路径里的字（规范第 5.1 节） |
| register | `发布登记` | 发布登记文件路径里的字（规范第 5.2 节） |
| page_suffixes | `.html` `.htm` | 报价页文件 |
| page_name | `安居报价` | 报价页文件名开头（规范第 3.5 节：安居报价-v版本号.html） |

## 每组输入

一组输入写成 `编号=面积;档次;拆旧;定制`，Y 是要、N 是不要，面积原样照顾问会输的写法（空白就是什么都不输）。历史单五组和边界七组、无效六组在每张卡的业务日期都跑；切换三组在卡的其余日期再跑；卡上对话和附件里出现的输入另列。

| 键 | 取值 |
|---|---|
| history_cases | `h1=45;简装;N;N` `h2=89;标准;Y;Y` `h3=64;精装;N;N` `h4=52.6;标准;Y;N` `h5=124;简装;N;N` |
| edge_cases | `e1=60;标准;Y;N` `e2=59.9;标准;Y;N` `e3=６０．５;精装;N;Y` `e4=89㎡;标准;Y;Y` `e5=75平米;简装;Y;N` `e6=1000;简装;N;N` `e7=101.45;标准;N;Y` |
| refused_cases | `x1=;标准;N;N` `x2=-50;标准;N;N` `x3=0;简装;N;N` `x4=1000.01;简装;N;N` `x5=89.555;标准;Y;N` `x6=约90;标准;N;N` |
| switch_cases | `s1=89;标准;Y;Y` `s2=101.45;标准;N;Y` `s3=124;简装;N;N` `s4=90;标准;Y;N` |
| sheet_case | `h2` |

## 每张卡的日期和另列输入

日期栏第一个是业务日期（对方开口说的"今天"），其余是要另测的出单日期（切换前后、最后一期活动结束后的第一天）。`reported_*` 是反馈里只有复现才会写出的数：页面显示的错数或报价单编号，比较时折叠全角、去掉千分位。

| 键 | 取值 |
|---|---|
| xinghu | `2026-10-13` |
| baodai | `2026-10-15` |
| chaijiu | `2026-10-20` |
| nuandong | `2026-11-03` `2026-10-31` `2026-11-01` `2026-12-01` |
| kuayue | `2026-10-29` `2026-10-31` `2026-11-01` `2026-12-01` |
| quanjiao | `2026-11-10` `2026-12-01` |
| xiangcheng | `2026-10-12` |
| xiangchengagain | `2026-10-12` |
| kehu | `2026-11-20` `2026-12-01` |
| kaiye | `2026-11-09` `2026-12-01` |
| xinjiamu | `2026-12-28` `2026-12-31` `2027-01-01` |
| weishu | `2026-11-16` `2026-12-01` |
| extra_baodai | `c1=76.35;标准;Y;N` |
| extra_quanjiao | `c1=８５．５;标准;Y;N` `c2=92平米;简装;Y;N` `c3=1200;精装;Y;Y` `c4=130.555;标准;N;N` |
| extra_xiangcheng | `c1=72;精装;Y;N` `c2=130;标准;Y;Y` |
| extra_xiangchengagain | `c1=72;精装;Y;N` `c2=130;标准;Y;Y` |
| extra_kehu | `c1=110;精装;N;Y` |
| extra_kaiye | `c1=95;标准;Y;N` `c2=58;简装;Y;N` |
| extra_xinjiamu | `c1=92;标准;Y;N` |
| extra_weishu | `c1=61.51;简装;N;N` |
| reported_chaijiu | `72,393` `AJ20261019-152611` |
| reported_quanjiao | `69,219` `144,621` `2,039,974` |
| reported_weishu | `49,238` `AJ20261112-153417` |

## Additional observation vocabulary and source bindings

These labels locate a supported control or structured record column. Missing matches are observation limitations,
not a demand that a valid page use one exact label. The owner also receives the complete source and rendered text.

| Key | Values | Source |
|---|---|---|
| record_root | `报价工具` | tool-procedure section 5 |
| expected_column | `应得` `预期` `expected` | tool-procedure section 5.1 |
| source_column | `来源` `source` | tool-procedure section 5.1 |
| conclusion_column | `结论` `结果` `result` | tool-procedure section 5.1 |
| agree_conclusions | `一致` `相符` `通过` `pass` `matches` `consistent` | semantic equivalents of the section 5.1 conclusion |
| yes_values | `是` `要` `yes` `y` `true` `1` | option state equivalents |
| no_values | `否` `不` `无` `不要` `不拆旧` `不做定制` `no` `n` `false` `0` | option state equivalents |
| advisor_labels | `家装顾问` `顾问姓名` `顾问` `advisor name` `advisor` | baodai's requested advisor name |
| advisor_phone_labels | `顾问手机` `顾问电话` `手机号` `手机号码` `advisor phone` `phone` `mobile` | baodai's requested phone |
| customer_labels | `客户称呼` `称呼` `customer name` `customer` | kehu's optional customer form of address |
| community_labels | `小区名` `小区` `楼盘` `community` `estate` | kehu's optional community |
| register_columns | `版本` `发布日期` `需求人` `变更内容` `适用价目表` `适用活动` `核对记录` `核对结果` | tool-procedure section 5.2 |
| target_xinghu | `v1.0` | new release, tool-procedure 3.5 |
| target_xiangcheng | `v1.0` | new release, tool-procedure 3.5 |
| target_xiangchengagain | `v1.0` | new release, tool-procedure 3.5 |
| target_kaiye | `v1.0` | new release, tool-procedure 3.5 |
| target_baodai | `v1.1` | v1.0 handout plus 0.1 |
| target_chaijiu | `v1.2` | v1.1 handout plus 0.1 |
| target_nuandong | `v1.3` | v1.2 handout plus 0.1 |
| target_kuayue | `v1.3` | v1.2 handout plus 0.1 |
| target_quanjiao | `v1.4` | v1.3 handout plus 0.1 |
| target_weishu | `v1.5` | v1.4 handout plus 0.1 |
| target_kehu | `v1.6` | v1.5 handout plus 0.1 |
| target_xinjiamu | `v1.6` | v1.5 handout plus 0.1 |
| history_dates | `h1=2026-10-02` `h2=2026-10-03` `h3=2026-10-05` `h4=2026-10-06` `h5=2026-10-08` | sample-quotes; tool-procedure FAQ requires original and current dates |
| original_chaijiu | `r1=59.9;标准;Y;N` | reported input on 2026-10-19 |
| original_dates_chaijiu | `2026-10-19` | feedback handout |
| original_quanjiao | `r1=９２平米;标准;N;N` `r2=;标准;N;N` `r3=130.555;标准;N;N` `r4=1200;精装;Y;Y` | feedback handout; r1 is an entry-refusal check, its unreported pricing options use the original page's defaults, not asserted customer facts |
| original_dates_quanjiao | `2026-11-05` `2026-11-06` `2026-11-07` `2026-11-08` | dates of the four feedback reports |
| original_weishu | `r1=61.51;简装;N;N` | reported input on 2026-11-12 |
| original_dates_weishu | `2026-11-12` | audit handout |
| original_shown_chaijiu | `72393` | original page and reported quote |
| original_shown_quanjiao | `entry refused` `69219` `144621` `2039974` | original page and reported outcomes |
| original_shown_weishu | `49238` | original page and reported quote |

| opening_marker | `开口说：` | persona opening instruction, used only by offline native controls |
