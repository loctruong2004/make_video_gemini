# click_tools.py
# pip install playwright requests
# python -m playwright install

from pathlib import Path
import os
import time, sys, traceback
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ====== CẤU HÌNH ======
COOKIE_FILE   = r"C:\Users\BHMedia-PC\UI_make_video_AI\cookies.json"   # Netscape cookies
TARGET_URL    = "https://gemini.google.com/app"
IMAGE_PATH    = r"C:\Users\BHMedia-PC\UI_make_video_AI\tx02.webp"      # file ảnh cần upload
PROMPT_TEXT   = "tạo video quảng cáo túi sách"                          # prompt cần nhập

AUTO_CLICK_SEND     = True     # Gửi bằng "Send message"
AUTO_CLICK_GENERATE = False    # Hoặc bấm "Generate" (đặt True nếu muốn)

# Thư mục lưu video tải về
DOWNLOAD_DIR  = r"C:\Users\BHMedia-PC\UI_make_video_AI\downloads"

# Thời gian đợi & retry
FIRST_DOWNLOAD_DELAY_SEC = 10      # đợi trước lần thử tải đầu tiên
RETRY_INTERVAL_SEC       = 120     # khoảng cách giữa các lần thử tải
PER_TRY_TIMEOUT_MS       = 60_000  # timeout chờ event download mỗi lần thử


# ====== HÀM TIỆN ÍCH COOKIE ======
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
        secure = str(secure_flag).upper() == "TRUE"
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


# ====== HÀM TRỢ GIÚP UI ======
def wait_image_attached(page, max_wait_sec: int = 30) -> bool:
    """Đợi input[type=file] có file (xác nhận ảnh đã attach)."""
    start = time.time()
    while time.time() - start < max_wait_sec:
        try:
            has_file = page.evaluate(
                """() => {
                    const inp = document.querySelector('input[type="file"]');
                    if (!inp) return false;
                    const f = inp.files;
                    return !!(f && f.length > 0);
                }"""
            )
            if has_file:
                print("✅ Ảnh đã được gắn vào input.")
                return True
        except Exception:
            pass
        time.sleep(1)
    print(f"⚠️ Hết {max_wait_sec}s vẫn chưa xác nhận ảnh gắn vào input.")
    return False


def try_click_tools(page) -> bool:
    """Mở panel Tools."""
    try:
        page.get_by_role("button", name="Tools").click(timeout=15_000)
        print("✅ Click Tools (role).")
        return True
    except Exception:
        pass
    try:
        page.click("button.toolbox-drawer-button:has-text('Tools')", timeout=15_000)
        print("✅ Click Tools (CSS).")
        return True
    except Exception:
        pass
    try:
        icon = page.locator("mat-icon[fonticon='page_info']").first
        if icon.count() > 0:
            btn = icon.evaluate_handle("el => el.closest('button')")
            if btn:
                page.evaluate("(el)=>el.scrollIntoView({block:'center'})", btn)
                page.evaluate("(el)=>el.click()", btn)
                print("✅ Click Tools (icon).")
                return True
    except Exception as e:
        print("[!] Lỗi click Tools:", e)
    return False


def try_click_create_veo(page) -> bool:
    """Click 'Create videos with Veo'."""
    try:
        page.get_by_role("button", name="Create videos with Veo").click(timeout=15_000)
        print("✅ Click 'Create videos with Veo' (role).")
        return True
    except Exception:
        pass
    try:
        page.click("button:has-text('Create videos with Veo')", timeout=15_000)
        print("✅ Click 'Create videos with Veo' (CSS).")
        return True
    except Exception:
        pass
    try:
        icon = page.locator("mat-icon[fonticon='movie']").first
        if icon.count():
            btn = icon.evaluate_handle("el => el.closest('button')")
            if btn:
                page.evaluate("(el)=>el.scrollIntoView({block:'center'})", btn)
                page.evaluate("(el)=>el.click()", btn)
                print("✅ Click 'Create videos with Veo' (icon).")
                return True
    except Exception as e:
        print("❌ Không click được 'Create videos with Veo':", e)
    return False


