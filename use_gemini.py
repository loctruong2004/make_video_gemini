# click_tools.py
# pip install playwright requests
# python -m playwright install

from pathlib import Path
import os
import time, sys, traceback
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

COOKIE_FILE = r"C:\Users\BHMedia-PC\UI_make_video_AI\cookies.json"   # <-- file Netscape cookies (dán nội dung bạn có vào đây)
TARGET_URL = "https://gemini.google.com/"
IMAGE_PATH = r"C:\Users\BHMedia-PC\UI_make_video_AI\tx02.webp"  # <-- Ảnh cần upload
PROMPT_TEXT = "tạo video quảng cáo túi sách"       # <-- Prompt cần nhập
AUTO_CLICK_SEND = True                                                   # <-- Gửi bằng nút Send message
AUTO_CLICK_GENERATE = False                                              # <-- Hoặc bấm Generate (đặt True nếu muốn)

# Thư mục lưu video tải về
DOWNLOAD_DIR = r"C:\Users\BHMedia-PC\UI_make_video_AI\downloads"

def parse_cookies_netscape(path: str):
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
def _wait_image_ready(page, max_wait_sec: int = 30) -> bool:
    """
    Đợi cho đến khi input[type=file] có ít nhất 1 file (ảnh đã gắn vào form).
    Trả về True nếu đã thấy file, False nếu quá timeout.
    """
    start = time.time()
    while time.time() - start < max_wait_sec:
        try:
            has_file = page.evaluate("""
            () => {
              const inp = document.querySelector('input[type="file"]');
              if (!inp) return false;
              const f = inp.files;
              return !!(f && f.length > 0);
            }
            """)
            if has_file:
                print("✅ Ảnh đã được gắn vào input.")
                return True
        except Exception:
            pass
        time.sleep(1)
    print(f"⚠️ Hết {max_wait_sec}s vẫn chưa xác nhận ảnh gắn vào input.")
    return False

def _try_click_tools(page) -> bool:
    try:
        page.get_by_role("button", name="Tools").click(timeout=15000)
        print("✅ Đã click Tools (role).")
        return True
    except Exception:
        pass
    try:
        page.click("button.toolbox-drawer-button:has-text('Tools')", timeout=15000)
        print("✅ Đã click Tools (CSS).")
        return True
    except Exception:
        pass
    try:
        icon = page.query_selector("mat-icon[fonticon='page_info']")
        if icon:
            btn = icon.evaluate_handle("el => el.closest('button')")
            if btn:
                page.evaluate("(el)=>el.scrollIntoView({block:'center'})", btn)
                page.evaluate("(el)=>el.click()", btn)
                print("✅ Đã click Tools (icon).")
                return True
    except Exception as e:
        print("[!] Lỗi click Tools:", e)
    return False

def _try_click_create_veo(page) -> bool:
    try:
        page.get_by_role("button", name="Create videos with Veo").click(timeout=15000)
        print("✅ Click 'Create videos with Veo' (role).")
        return True
    except Exception:
        pass
    try:
        page.click("button:has-text('Create videos with Veo')", timeout=15000)
        print("✅ Click 'Create videos with Veo' (CSS).")
        return True
    except Exception:
        pass
    try:
        icon = page.query_selector("mat-icon[fonticon='movie']")
        if icon:
            btn = icon.evaluate_handle("el => el.closest('button')")
            if btn:
                page.evaluate("(el)=>el.scrollIntoView({block:'center'})", btn)
                page.evaluate("(el)=>el.click()", btn)
                print("✅ Click 'Create videos with Veo' (icon).")
                return True
    except Exception as e:
        print("❌ Không click được 'Create videos with Veo':", e)
    return False

def _click_add_photo_via_js(page) -> bool:
    try:
        page.evaluate("""
        document.querySelector("mat-icon[fonticon='add_photo_alternate']")
          ?.closest("button")
          ?.click();
        """)
        print("✅ Đã click 'Add photo' (JS).")
        return True
    except Exception as e:
        print("❌ Không click được 'Add photo' qua JS:", e)
        return False

def _upload_image_via_input(page, image_path: str) -> bool:
    try:
        time.sleep(1)
        loc = page.locator("input[type='file'][accept*='image']")
        if not loc.count():
            loc = page.locator("input[type='file']")
        loc.first.wait_for(state="attached", timeout=10000)
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        loc.first.set_input_files(image_path)
        print(f"✅ Đã upload ảnh: {image_path}")
        return True
    except Exception as e:
        print("❌ Không upload được ảnh:", e)
        try:
            page.screenshot(path="upload_error.png")
            Path("upload_error.html").write_text(page.content(), encoding="utf-8")
        except:
            pass
        return False

def _fill_prompt_quill(page, text: str) -> bool:
    try:
        ok = page.evaluate("""
        (text) => {
          const el = document.querySelector('.ql-editor.textarea.new-input-ui[contenteditable="true"]');
          if (!el) return false;
          el.focus();
          document.execCommand('selectAll', false, null);
          document.execCommand('delete', false, null);
          document.execCommand('insertText', false, text);
          el.dispatchEvent(new InputEvent('input', {bubbles: true}));
          el.dispatchEvent(new Event('change', {bubbles: true}));
          return true;
        }
        """, text)
        if ok:
            print("✅ Đã nhập prompt vào ô mô tả video.")
            return True
        else:
            print("⚠️ Không tìm thấy ô nhập (Quill editor).")
            return False
    except Exception as e:
        print("❌ Lỗi khi nhập prompt:", e)
        return False

