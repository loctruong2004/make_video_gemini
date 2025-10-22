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

# ==== PHÁT HIỆN TRẠNG THÁI GENERATION ====
def is_generation_running(page) -> bool:
    """
    Đang tạo khi:
      - Có thẻ chứa text 'Cancel generation' còn hiển thị, hoặc
      - Có progress tạo (class .creating-progress), hoặc
      - Có message 'Content generation in progress'
    """
    try:
        # 1) Nút Cancel
        cancel = page.locator("div:has-text('Cancel generation')").first
        if cancel.count() > 0 and cancel.is_visible():
            return True

        # 2) Progress tròn
        if page.locator(".creating-progress").count() > 0:
            return True

        # 3) Thông báo đang tạo
        if page.locator("div:has-text('Content generation in progress')").count() > 0:
            return True
    except Exception:
        pass
    return False


def wait_until_ready(page, max_wait_sec: int = 900, poll_sec: float = 3.0) -> None:
    """
    Đợi cho tới khi KHÔNG còn trạng thái 'đang tạo'.
    Hết thời gian thì thoát vòng lặp (vẫn tiếp tục flow tải thử).
    """
    deadline = time.time() + max_wait_sec
    while time.time() < deadline:
        if not is_generation_running(page):
            print("✅ Không còn đang generate — tiếp tục tải.")
            return
        remaining = int(deadline - time.time())
        print(f"⏳ Đang generate... chờ {poll_sec}s (còn ~{remaining}s)")
        time.sleep(poll_sec)
    print("⚠️ Hết thời gian chờ, vẫn thấy đang tạo. Sẽ thử tải video sẵn có (nếu có).")

def get_first_ready_video_url(page) -> str | None:
   
    return page.evaluate(
        """
        () => {
          // Tìm tất cả thẻ có class chứa 'video-card'
          const cards = Array.from(document.querySelectorAll('[class*="video-card"]'));
          for (const card of cards) {
            // Bỏ qua card đang tạo
            if (card.querySelector('.creating-progress')) continue;
            // Tìm video hợp lệ
            const v = card.querySelector('video');
            if (v && (v.currentSrc || v.src)) {
              return v.currentSrc || v.src;
            }
          }
          return null;
        }
        """
    )
def download_ready_video_like_console(
    page,
    save_dir: str,
    container_selector: str = 'div.flex.flex-col.items-center',
    first_delay_sec: int = 10,
    retry_interval_sec: int = 30,
    per_try_timeout_ms: int = 60_000,
) -> str:
    """
    Lặp cho đến khi KHÔNG còn video đang tạo thì tải video đầu tiên.
    Trả về đường dẫn file đã tải khi thành công.
    """

    Path(save_dir).mkdir(parents=True, exist_ok=True)
    attempt = 0

    def has_generating() -> bool:
        try:
            if page.locator("div:has-text('Cancel generation')").count() > 0:
                return True
            if page.locator(".creating-progress").count() > 0:
                return True
            if page.locator("div:has-text('Content generation in progress')").count() > 0:
                return True
        except Exception:
            pass
        return False

    # delay đầu tiên
    print(f"[*] Chờ {first_delay_sec}s trước khi bắt đầu kiểm tra video...")
    time.sleep(first_delay_sec)

    while True:
        attempt += 1
        print(f"\n=== 🔁 Lần thử {attempt} ===")

        if has_generating():
            print("⏳ Đang có video đang tạo → đợi thêm trước khi retry...")
            time.sleep(retry_interval_sec)
            continue

        # Không có video đang tạo → thử lấy URL video đầu tiên
        video_url = page.evaluate(
            """
            () => {
              const cards = Array.from(document.querySelectorAll('[class*="video-card"]'));
              for (const card of cards) {
                // Bỏ qua card đang tạo
                if (card.querySelector('.creating-progress')) continue;
                const v = card.querySelector('video');
                if (v && (v.currentSrc || v.src)) {
                  return v.currentSrc || v.src;
                }
              }
              return null;
            }
            """
        )

        if not video_url:
            print("⚠️ Không tìm thấy video sẵn sàng để tải, thử lại sau...")
            time.sleep(retry_interval_sec)
            continue

        print(f"🎯 Tìm thấy video URL: {video_url}")

        try:
            # Thử tải bằng anchor như console
            with page.expect_download(timeout=per_try_timeout_ms) as dl_info:
                ok = page.evaluate(
                    """(url) => {
                        const a = document.createElement('a');
                        a.href = url;
                        a.download = 'video.mp4';
                        document.body.appendChild(a);
                        a.click();
                        a.remove();
                        return true;
                    }""",
                    video_url,
                )
                if not ok:
                    raise RuntimeError("Không thể kích hoạt download bằng anchor.")

            download = dl_info.value  # type: ignore
            fname = download.suggested_filename or f"video_{int(time.time())}.mp4"
            target_path = os.path.join(save_dir, fname)
            download.save_as(target_path)
            print(f"✅ Đã tải thành công: {target_path}")
            return target_path

        except Exception as e:
            print("❌ Lỗi khi tải:", e)
            time.sleep(retry_interval_sec)


