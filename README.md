# Cloudflare workers
Cloudflare Workers를 활용한 웹페이지 테스트 프로젝트입니다.

## Monte Carlo Simulation Web App
뽑기 확률 분포를 시뮬레이션하고 정규분포 피팅 결과를 시각화하는 Cloudflare Workers 기반 웹 앱입니다.

<!-- AUTO-UPDATE:START -->
## Dir Structure
```

├── KV_INTEGRATION.md           # KV 통합 문서
├── PERFORMANCE.md              # 성능 분석
├── kv-upload/                  # KV 업로드 도구
│   ├── upload-game-data.js     # JSON → KV 업로드
│   └── worker-game-data.ts     # KV 데이터 조회 예제
│
├── webpage/
│   ├── assets/
│   │   ├── index.html          # 메인 HTML
│   │   ├── app.js              # 클라이언트 로직 (API 호출, 타이밍 계측)
│   │   ├── styles.css
│   │   └── data/               # precomputed 데이터
│   │       ├── precomputed_game1_v2.json
│   │       └── precomputed_game2_v2.json
│
├── src/
│   ├── entry.py                # 진입점, 라우팅 및 타이밍 수집
│   └── logic/
│       ├── compute.py          # 핵심 로직: decompress_totals, summarize, make_hist_svg
│       ├── compute_not_used.py # 오프라인/관리용 유틸 (precompute, KV I/O 등)
│       ├── precomputed_game1_v2.json
│       └── precomputed_game2_v2.json
│
├── wrangler.toml               # Cloudflare 설정 (ASSETS/KV 바인딩)
└── README.md

```

**요약**
- `run_simulation`: precomputed_data 기반 요약/시각화, 단계별 타이밍 수집  
- `entry.py`: 요청 타이밍 수집, 예외 시 traceback 로깅  
- `app.js`: 성공 시 타이밍 출력, 에러 시 throw 처리  

## Workflow

### 1. 요청 흐름
```

index.html → app.js (검증/요청)
↓
POST /api/simulate
↓
entry.py (라우팅·CORS·타이밍 수집)
↓
ASSETS에서 precomputed 데이터 조회
↓
run_simulation 실행
↓
요약·SVG 생성 후 timings 포함 응답

````

- **POST /api/simulate**
  - 입력: {GAME_ID, GOAL, OBS_TOTAL, ...}
  - 처리: ASSETS 조회 → decompress/summarize → 결과 반환
  - 예외 시: traceback 출력, "01_" 접두사 포함 에러 JSON
- **GET /api/health**: 상태 확인

### 2. 시뮬레이션 파이프라인
1. 입력 검증 (클라이언트 + 서버)  
2. 데이터 우선순위: ASSETS → KV(비활성) → 오프라인 샘플링  
3. 처리 단계: decompress → summarize → make_hist_svg  
   결과에 compute/request 타이밍 포함  

### 3. 배포 / 운영
- `wrangler.toml` 설정
  ```toml
  [assets]
  directory = "./assets"
  binding = "ASSETS"
    ```

* 배포

  ```bash
  npx wrangler publish
  ```
* KV 네임스페이스

  ```bash
  npx wrangler kv:namespace create "GLOBAL_STORE"
  ```
* KV 업로드 (관리용)

  ```bash
  cd kv-upload && node upload-game-data.js
  ```

## Features

1. **경량화 파이프라인**

   * precomputed_data → decompress → summarize → make_hist_svg
   * 빠른 엣지 응답을 위한 설계

2. **ASSETS 기반 사전계산 우선**

   * 포맷: [min_val, freq_list]
   * 엣지 직접 로드로 지연 최소화

3. **오프라인/관리용 유틸**

   * KV 업로드, precompute 생성 등

4. **다중 게임 모드**

   * goal별 precomputed 지원

5. **웹 UI 및 성능 계측**

   * 입력(GAME_ID, GOAL, OBS_TOTAL) → summary+SVG 출력
   * 클라이언트/서버 타이밍 병합 제공

### 기술적 특징

* Alias 샘플링 및 v2 압축 포맷 사용
* 타이밍 키

  * request: `"0_parse_request_ms"`, `"1_load_assets_ms"` 등
  * compute: `"1_validation_ms"` ~ `"5_total_compute_ms"`
* CORS 및 예외 처리 강화
* README 자동 갱신 스크립트 포함

## Versions

### v2.6 (2025-10-20)

* **변경:** request/computation 타이밍 수집, 예외 로깅 강화
* **최적화:** 샘플링 제거, ASSETS 우선 전략
* **버그 수정:** app.js 타이밍 출력 조건 수정
* **신기능:** API 응답에 timings 필드 포함

### v2.5 (이전)
- ASSETS 기반 precompute 우선 전략
- precomputed(v2) 포맷 도입: [min_val, freq_list]
- 오프라인 KV 업로드 도구(kv-upload)
- 히스토그램 SVG 생성(make_hist_svg) 및 summarize 기능 제공
<!-- AUTO-UPDATE:END -->

<!-- LAST_PROCESSED_SHA: 2e5baf9b64c2181f6c569e0ee736acc5e5f514f0 -->
