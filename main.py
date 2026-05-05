import os
import json
import re
import time
import random
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import gspread
from google.oauth2.service_account import Credentials
from playwright.sync_api import sync_playwright


# ==========================================
# 1. 구글 시트 인증
# ==========================================
secrets = os.environ.get("GOOGLE_CREDENTIALS")
creds_dict = json.loads(secrets)

creds = Credentials.from_service_account_info(creds_dict, scopes=[
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
])

client = gspread.authorize(creds)
sheet = client.open("올리브영 실시간 금액 관리").sheet1


# ==========================================
# 2. URL 정리 함수
# ==========================================
def clean_oliveyoung_url(url):
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        goods_no = params.get("goodsNo", [""])[0]

        if goods_no:
            return f"https://www.oliveyoung.co.kr/store/goods/getGoodsDetail.do?goodsNo={goods_no}"
    except Exception:
        pass

    return url.strip()


# ==========================================
# 3. HTML 안 JSON 데이터 추출 함수
# ==========================================
def extract_product_data(html):
    title_patterns = [
        r'\\"goodsName\\":\\"(.*?)\\"',
        r'"goodsName":"(.*?)"'
    ]

    title = "상품명 없음"
    for pattern in title_patterns:
        match = re.search(pattern, html)
        if match:
            title = match.group(1)
            title = title.replace('\\"', '"').replace("\\/", "/")
            break

    price_patterns = [
        r'\\"finalPrice\\":(\d+)',
        r'"finalPrice":(\d+)',
        r'\\"salePrice\\":(\d+)',
        r'"salePrice":(\d+)'
    ]

    price = 0
    for pattern in price_patterns:
        match = re.search(pattern, html)
        if match:
            price = int(match.group(1))
            break

    sold_out = (
        '\\"soldOutFlag\\":true' in html
        or '"soldOutFlag":true' in html
    )

    status = "품절" if sold_out else "판매중"

    if title == "상품명 없음" or price == 0:
        return "에러(파싱실패)", 0, "에러"

    return title, price, status


# ==========================================
# 4. 가격 변동 계산
# ==========================================
def calculate_change(current_price, previous_price):
    diff = current_price - previous_price

    if diff > 0:
        mark = "▲"
    elif diff < 0:
        mark = "▼"
    else:
        mark = "-"

    return diff, mark


# ==========================================
# 5. Playwright 크롤링 함수
# ==========================================
def crawl_with_browser(page, url):
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(random.uniform(3, 5))

        html = page.content()

        blocked_keywords = [
            "Access Denied",
            "Forbidden",
            "captcha",
            "비정상",
            "차단",
            "보안",
            "robot",
            "bot"
        ]

        if any(keyword.lower() in html.lower() for keyword in blocked_keywords):
            return "에러(차단감지)", 0, "에러"

        title, price, status = extract_product_data(html)

        if price == 0 or "에러" in status:
            print("⚠️ 파싱 실패. HTML 앞부분:")
            print(html[:700])

        return title, price, status

    except Exception as e:
        print(f"⚠️ 브라우저 크롤링 실패: {url} / {e}")
        return "에러(브라우저실패)", 0, "에러"


# ==========================================
# 6. 메인 실행
# ==========================================
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
rows = sheet.get_all_values()

if len(rows) <= 1:
    print("❌ 시트 E열에 상품 링크가 없습니다!")
else:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage"
            ]
        )

        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768}
        )

        page = context.new_page()

        # 메인 먼저 방문
        try:
            page.goto(
                "https://www.oliveyoung.co.kr/store/main/main.do",
                wait_until="domcontentloaded",
                timeout=60000
            )
            time.sleep(random.uniform(2, 4))
        except Exception as e:
            print(f"⚠️ 메인 페이지 방문 실패: {e}")

        for i, row in enumerate(rows[1:]):
            if len(row) > 4 and row[4].strip():
                target_url = clean_oliveyoung_url(row[4].strip())

                title, current_price, status = crawl_with_browser(page, target_url)

                print(f"🎯 {title} / {current_price}원 / {status}")

                previous_price = 0

                if len(row) > 2:
                    old_price_text = str(row[2]).replace(",", "").strip()
                    if old_price_text.isdigit():
                        previous_price = int(old_price_text)

                if current_price == 0:
                    current_price = previous_price
                    diff = 0
                    mark = "-"
                else:
                    if previous_price == 0:
                        previous_price = current_price

                    diff, mark = calculate_change(current_price, previous_price)

                sheet.update(
                    values=[[now, title, current_price, status, target_url, previous_price, diff, mark]],
                    range_name=f"A{i+2}:H{i+2}"
                )

                print(f"✅ {i+2}행 업데이트 완료 / 변동: {diff} {mark}")

                time.sleep(random.uniform(4, 7))

        browser.close()

print("🔥 Playwright 올영 순찰 완료!")
