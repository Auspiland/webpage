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
│   │                                         클라이언트 측 타이밍 계측 추가: runSimulate에서 clientStart/ fetch/parse/total 측정 및 서버 타이밍 출력(응답에 timings 필드가 있으면 정렬 출력).
│   ├── styles.css                          # 스타일시트
│   └── data/
│       ├── precomputed_game1_v2.json       # GAME_ID=1 압축 사전계산 데이터 (v2, 빈도 리스트) — Assets 우선 읽기 대상
│       └── precomputed_game2_v2.json       # GAME_ID=2 압축 사전계산 데이터 (v2, 빈도 리스트)
│
├── src/                                    # 백엔드 로직 (Python Workers)
│   ├── entry.py                            # Workers 진입점 (라우팅, CORS, Assets 우선 조회 -> load_precomputed_from_assets 사용; 요청/컴퓨트 타이밍 계측 추가, 응답에 "timings" 병합 포함)
│   └── logic/                              # 시뮬레이션/유틸 로직
│       ├── __init__.py
│       ├── compute.py                      # 런타임 경량화된 시뮬레이션 핸들러
│       │                                        - 주요 역할: 압축 데이터(decompress_totals) 복원, summarize, make_hist_svg, run_simulation에서 타이밍 수집 후 (summary, svg, timings) 반환
│       │                                        - 변경/중요: 라이브 샘플링(sample_total_draws) 및 CDF/alias 관련 전처리 함수는 이 파일에서 제거되어 더 이상 런타임 경로에서 사용되지 않음. run_simulation은 precomputed_data 필수(없으면 ValueError).
│       ├── compute_not_used.py              # (신규) 사용되지 않는/아카이브된 구현 모음:
│       │                                        - compress_totals, build_pity_cdf, _build_alias_from_cdf, _alias_sample, _binomial_7, sample_total_draws 등 원래의 샘플링 및 사전계산 유틸리티를 보관
│       │                                        - 파일에는 또한 load_precomputed_from_assets, load_precomputed_from_kv, generate_precomputed_data, save/load 유틸리티가 포함되어 있어 오프라인 생성/검증/백오피스 용도에 적합
│       ├── precomputed_game1.json          # (보존용) GAME_ID=1 원본 사전 계산 데이터 (디버그/생성용) — 사용 중이진 않음
│       ├── precomputed_game2.json          # (보존용) GAME_ID=2 원본 사전 계산 데이터
│       ├── precomputed_game1_v2.json       # GAME_ID=1 압축 데이터 (v2) - 빈도 리스트 형식 (assets/data/)
│       └── precomputed_game2_v2.json       # GAME_ID=2 압축 데이터 (v2) - 빈도 리스트 형식 (assets/data/)
│
├── wrangler.toml                           # Cloudflare Workers 설정
│   ├─ (ASSETS) [assets] directory = "./assets", binding = "ASSETS"  # Assets 바인딩: precomputed JSON을 엣지에서 직접 읽도록 설정됨
│   └─ (KV) [[kv_namespaces]] binding = "GLOBAL" id = "<namespace-id>"  # KV 네임스페이스 바인딩 (운영/툴링용)
└── README.md                               # 프로젝트 설명 및 API/개발 가이드 (자동 갱신 메커니즘 포함)
```

- 추가/변경 주요 파일 설명
  - assets/app.js: runSimulate에 client-side 타이밍 계측 추가(변수: clientStartTime, fetchStartTime, fetchEndTime, parseStartTime, parseEndTime, clientEndTime). 서버에서 반환하는 timings 필드가 존재하면 정렬하여 출력.
  - src/entry.py:
    - 요청 처리 타이밍 계측 추가: request 전체/단계별 타이밍(예: "0_parse_request_ms", "1_load_assets_ms", "2_cdf_cache_ms", "3_run_simulation_total_ms", "4_total_request_ms")을 기록.
    - run_simulation 호출 결과로 compute_timings을 받음. compute_timings과 request_timings를 병합하여 응답의 "timings" 필드로 반환하도록 변경.
    - 기존 동작: ASSETS에서 precomputed 조회(load_precomputed_from_assets), 데이터 없으면 400 반환(라이브 시뮬레이션/kv 폴백 비활성화)은 유지.
  - src/logic/compute.py:
    - 런타임 경량화: alias/샘플링/CDF 구성 관련 함수 제거. 현재는 decompress_totals, summarize, make_hist_svg와 run_simulation(요약+타이밍 수집)을 제공.
    - run_simulation 반환형 변경: (summary_dict, svg_string, timing_dict).
    - 타이밍 키 예: "1_validation_ms", "2_decompress_ms", "3_summarize_ms", "4_svg_generation_ms", "5_total_compute_ms".
  - src/logic/compute_not_used.py: 새 파일로, 이전에 compute.py에 있던 샘플링 알고리즘(Alias method, sample_total_draws), compress_totals, build_pity_cdf, precompute 생성/파일/KV 관련 유틸리티들을 보관(아카이브/관리용). 런타임 경로에서는 사용되지 않지만 운영/오프라인 precompute 생성 시 참조 가능.

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
POST /api/simulate
    ↓
entry.py (라우팅, 요청 검증, CORS, 서버 타이밍 계측)
    - 타이밍 항목 수집 시작: t_request_start
    - JSON 파싱 후 request_timings["0_parse_request_ms"] 기록
    ↓
1) Assets(ASSETS 바인딩)에서 사전계산 조회 시도:
    - 호출: precomputed_data = await load_precomputed_from_assets(self.env.ASSETS, game_id, goal)
    - entry.py가 로드 시간 측정(request_timings["1_load_assets_ms"])
    - if precomputed_data found:
        - precomputed_data == [min_val, freq_list]
        - totals = decompress_totals(min_val, freq_list)
        - run_simulation(..., precomputed_data=precomputed_data, kv_store=store)
    - else:
        - 즉시 400 응답: {"ok": False, "error": "No precomputed data for game_id={game_id}, goal={goal}. Please use goal between 1-20."}
        - (현재 KV 폴백 및 라이브 샘플링 경로 비활성화)
    ↓
run_simulation(..., precomputed_data=precomputed_data)
    - 현재 동작: precomputed_data 필수이며, totals 복원 후 summarize → make_hist_svg
    - run_simulation은 내부에서 단계별 타이밍 수집(compute_timings) 및 최종 timings dict 반환
    - 핵심 함수: decompress_totals, summarize(totals, obs_total, n_sims), make_hist_svg(totals, obs_total, bins, title)
    - 반환값: (summary, svg, compute_timings)
    ↓
entry.py:
    - request_timings["3_run_simulation_total_ms"] 등 추가 기록
    - compute_timings와 request_timings를 병합: all_timings = {**request_timings, **compute_timings}
    - 최종 JSON 응답에 "timings": all_timings 포함
    ↓
클라이언트 처리 (assets/app.js):
    - 클라이언트는 fetch/parse 타이밍을 측정하여 콘솔에 출력
    - 서버 응답에 timings 필드가 있으면 정렬하여 서버 내부 단계별 타이밍을 출력
```

