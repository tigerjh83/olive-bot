import requests
import json
import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import os
import time

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
    "accept": "application/json",
    "content-type": "application/json",
    "origin": "https://www.musinsa.com",
    "referer": "https://www.musinsa.com/",
    "user-agent": "Mozilla/5.0"
}

# ==========================================
# 4. 가격 정보 가져오기 함수
# ==========================================

def get_product_info(goods_no):
    api_candidates = [
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation/other-color",
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation"
    ]

    for api_url in api_candidates:
        try:
            print(f"🔍 가격 API 시도: {api_url}")

            res = requests.get(api_url, headers=headers, timeout=10)

            if res.status_code != 200:
                continue

            data = res.json()

            for tab in data["data"]["curationTabs"]:
                for item in tab["curationGoodsList"]:
                    if str(item.get("goodsNo")) == goods_no:
                        return {
                            "product_name": item.get("goodsName", "UNKNOWN"),
                            "brand_name": item.get("brandName", "UNKNOWN"),
                            "price": item.get("price", 0),
                            "coupon_price": item.get("couponPrice", 0) or 0,
                            "sale_rate": item.get("couponSaleRate", 0) or 0
                        }

        except Exception as e:
            print(f"⚠️ 가격 API 실패: {api_url}")
            print(e)

    return {
        "product_name": "UNKNOWN",
        "brand_name": "UNKNOWN",
        "price": 0,
        "coupon_price": 0,
        "sale_rate": 0
    }

# ==========================================
# 5. 상품 반복 시작
# ==========================================

for product_url in product_urls:
    try:
        print("=" * 50)
        print(f"🚀 상품 처리 시작: {product_url}")

        goods_no_match = re.search(r'/products/(\d+)', product_url)

        if not goods_no_match:
            print("❌ 상품번호 추출 실패")
            continue

        goods_no = goods_no_match.group(1)

        # 가격 정보
        product_info = get_product_info(goods_no)

        product_name = product_info["product_name"]
        brand_name = product_info["brand_name"]
        price = product_info["price"]
        coupon_price = product_info["coupon_price"]
        sale_rate = product_info["sale_rate"]

        print(f"✅ 상품명: {product_name}")
        print(f"✅ 가격: {price}")
        print(f"✅ 쿠폰가: {coupon_price}")

        # 옵션 API
        option_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options?goodsSaleType=SALE&optKindCd=SHOES"

        option_res = requests.get(option_api, headers=headers, timeout=10)
        option_res.raise_for_status()
        option_data = option_res.json()

        option_values = option_data["data"]["basic"][0]["optionValues"]

        size_list = []
        option_value_nos = []

        for item in option_values:
            option_no = item["no"]
            size_name = item["name"]

            size_list.append(size_name)
            option_value_nos.append(option_no)

        print("✅ 사이즈 목록 확보 완료")

        # 재고 API
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

        stock_res.raise_for_status()
        stock_data = stock_res.json()

        print("✅ 재고 API 연결 완료")

        # 구글시트 저장
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for idx, stock in enumerate(stock_data["data"]):
            size_name = size_list[idx] if idx < len(size_list) else "UNKNOWN"

            out_of_stock = stock.get("outOfStock")
            remain_qty = stock.get("remainQuantity")

            if out_of_stock:
                status = "품절"
                remain_qty = 0
            else:
                status = "판매중"
                if remain_qty is None:
                    remain_qty = "재고수량 비공개"

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

            print(f"✅ 저장 완료: {size_name} / {remain_qty} / {status}")

        print(f"🔥 완료: {product_name}")

        time.sleep(3)

    except Exception as e:
        print(f"❌ 에러 발생: {product_url}")
        print(e)

print("=" * 50)
print("🎉 전체 작업 완료!")
