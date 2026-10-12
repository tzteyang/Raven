# 参考事实用到的材料与词

本案例的 `owner.py` 从每张卡附带的订单台账里，按店主的口径算出这张卡"应有的数"：时段内每月营收、环比、掉得最多的月份、三个渠道的营收、复购率、要列的录错和重复、0 元单、跨调价的单，以及追问时用得上的分套餐营收和没有拍摄的日子；再从交付的网页里量出页面上点到了哪些单号、写了哪些百分比、有没有小数金额和超过两句的段落，从执行记录里数出交页前问过的问题、已核对订单的写入和委派。判定仍由店主读对话和页面后自己做。

下表第二栏里每个反引号是一个取值。这份文件不交给 AI 助理。

| 键 | 取值 | 说明 |
|---|---|---|
| price_material | `price-history` | 价目与调价记录所在的材料 |
| price_header | `生效日期` | 历次价目那张表第一列的表头 |
| price_columns | `证件照` `写真·简约` `写真·经典` `写真·臻选` `亲子照` `加修` | 历次价目表里各套餐和加修那几列的表头开头 |
| package_words | `证件照` `简约` `经典` `臻选` `亲子` | 认套餐的关键字，顺序同上 |
| sheet_dianping | `点评导出` | 团购平台那张表 |
| sheet_douyin | `抖音导出` | 手抄的短视频平台那张表 |
| sheet_wechat | `手记` | 微信收款那张表，也是自编单号的前缀 |
| dianping_id | `订单号` | 点评表：单号 |
| dianping_listing | `团购名称` | 点评表：套餐名 |
| dianping_bought | `下单时间` | 点评表：付款时刻 |
| dianping_used | `验券时间` | 点评表：拍摄时刻 |
| dianping_phone | `手机号` | 点评表：打码号码 |
| dianping_paid | `顾客实付` | 点评表：客人付的钱 |
| dianping_status | `订单状态` | 点评表：状态 |
| douyin_id | `订单编号` | 抖音表：单号 |
| douyin_listing | `商品` | 抖音表：套餐名 |
| douyin_bought | `支付时间` | 抖音表：付款时刻 |
| douyin_used | `核销时间` | 抖音表：拍摄时刻 |
| douyin_phone | `手机号` | 抖音表：打码号码 |
| douyin_paid | `支付金额` | 抖音表：客人付的钱 |
| douyin_status | `状态` | 抖音表：状态 |
| wechat_id | `单号` | 手记：单号 |
| wechat_day | `日期` | 手记：收钱那天 |
| wechat_name | `客人` | 手记：微信备注 |
| wechat_phone | `手机` | 手记：完整号码 |
| wechat_package | `套餐` | 手记：套餐简写 |
| wechat_kind | `款项` | 手记：款项 |
| wechat_paid | `金额` | 手记：金额 |
| wechat_note | `备注` | 手记：备注 |
| done_status | `已验券` `已核销` | 两张平台表里"已到店拍摄"的状态 |
| payment_types | `全款` `定金` `尾款` `加修` `退款` | 手记的五种款项，顺序固定 |
| count_unit | `张` | 备注里加修几张的量词 |
| deposit | `200` | 定金 |
| clear_note | `送` `置换` | 0 元单备注里出现就算写清楚了 |
| date_words | `年` `月` `日` | 文字日期里的年、月、日 |
| money_marks | `元` `￥` | 金额里要去掉的记号 |
| big_unit | `万` | 页面上不该出现的金额单位 |
| sentence_ends | `。` `！` `？` | 数段落句数用的句末标点 |
| question_marks | `？` `?` | 认问句用的问号 |
| checked_file | `已核对订单` | 已核对订单文件名里的词 |
| repurchase_word | `复购` | 页面上说复购率那一块的词 |
| channel_words | `点评` `抖音` `微信` | 页面上三个渠道的叫法，顺序是点评/美团、抖音、微信 |
| review_folder | `复盘` | 已核对订单所在的共享文件夹 |
| inbox | `uploads` | 店主发附件的文件夹，写在这里不算记下 |
| period_qiansanji | `2026-01` `2026-09` | 卡 qiansanji 问的时段 |
| period_jiuyue | `2026-09` `2026-09` | 卡 jiuyue 问的时段 |
| period_sanjidu | `2026-07` `2026-09` | 卡 sanjidu 问的时段 |
| period_shujia | `2026-07` `2026-08` | 卡 shujia 问的时段 |
| period_genxin | `2026-01` `2026-09` | 卡 genxin 问的时段 |
| period_erjidu | `2026-04` `2026-06` | 卡 erjidu 问的时段 |
| period_siji | `2025-10` `2025-12` | 卡 siji 问的时段 |
| period_shiyue | `2025-10` `2025-10` | 卡 shiyue 问的时段 |
| period_shieryue | `2025-12` `2025-12` | 卡 shieryue 问的时段 |
| period_shiyiyue | `2025-11` `2025-11` | 卡 shiyiyue 问的时段 |
| period_buqi | `2025-10` `2025-12` | 卡 buqi 问的时段 |
| period_sijiagain | `2025-10` `2025-12` | 卡 sijiagain 问的时段 |

| checked_headers | `单号` `日期` `表` `内容` `店主怎么说` `记的日期` | 复盘做法3.2规定的已核对订单六列；只写单号不算完整确认记录 |
