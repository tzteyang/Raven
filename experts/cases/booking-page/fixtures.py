"""标准答卷与刻意出错答卷，用于验证测量和评审，不发给员工。"""

import json
import re


def contract(rules):
    pick = lambda pattern: re.search(pattern, rules).group(1)
    gap = re.search(r"不足 (\d+) 分钟", rules)
    limit = re.search(r"同一日期最多预约 (\d+) 节", rules)
    return dict(gap=int(gap.group(1)) if gap else 0, limit=int(limit.group(1)) if limit else None,
                book=pick(r"可预约时文字“(.+?)”"), booked=pick(r"按钮文字变成“(.+?)”"),
                full=pick(r"文字“(.+?)”，不能扣成负数"), success=pick(r"页面显示“(.+?)”"),
                conflict=pick(r"冲突时显示“(.+?)”"), cap=pick(r"也不能约，提示“(.+?)”") if limit else "",
                prefix=pick(r"键名严格为“(.+?)”加课表 week_id"))


def page(question, faults=()):
    data = json.loads(question["files"]["课表.json"])
    options = contract(question["files"]["工作规则.md"])
    if "daily" in faults:
        options["limit"] = None
    options.update(faults=list(faults))
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>本周团课预约</title><style>
*{box-sizing:border-box}body{margin:0;background:#f6f6ef;color:#153329;font:17px/1.6 system-ui,sans-serif}
main{max-width:1060px;margin:auto;padding:28px}h1{margin:0 0 8px;font-size:30px}p{margin:8px 0}
label{display:block;font-weight:700}select{padding:10px;font:inherit;background:white;border:1px solid #526b60;border-radius:6px}
#notice{min-height:32px;font-weight:700;color:#733108}#cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px}
article{background:white;padding:18px;border:1px solid #bbc9bf;border-radius:10px}h2{font-size:20px;margin:0}
button,.fake-button{display:block;background:#204d3b;color:white;border:1px solid #204d3b;border-radius:6px;padding:10px 18px;font:inherit;cursor:pointer}
button:disabled{background:#e1e5df;color:#4c534d;border-color:#adb5ab;cursor:default}
button:focus-visible,select:focus-visible{outline:3px solid #bd5400;outline-offset:4px}[hidden]{display:none!important}
</style></head><body><main><h1 id="venue"></h1><p>选择喜欢的团课，在前台平板直接预约。</p>
<label for="type-filter">课程类型</label><select id="type-filter"><option value="all">全部</option></select>
<p id="notice" role="status" aria-live="polite"></p><section id="cards" aria-label="本周课程"></section></main>
<script>
const schedule=__DATA__;
const rules=__RULES__;
const key=rules.prefix+schedule.week_id;
const lookup=new Map(schedule.courses.map(c=>[c.id,c]));
let booked=new Set();
try{
 const stored=JSON.parse(localStorage.getItem(key));
 if(Array.isArray(stored))booked=new Set(stored.filter(id=>typeof id==='string'&&lookup.has(id)&&lookup.get(id).remaining>0));
}catch(e){}
const filter=document.getElementById('type-filter'), cards=document.getElementById('cards'), notice=document.getElementById('notice');
document.getElementById('venue').textContent=schedule.venue+' · 本周团课';
for(const type of [...new Set(schedule.courses.map(c=>c.type))]){const option=document.createElement('option');option.value=type;option.textContent=type;filter.append(option)}
const minutes=t=>Number(t.slice(0,2))*60+Number(t.slice(3));
function conflict(a,b){
 if(a.date!==b.date)return false;
 if(rules.faults.includes('start-only'))return a.start===b.start;
 return minutes(a.start)<minutes(b.end)+rules.gap&&minutes(b.start)<minutes(a.end)+rules.gap;
}
function book(course){
 if(booked.has(course.id)||course.remaining===0)return;
 if([...booked].some(id=>conflict(course,lookup.get(id)))){notice.textContent=rules.conflict;return}
 if(rules.limit&&[...booked].filter(id=>lookup.get(id).date===course.date).length>=rules.limit){notice.textContent=rules.cap;return}
 booked.add(course.id);
 try{if(!rules.faults.includes('no-save'))localStorage.setItem(key,JSON.stringify([...booked]))}catch(e){}
 notice.textContent=rules.success;render();
}
function render(){
 cards.replaceChildren();
 for(const course of schedule.courses){
  const card=document.createElement('article');card.dataset.courseId=course.id;card.hidden=filter.value!=='all'&&filter.value!==course.type;
  const heading=document.createElement('h2');heading.textContent=course.title;
  const detail=document.createElement('p');detail.textContent=course.type+' · '+course.date+' '+course.start+'–'+course.end;
  const trainer=document.createElement('p');trainer.textContent='教练：'+course.coach;
  const seats=document.createElement('p'), count=document.createElement('span');count.dataset.remaining='';
  count.textContent=String(course.remaining-(booked.has(course.id)?1:0));seats.append('剩余 ',count,' 个名额');
  const button=document.createElement('button');button.type='button';button.dataset.book='';
  button.textContent=booked.has(course.id)?rules.booked:(course.remaining===0?rules.full:rules.book);
  button.disabled=booked.has(course.id)||course.remaining===0;
  if(rules.faults.includes('keyboard'))button.tabIndex=-1;
  button.addEventListener('click',()=>book(course));card.append(heading,detail,trainer,seats,button);cards.append(card);
 }
}
filter.addEventListener('change',render);render();
</script></body></html>""".replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__RULES__", json.dumps(options, ensure_ascii=False))


def answer(question, faults=()):
    return "```html\n" + page(question, faults) + "\n```"
