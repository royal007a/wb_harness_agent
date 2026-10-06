# 8876发布独立复核

2026-10-07，mymacclaude在消息om_x100b636cd343b8a0b3bd8ffa09068f4对a3c5647/d6e3716给出Approved，仅限此次8876发布及两个新Run。其声明未重启、未发模型请求、未写入；以下现场观察归属复审方，不是归档者再次部署。

复审方核对local.harnessagent.dsh-session与8876唯一loopback监听均为PID69819，启动时间07:43:26；runtime和live checkout为da43bff。备份权限0600、父目录0700，SHA与course-deployment.json一致；未执行恢复验证，quick_check不等于恢复演练。

复审方先检查verify_receipts.py只发GET且禁用代理，再用python3 -I执行，两个固定Run均passed。其另核对API详情、两张截图、创建时间晚于服务启动、ID不在原24个Run中且列表变成26个。真实Run b7f78649花费13545 Token、5次模型调用；合成Run 4842e993花费520 Token、3次模型调用；均succeeded、reserved=0，findings均partial。截图和API一致，真实Run明确读取clause-1/clause-12，未复用旧浏览器证据。

归档者本轮也执行python3 -I harness/evidence/COURSE_RELEASE_20261007/verify_receipts.py，exit 0，两Run均read_only_receipt_check=passed；仅GET回查，不新增Run或Provider调用。固定回执、截图和复核脚本从a3c5647原样归档。

## 版本证明与保留限制

Run事件没有release字段。两个Run对应da43bff的结论依赖创建时间晚于新PID启动、观察期间PID/release不变及live checkout等旁证，是推断而非Run自身持久版本证明。HA-0113版本戳仍未合并，不以本记录补造事件。

一份公开合成合同、一次新增真实Run不是准确率评测；partial和人工核对要求保留。第七轮1852 passed/22 skipped的完整门禁有启动并发重叠，跳过不算通过，旧UI波动根因未定，前六轮失败保留。8765/132未变，HA93及后续候选未进入被测/发布代码。本次批准不包括数据库恢复成功或其余课程全文忠实度。
