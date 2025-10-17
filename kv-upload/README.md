# Cloudflare Workers KV 업로드

JSON 파일을 파싱하여 Cloudflare Workers KV에 업로드하는 도구입니다.

## 파일 구조

```
kv-upload/
├── upload-game-data.js    # KV 업로드 스크립트
├── worker-game-data.ts    # Worker API 코드 (선택사항)
└── README.md              # 이 파일
```

## JSON 파일 구조

```json
[
  [1, 2, 3, ..., 20],  // 첫 번째 배열: 키들
  [데이터1...],        // 두 번째 배열: 키 1에 대응하는 값
  [데이터2...],        // 세 번째 배열: 키 2에 대응하는 값
  ...
]
```

## 빠른 시작

### 1. 스크립트 실행

```bash
cd C:\Users\T3Q\jeonghan\my_github\webpage\kv-upload
node upload-game-data.js
```

스크립트는 자동으로:
- JSON 파일을 읽어서 첫 번째 배열을 키로 추출
- 각 키에 대응하는 데이터를 KV에 업로드
- 키 형식: `game1_1`, `game1_2`, ..., `game1_20` (또는 `game2_*`)

### 2. 설정 변경 (필요시)

`upload-game-data.js` 파일의 상단 설정을 수정:

```javascript
// 설정
const JSON_FILE_PATH = path.join(__dirname, '..', 'src', 'logic', 'precomputed_game1_v2.json');
const NAMESPACE_ID = 'f6c7f658dde04b339e48adbe04389c1b'; // auspiland-test-store
const KEY_PREFIX = 'game1_'; // KV 키 접두사
```

## 데이터 확인

### 업로드된 키 목록 보기

```bash
npx wrangler kv key list --namespace-id="f6c7f658dde04b339e48adbe04389c1b" --prefix="game1_"
```

### 특정 키의 데이터 조회

```bash
npx wrangler kv key get --namespace-id="f6c7f658dde04b339e48adbe04389c1b" "game1_5"
```

### 키 삭제

```bash
npx wrangler kv key delete --namespace-id="f6c7f658dde04b339e48adbe04389c1b" "game1_5"
```

## Worker API (선택사항)

`worker-game-data.ts`를 사용하여 HTTP API로 데이터를 제공할 수 있습니다.

### 배포

```bash
wrangler deploy kv-upload/worker-game-data.ts
```

### API 엔드포인트

- `GET /game1/5` - 키 5의 데이터 조회
- `GET /game1/list` - 모든 키 목록 조회
- `GET /game1/all` - 전체 데이터를 원본 JSON 형식으로 조회

### 사용 예시

```javascript
// 특정 키 데이터 가져오기
const response = await fetch('https://your-worker.workers.dev/game1/5');
const { data } = await response.json();

// 모든 키 목록
const response = await fetch('https://your-worker.workers.dev/game1/list');
const { keys } = await response.json(); // [1, 2, 3, ..., 20]

// 전체 데이터
const response = await fetch('https://your-worker.workers.dev/game1/all');
const fullData = await response.json(); // [[keys...], [data1...], ...]
```

## KV 정보

- **네임스페이스**: auspiland-test-store
- **네임스페이스 ID**: f6c7f658dde04b339e48adbe04389c1b
- **바인딩 이름**: GLOBAL (Worker에서 사용)

## 문제 해결

### "wrangler: command not found"

```bash
npx wrangler login
```

### "No KV Namespaces configured"

네임스페이스 ID가 올바른지 확인하거나 `wrangler.toml`에 바인딩 추가:

```toml
[[kv_namespaces]]
binding = "GLOBAL"
id = "f6c7f658dde04b339e48adbe04389c1b"
```

### 네임스페이스 ID 찾기

```bash
npx wrangler kv namespace list
```

## 참고

- KV 값 최대 크기: 25 MB
- 현재 각 키당 데이터 크기: ~수 KB
- KV는 eventual consistency (전파 시간 ~60초)
