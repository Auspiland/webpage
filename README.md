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
│   ├── app.js                              # 클라이언트 로직 (API 호출, UI 업데이트, SVG 렌더링). GOAL 범위 검증 추가 (1~20)
│   ├── styles.css                          # 스타일시트
│   └── data/
│       ├── precomputed_game1_v2.json       # GAME_ID=1 압축 사전계산 데이터 (v2, 빈도 리스트) — Assets 우선 읽기 대상
│       └── precomputed_game2_v2.json       # GAME_ID=2 압축 사전계산 데이터 (v2, 빈도 리스트)
│
├── src/                                    # 백엔드 로직 (Python Workers)
│   ├── entry.py                            # Workers 진입점 (라우팅, CORS, Assets 우선 조회 -> 현재는 Assets에 없으면 400 오류 반환). 변경: load_precomputed_from_assets 호출; KV 폴백/라이브 샘플링 비활성화
│   └── logic/                              # 시뮬레이션 코어 로직
│       ├── __init__.py
│       ├── compute.py                      # 시뮬레이션 엔진 및 유틸 (CDF 구성, Alias Method, SVG 생성)
│       │                                        핵심 함수: build_pity_cdf, sample_total_draws, summarize, make_hist_svg, preprocess_alias
│       │                                        변경/중요: run_simulation은 현재 precomputed_data 필수(없으면 ValueError). 라이브 샘플링 코드 보존용 주석 처리됨.
│       ├── generate_precomputed.py         # 사전 계산 데이터 생성 스크립트 (precompute -> JSON 압축 포맷)
│       ├── convert_data.py                 # 데이터 포맷 변환 유틸리티 (원본 -> v2 빈도 리스트)
│       ├── precomputed_game1.json          # GAME_ID=1 사전 계산 데이터 (원본, 디버그/생성용)
│       ├── precomputed_game2.json          # GAME_ID=2 사전 계산 데이터 (원본)
│       ├── precomputed_game1_v2.json       # GAME_ID=1 압축 데이터 (v2) - 빈도 리스트 형식 (assets/data/)
│       └── precomputed_game2_v2.json       # GAME_ID=2 압축 데이터 (v2) - 빈도 리스트 형식 (assets/data/)
│
├── wrangler.toml                           # Cloudflare Workers 설정
│   ├─ (ASSETS) [assets] directory = "./assets", binding = "ASSETS"  # Assets 바인딩: precomputed JSON을 엣지에서 직접 읽도록 설정됨
│   └─ (KV) [[kv_namespaces]] binding = "GLOBAL" id = "<namespace-id>"  # KV 네임스페이스 바인딩 (운영/툴링용)
└── README.md                               # 프로젝트 설명 및 API/개발 가이드 (자동 갱신 메커니즘 포함)
```

- 추가/변경 주요 파일 설명
  - assets/index.html: GOAL 입력에 max="20" 추가 (클라이언트/서버 범위 일치).
  - assets/app.js: runSimulate 호출 시 GOAL 범위 검증 추가 (1 <= GOAL <= 20). 클라이언트에서 잘못된 값이면 예외 throw.
  - src/entry.py: load_precomputed_from_assets(self.env.ASSETS, game_id, goal)를 통해 Assets에서 사전계산 조회. Assets에 데이터가 없으면 400 에러(JSON 응답: {"ok": False, "error": "...Please use goal between 1-20."})로 즉시 응답. KV 폴백 및 라이브 샘플링 경로는 현재 사용하지 않음.
  - src/logic/compute.py: run_simulation에서 precomputed_data가 필수화됨. precomputed_data 없으면 ValueError 발생. 라이브 시뮬레이션(sample_total_draws 등)은 주석 처리되어 비활성화(코드 보존용).
  - kv-upload/*: KV 업로드/운영 도구는 여전히 존재하지만 현재 런타임 경로(entry.py -> run_simulation)에서는 사용되지 않음(운영/관리 목적).

---

## Workflow

### 1. 클라이언트 요청 흐름 (현재 동작)
```
사용자 입력 (index.html, GOAL 1~20)
    ↓
클라이언트 유효성 검사 (assets/app.js)
    - GOAL 범위 검사: 1 <= GOAL <= 20 (앱에서 예외 발생 시 시뮬레이션 요청 중단)
    ↓
폼 제출 (app.js)
    ↓
POST /api/simulate
    ↓
entry.py (라우팅, 요청 검증, CORS)
    ↓
1) Assets(ASSETS 바인딩)에서 사전계산 조회 시도:
    - 호출: precomputed_data = await load_precomputed_from_assets(self.env.ASSETS, game_id, goal)
    - 내부 동작: ASSETS.fetch(f"/data/precomputed_game{game_id}_v2.json").json() → goal 인덱스 조회
    - if precomputed_data found:
        - precomputed_data == [min_val, freq_list]
        - totals = decompress_totals(min_val, freq_list)
        - run_simulation(..., precomputed_data=precomputed_data, kv_store=store)  # run_simulation은 precomputed path 처리
    - else:
        - 즉시 400 응답: {"ok": False, "error": "No precomputed data for game_id={game_id}, goal={goal}. Please use goal between 1-20."}
        - (현재 KV 폴백 및 라이브 샘플링 경로 비활성화)
    ↓
