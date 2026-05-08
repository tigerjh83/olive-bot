import requests
import json
import re

# 테스트 상품 URL
product_url = "https://www.musinsa.com/products/5190556"

goods_no_match = re.search(r'/products/(\d+)', product_url)
goods_no = goods_no_match.group(1) if goods_no_match else "5190556"

option_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options?goodsSaleType=SALE&optKindCd=SHOES"

headers = {
    "accept": "application/json",
    "origin": "https://www.musinsa.com",
    "referer": "https://www.musinsa.com/",
    "user-agent": "Mozilla/5.0"
}

try:
    print(f"🚀 무신사 옵션 API 테스트 시작: {goods_no}")

    res = requests.get(option_api, headers=headers, timeout=10)

    print("상태코드:", res.status_code)

    res.raise_for_status()

    data = res.json()

    print("✅ 옵션 API 응답 성공!")
    print(json.dumps(data, indent=2, ensure_ascii=False)[:5000])

except Exception as e:
    print("❌ 에러:", e)
