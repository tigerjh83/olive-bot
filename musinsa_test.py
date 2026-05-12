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
    "accept": "application/json, text/plain, */*",
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
# 5. 가격/상품정보 함수
# ==========================================

def to_int_price(value):
    if value is None:
        return 0

    if isinstance(value, int):
        return value if value > 0 else 0

    if isinstance(value, float):
        return int(value) if value > 0 else 0

    if isinstance(value, str):
        numbers = re.sub(r"[^0-9]", "", value)
        if numbers:
            return int(numbers)

    return 0


def extract_product_info_from_items(items, goods_no):
    """
    기존에 상품명/브랜드 잘 가져오던 방식.
    이건 최대한 건드리지 않는다.
    """
    for item in items:
        if str(item.get("goodsNo")) == str(goods_no):
            price = (
                to_int_price(item.get("price"))
                or to_int_price(item.get("finalPrice"))
                or to_int_price(item.get("normalPrice"))
                or to_int_price(item.get("salePrice"))
                or to_int_price(item.get("sellPrice"))
                or to_int_price(item.get("discountedPrice"))
                or to_int_price(item.get("goodsPrice"))
                or 0
            )

            coupon_price = (
                to_int_price(item.get("couponPrice"))
                or to_int_price(item.get("finalPrice"))
                or to_int_price(item.get("salePrice"))
                or price
                or 0
            )

            sale_rate = (
                to_int_price(item.get("couponSaleRate"))
                or to_int_price(item.get("saleRate"))
                or to_int_price(item.get("finalDiscount"))
                or to_int_price(item.get("discountRate"))
                or 0
            )

            return {
                "product_name": item.get("goodsName", "UNKNOWN"),
                "brand_name": item.get("brandName", "UNKNOWN"),
                "price": price,
                "coupon_price": coupon_price,
                "sale_rate": sale_rate
            }

    return None


def find_price_recursively(obj):
    """
    이번에 가격 가져오던 방식.
    API 응답 전체에서 가격 필드만 뒤진다.
    상품명/브랜드는 여기서 절대 안 건드림.
    """
    price_keys = [
        "price",
        "finalPrice",
        "normalPrice",
        "salePrice",
        "sellPrice",
        "discountedPrice",
        "goodsPrice",
        "consumerPrice",
        "listPrice",
        "originalPrice",
        "amount"
    ]

    if isinstance(obj, dict):
        for key in price_keys:
            if key in obj:
                price = to_int_price(obj.get(key))
                if price > 0:
                    return price

        for value in obj.values():
            found = find_price_recursively(value)
            if found:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = find_price_recursively(item)
            if found:
                return found

    return 0


