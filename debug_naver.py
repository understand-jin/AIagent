import requests
from bs4 import BeautifulSoup
import urllib.parse

keyword = "나보타"
encoded = urllib.parse.quote(keyword)
url = f"https://search.naver.com/search.naver?where=news&query={encoded}&sort=1"

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Referer": "https://search.naver.com/",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

resp = requests.get(url, headers=headers, timeout=10)
print("HTTP Status:", resp.status_code)
soup = BeautifulSoup(resp.text, "html.parser")

# li.bx 확인
li_bx = soup.select("li.bx")
print(f"li.bx 개수: {len(li_bx)}")

if li_bx:
    first = li_bx[0]
    print("\n--- 첫 번째 li.bx 내부 a 태그 ---")
    for a in first.find_all("a", href=True)[:6]:
        cls = a.get("class", [])
        href = a.get("href", "")[:80]
        text = a.get_text(strip=True)[:50]
        print(f"  class={cls}, text={repr(text)}, href={href}")

    print("\n--- li.bx[0] HTML (첫 600자) ---")
    print(str(first)[:600])
else:
    print("\n[li.bx 없음] — 다른 선택자 시도")

    # group_news 내부 탐색
    group = soup.select_one(".group_news")
    if group:
        print("group_news 내부 a 태그:")
        for a in group.find_all("a", href=True)[:8]:
            cls = a.get("class", [])
            text = a.get_text(strip=True)[:50]
            href = a.get("href", "")[:80]
            print(f"  class={cls}, text={repr(text)}, href={href}")
    else:
        print("group_news도 없음")
        # 페이지 자체 일부 출력
        print("\n--- 페이지 body 첫 1500자 ---")
        body = soup.find("body")
        if body:
            print(body.get_text()[:1500])
