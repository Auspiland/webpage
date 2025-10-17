# Cloudflare workers
Cloudflare workers를 활용한 webpage test입니다.

## Monte Carlo Simulation Web App

Cloudflare Workers 기반의 몬테카를로 시뮬레이션 웹 애플리케이션입니다. 가챠 게임의 확률 분포를 시뮬레이션하고 정규분포 피팅 결과를 시각화합니다.

<!-- AUTO-UPDATE:START -->
## Dir Structure

```
webpage/
├── assets/                                # 정적 파일 (프론트엔드)
│   ├── index.html                         # 메인 HTML 페이지
│   ├── app.js                             # 클라이언트 로직 (API 호출, UI 업데이트)
│   └── styles.css                         # 스타일시트
│
├── src/                                   # 백엔드 로직 (Python Workers)
│   ├── entry.py                           # Workers 진입점 (라우팅, CORS, KV)
│   └── logic/                             # 시뮬레이션 코어 로직
│       ├── __init__.py
│       ├── compute.py                     # 시뮬레이션 엔진 (CDF 구성, Alias Method, SVG 생성) - 핵심 함수: build_pity_cdf, sample_total_draws, summarize, make_hist_svg
│       ├── generate_precomputed.py        # 사전 계산 데이터 생성 스크립트 (precompute -> JSON)
│       ├── convert_data.py                # 데이터 포맷 변환 유틸리티
│       ├── precomputed_game1.json         # GAME_ID=1 사전 계산 데이터
│       ├── precomputed_game2.json         # GAME_ID=2 사전 계산 데이터
│       ├── precomputed_game1_v2.json      # GAME_ID=1 압축 데이터 (v2)
│       └── precomputed_game2_v2.json      # GAME_ID=2 압축 데이터 (v2)
│
├── wrangler.toml                          # Cloudflare Workers 설정
└── README.md                              # 프로젝트 설명 및 API/개발 가이드 (자동 갱신 메커니즘 포함)
```

## Workflow

### 1. 클라이언트 요청 흐름 (변경 없음 — 기존 엔드포인트 유지)

```
사용자 입력 (index.html)
    ↓
폼 제출 (app.js)
    ↓
POST /api/simulate
    ↓
entry.py (라우팅)
    ↓
compute.py (시뮬레이션 실행)
    ↓
JSON 응답 (summary + SVG)
    ↓
결과 렌더링 (app.js)
```

- 주요 라우트
  - POST /api/simulate: 본문에 JSON { "GAME_ID", "GOAL", "OBS_TOTAL" } 전송 → entry.py에서 입력 검증 후 compute.py의 sample_total_draws, summarize, make_hist_svg 실행
  - GET /api/health: 상태 확인 ({"ok": true})

### 2. 시뮬레이션 파이프라인 (변경 없음 — 로직/함수 명 보존)
- 2-1. CDF 구성 (build_pity_cdf)
  - Pity 시스템 기반 확률 모델링
  - BASE_P + 가속 구간 (ACCEL_START 이후)
  - 생존 확률 기반 PMF → CDF 변환
- 2-2. 몬테카를로 샘플링 (sample_total_draws)
  - Walker's Alias Method(O(1) 샘플링, 전처리 O(n))
  - 추가 에피소드 계산: 이항분포 B(7, CEIL_RATIO)
  - 기본 샘플 수: 1,000,000 반복 (configurable)
- 2-3. 통계 분석 (summarize)
  - 평균(mean), 표준편차(std) 계산
  - 관측값의 백분위 순위(percentile rank) 산출
- 2-4. 시각화 (make_hist_svg)
  - 히스토그램 density 계산
  - SVG path 생성 (기본 800×450px)
  - 관측값 표시(빨간 수직선), SVG 문자열을 image_svg로 반환

### 3. README 자동 갱신 파이프라인 (신규 — CI / 개발 워크플로우 관련)
- 위치: .github/scripts/update_readme.py
- 목적: 변경된 코드/파일 diff를 수집하여 README의 자동 업데이트 섹션을 생성/갱신
- 핵심 구현 세부사항:
  - 함수: llm_summarize(openai_key: str, model: str, prompt: str) -> str
  - OpenAI 클라이언트 초기화: client = OpenAI(api_key=openai_key)
  - Responses API 사용: resp = client.responses.create(..., input=[{"role":"system",...}, {"role":"user",...}], **token_param)
  - token_param: {"max_output_tokens": 6000} (출력 토큰 상한 값으로 확장)
  - 반환: resp.output_text (기존 choices[0].message.content 대신)
  - 재시도: tenacity.retry(wait_exponential(multiplier=1, min=2, max=20), stop_after_attempt(4))
  - 스크립트는 변경된 파일 목록을 수집하여 LLM에 프롬프트로 전달하고, 반환 텍스트를 README의 자동 갱신 블록에 삽입
- 로컬/수동 실행 예시:
```bash
# (관리용) README 갱신 스크립트 실행 (환경변수 OPENAI_API_KEY 필요)
python .github/scripts/update_readme.py --base-sha <base> --head-sha <head>
```

### 4. 배포 프로세스 (변경 없음)
```bash
# 로컬 개발 서버 실행
npx wrangler dev

# Cloudflare Workers 배포
npx wrangler deploy

# KV 네임스페이스 생성 (최초 1회)
npx wrangler kv:namespace create "GLOBAL_STORE"
```