def get_product_info(goods_no):
    """
    최종 합친 버전.

    1. 상품명/브랜드는 기존 방식으로 가져온다.
    2. 기존 방식에서 가격까지 나오면 그대로 사용.
    3. 가격이 0이면, 이번에 성공했던 가격 재귀탐색으로 가격만 보강.
    4. 상품명/브랜드는 절대 덮어쓰지 않는다.
    """

    product_info = None
    saved_api_jsons = []

    # ------------------------------------------
    # 1차: 기존 curation API
    # ------------------------------------------
    curation_apis = [
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation/other-color",
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation"
    ]

    for api_url in curation_apis:
        try:
            print(f"🔍 기존 상품정보 API 시도: {api_url}")

            res = requests.get(api_url, headers=headers, timeout=10)

            if res.status_code != 200:
                print(f"⚠️ 응답 실패: {res.status_code}")
                continue

            data = res.json()
            saved_api_jsons.append(data)

            tabs = data.get("data", {}).get("curationTabs", [])

            for tab in tabs:
                items = tab.get("curationGoodsList", [])
                found_info = extract_product_info_from_items(items, goods_no)

                if found_info:
                    product_info = found_info
                    print("✅ 기존 방식으로 상품명/브랜드 확보")
                    break

            if product_info:
                break

        except Exception as e:
            print(f"⚠️ curation API 실패: {api_url}")
            print(e)

    # ------------------------------------------
    # 2차: 기존 recommend API
    # ------------------------------------------
    recommend_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/recommends/multi?uuid=detail_goods_attributes_allbrand&limit=10"

    try:
        print(f"🔍 recommend API 시도: {recommend_api}")

        res = requests.get(recommend_api, headers=headers, timeout=10)

        if res.status_code == 200:
            data = res.json()
            saved_api_jsons.append(data)

            # 상품명/브랜드가 아직 없으면 기존 방식으로 찾기
            if not product_info:
                similar_groups = data.get("data", {}).get("similar", [])

                for group in similar_groups:
                    recommends_tabs = group.get("recommendsTabs", [])

                    for tab in recommends_tabs:
                        items = tab.get("recommendedGoodsList", [])
                        found_info = extract_product_info_from_items(items, goods_no)

                        if found_info:
                            product_info = found_info
                            print("✅ recommend 기존 방식으로 상품명/브랜드 확보")
                            break

                    if product_info:
                        break
        else:
            print(f"⚠️ recommend 응답 실패: {res.status_code}")

    except Exception as e:
        print("⚠️ recommend API 실패")
        print(e)

    # ------------------------------------------
    # 3차: 그래도 상품정보 없으면 기본값
    # ------------------------------------------
    if not product_info:
        product_info = {
            "product_name": "UNKNOWN",
            "brand_name": "UNKNOWN",
            "price": 0,
            "coupon_price": 0,
            "sale_rate": 0
        }

    # ------------------------------------------
    # 4차: 가격만 보강
    # 상품명/브랜드는 절대 건드리지 않음
    # ------------------------------------------
    if not product_info.get("price"):
        print("🔧 가격이 0이라 가격만 보강 시도")

        # 이미 받아온 API 응답들 먼저 뒤짐
        for data in saved_api_jsons:
            found_price = find_price_recursively(data)

            if found_price:
                product_info["price"] = found_price

                if not product_info.get("coupon_price"):
                    product_info["coupon_price"] = found_price

                print(f"✅ 저장된 API 응답에서 가격 보강 성공: {found_price}")
                break

        # 그래도 없으면 API를 다시 한번 직접 호출해서 가격만 뒤짐
        if not product_info.get("price"):
            extra_price_apis = [
                recommend_api,
                f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation",
                f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation/other-color"
            ]

            for api_url in extra_price_apis:
                try:
                    print(f"🔍 가격 보강 API 시도: {api_url}")

                    res = requests.get(api_url, headers=headers, timeout=10)

                    if res.status_code != 200:
                        print(f"⚠️ 가격 보강 응답 실패: {res.status_code}")
                        continue

                    data = res.json()
                    found_price = find_price_recursively(data)

                    if found_price:
                        product_info["price"] = found_price

                        if not product_info.get("coupon_price"):
                            product_info["coupon_price"] = found_price

                        print(f"✅ 가격 보강 성공: {found_price}")
                        break

                except Exception as e:
                    print(f"⚠️ 가격 보강 실패: {api_url}")
                    print(e)

    # 쿠폰가 비어 있으면 가격으로 맞춤
    if product_info.get("price") and not product_info.get("coupon_price"):
        product_info["coupon_price"] = product_info["price"]

    return product_info


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
        print(f"✅ 상품번호: {goods_no}")

        # 상품명 / 브랜드 / 가격 정보
        product_info = get_product_info(goods_no)

        product_name = product_info["product_name"]
        brand_name = product_info["brand_name"]
        price = product_info["price"]
        coupon_price = product_info["coupon_price"]
        sale_rate = product_info["sale_rate"]

        print(f"✅ 상품명: {product_name}")
        print(f"✅ 브랜드: {brand_name}")
        print(f"✅ 가격: {price}")
        print(f"✅ 쿠폰가/최종가: {coupon_price}")
        print(f"✅ 할인율: {sale_rate}")

        # 옵션 API
        option_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options?goodsSaleType=SALE&optKindCd=SHOES"

        print(f"🔍 옵션 API 시도: {option_api}")

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

        # 재고 API
        stock_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options/v2/prioritized-inventories"

        payload = {
            "optionValueNos": option_value_nos
        }

        print(f"🔍 재고 API 시도: {stock_api}")

        stock_res = requests.post(
            stock_api,
            headers=headers,
            json=payload,
            timeout=10
        )

        stock_res.raise_for_status()
        stock_data = stock_res.json()

        print("✅ 재고 API 연결 완료")

        # 사이즈별 재고 맵
        stock_map = {}

        for idx, stock in enumerate(stock_data["data"]):
            if idx >= len(size_list):
                continue

            size_name = size_list[idx]
            stock_map[size_name] = parse_stock_status(stock)

        # 한 줄 데이터 생성
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

        # 기존 행 있으면 업데이트, 없으면 추가
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
