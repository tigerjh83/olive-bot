import os
import json
import gspread
from google.oauth2.service_account import Credentials

# 1. 깃허브 금고에서 신분증 꺼내기
secrets = os.environ.get("GOOGLE_CREDENTIALS")
creds_dict = json.loads(secrets)
creds = Credentials.from_service_account_info(creds_dict, scopes=[
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
])

# 2. 구글 시트 연결
client = gspread.authorize(creds)
# 여기에 형님의 구글 시트 이름을 적으세요 (나중에 수정 가능)
sheet = client.open("올리브영 실시간 금액 관리").sheet1

# 3. 테스트 데이터 쓰기
sheet.append_row(["날짜", "상품명", "가격", "링크"])
sheet.append_row(["2026-05-04", "테스트 상품", "10,000원", "https://oliveyoung.co.kr"])

print("시트에 데이터 쓰기 성공!")
