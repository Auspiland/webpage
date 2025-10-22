# Cloudflare workers
Cloudflare workers를 활용한 webpage test입니다.

## Monte Carlo Simulation Web App

Cloudflare Workers 기반의 몬테카를로 시뮬레이션 웹 애플리케이션입니다. 가챠 게임의 확률 분포를 시뮬레이션하고 정규분포 피팅 결과를 시각화합니다.

<!-- AUTO-UPDATE:START -->
## Dir Structure

```
# 루트
├── README.md                           # (프로젝트 README, 자동 갱신 섹션 포함)
├── PERFORMANCE.md                      # 성능 분석/측정 문서 (Assets 우선 전략, CPU/메모리 데이터)
├── KV_INTEGRATION.md                   # KV 통합 가이드: 키/값 포맷, 업로드/운영 절차, 예시 워크플로우
├── wrangler.toml                        # Cloudflare Workers 설정 (main, ASSETS 바인딩, KV 네임스페이스)
│
├── kv-upload/                           # 오퍼레이터용 KV 업로드 도구 및 예제 Worker
│   ├── README.md                        # kv-upload 사용법 (wrangler 명령, 네임스페이스 정보)
│   ├── upload-game-data.js              # JSON -> KV 업로드 스크립트 (wrangler kv key put 호출)
│   └── worker-game-data.ts              # KV 조회용 예제 Worker (GET /game1/{key}, /game1/list, /game1/all)
│
├── webpage/                             # 정적 프론트엔드(Assets) — ASSETS binding 으로 엣지/CDN에 배포
│   └── assets/
│       ├── index.html                   # SPA / UI: GAME_ID, GOAL(1~20), OBS_TOTAL 입력 폼
│       ├── app.js                       # 클라이언트 로직: 폼 처리, runSimulate(), 타이밍 계측, SVG/JSON 다운로드
│       ├── styles.css                   # UI 스타일
│       └── data/
│           ├── precomputed_game1_v2.json  # GAME_ID=1, goal 1~20에 대한 압축된 사전계산 데이터(v2: [min_val, freq_list])
│           └── precomputed_game2_v2.json  # GAME_ID=2, goal 1~20 (v2)
│
└── src/                                 # Python Workers 서버 코드 (엔트리 + 시뮬레이션 로직)
    ├── entry.py                         # Worker 진입점: 라우팅, CORS, request-level 타이밍, ASSETS 우선 조회
    └── logic/
        ├── __init__.py                  # 패키지 초기화 (빈 파일)
        ├── compute.py                   # 런타임 경량화된 파이프라인
        │   ├─ 함수: decompress_totals(min_val, freq)
        │   ├─ 함수: summarize(totals, obs_total, n_sims)
        │   ├─ 함수: make_hist_svg(totals, obs_total, bins, title)
        │   └─ 함수: run_simulation(game_id, goal, obs_total, precomputed_data=...)
        │       # 반환: (summary_dict, svg_string, compute_timings_dict)
        ├── compute_not_used.py           # 오프라인/보관용 유틸: compress_totals, build_pity_cdf, alias 샘플러,
        │                                   # sample_total_draws, generate_precomputed_data, load/save, load_precomputed_from_assets(), load_precomputed_from_kv()
        ├── convert_data.py               # 기존 포맷 → v2 포맷(0-based freq) 변환 스크립트
        ├── generate_precomputed.py       # 오프라인 precompute 생성 스크립트(1M sims / goal 범위)
        ├── precomputed_game1.json        # 오프라인 원본(보존용)
        ├── precomputed_game2.json        # 오프라인 원본(보존용)
        ├── precomputed_game1_v2.json     # assets/data에 배포된 v2 포맷 복사본(여기에도 포함)
        └── precomputed_game2_v2.json
```

설명(파일/핵심 함수 정리)
- wrangler.toml
  - main = "src/entry.py" (Python Workers 엔트리)
  - [assets] binding = "ASSETS", directory = "./assets" — 정적 파일(CDN) 바인딩
  - kv_namespaces 설정: GLOBAL_STORE 바인딩 (ID: f6c7f658dde04b339e48adbe04389c1b)