def download_video_until_success(page,
                                 save_dir: str,
                                 first_delay_sec: int = 10,
                                 interval_sec: int = 120,
                                 per_try_timeout_ms: int = 60_000):
    """
    Lặp đến khi tải về thành công:
      - Đợi first_delay_sec giây trước lần thử đầu.
      - Mỗi lần thử: đặt expect_download TRƯỚC khi click nút download.
      - Nếu hết per_try_timeout_ms mà không có file, ngủ interval_sec rồi thử lại.
    """
    Path(save_dir).mkdir(parents=True, exist_ok=True)
    print(f"[*] Đợi {first_delay_sec}s trước khi thử tải...")
    time.sleep(first_delay_sec)

    attempt = 0
    while True:
        attempt += 1
        print(f"[*] Thử tải (lần {attempt})...")

        try:
            # expect_download phải được đặt TRƯỚC khi click
            with page.expect_download(timeout=per_try_timeout_ms) as dl_info:
                clicked = click_download_button_in_first_mt3(page)
                if not clicked:
                    raise PlaywrightTimeout("Không click được nút download trong .mt-3")

            download = dl_info.value  # type: ignore
            sug = download.suggested_filename
            fname = sug if (sug and sug.strip()) else f"video_{int(time.time())}.mp4"
            target_path = os.path.join(save_dir, fname)

            # Lưu file
            download.save_as(target_path)
            print(f"✅ Tải thành công: {target_path}")
            return

        except PlaywrightTimeout:
            print(f"⏳ Chưa có file tải về trong {per_try_timeout_ms}ms. Thử lại sau {interval_sec}s...")
            time.sleep(interval_sec)

        except Exception as e:
            print("❌ Lỗi khi tải:", e)
            time.sleep(interval_sec)
# ==== CHỜ HẾT QUÁ TRÌNH GENERATION (không còn nút "Cancel generation") ====
def wait_until_generation_finished(page, max_wait_sec: int = 900, poll_sec: float = 5.0) -> bool:
    """
    Trả về True nếu KHÔNG còn nút 'Cancel generation' (đã xong hoặc không xuất hiện),
    False nếu hết thời gian chờ mà nút vẫn còn hiển thị.
    """
    sel = "div:has-text('Cancel generation')"  # bền hơn là match text thay vì full class
    deadline = time.time() + max_wait_sec

    while time.time() < deadline:
        try:
            loc = page.locator(sel).first
            # nếu không tồn tại hoặc không hiển thị => coi như đã xong
            if loc.count() == 0:
                print("✅ Không có nút 'Cancel generation' (không xuất hiện).")
                return True
            if not loc.is_visible():
                print("✅ Nút 'Cancel generation' không còn hiển thị.")
                return True

            # đang hiển thị => vẫn đang generate
            print("⏳ Đang generate... đợi tiếp", f"({int(deadline - time.time())}s còn lại)")
            time.sleep(poll_sec)

        except Exception:
            # Nếu có lỗi tạm thời DOM, coi như đã xong để không kẹt
            print("ℹ️ Không đọc được trạng thái nút, thử tải tiếp.")
            return True

    print("⚠️ Hết thời gian chờ, vẫn thấy 'Cancel generation'. Sẽ thử tải dù vậy.")
    return False

