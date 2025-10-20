# tools_flow_slate.py
# pip install playwright requests
# python -m playwright install

from pathlib import Path
import os, time, sys, traceback
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ==== CẤU HÌNH ====
COOKIE_FILE   = r"C:\Users\BHMedia-PC\UI_make_video_AI\cookies.json"   # Netscape cookies
TARGET_URL    = "https://hailuoai.video/create/image-to-video"
IMAGE_PATH    = r"C:\Users\BHMedia-PC\UI_make_video_AI\tx02.webp"      # file ảnh cần upload
PROMPT_TEXT   = "tạo video quảng cáo túi sách"                          # prompt cần nhập
DOWNLOAD_DIR  = r"C:\Users\BHMedia-PC\UI_make_video_AI\downloads"       # thư mục lưu video
TYPE_SPEED_MS = 50                                                      # tốc độ gõ (ms/ký tự)
STEP_DELAY_S  = 5                                                       # delay giữa các giai đoạn

AUTO_TRY_DOWNLOAD      = True     # Bật/tắt khối auto tải video
FIRST_DELAY_BEFORE_DL  = 10       # đợi lần đầu trước khi thử bấm Download (giây)
RETRY_INTERVAL_SEC     = 120      # lặp lại mỗi 2 phút
PER_TRY_TIMEOUT_MS     = 60_000   # timeout cho mỗi lần expect_download

# ==== HÀM TIỆN ÍCH COOKIE ====
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

# ==== HÀM: CLICK THEO SELECTOR BẰNG JS ====
def click_by_js(page, selector: str) -> bool:
    try:
        ok = page.evaluate("""
        (sel) => {
          const el = document.querySelector(sel);
          if (!el) return false;
          el.scrollIntoView({block:'center'});
          el.click();
          return true;
        }
        """, selector)
        if ok: print(f"✅ Click JS thành công: {selector}")
        else:  print(f"⚠️ Không tìm thấy selector: {selector}")
        return bool(ok)
    except Exception as e:
        print(f"❌ Lỗi click JS ({selector}):", e)
        return False

# ==== HÀM: UPLOAD FILE (ổn định) ====
def upload_file_via_input(page, file_path: str) -> bool:
    try:
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"Không thấy file: {file_path}")

        # 1) Thử set_input_files trực tiếp (ổn nhất)
        try:
            loc = page.locator("input[type='file'][accept*='image']").first
            loc.wait_for(state="attached", timeout=5000)
            loc.set_input_files(file_path)
            print(f"✅ set_input_files vào input[accept*='image']: {file_path}")
            return True
        except Exception:
            pass

        try:
            inputs = page.locator("input[type='file']")
            inputs.first.wait_for(state="attached", timeout=5000)
            inputs.first.set_input_files(file_path)
            print(f"✅ set_input_files vào input[type=file] đầu tiên: {file_path}")
            return True
        except Exception:
            pass

        # 2) Nếu chưa được, bắt file chooser rồi click trigger
        try:
            with page.expect_file_chooser(timeout=15000) as fc_info:
                click_by_js(page, "button:has-text('Upload')") or \
                click_by_js(page, "[data-testid='upload-trigger']") or \
                click_by_js(page, "label[for*='upload']") or \
                click_by_js(page, "div.group\\/upload-history-list")
            fc = fc_info.value
            fc.set_files(file_path)
            print(f"✅ Upload qua file chooser: {file_path}")
            return True
        except PlaywrightTimeout:
            print("⚠️ Không bắt được file chooser.")
            return False

    except Exception as e:
        print("❌ Không upload được file:", e)
        try:
            page.screenshot(path="upload_error.png")
            Path("upload_error.html").write_text(page.content(), encoding="utf-8")
        except: pass
        return False

# ==== HÀM: GÕ PROMPT VÀO SLATE BẰNG “BÀN PHÍM” ====
def type_prompt_into_slate(page, prompt: str, per_char_ms: int = 50) -> bool:
    try:
        # Ưu tiên đúng dấu hiệu Slate
        editor = page.locator('div[contenteditable="true"][data-slate-editor="true"]')
        editor.first.wait_for(state="visible", timeout=15000)
        editor.first.click()
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        page.keyboard.type(prompt, delay=per_char_ms)
        print("✅ Đã gõ prompt vào Slate editor (keyboard.type).")
        return True
    except PlaywrightTimeout:
        print("⚠️ Không thấy editor Slate, thử fallback contenteditable.")
        try:
            editor2 = page.locator('div[contenteditable="true"]')
            editor2.first.wait_for(state="visible", timeout=8000)
            editor2.first.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            page.keyboard.type(prompt, delay=per_char_ms)
            print("✅ Fallback: gõ prompt vào contenteditable.")
            return True
        except Exception as e:
            print("❌ Fallback cũng lỗi:", e)
            try:
                page.screenshot(path="prompt_error.png")
                Path("prompt_error.html").write_text(page.content(), encoding="utf-8")
            except: pass
            return False
    except Exception as e:
        print("❌ Lỗi khi gõ prompt Slate (keyboard):", e)
        try:
            page.screenshot(path="prompt_error.png")
            Path("prompt_error.html").write_text(page.content(), encoding="utf-8")
        except: pass
        return False

# ==== HÀM: BẤM NÚT GỬI (linh hoạt) ====
def click_send_button(page) -> bool:
    selectors = [
        "button.new-color-btn-bg",
        "button:has-text('Create')",
        "button:has-text('Generate')",
        "button:has-text('Recreate')",
        "button[type='submit']",
    ]
    for sel in selectors:
        try:
            btn = page.locator(sel)
            if btn.count() > 0:
                btn.first.scroll_into_view_if_needed()
                btn.first.click()
                print(f"✅ Đã bấm nút gửi: {sel}")
                return True
        except Exception:
            pass
    print("⚠️ Không tìm thấy nút gửi qua các selector dự phòng.")
    return False

