# 课程优化批次：8876 发布与新浏览器冒烟

日期：2026-10-07（Asia/Shanghai）。本记录只覆盖 8876 本地 DSH 服务，不涉及 8765 或 118.196.123.132。

## 版本与发布

- 实际运行版本：`da43bff8caf66ca528c85e81d81b28869c1cb9a4`，launchd label 为 `local.harnessagent.dsh-session`，发布后 PID 为 69819。
- 页面：<http://127.0.0.1:8876/dsh>。
- 发布前运行版本为 `ad957fb888789eccc1150d0ea0df643cce8047c9`，原 checkout 为 `5939e5de2a76c6dc487cf7e062b1db901c474011`。发布时仅快进 live worktree 至上述候选；没有强制重置或改写历史。
- 停服前核对 label PID、唯一端口监听 PID 和启动时间，并确认已有 24 个 Run 均为终态。通过 SQLite backup API 备份服务实际使用的 `.local/dsh.db`，备份 quick_check 为 ok；位置与摘要见 `course-deployment.json`。备份权限为 0600、父目录为 0700，数据库未进入 Git。
- 只移除已核对的 label，等端口释放后使用原启动脚本启动。启动后再次核对 release、PID 和健康状态。启动预检及真实调用按已有授权解析 Keychain 引用；没有把密钥明文输出或写入命令参数、环境变量及证据。
- 回滚未执行。回滚目标代码为原运行版本 `ad957fb`；若需要回滚，应先确认当前任务已终止、核对当前 label/监听 PID，再在隔离 checkout 上运行原启动脚本并验证其 release。不得自动覆盖现有数据库；备份恢复是另一个需要明确决定的数据操作。

## 发布前完整验证

第七轮原命令 `sh harness/verify.sh` 完整退出 0：1852 passed、22 skipped、1 warning。日志和进程退出来源见 `../HA-0089/verify-seventh.md`、`verify-seventh.log`、`verify-seventh-process.json`。

该测试快照与本次 da43bff 的 backend、adapters、frontend、tests、dsh-adapter、specs、deploy 和 harness 根目录 Python/shell 验证脚本无差异；差异为研究报告与证据。HA-0085 至 HA-0092 的代码及离线复审与本次真实/浏览器证据分开报告。前六轮失败没有删除；这次通过不能证明此前 UI 偶发失败的根因已消除。

## 新浏览器验收

Chromium，视口 1440×1050。核对页面版本及默认合成模式，在实际页面选择 payment_terms、填写公开合成的十二条中文编号合同、勾选公开数据确认并提交；不是复用 HA-0077 的旧浏览器回执。第一条为收到发票且验收合格后 30 天付款，第十二条为发票错误时暂停付款，其他条款是普通归档义务。输入摘要见 JSON，没有上传业务秘密或课程 PDF。

| 模式 | 新 Run | 模型调用 | 工具调用 | Token 用量 | 工具往返轮次 |
| --- | --- | ---: | ---: | ---: | --- |
| 合成联调 | run_4842e9937b154d21b2c84ed957c528f4 | 3 | 2 | 520 | 1、2 |
| 真实豆包 | run_b7f78649e03a4e9db97b4bc82be5f97c | 5 | 12 | 13545 | 1、2、3、4 |

两次 Run 均 succeeded、预留归零，findings 均为 **partial**。页面显示 30 天及 clause-12 引文，错误提示为空。真实 Run 显式读取了 clause-1 和 clause-12；合成 Run 的内容来自搜索返回，没有额外调用 read_clause，不能把两者都称为显式逐条读取。

完整分页读取新 Run 的事件，序列无重复，最后一条均为 run.succeeded。未用到的下一轮票据在终态之前记为 retired，没有 failed 调用事件。真实 Run 最终有 17 张 completed 收据和 1 张 retired 收据；合成 Run 为 5 completed 和 1 retired。JSON 中 crossing_event_status_counts 是状态变更事件数量，不是当前 in_flight 数量；最终状态看 final_receipt_status_counts。

下载产物逐一核对字节数与 sha256。两张完整页面截图已人工查看：`course-integration_probe.png`、`course-real_provider.png`。截图只含上述公开合成输入、结果和运行标识。验收结束时 runtime 版本未变，工作目录 cleaned/pending/retained 为 0，另核对运行根目录无 run-* 和登记 JSON 残留。

## 回执来源与复核

`course-deployment.json` 由实际部署脚本分阶段生成；`course-browser.json` 由实际浏览器脚本生成，随后使用只读 GET 补入最后收据状态、显式读取 ID 等字段。postcheck_utc 是这次补充观察的时间，不是 Run 创建时间。没有补造未执行的浏览器步骤，也没有把离线数据写成真实模型结果。

同目录 `verify_receipts.py` 是归档后新增的只读复核器，可在服务仍运行此 release 时重取固定 Run/事件/产物并核对。不创建 Run、不调用 Provider、不部署。命令：

```sh
python3 harness/evidence/COURSE_RELEASE_20261007/verify_receipts.py
```

## 边界

- 只有一份公开合成合同、两种模式；真实模型仅新增一次 Run，共 13545 Token。不是准确率评测，不代表任意真实合同可正确审查。
- 计划完成和引文/数值机械校验不等于语义支持或证据找全，partial 如实保留。没有 OS 级沙箱；只能使用公开或合成文本并人工复核。
- HA-0093 及之后的独立候选没有合入本次发布。课程阅读的来源/计数审查与内容忠实度抽查有不同范围，本次部署不代替阅读报告的独立审查。
- 本记录是执行方证据；新增发布回执是否获独立复核，另由 reviewer 固定消息/证据记录，不在此预先宣称 Approved。
