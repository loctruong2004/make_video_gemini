# click_tools.py
# pip install playwright requests
# python -m playwright install

from pathlib import Path
import time, sys, traceback
from playwright.sync_api import sync_playwright

COOKIE_FILE = r"C:\Users\BHMedia-PC\UI_make_video_AI\cookies.json"   # <-- file Netscape cookies (dán nội dung bạn có vào đây)
TARGET_URL = "https://gemini.google.com/"

def parse_cookies_netscape(path: str):
    """
    Parse Netscape cookies.txt into list of cookie dicts for Playwright.
    Format per line: domain \t includeSubdomains \t path \t secure \t expires \t name \t value
    """
    out = []
    txt = Path(path).read_text(encoding="utf-8", errors="ignore")
    for raw in txt.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split('\t')
        if len(parts) < 7:
            parts = line.split()
        if len(parts) < 7:
            # skip unparseable lines
            continue
        domain, include_sub, path_v, secure_flag, expires, name, value = parts[:7]
        secure = secure_flag.upper() == "TRUE"
        try:
            expires_i = int(expires)
        except Exception:
            expires_i = None
        cookie = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": path_v or "/",
            "secure": secure,
            "httpOnly": False,
        }
        if expires_i and expires_i > 0:
            cookie["expires"] = expires_i
        out.append(cookie)
    return out

def load_cookies_into_context(context, cookie_file: str):
    p = Path(cookie_file)
    if not p.exists():
        print(f"[!] Cookie file not found: {cookie_file}")
        return False
    cookies = parse_cookies_netscape(cookie_file)
    if not cookies:
        print("[!] Không tìm thấy cookie hợp lệ trong file.")
        return False
    try:
        context.add_cookies(cookies)
        print(f"[+] Đã thêm {len(cookies)} cookie(s) vào context.")
        return True
    except Exception as e:
        print("[!] Lỗi khi add_cookies:", e)
        return False
def click_tools_flow():
    from playwright.sync_api import sync_playwright
    from pathlib import Path
    import time, traceback

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process",
            ],
        )

        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
            locale="en-US",
            timezone_id="Asia/Bangkok",
        )

        try:
            ok = load_cookies_into_context(context, COOKIE_FILE)  # giữ nguyên hàm cũ của bạn
            page = context.new_page()

            TARGET_URL = "https://gemini.google.com/app"
            print("[*] Mở trang:", TARGET_URL)
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=120_000)

            # chờ thêm cho UI ổn định
            time.sleep(5)
            if "accounts.google.com" in page.url or "signin" in page.url:
                print("⚠️ Cookie/phiên không hợp lệ → bị chuyển sang trang đăng nhập.")
                try:
                    page.screenshot(path="redirect_login.png")
                    Path("redirect_page.html").write_text(page.content(), encoding="utf-8")
                except:
                    pass
                context.close(); browser.close(); return

            page.wait_for_load_state("load", timeout=60_000)

            # ====== 1) CLICK TOOLS ======
            clicked_tools = False
            # C1: role + name
            try:
                page.get_by_role("button", name="Tools").click(timeout=15000)
                clicked_tools = True
                print("✅ Đã click Tools (role).")
            except Exception:
                # C2: CSS :has-text
                try:
                    page.click("button.toolbox-drawer-button:has-text('Tools')", timeout=15000)
                    clicked_tools = True
                    print("✅ Đã click Tools (CSS).")
                except Exception:
                    # C3: icon page_info
                    try:
                        icon = page.query_selector("mat-icon[fonticon='page_info']")
                        if icon:
                            btn = icon.evaluate_handle("el => el.closest('button')")
                            if btn:
                                page.evaluate("(el)=>el.scrollIntoView({block:'center'})", btn)
                                page.evaluate("(el)=>el.click()", btn)
                                clicked_tools = True
                                print("✅ Đã click Tools (icon).")
                    except Exception as e:
                        print("[!] Lỗi click Tools:", e)

            if not clicked_tools:
                print("⚠️ Không click được Tools. Lưu debug.")
                try:
                    page.screenshot(path="no_click_tools.png")
                    Path("page_no_click_tools.html").write_text(page.content(), encoding="utf-8")
                except: pass
                context.close(); browser.close(); return

            # ====== 2) ĐỢI 1s RỒI CLICK 'Create videos with Veo' ======
            time.sleep(1)  # theo yêu cầu: chờ 1 giây sau khi mở Tools

            # C1: Role + exact text
            try:
                page.get_by_role("button", name="Create videos with Veo").click(timeout=15000)
                print("✅ Click 'Create videos with Veo' (role).")
            except Exception:
                # C2: CSS chứa text
                try:
                    page.click("button:has-text('Create videos with Veo')", timeout=15000)
                    print("✅ Click 'Create videos with Veo' (CSS).")
                except Exception:
                    # C3: theo icon movie → closest button
                    try:
                        icon = page.query_selector("mat-icon[fonticon='movie']")
                        if icon:
                            btn = icon.evaluate_handle("el => el.closest('button')")
                            if btn:
                                page.evaluate("(el)=>el.scrollIntoView({block:'center'})", btn)
                                page.evaluate("(el)=>el.click()", btn)
                                print("✅ Click 'Create videos with Veo' (icon).")
                            else:
                                raise RuntimeError("Không tìm thấy button gần icon 'movie'.")
                        else:
                            raise RuntimeError("Không thấy icon 'movie'.")
                    except Exception as e:
                        print("❌ Không click được 'Create videos with Veo':", e)
                        try:
                            page.screenshot(path="no_click_veo.png")
                            Path("page_no_click_veo.html").write_text(page.content(), encoding="utf-8")
                        except: pass
                        # nếu muốn dừng hẳn:
                        # context.close(); browser.close(); return

            # (tuỳ chọn) chờ trang Veo load
            time.sleep(2)
            print("Title:", page.title())
            # lưu DOM sau khi chuyển sang Veo
            try:
                Path("after_click_veo.html").write_text(page.content(), encoding="utf-8")
            except: pass

        except Exception as e:
            print("❌ Lỗi runtime:", e)
            traceback.print_exc()
            try:
                page.screenshot(path="runtime_error.png")
                Path("runtime_page.html").write_text(page.content(), encoding="utf-8")
            except: pass
        finally:
            try: context.close()
            except: pass
            try: browser.close()
            except: pass


if __name__ == "__main__":
    click_tools_flow()
