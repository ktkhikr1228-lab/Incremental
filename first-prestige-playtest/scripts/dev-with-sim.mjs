import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const projectRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const forwardedArgs = process.argv.slice(2);
const bundledPython = process.env.USERPROFILE
  ? join(process.env.USERPROFILE, '.cache', 'codex-runtimes', 'codex-primary-runtime', 'dependencies', 'python', 'python.exe')
  : '';
const pythonCommand = process.env.CODEX_PYTHON || (bundledPython && existsSync(bundledPython) ? bundledPython : process.platform === 'win32' ? 'python' : 'python3');
const pythonArgs = ['sim_server.py'];

const simulator = spawn(pythonCommand, pythonArgs, {
  cwd: projectRoot,
  stdio: 'inherit',
  windowsHide: true,
});

const web = spawn(process.execPath, [join(projectRoot, 'node_modules', 'vinext', 'dist', 'cli.js'), 'dev', ...forwardedArgs], {
  cwd: projectRoot,
  stdio: 'inherit',
  windowsHide: true,
});

let shuttingDown = false;
function shutdown(code = 0) {
  if (shuttingDown) return;
  shuttingDown = true;
  simulator.kill();
  web.kill();
  process.exitCode = code;
}

simulator.on('exit', (code) => {
  if (!shuttingDown && code !== 0) shutdown(code ?? 1);
});
web.on('exit', (code) => shutdown(code ?? 0));
process.on('SIGINT', () => shutdown(0));
process.on('SIGTERM', () => shutdown(0));