def click_add_photo(page) -> bool:
    """Click 'Add photo' bằng JS (ổn hơn trên giao diện Angular/Material)."""
    try:
        ok = page.evaluate("""
        (() => {
          const btn = document.querySelector("mat-icon[fonticon='add_photo_alternate']")?.closest("button");
          if (!btn) return false;
          btn.click();
          return true;
        })();
        """)
        if ok:
            print("✅ Đã click 'Add photo'.")
            return True
    except Exception as e:
        print("❌ Không click được 'Add photo':", e)
    return False


def upload_image_via_input(page, image_path: str) -> bool:
    """Gán file ảnh vào input[type=file]."""
    try:
        time.sleep(1)
        loc = page.locator("input[type='file'][accept*='image']").first
        if not loc.count():
            loc = page.locator("input[type='file']").first
        loc.wait_for(state="attached", timeout=10_000)
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Image not found: {image_path}")
        loc.set_input_files(image_path)
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


def fill_prompt_quill(page, text: str) -> bool:
    """Nhập prompt vào editor Quill."""
    try:
        ok = page.evaluate(
            """
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
            """,
            text,
        )
        if ok:
            print("✅ Đã nhập prompt vào ô mô tả video.")
            return True
        print("⚠️ Không tìm thấy ô nhập (Quill editor).")
        return False
    except Exception as e:
        print("❌ Lỗi khi nhập prompt:", e)
        return False


def click_generate(page) -> bool:
    """Bấm nút Generate."""
    try:
        page.get_by_role("button", name="Generate").click(timeout=10_000)
        print("✅ Đã bấm nút Generate.")
        return True
    except Exception:
        try:
            page.locator("button:has-text('Generate')").first.click(timeout=10_000)
            print("✅ Đã bấm nút Generate (fallback).")
            return True
        except Exception as e:
            print("⚠️ Không bấm được Generate:", e)
            return False


def click_send_message(page) -> bool:
    """Bấm nút Send message."""
    try:
        ok = page.evaluate("""
        (() => {
          const btn = document.querySelector('button[aria-label="Send message"]');
          if (!btn) return false;
          btn.click();
          return true;
        })();
        """)
        if ok:
            print("✅ Đã bấm nút Send message.")
            return True
    except Exception:
        pass
    # fallback icon
    try:
        page.locator('mat-icon[fonticon="send"]').first.evaluate("el => el.closest('button').click()")
        print("✅ Đã bấm nút Send message (fallback icon).")
        return True
    except Exception as e2:
        print("❌ Send message thất bại:", e2)
        return False


# ====== DOWNLOAD: tìm nút, hover rồi click trong expect_download ======
def get_download_btn(page):
    """Trả về locator của nút Download (ưu tiên aria-label, fallback theo icon)."""
    sel = (
        'button[aria-label="Download video"].download-button, '
        'button.download-button:has(.mat-icon[data-mat-icon-name="download"]), '
        'button.download-button:has(.mat-icon[fonticon="download"])'
    )
    return page.locator(sel).first


