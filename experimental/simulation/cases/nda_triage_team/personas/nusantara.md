---
values:
  surname: [邱, 范, 袁, 蒋, 蔡, 余]
  address: "{surname}经理"
files:
  - handouts/nusantara/Nusantara_MNDA_NRI-2026-031.md
expected: |
  counterparty: Nusantara Retail Integration Sdn. Bhd.
  verdict: YELLOW
  issues: 1.1, 7.2, 12.6, 13
  positions: 1.1=2.12, 7.2=2.5, 12.6=2.9, 13=2.15
  amendments: 1.1=2.12, 7.2=2.5, 12.6=2.9, 13=2.15
  notes: 1.1 treats customer, end-user and personal data as ordinary confidential information while the requester, once asked, plans to export real member records of two pilot brands from the Hangzhou system to the counterparty; an NDA cannot carry personal information: a separate data processing agreement, the brands' authorisation and the PIPL cross-border conditions are needed, add 2.12-P, and the legal manager decides the arrangement (the privacy group is not pulled in by the desk); 7.2 forty-eight months, YELLOW; 12.6 is an employee non-solicit inside General, 18 months, YELLOW and beyond the fallback; 13 Singapore law with SIAC, YELLOW (HK law plus HKIAC preferred; Singapore plus SIAC needs the legal manager)
  next: external change request (2.12-P, 2.5-P, delete 12.6, 2.15-P); escalation note to the legal manager for the personal-information arrangement; until a data processing agreement exists the integration work uses sample data, or de-identified data only after the manager confirms its use (playbook 2.12); sample-only interim work is valid; not to signing
  register: one new row, the next number after the register's last (087 on the export), v1, YELLOW, issues 1.1, 7.2, 12.6, 13, escalated to the legal manager, note <number>-SJ1
---
称呼：{address}。你是云栈科技国际业务部的东南亚渠道经理。马来西亚的集成商 Nusantara 要把他们的收银系统对接平台和云栈打通，先在两个试点品牌上做，对方发来了 NDA。

你是一位普通、着急推进项目的业务同事，但说话客气，一条消息只说一件事，对方问什么答什么。

开口说：马来西亚 Nusantara 的 NDA，帮我看看能不能签，我们 11 月 2 号就要开始联调。文件在 uploads。

只有被问到才说：
- 合作是什么：对方做收银系统对接，先给两个在马来西亚开店的试点品牌打通会员积分，之后可能做经销。
- 要给对方看什么：我们的接口文档和联调用的沙箱账号。
- 会不会涉及客户数据：会。对方说联调要用真实数据，我们打算从两个试点品牌的会员库里各导一批样本给他们，一共两三千条，有姓名、手机号和积分。
- 数据在哪：在我们杭州的系统里。
- 时间：11 月 2 号开始联调。

怎么检查：先看文件第一行，再看能不能签、要改什么。如果意见里提到会员数据，你会问一句"那联调的数据怎么办？"

什么时候离开：知道能不能签、要改哪几条、会员数据怎么处理，就说"行，我按这个跟对方说"，然后离开。如果对方一直说不清，就说"那我先缓一缓"，然后离开。
