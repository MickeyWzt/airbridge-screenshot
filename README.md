# AirBridge Screenshot

在 iPad 点一次快捷指令，把截图发到 Windows 剪贴板。电脑显示可拖动的图片预览。

Windows x64 预览版，在 Windows 11 上完成本地收图和图片剪贴板测试。iPad 使用系统 Shortcuts，无需安装独立 iPad 应用。

**[下载 Windows 预览包](https://github.com/MickeyWzt/airbridge-screenshot/releases/download/v0.1.0-preview/AirBridgeScreenshot-0.1.0-preview-windows-x64.zip)** ·
[查看发布说明](https://github.com/MickeyWzt/airbridge-screenshot/releases/tag/v0.1.0-preview) ·
[通用快捷指令模板](https://www.icloud.com/shortcuts/095e297826a148f2bf62aeb77707975a)

## 普通用户怎么用

1. 下载 Windows ZIP，解压整个文件夹，双击 `AirBridgeScreenshot.exe`。
2. iPad 和电脑连同一局域网，用相机扫电脑窗口里的二维码。
3. 配对页先复制完整连接地址，点「添加截图快捷指令」。添加后把唯一 URL 里的 `SETUP_URL` 换成刚复制的地址，点 Done。
4. 回到要截的画面运行快捷指令，电脑出现预览即成功。再把它加进控制中心，以后点按钮截屏发送。
5. 勾选「登录 Windows 后自动接收」，以后无需每次找程序。

无需安装 Python、输入 PowerShell 命令、注册 Cloudflare 或购买 iCloud 会员。
当前包已提供经过动作和变量连线检查的通用 iCloud 快捷指令分享链接，
无需从头搭建六个动作。首次填写一次地址，再试发截图；真实新用户的 iPad 导入流程仍待验证。
手动创建说明保留在配对页的折叠区域，方便无法打开 iCloud 分享页时使用。

截图收到后自动复制，预览可以拖入支持图片或文件拖放的应用。关闭主窗口会留在托盘；
再次双击程序也会打开已有窗口。仅在拖动时生成临时 PNG，24 小时后清理，退出期间在下次启动补清。

## 连接限制

图片在局域网用 HTTP 直传，配对地址包含每台电脑独立随机生成的秘密，请勿公开。
两台设备需要能互访；同一个 Wi-Fi 名称不一定代表校园网允许设备互访。
默认用 `.local` 设备名称，在支持 mDNS 的网络中换 IP 后无需更改快捷指令。
部分校园网/代理无法解析设备名称时，窗口可切到当前 IP，复制完整备用地址。
IP 备用方式换网后可能需要再次扫码。预览版没有承诺在任意网络零配置连接。

「允许局域网连接…」会请求 Windows 管理员授权，只开放本程序所用 TCP 端口、
专用网络和本地子网，同时允许设备名称发现所需的 UDP 5353，不开放公网。该操作不改变网络类型。普通用户也可通过系统防火墙设置授权。
自动启动仅写当前用户注册表，取消勾选即可移除；移动程序文件夹后重新设置。
本工具需要使用快捷指令截屏，不会监听 iPad 的系统截屏按键。收到图片会覆盖当前剪贴板。

## 给维护者

Windows / Python 3.12：

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-build.txt
.venv\Scripts\python app.py
.\build.ps1 -Python .venv\Scripts\python.exe
```

`dist/AirBridgeScreenshot-0.1.0-preview-windows-x64.zip` 为便携包。
PySide6/Qt 等动态库和第三方许可随包提供。打包工具不需要装在最终用户电脑上。

```powershell
python test_receiver.py
python test_network.py
python test_directory_client.py
python test_onboarding.py
python test_shortcut.py
```

前几个测试沿用原接收器的图像校验、真正的 Windows 图片剪贴板往返、拖动和清理测试。
测试会尝试恢复原剪贴板；GUI/剪贴板测试请在本地 Windows 会话运行。
开发参数 `--host 127.0.0.1 --port 18769 --data-dir <临时目录>` 可与旧接收器隔离测试。
回环地址测试不发送局域网发现广播；最终包启动后可用
`python test_portable.py --port 18769 --data-dir <同一个临时目录>` 验证跨进程剪贴板像素。
本地回环测试不代表 iPad 配对或校园网连接已经通过。

配置和拖动缓存保存在 `%USERPROFILE%\.airbridge-screenshot-community`，不在源码目录中。

## 维护快捷指令模板

请在苹果设备创建不含个人地址或配对码的通用副本。基础动作顺序为：
Hide Control Center → Wait 1 second → Take Screenshot → Convert Image to PNG →
URL → Get Contents of URL（POST / File / Converted Image）。
URL 初始值为 `SETUP_URL`，不保留云端查询 GET、地址拼接或个人密钥。
使用者添加模板后，只需将这一项替换为配对页的完整地址；当前引导不依赖导入问题。
在 iPad 实测完整导入及发送后，用 Copy iCloud Link 分享通用模板，将官方链接写入 `shortcut-link.txt`。
分享的是无个人信息的模板，图片仍在局域网传输。iCloud 分享不等于启用 iCloud 照片。
Apple 文档：https://support.apple.com/guide/shortcuts/share-shortcuts-apdf01f8c054/ios

`shortcuts/` 中提供可检查的未签名模板源文件，尚不能当成已经验证的 iPad 导入文件。
维护者可在苹果设备重建并分享，或按目录中的说明用 Mac 签名。
`python verify_shortcut.py --link <iCloud链接>` 会读取苹果公开分享记录，检查动作、变量连线和占位地址。
构建脚本在 `shortcut-link.txt` 非空时自动执行同一检查；包含个人地址或旧查询流程时中止打包。
该检查只在维护者打包时联网，接收器运行时不会查询苹果记录。

当前发布标为预览版：Windows 可执行文件未做代码签名，真实新用户的 iPad 导入流程仍待实测。
基础版采用局域网直传，不包含云端地址查询部署。

## License

MIT。第三方组件见 `THIRD_PARTY_NOTICES.md`。
