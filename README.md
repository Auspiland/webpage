# Cloudflare workers
Cloudflare workers를 활용한 webpage test입니다.

## Monte Carlo Simulation Web App

Cloudflare Workers 기반의 몬테카를로 시뮬레이션 웹 애플리케이션입니다. 가챠 게임의 확률 분포를 시뮬레이션하고 정규분포 피팅 결과를 시각화합니다.

<!-- AUTO-UPDATE:START -->
## Dir Structure

```
# 루트 (프로젝트 최상위)
├── KV_INTEGRATION.md                      # KV 통합 문서: KV 데이터 키/값 포맷, 업로드/운영 가이드, 성능 비교
├── PERFORMANCE.md                          # 성능 최적화 문서: Assets 우선 전략, CPU/네트워크 비교, 메모리/응답 시간 분석
├── kv-upload/                              # KV 업로드 도구 및 예제 Worker (운영/배포 보조)
│   ├── README.md                           # kv-upload 사용법 및 예제
│   ├── upload-game-data.js                 # JSON -> KV 업로드 스크립트 (wrangler kv key put 사용). 설정: JSON_FILE_PATH, NAMESPACE_ID, KEY_PREFIX
│   └── worker-game-data.ts                 # KV를 읽어주는 예제 Cloudflare Worker (GET /game1/{key}, /game1/list, /game1/all) — CORS 및 예외 처리 포함
│
webpage/
├── assets/                                 # 정적 파일 (프론트엔드 + precomputed 데이터, CDN에 배포됨)
│   ├── index.html                          # 메인 HTML 페이지 (GOAL input에 max="20" 추가)
│   ├── app.js                              # 클라이언트 로직 (API 호출, UI 업데이트, SVG 렌더링).
│   │                                         # 변경: runSimulate에서 clientStart/fetch/parse/total 타이밍 계측. 이제 '성공 응답'일 때만 타이밍 콘솔 출력; 에러가 있으면 타이밍 출력 전에 throw.
│   ├── styles.css                          # 스타일시트
│   └── data/
│       ├── precomputed_game1_v2.json       # GAME_ID=1 압축 사전계산 데이터 (v2, [min_val, freq_list]) — ASSETS 우선 읽기 대상
│       └── precomputed_game2_v2.json       # GAME_ID=2 압축 사전계산 데이터 (v2, [min_val, freq_list])
│
├── src/                                    # 백엔드 로직 (Python Workers)
│   ├── entry.py                            # Workers 진입점 (라우팅, CORS, ASSETS 우선 조회)
│   │                                         # 변경/중요: request-level 타이밍 수집(request_timings), run_simulation 호출을 try/except로 감싸 예외 발생 시 traceback을 print로 로깅. 에러 응답에 디버깅 접두사("01_"/"02_") 포함.
│   └── logic/                              # 시뮬레이션/유틸 로직
│       ├── __init__.py
│       ├── compute.py                      # 런타임 경량화된 시뮬레이션 핸들러
│       │                                         # 제공 함수: decompress_totals, summarize, make_hist_svg, run_simulation
│       │                                         # run_simulation 반환: (summary_dict, svg_string, timing_dict). 라이브 샘플링/alias 관련 함수 제거(런타임 미사용).
│       ├── compute_not_used.py              # 아카이브/관리용 유틸 모음 (오프라인/백오피스 용)
│       │                                         # 보관 함수: compress_totals, build_pity_cdf, _build_alias_from_cdf, _alias_sample, _binomial_7, sample_total_draws
│       │                                         # I/O/전처리 유틸: load_precomputed_from_assets, load_precomputed_from_kv, generate_precomputed_data, save/load 등 — 운영자용/오프라인 precompute 생성 시 사용
│       ├── precomputed_game1.json          # (보존용) GAME_ID=1 원본 사전 계산 데이터 (디버그/생성용)
│       ├── precomputed_game2.json          # (보존용) GAME_ID=2 원본 사전 계산 데이터
│       ├── precomputed_game1_v2.json       # GAME_ID=1 압축 데이터 (v2) - 빈도 리스트 형식 (assets/data/)
│       └── precomputed_game2_v2.json       # GAME_ID=2 압축 데이터 (v2) - 빈도 리스트 형식 (assets/data/)
│
├── wrangler.toml                           # Cloudflare Workers 설정 (ASSETS 바인딩 + KV 네임스페이스)
│   ├─ (ASSETS) [assets] directory = "./assets", binding = "ASSETS"  # Assets 바인딩: precomputed JSON을 엣지에서 직접 읽도록 설정됨
│   └─ (KV) [[kv_namespaces]] binding = "GLOBAL" id = "<namespace-id>"  # KV 네임스페이스 바인딩 (운영/툴링용)
└── README.md                               # 프로젝트 설명 및 API/개발 가이드 (자동 갱신 메커니즘 포함)
```

