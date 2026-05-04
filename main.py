import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import requests
from bs4 import BeautifulSoup
import time
import random

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
# 2. 시트에서 URL 리스트 가져오기 (E열)
# ==========================================
rows = sheet.get_all_values()
urls = []

for row in rows[1:]:
    if len(row) > 4 and row[4].strip():
        urls.append(row[4].strip())

# ==========================================
# 3. 올리브영 크롤링 함수
# ==========================================
def crawl_product(url):
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
        "Mozilla/5.0 (X11; Linux x86_64)"
    ]

    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    # 재시도 로직
    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=10)
            res.raise_for_status()
            break
        except Exception as e:
            print(f"⚠️ 재시도 {attempt+1}: {url} / {e}")
            time.sleep(random.uniform(2, 4))
    else:
        return "에러", 0, "에러"

    soup = BeautifulSoup(res.text, "html.parser")

    # 상품명
    title_tag = soup.select_one(".prd_info .prd_name")
    title = title_tag.get_text(strip=True) if title_tag else "상품명 없음"

    # 가격
    price_tag = (
        soup.select_one(".prd_price .price-2 strong")
        or soup.select_one(".prd_price .price-1 strong")
    )

    if price_tag:
        price_text = price_tag.get_text(strip=True).replace(",", "")
        price = int(price_text) if price_text.isdigit() else 0
    else:
        price = 0

    # 품절 여부 (안정화 버전)
    buy_btn = soup.select_one(".btn_buy")

    if buy_btn:
        buy_text = buy_btn.get_text(strip=True)

        if "품절" in buy_text or "일시품절" in buy_text:
            status = "품절"
        elif "구매" in buy_text:
            status = "판매중"
        else:
            status = f"확인필요({buy_text})"
    else:
        status = "확인필요"

    # 가격 이상 방지
    if price == 0:
        status = "확인필요"

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
# 5. 실행
# ==========================================
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

for url in urls:
    title, current_price, status = crawl_product(url)

    print(f"🎯 {title} / {current_price}원 / {status}")

    rows = sheet.get_all_values()
    found = False

    for i, row in enumerate(rows):
        if len(row) > 4 and row[4].strip() == url:
            previous_price = 0

            if len(row) > 2:
                old_price_text = row[2].replace(",", "").strip()
                if old_price_text.isdigit():
                    previous_price = int(old_price_text)

            if previous_price == 0:
                previous_price = current_price

            diff, mark = calculate_change(current_price, previous_price)

            sheet.update(
                f"A{i+1}:H{i+1}",
                [[
                    now,
                    title,
                    current_price,
                    status,
                    url,
                    previous_price,
                    diff,
                    mark
                ]]
            )

            print(f"✅ {i+1}행 업데이트 완료 / 변동: {diff} {mark}")
            found = True
            break

    if not found:
        sheet.append_row([
            now,
            title,
            current_price,
            status,
            url,
            current_price,
            0,
            "-"
        ])
        print("✅ 신규 상품 추가 완료")

    # 차단 방지 딜레이
    time.sleep(random.uniform(1.5, 3.5))

print("🔥 전체 순찰 완벽하게 종료!")
