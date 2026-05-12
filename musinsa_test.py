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

html_headers = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
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
# 5. 상품명 / 브랜드 / 가격 추출 함수
# ==========================================

def to_int_price(value):
    """
    가격 값이 int, float, str 어떤 형태로 와도 숫자로 변환
    예: 129000, "129000", "129,000원"
    """
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


def clean_text(value):
    if value is None:
        return ""

    if not isinstance(value, str):
        value = str(value)

    value = re.sub(r"\s+", " ", value).strip()
    return value


def extract_product_info_from_item(item):
    """
    goodsNo가 일치하는 단일 상품 객체에서 상품명/브랜드/가격 추출
    """
    product_name = (
        clean_text(item.get("goodsName"))
        or clean_text(item.get("goodsNm"))
        or clean_text(item.get("name"))
        or clean_text(item.get("goodsTitle"))
        or clean_text(item.get("title"))
        or "UNKNOWN"
    )

    brand_name = (
        clean_text(item.get("brandName"))
        or clean_text(item.get("brandNm"))
        or clean_text(item.get("brand"))
        or clean_text(item.get("brandTitle"))
        or clean_text(item.get("brandNameEng"))
        or "UNKNOWN"
    )

    price = (
        to_int_price(item.get("price"))
        or to_int_price(item.get("finalPrice"))
        or to_int_price(item.get("normalPrice"))
        or to_int_price(item.get("salePrice"))
        or to_int_price(item.get("sellPrice"))
        or to_int_price(item.get("discountedPrice"))
        or to_int_price(item.get("goodsPrice"))
        or to_int_price(item.get("consumerPrice"))
        or to_int_price(item.get("listPrice"))
        or to_int_price(item.get("originalPrice"))
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
        "product_name": product_name,
        "brand_name": brand_name,
        "price": price,
        "coupon_price": coupon_price,
        "sale_rate": sale_rate
    }


def find_goods_object_recursively(obj, goods_no):
    """
    API 응답 전체를 뒤져서 goodsNo가 현재 goods_no와 일치하는 dict 객체를 찾음
    상품명/브랜드가 추천상품으로 잘못 잡히는 걸 막기 위해 goodsNo 일치 기준 사용
    """
    if isinstance(obj, dict):
        possible_goods_no = (
            obj.get("goodsNo")
            or obj.get("goods_no")
            or obj.get("goodsNumber")
            or obj.get("id")
        )

        if str(possible_goods_no) == str(goods_no):
            return obj

        for value in obj.values():
            found = find_goods_object_recursively(value, goods_no)
            if found:
                return found

    elif isinstance(obj, list):
        for item in obj:
            found = find_goods_object_recursively(item, goods_no)
            if found:
                return found

    return None


