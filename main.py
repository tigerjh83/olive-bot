import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from curl_cffi import requests
from bs4 import BeautifulSoup
import time
import random
from urllib.parse import urlparse, parse_qs

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
# 3. 올리브영 크롤링 함수
# ==========================================
def crawl_product(url):
    session = requests.Session(impersonate="chrome110")

    for attempt in range(3):
        try:
            if attempt == 0:
                session.get(
                    "https://www.oliveyoung.co.kr/store/main/main.do",
                    timeout=15
                )
                time.sleep(random.uniform(1.5, 3.0))

            res = session.get(url, timeout=15)

            blocked_keywords = [
                "Access Denied",
                "Forbidden",
                "차단",
                "비정상",
                "보안",
                "captcha",
                "robot",
                "bot"
            ]

            if any(keyword.lower() in res.text.lower() for keyword in blocked_keywords):
                raise Exception("차단 페이지 감지됨")

            break

        except Exception as e:
            print(f"⚠️ 재시도 {attempt + 1}: {url} / 에러: {e}")
            time.sleep(random.uniform(4, 6))

    else:
        return "에러(방어막 막힘)", 0, "에러"

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

    # 품절 여부
    buy_btn = soup.select_one(".btn_buy")

    if buy_btn:
        buy_text = buy_btn.get_text(strip=True)

        if "품절" in buy_text or "일시품절" in buy_text:
            status = "품절"
        elif "구매" in buy_text or "장바구니" in buy_text:
            status = "판매중"
        else:
            status = f"확인({buy_text})"
    else:
        status = "확인필요"

    # 파싱 실패 방어
    if title == "상품명 없음" or price == 0:
        print("⚠️ 파싱 실패. HTML 앞부분:")
        print(res.text[:500])
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
# 5. 메인 실행 로직
# ==========================================
now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
rows = sheet.get_all_values()

if len(rows) <= 1:
    print("❌ 시트 E열에 상품 링크가 없습니다!")
else:
    for i, row in enumerate(rows[1:]):
        if len(row) > 4 and row[4].strip():
            target_url = clean_oliveyoung_url(row[4].strip())
            title, current_price, status = crawl_product(target_url)

            print(f"🎯 {title} / {current_price}원 / {status}")

            previous_price = 0

            if len(row) > 2:
                old_price_text = str(row[2]).replace(",", "").strip()
                if old_price_text.isdigit():
                    previous_price = int(old_price_text)

            if previous_price == 0:
                previous_price = current_price

            diff, mark = calculate_change(current_price, previous_price)

            sheet.update(
                values=[[now, title, current_price, status, target_url, previous_price, diff, mark]],
                range_name=f"A{i+2}:H{i+2}"
            )

            print(f"✅ {i+2}행 업데이트 완료")
            time.sleep(random.uniform(2, 4))

print("🔥 스텔스 순찰 임무 완수!")
