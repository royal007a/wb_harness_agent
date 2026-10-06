# ADR-0085：区分未执行票据与调用失败

状态：实施中。部署范围沿用 ADR-0083 的独立本地 DSH 8876，不改 8765/132。

## 来源和问题

HA-0084 首批课程阅读中 O16、H29 强调观测信号必须能区分实际行为与状态标签。具体依据见 `docs/research/JIKESUMMARY_READING_2026_10_06.md`，不是从课程复制运行代码。

DSH-CROSSING-02：平台预签发下一轮模型票据，即使模型已经完成答复，该票据也会在 finally 中被记成 failed，且事件排在 run.succeeded 之后。它从未发出请求，不能当作 Provider 失败。既有已发但结果不明的调用必须继续保持 unknown。

## 决定

1. 未使用 issued → retired；已执行 in_flight → unknown。完成、未知和历史 failed 不修改。无需表重建，status 为文本列；保留旧 failed 读取兼容，不反向猜测历史事实。新事件 data 带 schema_version=dsh-crossing@2，通用事件 envelope 不变。
2. 正常成功和失败时，将本 generation 的退役放在终态事务中、终态事件之前。成功产物与预算状态同事务，失败原子性不以 finally 补写冒充。
3. 每次退役事件会推进 Run sequence；退役后重新读取 Run 再写终态，避免旧对象覆盖事件序号。
4. 保留 finally 作为已终态 Run（尤其取消）的清扫。取消不等待 Provider 或 crossing 锁；迟到的 unknown/retired 审计允许出现在 cancelled 之后。终态事务本身失败或硬中断留下的非终态 Run 不在 finally 单独提交退役，交启动恢复处理；不假装终态事务已经成功。恢复仍只记未知、不发请求。
5. 不修改 Provider 协议、调用上限、预算、工具权限和真实模式准入。不实现 A2，不引入自动重试、遥测外发或统计平台。

## 验收

- 未用下一轮票据 retired、没有伪造失败；正常成功/失败终态为当次退出的最后事件。
- 两个退役事件及终态序号连续，不覆盖序号；completed 和 unknown 保留。
- 退役事件或终态插入故障时事务回滚；失败处理不留下已成功产物。
- 重复清理零写入、隔离代次、历史 failed 不迁移。
- 取消在阻塞回调期间可完成，迟到结果不发布，unknown 预算仍冻结。
- 官方 SDK + 合成 Provider 回归、旧版行为反例、定向突变、完整验证和独立 review 分别记证据；部署另验版本与 PID。