- 중요 변경/요약 (간단)
  - src/logic/compute.py: 런타임 경량화. run_simulation은 (summary_dict, svg_string, timing_dict) 반환하며, 내부 단계별 타이밍("1_validation_ms", "2_decompress_ms", "3_summarize_ms", "4_svg_generation_ms", "5_total_compute_ms")을 수집.
  - src/logic/compute_not_used.py: 구 샘플링/전처리/파일·KV 유틸 보관. load_precomputed_from_assets/load_precomputed_from_kv 등 오프라인 유틸 포함. entry.py는 일부 유틸을 이 파일에서 import하도록 변경 가능.
  - src/entry.py: run_simulation 호출을 try/except로 감싸며 예외 발생 시 traceback을 print로 로그 출력하고 JSON 에러를 반환(에러 문자열에 "01_"/"02_" 접두사).
  - assets/app.js: 성공 응답일 때만 client-side 타이밍 출력. 에러 발생 시 타이밍 출력 전에 에러를 throw.

---

## Workflow

### 1. 클라이언트 요청 흐름 (업데이트)
```
사용자 입력 (index.html, GOAL 1~20)
    ↓
클라이언트 유효성 검사 (assets/app.js)
    - GOAL 범위 검사: 1 <= GOAL <= 20 (클라이언트에서 예외 throw 시 요청 중단)
    ↓
폼 제출 (app.js → runSimulate)
    - 클라이언트는 내부적으로 타이밍 계측을 시작(clientStartTime)
    ↓
POST /api/simulate  (요청 body 예: {"GAME_ID":1,"GOAL":5,"OBS_TOTAL":30, "N_SIMS"?:100000, "SEED"?:1234, "BINS"?:50})
    ↓
entry.py (라우팅, 요청 검증, CORS, 서버 타이밍 계측)
    - request-level 타이밍 수집 시작(t_request_start)
    - JSON 파싱 후 request_timings["0_parse_request_ms"] 기록
    - precomputed 로드 시 request_timings["1_load_assets_ms"] 기록
    - run_simulation 호출부는 try/except로 감싸여 있으며, 예외 발생 시 traceback을 print(f"[Error #{count}] ...")로 stdout에 로깅
    ↓
1) ASSETS(엣지)에서 사전계산 조회 시도:
    - 호출: precomputed_data = await load_precomputed_from_assets(self.env.ASSETS, game_id, goal)
    - precomputed_data 포맷: [min_val, freq_list] (v2 압축 포맷)
    - 만약 존재하지 않으면 즉시 400 응답 반환(현재 KV 폴백/라이브 샘플링 경로 비활성화)
    ↓
run_simulation(..., precomputed_data=precomputed_data)
    - run_simulation은 precomputed_data 필수(없으면 ValueError)
    - 내부 처리: decompress_totals → summarize → make_hist_svg
    - compute-level 단계별 타이밍 수집(compute_timings) — 예: "1_validation_ms","2_decompress_ms","3_summarize_ms","4_svg_generation_ms","5_total_compute_ms"
    - 반환값: (summary, svg, compute_timings)
    - entry.py에서 run_simulation 호출을 try/except로 감싸며 예외 발생 시 traceback을 print로 로그 출력하고 에러 JSON 반환(에러 메시지에 "01_" / "02_" 접두사 가능)
    ↓
entry.py:
    - request_timings["3_run_simulation_total_ms"] 등 추가 기록
    - compute_timings와 request_timings를 병합: all_timings = {**request_timings, **compute_timings}
    - 최종 JSON 응답에 "timings": all_timings 포함 (ms 단위)
    - 에러 발생시 반환되는 에러 메시지는 디버깅 접두사("01_" 또는 "02_")를 포함할 수 있음
    ↓
클라이언트 처리 (assets/app.js):
    - fetch/parse/total 타이밍 측정
    - 성공 응답인 경우에만 client-side 타이밍(및 서버 "timings")을 콘솔에 정렬 출력
    - 에러인 경우 타이밍 출력 전에 에러 throw
```

