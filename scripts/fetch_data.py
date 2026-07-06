#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
소노 로컬리프트 대시보드 · 데이터 자동 수집기
공공데이터포털(한국관광공사 관광빅데이터) OpenAPI → data/dashboard_data.json

실행: DATA_GO_KR_KEY=발급키 python scripts/fetch_data.py
필요 환경변수: DATA_GO_KR_KEY (공공데이터포털 일반 인증키)

■ 실규격 (2026-07 실호출로 검증 완료)
- 엔드포인트: https://apis.data.go.kr/B551011/DataLabService/locgoRegnVisitrDDList
- 중요: areaCd/signguCd 같은 '지역 필터 파라미터'를 넣으면
  INVALID_REQUEST_PARAMETER_ERROR 로 거부됨. → 필터 없이 전체를 받아 코드/이름으로 거른다.
- 응답: response.body.items.item[]
  · signguCode(법정동, 예: 종로 11110)  · signguNm(예: 홍천군)
  · touDivCd 1=현지인 2=외지인 3=외국인  · touNum(방문객수, float)  · baseYmd(YYYYMMDD)
- 월별 오퍼레이션 없음(일자별 DDList만) → 일자별로 받아 월합산.

동작 원칙
- 키가 없거나 호출이 실패하면 기존 dashboard_data.json 을 보존하고 meta 만 갱신(대시보드가 깨지지 않게).
- 성공 시 최근 N개월 '소노 9개 인구감소 시군구'의 월별 외지인+외국인(관광 유입) 합계를 저장.
"""
import os, json, sys, time, datetime as dt
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "dashboard_data.json"

BASE = "https://apis.data.go.kr/B551011/DataLabService"
OP = "locgoRegnVisitrDDList"        # 기초지자체(시군구) 방문자수 · 일자별
KEY = os.getenv("DATA_GO_KR_KEY", "").strip()
MONTHS = int(os.getenv("VISIT_MONTHS", "24"))   # 최근 몇 개월

# ── 소노 소재 인구감소 시군구 (이름으로 매칭) ──
#   이름은 전국에서 유일(고성군만 강원/경남 중복 → 강원 코드 51 로 한정)
TARGET_NAMES = {"홍천군", "부안군", "고성군", "청송군", "남해군", "삼척시", "단양군", "진도군", "양양군"}
GOSEONG_GANGWON_PREFIX = "51"       # 고성군 동명이역 방지 (강원=51)


def is_target(nm, code):
    if nm not in TARGET_NAMES:
        return False
    if nm == "고성군" and not str(code).startswith(GOSEONG_GANGWON_PREFIX):
        return False   # 경남 고성군 제외
    return True


def month_labels(n):
    first = dt.date.today().replace(day=1)
    out = []
    for i in range(n, 0, -1):
        y, m = first.year, first.month - i
        while m <= 0:
            m += 12; y -= 1
        out.append(f"{y:04d}-{m:02d}")
    return out


def api_page(op, params):
    q = urlencode({**params, "serviceKey": KEY, "MobileOS": "ETC",
                   "MobileApp": "SonoLift", "_type": "json"}, safe="%")
    url = f"{BASE}/{op}?{q}"
    req = Request(url, headers={"User-Agent": "SonoLift/1.0"})
    with urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8", errors="replace")
    preview = raw[:400].replace("\n", " ")
    if not raw.lstrip().startswith("{"):
        raise ValueError(f"JSON 아님(게이트웨이/인증 오류 추정) ← {preview}")
    data = json.loads(raw)
    resp = data.get("response")
    if resp is None:
        raise ValueError(f"'response' 없음(파라미터 오류 추정) ← {preview}")
    code = str((resp.get("header") or {}).get("resultCode", ""))
    if code not in ("0000", "00", ""):
        msg = (resp.get("header") or {}).get("resultMsg", "")
        raise ValueError(f"API 오류 resultCode={code} resultMsg={msg} ← {preview}")
    body = resp.get("body") or {}
    wrap = body.get("items")
    items = (wrap or {}).get("item", []) if isinstance(wrap, dict) else []
    if isinstance(items, dict):
        items = [items]
    return items, int(body.get("totalCount", 0) or 0)


def fetch_visitors(months):
    """일자별 전체 → 타깃 시군구 월별 외지인+외국인 합계."""
    start = months[0].replace("-", "") + "01"
    last = dt.date.today().replace(day=1) - dt.timedelta(days=1)   # 지난달 말일
    end = last.strftime("%Y%m%d")

    agg = defaultdict(float)          # 'YYYY-MM' -> 방문객 합
    by_region = defaultdict(lambda: defaultdict(float))  # region -> month -> 합
    matched_codes = {}

    page, rows_per = 1, 10000
    total = None; got = 0
    while True:
        items, tc = api_page(OP, {"numOfRows": rows_per, "pageNo": page,
                                  "startYmd": start, "endYmd": end})
        if total is None:
            total = tc
            print(f"[info] {OP} 전체 {total:,}행, 페이지당 {rows_per} → {(-(-total//rows_per))}페이지 예상")
        if not items:
            break
        for it in items:
            nm = it.get("signguNm", ""); code = it.get("signguCode", "")
            if not is_target(nm, code):
                continue
            div = str(it.get("touDivCd", ""))
            if div not in ("2", "3"):        # 외지인+외국인만(관광 유입)
                continue
            ymd = str(it.get("baseYmd", ""))
            key = f"{ymd[:4]}-{ymd[4:6]}" if len(ymd) >= 6 else None
            if not key:
                continue
            val = float(it.get("touNum") or 0)
            agg[key] += val
            by_region[nm][key] += val
            matched_codes[nm] = code
        got += len(items)
        if got >= total or len(items) < rows_per:
            break
        page += 1
        time.sleep(0.2)

    print(f"[info] 매칭된 시군구: " + ", ".join(f"{k}({v})" for k, v in sorted(matched_codes.items())))
    values = [round(agg.get(m, 0)) for m in months]
    regions = {nm: [round(by_region[nm].get(m, 0)) for m in months]
               for nm in sorted(by_region)}
    return values, regions, matched_codes


def load_existing():
    if OUT.exists():
        return json.loads(OUT.read_text(encoding="utf-8"))
    return None


def main():
    existing = load_existing()
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")
    months = month_labels(MONTHS)

    if not KEY:
        # 키가 없어도 마지막 실데이터를 절대 훼손하지 않는다(isSample 강제 변경 금지).
        # 단, 실데이터가 한 번도 없었던 초기 상태(isSample 부재)면 샘플로 표기.
        print("[warn] DATA_GO_KR_KEY 미설정 → 기존 데이터 보존(실데이터면 그대로 유지)")
        if existing:
            existing.setdefault("meta", {})
            existing["meta"]["updated"] = now
            existing["meta"].setdefault("isSample", True)
            OUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    try:
        values, regions, codes = fetch_visitors(months)
        if sum(values) == 0:
            raise ValueError("타깃 시군구 매칭 0건 — signguNm 매칭 규칙 확인 필요")
        base = existing or {}
        base.setdefault("timing", FALLBACK_TIMING)
        base.setdefault("scoring", FALLBACK_SCORING)
        base.setdefault("kpi", FALLBACK_KPI)
        base["visitors"] = {"labels": months, "values": values, "byRegion": regions}
        base["meta"] = {
            "updated": now,
            "anchor": "소노 소재 인구감소 시군구 9곳(홍천·부안·고성·청송·남해·삼척·단양·진도·양양)",
            "anchorType": "인구감소지역",
            "metric": "월별 외지인+외국인 방문객 합계(관광 유입) · 한국관광 데이터랩 이동통신",
            "source": "공공데이터포털 · 한국관광공사 관광빅데이터 locgoRegnVisitrDDList(15101972)",
            "matched": codes,
            "isSample": False,
            "note": "GitHub Actions가 매일 06:00(KST) 자동 갱신",
        }
        OUT.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[ok] 방문자수 {len(values)}개월 갱신 · 합계 {sum(values):,} → {OUT}")
        return 0
    except (HTTPError, URLError, ValueError, KeyError) as e:
        print(f"[error] API 실패({e}) → 기존 데이터 보존")
        if existing:
            existing.setdefault("meta", {})
            existing["meta"]["updated"] = now
            OUT.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        return 1


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
