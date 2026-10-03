# HA-0068 独立复审

mymacclaude对固定697ef73给出Approved（2 Low、3 Info）。来源：当前飞书话题
om_x100b632d2f5594a0c33e795b4fe03ee。以下为复审者报告，不冒充作者追加重跑。

- 新38通过且SHA一致。相关7文件干净worktree为179 passed/6 skipped；链接本机
  已安装的pi-adapter/node_modules后185 passed。全量1225 passed/16 skipped。
  相关Faux sidecar需要既有npm ci依赖，新38合成Adapter测试本身不需要Node。
- 原测试回868f4b3：30 failed/8 passed/errors0；旧Gate终态重放409真实复现。
- 补充9项探针通过：pass/reject/cancel三方Barrier竞争40轮，三种终态都出现；
  每轮唯一终态，Gate事件/Artifact/收据数量与成功决定一致；晚到emit超时、
  两个发布点DB失败、Gate失败同key重试、600条后的Gate、空页和坏请求。
- 独立10突变被杀死，包括事务外Gate检查、丢取消/超时重查、错误游标算法、
  详情只读前500、请求additionalProperties及events/list响应解绑。

Low（生产代码正确，测试保护缺口）：

1. pi_contract_review.py:91-92的Pi Child过滤删除后全量仍通过；需显式种子Child
   的行为反例，不能只靠响应Schema表达根Run约束。
2. :213的cancel终态保护删除后全量仍通过；需Gate先成功再cancel的反向竞态用例。

Info与边界：waiting_approval超过timeout后仍可人工Gate，现规格未禁止；
185相关测试依赖Node已安装包；同一DB第二个app被flock拒绝，只有进程内线程
并发证据。新app/sameDB、合成Adapter及Faux sidecar证据分开。未测真实socket、
多进程、倒序扫描大数据性能；RLock不管外部绕flock直写DB。双部署仍未验收。