# ==== HÀM: CLICK NÚT TRONG .mt-3 ĐẦU TIÊN CỦA THẺ ĐẦU TIÊN ====
def click_download_button_in_first_mt3(page) -> bool:
    """
    - Lấy thẻ card đầu tiên trong container preview
    - Tìm .mt-3 đầu tiên (khối 3 nút)
    - Click nút ant-dropdown-trigger phù hợp (ưu tiên SVG path bạn cung cấp)
    """
    try:
        # Card đầu tiên trong danh sách video
        card = page.locator("#preview-video-scroll-container > div:nth-child(1) > div").first
        card.wait_for(state="visible", timeout=15000)

        # .mt-3 đầu tiên bên phải (khối chứa các button)
        mt3 = card.locator(".mt-3").first
        mt3.wait_for(state="visible", timeout=8000)

        # Ưu tiên đúng nút theo SVG path bạn đã dán (mũi tên/box icon)
        # Nếu selector này không match, sẽ fallback sang ant-dropdown-trigger đầu tiên
        btn_svg_specific = mt3.locator(
            "button.ant-dropdown-trigger:has(svg path[d^='M2 9.26074'])"
        )

        if btn_svg_specific.count() > 0:
            btn_svg_specific.first.scroll_into_view_if_needed()
            btn_svg_specific.first.click()
            print("✅ Click nút ant-dropdown-trigger (match SVG path).")
            return True

        # Fallback: lấy button.ant-dropdown-trigger đầu tiên
        btn_any = mt3.locator("button.ant-dropdown-trigger").first
        if btn_any.count() > 0:
            btn_any.scroll_into_view_if_needed()
            btn_any.click()
            print("✅ Click nút ant-dropdown-trigger (fallback nút đầu tiên).")
            return True

        print("⚠️ Không tìm thấy button.ant-dropdown-trigger trong .mt-3 đầu tiên.")
        return False

    except Exception as e:
        print("❌ Lỗi khi click nút trong .mt-3:", e)
        return False

# ==== HÀM: TẢI VIDEO (dựa trên nút trong .mt-3) ====
def download_video_until_success(page,
                                 save_dir: str,
                                 first_delay_sec: int = 10,
                                 interval_sec: int = 120,
                                 per_try_timeout_ms: int = 60000):
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    print(f"[*] Đợi {first_delay_sec}s trước khi thử tải...")
    time.sleep(first_delay_sec)
    attempt = 0
    while True:
        attempt += 1
        print(f"[*] Thử tải (lần {attempt})...")

        try:
            # Đặt expect_download TRƯỚC khi click
            with page.expect_download(timeout=per_try_timeout_ms) as dl_info:
                clicked = click_download_button_in_first_mt3(page)
                if not clicked:
                    raise PlaywrightTimeout("Không click được nút download trong .mt-3")
            download = dl_info.value  # type: ignore
            sug = download.suggested_filename
            target_path = os.path.join(save_dir, sug if sug else f"video_{int(time.time())}.mp4")
            download.save_as(target_path)
            print(f"✅ Tải thành công: {target_path}")
            return
        except PlaywrightTimeout:
            print(f"⏳ Chưa có file tải về trong {per_try_timeout_ms}ms. Thử lại sau {interval_sec}s...")
            time.sleep(interval_sec)
        except Exception as e:
            print("❌ Lỗi khi tải:", e)
            time.sleep(interval_sec)

# ==== LUỒNG CHÍNH ====
def run_flow():
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

        page = None
        try:
            load_cookies_into_context(context, COOKIE_FILE)
            page = context.new_page()

            print("[*] Mở:", TARGET_URL)
            page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_load_state("load", timeout=60_000)
            time.sleep(3)

            # Nếu bị đá sang login
            if "accounts.google.com" in page.url or "signin" in page.url:
                print("⚠️ Cookie không hợp lệ → bị chuyển trang đăng nhập.")
                try:
                    page.screenshot(path="redirect_login.png")
                    Path("redirect_login.html").write_text(page.content(), encoding="utf-8")
                except: pass
                return

            # === UPLOAD ẢNH ===
            if not upload_file_via_input(page, IMAGE_PATH):
                print("❌ Upload thất bại. Dừng flow.")
                return
            time.sleep(STEP_DELAY_S)

            # Có thể đợi preview/thumbnail một chút
            try:
                page.wait_for_selector("video, img.custom-video-cover, .group/web-video-player, .ant-progress", timeout=15000)
            except Exception:
                pass

            # === NHẬP PROMPT ===
            if not type_prompt_into_slate(page, PROMPT_TEXT, per_char_ms=TYPE_SPEED_MS):
                print("❌ Gõ prompt thất bại. Dừng flow.")
                return
            time.sleep(STEP_DELAY_S)

            # === GỬI ===
            click_send_button(page)

            # === DOWNLOAD TỪ .mt-3 ===
            if AUTO_TRY_DOWNLOAD:
                download_video_until_success(
                    page,
                    DOWNLOAD_DIR,
                    first_delay_sec=FIRST_DELAY_BEFORE_DL,
                    interval_sec=RETRY_INTERVAL_SEC,
                    per_try_timeout_ms=PER_TRY_TIMEOUT_MS
                )

        except Exception as e:
            print("❌ Lỗi runtime:", e)
            traceback.print_exc()
            try:
                if page:
                    page.screenshot(path="runtime_error.png")
                    Path("runtime_error.html").write_text(page.content(), encoding="utf-8")
            except: pass
        finally:
            try: context.close()
            except: pass
            try: browser.close()
            except: pass

if __name__ == "__main__":
    run_flow()
