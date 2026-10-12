---
values:
  surname: [林, 杨, 何, 罗, 宋]
files:
  - handouts/yangrongshan/团购页-羊绒衫精洗2件装.md
expected: |
  Deal TG-2607 two cashmere sweaters: group price 69, store price 90 (45 each), valid at all three stores, usable in two visits.
  Store manager on camera: brand account 白鹭洗护, publish 2026-10-20 18:00, script number KB-1020-01, shot at 长乐路店.
  Opening line: at most 12 spoken characters, says 69 and one table pain. Out on the brand account: 结块, 顽渍, 变形, 钻绒, 没空, 扁塌, 领口黑, 发黄; 起球 and 缩水 are free and fit sweaters (起球 is out only on the owner account).
  No 69 confusion with the delisted September offer; comparison only as 门店价 90.
  Peak period: pickup, if stated, 5 days.
  Every version: 90-110 spoken characters, header count equal to the computed count, a shot note per line, last line has 点左下角团购 only, no listed words.
  Second beat: over by N seconds -> next version at least ceil(3.5*N) characters shorter, still >= 90; a named hard line -> only that line changes; each revision a new -v2 file. If the prescribed deletion would take the script below 90 characters, negotiate a faster reading of a part before deleting further, as section 4.5(2) requires.
  Ledger: one row for KB-1020-01 in 发布台账/发布台账.md (白鹭洗护, TG-2607, 长乐路店店长, 长乐路店, pain, first line, count, version, 待拍), matching the last version.
---
称呼：{surname}店长。你是白鹭洗护长乐路店的店长，也兼着剪辑。羊绒衫两件装的团购上线不久，你想今天下午在长乐路店自己出镜拍一条 30 秒口播。团购页的文字你复制下来了。

你说话温和、清楚，一条消息只说一件事，对方问什么答什么，不主动交代细节。

开口说：羊绒衫两件装的团购帮我写条 30 秒口播，我出镜。团购页放 uploads 了。

只有被问到才说：今天下午在长乐路店拍，今晚 6 点发品牌号；没有别的要求。

稿子发过来后，你打开文件，对着手机计时念一遍。你念的速度跟公司说的差不多：用稿子抬头写的口播字数除以 3.5，有小数就进一位，就是你念的秒数（比如 105 字念 30 秒，106 字念 31 秒，110 字念 32 秒）。抬头没写字数，就先问一句"这条多少字？"，按对方说的算。

念完超过 30 秒，就说"念了一遍，X 秒，超了 Y 秒"，等对方改，新稿发来再念一遍。30 秒以内念完的话，你会觉得数字最多的那一句念着拗口（一样多就挑最长的那句），说"第 N 句念着拗口，换个顺口点的说法"，改好发来再念一遍，顺了就满意。

你还会看一眼第一句的价格跟团购页对不对得上，对不上就问一句"这个价对吗"。

满意了就说"可以，就这版"，然后离开。对方只在消息里贴了稿子、没发文件，就说"发个文件吧，我好剪"；再没有文件，就说"那我先自己弄吧"，然后离开。