- 주요 라우트 (변경점 요약)
  - POST /api/simulate
    - 요청 body: { "GAME_ID", "GOAL", "OBS_TOTAL", "N_SIMS"?: int, "SEED"?: int, "BINS"?: int }
    - 현재 처리:
      1. ASSETS에서 precomputed JSON 파일에서 goal 인덱스 조회(load_precomputed_from_assets).
      2. Assets에 항목이 없으면 400 에러 반환(실시간 시뮬레이션 및 KV 폴백 비활성화).
      3. Assets에 항목이 있으면 decompress_totals → run_simulation(요약/시각화 + compute 타이밍) → entry.py가 request 타이밍을 덧붙여 JSON 응답 반환. 응답 구조에 "timings" 필드(서버 내부 단계별 ms 단위)가 추가됨.
  - GET /api/health: 상태 확인 ({"ok": true}) — 유지

### 2. 시뮬레이션 파이프라인 (업데이트 요약)
- 2-1. 입력 검증
  - 클라이언트에서 GOAL 범위(1~20) 확인 (assets/app.js) + 서버에서도 entry.py가 정수 변환/범위 검증 수행.
- 2-2. 데이터 소스 (현재)
  - ASSETS(엣지) 우선: assets/data/precomputed_game{1,2}_v2.json에서 goal 인덱스 조회 → [min_val, freq_list] 반환
  - KV 폴백: 런타임 경로에서 비활성화(하지만 kv-upload 도구를 통한 KV 저장은 별도 운영 목적)
  - 라이브 샘플링: compute_not_used.py에 원래 샘플링/alias 구현 보관(아카이브). 런타임 경로에서는 비활성화
