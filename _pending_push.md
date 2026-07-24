# 대기 중인 푸시/실행 명령 (맥에서 실행)

> 이 샌드박스는 `git push` 및 외부 URL 다운로드가 불가능합니다.
> 아래 명령을 **맥 로컬 레포**에서 실행해야 라이브(GitHub Pages)에 반영됩니다.

---

## [완료] 2026-07-24T14:35Z — 리아 대시보드 전략·KPI 실데이터(스키마 0.2) — 2026-07-25 동일 커밋에 포함되어 푸시 완료

> ⓘ `ria-dashboard.html` / `data/ria_kpi_feed.json`은 원격에 한 번도 커밋된 적이 없어(신규 파일), 12:05Z 골격 블록과 14:35Z 실데이터 블록이 **단일 커밋으로 함께 게시**됨. 워킹트리 실체가 이미 schema_version 0.2였음.


**목적:** 기획실장 지시(0724_지시_리아대시보드_IG전략KPI_실데이터반영) 반영분 라이브 게시.
- 수정: `data/ria_kpi_feed.json` — SAMPLE(0.1) → **실데이터 스키마 0.2**. strategy(포지셔닝·슬로건·타깃 3층·채널 역할·필러 5·주간 편성 월~일) + kpi(baseline_date 2026-07-24, 팔로워 931→3,000 등, 미측정 지표는 pending) 실데이터. content/progress는 리아 실피드(7/25 오전) 도착 전까지 SAMPLE 유지.
- 수정: `ria-dashboard.html` — 전략 블록 렌더 확장(타깃/채널/필러5/주간편성), KPI pending 카드 처리 + baseline 표기, **블록별 배지**(전략·KPI = LIVE, 콘텐츠·진행 = SAMPLE), 상단 배지 "LIVE · 콘텐츠 SAMPLE".
- ⚠ 코드/데이터 변경만 — 외부 자산 다운로드 없음. auth 변경 없음(A안 GSNAuth 유지).

```bash
cd ~/Documents/Claude/Projects/"한국관광공사 데이터 랩 공모전"/sono-localift-dashboard
git fetch origin
git log --oneline origin/main..HEAD   # 이전 미푸시 커밋(대시보드 골격 등)도 함께 확인
git add ria-dashboard.html data/ria_kpi_feed.json
git commit -m "feat: 리아 대시보드 전략·KPI 실데이터 반영(ria_kpi_feed 스키마 0.2, baseline_date) + 블록별 LIVE/SAMPLE 배지"
git push origin main

# 라이브 검증 (Pages 빌드 1~2분 후, admin 로그인 상태에서)
#   https://cksals00-ai.github.io/sono-localift-dashboard/ria-dashboard.html
#     · 전략 블록 = LIVE 배지, 타깃 3층·채널 역할·필러 5·주간 편성(월~일) 노출
#     · KPI 블록 = LIVE·baseline 2026-07-24, 팔로워 931/3,000 막대, 미측정 지표 '측정 대기'
#     · 콘텐츠 현황·진행 현황 = SAMPLE 배지 유지
#   https://cksals00-ai.github.io/sono-localift-dashboard/data/ria_kpi_feed.json  (200·schema_version 0.2)
```

**후속:** 리아 실피드(ria_kpi_feed.json 원본) 7/25 오전 첫 수신 예정 — 도착 시 content/progress를 실데이터로 교체하고 SAMPLE 배지 제거.

---

## [완료] 2026-07-24T09:29Z — 리아 성과 대시보드 신설(골격+샘플) — 12:05Z 블록과 동일 대상, 2026-07-25 동일 커밋으로 해소

**목적:** 기획실장 지시(0724_리아성과대시보드) ① 단계 반영분 라이브 게시.
- 신규: `ria-dashboard.html` (admin 전용 · auth.js 가드 · 다크+골드 · 4블록: 전략/KPI/콘텐츠/진행)
- 신규: `data/ria_kpi_feed.json` (SAMPLE 골격 · 리아 1일2회 갱신 슬롯 · 정식 스키마 도착 시 교체)
- 수정: `action-board.html` nav 에 "리아 대시보드" admin 탭 추가(+admin 노출 스크립트)

```bash
cd ~/Documents/Claude/Projects/"한국관광공사 데이터 랩 공모전"/sono-localift-dashboard
git add ria-dashboard.html data/ria_kpi_feed.json action-board.html
git commit -m "feat: 리아 성과 대시보드(ria-dashboard.html) 신설 + ria_kpi_feed.json 샘플 골격 + 액션보드 nav 연결(admin 전용)"
git push origin main

# 라이브 검증 (Pages 빌드 1~2분 후, admin 로그인 상태에서)
#   https://cksals00-ai.github.io/sono-localift-dashboard/ria-dashboard.html   (4블록 렌더·SAMPLE 배지·KPI 주간/월간 토글)
#   https://cksals00-ai.github.io/sono-localift-dashboard/data/ria_kpi_feed.json (200·JSON)
#   액션보드 nav 에 "리아 대시보드" 탭 노출(admin)
```

**후속(대표님 조치 필요):** 구글 로그인(지시 ③단계)은 Dispatch 회신 도착 → 그러나 GitHub Pages origin 등록용 **신규 OAuth Client ID 발급이 선행**되어야 함. 발급 후 값을 교신함(to_온라인팀장)에 회신 주시면 반영. ※ 기존 사이트는 이미 GSNAuth(백엔드) 기반 구글 로그인이 있어, "기존 백엔드 유지 vs Dispatch 순수 클라이언트 화이트리스트로 전환" 방향 확인 필요(보고서 참조).

