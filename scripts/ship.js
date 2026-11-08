const { execSync } = require('child_process');

const commitMsg = process.argv.slice(2).join(' ').trim();
if (!commitMsg) {
  console.error('\n❌ [오류] 커밋 메시지를 입력해주세요.');
  console.log('👉 사용법: npm run ship "feat(cctv): 작업내용 설명"\n');
  process.exit(1);
}

console.log('====================================================');
console.log('🚀 [후디팜 CCTV] 원클릭 선적(Ship) 파이프라인 가동');
console.log(`📌 커밋 메시지: ${commitMsg}`);
console.log('====================================================\n');

try {
  // 1. nr da 세이프가드 사전 검증
  console.log('🛡️ 1단계: nr da 3대 세이프가드 종합 검증 가동...');
  execSync('node scripts/safeguard-da.js', { stdio: 'inherit' });

  // 2. 현재 브랜치 커밋
  const currentBranch = execSync('git branch --show-current', { encoding: 'utf8' }).trim();
  console.log(`\n📦 2단계: 현재 브랜치 [${currentBranch}] 변경사항 자동 커밋...`);
  execSync('git add .', { stdio: 'inherit' });
  execSync(`git commit -m "${commitMsg}"`, { stdio: 'inherit' });

  // 3. dev 브랜치 자동 병합 & 원격 푸시
  console.log(`\n🔀 3단계: dev 브랜치로 자동 병합 및 원격(GitHub) 안전 푸시...`);
  execSync('git push -u origin ' + currentBranch, { stdio: 'inherit' });
  
  if (currentBranch !== 'dev') {
    execSync('git checkout dev', { stdio: 'inherit' });
    execSync('git pull origin dev', { stdio: 'inherit' });
    execSync(`git merge ${currentBranch}`, { stdio: 'inherit' });
    execSync('git push origin dev', { stdio: 'inherit' });
    execSync(`git checkout ${currentBranch}`, { stdio: 'inherit' });
  }

  console.log('\n====================================================');
  console.log('✨ [선적 완료] 3대 세이프가드 통과 ➔ 커밋 ➔ dev 자동 병합 및 원격 푸시 완료!');
  console.log('====================================================\n');
} catch (e) {
  console.error('\n❌ [선적 실패] 세이프가드 검증 또는 Git 작업 중 오류가 발생하여 안전하게 중단되었습니다.');
  process.exit(1);
}