def find_price_recursively(obj):
    """
    API 응답 전체에서 가격처럼 보이는 필드를 재귀적으로 탐색
    가격 보강용
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


def find_name_brand_recursively(obj, goods_no):
    """
    API 응답 전체에서 goodsNo 일치 객체를 찾아 상품명/브랜드 추출
    """
    found_obj = find_goods_object_recursively(obj, goods_no)

    if found_obj:
        info = extract_product_info_from_item(found_obj)
        return {
            "product_name": info["product_name"],
            "brand_name": info["brand_name"],
            "price": info["price"],
            "coupon_price": info["coupon_price"],
            "sale_rate": info["sale_rate"]
        }

    return None


def get_name_from_html(goods_no):
    """
    API에서 상품명을 못 찾을 때 상품 상세 HTML meta에서 상품명 보강
    브랜드는 HTML에서 정확히 뽑기 어려우면 UNKNOWN 유지
    """
    product_page_urls = [
        f"https://www.musinsa.com/products/{goods_no}",
        f"https://goods.musinsa.com/app/goods/{goods_no}"
    ]

    for url in product_page_urls:
        try:
            print(f"🔍 HTML 상품명 보강 시도: {url}")

            res = requests.get(url, headers=html_headers, timeout=10)

            if res.status_code != 200:
                print(f"⚠️ HTML 응답 실패: {res.status_code}")
                continue

            html = res.text

            # og:title 우선
            og_title_match = re.search(
                r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
                html,
                re.IGNORECASE
            )

            if og_title_match:
                title = clean_text(og_title_match.group(1))

                # 무신사 뒤쪽 문구 제거
                title = re.sub(r"\s*-\s*무신사.*$", "", title).strip()
                title = re.sub(r"\s*\|\s*무신사.*$", "", title).strip()

                if title:
                    return {
                        "product_name": title,
                        "brand_name": "UNKNOWN"
                    }

            # title 태그 백업
            title_match = re.search(
                r"<title>(.*?)</title>",
                html,
                re.IGNORECASE | re.DOTALL
            )

            if title_match:
                title = clean_text(title_match.group(1))
                title = re.sub(r"\s*-\s*무신사.*$", "", title).strip()
                title = re.sub(r"\s*\|\s*무신사.*$", "", title).strip()

                if title:
                    return {
                        "product_name": title,
                        "brand_name": "UNKNOWN"
                    }

        except Exception as e:
            print("⚠️ HTML 상품명 보강 실패")
            print(e)

    return None


def merge_product_info(base_info, new_info):
    """
    기존 값은 살리고, UNKNOWN/0인 값만 새 값으로 보강
    """
    if not new_info:
        return base_info

    if base_info["product_name"] == "UNKNOWN" and new_info.get("product_name") not in [None, "", "UNKNOWN"]:
        base_info["product_name"] = new_info.get("product_name")

    if base_info["brand_name"] == "UNKNOWN" and new_info.get("brand_name") not in [None, "", "UNKNOWN"]:
        base_info["brand_name"] = new_info.get("brand_name")

    if not base_info.get("price") and new_info.get("price"):
        base_info["price"] = new_info.get("price")

    if not base_info.get("coupon_price") and new_info.get("coupon_price"):
        base_info["coupon_price"] = new_info.get("coupon_price")

    if not base_info.get("sale_rate") and new_info.get("sale_rate"):
        base_info["sale_rate"] = new_info.get("sale_rate")

    return base_info


def get_product_info(goods_no):
    """
    상품명/브랜드/가격 통합 수집 함수

    1. curation / recommend API에서 goodsNo 일치 객체 재귀 탐색
    2. 가격은 응답 전체 재귀 탐색으로 보강
    3. 상품명은 최후에 HTML meta에서 보강
    """
    product_info = {
        "product_name": "UNKNOWN",
        "brand_name": "UNKNOWN",
        "price": 0,
        "coupon_price": 0,
        "sale_rate": 0
    }

    api_urls = [
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation/other-color",
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/curation",
        f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/recommends/multi?uuid=detail_goods_attributes_allbrand&limit=10"
    ]

    # ------------------------------------------
    # 1차: API 응답 전체에서 goodsNo 일치 객체 찾기
    # ------------------------------------------
    for api_url in api_urls:
        try:
            print(f"🔍 상품정보 API 시도: {api_url}")

            res = requests.get(api_url, headers=headers, timeout=10)

            if res.status_code != 200:
                print(f"⚠️ 응답 실패: {res.status_code}")
                continue

            data = res.json()

            found_info = find_name_brand_recursively(data, goods_no)

            if found_info:
                product_info = merge_product_info(product_info, found_info)
                print("✅ goodsNo 일치 객체에서 상품정보 확보")

            # 가격은 별도로 전체 응답에서 보강
            if not product_info.get("price"):
                found_price = find_price_recursively(data)

                if found_price:
                    product_info["price"] = found_price

                    if not product_info.get("coupon_price"):
                        product_info["coupon_price"] = found_price

                    print(f"✅ 가격 보강 성공: {found_price}")

            # 상품명/브랜드/가격이 다 있으면 탈출
            if (
                product_info["product_name"] != "UNKNOWN"
                and product_info["brand_name"] != "UNKNOWN"
                and product_info["price"] > 0
            ):
                break

        except Exception as e:
            print(f"⚠️ 상품정보 API 실패: {api_url}")
            print(e)

    # ------------------------------------------
    # 2차: 상품명만 HTML에서 보강
    # ------------------------------------------
    if product_info["product_name"] == "UNKNOWN":
        html_info = get_name_from_html(goods_no)

        if html_info:
            product_info = merge_product_info(product_info, html_info)
            print("✅ HTML에서 상품명 보강 성공")

    # ------------------------------------------
    # 3차: coupon_price 비어있으면 price로 맞춤
    # ------------------------------------------
    if product_info["price"] > 0 and not product_info["coupon_price"]:
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