- 주요 라우트 (요약)
  - POST /api/simulate
    - 요청 body: { "GAME_ID", "GOAL", "OBS_TOTAL", "N_SIMS"?: int, "SEED"?: int, "BINS"?: int }
    - 처리 흐름:
      1. ASSETS에서 precomputed JSON 파일의 goal 인덱스 조회 (load_precomputed_from_assets — 유틸은 src/logic/compute_not_used.py에 보관).
      2. 항목이 없으면 400 에러 반환(실시간 시뮬레이션 및 KV 폴백 비활성화).
      3. 항목이 있으면 decompress_totals → run_simulation(요약/시각화 + compute 타이밍) → entry.py가 request 타이밍을 덧붙여 JSON 응답 반환(응답에 "timings" 필드 포함).
    - 에러/예외 처리:
      - run_simulation 호출부에 try/except가 추가되어, 예외 발생 시 traceback을 stdout에 print하고 에러 코드를 포함한 JSON을 반환(예: {"ok": False, "error": "01_<message>"}).
  - GET /api/health
    - 상태 확인: {"ok": true}

### 2. 시뮬레이션 파이프라인 (업데이트 요약)
- 2-1. 입력 검증
  - 클라이언트에서 GOAL 범위(1~20) 확인 (assets/app.js) + 서버(entry.py)에서 정수 변환/범위 검증 수행.
- 2-2. 데이터 소스 (현재)
  - ASSETS(엣지) 우선: assets/data/precomputed_game{1,2}_v2.json에서 goal 인덱스 조회 → [min_val, freq_list] 반환
  - KV 폴백: 런타임 경로에서 비활성화(운영/관리용 툴은 유지)
  - 라이브 샘플링: compute_not_used.py에 샘플링 알고리즘 보관(아카이브). 런타임에서는 미사용.
- 2-3. 통계/타이밍/시각화
  - totals 복원(decompress_totals) → summarize(mean, std, percentiles 등) → make_hist_svg(히스토그램 SVG 생성)
  - run_simulation은 compute_timings(예: "1_validation_ms", "2_decompress_ms", "3_summarize_ms", "4_svg_generation_ms", "5_total_compute_ms")을 수집하여 반환
  - entry.py는 request-level 타이밍(request_timings)을 수집하여 compute_timings과 병합 ⇒ 응답의 "timings" 필드 제공
  - 클라이언트는 fetch/parse/total 타이밍을 측정하고, 서버 타이밍을 받아 콘솔에 정렬 출력(성공 시)

