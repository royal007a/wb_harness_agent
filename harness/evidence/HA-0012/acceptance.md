# HA-0012 验收：分享链接官方客户端下载 Skill

日期：2026-09-13
状态：通过

- `skills/baidu-netdisk-download/` 仅从 stdin 接收当前用户明确提供的官方分享链接，stdout 不含 URL 或 `pwd`。
- 脚本只通过 macOS `open -a /Applications/BaiduNetdisk_mac.app` 交接，不发网络请求、不登录、不自动化 GUI、也不调用未验证数据面 API。
- 下载认领必须是用户明确指定的 `~/Downloads` 内常规非符号链接文件；Skill 不读取文件内容。
- 已运行 Skill 格式校验及 URL/脱敏/本地路径测试；完整回归结果见 `tests.xml`。
- Claude 同步采用指向项目 Skill 的符号链接；没有复制任何链接、提取码或凭证。
