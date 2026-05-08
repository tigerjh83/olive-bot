import requests
import json
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import time
from bs4 import BeautifulSoup

# ==========================================
# 1. 구글 인증
# ==========================================

secrets = os.environ.get("GOOGLE_CREDENTIALS")
creds_dict = json.loads(secrets)

creds = Credentials.from_service_account_info(
    creds_dict,
    scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
)

client = gspread.authorize(creds)

# 결과 저장 시트
result_sheet = client.open("무신사 신발 재고관리").sheet1

# ==========================================
# 2. 추적할 상품 URL 리스트
# ==========================================

product_urls = [
    "https://www.musinsa.com/products/5190556",
    "https://www.musinsa.com/products/6174864"
]

# ==========================================
# 3. 공통 헤더
# ==========================================

headers = {
    "accept": "application/json, text/html",
    "content-type": "application/json",
    "origin": "https://www.musinsa.com",
    "referer": "https://www.musinsa.com/",
    "user-agent": "Mozilla/5.0"
}

# ==========================================
# 4. 상품 반복 시작
# ==========================================

for product_url in product_urls:

    try:

        print("=" * 50)
        print(f"🚀 상품 처리 시작: {product_url}")

        # ==========================================
        # 상품번호 추출
        # ==========================================

        goods_no_match = re.search(r'/products/(\d+)', product_url)

        if not goods_no_match:
            print("❌ 상품번호 추출 실패")
            continue

        goods_no = goods_no_match.group(1)

        # ==========================================
        # HTML 상품 정보 가져오기
        # ==========================================

        html_res = requests.get(
            product_url,
            headers=headers,
            timeout=10
        )

        html_res.raise_for_status()

        soup = BeautifulSoup(html_res.text, "html.parser")

        html_text = soup.get_text(" ", strip=True)

        # 상품명
        product_name = "UNKNOWN"

        title_tag = soup.find("title")

        if title_tag:
            product_name = title_tag.text.replace(" | 무신사", "").strip()

        # 브랜드
        brand_name = "UNKNOWN"

        brand_match = re.search(r'브랜드\s+([^\s]+)', html_text)

        if brand_match:
            brand_name = brand_match.group(1)

        # 가격
        price = 0

        price_match = re.search(r'([\d,]+)원', html_text)

        if price_match:
            price = int(price_match.group(1).replace(",", ""))

        # 쿠폰가
        coupon_price = 0

        coupon_match = re.search(r'([\d,]+)원\s*쿠폰', html_text)

        if coupon_match:
            coupon_price = int(coupon_match.group(1).replace(",", ""))

        # 할인율
        sale_rate = 0

        sale_match = re.search(r'(\d+)%', html_text)

        if sale_match:
            sale_rate = int(sale_match.group(1))

        print(f"✅ 상품명: {product_name}")
        print(f"✅ 가격: {price}")

        # ==========================================
        # 옵션 API
        # ==========================================

        option_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options?goodsSaleType=SALE&optKindCd=SHOES"

        option_res = requests.get(
            option_api,
            headers=headers,
            timeout=10
        )

        option_data = option_res.json()

        option_values = option_data["data"]["basic"][0]["optionValues"]

        size_map = {}
        option_value_nos = []

        for item in option_values:

            option_no = item["no"]
            size_name = item["name"]

            size_map[option_no] = size_name
            option_value_nos.append(option_no)

        print("✅ 사이즈 목록 확보 완료")

        # ==========================================
        # 재고 API
        # ==========================================

        stock_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options/v2/prioritized-inventories"

        payload = {
            "optionValueNos": option_value_nos
        }

        stock_res = requests.post(
            stock_api,
            headers=headers,
            json=payload,
            timeout=10
        )

        stock_data = stock_res.json()

        print("✅ 재고 API 연결 완료")

        # ==========================================
        # 구글시트 저장
        # ==========================================

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for idx, stock in enumerate(stock_data["data"]):

            size_name = list(size_map.values())[idx]

            remain_qty = stock.get("remainQuantity")

            out_of_stock = stock.get("outOfStock")

            if out_of_stock:
                status = "품절"
                remain_qty = 0
            else:
                status = "판매중"

            row = [
                now,
                product_name,
                brand_name,
                price,
                coupon_price,
                sale_rate,
                size_name,
                remain_qty,
                status,
                product_url
            ]

            result_sheet.append_row(row)

            print(f"✅ 저장 완료: {size_name} / {remain_qty}")

        print(f"🔥 완료: {product_name}")

        # 너무 빠른 호출 방지
        time.sleep(3)

    except Exception as e:

        print(f"❌ 에러 발생: {product_url}")
        print(e)

print("=" * 50)
print("🎉 전체 작업 완료!")
