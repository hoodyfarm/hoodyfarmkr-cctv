const { execSync } = require('child_process');
const readline = require('readline');
const fs = require('fs');
const path = require('path');

const projectRoot = path.join(__dirname, '..');
console.log('🌇 [nr end] hoodyfarmkr-cctv 업무 종료 루틴을 실행합니다...\n');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

const ask = (query) => new Promise(resolve => rl.question(query, resolve));

// 헬퍼 함수: 개발 히스토리를 HISTORY.md 파일에 자동 적재
const appendHistory = (message, prefix = '') => {
  try {
    const historyPath = path.join(projectRoot, 'md', 'docs', 'HISTORY.md');
    const kstDateFull = new Date(Date.now() + 9 * 3600000).toISOString().replace('T', ' ').slice(0, 19);
    const entryPrefix = prefix ? `[${prefix}] ` : '';
    const historyEntry = `- **[${kstDateFull}]** ${entryPrefix}${message}\n`;

    if (!fs.existsSync(historyPath)) {
      const header = '# 📖 개발 장기 히스토리 (HISTORY)\n\n> 이 파일은 `nr end` 스크립트를 통해 자동 기록되며, 전체 작업 발자취를 보존하는 용도로 활용됩니다.\n\n';
      fs.writeFileSync(historyPath, header, 'utf8');
    }
    fs.appendFileSync(historyPath, historyEntry, 'utf8');
    console.log(`\n📝 [md/docs/HISTORY.md]에 장기 작업 이력이 기록되었습니다.`);
  } catch(e) {
    console.error('\n❌ 히스토리 기록 중 오류가 발생했습니다:', e.message);
  }
};

// 헬퍼 함수: 단기 작업 메모를 MEMO.md에 자동 적재
const appendMemo = (message) => {
  try {
    const memoPath = path.join(projectRoot, 'md', 'MEMO.md');
    const kstDateFull = new Date(Date.now() + 9 * 3600000).toISOString().replace('T', ' ').slice(0, 16);
    const memoEntry = `\n* **[WIP: ${kstDateFull}]** ${message}`;
    
    if (fs.existsSync(memoPath)) {
      let content = fs.readFileSync(memoPath, 'utf8');
      const targetHeader = '## Part 1. 핵심 메모 (Core Memos)';
      
      if (content.includes(targetHeader)) {
        content = content.replace(targetHeader, targetHeader + memoEntry);
        fs.writeFileSync(memoPath, content, 'utf8');
        console.log(`\n📝 [md/MEMO.md] 단기 작업(WIP) 영역에 메모가 업데이트 되었습니다.`);
        return;
      }
    }
    fs.appendFileSync(memoPath, memoEntry + '\n', 'utf8');
    console.log(`\n📝 [md/MEMO.md]에 단기 작업 메모가 추가되었습니다.`);
  } catch(e) {
    console.error('\n❌ MEMO.md 기록 중 오류가 발생했습니다:', e.message);
  }
};

(async () => {
  try {
    // 1. Git 상태 확인 및 저장 (프로젝트 최상위 디렉터리 기준 실행)
    console.log('📊 현재 작업 상태 요약:');
    const status = execSync('git status --short', { encoding: 'utf8', cwd: projectRoot });
    
    if (status.trim()) {
      console.log(status);
      console.log('\n⚠️ [경고] 커밋되지 않은 수정사항이 있습니다!');
      
      let commitMsg = await ask('👉 지금 바로 저장(Commit)하시겠습니까?\n커밋 메시지를 입력하세요 (엔터 입력 시 자동 생성): ');
      
      if (!commitMsg.trim()) {
        const kstDate = new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 16).replace('T', ' ');
        commitMsg = `Auto Save: ${kstDate}`;
      }

      console.log(`\n💾 변경사항을 저장합니다... ["${commitMsg}"]`);
      try {
        execSync('git add .', { stdio: 'ignore', cwd: projectRoot });
        execSync(`git commit -m "${commitMsg}"`, { stdio: 'inherit', cwd: projectRoot });
        console.log('✅ 저장 완료!');
        
        appendHistory(commitMsg, 'Commit');
        
        console.log('\n📝 내일 할 일을 기록해 주세요.');
        const memoAnswer = await new Promise(resolve => {
          rl.question('> ', resolve);
          rl.write(`- 진행상황: ${commitMsg} -> 내일 할 일: `);
        });
        if (memoAnswer.trim()) {
          appendMemo(memoAnswer.trim());
        }
      } catch (e) {
        console.error('\n❌ 저장 중 오류가 발생했습니다.');
      }
    } else {
      console.log('✨ 작업 트리가 깨끗합니다 (수정사항 없음).');
      
      const contextAnswer = await ask('\n📝 진행 중인 단기 작업 메모(MEMO.md)를 갱신하시겠습니까?\n(엔터 입력 시 건너뜁니다): ');
      if (contextAnswer.trim()) {
        appendMemo(contextAnswer.trim());
      }
    }

    // 2. Push 여부 확인
    const pushAnswer = await ask('\n☁️ 현재 브랜치의 코드를 원격 저장소로 푸시(Push)하시겠습니까? (y/N): ');
    if (pushAnswer.toLowerCase() === 'y') {
      console.log('\n🚀 푸시를 진행합니다...');
      try {
        execSync('git push', { stdio: 'inherit', cwd: projectRoot });
      } catch (e) {
        console.error('\n❌ 푸시 중 오류가 발생했습니다.');
      }
    } else {
      console.log('\n⏩ 푸시를 건너뜁니다.');
    }
    
    // 3. 윈도우 전원 관리
    if (process.platform === 'win32') {
      const powerAnswer = await ask('\n💻 예약된 종료를 취소하고 지금 바로 PC를 끄시겠습니까?\n(y: 즉시 종료 / c: 예약만 취소 / N: 그대로 두기): ');
      const ans = powerAnswer.toLowerCase().trim();
      if (ans === 'y') {
        try { execSync('shutdown -a', { stdio: 'ignore' }); } catch(e) {}
        console.log('\n🔌 PC를 즉시 종료합니다. 안녕히 가세요!');
        try { execSync('shutdown -s -t 0', { stdio: 'ignore' }); } catch(e) {}
      } else if (ans === 'c') {
        try { execSync('shutdown -a', { stdio: 'ignore' }); } catch(e) {}
        console.log('\n🛑 예약된 자동 종료가 취소되었습니다. PC를 끄지 않습니다.');
      }
    }

    console.log('\n🎉 오늘도 고생하셨습니다, 사장님! 편안한 휴식 되세요. 🌙\n');
  } catch (error) {
    console.error('\n❌ [오류] 업무 종료 루틴 실행 중 문제가 발생했습니다:', error.message);
  } finally {
    rl.close();
  }
})();