run_simulation(..., precomputed_data=precomputed_data, kv_store=store)
    - 현재 동작: precomputed_data가 필수이며, totals 복원 후 summarize → make_hist_svg
    - 핵심 함수: decompress_totals, summarize(totals, obs_total), make_hist_svg(totals, obs_total)
    ↓
JSON 응답 { summary: {...}, image_svg: "<svg...>" }
    ↓
결과 렌더링 (app.js)
```

- 주요 라우트
  - POST /api/simulate
    - 요청 body: { "GAME_ID", "GOAL", "OBS_TOTAL" }
    - 현재 처리:
      1. ASSETS에서 precomputed JSON 파일에서 goal 인덱스 조회(load_precomputed_from_assets).
      2. Assets에 항목이 없으면 400 에러 반환(실시간 시뮬레이션 및 KV 폴백 비활성화).
      3. Assets에 항목이 있으면 decompress_totals → summarize → make_hist_svg → JSON 응답 반환.
  - GET /api/health: 상태 확인 ({"ok": true}) — 유지

### 2. 시뮬레이션 파이프라인 (요약)
- 2-1. 입력 검증
  - 클라이언트에서 GOAL 범위(1~20) 확인 (assets/app.js) + 서버에서도 entry.py가 정수 변환/범위 검증 수행.
- 2-2. 데이터 소스 (현재)
  - ASSETS(엣지) 우선: assets/data/precomputed_game{1,2}_v2.json에서 goal 인덱스 조회 → [min_val, freq_list] 반환
  - KV 폴백: 런타임 경로에서 비활성화(하지만 kv-upload 도구를 통한 KV 저장은 별도 운영 목적)
  - 라이브 샘플링: compute.sample_total_draws 경로는 코드상 주석 처리되어 비활성화
- 2-3. 통계 및 시각화
  - totals 복원(decompress_totals) → summarize(mean, std, percentiles 등) → make_hist_svg(히스토그램 SVG 생성)
  - 반환: summary + image_svg (SVG 문자열)

### 3. 배포 / 운영 관련 (Assets 중심)
- wrangler.toml: ASSETS 바인딩 필요 확인
```toml
[assets]
directory = "./assets"
binding = "ASSETS"
```
- CDN(Assets) 기반 precomputed 파일 배포 (엣지에서 직접 읽음)
```bash
# assets/ 디렉토리(./assets/data/precomputed_game1_v2.json 등)를 포함하여 배포
npx wrangler publish  # 또는 npx wrangler deploy
```
- KV 네임스페이스 (운영/툴링용)
```bash
npx wrangler kv:namespace create "GLOBAL_STORE"
# wrangler.toml에 바인딩 추가: [[kv_namespaces]] binding = "GLOBAL" id = "<namespace-id>"
```
- precomputed JSON을 KV로 업로드 (운영 시 수동/백오피스 용도; 현재 런타임에서 KV 폴백 사용하지 않음)
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

1. 실시간 몬테카를로 시뮬레이션 (운영 시 비활성화)
   - 엔진 함수: sample_total_draws, build_pity_cdf, summarize, make_hist_svg (코드 유지)
   - 현재 런타임 정책: 라이브 시뮬레이션 경로는 비활성화되어, run_simulation은 precomputed_data를 필수로 요구함(src/logic/compute.py).
   - 디자인상 실시간 샘플링(예: N_SIMS 기본 1,000,000)은 코드상 존재하나 주석 처리로 배포에서는 사용되지 않음.

2. Assets 기반 사전계산(Precomputed) 우선 전략 (운영 중심)
   - Assets(ASSETS 바인딩)에 precomputed_game{1,2}_v2.json을 배포하여 엣지에서 직접 goal별 [min_val, freq_list]를 조회.
   - 함수/엔드포인트: load_precomputed_from_assets(env.ASSETS, game_id, goal) 호출 (src/entry.py).
   - 장점: 응답 지연 최소화(엣지 fetch + 압축 해제 → 즉시 통계/시각화).

3. KV 업로드 및 운영 툴링 (런타임 폴백은 현재 비활성)
   - kv-upload/upload-game-data.js: precomputed JSON을 KV에 업로드하는 도구(관리자용).
   - kv-upload/worker-game-data.ts: KV 조회 예제 Worker (운영/검증용).
   - 주의: 현재 entry.py는 KV 폴백을 사용하지 않으므로 KV에 업로드하더라도 런타임에서 자동으로 조회되지 않음(운영 정책에 따라 변경 가능).

4. 다중 게임 모드 및 Pity 모델링
   - GAME_ID별 구성: CEIL_RATIO, MAX_T, BASE_P 등 파라미터를 build_pity_cdf에서 사용.
   - compute.build_pity_cdf는 pity 가속(ACCEL_START, ACCEL_STEP)을 반영한 PMF→CDF 변환을 담당.

5. 웹 UI / 시각화 및 클라이언트 유효성 검사
   - 입력: GAME_ID, GOAL(1~20), OBS_TOTAL (assets/index.html, assets/app.js)
   - 출력: summarize 결과(JSON) + make_hist_svg로 생성된 SVG 문자열
   - 클라이언트 측 GOAL 범위 검증(1~20) 추가로 잘못된 요청 조기 차단

### 기술적 특징

알고리즘
- Walker's Alias Method: O(1) 샘플링 (전처리 O(n)) — compute.preprocess_alias / compute.sample_total_draws (코드 보존).
- 이항분포 샘플링: 추가 에피소드 계산에 B(7, CEIL_RATIO) 사용.
- 압축 포맷(v2): [min_val, freq_list] 형식으로 대규모 샘플 빈도를 효율적으로 저장/전송.

성능 (요약)
- Assets(ASSETS 바인딩) 사용 시: 엣지에서 precomputed fetch + 압축 복원으로 응답이 매우 빠름(운영 목표: 단일-digit ms 수준).
- KV 경로(운영용): 네트워크 왕복 포함 시 일반적으로 수십 ms 수준(참고: KV는 현재 런타임 폴백 비활성).
- 라이브 시뮬레이션: 환경에 따라 수초 소요(코드상 존재하지만 배포에서 비활성화).

보안 및 안정성
- CORS 헤더 설정 및 JSON 입력 검증 (entry.py, assets/app.js).
- 서버 측 에러 처리: precomputed 부재 시 명확한 400 오류 반환(에러 메시지에 goal 범위 안내 포함).
- KV 사용 시 주의: eventual consistency, 읽기 비용 제약(플랜별 제한).

CI / 도구
- README 자동 갱신 스크립트(.github/scripts/update_readme.py): 변경 diff를 LLM에 전달하여 README 자동 갱신.
- PERFORMANCE.md: Assets 우선 전략과 배포/테스트 체크리스트 문서화.
- kv-upload 툴: precomputed 데이터의 운영 반영을 자동화(관리자/오프라인 프로세스).

---

## Versions

### v2.4 (2025-10-17)
**주요 변경사항**
- 런타임에서 라이브 시뮬레이션 및 KV 폴백 비활성화: src/entry.py가 ASSETS에서만 precomputed 데이터를 조회하도록 변경되며, 데이터가 없으면 400 오류를 반환하도록 정책 변경됨.
  - 변경된 동작: entry.py -> load_precomputed_from_assets(self.env.ASSETS, game_id, goal)
  - 오류 반환 예시: {"ok": False, "error": "No precomputed data for game_id={game_id}, goal={goal}. Please use goal between 1-20."}
- run_simulation(precomputed_data=...) 필수화: src/logic/compute.py에서 precomputed_data가 없으면 ValueError를 발생시키도록 변경(라이브 경로는 주석 처리).
- 클라이언트 유효성 검사 강화: assets/app.js에서 GOAL 범위(1~20) 검사 추가, assets/index.html에 input max="20" 추가.

**최적화**
- Assets(엣지) 우선 정책으로 응답 지연 최소화(엣지 fetch + 압축 복원 → 즉시 통계/시각화).
- precomputed v2 포맷([min_val, freq_list]) 사용으로 네트워크/저장 효율 유지.

**버그 수정 / 안정성 개선**
- 잘못된/범위를 벗어난 GOAL 요청은 클라이언트 측에서 사전 차단되며, 서버는 명확한 400 응답을 반환하여 불필요한 처리 차단.
- 런타임 경로 단순화로 예외 상황(Assets 미존재 등)에 대한 명확한 실패 모드 정의.

**새 기능**
- 클라이언트 측 GOAL 범위 검증 추가 (assets/app.js).
- 운영/관리용 kv-upload 툴은 유지되며, 필요 시 수동으로 KV에 precomputed를 올려둘 수 있으나 현재 런타임에서 자동 폴백하지 않음.

---
### v2.3 (2025-10-17)
**주요 변경사항**
- Assets 기반 사전계산 추가: assets/data/precomputed_game1_v2.json 및 precomputed_game2_v2.json 추가(ASSETS 바인딩을 통해 엣지에서 직접 제공).
- PERFORMANCE.md 추가: Assets 우선 전략(ASSETS 바인딩), Assets vs KV vs live의 성능/메모리/비용 분석 문서화.
- Workflow 업데이트: entry.py 처리 흐름이 Assets -> KV -> live 순서로 변경(Assets fetch 우선).
- wrangler.toml에 ASSETS 바인딩([assets] directory = "./assets", binding = "ASSETS") 권장/문서화.

**최적화**
- Assets(전역 CDN)에서 사전계산을 읽으면 응답 시간 대폭 단축(수백 ms → ~5-8ms 목표).
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
- 기본 몬테카를로 시뮬레이션 엔
<!-- AUTO-UPDATE:END -->

<!-- LAST_PROCESSED_SHA: 09e7c2d04e77eddda1068eb67300258fb6a8e2af -->
