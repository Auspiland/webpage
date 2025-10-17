# Cloudflare workers
Cloudflare workers를 활용한 webpage test입니다.

## Monte Carlo Simulation Web App

Cloudflare Workers 기반의 몬테카를로 시뮬레이션 웹 애플리케이션입니다. 가챠 게임의 확률 분포를 시뮬레이션하고 정규분포 피팅 결과를 시각화합니다.

<!-- AUTO-UPDATE:START -->
## Dir Structure

```
# 루트 (프로젝트 최상위)
├── KV_INTEGRATION.md                      # KV 통합 문서: KV 데이터 키/값 포맷, 업로드/운영 가이드, 성능 비교
├── kv-upload/                             # KV 업로드 도구 및 예제 Worker
│   ├── README.md                          # kv-upload 사용법 및 예제
│   ├── upload-game-data.js                # JSON -> KV 업로드 스크립트 (wrangler kv key put 사용)
│   └── worker-game-data.ts                # KV를 읽어주는 예제 Cloudflare Worker (GET /game1/{key}, /game1/list, /game1/all)
│
webpage/
├── assets/                                # 정적 파일 (프론트엔드)
│   ├── index.html                         # 메인 HTML 페이지
│   ├── app.js                             # 클라이언트 로직 (API 호출, UI 업데이트)
│   └── styles.css                         # 스타일시트
│
├── src/                                   # 백엔드 로직 (Python Workers)
│   ├── entry.py                           # Workers 진입점 (라우팅, CORS, KV 통합 시도, 요청 로깅) - 변경: KV 사전계산 로드 호출(load_precomputed_from_kv), run_simulation 인자 확장
│   └── logic/                             # 시뮬레이션 코어 로직
│       ├── __init__.py
│       ├── compute.py                     # 시뮬레이션 엔진 및 유틸 (CDF 구성, Alias Method, SVG 생성)
│       │                                       핵심 함수: build_pity_cdf, sample_total_draws, summarize, make_hist_svg
│       │                                       변경/추가: run_simulation 서명 확장(kv_store, precomputed_data), load_precomputed_from_kv(async), decompress_totals 사용 경로
│       ├── generate_precomputed.py        # 사전 계산 데이터 생성 스크립트 (precompute -> JSON)
│       ├── convert_data.py                # 데이터 포맷 변환 유틸리티
│       ├── precomputed_game1.json         # GAME_ID=1 사전 계산 데이터 (원본)
│       ├── precomputed_game2.json         # GAME_ID=2 사전 계산 데이터 (원본)
│       ├── precomputed_game1_v2.json      # GAME_ID=1 압축 데이터 (v2) - 빈도 리스트 형식
│       └── precomputed_game2_v2.json      # GAME_ID=2 압축 데이터 (v2) - 빈도 리스트 형식
│
├── wrangler.toml                          # Cloudflare Workers 설정 (KV 네임스페이스 바인딩 등)
└── README.md                              # 프로젝트 설명 및 API/개발 가이드 (자동 갱신 메커니즘 포함)
```

- 추가된 파일/디렉토리 설명
  - KV_INTEGRATION.md: KV 통합 전반(키 규칙 game{game_id}_{goal}, 값 포맷 [min_val, freq_list], 업로드/성능/주의사항) 문서화.
  - kv-upload/upload-game-data.js: precomputed JSON을 읽어 wrangler kv key put으로 업로드하는 Node 스크립트. 기본 JSON 경로: src/logic/precomputed_game2_v2.json, KEY_PREFIX 기본 'game2_'.
  - kv-upload/worker-game-data.ts: KV 읽기용 예제 Worker로 GET /game1/{key} /game1/list /game1/all 엔드포인트 제공.
  - src/logic/compute.py: run_simulation 시 precomputed_data 사용 경로 추가, load_precomputed_from_kv() 비동기 함수 추가. run_simulation이 precomputed_data가 있으면 decompress_totals로 totals 복원하여 통계/SVG 생성.
  - src/entry.py: 요청 처리 시 load_precomputed_from_kv(store, game_id, goal) 호출하여 precomputed_data 전달; run_simulation 호출 시 kv_store 및 precomputed_data 인자 전달; 로그에 "KV precomputed" / "live simulation" 출력.

