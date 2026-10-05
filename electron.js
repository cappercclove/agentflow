const { app, BrowserWindow, Menu, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

let mainWindow;
let backendProcess;

function findPython() {
  const candidates = ['python', 'python3', 'py'];
  const commonPaths = [
    'C:\\Python311\\python.exe',
    'C:\\Python310\\python.exe',
    'C:\\Python39\\python.exe',
    'C:\\Users\\' + require('os').userInfo().username + '\\AppData\\Local\\Programs\\Python\\Python311\\python.exe',
    'C:\\Users\\' + require('os').userInfo().username + '\\AppData\\Local\\Programs\\Python\\Python310\\python.exe',
  ];

  for (const cmd of candidates) {
    try {
      const test = spawn(cmd, ['--version'], { stdio: 'pipe' });
      let output = '';
      test.stdout.on('data', (d) => (output += d));
      test.stderr.on('data', (d) => (output += d));
      if (test.pid) return cmd;
    } catch (e) {}
  }

  for (const p of commonPaths) {
    if (fs.existsSync(p)) return p;
  }

  return null;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 600,
    title: 'AgentFlow - AI 工作流平台',
    icon: path.join(__dirname, 'frontend', 'icons', 'icon-512.png'),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  const menu = Menu.buildFromTemplate([
    {
      label: 'AgentFlow',
      submenu: [
        { label: '关于 AgentFlow', role: 'about' },
        { type: 'separator' },
        { label: '退出', role: 'quit' },
      ],
    },
    {
      label: '编辑',
      submenu: [
        { label: '撤销', role: 'undo' },
        { label: '恢复', role: 'redo' },
        { type: 'separator' },
        { label: '剪切', role: 'cut' },
        { label: '复制', role: 'copy' },
        { label: '粘贴', role: 'paste' },
      ],
    },
    {
      label: '视图',
      submenu: [
        { label: '重新加载', role: 'reload' },
        { label: '强制重新加载', role: 'forceReload' },
        { label: '开发者工具', role: 'toggleDevTools' },
        { type: 'separator' },
        { label: '实际大小', role: 'resetZoom' },
        { label: '放大', role: 'zoomIn' },
        { label: '缩小', role: 'zoomOut' },
        { type: 'separator' },
        { label: '全屏', role: 'togglefullscreen' },
      ],
    },
  ]);
  Menu.setApplicationMenu(menu);

  mainWindow.loadURL('http://localhost:8001');

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function startBackend() {
  const pythonCmd = findPython();

  if (!pythonCmd) {
    dialog.showErrorBox(
      'Python 未找到',
      'AgentFlow 需要 Python 3.11+ 才能运行。\n\n请安装 Python 并确保将其添加到系统 PATH，或从 python.org 下载安装。'
    );
    app.quit();
    return;
  }

  const backendPath = path.join(__dirname, 'backend');

  backendProcess = spawn(pythonCmd, ['-m', 'uvicorn', 'main:app', '--host', '0.0.0.0', '--port', '8001'], {
    cwd: backendPath,
    stdio: 'pipe',
  });

  backendProcess.stdout.on('data', (data) => {
    console.log(`[Backend] ${data}`);
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`[Backend Error] ${data}`);
  });

  backendProcess.on('error', (err) => {
    console.error('[Backend] Failed to start:', err.message);
    dialog.showErrorBox('后端启动失败', `无法启动 Python 后端：${err.message}\n\n请确保已安装 Python 3.11+ 和 uvicorn。`);
  });

  backendProcess.on('close', (code) => {
    console.log(`[Backend] Process exited with code ${code}`);
  });
}

app.whenReady().then(() => {
  startBackend();

  setTimeout(() => {
    createWindow();
  }, 2000);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (backendProcess) {
    backendProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (backendProcess) {
    backendProcess.kill();
  }
});
