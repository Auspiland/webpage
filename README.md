# Cloudflare workers
Cloudflare workers를 활용한 webpage test입니다.

## Monte Carlo Simulation Web App

Cloudflare Workers 기반의 몬테카를로 시뮬레이션 웹 애플리케이션입니다. 가챠 게임의 확률 분포를 시뮬레이션하고 정규분포 피팅 결과를 시각화합니다.

<!-- AUTO-UPDATE:START -->
## Dir Structure

```
# 루트 (프로젝트 최상위)
├── KV_INTEGRATION.md                      # KV 통합 문서: KV 데이터 포맷, 업로드/운영 가이드
├── PERFORMANCE.md                          # 성능 분석 및 최적화 전략 문서
├── kv-upload/                              # KV 업로드 도구 및 예제 Worker (운영/배포 보조)
│   ├── README.md                           # kv-upload 사용법 및 예제
│   ├── upload-game-data.js                 # JSON -> KV 업로드 스크립트 (환경 변수: JSON_FILE_PATH, NAMESPACE_ID, KEY_PREFIX)
│   └── worker-game-data.ts                 # KV에서 게임 데이터 읽는 예제 Worker (GET /game1/{key}, /game1/list, /game1/all)
│
├── webpage/
│   ├── assets/                             # 정적 파일(프론트엔드 + precomputed 데이터, 엣지/CDN 배포 대상)
│   │   ├── index.html                      # 메인 HTML (GOAL 입력 max="20" 등)
│   │   ├── app.js                          # 클라이언트 로직: API 호출, UI 업데이트, SVG 렌더링
│   │   │                                       # 변경: runSimulate에서 clientStart/fetch/parse/total 타이밍 계측. 성공 응답일 때만 타이밍 콘솔 출력; 에러 발생 시 타이밍 출력 전에 throw.
│   │   ├── styles.css                      # 스타일시트
│   │   └── data/
│   │       ├── precomputed_game1_v2.json   # GAME_ID=1 압축 사전계산 데이터 (v2: [min_val, freq_list]) — ASSETS 우선 로드 대상
│   │       └── precomputed_game2_v2.json   # GAME_ID=2 압축 사전계산 데이터 (v2: [min_val, freq_list])
│
├── src/                                    # 백엔드 로직 (Python Workers)
│   ├── entry.py                            # Workers 진입점: 라우팅, CORS, ASSETS 우선 조회, request-level 타이밍 수집
│   │                                       # 변경/중요: run_simulation 호출을 try/except로 감싸 traceback을 print로 로깅. 에러 응답에 디버깅 접두사("01_"/"02_") 포함.
│   └── logic/                              # 시뮬레이션/유틸 로직
│       ├── __init__.py
│       ├── compute.py                      # 런타임 경량화된 시뮬레이션 핸들러
│       │                                       # 제공 함수: decompress_totals, summarize, make_hist_svg, run_simulation
│       │                                       # run_simulation 반환: (summary_dict, svg_string, timing_dict)
│       │                                       # 수집되는 compute 타이밍 예: "1_validation_ms","2_decompress_ms","3_summarize_ms","4_svg_generation_ms","5_total_compute_ms"
│       ├── compute_not_used.py              # 아카이브/관리용 유틸 (오프라인 precompute 생성, 샘플링/alias/CDF 구현 보관)
│       │                                       # 보관 함수: compress_totals, build_pity_cdf, _build_alias_from_cdf, _alias_sample, _binomial_7, sample_total_draws
│       │                                       # I/O/전처리: load_precomputed_from_assets, load_precomputed_from_kv, generate_precomputed_data, save/load 등 (운영자/오프라인 용)
│       ├── precomputed_game1.json          # (보존용) GAME_ID=1 원본 사전계산 데이터(디버그/생성용)
│       ├── precomputed_game2.json          # (보존용) GAME_ID=2 원본 사전계산 데이터
│       ├── precomputed_game1_v2.json       # assets/data에 복사된 GAME_ID=1 v2 압축 데이터
│       └── precomputed_game2_v2.json       # assets/data에 복사된 GAME_ID=2 v2 압축 데이터
│
├── wrangler.toml                           # Cloudflare Workers 설정 (ASSETS 바인딩 + KV 네임스페이스)
│   ├─ (ASSETS) [assets] directory = "./assets", binding = "ASSETS"
│   └─ (KV) [[kv_namespaces]] binding = "GLOBAL" id = "<namespace-id>"
└── README.md                               # 프로젝트 설명 및 API/개발 가이드 (자동 갱신 포함)
```