## Features

### 핵심 기능

**1. 실시간 몬테카를로 시뮬레이션**
- 1,000,000회 반복 시뮬레이션을 Edge에서 실행
- Walker's Alias Method를 통한 최적화된 샘플링 (compute.py 내부 구현)
- 메모리 효율적인 빈도 리스트 압축 (precomputed_game*_v2.json 포맷)

**2. 다중 게임 모드 지원**
- GAME_ID=1: CEIL_RATIO=0.5, MAX_T=80, BASE_P=0.008
- GAME_ID=2: CEIL_RATIO=0.55, MAX_T=90, BASE_P=0.006
- Pity 시스템 가속 구간 (ACCEL_START, ACCEL_STEP)은 compute.py의 build_pity_cdf에서 처리

**3. 인터랙티브 웹 UI**
- 파라미터 입력: GAME_ID, GOAL, OBS_TOTAL
- 실시간 결과 요약 (평균, 표준편차, 백분위)
- 색상 코딩된 백분위 표시 (금색: 95%+, 빨강: 10%-)
- SVG/JSON 다운로드 기능

**4. 분포 시각화**
- 히스토그램 density 플롯 (SVG)
- 관측값 위치 표시 (수직선)
- Blob URL 기반 이미지 렌더링 (Base64 없음)

**5. Cloudflare Workers 최적화**
- KV 기반 CDF 캐싱 (게임별 precomputed JSON 바인딩)
- 메모리 GC 강제 실행(시뮬레이션 전후)로 GC 관련 오버헤드 완화
- CORS 지원 (전체 도메인)
- Assets 바인딩을 통한 정적 파일 서빙

### 기술적 특징

**알고리즘**
- Walker's Alias Method: O(1) 샘플링 (전처리 O(n), compute.py 내부 preprocess_alias)
- 인라인 이항분포 샘플링: 함수 호출 오버헤드 최소화 (compute.py 최적화)
- 빈도 리스트 압축: 무손실 압축 포맷(v2)으로 전송/저장 효율화

**성능**
- 1,000,000회 시뮬레이션 목표: Cloudflare Workers에서 < 2초(환경 의존)
- SVG 생성: < 100ms (make_hist_svg)
- KV 캐시 히트 시 CDF 계산 스킵: 응답 시간 단축

**보안**
- CORS 헤더 설정 (entry.py)
- JSON 입력 검증 (entry.py - request body 유효성 검사)
- 에러 트레이스백 로깅 (에러 발생 시 상세 로그)

**CI / 도구 (신규)**
- README 자동 갱신 스크립트 (.github/scripts/update_readme.py)
  - OpenAI Responses API(client.responses.create) 사용하여 diff 요약 및 README 섹션 생성
  - token_param: max_output_tokens=6000로 출력 한도 확장
  - tenacity 기반 재시도(최대 4회)
  - 반환값으로 resp.output_text 사용 — 기존 OpenAI SDK msgs/choices 호환성 변경 반영

## Versions

### v2.1 (2025-10-17)
**주요 변경사항**
- README 자동 갱신 스크립트 업데이트: .github/scripts/update_readme.py 수정
  - llm_summarize 함수가 OpenAI Responses API 호출을 사용하도록 변경: client.responses.create(..., input=[...])
  - 반환값 처리 변경: resp.output_text 사용
  - token_param {"max_output_tokens": 6000} 추가로 LLM 출력 토큰 상한 확장
  - tenacity 재시도 설정 유지(stop_after_attempt=4, wait_exponential)

**최적화**
- README 생성 시 LLM 호출 파라미터 정리(token_param 분리)로 코드 가독성 및 확장성 개선
- 출력 토큰 한도 증가로 더 큰 섹션(4개 섹션 전체)을 안정적으로 처리

**버그 수정**
- 구버전 OpenAI 호출(choices/message 기반) 호환성 문제 수정 — 새 SDK(responses API)로 마이그레이션
- README 마지막 처리 SHA 주석 업데이트: <!-- LAST_PROCESSED_SHA: 4b4d30bb34c702529d5c97bd5ac47f4085ecbfcc -->

**설명**
- 이 변경은 CI/문서 자동화 스크립트에 한정되며, 런타임(Cloudflare Workers) 동작에는 영향 없음.

---

### v2.0 (2025-10-14)
**주요 변경사항**
- Cloudflare Workers Python 런타임으로 전환
- KV 네임스페이스 기반 CDF 캐싱 추가
- Assets 바인딩을 통한 정적 파일 관리
- 압축 데이터 v2 포맷 적용 (빈도 리스트)

**최적화**
- 메모리 GC 강제 실행 (시뮬레이션 전후)
- Walker's Alias Method 인라인 최적화
- 로컬 변수 캐싱 (random, len(prob))

**버그 수정**
- JSON 파싱 실패 시 에러 핸들링 강화
- SVG Blob URL 메모리 누수 방지
- Rate limit 헤더 표시 (준비)

### v1.0 (Initial Release)
- 기본 몬테카를로 시뮬레이션 엔진
- 정규분포 피팅 기능
- 히스토그램 시각화
- 2개 게임 모드 지원
- 사전 계산 데이터 생성 스크립트
<!-- AUTO-UPDATE:END -->

<!-- LAST_PROCESSED_SHA: 4b4d30bb34c702529d5c97bd5ac47f4085ecbfcc -->
