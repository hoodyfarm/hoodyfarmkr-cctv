const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const projectRoot = path.join(__dirname, '..');
console.log('🌅 [nr start] hoodyfarmkr-cctv 업무 시작 루틴을 실행합니다...\n');

try {
  // 1. 현재 브랜치 확인 (프로젝트 루트 기준)
  const currentBranch = execSync('git branch --show-current', { encoding: 'utf8', cwd: projectRoot }).trim();
  console.log(`📌 현재 브랜치: [${currentBranch}]`);

  // 2. main 브랜치 방어 로직 (안전을 위해 dev로 강제 전환)
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

  // 3. 최신 코드 동기화
  console.log('\n⬇️ 원격 저장소(origin)에서 최신 코드를 가져옵니다...');
  try {
    execSync('git pull', { stdio: 'inherit', cwd: projectRoot });
  } catch (pullError) {
    console.log('\n⚠️ [안내] 원격 브랜치(Upstream) 연결 전이거나 새 브랜치입니다. 무시하고 계속 진행합니다...');
  }
  
  // 4. 단기 메모(MEMO.md) 읽어오기
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
    } else {
      console.log('  (기록된 MEMO 파일이 없습니다.)');
    }
  } catch (err) {
    console.log('  MEMO.md를 읽어오는 중 문제가 발생했습니다.');
  }

  // 5. 장기 기억(HISTORY.md) 최근 3건 읽어오기
  console.log('\n📚 [최근 완료된 작업 - HISTORY.md]');
  try {
    const historyPath = path.join(projectRoot, 'md', 'docs', 'HISTORY.md');
    if (fs.existsSync(historyPath)) {
      const content = fs.readFileSync(historyPath, 'utf8');
      const lines = content.split('\n').filter(line => line.trim().startsWith('- **['));
      if (lines.length > 0) {
        const recentLines = lines.slice(-3);
        recentLines.forEach(line => console.log(`  ${line}`));
      } else {
        console.log('  (기록된 최근 작업이 없습니다.)');
      }
    } else {
      console.log('  (HISTORY.md 파일이 없습니다.)');
    }
  } catch (err) {
    console.log('  HISTORY.md를 읽어오는 중 문제가 발생했습니다.');
  }

  // 6. 작업 시작 시 메모/히스토리 파일 열기
  console.log('\n📖 작업 내용 확인을 위해 MEMO.md 및 HISTORY.md 파일을 열어둡니다...');
  try {
    const memoPath = path.join(projectRoot, 'md', 'MEMO.md');
    const historyPath = path.join(projectRoot, 'md', 'docs', 'HISTORY.md');
    const editors = ['antigravity-ide', 'code', 'code-insiders', 'cursor'];

    let opened = false;
    for (const editor of editors) {
      try {
        execSync(`${editor} --version`, { stdio: 'ignore', shell: true });
        execSync(`${editor} "${memoPath}" "${historyPath}"`, { stdio: 'ignore', shell: true });
        opened = true;
        break;
      } catch (editorError) {}
    }
  } catch (e) {
    console.log('  (에디터 열기 건너뜀)');
  }

  console.log('\n🚀 모든 준비가 완료되었습니다. 오늘도 화이팅입니다, 사장님!');
} catch (error) {
  console.error('\n❌ [오류] 업무 시작 루틴 실행 중 문제가 발생했습니다.');
  console.error(error.message);
  process.exit(1);
}
