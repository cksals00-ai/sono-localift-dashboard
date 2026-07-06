#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
소노 로컬리프트 대시보드 · 데이터 자동 수집기
공공데이터포털(한국관광공사 빅데이터) OpenAPI → data/dashboard_data.json

실행: python scripts/fetch_data.py
필요 환경변수: DATA_GO_KR_KEY  (공공데이터포털 발급 서비스키, Decoding 키 권장)

동작 원칙
- 키가 없거나 API 호출이 실패하면, 기존 dashboard_data.json을 보존하고
  meta.updated / meta.isSample 만 갱신한다 (대시보드가 절대 깨지지 않도록).
- 성공 시 최근 24개월 방문자수 + 12개월 관광수요/점유율 구조로 저장.

주의
- 아래 ENDPOINT/OPERATION/파라미터는 발급 시 함께 제공되는
  'TourAPI_Guide_(관광빅데이터) v4.1' 명세로 최종 확인 후 맞추세요.
- 지역코드(areaCd=시도, signguCd=시군구)도 명세의 코드표를 따릅니다.
"""
import os, json, sys, datetime as dt
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "dashboard_data.json"

# ── 앵커 지역 설정 (홍천군: 시도=강원 51, 시군구=홍천 51720 — 명세 코드표로 확정) ──
ANCHOR = {
    "name": "강원 홍천군 (소노벨·소노문 비발디파크 / 오션월드)",
    "areaCd": os.getenv("ANCHOR_AREA_CD", "51"),      # 강원특별자치도
    "signguCd": os.getenv("ANCHOR_SIGNGU_CD", "51720"),  # 홍천군
}

# 공공데이터포털 관광빅데이터 게이트웨이 (명세로 최종 확인)
BASE = "https://apis.data.go.kr/B551011/DataLabService"
OP_VISITORS = "locgoRegnVisitrDDList"   # 기초지자체 방문자수 (일자별)
KEY = os.getenv("DATA_GO_KR_KEY", "").strip()


def month_range(n=24):
    today = dt.date.today().replace(day=1)
    months = []
    for i in range(n, 0, -1):
        y = today.year; m = today.month - i
        while m <= 0: m += 12; y -= 1
        months.append(f"{y:04d}-{m:02d}")
    return months


def api_get(op, params):
    q = urlencode({**params, "serviceKey": KEY, "MobileOS": "ETC",
                   "MobileApp": "SonoLift", "_type": "json"}, safe="%")
    url = f"{BASE}/{op}?{q}"
    req = Request(url, headers={"User-Agent": "SonoLift/1.0"})
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_visitors():
    """최근 24개월 월별 방문자수 합계. 명세 응답 필드에 맞춰 파싱 조정 필요."""
    months = month_range(24)
    start = months[0].replace("-", "") + "01"
    end = dt.date.today().replace(day=1).strftime("%Y%m%d")
    data = api_get(OP_VISITORS, {
        "numOfRows": 10000, "pageNo": 1,
        "startYmd": start, "endYmd": end,
        "areaCd": ANCHOR["areaCd"], "signguCd": ANCHOR["signguCd"],
    })
    items = data["response"]["body"]["items"]["item"]
    if isinstance(items, dict): items = [items]
    agg = {m: 0 for m in months}
    for it in items:
        ymd = str(it.get("baseYmd") or it.get("basYmd") or "")
        cnt = float(it.get("touNum") or it.get("visitorCnt") or it.get("cnt") or 0)
        key = f"{ymd[:4]}-{ymd[4:6]}" if len(ymd) >= 6 else None
        if key in agg: agg[key] += cnt
    return months, [round(agg[m]) for m in months]


def load_existing():
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return None


def main():
    existing = load_existing()
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")

    if not KEY:
        print("[warn] DATA_GO_KR_KEY 미설정 → 기존 데이터 유지, 샘플 표기")
        if existing:
            existing["meta"]["updated"] = now
            existing["meta"]["isSample"] = True
            OUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    try:
        labels, values = fetch_visitors()
        base = existing or {}
        base.setdefault("timing", FALLBACK_TIMING)
        base.setdefault("scoring", FALLBACK_SCORING)
        base.setdefault("kpi", FALLBACK_KPI)
        base["visitors"] = {"labels": labels, "values": values}
        base["meta"] = {
            "updated": now,
            "anchor": ANCHOR["name"],
            "anchorType": "인구감소지역 · 우대지원",
            "source": "공공데이터포털 · 한국관광공사 빅데이터 (지역별 방문자수 15101972)",
            "isSample": False,
            "note": "GitHub Actions가 매일 06:00(KST) 자동 갱신",
        }
        OUT.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] 방문자수 {len(values)}개월 갱신 완료 → {OUT}")
        return 0
    except (HTTPError, URLError, KeyError, ValueError) as e:
        print(f"[error] API 실패({e}) → 기존 데이터 보존")
        if existing:
            existing["meta"]["updated"] = now
            OUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1


# 방문자수만 API로 받고, 나머지 축은 초기 구조 유지 (추후 API 추가 시 확장)
FALLBACK_TIMING = {"months": ["1월","2월","3월","4월","5월","6월","7월","8월","9월","10월","11월","12월"],
                   "demandIndex": [88,80,58,62,72,66,95,100,70,78,64,90],
                   "sonoOccupancy": [72,68,55,58,63,60,85,90,64,70,58,80]}
FALLBACK_SCORING = {"labels": ["홍천(비발디)","고성(델피노)","청송","영덕","단양","부안(변산)"],
                    "values": [4.45,4.35,4.30,4.30,4.00,3.95]}
FALLBACK_KPI = [
    {"name":"지역 방문자 증가","unit":"%","bench":"+18%","target":"+15%","source":"이동통신 방문자수"},
    {"name":"지역 관광 소비 유도액","unit":"억원","bench":"69억","target":"30억","source":"신용카드 지출액"},
    {"name":"지역화폐/쿠폰 사용률","unit":"%","bench":"+71%","target":"+50%","source":"지자체+소노 발권"},
    {"name":"비수기 가동률 개선","unit":"%p","bench":"-","target":"+8%p","source":"소노 대시보드"},
    {"name":"생산유발효과","unit":"억원","bench":"240억","target":"100억","source":"산업연관표 추정"},
]

if __name__ == "__main__":
    sys.exit(main())
