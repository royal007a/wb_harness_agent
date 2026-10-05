# HA-0078：DSH 补充边界与故障验证

1. 对照 HA-0077 的 30 项测试，补充规格矩阵。
2. 分层编写真实 SDK + 合成 Provider、合成 Adapter、离线 HTTP 和目录所有权测试。
3. 运行新增、相关与全量验证，做定向突变，记录发现和证据限制。
4. 提交测试与证据；不重启 8876，不触碰 8765/132/正式数据库/Keychain。

## 完成（2026-10-05）

- 新增60项，与既有30项合计90 passed；分为11真实SDK+合成Provider、23平台编排/API、19离线协议、7目录所有权用例。
- 7个定向突变全部由行为断言捕获，生产文件SHA前后不变。
- verify exit 0，1614 passed /22 skipped；任务登记Schema和8份JUnit XML可解析。
- 没有生产修改，没有部署或真实模型调用。独立review未在本轮执行。
- 证据：harness/evidence/HA-0078/acceptance.md。