## Workflow

### 1. 클라이언트 요청 흐름 (업데이트)
```
사용자 입력 (index.html)
    ↓
폼 제출 (app.js)
    ↓
POST /api/simulate
    ↓
entry.py (라우팅)
    ↓
1) KV 사전계산 조회 시도: await load_precomputed_from_kv(store, game_id, goal)
    ├─ if precomputed_data: decompress_totals -> totals (압축 복원)
    └─ else: build_pity_cdf (if missing in KV), sample_total_draws -> totals (live 샘플링)
    ↓
run_simulation(...)  # cdf, kv_store, precomputed_data 전달
    ↓
summarize(...) & make_hist_svg(...)
    ↓
JSON 응답 (summary + image_svg)
    ↓
결과 렌더링 (app.js)
```

- 주요 라우트 (변경된 동작 요약)
  - POST /api/simulate: JSON body { "GAME_ID", "GOAL", "OBS_TOTAL" } 전송 → entry.py에서 입력 검증 후:
    - load_precomputed_from_kv(store, game_id, goal)로 KV에 저장된 압축 결과 조회 시도
    - precomputed_data가 존재하면 run_simulation(..., precomputed_data=...)에서 decompress_totals로 복원하여 통계/시각화 생성
    - 없으면 기존 live 시뮬레이션(sample_total_draws, Alias Method) 실행
  - GET /api/health: 상태 확인 ({"ok": true}) — 유지

### 2. 시뮬레이션 파이프라인 (변경 요약)
- 2-1. CDF 구성 (build_pity_cdf)
  - Pity 시스템 기반 확률 모델링
  - BASE_P + 가속 구간 (ACCEL_START 이후)
  - 생존 확률 기반 PMF → CDF 변환
- 2-2. 입력 데이터 소스 분기 (신규)
  - KV 사전계산 사용: load_precomputed_from_kv → 반환 [min_val, freq_list] → decompress_totals(min_val, freq)로 totals 복원 (n_sims = len(totals))
  - 라이브 샘플링: sample_total_draws (Walker’s Alias Method)로 totals 생성
- 2-3. 몬테카를로 샘플링 (sample_total_draws)
  - Walker's Alias Method (O(1) 샘플링, 전처리 O(n)) — 함수명: sample_total_draws
  - 추가 에피소드 계산: 이항분포 B(7, CEIL_RATIO)
  - 기본 샘플 수: N_SIMS (기본 1,000,000, configurable)
- 2-4. 통계 분석 (summarize)
  - mean, std, percentile rank 계산 — summarize 함수 유지
- 2-5. 시각화 (make_hist_svg)
  - 히스토그램 density 계산, SVG path 생성 (기본 800×450px)
  - 관측값 표시(빨간 수직선), SVG 문자열 반환 (image_svg)

### 3. README 자동 갱신 파이프라인 (CI / 개발 워크플로우)
- 위치: .github/scripts/update_readme.py (기존)
- 기능: 변경된 파일 diff를 LLM에 전달하여 README의 자동 갱신 블록 생성 (OpenAI Responses API 사용, token_param max_output_tokens=6000, tenacity 재시도)
- 로컬 실행 예시:
```bash
python .github/scripts/update_readme.py --base-sha <base> --head-sha <head>
```

### 4. KV 업로드 및 배포/운영(신규 절차)
- KV 네임스페이스 생성/바인딩(초기 설정)
```bash
npx wrangler kv:namespace create "GLOBAL_STORE"
# wrangler.toml에 바인딩 추가: [[kv_namespaces]] binding = "GLOBAL" id = "<namespace-id>"
```
- precomputed JSON을 KV로 업로드 (kv-upload 도구)
```bash
# 예: kv-upload 스크립트 사용 (wrangler 로그인 및 네임스페이스 권한 필요)
cd kv-upload
node upload-game-data.js
# (스크립트 내부 설정: JSON_FILE_PATH, NAMESPACE_ID, KEY_PREFIX)
```
- 업로드 확인
```bash
npx wrangler kv key list --namespace-id="<NAMESPACE_ID>" --prefix="game1_"
npx wrangler kv key get --namespace-id="<NAMESPACE_ID>" "game1_5"
```
- Worker 배포
```bash
npx wrangler deploy
```