### 3. 배포 / 운영 관련 (요약)
- wrangler.toml: ASSETS 바인딩 확인 (변경 없음)
```toml
[assets]
directory = "./assets"
binding = "ASSETS"
```
- 배포 (Assets 포함)
```bash
# assets/ 디렉토리(./assets/data/precomputed_game1_v2.json 등)를 포함하여 배포
npx wrangler publish  # 또는 npx wrangler deploy
```
- KV 네임스페이스 (운영/툴링용)
```bash
npx wrangler kv:namespace create "GLOBAL_STORE"
# wrangler.toml에 바인딩 추가: [[kv_namespaces]] binding = "GLOBAL" id = "<namespace-id>"
```
- precomputed JSON을 KV로 업로드 (관리자용; 런타임은 KV 폴백 미사용)
```bash
cd kv-upload
node upload-game-data.js  # 설정: JSON_FILE_PATH, NAMESPACE_ID, KEY_PREFIX
npx wrangler kv key list --namespace-id="<NAMESPACE_ID>" --prefix="game1_"
npx wrangler kv key get --namespace-id="<NAMESPACE_ID>" "game1_5"
```

---

## Features

### 핵심 기능 (핵심 5개 항목)

1. 런타임 경량화된 요약/시각화 파이프라인
   - 주요 구현: src/logic/compute.run_simulation — precomputed_data를 이용해 decompress_totals → summarize → make_hist_svg를 실행.
   - 반환형: (summary_dict, svg_string, timing_dict). timing_dict은 단계별 소요(ms)를 포함.
   - 설계: 실시간 샘플링 대신 오프라인 precompute를 사용하여 엣지에서 빠른 응답 제공.

2. ASSETS 기반 사전계산(Precomputed) 우선 전략
   - 데이터 포맷: v2 압축 - [min_val, freq_list] (assets/data/precomputed_game{1,2}_v2.json).
   - 로드 유틸: load_precomputed_from_assets (관리/오프라인 유틸은 src/logic/compute_not_used.py에 보관).
   - 장점: 엣지에서 직접 파일 조회 → 빠른 압축 해제 및 통계/시각화 생성.

3. 운영/관리용 오프라인 툴 및 KV 업로드
   - kv-upload/upload-game-data.js: precomputed JSON을 KV에 업로드(관리자용).
   - src/logic/compute_not_used.py: precompute 생성(generate_precomputed_data), compress/저장(save/load), KV I/O 관련 유틸 보관 — 오프라인/백오피스 용도.

4. 다중 게임 모드 및 파라미터화
   - GAME_TABLE 기반 파라미터(예: CEIL_RATIO, MAX_T, BASE_P)는 유지되어 다양한 GAME_ID/GOAL 조합 지원.
   - precomputed 데이터는 goal별로 생성되어 run_simulation이 이를 받아 처리.

5. 웹 UI / 시각화 및 엔드투엔드 성능 계측
   - 입력: GAME_ID, GOAL, OBS_TOTAL (assets/index.html, assets/app.js)
   - 출력: summary JSON + make_hist_svg로 생성된 SVG
   - 성능 계측: 클라이언트(app.js)에서 fetch/parse/total 계측, 서버(entry.py + compute.py)에서 단계별 타이밍을 수집해 응답의 "timings" 필드로 제공.

### 기술적 특징

알고리즘
- Alias method 및 고성능 샘플링 알고리즘은 이전 구현에서 제공되며(src/logic/compute_not_used.py), 오프라인 precompute 생성 시 재사용 가능.
- 압축 포맷(v2): [min_val, freq_list] 구조로 빈도 기반 저장을 최소화하여 엣지 전송 비용 절감.

성능 / 계측
- 서버 측 타이밍
  - entry.py: request-level 타이밍 키 예: "0_parse_request_ms", "1_load_assets_ms", "3_run_simulation_total_ms", "4_total_request_ms"
  - compute.run_simulation: compute-level 타이밍 예: "1_validation_ms", "2_decompress_ms", "3_summarize_ms", "4_svg_generation_ms", "5_total_compute_ms"
  - 응답에 timings 딕셔너리 포함 → 상세 프로파일링 가능
- 클라이언트 측 타이밍
  - assets/app.js: fetch/parse/total 측정, 성공 응답 시 서버 timings과 함께 콘솔 출력
