#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
리아 성과 대시보드 자동 수집기 (Instagram Graph API → data/ria_kpi_feed.json)

설계 원칙
---------
1. 시크릿은 코드·레포·Drive에 절대 남기지 않는다. 토큰은 GitHub Actions Secrets
   (IG_ACCESS_TOKEN)에서 환경변수로만 주입받는다. 로그에도 출력하지 않는다.
2. 토큰이 없거나 API가 실패하면 **기존 피드를 건드리지 않고 exit 0** 한다.
   대시보드가 깨지는 것보다 어제 숫자가 그대로 보이는 게 낫다.
3. 사람이 쓴 편집 블록(strategy)은 절대 덮어쓰지 않는다. API가 만질 수 있는 것은
   측정값(measured / kpi.*.actual / content / progress.published)뿐이다.
4. 매 실행마다 data/ria_kpi_history.json 에 스냅샷 1건을 append 한다.
   추세선 없는 성과 대시보드는 숫자판이지 대시보드가 아니다.

실행:  python scripts/fetch_ria_kpi.py
환경:  IG_ACCESS_TOKEN (secret, 필수)  IG_USER_ID (var, 필수)
       IG_API_VERSION (기본 v21.0)     RIA_BASELINE_FOLLOWERS (기본 0)
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEED = os.path.join(ROOT, "data", "ria_kpi_feed.json")
HIST = os.path.join(ROOT, "data", "ria_kpi_history.json")

TOKEN = os.environ.get("IG_ACCESS_TOKEN", "").strip()
IG_USER = os.environ.get("IG_USER_ID", "").strip()
VER = os.environ.get("IG_API_VERSION", "v21.0").strip()
BASELINE_FOLLOWERS = int(os.environ.get("RIA_BASELINE_FOLLOWERS", "0") or 0)
BASE = "https://graph.facebook.com/%s" % VER

HIST_MAX = 400          # 하루 2회 × 약 6개월
MEDIA_LIMIT = 25        # 최근 게시물 조회 개수
WEEK_DAYS = 7


def log(msg):
    print("[ria-kpi] %s" % msg, flush=True)


# ---------------------------------------------------------------- HTTP


def api(path, **params):
    """Graph API GET. 실패 시 None 반환(예외 전파 안 함). 토큰은 로그에 남기지 않는다."""
    params["access_token"] = TOKEN
    url = "%s/%s?%s" % (BASE, path.lstrip("/"), urllib.parse.urlencode(params))
    safe = url.split("access_token=")[0] + "access_token=***"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "APLocaLift-RiaKPI/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8")[:300]
        except Exception:
            pass
        log("HTTP %s on %s :: %s" % (e.code, safe, body))
    except Exception as e:
        log("ERR on %s :: %s" % (safe, e))
    return None


def insights(path, metric_sets, period=None):
    """
    metric 이름은 Graph API 버전마다 바뀐다(impressions→views 등).
    후보 metric 세트를 순서대로 시도하고 처음 성공한 것을 쓴다.
    반환: {metric: value}
    """
    for metrics in metric_sets:
        for use_total in (True, False):
            p = {"metric": ",".join(metrics)}
            if period:
                p["period"] = period
            if use_total:
                p["metric_type"] = "total_value"
            res = api("%s/insights" % path, **p)
            if not res or "data" not in res:
                continue
            out = {}
            for row in res["data"]:
                name = row.get("name")
                if "total_value" in row and isinstance(row["total_value"], dict):
                    out[name] = row["total_value"].get("value")
                elif row.get("values"):
                    out[name] = row["values"][-1].get("value")
            if out:
                return out
    return {}


# ---------------------------------------------------------------- 수집


def collect():
    prof = api(IG_USER, fields="username,name,followers_count,media_count")
    if not prof or "followers_count" not in prof:
        log("프로필 조회 실패 — 토큰/권한/IG_USER_ID 확인 필요. 피드 미변경.")
        return None

    acct = insights(
        IG_USER,
        [
            ["reach", "views", "profile_views", "accounts_engaged", "total_interactions"],
            ["reach", "impressions", "profile_views"],
            ["reach"],
        ],
        period="day",
    )

    media = []
    res = api(
        "%s/media" % IG_USER,
        fields="id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count",
        limit=MEDIA_LIMIT,
    )
    for m in (res or {}).get("data", []):
        ins = insights(
            m["id"],
            [
                ["reach", "views", "saved", "shares"],
                ["reach", "plays", "saved", "shares"],
                ["reach", "impressions", "saved"],
                ["reach"],
            ],
        )
        views = ins.get("views") or ins.get("plays") or ins.get("impressions") or ins.get("reach") or 0
        cap = (m.get("caption") or "").strip().replace("\n", " ")
        media.append(
            {
                "id": m["id"],
                "date": (m.get("timestamp") or "")[:10],
                "ts": m.get("timestamp") or "",
                "title": (cap[:38] + "…") if len(cap) > 38 else (cap or "(캡션 없음)"),
                "format": fmt_label(m),
                "url": m.get("permalink", ""),
                "views": int(views or 0),
                "likes": int(m.get("like_count") or 0),
                "comments": int(m.get("comments_count") or 0),
                "saves": int(ins.get("saved") or 0),
                "shares": int(ins.get("shares") or 0),
                "reach": int(ins.get("reach") or 0),
            }
        )

    followers = int(prof["followers_count"])
    snap = {
        "at": datetime.now(KST).isoformat(timespec="seconds"),
        "followers": followers,
        "media_count": int(prof.get("media_count") or 0),
        "reach_day": int(acct.get("reach") or 0),
        "views_day": int(acct.get("views") or acct.get("impressions") or 0),
        "profile_views_day": int(acct.get("profile_views") or 0),
        "interactions_day": int(acct.get("total_interactions") or 0),
    }
    return {"profile": prof, "snapshot": snap, "media": media}