- src/entry.py
  - 경로 라우팅: GET /api/health, POST /api/simulate, 그 외는 ASSETS.fetch fallback
  - Request-level 타이밍 수집: request_timings keys ("0_parse_request_ms","1_load_assets_ms","2_cdf_cache_ms","3_run_simulation_total_ms","4_total_request_ms")
  - CORS 헤더 적용, GLOBAL_STORE("count" 키로 요청 카운트)
  - precomputed data 로드: load_precomputed_from_assets(self.env.ASSETS, game_id, goal)
  - CDF 캐시: KV에 "cdf_{game_id}" 저장/조회 (store.get/put)
  - run_simulation(...) 호출 및 compute_timings 병합 후 JSON 응답
  - 예외 처리: traceback를 stdout에 print 및 에러 JSON 반환("01_"/"02_" 접두사)
- src/logic/compute.py
  - decompress_totals(min_val, freq): 빈도 리스트 → 원본 totals 완전 복원
  - summarize(totals, obs_total, n_sims): mean, std, percentile_rank_of_obs_%, samples 등 반환
  - make_hist_svg(totals, obs_total, bins, title): 히스토그램 SVG 생성 (SVG 문자열 반환)
  - run_simulation(..., precomputed_data=...): 입력 검증 → decompress → summarize → svg 생성 → timings 수집 → (summary, svg, timings)
- src/logic/compute_not_used.py (오프라인)
  - compress_totals(totals): 빈도 압축 (min_val, freq)
  - build_pity_cdf(game_id): 단일 에피소드 성공까지의 CDF 생성
  - _build_alias_from_cdf/_alias_sample: Alias method 전처리 & 샘플링 (O(1))
  - sample_total_draws(...): 오프라인 Monte Carlo 샘플링 (사용자 정의 시드)
  - generate_precomputed_data(...): goal 범위에 대해 n_sims 시뮬레이션 후 compress 저장
  - load_precomputed_from_assets(assets_binding, game_id, goal): ASSETS에서 precomputed v2 JSON 읽어 goal 인덱스 추출
  - load_precomputed_from_kv(kv_store, game_id, goal): KV에서 key "game{game_id}_{goal}" 로 로드 (폴백)
- webpage/assets/app.js (클라이언트)
  - runSimulate(payload): client-side validation(GOAL 1~20), performance timing, fetch("/api/simulate"), parse JSON, 성공 시 서버 timings 출력
  - showRateLimitHeaders(res): X-RateLimit-* 헤더 표시
  - setPlotFromSvg(svgText): Blob URL 생성 후 <img>에 연결
  - Download 버튼: SVG/JSON 다운로드 지원
- webpage/assets/index.html
  - UI: GAME_ID select(1/2), GOAL input (min=1,max=20), OBS_TOTAL input
  - <script src="/app.js"> 포함 — 클라이언트 동작
- kv-upload/upload-game-data.js
  - JSON 파일을 분해하여 npx wrangler kv key put 으로 업로드 (KEY_PREFIX e.g. "game1_")
  - 사용 시: 환경에 맞게 JSON_FILE_PATH, NAMESPACE_ID, KEY_PREFIX 수정

---

## Workflow

요약: 클라이언트 → Edge(Assets) → Worker(entry.py) → precomputed 데이터(ASSETS 우선) → run_simulation → 결과(JSON + SVG) 반환

1) 클라이언트 측 (assets/app.js)
- 사용자가 폼 제출 → readForm()로 payload 구성
- 클라이언트 유효성 검사: GOAL 범위 제한 (1 ≤ GOAL ≤ 20). 범위 벗어나면 throw(요청 중단).
- runSimulate(payload)
  - clientStartTime 시작
  - POST /api/simulate (application/json)
  - fetch/parse 타이밍 기록(성공 응답인 경우만 콘솔에 정렬 출력)
  - 성공 시: data.summary → UI에 포맷팅(formatSummary), data.image_svg → Blob으로 변환해 <img>에 표시

2) 네트워크: POST /api/simulate
- 예시 요청:
```bash
curl -X POST http://localhost:8787/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"GAME_ID":1,"GOAL":5,"OBS_TOTAL":300}'
```

3) 서버(Worker: src/entry.py)
- 요청 카운트 증가: GLOBAL_STORE.get/put("count")
- CORS 프리플라이트 처리 (OPTIONS)
- JSON 파싱 → request_timings["0_parse_request_ms"]
- ASSETS에서 precomputed 데이터 로드:
  - load_precomputed_from_assets(self.env.ASSETS, game_id, goal) 호출 → request_timings["1_load_assets_ms"]
  - 포맷: v2 배열(첫 요소는 goal 리스트, 인덱스 계산 후 [min_val,freq_list] 반환)
