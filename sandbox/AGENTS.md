# 隔离代码执行

- runner.py 仅复制到容器镜像内执行，禁止在宿主启动。
- Runner JSON 结果仍不可信；成功必须经控制面数值回算。
- 输入目录只挂载该 Run 的已登记 CSV，不能挂载仓库、用户目录或 Docker socket。
- 镜像固定摘要；修改 Runner、Dockerfile 或运行参数后必须重跑隔离探针。
