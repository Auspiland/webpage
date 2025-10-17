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
├── kv-upload/                              # KV 업로드 도구 및 예제 Worker
│   ├── README.md                           # kv-upload 사용법 및 예제
│   ├── upload-game-data.js                 # JSON -> KV 업로드 스크립트 (wrangler kv key put 사용). 설정: JSON_FILE_PATH, NAMESPACE_ID, KEY_PREFIX
│   └── worker-game-data.ts                 # KV를 읽어주는 예제 Cloudflare Worker (GET /game1/{key}, /game1/list, /game1/all) — CORS 및 예외 처리 포함
│
webpage/
├── assets/                                 # 정적 파일 (프론트엔드 + precomputed 데이터, CDN에 배포됨)
│   ├── index.html                          # 메인 HTML 페이지
│   ├── app.js                              # 클라이언트 로직 (API 호출, UI 업데이트, SVG 렌더링)
│   ├── styles.css                          # 스타일시트
│   └── data/
│       ├── precomputed_game1_v2.json       # GAME_ID=1 압축 사전계산 데이터 (v2, 빈도 리스트) — Assets 우선 읽기 대상
│       └── precomputed_game2_v2.json       # GAME_ID=2 압축 사전계산 데이터 (v2, 빈도 리스트)
│
├── src/                                    # 백엔드 로직 (Python Workers)
│   ├── entry.py                            # Workers 진입점 (라우팅, CORS, Assets 우선 조회 -> KV 폴백 -> live 시뮬레이션). 변경: Assets fetch 우선, load_precomputed_from_kv 호출 유지, run_simulation 인자 확장(precomputed_data, kv_store)
│   └── logic/                              # 시뮬레이션 코어 로직
│       ├── __init__.py
│       ├── compute.py                      # 시뮬레이션 엔진 및 유틸 (CDF 구성, Alias Method, SVG 생성)
│       │                                        핵심 함수: build_pity_cdf, sample_total_draws, summarize, make_hist_svg, preprocess_alias
│       │                                        변경/추가: run_simulation 서명 확장(kv_store, precomputed_data), load_precomputed_from_kv(async), decompress_totals 경로/사용
│       ├── generate_precomputed.py         # 사전 계산 데이터 생성 스크립트 (precompute -> JSON 압축 포맷)
│       ├── convert_data.py                 # 데이터 포맷 변환 유틸리티 (원본 -> v2 빈도 리스트)
│       ├── precomputed_game1.json          # GAME_ID=1 사전 계산 데이터 (원본, 디버그/생성용)
│       ├── precomputed_game2.json          # GAME_ID=2 사전 계산 데이터 (원본)
│       ├── precomputed_game1_v2.json       # GAME_ID=1 압축 데이터 (v2) - 빈도 리스트 형식 (assets/data/)
│       └── precomputed_game2_v2.json       # GAME_ID=2 압축 데이터 (v2) - 빈도 리스트 형식 (assets/data/)
│
├── wrangler.toml                           # Cloudflare Workers 설정
│   ├─ (ASSETS) [assets] directory = "./assets", binding = "ASSETS"  # Assets 바인딩: precomputed JSON을 엣지에서 직접 읽도록 설정됨
│   └─ (KV) [[kv_namespaces]] binding = "GLOBAL" id = "<namespace-id>"  # KV 네임스페이스 바인딩
└── README.md                               # 프로젝트 설명 및 API/개발 가이드 (자동 갱신 메커니즘 포함)
```

- 추가/변경 파일 설명
  - PERFORMANCE.md: Assets 우선 전략(ASSETS 바인딩)과 Assets vs KV vs live 시뮬레이션의 성능/메모리/비용 분석, 권장 배포/테스트 절차를 기술. 예시: assets.fetch("/data/precomputed_game1_v2.json").json() 사용 및 압축 해제(decompress_totals) 타이밍 표기.
  - assets/data/precomputed_game1_v2.json: GAME_ID=1용 빈도 리스트 포맷(v2). CDN 캐싱을 통해 Assets가 최우선 데이터 소스가 되도록 추가.
  - wrangler.toml: ASSETS 바인딩 섹션 추가(assets 디렉토리 자동 업로드 및 엣지 캐싱).

---

## Workflow

### 1. 클라이언트 요청 흐름 (업데이트: Assets 우선)
```
사용자 입력 (index.html)
    ↓
폼 제출 (app.js)
    ↓
POST /api/simulate
    ↓
entry.py (라우팅, 요청 검증, CORS)
    ↓