- CDF 캐싱:
  - KV key: f"cdf_{game_id}" 조회/생성 → request_timings["2_cdf_cache_ms"]
  - build_pity_cdf() 는 compute_not_used.py에 보관(오프라인 재사용)
- run_simulation 호출:
  - run_simulation(game_id, goal, obs_total, precomputed_data=...)
  - 내부 compute_timings 수집(예: "1_validation_ms","2_decompress_ms","3_summarize_ms","4_svg_generation_ms","5_total_compute_ms")
  - run_simulation은 precomputed_data 필수(현재 실시간 샘플링 경로는 비활성화)
- 에러 처리:
  - run_simulation 호출부는 try/except로 감싸 traceback을 stdout으로 print (print(f"[Error #{count}] {traceback}"))
  - 클라이언트에게는 {"ok": False, "error": "01_ ..."} 또는 "02_" 접두사 붙은 에러 반환
- 최종 응답:
```json
{
  "ok": true,
  "summary": { "samples": ..., "mean_total_draws": ..., "percentile_rank_of_obs_%": ... },
  "image_svg": "<svg ...>...</svg>",
  "timings": {
     // merged dictionary: request_timings + compute_timings (ms)
  }
}
```

4) 시뮬레이션 파이프라인 (run_simulation 중심)
- 입력: game_id, goal, obs_total, precomputed_data([min_val, freq])
- 단계:
  1. 입력 검증 (GAME_TABLE 확인) — timings["1_validation_ms"]
  2. 압축 해제: decompress_totals(min_val, freq) → totals (리스트) — timings["2_decompress_ms"]
  3. 통계 요약: summarize(totals, obs_total, n_sims) — timings["3_summarize_ms"]
  4. 시각화: make_hist_svg(totals, obs_total, bins=...) — timings["4_svg_generation_ms"]
  5. totals 참조 해제 및 전체 컴퓨트 타이밍 기록 — timings["5_total_compute_ms"]
- 반환: (summary_dict, svg_string, timings_dict)

5) 에셋 우선 전략 및 폴백
- 우선순위: ASSETS (assets/data/precomputed_game{1,2}_v2.json) → KV (load_precomputed_from_kv, 현재는 폴백/관리용) → 라이브 시뮬레이션(현재 비활성화)
- 이유: ASSETS는 CDN에 캐시되어 전 세계 엣지에서 매우 빠름(1-3ms 파일 읽기)

6) 배포 / 운영 주요 명령
- 로컬 개발:
```bash
npx wrangler dev
```
- 배포 (ASSETS 포함):
```bash
npx wrangler deploy   # 또는 npx wrangler publish
```
- KV 네임스페이스 생성 (관리자):
```bash
npx wrangler kv:namespace create "GLOBAL_STORE"
# 얻은 id를 wrangler.toml의 kv_namespaces에 추가
```
- KV 업로드 (kv-upload 스크립트 사용):
```bash
cd kv-upload
node upload-game-data.js
# 또는 수동으로:
npx wrangler kv key put "game1_5" --namespace-id="<NAMESPACE_ID>" --path="temp_game1_5.json"
```

7) 흐름 다이어그램 (텍스트)
```
Client (index.html / app.js)
    |
    | POST /api/simulate (payload)
    v
Worker entry.py
    ├─ increment GLOBAL_STORE.count
    ├─ parse JSON (timing)
    ├─ load_precomputed_from_assets(ASSETS, game_id, goal) (timing)
    ├─ ensure CDF cached in KV (store.get/put) (timing)
    └─ run_simulation(precomputed_data) -> (summary, svg, compute_timings)
          ├─ decompress_totals()
          ├─ summarize()
          └─ make_hist_svg()
    |
    └-> Response JSON { ok, summary, image_svg, timings }
    |
Client parses JSON, shows SVG, logs timings
```

---

## Features

### 핵심 기능 (핵심 5개)
1. Simulation capabilities
   - 오프라인으로 1,000,000 샘플로 생성된 사전계산 데이터(precomputed)를 사용해 엣지에서 빠르게 통계/시각화 수행.
   - 핵심 런타임 함수: src/logic/compute.run_simulation(game_id, goal, obs_total, precomputed_data=...)
   - summarize()로 mean/std/percentile(관측값의 백분위)을 계산해 리포트 제공.