- 2-3. 통계/타이밍/시각화
  - totals 복원(decompress_totals) → summarize(mean, std, percentiles 등) → make_hist_svg(히스토그램 SVG 생성)
  - run_simulation은 단계별 타이밍(compute_timings)을 수집하여 반환
  - entry.py는 request-level 타이밍(request_timings)을 수집하여 compute_timings과 병합 ⇒ 응답의 "timings" 필드 제공
  - 클라이언트는 fetch/parse/total 타이밍을 측정하고, 서버 타이밍을 받아 콘솔에 정렬 출력

### 3. 배포 / 운영 관련 (변경 없음 / 권장)
- wrangler.toml: ASSETS 바인딩 필요 확인 (변경 없음)
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

1. 실시간 몬테카를로 시뮬레이션 (운영 경로에서는 비활성화, 코드 보존)
   - 관련 함수(보존 위치): sample_total_draws, _build_alias_from_cdf, _alias_sample, _binomial_7 등은 src/logic/compute_not_used.py에 보관(오프라인/개발용).
   - 런타임 정책: src/logic/compute.run_simulation은 precomputed_data(압축 빈도 리스트)를 필수로 요구하며, 실시간 샘플링 경로는 배포 시 비활성화되어 있음.
   - 설계 의도: 오프라인에서 대규모 precompute를 생성(예: N_SIMS=100,000)하여 Assets에 배포하고 엣지에서 빠르게 응답.

2. Assets 기반 사전계산(Precomputed) 우선 전략 (운영 중심)
   - ASSETS 바인딩을 통해 assets/data/precomputed_game{1,2}_v2.json에서 goal별 [min_val, freq_list]를 조회.
   - 함수/엔드포인트: load_precomputed_from_assets(...) 호출 (처리 흐름은 entry.py에서 수행).
   - 장점: 엣지 fetch(일반적으로 ~1-3ms) + 압축 해제 → 즉시 통계/시각화(서버 내부 타이밍 측면에서 빠른 응답).

3. 운영/관리용 KV 업로드 및 오프라인 툴
   - kv-upload/upload-game-data.js: precomputed JSON을 KV에 업로드하는 관리자용 도구(운영/검증).
   - compute_not_used.py 내부에 load_precomputed_from_kv, generate_precomputed_data 등 오프라인 유틸이 보관되어 있음.
   - 주의: 현재 entry.py는 KV 폴백을 사용하지 않으므로 KV에 올려도 런타임에서 자동 조회되지 않음(운영 정책에 따라 변경 가능).

4. 다중 게임 모드 및 Pity 모델링 (파라미터화된 구성)
   - GAME_TABLE 기반 파라미터 사용: CEIL_RATIO, MAX_T, BASE_P 등(이전 CDF 구성 함수는 아카이브된 상태지만 파라미터 테이블은 유지).
   - 시스템은 precomputed 데이터(빈도 리스트)를 통해 다양한 goal/게임 설정을 빠르게 처리.

5. 웹 UI / 시각화 및 성능 계측
   - 입력: GAME_ID, GOAL(1~20), OBS_TOTAL (assets/index.html, assets/app.js)
   - 출력: summarize 결과(JSON) + make_hist_svg로 생성된 SVG 문자열
   - 신규: 클라이언트 측 타이밍 로깅(assets/app.js). 서버는 내부 단계별 타이밍을 수집하여 응답의 "timings" 필드로 제공함 → 성능 분석 및 디버깅이 용이.