- 중요 포인트(요약)
  - src/logic/compute.run_simulation은 precomputed_data를 필수 인자로 받아 decompress_totals → summarize → make_hist_svg를 수행하고 (summary_dict, svg_string, timing_dict)를 반환.
  - compute.run_simulation은 단계별 compute 타이밍을 수집(예: "1_validation_ms", "2_decompress_ms", "3_summarize_ms", "4_svg_generation_ms", "5_total_compute_ms").
  - entry.py는 request-level 타이밍(request_timings 키들)을 수집 및 run_simulation 호출을 try/except로 감싸 traceback을 stdout에 print. 에러 메시지에 "01_"/"02_" 접두사 부착 가능.
  - assets/app.js는 클라이언트 타이밍을 계측하되 '성공 응답'일 때만 콘솔에 정렬 출력하며 에러 시 타이밍 출력 전에 throw 처리.

## Workflow

### 1. 클라이언트 요청 흐름
```
사용자 입력 (index.html, GOAL 1~20)
    ↓
클라이언트 유효성 검사 (assets/app.js)
    - GOAL 범위: 1 <= GOAL <= 20 (클라이언트에서 예외 throw 시 요청 중단)
    ↓
폼 제출 (app.js → runSimulate)
    - clientStartTime 측정 시작
    ↓
POST /api/simulate
    - 요청 body 예: {"GAME_ID":1,"GOAL":5,"OBS_TOTAL":30, "N_SIMS"?:100000, "SEED"?:1234, "BINS"?:50}
    ↓
entry.py (라우팅, CORS, request-level 타이밍 수집)
    - request_timings 수집: 예: "0_parse_request_ms", "1_load_assets_ms", "3_run_simulation_total_ms", "4_total_request_ms"
    - JSON 파싱 후 request_timings["0_parse_request_ms"] 기록
    - ASSETS 로드 시 request_timings["1_load_assets_ms"] 기록
    - run_simulation 호출을 try/except로 감싸 예외 발생 시 traceback을 print(stdout)로 로깅(카운터 포함 로그 포맷 예: print(f"[Error #{count}] ..."))
    ↓
ASSETS(엣지)에서 사전계산 조회(우선)
    - 호출: precomputed_data = await load_precomputed_from_assets(self.env.ASSETS, game_id, goal)
    - precomputed_data 포맷: [min_val, freq_list] (v2 압축)
    - 항목 부재 시 400 응답 반환 (KV 폴백/라이브 샘플링 경로는 런타임에서 비활성화)
    ↓
run_simulation(..., precomputed_data=precomputed_data)
    - 필수: precomputed_data (없으면 ValueError)
    - 내부: decompress_totals → summarize → make_hist_svg
    - compute-level 타이밍 수집(compute_timings): "1_validation_ms","2_decompress_ms","3_summarize_ms","4_svg_generation_ms","5_total_compute_ms"
    - 반환값: (summary_dict, svg_string, compute_timings)
    - 예외 발생 시 entry.py가 traceback을 print하고 에러 JSON 반환(에러 메시지에 "01_" / "02_" 접두사 가능)
    ↓
entry.py:
    - request_timings에 "3_run_simulation_total_ms" 등 추가 기록
    - all_timings = {**request_timings, **compute_timings}
    - 최종 JSON에 "timings": all_timings 포함하여 반환 (ms 단위)
    ↓
클라이언트 (assets/app.js):
    - fetch/parse/total 타이밍 측정
    - 성공 응답인 경우에만 client-side 타이밍과 서버 "timings"를 콘솔에 정렬 출력
    - 에러인 경우 타이밍 출력 이전에 에러를 throw
```

- 주요 라우트
  - POST /api/simulate
    - 요청 body: { "GAME_ID", "GOAL", "OBS_TOTAL", "N_SIMS"?: int, "SEED"?: int, "BINS"?: int }
    - 처리 요약:
      1. ASSETS에서 precomputed JSON의 goal 인덱스 조회 (load_precomputed_from_assets — 유틸은 src/logic/compute_not_used.py 보관).
      2. 항목 없으면 400 반환.
      3. 항목 있으면 decompress_totals → run_simulation(요약, 시각화) → entry.py가 request_timings를 덧붙여 JSON 응답("timings" 포함).
    - 예외 처리:
      - run_simulation 호출부는 try/except로 감싸여 있으며 traceback을 stdout에 print하고 {"ok": False, "error": "01_<message>"} 형태의 에러 JSON을 반환할 수 있음.
  - GET /api/health
    - 상태 확인: {"ok": true}

