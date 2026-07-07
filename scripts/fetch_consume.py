#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
소노 로컬리프트 · 지역 관광소비 지수 수집기 (풍선효과 외부검증)
공공데이터포털 · 한국관광공사 '지역별 관광 자원 수요'(15152138) OpenAPI
  → AreaTarResDemService/areaTarSvcDemList

■ 실규격 (2026-07 실호출 검증 완료)
- 필수: baseYm(YYYYMM), areaCd(법정동 시도)  · 옵션: signguCd(법정동 시군구), tarSvcDemIxCd(지표코드)
- 응답: response.body.items.item[] · 필드 tarSvcDemIxVal(지수 0~100)
- 지표코드: 1105 쇼핑업/1106 식음료/1107 숙박업/1108 여가서비스업 소비액, 1101~1104 SNS 언급량
- 데이터 갱신: 월 1회(매월 16일). 값은 원(KRW)이 아니라 '관광수요지수' 구성 지표값(상대지수).

출력: data/consume.json  (지역별 최신월 소비지수 + 숙박 소비지수 12개월 추이)
"""
import os, json, sys, time, datetime as dt
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "consume.json"
BASE = "https://apis.data.go.kr/B551011/AreaTarResDemService"   # 자원수요(15152138): 업종별 소비액·SNS
OP = "areaTarSvcDemList"
DS_BASE = "https://apis.data.go.kr/B551011/AreaTarDemDsService"  # 수요강도(15151868): 외지인 소비 강도
DS_OP = "areaTarExpDsList"
KEY = os.getenv("DATA_GO_KR_KEY", "").strip()
# 소비강도 지표: 2201 외지인 소비액, 2202 전체 대비 외지인소비액 비중, 2203 방문량 대비 소비액
DS_IX = {"2201": "out_spend", "2202": "out_ratio", "2203": "spend_per_visit"}

# 소노 소재 9개 인구감소 시군구 (법정동 areaCd/signguCd · 고성=강원 51820)
REGIONS = [
    {"key": "홍천군", "loc": "강원 홍천", "area": "51", "signgu": "51720", "hero": "비발디파크·오션월드"},
    {"key": "삼척시", "loc": "강원 삼척", "area": "51", "signgu": "51230", "hero": "소노 삼척"},
    {"key": "고성군", "loc": "강원 고성", "area": "51", "signgu": "51820", "hero": "소노문 델피노"},
    {"key": "양양군", "loc": "강원 양양", "area": "51", "signgu": "51830", "hero": "쏠비치 양양"},
    {"key": "부안군", "loc": "전북 부안", "area": "52", "signgu": "52800", "hero": "소노벨 변산"},
    {"key": "단양군", "loc": "충북 단양", "area": "43", "signgu": "43800", "hero": "소노 단양"},
    {"key": "남해군", "loc": "경남 남해", "area": "48", "signgu": "48840", "hero": "소노 남해"},
    {"key": "진도군", "loc": "전남 진도", "area": "46", "signgu": "46900", "hero": "소노캄 진도"},
    {"key": "청송군", "loc": "경북 청송", "area": "47", "signgu": "47750", "hero": "소노벨 청송"},
]
# 소비액 지표 (풍선효과=객실 외 지역 소비)
IX = {"1107": "lodge", "1106": "food", "1105": "shop", "1108": "leisure"}
IX_NM = {"lodge": "숙박업 소비액", "food": "식음료 소비액", "shop": "쇼핑업 소비액", "leisure": "여가서비스업 소비액",
         "out_spend": "외지인 소비액", "out_ratio": "외지인 소비비중", "spend_per_visit": "방문량 대비 소비액"}


def api(base, op, params):
    q = urlencode({**params, "serviceKey": KEY, "MobileOS": "ETC",
                   "MobileApp": "SonoLift", "_type": "json"}, safe="%")
    req = Request(f"{base}/{op}?{q}", headers={"User-Agent": "SonoLift/1.0"})
    last = None
    for attempt in range(3):                    # 502 등 일시오류 재시도
        try:
            with urlopen(req, timeout=60) as r:
                raw = r.read().decode("utf-8", errors="replace")
            break
        except (HTTPError, URLError) as e:
            last = e
            time.sleep(0.6 * (attempt + 1))
    else:
        raise last
    if not raw.lstrip().startswith("{"):
        raise ValueError(f"JSON 아님 ← {raw[:200]}")
    data = json.loads(raw)
    body = (data.get("response") or {}).get("body") or {}
    wrap = body.get("items")
    items = (wrap or {}).get("item", []) if isinstance(wrap, dict) else []
    if isinstance(items, dict):
        items = [items]
    return items


def get_val(area, signgu, ym, ixcd):
    """자원수요: 업종별 소비액 지수 (tarSvcDemIxVal)."""
    try:
        for it in api(BASE, OP, {"numOfRows": 10, "pageNo": 1, "baseYm": ym,
                                 "areaCd": area, "signguCd": signgu, "tarSvcDemIxCd": ixcd}):
            v = it.get("tarSvcDemIxVal")
            if v not in (None, ""):
                return round(float(v), 2)
    except (HTTPError, URLError, ValueError, KeyError):
        pass
    return None


def get_ds(area, signgu, ym, ixcd):
    """수요강도: 외지인 소비 강도 지수 (tarExpDsIxVal)."""
    try:
        for it in api(DS_BASE, DS_OP, {"numOfRows": 10, "pageNo": 1, "baseYm": ym,
                                       "areaCd": area, "signguCd": signgu, "tarExpDsIxCd": ixcd}):
            v = it.get("tarExpDsIxVal")
            if v not in (None, ""):
                return round(float(v), 2)
    except (HTTPError, URLError, ValueError, KeyError):
        pass
    return None


def latest_ym():
    """홍천 숙박소비액이 존재하는 최신 baseYm 탐색 (당월-1 부터 최대 6개월 역순)."""
    d = dt.date.today().replace(day=1)
    for i in range(1, 8):
        y, m = d.year, d.month - i
        while m <= 0:
            m += 12; y -= 1
        ym = f"{y:04d}{m:02d}"
        if get_val("51", "51720", ym, "1107") is not None:
            return ym
    return None


def month_seq(end_ym, n=12):
    y, m = int(end_ym[:4]), int(end_ym[4:6])
    out = []
    for _ in range(n):
        out.append(f"{y:04d}{m:02d}")
        m -= 1
        if m == 0:
            m = 12; y -= 1
    return list(reversed(out))


def main():
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec="seconds")
    if not KEY:
        print("[warn] DATA_GO_KR_KEY 미설정 → 스킵")
        return 0
    ym = latest_ym()
    if not ym:
        print("[error] 사용 가능한 baseYm을 찾지 못함")
        return 1
    print(f"[info] 최신 기준월 baseYm={ym}")

    # 1) 지역별 최신월 4개 소비지수
    by_region = []
    for r in REGIONS:
        row = {"key": r["key"], "loc": r["loc"], "hero": r["hero"]}
        for ixcd, name in IX.items():          # 자원수요: 업종별 소비액
            row[name] = get_val(r["area"], r["signgu"], ym, ixcd)
            time.sleep(0.05)
        for ixcd, name in DS_IX.items():        # 수요강도: 외지인 소비 강도
            row[name] = get_ds(r["area"], r["signgu"], ym, ixcd)
            time.sleep(0.05)
        by_region.append(row)
        print(f"  {r['key']}: 숙박={row['lodge']} 여가={row['leisure']} | 외지인소비비중={row['out_ratio']} 외지인소비액={row['out_spend']}")

    # 2) 숙박업 소비액(1107) 12개월 추이 — 9개 지역 평균
    months = month_seq(ym, 12)
    trend = []
    for mm in months:
        vals = [get_val(r["area"], r["signgu"], mm, "1107") for r in REGIONS]
        vals = [v for v in vals if v is not None]
        trend.append(round(sum(vals) / len(vals), 2) if vals else None)
        time.sleep(0.03)

    out = {
        "meta": {
            "updated": now, "baseYm": ym,
            "source": "데이터랩 지역별 관광 자원 수요(15152138)·수요강도(15151868) · AreaTarResDemService/AreaTarDemDsService",
            "note": "값=관광수요지수 구성 지표(상대지수 0~100, 원화 아님) · 월 1회(16일) 갱신 · 외지인소비비중=관광객이 지역 소비에서 차지하는 비중",
        },
        "ixName": IX_NM,
        "byRegion": by_region,
        "lodgeTrend": {"labels": [f"{m[:4]}-{m[4:6]}" for m in months], "values": trend},
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 지역 소비지수 {len(by_region)}개 지역 · baseYm {ym} → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