def _click_generate(page) -> bool:
    try:
        page.get_by_role("button", name="Generate").click(timeout=10000)
        print("✅ Đã bấm nút Generate.")
        return True
    except Exception:
        try:
            page.locator("button:has-text('Generate')").first.click(timeout=10000)
            print("✅ Đã bấm nút Generate (fallback).")
            return True
        except Exception as e:
            print("⚠️ Không bấm được Generate:", e)
            return False

def _click_send_message(page) -> bool:
    try:
        page.evaluate("""
        (() => {
          const btn = document.querySelector('button[aria-label="Send message"]');
          if (!btn) return false;
          btn.click();
          return true;
        })();
        """)
        print("✅ Đã bấm nút Send message.")
        return True
    except Exception as e:
        print("⚠️ Không bấm được Send message:", e)
        try:
            page.locator('mat-icon[fonticon="send"]').first.evaluate("el => el.closest('button').click()")
            print("✅ Đã bấm nút Send message (fallback icon).")
            return True
        except Exception as e2:
            print("❌ Send message thất bại:", e2)
            return False

def _click_download_button_js(page) -> bool:
    """Click nút Download video bằng JS theo yêu cầu."""
    try:
        ok = page.evaluate("""
        (() => {
          const btn = document.querySelector('button[aria-label="Download video"]')
                   || document.querySelector('mat-icon[fonticon="download"]')?.closest('button');
          if (!btn) return false;
          btn.click();
          return true;
        })();
        """)
        if ok:
            print("✅ Đã bấm nút Download video.")
            return True
        print("⚠️ Chưa thấy nút Download video.")
        return False
    except Exception as e:
        print("⚠️ Lỗi khi click Download video:", e)
        return False

def _download_video_until_success(page, save_dir: str, first_delay_sec: int = 10, interval_sec: int = 120, per_try_timeout_ms: int = 60000) -> None:
    """
    Đợi first_delay_sec (mặc định 10s) sau khi gửi, rồi
    LẶP VÔ HẠN: mỗi interval_sec (mặc định 120s) bấm Download và chờ sự kiện download.
    Khi tải thành công thì kết thúc (return).
    """
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    print(f"[*] Đợi {first_delay_sec}s rồi bắt đầu thử tải...")
    time.sleep(first_delay_sec)

    attempt = 0
    while True:
        attempt += 1
        print(f"[*] Thử tải video (lần {attempt})... (Ctrl+C để dừng)")
        clicked = _click_download_button_js(page)
        if not clicked:
            print(f"⏳ Chưa thấy nút Download. Sẽ thử lại sau {interval_sec} giây...")
            time.sleep(interval_sec)
            continue
        try:
            with page.expect_download(timeout=per_try_timeout_ms) as dl_info:
                pass
            download = dl_info.value  # type: ignore
            sug = download.suggested_filename
            target_path = os.path.join(save_dir, sug if sug else f"video_{int(time.time())}.mp4")
            download.save_as(target_path)
            print(f"✅ Tải xong: {target_path}")
            return
        except PlaywrightTimeout:
            print(f"⏳ Chưa có download (timeout {per_try_timeout_ms} ms). Sẽ thử lại sau {interval_sec} giây...")
            time.sleep(interval_sec)
        except Exception as e:
            print("❌ Lỗi trong quá trình tải:", e)
            time.sleep(interval_sec)

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

        # Cho phép tải file
        context = browser.new_context(
            user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"),
            locale="en-US",
            timezone_id="Asia/Bangkok",
            accept_downloads=True,
        )

        try:
            ok = load_cookies_into_context(context, COOKIE_FILE)
            page = context.new_page()

            target = "https://gemini.google.com/app"
            print("[*] Mở trang:", target)
            page.goto(target, wait_until="domcontentloaded", timeout=120_000)

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

            # 1) Tools
            if not _try_click_tools(page):
                print("⚠️ Không click được Tools. Lưu debug.")
                try:
                    page.screenshot(path="no_click_tools.png")
                    Path("page_no_click_tools.html").write_text(page.content(), encoding="utf-8")
                except: pass
                context.close(); browser.close(); return

            # 2) Veo
            time.sleep(1)
            if not _try_click_create_veo(page):
                print("⚠️ Không click được 'Create videos with Veo'. Lưu debug.")
                try:
                    page.screenshot(path="no_click_veo.png")
                    Path("page_no_click_veo.html").write_text(page.content(), encoding="utf-8")
                except: pass

            time.sleep(2)
            print("Title:", page.title())
            try:
                Path("after_click_veo.html").write_text(page.content(), encoding="utf-8")
            except: pass

            # 3) Add photo + upload
            if _click_add_photo_via_js(page):
                if _upload_image_via_input(page, IMAGE_PATH):
                    # ⬇️ ĐỢI ẢNH THỰC SỰ GẮN VÀO FORM
                    _wait_image_ready(page, max_wait_sec=30)
                    # ⬇️ RỒI ĐỢI THÊM 10 GIÂY NHƯ YÊU CẦU
                    time.sleep(10)

            # 4) Nhập prompt
            _fill_prompt_quill(page, PROMPT_TEXT)
            time.sleep(10)

            # 5) Gửi: ưu tiên Send, nếu không thì Generate
            if AUTO_CLICK_SEND:
                _click_send_message(page)
            elif AUTO_CLICK_GENERATE:
                _click_generate(page)


            # 6) Đợi 10s, rồi lặp 2 phút/lần cho tới khi download thành công
            _download_video_until_success(
                page,
                DOWNLOAD_DIR,
                first_delay_sec=10,
                interval_sec=120,
                per_try_timeout_ms=60000
            )

            time.sleep(2)

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