### 2. 시뮬레이션 파이프라인
- 2-1. 입력 검증
  - 클라이언트에서 범위 검증(assets/app.js) + 서버(entry.py)에서 타입/범위 재검증.
- 2-2. 데이터 소스(우선순위)
  - 1) ASSETS(엣지): assets/data/precomputed_game{1,2}_v2.json에서 goal 인덱스 조회 → [min_val, freq_list]
  - 2) KV 폴백: 런타임에서는 비활성화(운영/관리용 툴로 보관)
  - 3) 라이브 샘플링: compute_not_used.py에 샘플링/alias/CDF 구현 보관(오프라인 용)
- 2-3. 통계/타이밍/시각화
  - decompress_totals → summarize(mean, std, percentiles 등) → make_hist_svg(히스토그램 SVG 생성)
  - run_simulation은 compute_timings를 수집하여 반환. entry.py는 request_timings와 병합하여 응답의 "timings" 필드로 제공.
  - 클라이언트는 fetch/parse/total을 측정하여 성공 시 서버 timings과 함께 출력.

### 3. 배포 / 운영 관련
- wrangler.toml: ASSETS 바인딩 필요(변경 없음)
```toml
[assets]
directory = "./assets"
binding = "ASSETS"
```

- 배포 (Assets 포함)
```bash
# assets/data/precomputed_game*_v2.json 등 정적 파일을 포함하여 배포
npx wrangler publish  # 또는 npx wrangler deploy
```

- KV 네임스페이스 생성 (관리자용)
```bash
npx wrangler kv:namespace create "GLOBAL_STORE"
# wrangler.toml에 바인딩 추가: [[kv_namespaces]] binding = "GLOBAL" id = "<namespace-id>"
```

- precomputed JSON을 KV에 업로드 (관리자/오프라인 용도; 런타임은 KV 폴백 미사용)
```bash
cd kv-upload
node upload-game-data.js  # 환경 변수/스크립트 설정: JSON_FILE_PATH, NAMESPACE_ID, KEY_PREFIX
npx wrangler kv key list --namespace-id="<NAMESPACE_ID>" --prefix="game1_"
npx wrangler kv key get --namespace-id="<NAMESPACE_ID>" "game1_5"
```

## Features

### 핵심 기능 (핵심 5개 항목)

1. 런타임 경량화된 요약/시각화 파이프라인
   - 구현 위치: src/logic/compute.run_simulation
   - 처리: precomputed_data → decompress_totals → summarize → make_hist_svg
   - 반환값: (summary_dict, svg_string, timing_dict). timing_dict은 단계별 소요(ms)를 포함.
   - 설계 의도: 실시간 샘플링을 배제하고 오프라인 precompute로 엣지 응답 속도 최적화.

2. ASSETS 기반 사전계산(Precomputed) 우선 전략
   - 데이터 포맷: v2 압축 — [min_val, freq_list] (assets/data/precomputed_game{1,2}_v2.json)
   - 로드 유틸: load_precomputed_from_assets (오프라인 유틸은 src/logic/compute_not_used.py에 보관)
   - 장점: 엣지에서 직접 파일 조회 후 빠르게 decompress → summarize/visualize

3. 운영/관리용 오프라인 툴 및 KV 업로드
   - kv-upload/upload-game-data.js: precomputed JSON을 KV에 업로드하는 관리자 도구
   - src/logic/compute_not_used.py: precompute 생성(generate_precomputed_data), compress/저장, KV I/O 및 기존 샘플링/alias 구현 보관(오프라인 검증/생성용)

4. 다중 게임 모드 및 파라미터화
   - GAME_TABLE 기반 파라미터 유지(예: CEIL_RATIO, MAX_T, BASE_P)
   - precomputed 데이터는 goal별로 생성되어 run_simulation에서 처리 가능 (다양한 GAME_ID/GOAL 조합 지원)

5. 웹 UI / 엔드투엔드 시각화 및 성능 계측
   - 입력: GAME_ID, GOAL, OBS_TOTAL (assets/index.html, assets/app.js)
   - 출력: summary JSON + make_hist_svg로 생성된 SVG 문자열
   - 성능 계측: 클라이언트(app.js)에서 fetch/parse/total 측정, 서버(entry.py + compute.py)에서 request- 및 compute-level 타이밍을 수집하여 응답의 "timings" 필드로 제공