def download_video_until_success(page,
                                 save_dir: str,
                                 first_delay_sec: int = FIRST_DOWNLOAD_DELAY_SEC,
                                 interval_sec: int = RETRY_INTERVAL_SEC,
                                 per_try_timeout_ms: int = PER_TRY_TIMEOUT_MS) -> str:
    """
    Lặp đến khi tải về thành công:
      - Đợi first_delay_sec trước lần thử đầu.
      - Mỗi lần thử: tìm nút download → scroll + hover → expect_download TRƯỚC → click.
      - Nếu hết per_try_timeout_ms mà không có file, ngủ interval_sec rồi thử lại.
    Trả về đường dẫn file đã lưu.
    """
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    print(f"[*] Đợi {first_delay_sec}s rồi bắt đầu thử tải...")
    time.sleep(first_delay_sec)

    attempt = 0
    while True:
        attempt += 1
        print(f"[*] Thử tải video (lần {attempt})... (Ctrl+C để dừng)")

        btn = get_download_btn(page)
        try:
            btn.wait_for(state="visible", timeout=10_000)
        except Exception:
            print(f"⏳ Chưa thấy nút Download. Thử lại sau {interval_sec}s...")
            time.sleep(interval_sec)
            continue

        # Hover trước để unlock
        try:
            btn.scroll_into_view_if_needed(timeout=5_000)
            btn.hover(timeout=5_000)
        except Exception:
            pass  # đôi khi không cần hover

        try:
            # expect_download PHẢI TRƯỚC khi click
            with page.expect_download(timeout=per_try_timeout_ms) as dl_info:
                btn.click(timeout=10_000)
            download = dl_info.value  # type: ignore

            # Gợi ý tên file & nơi lưu
            sug = (download.suggested_filename or "").strip()
            fname = sug if sug else f"video_{int(time.time())}.mp4"
            target_path = os.path.join(save_dir, fname)

            # (tuỳ chọn) in ra đường dẫn tạm
            try:
                tmp_path = download.path()
                if tmp_path:
                    print(f"    • File tạm: {tmp_path}")
            except Exception:
                pass

            # Lưu file về thư mục bạn chọn
            download.save_as(target_path)
            print(f"✅ Tải xong: {target_path}")
            return target_path

        except PlaywrightTimeout:
            print(f"⏳ Hết {per_try_timeout_ms}ms chưa có sự kiện download. Thử lại sau {interval_sec}s...")
            time.sleep(interval_sec)

        except Exception as e:
            print("❌ Lỗi trong quá trình tải:", e)
            time.sleep(interval_sec)


# ====== LUỒNG CHÍNH ======
def click_tools_flow():
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
            accept_downloads=True,
        )

        try:
            _ = load_cookies_into_context(context, COOKIE_FILE)
            page = context.new_page()

            print("[*] Mở trang:", TARGET_URL)
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_load_state("load", timeout=60_000)
            time.sleep(5)

            if "accounts.google.com" in page.url or "signin" in page.url:
                print("⚠️ Cookie/phiên không hợp lệ → bị chuyển sang trang đăng nhập.")
                try:
                    page.screenshot(path="redirect_login.png")
                    Path("redirect_page.html").write_text(page.content(), encoding="utf-8")
                except:
                    pass
                return

            # 1) Mở Tools
            if not try_click_tools(page):
                print("⚠️ Không click được Tools.")
                try:
                    page.screenshot(path="no_click_tools.png")
                    Path("page_no_click_tools.html").write_text(page.content(), encoding="utf-8")
                except: pass
                return

            # 2) Chọn Veo
            time.sleep(1)
            if not try_click_create_veo(page):
                print("⚠️ Không click được 'Create videos with Veo'.")
                try:
                    page.screenshot(path="no_click_veo.png")
                    Path("page_no_click_veo.html").write_text(page.content(), encoding="utf-8")
                except: pass

            time.sleep(2)
            try:
                Path("after_click_veo.html").write_text(page.content(), encoding="utf-8")
            except: pass

            # 3) Add photo + upload
            # if click_add_photo(page):
            if upload_image_via_input(page, IMAGE_PATH):
                # Đợi ảnh attach thật sự
                wait_image_attached(page, max_wait_sec=30)
                # Đợi thêm cho UI xử lý
                time.sleep(10)

            # 4) Nhập prompt
            fill_prompt_quill(page, PROMPT_TEXT)
            time.sleep(10)

            # 5) Gửi: ưu tiên Send, nếu không thì Generate
            if AUTO_CLICK_SEND:
                click_send_message(page)
            elif AUTO_CLICK_GENERATE:
                click_generate(page)

            # 6) Đợi & tải
            path_saved = download_video_until_success(
                page,
                DOWNLOAD_DIR,
                first_delay_sec=FIRST_DOWNLOAD_DELAY_SEC,
                interval_sec=RETRY_INTERVAL_SEC,
                per_try_timeout_ms=PER_TRY_TIMEOUT_MS
            )
            print(">>> File đã lưu:", path_saved)

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
