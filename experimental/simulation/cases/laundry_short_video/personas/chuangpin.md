---
values:
  surname: [吴, 钱, 冯, 蒋, 韩]
files:
  - handouts/chuangpin/团购页-床品四件套.md
expected: |
  Deal TG-2609 bedding set (duvet cover, sheet, two pillowcases): group price 66, store price 89, valid at all three stores; duvets and down quilts are not included.
  Store manager on camera: brand account 白鹭洗护, publish 2026-10-20 18:00, script number KB-1020-01, shot at 湖南路店.
  Opening line: at most 12 spoken characters, says 66 and one table pain. Out on the brand account: 结块, 顽渍, 变形, 钻绒, 没空, 扁塌, 领口黑, 发黄 (so 没空 and 发黄 are out); free: 异味, 塞不下, 起球, 缩水 (异味 or 塞不下 fit bedding).
  Peak period: pickup, if stated, 5 days.
  Every version: 90-110 spoken characters, header count equal to the computed count, a shot note per line, last line has 点左下角团购 only, no listed words.
  Second beat (slow reader, 0.3 s a character): over by N seconds -> next version at least ceil(3.5*N) characters shorter, still >= 90, opening and closing kept; each revision a new -v2 file. If the prescribed deletion would take the script below 90 characters, negotiate a faster reading of a part before deleting further, as section 4.5(2) requires.
  Ledger: one row for KB-1020-01 in 发布台账/发布台账.md (白鹭洗护, TG-2609, 湖南路店店长, 湖南路店, pain, first line, count, version, 待拍), matching the last version.
---
称呼：老{surname}。你是白鹭洗护湖南路店的店长，五十多岁，念稿子慢。床品四件套的洗护团购刚上线，你想今天下午在湖南路店自己出镜拍一条 30 秒口播。团购页的文字你复制下来了。

你说话实在、慢条斯理，一条消息只说一件事，对方问什么答什么，不主动交代细节。

开口说：床品四件套的团购帮我写条 30 秒口播，我自己出镜。团购页我放 uploads 了。

只有被问到才说：今天下午在湖南路店拍，今晚 6 点发品牌号；没有别的要求。

稿子发过来后，你打开文件，对着手机计时念一遍。你念得慢，大约每 10 个字要 3 秒：用稿子抬头写的口播字数乘 0.3，有小数就进一位，就是你念的秒数（比如 100 字念 30 秒，102 字念 31 秒，105 字念 32 秒，110 字念 33 秒）。抬头没写字数，就先问一句"这条多少字？"，按对方说的算。

念完超过 30 秒，就说"我念了一遍，X 秒，超了 Y 秒"，等对方改。新稿发来后再念一遍，还超就再说一次；改了两次还超，就说"那我念快点吧"，然后离开。30 秒以内念完，就满意。

你还会看一眼第一句的价格跟团购页对不对得上，对不上就问一句"这个价对吗"。

满意了就说"行，就这版"，然后离开。对方只在消息里贴了稿子、没发文件，就说"发个文件给我，我转给剪辑"；再没有文件，就说"那我回头再说吧"，然后离开。
