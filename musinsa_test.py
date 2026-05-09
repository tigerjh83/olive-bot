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

spreadsheet = client.open("무신사 신발 재고관리")
result_sheet = spreadsheet.sheet1
url_sheet = spreadsheet.worksheet("URL_LIST")

# ==========================================
# 2. URL_LIST 시트에서 URL 읽기
# ==========================================

url_values = url_sheet.col_values(1)

product_urls = [
    url.strip()
    for url in url_values[1:]
    if url.strip()
]

print(f"📌 URL_LIST에서 읽은 상품 수: {len(product_urls)}개")

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
# 4. 사이즈 컬럼
# ==========================================

SIZE_COLUMNS = [
    "220", "225", "230", "235", "240",
    "245", "250", "255", "260", "265",
    "270", "275", "280", "285", "290",
    "295"
]

# ==========================================
# 5. 상품명 / 브랜드 / 가격 정보 가져오기
# ==========================================

def to_number(value):
    if value is None:
        return 0

    if isinstance(value, int):
        return value

    if isinstance(value, float):
        return int(value)

    value = str(value)
    value = re.sub(r"[^0-9]", "", value)

    return int(value) if value else 0


def clean_price(value):
    price = to_number(value)

    if price < 1000 or price > 5000000:
        return 0

    return price


def extract_name_brand_from_item(item):
    if not isinstance(item, dict):
        return {
            "product_name": "UNKNOWN",
            "brand_name": "UNKNOWN"
        }

    product_name = (
        item.get("goodsName")
        or item.get("goodsNm")
        or item.get("productName")
        or item.get("name")
        or "UNKNOWN"
    )

    brand_name = (
        item.get("brandName")
        or item.get("brandNm")
        or item.get("brand")
        or "UNKNOWN"
    )

    return {
        "product_name": product_name,
        "brand_name": brand_name
    }


def find_product_item_by_goods_no(data, goods_no):
    if isinstance(data, dict):
        if str(data.get("goodsNo")) == str(goods_no):
            return data

        for value in data.values():
            found = find_product_item_by_goods_no(value, goods_no)
            if found:
                return found

    elif isinstance(data, list):
        for item in data:
            found = find_product_item_by_goods_no(item, goods_no)
            if found:
                return found

    return None


def get_price_from_curation(goods_no):
    curation_urls = [
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation/other-color",
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation"
    ]

    for api_url in curation_urls:
        try:
            print(f"🔍 가격 전용 curation API 시도: {api_url}")

            res = requests.get(api_url, headers=headers, timeout=10)

            if res.status_code != 200:
                continue

            data = res.json()

            item = find_product_item_by_goods_no(data, goods_no)

            if not item:
                print("⚠️ curation 안에서 goodsNo 일치 item 없음")
                continue

            price = clean_price(item.get("price"))
            coupon_price = clean_price(item.get("couponPrice"))
            sale_rate = to_number(item.get("couponSaleRate"))

            if price > 0 or coupon_price > 0:
                print(f"💰 curation 가격 발견: {price}")
                print(f"💰 curation 쿠폰가 발견: {coupon_price}")
                print(f"💰 curation 할인율 발견: {sale_rate}")

                return {
                    "price": price,
                    "coupon_price": coupon_price,
                    "sale_rate": sale_rate
                }

            print("⚠️ goodsNo 일치 item은 찾았지만 가격 값이 없음")

        except Exception as e:
            print(f"⚠️ 가격 curation API 실패: {api_url}")
            print(e)

    return {
        "price": 0,
        "coupon_price": 0,
        "sale_rate": 0
    }


def get_title_from_html(product_url):
    try:
        print(f"🔍 HTML 상품명 fallback 시도: {product_url}")

        res = requests.get(product_url, headers=headers, timeout=10)

        if res.status_code != 200:
            return "UNKNOWN"

        html = res.text

        title_match = re.search(
            r'<meta property="og:title" content="([^"]+)"',
            html
        )

        if title_match:
            return title_match.group(1).strip()

    except Exception as e:
        print("⚠️ HTML 상품명 fallback 실패")
        print(e)

    return "UNKNOWN"