### 기술적 특징

알고리즘
- Alias method 및 O(1) 샘플링 관련 구현은 src/logic/compute_not_used.py에 보관(오프라인 전처리/검증 재사용 가능).
- 압축 포맷(v2): [min_val, freq_list]로 빈도 기반 저장을 최소화하여 엣지 전송 비용 절감.

성능 / 계측
- 서버 측 타이밍
  - entry.py: request-level 타이밍 키 예: "0_parse_request_ms", "1_load_assets_ms", "3_run_simulation_total_ms", "4_total_request_ms"
  - compute.run_simulation: compute-level 타이밍 예: "1_validation_ms", "2_decompress_ms", "3_summarize_ms", "4_svg_generation_ms", "5_total_compute_ms"
  - 최종 응답에 timings 딕셔너리 포함 → 상세 프로파일링 가능
- 클라이언트 측 타이밍
  - assets/app.js: fetch/parse/total 측정 및 성공 시 서버 timings과 함께 콘솔 출력
- 성능 기대치
  - ASSETS 조회 + decompress → 보통 매우 낮은 지연(수 ms ~ 10ms 범위 컴퓨트)
  - 라이브 샘플링 또는 KV 폴백 활성화 시 지연 증가 가능(수십 ms~초)

보안 및 안정성
- CORS 헤더 설정 및 입력 검증 유지(entry.py + client-side)
- precomputed 부재 시 명확한 400 응답 반환
- 예외 처리: entry.py가 run_simulation 예외를 잡아 traceback을 stdout에 print하고 에러 메시지에 디버깅 접두사("01_"/"02_")를 포함 — 운영 환경에서는 민감 정보 필터링 권장

CI / 도구
- README 자동 갱신 스크립트(.github/scripts/update_readme.py) 및 PERFORMANCE.md 참조
- compute_not_used.py는 오프라인 precompute 생성/검증에 참고 가능

## Versions

### v2.6 (2025-10-20)
**주요 변경사항**
- 서버/클라이언트 프로파일링 강화
  - src/entry.py에 request-level 타이밍 수집 로직 추가 및 request_timings 키 도입("0_parse_request_ms", "1_load_assets_ms", "3_run_simulation_total_ms", "4_total_request_ms").
  - src/logic/compute.run_simulation이 compute-level 단계 타이밍을 수집하여 반환하도록 변경(반환값: (summary_dict, svg_string, compute_timings)).
  - entry.py는 compute_timings와 request_timings을 병합하여 API 응답의 "timings" 필드로 반환.
- 런타임 안정성 및 에러 로깅
  - entry.py에서 run_simulation 호출을 try/except로 감싸고 예외 발생 시 traceback을 print(stdout)로 로깅. 에러 응답 메시지에 디버깅 접두사("01_"/"02_")를 추가할 수 있음.
- 런타임 경량화
  - src/logic/compute.py에서 실시간 샘플링(CDF/alias/_alias_sample 등)을 제거하고 decompress_totals / summarize / make_hist_svg 및 타이밍 수집에 집중.
- 오프라인/관리용 유틸 보관
  - src/logic/compute_not_used.py에 기존 샘플링, alias method, compress/전처리, load/save 및 KV I/O 유틸을 아카이브.

**최적화**
- 런타임에서 불필요한 샘플링/전처리 코드 제거로 cold-start/임포트 비용 감소.
- ASSETS 우선 전략으로 엣지에서 파일 직접 로드하여 전체 응답 지연 최소화.

**버그 수정**
- assets/app.js: 성공 응답일 때만 타이밍 콘솔 출력하도록 수정(에러 발생 시 타이밍 출력 이전에 throw).
- run_simulation 호출부에서 예외 발생 시 traceback 출력 및 JSON 에러 반환으로 디버깅 용이성 개선.

**새 기능**
- API 응답에 단계별 타이밍("timings") 포함 — 서버/컴퓨트/클라이언트 타이밍을 종합 제공.

---

### v2.5 (이전)
- ASSETS 기반 precompute 우선 전략
- precomputed(v2) 포맷 도입: [min_val, freq_list]
- 오프라인 KV 업로드 도구(kv-upload)
- 히스토그램 SVG 생성(make_hist_svg) 및 summarize 기능 제공
<!-- AUTO-UPDATE:END -->
<!-- AUTO-UPDATE:END -->

<!-- LAST_PROCESSED_SHA: 2353042e1cb6c39932240c852167f08ac88e4c50 -->
