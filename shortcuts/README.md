# 截屏到电脑模板源文件

`AirBridgeScreenshot.unsigned.shortcut` 是从实际 iPad 导出格式整理的六动作二进制 plist。
已删除原来的云端查询、地址拼接、个人网址和密钥，只保留一个 `SETUP_URL`。
转换和上传的输入分别明确连接到截图、转换后的 PNG，POST 的目标连接到唯一 URL。

这是给维护者检查和签名的源文件。没有 Apple 签名，也没有完成真实 iPad 导入测试，
不要把它作为普通用户可以直接导入的文件发布。Windows 安装包不包含这个未签名文件。

## iPad 上创建分享副本

保留日常快捷指令，复制副本后改成以下六个动作：

1. Hide Control Center
2. Wait 1 second
3. Take Screenshot
4. Convert Screenshot to PNG
5. URL：普通文本 `SETUP_URL`
6. Get Contents of URL：URL 变量选择第 5 步；Method = POST；Request Body = File；File = Converted Image。

如果副本来自旧的云端版本，删除原来的 GET 查询动作及拼接 `/clip/` 的第二块 URL。
最后上传动作重新选择剩下的 URL 变量。Share → Copy iCloud Link 生成通用分享链接。
当前 Windows 引导要求使用者在添加后修改唯一 URL，不依赖额外导入问题。

## 用 Mac 签名

在 Mac 上可以使用 Apple 提供的命令（Windows 没有该命令）：

```sh
shortcuts sign --mode anyone --input AirBridgeScreenshot.unsigned.shortcut --output AirBridgeScreenshot.shortcut
```

签名会将模板副本交给 Apple 验证。仍须在苹果设备实测导入、编辑地址、上传 PNG。
本项目尚未执行这一步，不能将结构检查当作导入成功。

- [Apple 分享说明](https://support.apple.com/guide/shortcuts/share-shortcuts-apdf01f8c054/ios)
- [Apple 命令行签名说明](https://support.apple.com/guide/shortcuts-mac/run-shortcuts-from-the-command-line-apd455c82f02/mac)
