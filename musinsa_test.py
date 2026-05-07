
import requests
from bs4 import BeautifulSoup
import json
import re

# 테스트 상품 URL (디스커버리 조거플렉스 등 무신사 신발 링크)
url = "https://www.musinsa.com/products/5190556"

# 1. URL에서 상품 번호(goodsNo)만 자동으로 쏙 뽑아내기
goods_no_match = re.search(r'/products/(\d+)', url)
goods_no = goods_no_match.group(1) if goods_no_match else "5190556"

# 2. 강력한 위장막 (사람인 척)
headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": url
}

try:
    print(f"🚀 무신사 상품번호 [{goods_no}] API 타격 시작...")

    # 3. 상품명 & 가격 가져오기 (HTML 앞단)
    res = requests.get(url, headers=headers, timeout=10)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    
    title_tag = soup.select_one(".product-detail__sc-1klhlce-3") # 무신사 상품명 클래스 (변경될 수 있음)
    title = title_tag.text.strip() if title_tag else soup.title.text.replace(" - 무신사", "").strip()
    print(f"🎯 상품명: {title}")

    # 4. 재고 API (뒷문) 타격하기
    stock_api = f"https://goods-detail.musinsa.com/api2/goods/{goods_no}/options/v2/prioritized-inventories"
    
    stock_res = requests.get(stock_api, headers=headers, timeout=10)
    stock_res.raise_for_status()
    stock_data = stock_res.json()

    print("\n✅ 재고 API 연결 성공! 옵션별 재고 현황을 분석합니다.\n")
    print("-" * 40)

    # 5. JSON 데이터에서 사이즈와 재고량만 깔끔하게 뽑아내기
    # (API 응답 구조가 'data' -> 'inventories' 등에 있다고 가정한 로직)
    # 실제 응답 구조에 따라 데이터 파싱
    print(json.dumps(stock_data, indent=2, ensure_ascii=False)[:1000]) # 구조 파악을 위해 앞부분 출력
    
    # 🚨 API가 정상적으로 뚫리는지 이 출력 결과를 봐야 구글 시트 엑셀화가 가능합니다.

except requests.exceptions.RequestException as e:
    print(f"❌ 무신사 방어막에 막혔거나 네트워크 에러: {e}")
except Exception as e:
    print(f"⚠️ 에러 발생: {e}")
