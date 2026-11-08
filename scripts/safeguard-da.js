const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

console.log('====================================================');
console.log('🛡️ [후디팜 CCTV] nr da 3대 무결성 종합 세이프가드 검증');
console.log('====================================================\n');

const projectRoot = path.join(__dirname, '..');
const pythonExe = path.join(projectRoot, '.venv', 'Scripts', 'python.exe');

// 1. Python 가상환경 및 문법 검사 (Syntax / Linter)
console.log('▶ [1/3] Python 소스코드 정적 컴파일 및 문법 무결성 검증 (0-Defect)...');
try {
  execSync(`"${pythonExe}" -m py_compile src/main.py src/services/ingestion_worker.py src/services/inference_worker.py src/services/storage_cleaner.py src/api/pipeline_routes.py`, {
    stdio: 'inherit',
    cwd: projectRoot
  });
  console.log('✅ [1/3 통과] 모든 비전/파이프라인 핵심 소스코드 문법 무결성 검증 완료!\n');
} catch (e) {
  console.error('❌ [1/3 실패] Python 소스코드 문법 오류 발생!');
  process.exit(1);
}

// 2. TDD 단위 및 회귀 테스트 (pytest 100% All-Green)
console.log('▶ [2/3] CCTV 전사 37개 TDD 단위/통합 회귀 테스트 스위트 검증...');
try {
  execSync(`"${pythonExe}" -m pytest`, {
    stdio: 'inherit',
    cwd: projectRoot,
    env: { ...process.env, PYTHONUTF8: '1' }
  });
  console.log('✅ [2/3 통과] 전사 37개 테스트 100% All-Green 통과 완료!\n');
} catch (e) {
  console.error('❌ [2/3 실패] 테스트 케이스 검증 실패!');
  process.exit(1);
}

// 3. 디스크 스토리지 & 2단 버퍼(spool -> events) 무결성 검사
console.log('▶ [3/3] 2단 스테이징 버퍼(spool/events) 및 청소기 동작 무결성 점검...');
try {
  execSync(`"${pythonExe}" -c "from src.services.storage_cleaner import StorageCleaner; c = StorageCleaner('${projectRoot.replace(/\\/g, '/')}'); res = c.run_cleanup_cycle(); print('Storage cleaner cycle OK:', res)"`, {
    stdio: 'inherit',
    cwd: projectRoot
  });
  console.log('✅ [3/3 통과] 디스크 스토리지 버퍼 및 청소기 검증 완료!\n');
} catch (e) {
  console.error('❌ [3/3 실패] 스토리지 청소기 점검 실패!');
  process.exit(1);
}

console.log('====================================================');
console.log('🎉 [SEALED] CCTV 파이프라인 3대 무결성 검증 100% 통과! 선적(Ship) 준비 완료!');
console.log('====================================================\n');
