# Cloudflare workers
Cloudflare workers를 활용한 webpage test입니다.

## Monte Carlo Simulation Web App

Cloudflare Workers 기반의 몬테카를로 시뮬레이션 웹 애플리케이션입니다. 가챠 게임의 확률 분포를 시뮬레이션하고 정규분포 피팅 결과를 시각화합니다.

<!-- AUTO-UPDATE:START -->
## Dir Structure

```
webpage/
├── assets/                    # 정적 파일 (프론트엔드)
│   ├── index.html            # 메인 HTML 페이지
│   ├── app.js                # 클라이언트 로직 (API 호출, UI 업데이트)
│   └── styles.css            # 스타일시트
│
├── src/                      # 백엔드 로직 (Python Workers)
│   ├── entry.py              # Workers 진입점 (라우팅, CORS, KV)
│   └── logic/                # 시뮬레이션 코어 로직
│       ├── __init__.py
│       ├── compute.py        # 시뮬레이션 엔진 (CDF, Alias Method, SVG 생성)
│       ├── generate_precomputed.py  # 사전 계산 데이터 생성 스크립트
│       ├── convert_data.py   # 데이터 포맷 변환 유틸리티
│       ├── precomputed_game1.json    # GAME_ID=1 사전 계산 데이터
│       ├── precomputed_game2.json    # GAME_ID=2 사전 계산 데이터
│       ├── precomputed_game1_v2.json # GAME_ID=1 압축 데이터 (v2)
│       └── precomputed_game2_v2.json # GAME_ID=2 압축 데이터 (v2)
│
├── wrangler.toml             # Cloudflare Workers 설정
└── README.md
```

## Workflow

### 1. 클라이언트 요청 흐름

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

### 2. 시뮬레이션 파이프라인

**2-1. CDF 구성 (build_pity_cdf)**
- Pity 시스템 기반 확률 모델링
- BASE_P + 가속 구간 (ACCEL_START 이후)
- 생존 확률 기반 PMF → CDF 변환

**2-2. 몬테카를로 샘플링 (sample_total_draws)**
- Walker's Alias Method로 O(1) 샘플링
- 이항분포 B(7, CEIL_RATIO)로 추가 에피소드 계산
- 1,000,000회 반복 시뮬레이션

**2-3. 통계 분석 (summarize)**
- 평균, 표준편차 계산
- 관측값의 백분위 순위 (percentile rank)

**2-4. 시각화 (make_hist_svg)**
- 히스토그램 density 계산
- SVG path 생성 (800×450px)
- 관측값 표시 (빨간 수직선)

### 3. 배포 프로세스

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
- Walker's Alias Method를 통한 최적화된 샘플링
- 메모리 효율적인 빈도 리스트 압축

**2. 다중 게임 모드 지원**
- GAME_ID=1: CEIL_RATIO=0.5, MAX_T=80, BASE_P=0.008
- GAME_ID=2: CEIL_RATIO=0.55, MAX_T=90, BASE_P=0.006
- Pity 시스템 가속 구간 (ACCEL_START, ACCEL_STEP)

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
- KV 기반 CDF 캐싱 (게임별)
- 메모리 GC 강제 실행
- CORS 지원 (전체 도메인)
- Assets 바인딩을 통한 정적 파일 서빙

### 기술적 특징

**알고리즘**
- Walker's Alias Method: O(1) 샘플링 (전처리 O(n))
- 인라인 이항분포 샘플링 (함수 호출 오버헤드 제거)
- 빈도 리스트 압축 (무손실, 최대 96% 압축률)

**성능**
- 1,000,000회 시뮬레이션 < 2초 (Cloudflare Workers)
- SVG 생성 < 100ms
- KV 캐시 히트 시 CDF 계산 스킵

**보안**
- CORS 헤더 설정
- JSON 입력 검증
- 에러 트레이스백 로깅

## Versions

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

---

## API Reference

### POST /api/simulate

**Request Body**
```json
{
  "GAME_ID": 1,
  "GOAL": 7,
  "OBS_TOTAL": 888
}
```

**Response**
```json
{
  "ok": true,
  "summary": {
    "samples": 1000000,
    "obs_total_draws": 888,
    "mean_total_draws": 678.1234,
    "std_total_draws": 89.5678,
    "percentile_rank_of_obs_%": 97.12345
  },
  "image_svg": "<svg xmlns=\"http://www.w3.org/2000/svg\">...</svg>"
}
```

### GET /api/health

**Response**
```json
{
  "ok": true
}
```

---

## Development

### 요구사항
- Node.js 18+
- Wrangler CLI
- Cloudflare Workers 계정

### 로컬 실행
```bash
# 의존성 설치
npm install -g wrangler

# 개발 서버 실행
npx wrangler dev

# 브라우저에서 접속
# http://localhost:8787
```

### 사전 계산 데이터 생성
```bash
cd src/logic
python generate_precomputed.py
```

### 배포
```bash
# wrangler.toml 설정 확인
# - name: 프로젝트 이름
# - kv_namespaces: KV ID 설정

# 배포 실행
npx wrangler deploy
```

---

## License

MIT License
<!-- AUTO-UPDATE:END -->

<!-- LAST_PROCESSED_SHA: 0000000 -->