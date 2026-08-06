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
DUR = os.path.join(ROOT, "data", "ria_media_duration.json")

DUR_NOTE = (
    "릴 영상 길이(초). 리텐션 = 평균 시청시간 ÷ 영상 길이 의 분모다. "
    "IG Graph API 가 미디어 길이를 주지 않으므로 사람이 한 번만 채운다(길이는 바뀌지 않는다). "
    "새 릴은 수집기가 값 null 로 자동 추가하므로, 숫자만 적어 넣으면 된다. "
    "null 인 항목은 리텐션이 계산되지 않고 판정에서 제외된다."
)

# 리텐션 분자 후보. Graph API 버전마다 이름이 다르므로 순서대로 시도한다.
RETENTION_METRICS = ["ig_reels_avg_watch_time", "ig_reels_video_view_total_time"]

RETENTION_PASS_PCT = 40.0   # 0730 v2: 40% 이상 = 성공
RETENTION_WINDOW = 5        # 통과 판정 = 직전 5개 중 3개 이상

TOKEN = os.environ.get("IG_ACCESS_TOKEN", "").strip()
IG_USER = os.environ.get("IG_USER_ID", "").strip()
VER = os.environ.get("IG_API_VERSION", "v21.0").strip()
BASELINE_FOLLOWERS = int(os.environ.get("RIA_BASELINE_FOLLOWERS", "0") or 0)
BASE = "https://graph.facebook.com/%s" % VER

HIST_MAX = 400          # 하루 2회 × 약 6개월
MEDIA_LIMIT = 25        # 최근 게시물 조회 개수
WEEK_DAYS = 7
POST_GAP_ALERT_H = 36   # 마지막 게시 후 36시간 초과 = 게시 중단 경보


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


HOME_COUNTRY = os.environ.get("RIA_HOME_COUNTRY", "KR").strip().upper()


def demographics():
    """
    팔로워 국가 분포를 얻는다. 반환: {국가코드: 팔로워수}. 실패하면 {}.

    v21 이후는 follower_demographics(metric_type=total_value, breakdown=country),
    구버전은 audience_country(period=lifetime) 다. 응답 구조가 서로 달라 둘 다 파싱한다.
    실패해도 예외를 던지지 않는다 — 설계 원칙 2(피드를 깨뜨리지 않는다).
    """
    # 1) 신형: follower_demographics + breakdown=country
    res = api(
        "%s/insights" % IG_USER,
        metric="follower_demographics",
        period="lifetime",
        metric_type="total_value",
        breakdown="country",
    )
    out = {}
    if res and res.get("data"):
        for row in res["data"]:
            tv = row.get("total_value") or {}
            for bd in tv.get("breakdowns") or []:
                for item in bd.get("results") or []:
                    dims = item.get("dimension_values") or []
                    if not dims:
                        continue
                    try:
                        out[str(dims[0]).upper()] = int(item.get("value") or 0)
                    except Exception:
                        continue
    if out:
        return out

    # 2) 구형: audience_country
    res = api("%s/insights" % IG_USER, metric="audience_country", period="lifetime")
    if res and res.get("data"):
        for row in res["data"]:
            vals = row.get("values") or []
            if not vals:
                continue
            v = vals[-1].get("value")
            if isinstance(v, dict):
                for cc, cnt in v.items():
                    try:
                        out[str(cc).upper()] = int(cnt or 0)
                    except Exception:
                        continue
    return out


def audience_split(by_country):
    """
    국가 분포 → 국내/해외 요약. 측정이 안 되면 measurable=False 로 둔다.
    측정값이 없는데 0% 라고 적지 않는다 — 그건 사실이 아니라 공백이다.
    """
    if not by_country:
        return {
            "measurable": False,
            "by_country": {},
            "home_country": HOME_COUNTRY,
            "home_followers": None,
            "foreign_followers": None,
            "foreign_pct": None,
            "top_foreign": [],
            "counted": 0,
        }
    total = sum(by_country.values())
    home = int(by_country.get(HOME_COUNTRY, 0))
    foreign = total - home
    top = sorted(
        ((cc, n) for cc, n in by_country.items() if cc != HOME_COUNTRY),
        key=lambda kv: kv[1],
        reverse=True,
    )[:10]
    return {
        "measurable": True,
        "by_country": dict(sorted(by_country.items(), key=lambda kv: kv[1], reverse=True)),
        "home_country": HOME_COUNTRY,
        "home_followers": home,
        "foreign_followers": foreign,
        "foreign_pct": round(foreign / total * 100, 1) if total else None,
        "top_foreign": [{"country": cc, "followers": n} for cc, n in top],
        "counted": total,
    }


