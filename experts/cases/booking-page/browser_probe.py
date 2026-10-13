"""在隔离 Chromium 中操作实际交付，不根据源码猜行为。

stdin={html,question}；stdout是浏览器观察记录。由measure.py作为子进程运行，
避免Studio的asyncio事件循环与sync Playwright冲突。所有非主文档请求都记录并拦截。
"""

import json
import sys
import traceback

from playwright.sync_api import sync_playwright

MAIN = "http://booking.test/booking.html"


def probe(question, html):
    ref = question["reference"]
    roles, key = ref["浏览器动作"], ref["当前存储键"]
    requests, errors, console_errors, dialogs = [], [], [], []
    result = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(viewport={"width": 1024, "height": 768}, service_workers="block")

        def routing(route):
            url = route.request.url
            if url == MAIN:
                route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            else:
                requests.append(url)
                route.abort()
        context.route("**/*", routing)
        page = context.new_page()
        page.set_default_timeout(1300)
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
        page.on("dialog", lambda dialog: (dialogs.append(dict(type=dialog.type, message=dialog.message)), dialog.dismiss()))

        def navigate():
            page.goto(MAIN, wait_until="load", timeout=6000)
            page.wait_for_timeout(40)

        def snapshot(detail=False):
            return page.evaluate("""detail => {
              const cards=[...document.querySelectorAll('[data-course-id]')];
              const visible=e=>!!(e.getClientRects().length)&&getComputedStyle(e).visibility!=='hidden';
              const remaining={}, buttons={}, disabled=[], shown=[], missing=[], details=[];
              for(const c of cards){
                const id=c.getAttribute('data-course-id'), n=c.querySelectorAll('[data-remaining]'), bs=c.querySelectorAll('[data-book]');
                if(n.length!==1||bs.length!==1)missing.push({id,remainingNodes:n.length,buttonNodes:bs.length});
                remaining[id]=n.length ? n[0].textContent.trim() : null;
                if(visible(c))shown.push(id);
                if(bs.length){const b=bs[0], text=b.innerText?.trim()||b.textContent.trim();
                  (buttons[text]??=[]).push(id); if(b.disabled||b.getAttribute('aria-disabled')==='true')disabled.push(id);}
                if(detail)details.push({id,text:c.innerText,visible:visible(c)});
              }
              const n=document.getElementById('notice');
              return {cardCount:cards.length,visible:shown,remaining,buttons,disabled,missing,
                notice:n?.innerText?.trim()??null,
                ...(detail?{details,noticeAttributes:n?{role:n.getAttribute('role'),live:n.getAttribute('aria-live'),visible:visible(n)}:null,
                select:document.querySelector('#type-filter')?{tag:document.querySelector('#type-filter').tagName,
                label:[...document.querySelectorAll('label')].filter(l=>l.control===document.querySelector('#type-filter')).map(l=>l.innerText),
                options:[...document.querySelector('#type-filter').options||[]].map(o=>({value:o.value,text:o.text}))}:null}:{})};
            }""", detail)

        def click(cid, physical=False):
            button = page.locator(f'[data-course-id="{cid}"] [data-book]')
            if button.count() != 1:
                return {"action": "无法点击", "reason": f"按钮数量{button.count()}"}
            if not button.is_visible():
                return {"action": "无法点击", "reason": "按钮不可见"}
            if physical:
                # A real pointer click also probes faux-disabled divs/aria-disabled buttons.
                # Playwright's ordinary click would refuse those before the page sees input.
                button.scroll_into_view_if_needed()
                box = button.bounding_box()
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
                page.wait_for_timeout(20)
                return {"action": "鼠标实际点到按钮位置", "browserDisabled": not button.is_enabled()}
            if not button.is_enabled():
                return {"action": "未触发", "reason": "浏览器识别为禁用"}
            try:
                button.click(timeout=1300)
                page.wait_for_timeout(20)
                return {"action": "已点击"}
            except Exception as exc:
                return {"action": "点击异常", "reason": str(exc).splitlines()[0][:180]}

        def storage():
            try:
                return page.evaluate("Object.fromEntries(Object.keys(localStorage).map(k=>[k,localStorage.getItem(k)]))")
            except Exception as exc:
                return {"read_error": str(exc).splitlines()[0][:180]}

        def reset(value=None, alternate=False):
            page.evaluate("""v=>{localStorage.clear();if(v.value!==null)localStorage.setItem(v.key,v.value)}""",
                          dict(key=key + "-old" if alternate else key, value=value))
            page.reload(wait_until="load", timeout=6000)
            page.wait_for_timeout(30)

        try:
            navigate()
            result["initial"] = snapshot(True)
            result["filters"] = []
            filt = page.locator("#type-filter")
            for kind in list(ref["筛选后可见id"]) + ["all"]:
                try:
                    filt.select_option(kind, timeout=900)
                    s = snapshot()
                    result["filters"].append(dict(selected=kind, visible=s["visible"], remaining=s["remaining"]))
                except Exception as exc:
                    result["filters"].append(dict(selected=kind, error=str(exc).splitlines()[0][:180]))
            result["full"] = []
            for cid in ref["满员id"]:
                result["full"].append(dict(click=cid, operation=click(cid, physical=True), after=snapshot()))
            result["sequence"] = []
            for step in ref["顺序操作"]:
                result["sequence"].append(dict(action=step["action"], click=step["click"], operation=click(step["click"]), after=snapshot()))
            result["saved"] = storage()
            page.reload(wait_until="load", timeout=6000)
            result["reload"] = snapshot()
            result["filter_after_booking"] = []
            for kind in [next(iter(ref["筛选后可见id"])), "all"]:
                try:
                    filt.select_option(kind, timeout=900)
                    result["filter_after_booking"].append(dict(selected=kind, after=snapshot()))
                except Exception as exc:
                    result["filter_after_booking"].append(dict(selected=kind, error=str(exc).splitlines()[0][:180]))
            result["storage_cases"] = []
            trials = [("清空", None, False), ("坏JSON", "{broken:", False),
                      ("非数组", '{"booked":["' + roles["first"] + '"]}', False),
                      ("混合数组", json.dumps(ref["混合存储"]["input"]), False),
                      ("别的周", json.dumps([roles["first"]]), True)]
            for label, value, alternate in trials:
                start_errors = len(errors)
                reset(value, alternate)
                result["storage_cases"].append(dict(name=label, after=snapshot(), pageerrors=errors[start_errors:]))
            reset()
            page.evaluate("document.activeElement?.blur()")
            tabs = []
            # Initial focus audit visits every focusable control with real Tab presses.
            for _ in range(min(80, len(ref["初始名额"]) * 3 + 15)):
                page.keyboard.press("Tab")
                focus = page.evaluate("""() => {const e=document.activeElement,s=getComputedStyle(e);return {
                  tag:e.tagName,id:e.id,course:e.closest('[data-course-id]')?.getAttribute('data-course-id')??null,
                  isBook:e.hasAttribute('data-book'),text:e.innerText?.slice(0,70)??'',
                  focusVisible:e.matches(':focus-visible'),outline:s.outline,boxShadow:s.boxShadow,
                  border:s.border,background:s.backgroundColor}}
                """)
                tabs.append(focus)
                observed = {f["course"] for f in tabs if f["isBook"]}
                if roles["first"] in observed and set(i for i, n in ref["初始名额"].items() if n > 0) <= observed and any(f["id"] == "type-filter" for f in tabs):
                    break
            # Start again so Enter is delivered to a button reached only by Tab.
            reset()
            page.evaluate("document.activeElement?.blur()")
            entered = False
            for _ in range(min(80, len(ref["初始名额"]) * 3 + 15)):
                page.keyboard.press("Tab")
                on_target = page.evaluate("""id=>document.activeElement?.hasAttribute('data-book')&&
                    document.activeElement.closest('[data-course-id]')?.getAttribute('data-course-id')===id""", roles["first"])
                if on_target:
                    page.keyboard.press("Enter")
                    entered = True
                    break
            result["keyboard"] = dict(tab= tabs, enterSent=entered, after=snapshot())
            reset()
            # Fresh documents receive forbidden storage access from their first script onward.
            page.add_init_script("""Object.defineProperty(window,'localStorage',{configurable:true,get(){
                throw new DOMException('Storage blocked for test','SecurityError')}});""")
            start_errors = len(errors)
            page.reload(wait_until="load", timeout=6000)
            initial_blocked = snapshot()
            action = click(roles["first"])
            after_blocked = snapshot()
            page.reload(wait_until="load", timeout=6000)
            result["storage_disabled"] = dict(initial=initial_blocked, operation=action, after=after_blocked,
                                              reload=snapshot(), pageerrors=errors[start_errors:])
        except Exception as exc:
            result["probe_interrupted"] = str(exc).splitlines()[0][:300]
        result.update(external_requests=list(dict.fromkeys(requests)), pageerrors=list(dict.fromkeys(errors)),
                      console_errors=list(dict.fromkeys(console_errors)), dialogs=dialogs)
        context.close()
        browser.close()
    return result


if __name__ == "__main__":
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(probe(payload["question"], payload["html"]), ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"probe_error": str(exc), "trace": traceback.format_exc(limit=2)}, ensure_ascii=False))
        sys.exit(1)
