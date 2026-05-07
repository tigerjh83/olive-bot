import requests
import json
import re

# 테스트 상품 URL
url = "https://www.musinsa.com/products/5190556"

# 상품 번호 추출
goods_no_match = re.search(r'/products/(\d+)', url)
goods_no = goods_no_match.group(1) if goods_no_match else "5190556"

headers = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json"
}

try:
    print(f"🚀 무신사 상품번호 [{goods_no}] API 타격 시작...")

    # 재고 API 직접 호출
    stock_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options/v2/prioritized-inventories"

    stock_res = requests.get(stock_api, headers=headers, timeout=10)
    stock_res.raise_for_status()

    stock_data = stock_res.json()

    print("✅ 재고 API 연결 성공!\n")

    # JSON 앞부분 출력
    print(json.dumps(stock_data, indent=2, ensure_ascii=False)[:3000])

except requests.exceptions.RequestException as e:
    print(f"❌ API 에러: {e}")

except Exception as e:
    print(f"⚠️ 에러 발생: {e}")
