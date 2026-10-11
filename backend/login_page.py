"""The page a first-time visitor sees when the site is password-gated.

Self-contained on purpose: the app's own bundle is behind the same gate, so this
cannot depend on any of it.
"""

LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AgentFlow · 访问口令</title>
<style>
  * { box-sizing: border-box; }
  body {
    margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
    font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'SF Pro Display', 'Helvetica Neue', 'PingFang SC', sans-serif;
    color: #1a1a1a; background: #fafafa;
    background-image: radial-gradient(900px 480px at 50% -12%, rgba(99,102,241,.13), transparent 62%),
                      radial-gradient(600px 380px at 88% 108%, rgba(34,197,94,.10), transparent 60%);
  }
  .card {
    width: 360px; padding: 34px 30px 28px; background: #fff; border: 1px solid rgba(0,0,0,.07);
    border-radius: 16px; box-shadow: 0 18px 44px -22px rgba(24,24,48,.28);
    animation: rise .45s cubic-bezier(.22,1,.36,1) both;
  }
  @keyframes rise { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
  .mark {
    width: 42px; height: 42px; border-radius: 11px; display: grid; place-items: center; margin-bottom: 16px;
    background: linear-gradient(140deg, #6366f1, #8b5cf6); box-shadow: 0 8px 18px -8px rgba(99,102,241,.8);
  }
  h1 { margin: 0 0 5px; font-size: 20px; letter-spacing: -.4px; }
  .sub { margin: 0 0 22px; font-size: 13px; color: #737373; }
  label { display: block; font-size: 12px; color: #737373; margin-bottom: 7px; letter-spacing: .2px; }
  input {
    width: 100%; padding: 11px 13px; font-size: 15px; font-family: inherit; color: inherit;
    background: #fafafa; border: 1px solid rgba(0,0,0,.10); border-radius: 10px; outline: none;
    transition: border-color .16s, box-shadow .16s, background .16s;
  }
  input:focus { background: #fff; border-color: #6366f1; box-shadow: 0 0 0 3px rgba(99,102,241,.15); }
  input.shake { border-color: #ef4444; animation: shake .3s; }
  @keyframes shake { 25% { transform: translateX(-5px); } 75% { transform: translateX(5px); } }
  button {
    width: 100%; margin-top: 16px; padding: 11px; font-size: 14px; font-weight: 600; font-family: inherit;
    color: #fff; background: #6366f1; border: 0; border-radius: 10px; cursor: pointer;
    transition: background .16s, transform .06s;
  }
  button:hover { background: #4f46e5; }
  button:active { transform: translateY(1px); }
  button[disabled] { opacity: .6; cursor: default; }
  .msg { min-height: 18px; margin: 10px 0 0; font-size: 12.5px; color: #ef4444; }
  .foot { margin-top: 18px; padding-top: 14px; border-top: 1px solid rgba(0,0,0,.06); font-size: 11.5px; color: #a3a3a3; }
  code { font-family: 'SF Mono', 'Fira Code', ui-monospace, Menlo, monospace; font-size: 11px; }
</style>
</head>
<body>
  <form class="card" id="f" autocomplete="off">
    <div class="mark">
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="5" cy="6" r="2.2"/><circle cx="19" cy="6" r="2.2"/><circle cx="12" cy="18" r="2.2"/>
        <path d="M7 7.2 10.6 16M17 7.2 13.4 16M7.2 6h9.6"/>
      </svg>
    </div>
    <h1>AgentFlow</h1>
    <p class="sub">可视化 AI 工作流编排平台 · 需要访问口令</p>
    <label for="code">访问口令</label>
    <input id="code" type="password" placeholder="请输入口令" autofocus>
    <button id="go" type="submit">进入</button>
    <p class="msg" id="msg"></p>
    <div class="foot">演示环境，模型调用有额度与频率上限。口令由 <code>AGENTFLOW_ACCESS_CODE</code> 配置。</div>
  </form>
<script>
  const form = document.getElementById('f');
  const box = document.getElementById('code');
  const btn = document.getElementById('go');
  const msg = document.getElementById('msg');

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    btn.disabled = true;
    msg.textContent = '';
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: box.value }),
      });
      if (res.ok) { location.href = '/'; return; }
      const data = await res.json().catch(() => ({}));
      msg.textContent = (data.detail) || '口令不正确';
      box.classList.add('shake');
      setTimeout(() => box.classList.remove('shake'), 320);
    } catch (e) {
      msg.textContent = '无法连接服务端，请重试';
    } finally {
      btn.disabled = false;
      box.focus();
    }
  });
</script>
</body>
</html>"""
