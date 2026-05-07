import requests
import json

url = "https://goods-detail.musinsa.com/api2/goods/5190556/options/v2/prioritized-inventories"

headers = {
    "accept": "application/json",
    "content-type": "application/json",
    "origin": "https://www.musinsa.com",
    "referer": "https://www.musinsa.com/",
    "user-agent": "Mozilla/5.0"
}

payload = {
    "optionValueNos": [
        21518632,
        21518633,
        21518634,
        21518635,
        21518636,
        21518637,
        21518638,
        21518639,
        21518640,
        21518641,
        21518642,
        21518643,
        21518644,
        21518645,
        21518646,
        21518647,
        21518648,
        21518649,
        21518650
    ]
}

try:
    print("🚀 무신사 재고 API POST 테스트 시작")

    res = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=10
    )

    print("상태코드:", res.status_code)

    data = res.json()

    print("✅ API 응답 성공!\n")

    print(json.dumps(data, indent=2, ensure_ascii=False)[:5000])

except Exception as e:
    print("❌ 에러:", e)