1) Assets(ASSETS 바인딩)에서 사전계산 조회 시도:
    - path = f"/data/precomputed_game{game_id}_v2.json" 또는 단일 파일 내 goal 인덱스 조회
    - full_data = await ASSETS.fetch(path).json()
    - if goal entry found: min_val, freq_list -> totals = decompress_totals(min_val, freq_list)
      → n_sims = len(totals)  (Assets 경로)
    └─ else: 2) KV에서 사전계산 조회 시도:
         - precomputed_data = await load_precomputed_from_kv(kv_store, game_id, goal)
         - if precomputed_data: min_val, freq_list -> totals = decompress_totals(min_val, freq_list)
         - else: 3) 라이브 샘플링 경로
                 - build_pity_cdf(...)  # 필요한 경우 CDF 생성/캐싱
                 - totals = sample_total_draws(cdf, N_SIMS)  # Walker's Alias Method 사용 (compute.sample_total_draws)
    ↓
run_simulation(..., precomputed_data=precomputed_data_or_assets, kv_store=store)
    - run_simulation 내부: precomputed path면 decompress_totals를 통해 통계/SVG 생성 루틴으로 직행
    - live path면 sample_total_draws → summarize → make_hist_svg
    ↓
summarize(totals, obs_total) & make_hist_svg(totals, obs_total)
    ↓
JSON 응답 { summary: {...}, image_svg: "<svg...>" }
    ↓
