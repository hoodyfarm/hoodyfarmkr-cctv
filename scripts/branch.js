const { execSync } = require('child_process');
const path = require('path');

const projectRoot = path.join(__dirname, '..');
const args = process.argv.slice(2).filter(arg => arg !== '--');
const branchName = args[0];

if (!branchName) {
  console.error('❌ [오류] 생성/전환할 브랜치명을 입력해주세요.');
  console.error('👉 사용 예시: nr branch feat/env  또는  npm run branch feat/env');
  process.exit(1);
}

console.log(`🌿 브랜치 생성 및 전환 시도: [${branchName}]`);

try {
  // 브랜치 존재 여부 확인
  const branches = execSync('git branch --list', { encoding: 'utf8', cwd: projectRoot });
  const exists = branches.split('\n').map(b => b.trim().replace(/^\*\s*/, '')).includes(branchName);

  if (exists) {
    console.log(`🔄 기존 브랜치 [${branchName}](으)로 전환합니다...`);
    execSync(`git checkout ${branchName}`, { stdio: 'inherit', cwd: projectRoot });
  } else {
    console.log(`✨ 새 브랜치 [${branchName}](을)를 생성하고 전환합니다...`);
    execSync(`git checkout -b ${branchName}`, { stdio: 'inherit', cwd: projectRoot });
  }
  console.log(`✅ [성공] 브랜치 준비 완료: [${branchName}]`);
} catch (error) {
  console.error(`❌ [오류] 브랜치 작업 중 문제가 발생했습니다: ${error.message}`);
  process.exit(1);
}