# ==== CLICK NÚT "ant-tour-close" (nếu có) ====
def click_tour_close_button(page, retries: int = 3, delay_sec: float = 1.5) -> bool:
    """
    Tự động click nút hướng dẫn (nút có class 'ant-tour-close') nếu có hiển thị.
    Thử tối đa `retries` lần, mỗi lần cách nhau `delay_sec` giây.
    Trả về True nếu click được ít nhất một lần.
    """
    for i in range(retries):
        try:
            # Dò xem có nút close không
            btn = page.locator("button.ant-tour-close").first
            if btn.count() > 0 and btn.is_visible():
                btn.scroll_into_view_if_needed()
                btn.click(timeout=3000)
                print("✅ Đã click nút hướng dẫn (ant-tour-close).")
                return True
            else:
                print(f"⏳ Lần {i+1}: chưa thấy nút ant-tour-close, đợi {delay_sec}s...")
                time.sleep(delay_sec)
        except Exception as e:
            print(f"⚠️ Lỗi khi thử click ant-tour-close (lần {i+1}):", e)
            time.sleep(delay_sec)
    print("ℹ️ Không tìm thấy nút ant-tour-close sau khi thử nhiều lần.")
    return False

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

            # === ĐÓNG POPUP TOUR (nếu có) ===
            click_tour_close_button(page)

            # === CLICK NÚT MŨI TÊN MỞ DROPDOWN CHỌN MODEL ===
            try:
                page.evaluate("""
                (() => {
                  const span = document.querySelector('span.hover\\\\:bg-hl_bg_00_4.cursor-pointer.content-end.rounded-lg.p-2.text-transparent.transition-all.hover\\\\:scale-110');
                  if (span) {
                    span.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    span.click();
                    console.log('✅ Đã click mũi tên mở dropdown model.');
                  } else {
                    console.warn('⚠️ Không tìm thấy span mũi tên dropdown.');
                  }
                })();
                """)
                print("✅ Đã click mũi tên mở dropdown model.")
                time.sleep(2)
            except Exception as e:
                print("⚠️ Lỗi khi click mũi tên dropdown:", e)

            # === CLICK CHỌN MODEL “Hailuo 01” ===
            try:
                page.evaluate("""
                (() => {
                  const divs = document.querySelectorAll('div.hover\\\\:border-hl_bg_00_75.flex.h-\\\\[40px\\\\].cursor-pointer');
                  for (const div of divs) {
                    if (div.innerText.includes('Hailuo 01')) {
                      div.scrollIntoView({ behavior: 'smooth', block: 'center' });
                      div.click();
                      console.log('✅ Đã click vào thẻ chứa Hailuo 01');
                      return;
                    }
                  }
                  console.warn('⚠️ Không tìm thấy thẻ chứa "Hailuo 01"');
                })();
                """)
                print("✅ Đã click chọn Hailuo 01.")
                time.sleep(2)
            except Exception as e:
                print("⚠️ Lỗi khi click Hailuo 01:", e)

            # === CLICK CHỌN MODEL CON “Base image-to-video model in 01 series” ===
            try:
                page.evaluate("""
                (() => {
                  const divs = document.querySelectorAll('div.ant-typography.ant-typography-ellipsis.ant-typography-ellipsis-multiple-line.text-hl_text_02');
                  for (const div of divs) {
                    if (div.innerText.trim().includes('Base image-to-video model in 01 series')) {
                      div.scrollIntoView({ behavior: 'smooth', block: 'center' });
                      div.click();
                      console.log('✅ Đã click vào thẻ chứa: "Base image-to-video model in 01 series"');
                      return;
                    }
                  }
                  console.warn('⚠️ Không tìm thấy thẻ cần click');
                })();
                """)
                print("✅ Đã click chọn Base image-to-video model in 01 series.")
                time.sleep(2)
            except Exception as e:
                print("⚠️ Lỗi khi click Base image-to-video model:", e)

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

            # === TỰ ĐỘNG TẢI (lặp đến khi tải được video đầu tiên) ===
            if AUTO_TRY_DOWNLOAD:
                saved_path = download_ready_video_like_console(
                    page,
                    save_dir=DOWNLOAD_DIR,
                    container_selector='div.flex.flex-col.items-center',
                    first_delay_sec=10,
                    retry_interval_sec=30,      # đợi 30s giữa mỗi lần kiểm tra
                    per_try_timeout_ms=PER_TRY_TIMEOUT_MS
                )
                print("[RESULT] File đã lưu:", saved_path)

        except Exception as e:
            print("❌ Lỗi runtime:", e)
            traceback.print_exc()
            try:
                if page:
                    page.screenshot(path="runtime_error.png")
                    Path("runtime_error.html").write_text(page.content(), encoding="utf-8")
            except:
                pass
        finally:
            try:
                context.close()
            except:
                pass
            try:
                browser.close()
            except:
                pass


if __name__ == "__main__":
    run_flow()