2. Game modes
   - 다중 게임 지원: GAME_ID 1 및 2 (파라미터는 GAME_TABLE에 정의: CEIL_RATIO, MAX_T, BASE_P, ACCEL_START, ACCEL_STEP)
   - goal 값(1~20)에 대해 사전계산 데이터 제공(assets/data/precomputed_game{1,2}_v2.json)

3. UI/UX features
   - Single-page UI: assets/index.html + assets/app.js
   - 입력 검증(GOAL 1~20) 및 클라이언트 타이밍(순간 측정: fetch/parse/total)
   - SVG 이미지 미리보기, SVG/JSON 다운로드 버튼 (Blob 기반)

4. Visualization features
   - make_hist_svg()가 히스토그램을 SVG 문자열로 생성 — 서버는 Base64 없이 생 SVG를 반환하여 응답 크기 최적화
   - 관측값(obs_total)은 빨간 점선으로 강조
   - Bins 계산은 goal에 비례하여 동적으로 결정(해상도 조정)

5. Optimization features
   - ASSETS 우선 전략: precomputed JSON을 ASSETS(CDN)에서 읽어 빠르게 decompress 후 처리 (PERFORMANCE.md 근거: 응답 ~5-8ms)
   - 압축 포맷(v2): [min_val, freq_list] 로 빈도 기반 무손실 저장, 압축률 약 99.5%
   - 런타임 코드 경량화: compute.py는 decompress/summarize/svg generation에만 집중, 샘플링/alias 코드는 compute_not_used.py에 보관(임포트 비용 최소화)
   - KV는 cdf 캐시 등 보조 용도로만 사용(읽기 지연 최소화)

### 기술적 특징
- 알고리즘
  - Monte Carlo (오프라인 대규모 시뮬레이션) — generate_precomputed_data()로 1M 샘플 생성
  - Alias method (compute_not_used._build_alias_from_cdf / _alias_sample) — O(1) 샘플링용 전처리(오프라인 보관)
  - 압축/복원: compress_totals / decompress_totals — 빈도 리스트를 사용한 무손실 압축
  - 통계: mean, sample std (n-1), percentile 계산(single pass + second pass for variance)
- 성능 지표 (PERFORMANCE.md 요약)
  - ASSETS 방식: 전체 응답 ~5-8ms (Assets fetch 1-3ms + decompress ~20ms?; 문서상 전체 ~5-8ms로 최적화)
  - KV 폴백: ~40-50ms
  - 실시간 샘플링: 수초(~5-10s) — 런타임에서 비활성화되어 있음
  - 메모리 사용: 압축 해제(1M 샘플) 피크 약 ~4MB, 전체 피크 ~5MB(Workers 한도 내)
- 보안/안정성
  - CORS 헤더 설정 (entry.py)
  - 클라이언트 및 서버 측 입력 검증 (app.js, entry.py)
  - 예외 처리 시 traceback stdout 로깅(운영 중 민감정보 필터 권장)
  - KV는 eventual consistency 특성(전파 지연 약 60s) — KV 기반 의존은 최소화
- 아키텍처 하이라이트
  - ASSETS 바인딩 (wrangler.toml)으로 precomputed JSON을 CDN에 배포 → 전 세계 엣지에서 빠른 읽기
  - GLOBAL_STORE (KV) 바인딩: 요청 카운트, CDF 캐싱 등 운영용
  - 서버는 Python Workers (main = src/entry.py), 프론트는 정적 Assets (index.html, app.js, styles.css)
  - 오프라인 툴(kv-upload/upload-game-data.js, compute_not_used.generate_precomputed_data)로 운영자가 KV/Assets에 데이터 업로드 가능

---

## Versions

### v2.6 (2025-10-20) — 최신
- 주요 변경사항
  - 서버/클라이언트 프로파일링 강화
    - src/entry.py: request-level 타이밍 수집 도입 (keys: "0_parse_request_ms","1_load_assets_ms","2_cdf_cache_ms","3_run_simulation_total_ms","4_total_request_ms")
    - src/logic/compute.run_simulation: compute-level 단계 타이밍 수집 및 반환 (keys: "1_validation_ms","2_decompress_ms","3_summarize_ms","4_svg_generation_ms","5_total_compute_ms")
  - 예외 처리 개선: run_simulation 호출을 try/except로 감싸 traceback을 stdout에 print, 클라이언트 에러에 "01_"/"02_" 접두사를 붙임
  - 런타임 경량화: 실시간 샘플링 코드 제거(또는 비활성화) 및 compute.py 의 임포트 비용 최소화
