# HA-0045：Pi metadata-only Guard Contract

## 目标

将课程 20 的外部护栏边界固化为可验证的控制面接口，覆盖工具调用/结果、上下文和 Provider 请求的准入判断。

## 已实现

- `backend/pi_security_guard.py`：只读确定性评估器；不执行动作，不调用模型/网络。
- `specs/v1/pi-security-guard.schema.json`：action、policy、response 机器契约。
- `POST /api/local/pi-contract-pipeline/security-check`：幂等决策接口。
- 未知 phase/tool、越权路径、敏感内容、非 HTTPS 白名单域名、token/cost 超限、未准入 Provider 均拒绝。

## 非目标

- 不授予运行时权限，不启动真实 Pi/Provider，不替代 OS 沙箱、出口代理或身份认证。

## 验收

- 定向测试覆盖 allow、各类 deny、Provider 显式准入、幂等和未知字段。
- `harness/verify.sh` 全量通过；本机与公网部署后 health 与接口冒烟通过。
