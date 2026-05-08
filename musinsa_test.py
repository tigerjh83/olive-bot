import requests
import json
import re

# 테스트 상품 URL
product_url = "https://www.musinsa.com/products/5190556"

# 상품번호 추출
goods_no_match = re.search(r'/products/(\d+)', product_url)
goods_no = goods_no_match.group(1) if goods_no_match else "5190556"

# 옵션 API
option_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options?goodsSaleType=SALE&optKindCd=SHOES"

# 재고 API
stock_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options/v2/prioritized-inventories"

headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": "https://www.musinsa.com",
    "referer": "https://www.musinsa.com/",
    "user-agent": "Mozilla/5.0"
}

try:
    print(f"🚀 무신사 사이즈+재고 통합 테스트 시작: {goods_no}")

    # ==========================================
    # 1. 옵션 API 호출
    # ==========================================
    option_res = requests.get(option_api, headers=headers, timeout=10)
    option_res.raise_for_status()

    option_data = option_res.json()

    option_values = option_data["data"]["basic"][0]["optionValues"]

    # optionValueNo ↔ 사이즈명 매핑
    size_map = {}

    option_value_nos = []

    for item in option_values:
        option_no = item["no"]
        size_name = item["name"]

        size_map[option_no] = size_name
        option_value_nos.append(option_no)

    print("✅ 사이즈 목록 확보 완료")

    # ==========================================
    # 2. 재고 API 호출
    # ==========================================
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

    print("✅ 재고 API 연결 완료\n")

    # ==========================================
    # 3. 사이즈 + 재고 합치기
    # ==========================================
    print("=" * 40)

    for idx, stock in enumerate(stock_data["data"]):

        size_name = list(size_map.values())[idx]

        remain_qty = stock.get("remainQuantity")

        out_of_stock = stock.get("outOfStock")

        if out_of_stock:
            status = "품절"
            remain_qty = 0
        else:
            status = "판매중"

        print(f"사이즈: {size_name}")
        print(f"재고수량: {remain_qty}")
        print(f"상태: {status}")
        print("-" * 40)

except Exception as e:
    print("❌ 에러 발생:", e)