---

## ✅ 2026-07-24T08:57Z 기준 — 아래 대기분 전부 해소됨 (기획실장 확인)

대표님이 맥에서 `_pending_push.md` 명령을 직접 실행 완료했고, 기획실장 라이브 검증에서 전부 정상 확인됨:
- `products/detail.html` 200 (섹션 #p1~#p10 = 10개, 훅·DEMO 배너 정상)
- `shop.html` Details 앵커 10개 연결, 3×3·05 숨김 유지
- `proposal-sono` / `ir`(4축) / 액션보드 통합 모두 라이브

→ 아래 "2026-07-24T05:37Z" 블록은 **원격 반영 완료**. 신규 대기 명령은 이 배너 아래에 계속 누적.

---

## [완료] 2026-07-24T05:37Z — 온라인팀장 자동반영 (shop 3×3 + 상세페이지 v2) — 원격 반영·라이브 검증 확인(기획실장, 08:57Z)

**목적:** 기획실장 지시 3건 반영분을 라이브에 게시.
- 상세페이지 v2 신규 게시: `products/detail.html` (앵커 #p1~#p10)
- shop.html: 05 조선미녀 placeholder 숨김(hidden), 이미지 없는 SKU 제외 → 9종 3×3, 카드 Details → 상세앵커 라우팅

**⚠ 중요 — 라이브 미반영(404) 원인 점검:**
기획실장 검증에서 proposal-sono.html 404 / ir.html 3축 / shop 슬롯 미반영이 보고됨.
로컬 커밋은 있으나 **원격(origin)에 실제 푸시가 안 됐을 가능성**이 큽니다.
아래 명령으로 **미푸시 커밋 유무를 먼저 확인 후 한 번에 푸시**하세요.

```bash
cd ~/Documents/Claude/Projects/"한국관광공사 데이터 랩 공모전"/sono-localift-dashboard

# 0) 원격 동기화 상태 확인
git fetch origin
git log --oneline origin/main..HEAD   # 여기에 커밋이 뜨면 = 아직 푸시 안 된 것

# 1) 이번 자동반영분 커밋
git add products/detail.html shop.html
git commit -m "feat: 상세페이지 v2(products/detail.html #p1~p10) 게시 + shop 9종 3x3·05숨김·Details 앵커 라우팅"

# 2) 푸시 (이전 미푸시 커밋 IR 4축·proposal-sono·마켓워치통합 등도 함께 올라감)
git push origin main

# 3) 라이브 검증 (Pages 빌드 1~2분 후)
#   https://cksals00-ai.github.io/sono-localift-dashboard/proposal-sono.html   (404 해소 확인)
#   https://cksals00-ai.github.io/sono-localift-dashboard/ir.html              (K-Stay Boost 4축 노출 확인)
#   https://cksals00-ai.github.io/sono-localift-dashboard/shop.html            (9종 3x3·Details 클릭 시 detail.html 앵커 이동)
#   https://cksals00-ai.github.io/sono-localift-dashboard/products/detail.html (상세 v2 EN/VI·DEMO 배너)
```

**참고 — 상세페이지 이미지:** v2는 브랜드 CDN 직링크(데모)라 핫링크 차단 시 일부 이미지가 안 뜰 수 있습니다.
차단 대비 `onerror` placeholder("Image unavailable (brand CDN · demo)")를 자동 적용해 뒀으므로 레이아웃은 깨지지 않습니다.
정식 게시 전 자체 촬영본으로 교체 권장(재호스팅 원칙).

---

## [완료] 2026-07-24T12:05Z — 리아 성과 대시보드 골격 + 액션보드 나브 — 2026-07-25 커밋·푸시 완료

**목적:** 이전 자동반영분(리아 성과 대시보드 골격)을 라이브에 게시. 로컬에만 존재(origin 미푸시).
**대상 파일:** `ria-dashboard.html`(신규), `data/ria_kpi_feed.json`(신규 SAMPLE 피드), `action-board.html`(nav '리아 대시보드' admin 탭 추가)
**구글 로그인:** 대표님 A안 확정 — 기존 GSNAuth(js/auth.js) 백엔드 유지. **auth 코드 변경 없음**(구조 그대로). 이 푸시에 auth 파일 변경 포함 안 됨.

```bash
cd ~/Documents/Claude/Projects/"한국관광공사 데이터 랩 공모전"/sono-localift-dashboard

# 0) 원격 동기화 상태 확인(디버전스 방지)
git fetch origin
git log --oneline origin/main..HEAD   # 뜨는 커밋이 있으면 아직 푸시 안 된 것

# 1) 리아 대시보드 골격 커밋
git add ria-dashboard.html data/ria_kpi_feed.json action-board.html
git commit -m "feat: 리아 성과 대시보드 골격(ria-dashboard.html·SAMPLE 피드) + 액션보드 nav 리아 대시보드 admin 탭"

# 2) 푸시
git push origin main

# 3) 라이브 검증 (Pages 빌드 1~2분 후, admin 로그인 상태에서)
#   https://cksals00-ai.github.io/sono-localift-dashboard/ria-dashboard.html          (4블록·SAMPLE 배지)
#   https://cksals00-ai.github.io/sono-localift-dashboard/data/ria_kpi_feed.json      (200)
#   https://cksals00-ai.github.io/sono-localift-dashboard/action-board.html           (admin, nav '리아 대시보드' 노출)
```

**참고:** `ria_kpi_feed.json`은 SAMPLE(schema_version 0.1-draft). 리아 정식 스키마 도착 시 교신 합의 후 교체.
