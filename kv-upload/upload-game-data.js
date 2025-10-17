/**
 * JSON 파일을 파싱하여 각 키에 대응하는 값을 Cloudflare Workers KV에 업로드
 *
 * 사용법: node upload-game-data.js
 *
 * JSON 구조:
 * [
 *   [1, 2, 3, ..., 20],  // 첫 번째 배열: 키들
 *   [값들...],           // 두 번째 배열: 키 1에 대응
 *   [값들...],           // 세 번째 배열: 키 2에 대응
 *   ...
 * ]
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// 설정
const JSON_FILE_PATH = path.join(__dirname, '..', 'src', 'logic', 'precomputed_game2_v2.json');
const NAMESPACE_ID = 'f6c7f658dde04b339e48adbe04389c1b'; // auspiland-test-store의 네임스페이스 ID
const KEY_PREFIX = 'game2_'; // KV 키 접두사 (예: game2_1, game2_2, ...)

console.log('=== Cloudflare Workers KV 업로드 스크립트 ===\n');

try {
  // JSON 파일 읽기
  console.log('1. JSON 파일 읽는 중...');
  const rawData = fs.readFileSync(JSON_FILE_PATH, 'utf8');
  const data = JSON.parse(rawData);

  console.log(`   ✓ 파일 크기: ${(Buffer.byteLength(rawData, 'utf8') / 1024).toFixed(2)} KB`);
  console.log(`   ✓ 배열 개수: ${data.length}`);

  // 첫 번째 배열이 키들
  const keys = data[0];
  console.log(`\n2. 키 목록: [${keys.join(', ')}]`);
  console.log(`   ✓ 총 ${keys.length}개의 키`);

  // 데이터 검증
  if (data.length - 1 !== keys.length) {
    console.warn(`\n⚠️  경고: 키 개수(${keys.length})와 데이터 배열 개수(${data.length - 1})가 일치하지 않습니다.`);
  }

  console.log('\n3. KV에 업로드 시작...\n');

  let successCount = 0;
  let failCount = 0;

  // 각 키에 대응하는 데이터를 KV에 업로드
  for (let i = 0; i < keys.length; i++) {
    const key = keys[i];
    const kvKey = `${KEY_PREFIX}${key}`;
    const valueArray = data[i + 1]; // i+1 because data[0] is keys

    if (!valueArray) {
      console.log(`   ⚠️  ${kvKey}: 데이터 없음 (건너뜀)`);
      failCount++;
      continue;
    }

    try {
      // JSON 배열을 문자열로 변환
      const jsonValue = JSON.stringify(valueArray);
      const sizeKB = (Buffer.byteLength(jsonValue, 'utf8') / 1024).toFixed(2);

      // 임시 파일에 저장
      const tempFile = path.join(__dirname, `temp_${kvKey}.json`);
      fs.writeFileSync(tempFile, jsonValue);

      // wrangler 명령어로 KV에 업로드
      const command = `npx wrangler kv key put "${kvKey}" --namespace-id="${NAMESPACE_ID}" --path="${tempFile}"`;

      execSync(command, { stdio: 'pipe' });

      // 임시 파일 삭제
      fs.unlinkSync(tempFile);

      console.log(`   ✓ ${kvKey}: ${sizeKB} KB (배열 길이: ${valueArray.length})`);
      successCount++;

    } catch (error) {
      console.log(`   ✗ ${kvKey}: 업로드 실패 - ${error.message}`);
      failCount++;
    }
  }

  console.log(`\n4. 업로드 완료!`);
  console.log(`   성공: ${successCount}개`);
  console.log(`   실패: ${failCount}개`);

  if (successCount > 0) {
    console.log('\n5. 업로드된 키 확인:');
    try {
      const listCommand = `npx wrangler kv key list --namespace-id="${NAMESPACE_ID}" --prefix="${KEY_PREFIX}"`;
      const result = execSync(listCommand, { encoding: 'utf8' });
      console.log(result);
    } catch (error) {
      console.log('   (키 목록 조회 실패)');
    }
  }

  console.log('\n✅ 모든 작업이 완료되었습니다!\n');

} catch (error) {
  console.error('\n❌ 오류 발생:', error.message);
  process.exit(1);
}