- 성능 기대치
  - ASSETS 조회 + decompress → 보통 매우 낮은 지연(대개 수 ms ~ 10ms 단위 내부 컴퓨트)
  - 라이브 샘플링 또는 KV 폴백 활성화 시 지연 급증 가능(수십 ms ~ 초)

보안 및 안정성
- CORS 헤더 설정 및 입력 검증(entry.py + client-side) 유지
- precomputed 부재 시 명확한 400 응답 반환
- 예외 처리: entry.py가 run_simulation 예외를 잡아 traceback을 stdout에 print하고 디버깅 접두사("01_"/"02_")를 에러 메시지에 포함하여 문제 추적을 돕도록 변경됨(운영 시 민감 정보 노출 여부 검토 및 필터링 권장)

CI / 도구
- README 자동 갱신 스크립트(.github/scripts/update_readme.py) 및 PERFORMANCE.md 참조
- compute_not_used.py는 아카이브된 구현과 오프라인 유틸을 포함하므로, precompute 생성/검증 시 참조 가능

---

## Versions

### v2.6 (2025-10-20)  <-- 최신 변경사항
**주요 변경사항**
- 서버/클라이언트 프로파일링 강화
  - src/entry.py에 request-level 타이밍 수집 로직 추가 및 request_timings 키 도입("0_parse_request_ms", "1_load_assets_ms", "3_run_simulation_total_ms", "4_total_request_ms").
  - src/logic/compute.run_simulation이 compute-level 단계 타이밍을 수집하여 반환하도록 변경(반환값: (summary, svg, compute_timings)).
  - entry.py는 compute_timings와 request_timings을 병합하여 API 응답의 "timings" 필드로 반환.
- 런타임 안정성 및 에러 로깅
  - entry.py에서 run_simulation 호출을 try/except로 감싸고 예외 발생 시 traceback을 print로 stdout에 로깅. 에러 응답 메시지에 디버깅 접두사("01_"/"02_")를 추가.
- 런타임 경량화
  - src/logic/compute.py에서 실시간 샘플링(alias/CDF/샘플링 함수 등)을 제거하고 decompress_totals / summarize / make_hist_svg 및 타이밍 수집에 집중.
- 오프라인/관리용 유틸 보관
  - src/logic/compute_not_used.py 추가: 기존 샘플링, alias method, compress/전처리, load/save 및 KV I/O 유틸을 아카이브하여 오프라인 precompute 생성 및 운영자 툴로 제공.

**최적화**
- 런타임 파일에서 불필요한 샘플링/전처리 코드 제거로 cold-start/임포트 비용 감소.
- ASSETS 우선 전략으로 엣지에서 파일 직접 로드하여 전체 응답 지연 최소화.

**버그 수정**
- 클라이언트 타이밍 출력 조건 변경: assets/app.js가 '성공 응답'일 때만 타이밍 콘솔 출력하도록 수정(에러 발생 시 타이밍 출력 이전에 throw).
- run_simulation 호출부에서 예외가 발생할 경우 명확한 에러 로그(print) 및 JSON 반환으로 운영 중 디버깅 용이성 개선.

**새 기능**
- 응답에 단계별 타이밍("timings") 포함 — 운영/성능 분석을 위해 서버/컴퓨트/클라이언트 타이밍을 종합 제공.

---

### v2.5 (2025-10-XX)
(이전 릴리스 요약 — 변경 없음에서 유지되는 항목)
- precomputed(v2) 포맷 도입: [min_val, freq_list]
- Assets 기반 precompute 우선 전략
- 오프라인 KV 업로드 도구(kv-upload)
- 히스토그램 SVG 생성(make_hist_svg) 및 summarize 기능 제공

<!-- AUTO-UPDATE:END -->
<!-- AUTO-UPDATE:END -->

<!-- LAST_PROCESSED_SHA: 82d544a137a787f68d75cd4bbe9f7e6e09a602aa -->