def watch_time_ms(media_id, probe, plays=None):
    """
    릴 평균 시청시간(ms)을 얻는다. 없으면 None.
    ig_reels_avg_watch_time 이 우선이고, 없으면 총 시청시간 ÷ 재생수로 만든다.
    어떤 metric 이 되고 안 되는지를 probe 에 남긴다 — 권한 문제를 다음 실행 때
    로그를 뒤지지 않고 대시보드에서 바로 보기 위해서다.
    """
    for metric in RETENTION_METRICS:
        res = api("%s/insights" % media_id, metric=metric)
        if not res or "data" not in res or not res["data"]:
            if metric not in probe["metric_failed"]:
                probe["metric_failed"].append(metric)
            continue
        val = None
        for r in res["data"]:
            if isinstance(r.get("total_value"), dict):
                val = r["total_value"].get("value")
            elif r.get("values"):
                val = r["values"][-1].get("value")
        if val is None:
            continue
        if metric not in probe["metric_ok"]:
            probe["metric_ok"].append(metric)
        if metric == "ig_reels_video_view_total_time":
            if not plays:
                continue          # 분모(재생수)를 모르면 평균을 만들 수 없다
            return float(val) / float(plays)
        return float(val)
    return None


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

    aud = audience_split(demographics())
    if aud["measurable"]:
        log("팔로워 국가 분포 수집 성공 — 해외 %s%% (%s/%s)"
            % (aud["foreign_pct"], aud["foreign_followers"], aud["counted"]))
    else:
        log("팔로워 국가 분포 미수집 — 권한(instagram_manage_insights) 또는 "
            "팔로워 100명 미만 제한일 수 있다. 해외 비중은 공백으로 둔다.")

    media = []
    res = api(
        "%s/media" % IG_USER,
        fields="id,caption,media_type,media_product_type,permalink,timestamp,like_count,comments_count",
        limit=MEDIA_LIMIT,
    )
    durations = load(DUR, {"schema_version": "1.0", "note": DUR_NOTE, "durations": {}})
    dur_map = durations.get("durations") or {}
    probe = {"metric_tried": RETENTION_METRICS, "metric_ok": [], "metric_failed": [],
             "reels": 0, "with_avg_watch": 0, "with_duration": 0}

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
        row = {
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

        # --- 리텐션 원자료 (릴만). 분자=평균 시청시간, 분모=영상 길이 ---
        if row["format"] == "Reels":
            probe["reels"] += 1
            avg_ms = watch_time_ms(m["id"], probe, plays=ins.get("plays") or ins.get("views"))
            row["avg_watch_sec"] = round(avg_ms / 1000.0, 1) if avg_ms else None
            d = dur_map.get(m["id"])
            row["duration_sec"] = float(d) if isinstance(d, (int, float)) and d > 0 else None
            if row["avg_watch_sec"] is not None:
                probe["with_avg_watch"] += 1
            if row["duration_sec"] is not None:
                probe["with_duration"] += 1
            # 계산은 여기 한 곳에서만 한다 (단일 원천 규칙)
            row["retention_pct"] = (
                round(row["avg_watch_sec"] / row["duration_sec"] * 100, 1)
                if row["avg_watch_sec"] is not None and row["duration_sec"] else None
            )
            # 길이를 사람이 채울 수 있게 빈 칸을 만들어 둔다 (한 번만 채우면 된다)
            if m["id"] not in dur_map:
                dur_map[m["id"]] = None

        media.append(row)

    durations["durations"] = dur_map
    durations["note"] = DUR_NOTE
    durations["updated_at"] = datetime.now(KST).isoformat(timespec="seconds")
    atomic_write(DUR, durations)

    followers = int(prof["followers_count"])
    snap = {
        "at": datetime.now(KST).isoformat(timespec="seconds"),
        "followers": followers,
        "media_count": int(prof.get("media_count") or 0),
        "reach_day": int(acct.get("reach") or 0),
        "views_day": int(acct.get("views") or acct.get("impressions") or 0),
        "profile_views_day": int(acct.get("profile_views") or 0),
        "interactions_day": int(acct.get("total_interactions") or 0),
        "foreign_followers": aud["foreign_followers"],
        "foreign_pct": aud["foreign_pct"],
    }
    return {"profile": prof, "snapshot": snap, "media": media, "probe": probe,
            "audience": aud}


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


def retention_view(media):
    """
    유일한 관리 지표. 게시 시각 역순으로 릴 5개를 보고, 리텐션이 계산된 것만 판정한다.
    길이가 비어 계산이 안 된 건은 '아직 모름'이며 실패로 세지 않는다 — 모르는 것을
    실패로 세면 잠금이 잘못 걸린다.
    """
    reels = sorted([m for m in media if m.get("format") == "Reels"],
                   key=lambda m: m["ts"], reverse=True)[:RETENTION_WINDOW]
    known = [m for m in reels if m.get("retention_pct") is not None]
    passed = [m for m in known if m["retention_pct"] >= RETENTION_PASS_PCT]
    return {
        "window": RETENTION_WINDOW,
        "pass_threshold_pct": RETENTION_PASS_PCT,
        "measurable": len(known),
        "unmeasurable": len(reels) - len(known),
        "pass_count": len(passed) if known else None,
        "latest": [
            {"date": m["date"], "title": m["title"], "retention_pct": m.get("retention_pct"),
             "avg_watch_sec": m.get("avg_watch_sec"), "duration_sec": m.get("duration_sec")}
            for m in reels
        ],
    }


def hours_since_last_post(media):
    """마지막 게시 이후 경과 시간(h). 게시가 멈춘 것을 숫자로 잡기 위한 지표다."""
    ts_list = []
    for m in media:
        try:
            ts_list.append(datetime.fromisoformat(m["ts"].replace("+0000", "+00:00")))
        except Exception:
            continue
    if not ts_list:
        return None
    delta = datetime.now(timezone.utc) - max(ts_list)
    return round(delta.total_seconds() / 3600.0, 1)


# label → 측정값 계산 함수. 여기 없는 label은 사람이 관리하는 값이므로 손대지 않는다.
def kpi_actuals(followers, wk, ret, snap=None, aud=None, gap_h=None):
    net = followers - BASELINE_FOLLOWERS
    snap = snap or {}
    aud = aud or {}
    return {
        "직전 5개 중 리텐션 40% 이상": ret["pass_count"],
        "팔로워 순증 (참고)": net,
        "팔로워 순증": net,
        "팔로워 (4주 목표)": net,
        "릴 평균 조회수": wk["reel_avg_views"],
        "주간 저장수": wk["saves"],
        "주간 댓글수": wk["comments"],
        "저장수 (주)": wk["saves"],
        # --- 0806 v3: 팔로워 수 목표 폐기 후 들어온 관리 축 ---
        "주간 게시 건수": wk["posts"],
        "일일 도달": snap.get("reach_day"),
        "마지막 게시 후 경과 (시간)": gap_h,
        "해외 팔로워 비중 (%)": aud.get("foreign_pct"),
        "해외 팔로워 수": aud.get("foreign_followers"),
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
    ret = retention_view(got["media"])
    aud = got.get("audience") or {}
    gap_h = hours_since_last_post(got["media"])
    acts = kpi_actuals(followers, wk, ret, got["snapshot"], aud, gap_h)

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
        dict(
            {k: m[k] for k in ("date", "title", "format", "url", "views", "likes", "comments", "saves")},
            avg_watch_sec=m.get("avg_watch_sec"),
            duration_sec=m.get("duration_sec"),
            retention_pct=m.get("retention_pct"),
        )
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
        # 유일한 관리 지표. 계산은 이 스크립트 한 곳에서만 한다.
        "retention": ret,
        # 이 지표가 현재 권한으로 실제로 나오는지를 매 실행마다 기록한다.
        "retention_probe": got.get("probe"),
        # 0806 v3: 게시 무결성. 팔로워 감소의 원인은 게시 중단이었다.
        "posting": {
            "hours_since_last_post": gap_h,
            "alert_threshold_h": POST_GAP_ALERT_H,
            "stalled": (gap_h is not None and gap_h > POST_GAP_ALERT_H),
            "week_posts": wk["posts"],
        },
    }

    # --- 0806 v3: 팔로워 국가 분포 (외국인 팔로워 관리 축) ---
    feed["audience"] = aud

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
    meta["schema_version"] = "0.5"
    meta["note"] = ("전략 블록은 사람이 관리하는 편집 데이터이며 자동수집이 덮어쓰지 않는다. "
                    "KPI actual·콘텐츠 성과·측정 블록은 IG Graph API 실값이다. "
                    "리텐션은 평균 시청시간 ÷ 영상 길이이며, 계산은 수집기 한 곳에서만 한다. "
                    "영상 길이는 data/ria_media_duration.json 에 사람이 한 번만 채운다.")

    atomic_write(FEED, feed)

    # --- history append ---
    hist = load(HIST, {"schema_version": "1.0", "snapshots": []})
    snaps = hist.get("snapshots", [])
    snaps.append(dict(got["snapshot"], week_saves=wk["saves"], week_comments=wk["comments"],
                      week_reel_avg_views=wk["reel_avg_views"],
                      retention_pass_count=ret["pass_count"],
                      retention_measurable=ret["measurable"],
                      retention_unmeasurable=ret["unmeasurable"],
                      week_posts=wk["posts"],
                      hours_since_last_post=gap_h))
    hist["snapshots"] = snaps[-HIST_MAX:]
    hist["updated_at"] = got["snapshot"]["at"]
    atomic_write(HIST, hist)

    pr = got.get("probe") or {}
    log("완료 — 팔로워 %s · 주간(게시 %s/저장 %s/댓글 %s) · KPI %s행 갱신 · 히스토리 %s건"
        % (followers, wk["posts"], wk["saves"], wk["comments"], updated, len(hist["snapshots"])))
    log("리텐션 — 릴 %s개 중 시청시간 %s개 · 길이 %s개 · 판정가능 %s개 · 40%%↑ %s"
        % (pr.get("reels"), pr.get("with_avg_watch"), pr.get("with_duration"),
           ret["measurable"], ret["pass_count"]))
    if not pr.get("metric_ok"):
        log("⚠️ 평균 시청시간 metric 이 하나도 응답하지 않았습니다 — 권한/버전 확인 필요. "
            "실패 metric: %s" % ", ".join(pr.get("metric_failed") or []))
    if ret["unmeasurable"]:
        log("⚠️ 길이 미입력으로 판정 제외된 릴 %s개 — data/ria_media_duration.json 을 채우십시오."
            % ret["unmeasurable"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