결과 렌더링 (app.js)
```

- 주요 라우트 (동작 요약)
  - POST /api/simulate
    - JSON body: { "GAME_ID", "GOAL", "OBS_TOTAL" }
    - 처리:
      1. ASSETS에서 해당 게임/goal 사전계산 JSON을 먼저 조회 (assets.fetch 경로)
      2. 실패하면 KV (load_precomputed_from_kv) 폴백
      3. 둘 다 없으면 라이브 시뮬레이션(sample_total_draws using Alias Method)
    - 반환: summary + image_svg (SVG 문자열)
  - GET /api/health: 상태 확인 ({"ok": true}) — 유지

### 2. 시뮬레이션 파이프라인 (요약)
- 2-1. CDF 구성 (build_pity_cdf)
  - Pity 시스템 기반 확률 모델링: BASE_P, ACCEL_START, ACCEL_STEP, MAX_T 파라미터
  - 생존 확률 기반 PMF → CDF 변환 (compute.build_pity_cdf)
- 2-2. 입력 데이터 소스 분기 (신규)
  - Assets(ASSETS 바인딩) 우선: assets.fetch("/data/precomputed_game{1,2}_v2.json") → goal 인덱스 조회 → decompress_totals(min_val, freq)
  - KV 폴백: load_precomputed_from_kv(kv_store, game_id, goal) (async)
  - 라이브 샘플링: sample_total_draws (Alias Method) 호출
- 2-3. 몬테카를로 샘플링 (sample_total_draws)
  - Walker's Alias Method: O(1) 샘플링 (전처리 O(n)) — 함수명: sample_total_draws
  - 추가 에피소드 계산: 이항분포 B(7, CEIL_RATIO)
  - 기본 샘플 수: N_SIMS (기본 1,000,000, configurable)
- 2-4. 통계 분석 (summarize)
  - mean, std, percentile rank 등 (summarize 함수)
- 2-5. 시각화 (make_hist_svg)
  - 히스토그램 density 계산, SVG path 생성 (기본 800×450px)
  - 관측값 표시(빨간 수직선), SVG 문자열 반환 (image_svg)

### 3. 배포 / 운영 관련 (Assets + KV + Worker)
- wrangler.toml: ASSETS 바인딩 추가 확인
```toml
[assets]
directory = "./assets"
binding = "ASSETS"
```
- KV 네임스페이스 생성/바인딩
```bash
npx wrangler kv:namespace create "GLOBAL_STORE"
# wrangler.toml에 바인딩 추가: [[kv_namespaces]] binding = "GLOBAL" id = "<namespace-id>"
```
- Assets 기반 precomputed 파일 배포 (자동으로 CDN에 업로드됨)
```bash
# assets/ 디렉토리(./assets/data/precomputed_game1_v2.json 등)를 포함하여 배포
npx wrangler publish  # 또는 npx wrangler deploy
```
- precomputed JSON을 KV로 업로드 (운영 시 KV 폴백용)
```bash
cd kv-upload
node upload-game-data.js  # 설정: JSON_FILE_PATH, NAMESPACE_ID, KEY_PREFIX
```
- 업로드/검증 명령
```bash
npx wrangler kv key list --namespace-id="<NAMESPACE_ID>" --prefix="game1_"
npx wrangler kv key get --namespace-id="<NAMESPACE_ID>" "game1_5"
npx wrangler deploy
```

---

## Features

### 핵심 기능 (핵심 5개 항목)

1. 실시간 몬테카를로 시뮬레이션
   - 엔진: N_SIMS(기본 1,000,000) 기반 샘플링을 지원. 핵심 함수: sample_total_draws, build_pity_cdf, summarize.
   - Walker's Alias Method로 O(1) 샘플링 구현 (compute.preprocess_alias / compute.sample_total_draws).
   - SVG 히스토그램 자동 생성 (compute.make_hist_svg).

2. Assets 기반 사전계산(Precomputed) 우선 전략 (신규)
   - ASSETS 바인딩(assets/)에 precomputed_game{1,2}_v2.json을 배포하여 엣지에서 직접 읽음.
   - entry.py는 먼저 ASSETS.fetch("/data/precomputed_game{game_id}_v2.json") 시도 → goal 인덱스에서 [min_val, freq_list]를 추출 → decompress_totals로 totals 복원.
   - Assets 캐시 히트 시 응답 지연을 대폭 단축(응답 ~5-8ms 목표).

3. KV 기반 사전계산 폴백 및 운영 툴링
   - load_precomputed_from_kv(kv_store, game_id, goal) 비동기 함수로 KV 조회 지원.
   - kv-upload/upload-game-data.js: 대량 precomputed JSON을 KV에 일괄 업로드하는 스크립트.
   - kv-upload/worker-game-data.ts: KV 조회용 예제 Worker (운영/검증용).

4. 다중 게임 모드 및 Pity 모델링
   - GAME_ID=1/2 등 다중 모드 지원 (예: CEIL_RATIO, MAX_T, BASE_P 값)
   - Pity 가속(ACCEL_START, ACCEL_STEP) 및 확률 조합은 build_pity_cdf에서 처리.

5. 인터랙티브 웹 UI 및 결과 내보내기
   - 입력: GAME_ID, GOAL, OBS_TOTAL
   - 실시간 요약(평균/표준편차/백분위)과 SVG 렌더링
   - SVG/JSON 다운로드 및 클라이언트 사이드 렌더링 (app.js)

### 기술적 특징

알고리즘
- Walker's Alias Method: O(1) 샘플링 (전처리 O(n)) — compute.preprocess_alias / sample_total_draws.
- 이항분포 샘플링: 추가 에피소드 계산에 B(7, CEIL_RATIO) 사용.
- 압축 포맷(v2): [min_val, freq_list] 형식으로 1,000,000개 이상의 샘플 빈도를 효율적으로 저장/전송.

성능 (요약)
- Assets(ASSETS 바인딩) 사용 시: 응답 시간 약 ~5-8ms (assets.fetch 1-3ms + 압축 해제 20ms + 통계 5ms 기준 최적화; PERFORMANCE.md 참조).
- KV 조회 경로: 대략 40-50ms (네트워크 왕복 포함, 환경 의존).
- 라이브 시뮬레이션: 수초(환경/설정에 따라 5~10초).
- SVG 생성(make_hist_svg): 목표 <100ms.

보안 및 안정성
- CORS 헤더 설정 (entry.py 및 worker-game-data.ts).
- JSON 입력 검증 (entry.py: 요청 body 파싱/정수 변환/범위 체크).
- 에러 로깅 및 예외 처리 강화 (load_precomputed_from_kv 내부 예외 캐치 등).
- KV 사용 시 주의: eventual consistency, 읽기 비용 제약(플랜별 제한).

CI / 도구
- README 자동 갱신 스크립트(.github/scripts/update_readme.py): 변경 diff를 LLM에 전달하여 README 자동 갱신.
- PERFORMANCE.md: 배포/운영 시 Assets 우선 전략과 비용/CPU 분석 제공.
- kv-upload 툴: precomputed 데이터의 운영 반영을 자동화.

---

## Versions

### v2.3 (2025-10-17)
**주요 변경사항**
- Assets 기반 사전계산 추가: assets/data/precomputed_game1_v2.json 및 precomputed_game2_v2.json 추가(ASSETS 바인딩을 통해 엣지에서 직접 제공).
- PERFORMANCE.md 추가: Assets 우선 전략(ASSETS 바인딩), Assets vs KV vs live의 성능/메모리/비용 분석 문서화.
- Workflow 업데이트: entry.py 처리 흐름이 Assets -> KV -> live 순서로 변경(Assets fetch 우선).
- wrangler.toml에 ASSETS 바인딩([assets] directory = "./assets", binding = "ASSETS") 권장/문서화.

**최적화**
- Assets(전역 CDN)에서 사전계산을 읽으면 응답 시간 대폭 단축(수백 ms → ~5-8ms).
- Assets 캐시 히트 시 CDF/샘플링 경로(전처리)를 건너뜀으로써 CPU 사용량과 비용 절감.
- precomputed v2 빈도 리스트 포맷을 통해 네트워크/스토리지 효율 개선(파일 크기: game1 ~102KB, game2 ~117KB).

**버그 수정 / 안정성 개선**
- Assets와 KV 경로 병행 시 예외/파싱 로직 보강(Assets JSON 파싱 실패 시 KV 폴백, 로깅 강화).
- kv-upload 스크립트의 임시 파일 처리 안정화(대용량 업로드 중 안정성 향상).

**새 기능**
- PERFORMANCE.md: 배포 체크리스트, 로컬/실서버 테스트 예시, 추가 최적화 옵션(Brotli, 파일 분리, 메모리 캐시) 제시.
- assets/data/* 로 precomputed 파일 배포 가능 — 엣지에서 직접 읽어 latency 최적화.

---

### v2.2 (2025-10-17)
**주요 변경사항**
- KV 사전계산 통합: src/logic/compute.py에 async load_precomputed_from_kv(kv_store, game_id, goal) 추가 및 run_simulation 서명 확장(kv_store, precomputed_data).
- entry.py 변경: 요청 처리 시 load_precomputed_from_kv 호출, run_simulation에 precomputed_data 전달. 로그에 데이터 소스 표기("KV precomputed" 또는 "live simulation") 추가.
- KV 업로드 툴 추가: kv-upload/upload-game-data.js (JSON -> wrangler kv key put), kv-upload/worker-game-data.ts (예제 KV 조회 Worker), kv-upload/README.md 문서화.
- 운영 문서 추가: KV_INTEGRATION.md로 키/값 포맷, 업로드/성능/주의사항 상세 문서화.

**최적화**
- precomputed_data 사용 경로 추가로 반복 샘플링 회피 → latency 크게 개선(수백 ms → 수십 ms).
- run_simulation에서 precomputed path 시 n_sims = len(totals)로 자동 조정.
- kv-upload 스크립트에서 업로드시 임시 파일 생성 후 wrangler로 업로드하여 대용량 처리 안정화.

**버그 수정 / 안정성 개선**
- KV 조회 실패/파싱 예외 처리 보강 (load_precomputed_from_kv 내부에서 예외 캐치 및 로그 출력).
- entry.py에서 cdf 캐싱 로직 유지하면서 precomputed_data 우선 사용 흐름 정렬.

**새 기능**
- kv-upload 툴: 대량의 precomputed JSON을 KV로 자동 업로드하는 CLI 스크립트 제공.
- worker-game-data.ts: KV 데이터를 HTTP로 조회할 수 있는 예제 Worker (운영/검증 용도).
- KV_INTEGRATION.md: KV 운영 가이드(키 규칙: game{game_id}_{goal}, 값 포맷: [min_val, freq_list]) 및 성능 비교 표 포함.

---

### v2.1 (2025-10-17)
**주요 변경사항**
- README 자동 갱신 스크립트 업데이트: .github/scripts/update_readme.py가 OpenAI Responses API(client.responses.create) 사용하도록 변경.
- llm_summarize 반환값 처리: resp.output_text 사용.
- token_param {"max_output_tokens": 6000} 추가.

**최적화**
- LLM 호출 파라미터 정리 및 출력 토큰 한도 증가.

**버그 수정**
- 구버전 OpenAI 호출(choices/message 기반) 호환성 문제 수정.

---

### v2.0 (2025-10-14)
**주요 변경사항**
- Cloudflare Workers Python 런타임으로 전환.
- KV 네임스페이스 기반 CDF 캐싱 추가.
- Assets 바인딩을 통한 정적 파일 관리.
- 압축 데이터 v2 포맷 적용 (빈도 리스트).

**최적화**
- 메모리 GC 강제 실행(시뮬레이션 전후).
- Walker's Alias Method 인라인 최적화.

**버그 수정**
- JSON 파싱 실패 시 에러 핸들링 강화.
- SVG Blob URL 관련 메모리 누수 완화.

---

### v1.0 (Initial Release)
- 기본 몬테카를로 시뮬레이션 엔진
- 정규분포 피팅 기능
- 히스토그램 시각화
- 2개 게임 모드 지원
- 사전 계산 데이터 생성 스크립트
<!-- AUTO-UPDATE:END -->

<!-- LAST_PROCESSED_SHA: 35b2de312034ca2553f992df8a8c304d019bb3a9 -->