def get_product_info(goods_no, product_url):
    best_info = {
        "product_name": "UNKNOWN",
        "brand_name": "UNKNOWN",
        "price": 0,
        "coupon_price": 0,
        "sale_rate": 0
    }

    # 1. 가격/쿠폰가/할인율은 curation API에서 goodsNo 일치 객체 기준으로만 추출
    price_info = get_price_from_curation(goods_no)
    best_info["price"] = price_info["price"]
    best_info["coupon_price"] = price_info["coupon_price"]
    best_info["sale_rate"] = price_info["sale_rate"]

    # 2. 상품명/브랜드는 fallback 유지
    info_api_candidates = [
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation/other-color",
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation",
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}",
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/detail",
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/summary",
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/information"
    ]

    for api_url in info_api_candidates:
        try:
            print(f"🔍 상품명/브랜드 API 시도: {api_url}")

            res = requests.get(api_url, headers=headers, timeout=10)

            if res.status_code != 200:
                continue

            data = res.json()

            item = find_product_item_by_goods_no(data, goods_no)

            if item:
                name_brand = extract_name_brand_from_item(item)
            elif isinstance(data, dict) and isinstance(data.get("data"), dict):
                name_brand = extract_name_brand_from_item(data["data"])
            else:
                continue

            if best_info["product_name"] == "UNKNOWN" and name_brand["product_name"] != "UNKNOWN":
                best_info["product_name"] = name_brand["product_name"]

            if best_info["brand_name"] == "UNKNOWN" and name_brand["brand_name"] != "UNKNOWN":
                best_info["brand_name"] = name_brand["brand_name"]

        except Exception as e:
            print(f"⚠️ 상품명/브랜드 API 실패: {api_url}")
            print(e)

    if best_info["product_name"] == "UNKNOWN":
        best_info["product_name"] = get_title_from_html(product_url)

    return best_info

# ==========================================
# 6. 재고 상태 판정
# ==========================================

def parse_stock_status(stock):
    remain_qty = stock.get("remainQuantity")
    out_of_stock = stock.get("outOfStock")
    related_option = stock.get("relatedOption")

    if out_of_stock is False:
        if remain_qty is None:
            return "판매중"
        return str(remain_qty)

    if related_option and related_option.get("outOfStock") is False:
        return "브랜드배송"

    return "품절"

# ==========================================
# 7. 기존 URL 행 찾기
# ==========================================

def find_existing_row_by_url(sheet, product_url):
    rows = sheet.get_all_values()

    for idx, row in enumerate(rows[1:], start=2):
        if len(row) >= 7 and row[6].strip() == product_url.strip():
            return idx

    return None

# ==========================================
# 8. 상품 반복 시작
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

        product_info = get_product_info(goods_no, product_url)

        product_name = product_info["product_name"]
        brand_name = product_info["brand_name"]
        price = product_info["price"]
        coupon_price = product_info["coupon_price"]
        sale_rate = product_info["sale_rate"]

        print(f"✅ 상품명: {product_name}")
        print(f"✅ 브랜드: {brand_name}")
        print(f"✅ 가격: {price}")
        print(f"✅ 쿠폰가: {coupon_price}")
        print(f"✅ 할인율: {sale_rate}")

        option_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options?goodsSaleType=SALE&optKindCd=SHOES"

        option_res = requests.get(option_api, headers=headers, timeout=10)
        option_res.raise_for_status()
        option_data = option_res.json()

        option_values = option_data["data"]["basic"][0]["optionValues"]

        size_list = []
        option_value_nos = []

        for item in option_values:
            size_list.append(item["name"])
            option_value_nos.append(item["no"])

        print("✅ 사이즈 목록 확보 완료")

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

        stock_map = {}

        for idx, stock in enumerate(stock_data["data"]):
            if idx >= len(size_list):
                continue

            size_name = size_list[idx]
            stock_map[size_name] = parse_stock_status(stock)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        row = [
            now,
            product_name,
            brand_name,
            price,
            coupon_price,
            sale_rate,
            product_url
        ]

        for size in SIZE_COLUMNS:
            row.append(stock_map.get(size, ""))

        existing_row = find_existing_row_by_url(result_sheet, product_url)

        if existing_row:
            result_sheet.update(
                values=[row],
                range_name=f"A{existing_row}:W{existing_row}"
            )
            print(f"🔄 기존 행 업데이트 완료: {existing_row}행 / {product_name}")
        else:
            result_sheet.append_row(row)
            print(f"➕ 신규 행 추가 완료: {product_name}")

        time.sleep(3)

    except Exception as e:
        print(f"❌ 에러 발생: {product_url}")
        print(e)

print("=" * 50)
print("🎉 전체 작업 완료!")