def fmt_label(m):
    p = (m.get("media_product_type") or "").upper()
    t = (m.get("media_type") or "").upper()
    if p == "REELS":
        return "Reels"
    if t == "CAROUSEL_ALBUM":
        return "Carousel"
    if t == "VIDEO":
        return "Video"
    return "Image"


# ---------------------------------------------------------------- 집계


def weekly(media):
    """최근 7일 게시물 기준 주간 집계."""
    cut = datetime.now(timezone.utc) - timedelta(days=WEEK_DAYS)
    win = []
    for m in media:
        try:
            ts = datetime.fromisoformat(m["ts"].replace("+0000", "+00:00"))
        except Exception:
            continue
        if ts >= cut:
            win.append(m)
    reels = [m for m in win if m["format"] == "Reels"]
    return {
        "posts": len(win),
        "reels": len(reels),
        "reel_avg_views": int(sum(m["views"] for m in reels) / len(reels)) if reels else None,
        "saves": sum(m["saves"] for m in win),
        "comments": sum(m["comments"] for m in win),
        "shares": sum(m["shares"] for m in win),
        "reach": sum(m["reach"] for m in win),
        "views": sum(m["views"] for m in win),
    }


# label → 측정값 계산 함수. 여기 없는 label은 사람이 관리하는 값이므로 손대지 않는다.
def kpi_actuals(followers, wk):
    net = followers - BASELINE_FOLLOWERS
    return {
        "팔로워 순증": net,
        "팔로워 (4주 목표)": net,
        "릴 평균 조회수": wk["reel_avg_views"],
        "주간 저장수": wk["saves"],
        "주간 댓글수": wk["comments"],
        "저장수 (주)": wk["saves"],
    }


# ---------------------------------------------------------------- 병합·저장


def load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def atomic_write(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def main():
    if not TOKEN or not IG_USER:
        log("IG_ACCESS_TOKEN / IG_USER_ID 미설정 — 자동수집 건너뜀(정상 종료). "
            "기존 피드를 그대로 유지합니다.")
        return 0

    got = collect()
    if not got:
        return 0

    feed = load(FEED, None)
    if not isinstance(feed, dict):
        log("기존 피드를 읽을 수 없음 — 안전상 중단(피드 미변경).")
        return 0

    followers = got["snapshot"]["followers"]
    wk = weekly(got["media"])
    acts = kpi_actuals(followers, wk)

    # --- kpi.actual 갱신 (label 매칭된 것만. target/note/편집문구는 보존) ---
    updated = 0
    for seg in ("weekly", "monthly"):
        for row in (feed.get("kpi") or {}).get(seg, []) or []:
            v = acts.get(row.get("label"))
            if v is None:
                continue
            row["actual"] = v
            row["pending"] = False
            updated += 1

    # --- 콘텐츠 성과 테이블: 실데이터로 교체 ---
    content = sorted(got["media"], key=lambda m: m["ts"], reverse=True)[:12]
    feed["content"] = [
        {k: m[k] for k in ("date", "title", "format", "url", "views", "likes", "comments", "saves")}
        for m in content
    ]
    feed["content_sample"] = False

    # --- 원시 측정 블록(대시보드 확장용) ---
    feed["measured"] = {
        "live": True,
        "followers": followers,
        "media_count": got["snapshot"]["media_count"],
        "baseline_followers": BASELINE_FOLLOWERS,
        "day": {
            "reach": got["snapshot"]["reach_day"],
            "views": got["snapshot"]["views_day"],
            "profile_views": got["snapshot"]["profile_views_day"],
            "interactions": got["snapshot"]["interactions_day"],
        },
        "week": wk,
        "engagement_rate_pct": round(
            (wk["saves"] + wk["comments"] + wk["shares"]) / wk["reach"] * 100, 2
        ) if wk["reach"] else None,
    }

    # --- 주간 진행 현황: 게시 실적만 실데이터로 ---
    prog = feed.get("progress")
    if isinstance(prog, dict):
        prog["published"] = wk["posts"]
        feed["progress_sample"] = False

    # --- meta ---
    meta = feed.setdefault("meta", {})
    meta["sample"] = False
    meta["auto"] = True
    meta["updated_at"] = got["snapshot"]["at"]
    meta["owner"] = "리아 (@%s)" % got["profile"].get("username", "lia_park55")
    meta["source"] = "Instagram Graph API %s 자동 수집 (GitHub Actions)" % VER
    meta["schema_version"] = "0.3"
    meta["note"] = ("전략 블록은 사람이 관리하는 편집 데이터이며 자동수집이 덮어쓰지 않는다. "
                    "KPI actual·콘텐츠 성과·측정 블록은 IG Graph API 실값이다.")

    atomic_write(FEED, feed)

    # --- history append ---
    hist = load(HIST, {"schema_version": "1.0", "snapshots": []})
    snaps = hist.get("snapshots", [])
    snaps.append(dict(got["snapshot"], week_saves=wk["saves"], week_comments=wk["comments"],
                      week_reel_avg_views=wk["reel_avg_views"]))
    hist["snapshots"] = snaps[-HIST_MAX:]
    hist["updated_at"] = got["snapshot"]["at"]
    atomic_write(HIST, hist)

    log("완료 — 팔로워 %s · 주간(게시 %s/저장 %s/댓글 %s) · KPI %s행 갱신 · 히스토리 %s건"
        % (followers, wk["posts"], wk["saves"], wk["comments"], updated, len(hist["snapshots"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
