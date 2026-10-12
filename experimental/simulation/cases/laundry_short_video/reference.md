# 参考事实用到的词和尺子

`owner.py` 从这里读老板娘评审口播稿时当秒表和词表用的东西。团购价和门店价从材料 group-listings 的表里读，用过的开头痛点从材料 publish-ledger 的表里读；表头按下面各列的名字找。算出来的事实交给老板娘，判定由她读稿子后自己做。

下表第二栏里每个反引号是一个取值。这份文件不交给员工。

| 键 | 取值 | 说明 |
|---|---|---|
| today | `2026-10-20` | profile |
| window_days | `14` | 3.3 |
| script_folder | `口播稿` | 7.1 |
| ledger_path | `发布台账/发布台账.md` | 8.1 |
| ledger_material | `publish-ledger` | — |
| listings_material | `group-listings` | — |
| listing_id | `团购编号` | — |
| listing_name | `团购名称` | — |
| listing_group | `团购价` | — |
| listing_store | `门店价` | — |
| listing_stores | `适用门店` | — |
| listing_status | `状态` | — |
| ledger_date | `发布日期` | — |
| ledger_account | `账号` | — |
| ledger_number | `稿件编号` | — |
| ledger_deal | `团购` | — |
| ledger_pain | `开头痛点` | — |
| ledger_first | `首句` | — |
| ledger_speaker | `出镜` | 8.6 |
| ledger_store | `拍摄门店` | 8.6 |
| ledger_count | `口播字数` | 8.6 |
| ledger_version | `版本` | 8.6 |
| ledger_status | `状态` | 8.6 |
| ledger_orders | `成交` | 8.6 |
| ledger_notes | `备注` | 8.6 |
| number_prefix | `KB-` | 8.4 |
| publish_label | `计划发布` | 7.2 |
| account_label | `发布账号` | 7.2 |
| shot | `画面` | 6.1 |
| spoken_label | `口播` | 7.2 |
| count_label | `口播字数` | 7.2 |
| cta | `点左下角团购` | 3.6 |
| currency | `元` `块` | — |
| currency_symbols | `¥=元` | 4.3 |
| prefix_units | `%=百分之` | 4.3 |
| suffix_units | `cm=厘米` `kg=公斤` `km=公里` `h=小时` `°C=度` | 4.3 |
| symbols | `+=加` `/=每` | 4.3 |
| time_words | `点` `半` `分` | 4.3 |
| range_word | `到` | 4.3 |
| year_word | `年` | 4.3 |
| two_word | `两` | 念作二 |
| count_units | `小时` `厘米` `公分` `公斤` `公里` `天` `件` `双` `家` `店` `号` | — |
| count_units_more | `点` `分` `年` `月` `日` `秒` `个` `字` `次` `套` `岁` `米` `度` `折` `层` `位` `条` `成` | — |
| time_units | `小时` `天` | — |
| not_durations | `同一天` `这一天` `那一天` `提前一天` | — |
| validity_marks | `有效` `购买之日` `过期` `买了` `购买` `能用` `可用` `使用期限` | 有效期，不是取件时效 |
| pickup_marks | `取` `送来` `送洗` | 未辨明用途的天数不当作取件承诺 |
| price_marks | `团购` `精洗` `门店价` `短款` `长款` | 没有货币单位的金额仍须按上下文保留 |
| display_marks | `贴片` `字幕` `手卡` `价目牌` `价格牌` | 明确展示给观众的文字，不是镜头参数或场景说明 |
| stores | `长乐路` `河西` `湖南路` | — |
| store_counter | `家` | — |
| accounts | `白鹭洗护老板娘` `白鹭洗护` | — |
| account_aliases | `白鹭洗护老板娘=白鹭洗护老板娘` `老板娘号=白鹭洗护老板娘` `白鹭洗护=白鹭洗护` `品牌号=白鹭洗护` | 明确发布账号的出镜人说明 |
| publish_actions | `发` `发布` `改成` | 出镜人的明确发布说明 |
| past_marks | `上次` `上条` `上周` `之前` `上个月` | 旧视频的回忆不改当前发布安排 |
| publication_negations | `别发` `不发` `不要发` `别用` `不用` `不要用` `不是` | 否定的账号或日期不是新的发布安排 |
| publication_uncertain | `或者` `要不` `待定` `可能` | 未确定的发布安排保留原话，不能自行决定 |
| catchphrases | `家人们` `宝子们` `绝绝子` `老铁们` `集美们` | — |
| clickbait | `不看后悔` `千万别` `先看完` `行业秘密` `行业内幕` `不想让你知道` `99%的人` `震惊` `必看` | — |
| ending_cliches | `关注不迷路` `关注我` `点个关注` `下期` `评论区` `双击` | — |
| offsite | `私信` `微信` `加V` `vx` `电话` `二维码` | — |
| absolute | `最便宜` `最低价` `全城最低` `全网最低` `排名第一` `第一名` `最好的` `最干净` `最专业` `顶级` `100%` `百分百` `百分之百` `绝对` `史上` `唯一` `首选` `独家` | — |
| comparison | `原价` `划线价` `市场价` `专柜价` `打折` `折扣` `立省` `省了` | — |
| overpromise | `全额赔` `包赔` `照价赔` `吊牌价` `原价赔` `假一赔` `洗不坏` `保证洗干净` `一定洗干净` `算我们的` | — |
| guarantee_line | `有保障，赔付按门店保障办法` | — |
| guarantee_terms | `保价` `折旧` `封顶` `最高赔` `赔付` `赔偿` `赔你` `赔钱` | 保障办法 8.2 |
| exaggeration | `跟新的一样` `像新的一样` `焕然一新` `一次见效` `立竿见影` `彻底` | 平台摘录 1.3 |
| sold | `已售` `好评` `售出` `销量` | 5.5 |
| pain_lumps | `结块` `一坨` `成团` | — |
| pain_flat | `扁塌` `扁了` `不蓬松` `塌了` | — |
| pain_leak | `钻绒` `跑绒` `钻毛` `掉绒` | — |
| pain_smell | `异味` `有味` `股味` `发霉` `臭味` `发臭` `鞋臭` | — |
| pain_yellow | `发黄` `泛黄` `黄了` | — |
| pain_collar | `领口黑` `袖口黑` `领口脏` `袖口脏` `油渍` `黑边` | — |
| pain_pilling | `起球` `毛球` | — |
| pain_shape | `变形` `鼓包` `走样` | — |
| pain_shrink | `缩水` `洗小了` | — |
| pain_stain | `顽渍` `污渍` `刷不干净` `洗不掉` | — |
| pain_bulky | `塞不下` `塞不进` `装不下` | — |
| pain_busy | `没空` `没时间` `懒得` | — |

开头痛点各行的第一个取值是台账"开头痛点"一栏登记的名称，其余是口播里常见的说法。