### 기술적 특징

알고리즘
- Walker's Alias Method 및 고성능 샘플링 알고리즘:
  - 원래 구현(전처리 및 O(1) 샘플링)은 compute_not_used.py에 보존되어 있으며, 필요시 오프라인/로컬 테스트에 재사용 가능.
- 압축 포맷(v2):
  - [min_val, freq_list] 형식으로 대규모 샘플 빈도를 효율적으로 저장/전송(Assets에 배포).
- 통계 처리:
  - summarize(totals, obs_total, n_sims)에서 평균, 표준편차, 백분위수 등을 산출. make_hist_svg는 히스토그램을 SVG로 렌더링.

성능 / 계측 (요약)
- 서버 측 타이밍 계측:
  - entry.py: request-level 단계 타이밍(예: "0_parse_request_ms", "1_load_assets_ms", "2_cdf_cache_ms", "3_run_simulation_total_ms", "4_total_request_ms")
  - compute.run_simulation: compute-level 단계 타이밍(예: "1_validation_ms", "2_decompress_ms", "3_summarize_ms", "4_svg_generation_ms", "5_total_compute_ms")
  - 응답에 timings 딕셔너리 포함 → 운영/디버깅용 상세 프로파일링 가능
- 클라이언트 측 타이밍:
  - assets/app.js가 fetch/parse/total 소요를 측정하여 서버 타이밍과 함께 콘솔에 출력
- 성능 기대치:
  - ASSETS에서 사전계산 조회 시: 엣지 fetch + 압축 해제 → 매우 짧은 응답(자주 ~1-10ms 내부 컴퓨트 추가)
  - KV 조회 또는 라이브 시뮬레이션(활성화된 경우): 더 높은 지연 가능(수십 ms~초)

보안 및 안정성
- CORS 헤더 설정 및 입력 검증(entry.py 및 client-side) 유지
- 서버는 precomputed 부재 시 명확한 400 응답 반환(메시지 포함)
- 타이밍 정보는 디버깅 목적이며, 운영 환경에서는 민감 정보 노출 여부를 검토 후 필터링 권장

CI / 도구
- README 자동 갱신 스크립트(.github/scripts/update_readme.py) 및 PERFORMANCE.md 참조
- compute_not_used.py는 아카이빙된 구현을 포함하므로, 오프라인 precompute 생성/디버깅 시 재사용 가능

---

## Versions

### v2.5 (2025-10-20)
**주요 변경사항**
- 서버/클라이언트 성능 계측(Profiling) 도입:
  - src/entry.py에 request-level 타이밍 수집 로직 추가(예: "0_parse_request_ms", "1_load_assets_ms", "2_cdf_cache_ms", "3_run_simulation_total_ms", "4_total_request_ms").
  - src/logic/compute.run_simulation이 compute-level 타이밍을 수집해 반환하도록 변경(반환값: (summary, svg, compute_timings)).
  - entry.py는 compute_timings과 request_timings을 병합하여 JSON 응답의 "timings" 필드로 반환.
  - assets/app.js에 client-side 타이밍(페치/파싱/총 소요) 측정 및 서버 타이밍 정렬 출력 추가.
- compute.py 리팩터링(경량화):
  - 샘플링/alias/CDF 구성 등 런타임에서 사용되지 않는 무거운 함수들을 제거하여 런타임 파일을 경량화.
  - run_simulation은 precomputed_data(decompressed totals) 기반의 요약/시각화/타이밍 수집에 집중.
- 아카이브 파일 추가:
  - src/logic/compute_not_used.py 추가: 이전의 compress_totals, build_pity_cdf, _build_alias_from_cdf, sample_total_draws, load_precomputed_from_assets/load_precomputed_from_kv, generate_precomputed_data 등 원래 구현을 보존(오프라인/관리용).

**최적화**
- 런타임 파일에서 불필요한 알고리즘 제거로 로딩
<!-- AUTO-UPDATE:END -->

<!-- LAST_PROCESSED_SHA: 950fd03006bc03db97e223a0e81e0ca37a7fe628 -->
