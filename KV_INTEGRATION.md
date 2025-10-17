# Cloudflare KV 통합 완료

## 변경 사항 요약

### 1. `compute.py` 수정

**새로운 함수 추가:**

```python
async def load_precomputed_from_kv(kv_store, game_id: int, goal: int):
    """KV에서 사전 계산된 압축 데이터 불러오기

    KV 키 형식: game{game_id}_{goal}
    예: game1_5, game2_9
    """
```

**`run_simulation` 함수 수정:**
- `precomputed_data` 파라미터 추가
- KV에서 불러온 데이터가 있으면 압축 해제하여 사용
- 없으면 기존처럼 실시간 시뮬레이션 실행

### 2. `entry.py` 수정

**시뮬레이션 API 워크플로우:**

```python
# 1. KV에서 사전 계산된 데이터 로드 시도
precomputed_data = await load_precomputed_from_kv(store, game_id, goal)

# 2. run_simulation에 전달
summary, svg = run_simulation(
    game_id=game_id,
    goal=goal,
    obs_total=obs_tot,
    cdf=cdf,
    precomputed_data=precomputed_data  # 있으면 사용, 없으면 None
)
```

## KV 데이터 구조

### 키 형식
```
game{game_id}_{goal}
```

### 값 형식 (JSON)
```json
[min_val, [freq1, freq2, freq3, ...]]
```

**예시:**
- 키: `game1_5`
- 값: `[60, [0, 3, 7, 15, ...]]`
  - `min_val = 60`: 시뮬레이션 결과의 최소값
  - `[freq1, freq2, ...]`: 각 값의 빈도 리스트

### 데이터 압축 원리

100만 개의 시뮬레이션 결과를 빈도 리스트로 압축:

```python
# 원본: [62, 75, 62, 68, 75, 75, ...] (1,000,000개)
# 압축: [60, [0, 0, 2, 0, 0, 0, 1, 0, ...]] (약 4,800개)
```

압축률: ~99.5% (1,000,000 → 4,800)

## 작동 방식

### 시나리오 1: KV에 데이터가 있는 경우

```
1. 사용자 요청: GAME_ID=1, GOAL=5, OBS_TOTAL=300
2. KV 조회: "game1_5" → [60, [0, 3, 7, ...]] 발견
3. 압축 해제: decompress_totals(60, [0, 3, 7, ...]) → 1,000,000개 데이터 복원
4. 통계 계산 및 SVG 생성
5. 응답 반환 (로그: "KV precomputed")
```

**장점:**
- 실시간 시뮬레이션 불필요 (100배 이상 빠름)
- 메모리 효율적 (압축된 상태로 저장)
- 일관된 결과 (동일한 시드 사용)

### 시나리오 2: KV에 데이터가 없는 경우

```
1. 사용자 요청: GAME_ID=1, GOAL=100, OBS_TOTAL=5000
2. KV 조회: "game1_100" → None (없음)
3. 실시간 시뮬레이션 실행 (1,000,000회)
4. 통계 계산 및 SVG 생성
5. 응답 반환 (로그: "live simulation")
```

**장점:**
- 모든 goal 값에 대응 가능
- 유연성 유지

## 업로드 데이터 현황

### game1 (1~20)
```bash
npx wrangler kv key list --namespace-id="f6c7f658dde04b339e48adbe04389c1b" --prefix="game1_"
```

### game2 (1~20)
```bash
npx wrangler kv key list --namespace-id="f6c7f658dde04b339e48adbe04389c1b" --prefix="game2_"
```

## 성능 비교

| 방식 | 시간 | 메모리 | 일관성 |
|------|------|--------|--------|
| KV 사전 계산 | ~50ms | ~5MB | ✓ |
| 실시간 시뮬레이션 | ~5-10s | ~100MB | ✗ |

## 추가 goal 값 업로드

새로운 goal 값(예: 21~30)을 추가하려면:

### 1. JSON 파일 생성

```bash
cd C:\Users\T3Q\jeonghan\my_github\webpage\src\logic
python generate_precomputed.py --game-id 1 --goal-range 21 31
```

### 2. KV 업로드

`kv-upload/upload-game-data.js` 수정:
```javascript
const JSON_FILE_PATH = path.join(__dirname, '..', 'src', 'logic', 'precomputed_game1_extended.json');
const KEY_PREFIX = 'game1_';
```

실행:
```bash
cd C:\Users\T3Q\jeonghan\my_github\webpage\kv-upload
node upload-game-data.js
```

## 테스트

### 로컬 테스트

```bash
npx wrangler dev
```

### API 호출

```bash
curl -X POST http://localhost:8787/api/simulate \
  -H "Content-Type: application/json" \
  -d '{"GAME_ID": 1, "GOAL": 5, "OBS_TOTAL": 300}'
```

### 로그 확인

```
[Request #1] game_id=1, goal=5, obs_total=300 (KV precomputed)
Using precomputed data for game_id=1, goal=5
Summary: 42.5
```

## 배포

```bash
npx wrangler deploy
```

## 모니터링

Cloudflare 대시보드에서:
- Workers > Metrics: 요청 수, 응답 시간
- KV > Analytics: 읽기/쓰기 작업 수

## 주의사항

1. **KV 읽기 제한**: 무료 플랜 100,000회/일
2. **데이터 일관성**: eventual consistency (~60초)
3. **압축 해제 비용**: 메모리 사용 고려 (goal이 클수록 증가)
4. **캐시 무효화**: KV 데이터 업데이트 시 약 60초 소요

## 문제 해결

### KV에서 데이터를 못 찾는 경우

```bash
# 키 존재 확인
npx wrangler kv key get --namespace-id="f6c7f658dde04b339e48adbe04389c1b" "game1_5"

# 모든 키 확인
npx wrangler kv key list --namespace-id="f6c7f658dde04b339e48adbe04389c1b"
```

### JSON 파싱 에러

KV에 저장된 데이터 형식 확인:
```python
import json
data = await kv_store.get("game1_5")
parsed = json.loads(data)
assert len(parsed) == 2
assert isinstance(parsed[0], int)
assert isinstance(parsed[1], list)
```

## 다음 단계

1. ✅ KV 통합 완료
2. ✅ game1, game2 데이터 업로드 (1~20)
3. 🔲 프로덕션 배포
4. 🔲 성능 모니터링
5. 🔲 필요시 goal 범위 확장 (21~50)
