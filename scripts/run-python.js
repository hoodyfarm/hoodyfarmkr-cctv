const { execSync } = require('child_process');
const path = require('path');
const fs = require('fs');

const projectRoot = path.join(__dirname, '..');

function isWorkingPython(cmd) {
  try {
    const output = execSync(`"${cmd}" -c "import sys; print(sys.version)"`, {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
      timeout: 3000
    });
    return output && output.includes('3.');
  } catch (e) {
    return false;
  }
}

function findPythonExecutable() {
  const venvPython = path.join(projectRoot, '.venv', 'Scripts', 'python.exe');
  
  // 1. Check local virtual environment first
  if (fs.existsSync(venvPython) && isWorkingPython(venvPython)) {
    return `"${venvPython}"`;
  }

  // 2. Candidate commands
  const candidates = ['python', 'python3', 'py'];
  for (const cmd of candidates) {
    if (isWorkingPython(cmd)) {
      return `"${cmd}"`;
    }
  }

  // 3. Search common Windows installation paths
  const userProfile = process.env.USERPROFILE || 'C:\\Users\\USER';
  const windowsPaths = [
    path.join(userProfile, 'AppData', 'Local', 'Programs', 'Python', 'Python311', 'python.exe'),
    path.join(userProfile, 'AppData', 'Local', 'Programs', 'Python', 'Python312', 'python.exe'),
    path.join(userProfile, 'AppData', 'Local', 'Programs', 'Python', 'Python310', 'python.exe'),
    'C:\\Python311\\python.exe',
    'C:\\Python312\\python.exe',
    'C:\\Python310\\python.exe'
  ];

  for (const winPath of windowsPaths) {
    if (fs.existsSync(winPath) && isWorkingPython(winPath)) {
      return `"${winPath}"`;
    }
  }

  return null;
}

const args = process.argv.slice(2);
if (args.length === 0) {
  console.error('Usage: node scripts/run-python.js <script-path> [args...]');
  process.exit(1);
}

const pythonCmd = findPythonExecutable();

if (!pythonCmd) {
  console.log('\n⚠️ [안내] 시스템에서 실행 가능한 Python 3 환경을 찾을 수 없습니다.');
  console.log('📌 Python 가상환경(.venv)을 생성하거나 설치해 주세요:');
  console.log('   1) py -m venv .venv  (또는 python -m venv .venv)');
  console.log('   2) .venv\\Scripts\\pip install -r requirements.txt\n');
  process.exit(1);
}

const targetScript = args.join(' ');

try {
  execSync(`${pythonCmd} ${targetScript}`, { stdio: 'inherit', cwd: projectRoot });
} catch (e) {
  process.exit(e.status || 1);
}
