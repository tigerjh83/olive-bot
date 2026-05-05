import os
import json
import re
import time
import random
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import gspread
from google.oauth2.service_account import Credentials
from curl_cffi import requests

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
# 3. HTML 안 JSON 데이터 추출 함수 (고급 스킬)
# ==========================================
def extract_product_data(html):
    # 상품명
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

    # 가격: finalPrice 우선, 없으면 salePrice
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

    # 품절 여부
    soldout_true_patterns = [
        r'\\"soldOutFlag\\":true',
        r'"soldOutFlag":true'
    ]

    sold_out = any(re.search(pattern, html) for pattern in soldout_true_patterns)
    status = "품절" if sold_out else "판매중"

    if title == "상품명 없음" or price == 0:
        return "에러(파싱실패)", 0, "에러"

    return title, price, status

# ==========================================
# 4. 올리브영 페이지 요청 함수
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
                "Access Denied", "Forbidden", "차단", "비정상", "보안", "captcha", "robot", "bot"
            ]

            if any(keyword.lower() in res.text.lower() for keyword in blocked_keywords):
                raise Exception("차단 페이지 감지됨")

            title, price, status = extract_product_data(res.text)

            if price == 0 or "에러" in status:
                print("⚠️ 파싱 실패. HTML 앞부분:")
                print(res.text[:700])

            return title, price, status

        except Exception as e:
            print(f"⚠️ 재시도 {attempt + 1}: {url} / 에러: {e}")
            time.sleep(random.uniform(4, 6))

    return "에러(방어막 막힘)", 0, "에러"

# ==========================================
# 5. 가격 변동 계산
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
# 6. 메인 실행 로직
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

            # 크롤링 실패 시 기존 가격 유지 (이거 추가하신 것도 신의 한 수입니다!)
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

            time.sleep(random.uniform(2, 4))

print("🔥 올영 JSON 순찰 임무 완수!")
