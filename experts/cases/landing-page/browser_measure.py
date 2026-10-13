"""Playwright独立进程：stdin JSON，stdout JSON；只提供渲染事实，不给通过/失败判定。

由measure.py调用仓库根目录的 .venv/bin/python运行，避免异步评审循环内启动同步Playwright。
任何网页外部请求均拦截；脚本不执行，规则要求静态单文件。
"""

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

COLLECT = r"""({targets, products}) => {
  const rnd = x => Math.round(x * 100) / 100;
  const norm = s => (s || '').replace(/\s+/g, '');
  const contains = (hay, needle) => {
    hay=norm(hay);needle=norm(needle);let pos=-1;
    while((pos=hay.indexOf(needle,pos+1))>=0){
      if(/^\d/.test(needle) && pos>0 && /[\d.]/.test(hay[pos-1]))continue;
      if(/\d$/.test(needle) && /[\d.]/.test(hay[pos+needle.length]||''))continue;
      return true;
    }
    return false;
  };
  const rect = r => ({left:rnd(r.left), top:rnd(r.top), right:rnd(r.right), bottom:rnd(r.bottom), width:rnd(r.width), height:rnd(r.height)});
  const color = s => {
    if (!s || s === 'transparent' || s === 'none') return [0,0,0,0];
    const v = s.match(/[\d.]+/g);
    if (s.startsWith('rgb') && v) return [+v[0],+v[1],+v[2],v.length > 3 ? +v[3] : 1];
    return null;
  };
  const over = (a,b) => {
    if (!a || !b) return null;
    const alpha = a[3] + b[3] * (1-a[3]);
    return alpha ? [0,1,2].map(i => (a[i]*a[3]+b[i]*b[3]*(1-a[3]))/alpha).concat(alpha) : [0,0,0,0];
  };
  const hex = a => a ? '#' + a.slice(0,3).map(v => Math.round(v).toString(16).padStart(2,'0')).join('').toUpperCase() : 'unsupported';
  const composite = (el,paint,ownBackground) => {
    let result = paint;
    for (let p=el;p;p=p.parentElement) {
      const c = getComputedStyle(p);
      if (p !== el || ownBackground) result = over(result,color(c.backgroundColor));
      if (!result) return null;
      result[3] *= Number(c.opacity);
    }
    return over(result,[255,255,255,1]);
  };
  const lum = a => a.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);
  const contrast = (a,b) => a && b ? rnd((Math.max(lum(a),lum(b))+.05)/(Math.min(lum(a),lum(b))+.05)) : null;
  const displayed = el => {
    for (let p=el;p;p=p.parentElement) {
      const c=getComputedStyle(p);
      if(c.display==='none'||c.visibility==='hidden'||c.visibility==='collapse'||Number(c.opacity)===0) return false;
    }
    return el.getClientRects().length > 0;
  };
  const clipped = (el,r) => {
    const cuts=[];
    for(let p=el.parentElement;p;p=p.parentElement) {
      const c=getComputedStyle(p), b=p.getBoundingClientRect();
      if(['hidden','clip','scroll','auto'].includes(c.overflowX) && (r.left<b.left-.5||r.right>b.right+.5)) cuts.push(p.tagName+':x');
      if(['hidden','clip','scroll','auto'].includes(c.overflowY) && (r.top<b.top-.5||r.bottom>b.bottom+.5)) cuts.push(p.tagName+':y');
    }
    return cuts;
  };
  const visible = el => {
    const r=el.getBoundingClientRect();
    let occluded=null;
    if(r.bottom>0&&r.top<innerHeight&&r.right>0&&r.left<innerWidth){
      const x=Math.min(innerWidth-1,Math.max(0,(r.left+r.right)/2)),y=Math.min(innerHeight-1,Math.max(0,(r.top+r.bottom)/2));
      const top=document.elementFromPoint(x,y);
      occluded=!!top && top!==el&&!el.contains(top)&&!top.contains(el);
    }
    return {displayed:displayed(el), rect:rect(r), clipping:clipped(el,r), centerCovered:occluded};
  };
  const all=[...document.querySelectorAll('body *')].filter(e=>!['SCRIPT','STYLE','META','LINK','TITLE'].includes(e.tagName));
  const paints=new Map(), effects=[], styles=[], styleIds=new Map(), textRuns=[];
  const addPaint=(kind,css,actual,el)=> {
    if(!actual)return;
    const k=kind+hex(actual), old=paints.get(k);
    if(old) {old.elements++;return;}
    paints.set(k,{kind,css,actual:hex(actual),sample:el.tagName.toLowerCase()+(el.id?'#'+el.id:''),elements:1});
  };
  for(const el of [document.documentElement,document.body,...all]) {
    if(!el||!displayed(el))continue;
    const c=getComputedStyle(el), b=color(c.backgroundColor);
    if(b&&b[3]>0) addPaint('background',c.backgroundColor,composite(el,b,false),el);
    for(const side of ['Top','Right','Bottom','Left']) if(parseFloat(c['border'+side+'Width'])>0 && c['border'+side+'Style']!=='none'){
      const paint=color(c['border'+side+'Color']);
      if(paint&&paint[3]>0)addPaint('border',c['border'+side+'Color'],composite(el,paint,true),el);
    }
    if(el.namespaceURI==='http://www.w3.org/2000/svg')for(const k of ['fill','stroke']){
      const paint=color(c[k]);
      if(paint&&paint[3]>0 && !['svg','g','defs'].includes(el.tagName))addPaint('svg-'+k,c[k],composite(el,paint,true),el);
    }
    const used={};
    for(const [k,value] of Object.entries({backgroundImage:c.backgroundImage,boxShadow:c.boxShadow,textShadow:c.textShadow,filter:c.filter,backdropFilter:c.backdropFilter,mixBlendMode:c.mixBlendMode}))
      if(value && value!=='none'&&value!=='normal')used[k]=value;
    for(const pseudo of ['::before','::after']){
      const pc=getComputedStyle(el,pseudo);
      if(pc.content && !['none','normal','""'].includes(pc.content))used[pseudo+' content']=pc.content;
    }
    if(Object.keys(used).length)effects.push({element:el.tagName.toLowerCase()+(el.id?'#'+el.id:''),text:el.innerText?.slice(0,80)||'',...used});
  }
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  let node;
  while(node=walker.nextNode()) {
    const el=node.parentElement,text=node.textContent.replace(/\s+/g,' ').trim();
    if(!text||!el||['SCRIPT','STYLE'].includes(el.tagName)||!displayed(el))continue;
    const range=document.createRange();range.selectNodeContents(node);const r=range.getBoundingClientRect();
    if(r.width===0||r.height===0)continue;
    const c=getComputedStyle(el), fg=composite(el,color(c.color),true),bg=composite(el,color(c.backgroundColor),false);
    const style={heading:!!el.closest('h1,h2,h3,h4,h5,h6'),fontFamily:c.fontFamily,fontSize:parseFloat(c.fontSize),fontWeight:c.fontWeight,
                 cssColor:c.color,actualColor:hex(fg),actualBackground:hex(bg),contrast:contrast(fg,bg)};
    const sk=JSON.stringify(style);let id=styleIds.get(sk);
    if(!id){id='s'+(styles.length+1);styleIds.set(sk,id);styles.push({id,...style});}
    addPaint('text',c.color,fg,el);
    textRuns.push({text,style:id,rect:rect(r),clipping:clipped(el,r)});
  }
  const occurrences = needle => all.filter(el => contains(el.textContent,needle) &&
        ![...el.children].some(child=>contains(child.textContent,needle)))
        .slice(0,8).map(el=>({text:el.innerText||el.textContent,...visible(el)}));
  const matched={}; for(const [k,needle] of Object.entries(targets))matched[k]=occurrences(needle);
  const pairs=products.map(p=>({name:p['名称'],price:p['价格'],status:p['状态'],nameOccurrences:occurrences(p['名称']),priceOccurrences:occurrences(p['价格']),
    containers:all.filter(el=>contains(el.textContent,p['名称'])&&contains(el.textContent,p['价格'])&&
      ![...el.children].some(ch=>contains(ch.textContent,p['名称'])&&contains(ch.textContent,p['价格'])))
      .slice(0,3).map(el=>({text:(el.innerText||el.textContent).slice(0,250),...visible(el)}))}));
  return {viewport:{width:innerWidth,height:innerHeight},document:{width:Math.max(document.documentElement.scrollWidth,document.body.scrollWidth),height:Math.max(document.documentElement.scrollHeight,document.body.scrollHeight)},
    main:[...document.querySelectorAll('main')].map(visible),targets:matched,products:pairs,
    actions:[...document.querySelectorAll('a,button,[role=button]')].map(el=>{const c=getComputedStyle(el);return {text:el.innerText,...visible(el),radii:[c.borderTopLeftRadius,c.borderTopRightRadius,c.borderBottomRightRadius,c.borderBottomLeftRadius],fontFamily:c.fontFamily};}),
    styles,textRuns,paints:[...paints.values()],effects,
    restrictedElements:[...document.querySelectorAll('img,canvas,video,iframe,script,svg text')].map(el=>({tag:el.tagName,source:el.getAttribute('src'),text:el.textContent.slice(0,80)})),
    text:document.body.innerText};
}"""


def inspect(html: str, views: list, targets: dict, products: list, screenshot: str | None = None) -> dict:
    result, requests = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = browser.new_context(java_script_enabled=False)
            context.route("**/*", lambda route: (requests.append(route.request.url), route.abort()))
            page = context.new_page()
            for n, (width, height) in enumerate(views):
                page.set_viewport_size({"width": width, "height": height})
                page.set_content(html, wait_until="domcontentloaded", timeout=12000)
                page.evaluate("window.scrollTo(0,0)")
                result.append(page.evaluate(COLLECT, {"targets": targets, "products": products}))
                if screenshot and n == 0:
                    page.screenshot(path=screenshot, full_page=True)
        finally:
            browser.close()
    return {"engine": "Chromium / Playwright (external requests blocked)", "views": result, "externalRequests": sorted(set(requests))}


if __name__ == "__main__":
    payload = json.load(sys.stdin)
    try:
        print(json.dumps(inspect(**payload), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"measurement_error": f"{type(exc).__name__}: {str(exc)[:800]}"}, ensure_ascii=False))
        raise SystemExit(2)