- 최적화
  - ASSETS 우선 전략을 명확화(assets/data/precomputed_game*_v2.json 사용)
  - compute.py는 decompression → summarize → svg generation 흐름에 집중
- 버그 수정
  - assets/app.js: 성공 응답일 때만 타이밍 출력 (에러 시 타이밍 출력 전에 throw)
- 새 기능
  - API 응답에 상세 타이밍("timings") 포함 — 서버/클라이언트 타이밍 통합 제공

### v2.5
- 주요 변경사항
  - precomputed v2 포맷 도입: [min_val, freq_list] (빈도 기반, 무손실)
  - assets/data에 precomputed_game{1,2}_v2.json 배포하여 ASSETS 우선 전략 적용
  - kv-upload 도구 추가 (kv-upload/upload-game-data.js, worker-game-data.ts) — KV 업로드/조회 자동화
- 최적화
  - 빈도 리스트 압축으로 JSON 크기 대폭 감소(약 99.5% 압축 효과)
  - 서버 응답 크기 최적화: SVG는 생 문자열로 반환하여 base64 오버헤드 제거
- 새 기능
  - generate_precomputed.py: 오프라인에서 1M 시뮬레이션 생성/저장 스크립트

### v2.0
- 주요 변경사항
  - 전체 프로젝트를 Cloudflare Python Workers로 마이그레이션 (main = src/entry.py)
  - Assets 바인딩 도입(wrangler.toml) — 정적 파일 CDN 서빙
  - run_simulation API 설계 및 compute.py 분리(런타임 핵심)
- 최적화
  - Cold-start 최소화를 위해 오프라인 샘플링/복잡한 로직은 compute_not_used.py로 분리
- 새 기능
  - 클라이언트 타이밍 계측 (assets/app.js의 performance 측정)

### v1.5
- 주요 변경사항
  - 히스토그램 SVG 생성기 도입 (make_hist_svg in compute.py)
  - summarize() 추가: percentile, mean, std 계산 및 summary 구조 표준화
- 최적화
  - SVG 생성 시 히스토그램을 density 기반으로 생성하여 y-axis 스케일 보정
- 버그 수정
  - percentiles 및 평균 계산 시 자료형 일관성 개선

### v1.2
- 주요 변경사항
  - Alias method 및 O(1) 샘플링 알고리즘을 오프라인 코드로 구현 (compute_not_used._build_alias_from_cdf, _alias_sample)
  - sample_total_draws() 구현: 복합 에피소드 합산 로직 포함
- 새 기능
  - compress_totals / decompress_totals (무손실 빈도 압축 포맷 초기 구현)

### v1.1
- 주요 변경사항
  - 초기 Monte Carlo 시뮬레이션 파이프라인 구축 (generate_precomputed_data, save/load)
  - Game parameter table (GAME_TABLE) 정의 (CEIL_RATIO, MAX_T, BASE_P 등)
- 버그 수정
  - 확률 PMF/CDF 꼬리 보정 로직 추가(build_pity_cdf) — 누락시 합이 1이 되지 않는 문제 수정

### v1.0 (초기)
- 주요 변경사항
  - 프로젝트 초기 릴리스: 기본 Monte Carlo 개념, 단일 게임 시뮬레이션 및 UI 프로토타입
  - 기능: 샘플링, 통계 요약, 간단한 클라이언트-서버 흐름
- 제한사항
  - 아직 ASSETS/CDN 최적화 미완료; 대규모 사전계산 데이터 관리는 수동
  - 타이밍 계측 및 운영용 KV 통합 미포함

(참고)
- 각 버전에서의 파일/함수 참조:
  - run_simulation, decompress_totals, summarize, make_hist_svg: src/logic/compute.py
  - build_pity_cdf, compress_totals, sample_total_draws, generate_precomputed_data: src/logic/compute_not_used.py
  - ASSETS 로드 유틸: src/logic/compute_not_used.load_precomputed_from_assets
  - KV 업로드 스크립트: kv-upload/upload-game-data.js
  - 클라이언트: webpage/assets/app.js (runSimulate, showRateLimitHeaders, setPlotFromSvg)

---
<!-- AUTO-UPDATE:END -->
<!-- AUTO-UPDATE:END -->

<!-- LAST_PROCESSED_SHA: c10bad7e8c3d8c4d9f8e44e1fda9d76e09833263 -->
