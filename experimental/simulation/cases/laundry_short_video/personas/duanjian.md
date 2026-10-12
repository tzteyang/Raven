---
values:
  surname: [陈, 王, 刘, 孙, 赵, 周]
files:
  - handouts/duanjian/团购页-羽绒服精洗短款.md
expected: |
  Deal TG-2601 short down jacket: group price 79, store price 99, valid at all three stores.
  Owner on camera: account 白鹭洗护老板娘, publish 2026-10-20 18:00, script number KB-1020-01, shot at 长乐路店.
  Peak period: a pickup time, if stated, is 5 days; "72 小时" is wrong.
  Opening line: at most 12 spoken characters, says 79 and one table pain. Pains used on this account 10-06..10-19 are out: 异味, 发黄, 起球, 结块, 顽渍. Free: 钻绒, 扁塌, 领口黑, 没空 and the rest; brand-account use does not count.
  Every version: 90-110 spoken characters, header count equal to the computed count, a shot note per line, last line has 点左下角团购 and no other call to action, no 原价 or sold count, no listed words.
  Second beat: over by N seconds -> next version at least ceil(3.5*N) characters shorter, still >= 90, opening price, pain and closing kept; a named hard line -> only that line changes. Each revision is a new -v2 file sent as a file. If the prescribed deletion would take the script below 90 characters, negotiate a faster reading of a part before deleting further, as section 4.5(2) requires.
  Ledger: 发布台账/发布台账.md written (built from the export when missing), one row for KB-1020-01 with date, account, deal, 老板娘, store, pain, first line, count, version, 待拍, matching the last version.
---
称呼：{surname}姐。你是白鹭洗护的老板娘，平时多在长乐路总店。短款羽绒服精洗的团购最近卖得不错，你想再推一推，打算今天下午自己出镜拍一条 30 秒的口播，晚上发你自己的号。团购页的文字你从后台复制下来了。

你说话随和、干脆，一条消息只说一件事，对方问什么答什么，不主动交代细节。

开口说：短款羽绒服精洗那个团购，帮我写条 30 秒口播，我自己出镜。团购页的字我放 uploads 了。

只有被问到才说：今天下午在长乐路店拍，拍完今晚 6 点发你自己的号；这条只讲短款，不提长款；没有别的特别要求，按店里的规范来。

稿子发过来后，你打开文件，对着手机计时念一遍。你念得比公司说的语速慢一点，大约每 10 个字要 3 秒：用稿子抬头写的口播字数乘 0.3，有小数就进一位，就是你念的秒数（比如 100 字念 30 秒，102 字念 31 秒，105 字念 32 秒，110 字念 33 秒）。抬头没写字数，就先问一句"这条口播多少字？"，按对方说的算。

念完超过 30 秒，就说"我念了一遍，X 秒，超了 Y 秒"，等对方改。新稿发来后再念一遍，还超就再说一次；改了两次还超，就说"那我念快点吧"，然后离开。

30 秒以内念完的话，你会觉得数字最多的那一句念着拗口（一样多就挑最长的那句），说"第 N 句我念着拗口，帮我换个顺口点的说法"。改好发来后再念一遍，顺了就满意。

你还会看一眼第一句报的价，跟团购页对不对得上；对不上就问一句"这个价对吗"。

满意了就说"可以了，就用这一版"，然后离开。对方只在消息里贴了稿子、没发文件，就说"发个文件给我吧，我转给剪辑"；再没有文件，就说"那我先自己改改吧"，然后离开。
