# 소노 로컬리프트 · 데이터랩 대시보드

2026 한국관광 데이터랩 활용 경진대회(지역경제 기여 트랙) 파일럿 대시보드.
공공데이터포털(한국관광공사 빅데이터) OpenAPI를 **GitHub Actions가 매일 06:00(KST) 자동 호출** → `data/dashboard_data.json` 갱신 → **GitHub Pages**가 서빙합니다. 소노 GS팀 대시보드의 "구글시트 연동 + 06시 자동갱신"과 동일한 결의 무(無)서버 구조입니다.

## 구성

```
index.html                     대시보드(단일 파일, Chart.js CDN) — 샘플 데이터로 즉시 렌더
data/dashboard_data.json       화면이 읽는 데이터 (Actions가 자동 갱신)
scripts/fetch_data.py          공공데이터포털 API 수집기 (키 없으면 기존 데이터 보존)
.github/workflows/update-data.yml  매일 06:00 KST cron + 수동 실행
```

## 배포 (5분)

1. 이 폴더를 GitHub 새 저장소에 푸시
   ```bash
   git init && git add . && git commit -m "init: sono localift dashboard"
   git branch -M main
   git remote add origin https://github.com/<계정>/sono-localift-dashboard.git
   git push -u origin main
   ```
2. **Settings → Pages** → Source: `main` / `/ (root)` → 저장. 몇 분 뒤 `https://<계정>.github.io/sono-localift-dashboard/` 공개.
3. 이 시점에서 이미 **샘플 데이터로 대시보드가 동작**합니다.

## 실데이터 자동 연동 (서비스키 등록)

1. 공공데이터포털에서 서비스키 발급 (무료, 개발계정 자동승인)
   - [지역별 방문자수 (15101972)](https://www.data.go.kr/data/15101972/openapi.do) → **활용신청**
   - (선택) [지역별 관광 수요 강도 (15151868)](https://www.data.go.kr/data/15151868/openapi.do),
     [방문자 추이 예측 (15128555)](https://www.data.go.kr/data/15128555/openapi.do)
   - 발급 후 함께 제공되는 **TourAPI_Guide(관광빅데이터) v4.1** 명세로 엔드포인트·파라미터·지역코드 확인
2. GitHub → **Settings → Secrets and variables → Actions**
   - **New repository secret**: `DATA_GO_KR_KEY` = 발급받은 Decoding 서비스키
   - (선택) **Variables**: `ANCHOR_AREA_CD`(예 51=강원), `ANCHOR_SIGNGU_CD`(예 51720=홍천) — 앵커 지역 변경용
3. **Actions 탭 → Update dashboard data → Run workflow**로 즉시 1회 실행. 이후 매일 06:00 KST 자동 갱신.

> `scripts/fetch_data.py` 상단의 `BASE / OP_VISITORS / 파라미터 / 지역코드`는
> 발급 시 제공되는 공식 명세로 최종 확인해 맞추세요. 키가 없거나 호출이 실패하면
> 기존 데이터를 보존하므로 화면이 깨지지 않습니다.

## 데이터 해석 유의
- '방문자수'는 일자별 순방문자(2박3일=3명 집계), 광역·기초 합산 불가. 상세는 [데이터랩 데이터 설명](https://datalab.visitkorea.or.kr) 참조.
- 인구감소지역 지정은 [행정안전부 고시](https://www.mois.go.kr/frt/sub/a06/b06/populationDecline/screen.do) 기준.

## 데이터 출처
공공데이터포털 · 한국관광공사 빅데이터 / 인구감소지역: 행정안전부 / 벤치마크: 2025 경진대회 대상(강진군, 공개 보도)