## Features

### 핵심 기능 (핵심 5개 항목)

1. 실시간 몬테카를로 시뮬레이션
   - 기본 엔진: N_SIMS(기본 1,000,000) 기반 시뮬레이션. 핵심 함수: sample_total_draws, build_pity_cdf, summarize.
   - Walker's Alias Method를 이용한 O(1) 샘플링 (compute.py 구현).
   - SVG 히스토그램(make_hist_svg) 자동 생성.

2. KV 기반 사전계산(Precomputed) 통합 (신규)
   - entry.py가 요청 시 load_precomputed_from_kv(store, game_id, goal)를 호출하여 KV에서 압축된 빈도 리스트([min_val, freq_list]) 로드 시도.
   - precomputed_data 존재 시 run_simulation은 decompress_totals(min_val, freq)로 totals 복원하여 통계/시각화 즉시 반환 — latency 대폭 개선.
   - KV 키 형식: game{game_id}_{goal} (예: game1_5). 데이터 포맷: [min_val, [freq0, freq1, ...]].

3. 다중 게임 모드 지원
   - GAME_ID=1: CEIL_RATIO=0.5, MAX_T=80, BASE_P=0.008
   - GAME_ID=2: CEIL_RATIO=0.55, MAX_T=90, BASE_P=0.006
   - Pity 가속 구간(ACCEL_START, ACCEL_STEP)은 build_pity_cdf에서 처리.

4. 인터랙티브 웹 UI
   - 파라미터 입력: GAME_ID, GOAL, OBS_TOTAL
   - 실시간 요약(평균/표준편차/백분위)과 SVG 렌더링
   - SVG/JSON 다운로드 기능

5. KV 업로드 툴링 및 운영 지원 (신규)
   - kv-upload/upload-game-data.js: precomputed JSON을 읽어 wrangler kv key put로 일괄 업로드.
   - kv-upload/worker-game-data.ts: KV 읽기용 예제 Worker 제공 (운영 시 API로서 활용 가능).
   - 운영 커맨드 예시 포함(KV key list/get/delete).

### 기술적 특징

알고리즘
- Walker's Alias Method: O(1) 샘플링 (전처리 O(n)) — compute.py 내 preprocess_alias/sample_total_draws.
- 인라인 이항분포 샘플링: 추가 에피소드 계산에 B(7, CEIL_RATIO) 사용.
- 빈도 리스트 압축 (v2): 1,000,000개의 결과를 [min_val, freq_list]로 압축하여 저장 및 전송(압축률 약 99% 수준).

성능
- KV 사전계산 사용 시 응답 시간: ~50ms(환경 의존). (KV_INTEGRATION.md 성능 표 참조)
- 라이브 시뮬레이션: 수초 단위(환경 및 N_SIMS에 따라 5~10s).
- SVG 생성(make_hist_svg): <100ms 목표.
- KV 캐시 히트 시 CDF 재계산/샘플링 경로를 건너뛰어 응답 시간 단축.

보안 및 안정성
- CORS 헤더 설정 (entry.py 및 worker-game-data.ts).
- JSON 입력 검증 (entry.py: 요청 body 파싱/정수 변환 검증).
- 에러 로깅 및 트레이스백(에러 발생 시 상세 로그 출력).
- KV 사용 시 주의: eventual consistency, 읽기 비용 제약(플랜별 제한).

CI / 도구
- README 자동 갱신 스크립트(.github/scripts/update_readme.py): OpenAI Responses API(client.responses.create) 사용, token_param max_output_tokens=6000, tenacity 재시도 사용.
- KV 업로드 스크립트 및 예제 Worker로 사전계산 데이터를 운영 환경에 손쉽게 반영 가능.

## Versions

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

### v1.0 (Initial Release)
- 기본 몬테카를로 시뮬레이션 엔진
- 정규분포 피팅 기능
- 히스토그램 시각화
- 2개 게임 모드 지원
- 사전 계산 데이터 생성 스크립트
<!-- AUTO-UPDATE:END -->

<!-- LAST_PROCESSED_SHA: d52a3d952e8f654041623dc56efcadb7f9b95d05 -->
