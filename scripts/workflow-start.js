const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const projectRoot = path.join(__dirname, '..');
console.log('🌅 [nr start] hoodyfarmkr-cctv AI 업무 시작 루틴을 실행합니다...\n');

try {
  // 1. 현재 브랜치 확인 및 main 브랜치 방어
  const currentBranch = execSync('git branch --show-current', { encoding: 'utf8', cwd: projectRoot }).trim();
  console.log(`📌 현재 브랜치: [${currentBranch}]`);

  if (currentBranch === 'main') {
    console.log('⚠️ [경고] main 브랜치에서는 직접 작업할 수 없습니다 (Golden Standard 정책).');
    console.log('🔄 안전을 위해 dev 브랜치로 전환을 시도합니다...');
    try {
      execSync('git checkout dev', { stdio: 'inherit', cwd: projectRoot });
    } catch (e) {
      console.log('✨ dev 브랜치가 없어 새 브랜치를 생성합니다...');
      execSync('git checkout -b dev', { stdio: 'inherit', cwd: projectRoot });
    }
  }

  // 2. 원격 저장소 동기화
  console.log('\n⬇️ 원격 저장소(origin)에서 최신 코드를 가져옵니다...');
  try {
    execSync('git pull', { stdio: 'inherit', cwd: projectRoot });
  } catch (pullError) {
    console.log('⚠️ [안내] 원격 브랜치 연결 전이거나 새 브랜치입니다. 무시하고 계속 진행합니다...');
  }
  
  // 3. 자가진단 환경 점검 (check_env.py)
  console.log('\n🩺 [1단계 자가 진단] CCTV 시스템 환경 변수 점검 중...');
  try {
    execSync('node scripts/run-python.js src/tools/check_env.py', { stdio: 'inherit', cwd: projectRoot });
  } catch (envError) {
    console.log('⚠️ [경고] 환경 변수 자가 진단 중 일부 경고가 발견되었습니다. .env 설정을 확인하세요.');
  }

  // 4. 단기 메모 (MEMO.md) 확인
  console.log('\n📖 [최근 단기 작업 맥락 - MEMO.md]');
  try {
    const memoPath = path.join(projectRoot, 'md', 'MEMO.md');
    if (fs.existsSync(memoPath)) {
      const content = fs.readFileSync(memoPath, 'utf8');
      const lines = content.split('\n');
      let printed = 0;
      for (const line of lines) {
        if (line.includes('## Part 2')) break;
        if (line.trim() !== '') {
          console.log(`  ${line}`);
          printed++;
        }
        if (printed > 15) break;
      }
    }
  } catch (err) {
    console.log('  MEMO.md를 읽어오는 중 문제가 발생했습니다.');
  }

  // 5. 틱톡 전략 및 리팩토링 가이드 확인 안내
  console.log('\n⏱️ [Tick-Tock 단권화 전략 & AI 리팩토링 가이드 Ready]');
  console.log('  - Tick-Tock 전략: md/TICKTOCK.md');
  console.log('  - AI 리팩토링 프롬프트: md/REFACTORING_PROMPT.md');
  console.log('  - AI 자가진단 CLI: python src/tools/test_code_refiner.py');

  // 6. 에디터로 주요 관리 문서 자동 열기
  console.log('\n📖 작업 시작을 위해 주요 관리 파일들을 에디터로 연다...');
  try {
    const memoPath = path.join(projectRoot, 'md', 'MEMO.md');
    const ticktockPath = path.join(projectRoot, 'md', 'TICKTOCK.md');
    const promptPath = path.join(projectRoot, 'md', 'REFACTORING_PROMPT.md');
    
    const editors = ['antigravity-ide', 'code', 'code-insiders', 'cursor'];
    for (const editor of editors) {
      try {
        execSync(`${editor} --version`, { stdio: 'ignore', shell: true });
        execSync(`${editor} "${memoPath}" "${ticktockPath}" "${promptPath}"`, { stdio: 'ignore', shell: true });
        break;
      } catch (e) {}
    }
  } catch (e) {}

  console.log('\n🚀 모든 준비가 완료되었습니다. 오늘도 화이팅입니다, 사장님!');
} catch (error) {
  console.error('\n❌ [오류] 업무 시작 루틴 실행 중 문제가 발생했습니다.');
  console.error(error.message);
  process.exit(1);
}
