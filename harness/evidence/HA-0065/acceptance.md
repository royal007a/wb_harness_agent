# HA-0065 Product边界与契约负例

2026-10-04，基线0ee58a0；固定e6e1fb9已独立Approved（review.md）。离线证据；未发布，不触碰正式DB/8765/132、
Provider、凭据或部署拓扑。规格PRODUCT_CONTRACT_BOUNDARIES.md，决策ADR-0065。

## 变更

- after为0..9223372036854775807；HTTP Query和Store.events双重校验，越界422，
  不截断或伪空页。动态OpenAPI直接继承Query约束，不再手工补一个minimum。
- 静态after与源next_cursor/Event.sequence/Run.latest_sequence上界一致。
- Event.task_id/run_id及Artifact.run_id采用现有Product ID格式；不代表引用完整性。
- 补动态422信封、Task详情runs必填、retryable固定false的精确负例。
- UTC新增14组Schema层正反例；发现当前Python解析器接受24:00:00并归一化，
  故检查器显式限制小时00–23、分秒00–59，而非只依赖datetime解析成功。

## 证据

| 文件 | 结果 | 说明 |
|---|---|---|
| before.xml / before.log | 27 failed / 9 passed / 24 deselected，3.73s | 修生产代码前的游标/引用选择集 |
| before-final-test.xml / log | 28 failed / 32 passed，7.28s | 最终新增60项放回0ee58a0；另抓住旧UTC检查器24小时误放行 |
| new.xml | 60 passed，6.91s | 最终新增文件，UTC修复后 |
| targeted.xml / targeted-http-observations.json | 250 passed，29.35s | 5个相关文件，68入口observed且有passing-test 2xx |
| full-http-observations.json | 1095 passed / 16 skipped，109.33s | 148入口observed且有passing-test 2xx，不等于功能/分支验收率 |
| mutations.md及mutation-*.xml/log | 10/10定向突变被杀死，errors=0 | 每次独立worktree单点修改，恢复后文件SHA与修改前相同 |

完整`bash harness/verify.sh`已结束，exit 0（verify.log）：全量1095 passed /
16 skipped，103.41s；另跑retrieval-state 2、agentic-state 2、adaptive 6项均通过，
后续评测、准入检查、前端语法与diff检查通过。只有既有AnyIO BlockingPortal
弃用告警；skipped及not_admitted不计作真实能力验收。没有借此宣称历史任务注册表
的所有证据路径都齐全（已登记EVIDENCE-PATH-01仍未修）。

最终新增测试SHA-256：2c3addf1bf5fbac43188ae7d10b5a9c2b2a120ca05c9fd7ea70a34145b348caa。
将该文件复制到独立0ee58a0 worktree后直接pytest该文件即可复现28失败；它导入的
test_product_http_contracts.py须保留基线版本，因为UTC检查器本身就是本次被测
修复对象。不是把修复后的UTC函数带回旧版来证明旧版失败。新增文件两端同SHA。

28项分别为HTTP状态/读取顺序4、查询Schema上界2、Store类型/范围8、响应上界1、
引用格式12、UTC格式1。不是导入或缺helper失败；Store组包含旧代码抛OverflowError/
ProgrammingError或没有拒绝的行为。targeted-initial.xml记录UTC修复前1 failed/168 passed，
失败是真正的24小时检查漏洞，未删去这条中间证据。mutation_store_guard中的失败
也包括移除防御导致的异常类型不符，不冒称每条都是HTTP状态断言。

targeted/targeted-initial XML中31个Workbench参数名经safe_test_id改为SHA，避免
测试名携带大段合成输入；before与mutation日志/XML仅清理行尾空白。结果不改写。
两份观察器都如实记录0ee58a0+dirty，140项源码/契约/测试/映射哈希前后一致，
事后重算无差异；不是最终提交的预先伪造SHA。16 skipped不算通过。

## 边界

- TestClient +临时SQLite，合法/拒绝查询比较全部表及total_changes；非法HTTP
  参数另用Store调用记录证明入口已拒绝，不依赖Store抛异常补救。
- 最大序列案例通过测试DB稀疏种入max-1/max，不是实际写入2^63条事件；不声称
  已验证序列耗尽的写入恢复、并发分页或所有客户端大整数精度。
- 新引用约束是公开机器契约，不是新建运行时全响应Schema拦截器或坏库修补器；
  不核对引用对象是否存在/同域。UTC检查器为服务输出子集，不是通用RFC3339。
- 10个定向突变不是全库mutation score；其他模块Schema、REQUEST-ID-01与字面
  $ref投影问题仍未完成。合法日期输出、Task/Run业务及执行门禁不扩展。
- 基线/突变worktree均已清理；不碰mymacclaude的HA-0064 review worktree。
  固定提交已独立review；实际发布需兼容本机拓扑后先本机再132。
