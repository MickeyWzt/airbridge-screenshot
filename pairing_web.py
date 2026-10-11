"""Small, self-contained iPad onboarding page. No analytics or remote assets."""
import html
import re


def shortcut_link(value):
    value = value.strip()
    return value if re.fullmatch(r'https://www\.icloud\.com/shortcuts/[0-9a-fA-F]{32}', value) else ''


def setup_page(config):
    address = html.escape(config.get('upload_url', ''), quote=True)
    shared = shortcut_link(config.get('shortcut_link', ''))
    if shared:
        template = f'<a class="button" href="{shared}" rel="noreferrer">添加截图快捷指令</a><p>添加后，在 Shortcuts 中点刚添加的快捷指令上的 <b>…</b>。把唯一一块 <b>URL</b> 里的 <b>SETUP_URL</b> 替换为刚复制的完整连接地址，然后点 <b>Done</b>。只需设置一次。</p>'
    else:
        template = '<p class="note">可导入模板还在准备中。当前预览版可按下方步骤创建一次；以后无需重建。</p>'
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>连接 AirBridge Screenshot</title>
<style>
:root{color-scheme:light dark;font-family:system-ui,-apple-system,sans-serif}*{box-sizing:border-box}
body{margin:0;background:#eef3f8;color:#172437}main{max-width:620px;margin:auto;padding:28px 22px 50px}
h1{font-size:28px;letter-spacing:-.7px;margin:10px 0}h2{font-size:20px;margin:0 0 14px}
p{line-height:1.6;margin:12px 0}section{background:white;border-radius:20px;padding:22px;margin:18px 0;border:1px solid #dfe7f0}
.badge{font-size:13px;color:#446680}.success{background:#e2f5eb;color:#146740;padding:14px;border-radius:12px}
.note{color:#5d697b}.button,button{display:inline-block;padding:13px 18px;border:0;border-radius:12px;background:#2465db;color:white;font:600 16px system-ui;text-decoration:none}
textarea{width:100%;padding:14px;border:1px solid #ccd8e5;border-radius:10px;resize:none;background:#f7f9fc;color:#172437;font:14px ui-monospace,monospace;overflow-wrap:anywhere}
ol{padding-left:22px;line-height:1.75}li{padding:5px 0}code{background:#edf2f8;border-radius:4px;padding:2px 4px}
details{margin-top:18px}summary{cursor:pointer;color:#2465db}a{color:#2465db}
@media(prefers-color-scheme:dark){body{background:#131b28;color:#edf3fc}section{background:#1d2839;border-color:#334157}.note,.badge{color:#b3c0d0}textarea,code{background:#152033;color:#edf3fc;border-color:#3b4e69}.success{background:#193d32;color:#a6ebcb}}
</style><main><span class="badge">AirBridge Screenshot · 首次连接</span>
<h1>把截图发到这台电脑</h1>
<p class="success" id="connection">已打开电脑上的配对页面。正在检查接收状态…</p>
<section><h2>1 · 添加快捷指令</h2>
<p>先复制这台电脑的连接地址（仅供你自己的设备使用）：</p>
<textarea id="address" rows="4" readonly>''' + address + '''</textarea>
<p><button id="copy">复制连接地址</button> <span id="copied" class="note"></span></p>''' + template + '''
<details''' + ('' if shared else ' open') + '''><summary>手动创建快捷指令</summary>
<ol><li>打开 <b>Shortcuts</b>，点 <b>＋</b>，命名为「截屏到电脑」。</li>
<li>添加 <b>Hide Control Center</b>，然后 <b>Wait</b>，设为 <b>1 second</b>。</li>
<li>添加 <b>Take Screenshot</b>，然后 <b>Convert Image</b>，选择 <b>PNG</b>。</li>
<li>添加 <b>URL</b>，粘贴上面的完整连接地址。</li>
<li>添加 <b>Get Contents of URL</b>，展开设置：<b>Method = POST</b>，<b>Request Body = File</b>，<b>File = Converted Image</b>。</li></ol>
<p class="note">连接地址已经完整，不用再拼接 /clip 或其他变量。</p></details></section>
<section><h2>2 · 试发一张截图</h2><p>回到要截的画面，运行刚设置好的快捷指令。第一次运行时允许它访问本地网络。</p>
<p>电脑右下角出现图片，就是连接成功。之后可以 Ctrl+V 粘贴，也可以直接拖走预览。</p></section>
<section><h2>3 · 放进控制中心</h2><p>打开 Control Center → 长按空白 → Add a Control → Shortcuts / Run Shortcut → 选择刚设置好的快捷指令。以后点这个按钮就可以。</p></section>
<p class="note">电脑和 iPad 需要连到允许设备互访的同一局域网。使用设备名称时通常不必随 IP 修改地址；若校园网不支持 .local 名称，请在电脑窗口切到「当前 IP」再扫码。</p>
<p class="note">通过快捷指令按钮截屏并发送；系统按键截屏不会触发发送。图片在局域网直传，不需要 iCloud 会员或云端账号。</p>
<script>
document.getElementById('copy').onclick=async()=>{const field=document.getElementById('address');field.focus();field.select();field.setSelectionRange(0,field.value.length);let ok=false;try{if(navigator.clipboard&&window.isSecureContext){await navigator.clipboard.writeText(field.value);ok=true}else{ok=document.execCommand('copy')}}catch{}document.getElementById('copied').textContent=ok?'已复制':'请长按地址，选择全部 → 复制'};
fetch('/health',{cache:'no-store'}).then(r=>r.json()).then(data=>{document.getElementById('connection').textContent=data.ready?'✓ iPad 已连接到这台电脑，可以开始设置。':'电脑接收已暂停，请在电脑窗口点击「恢复接收」。'}).catch(()=>{document.getElementById('connection').textContent='连接已中断，请确认电脑上的接收器仍在运行，然后刷新。'});
</script></main></html>'''
