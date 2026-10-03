# HA-0055 持久 Runtime 状态 UI

来源：HA-0054 视觉检查发现 error 瞬时显示后被消息刷新擦除。
规格：specs/testing/AGENT_RUNTIME_UI.md。

1. 临时库/真实浏览器增加稳定断言，确认旧实现失败。
2. 按消息关联呈现 Exchange，区分真实回答与未提交流状态；加选择代次和
   固定发送 Session，防止旧请求覆盖新选择。
3. 回归失败/取消/活动/成功、注入和慢响应竞态；改真实部署浏览器脚本。
4. 固定版本验证、备份与双端部署；桌面/手机查看；交 mymacclaude 只读 review。

不改权限、模型 gate、后端状态机和 Product Run；OpenAPI 覆盖缺陷仍单独待办。
