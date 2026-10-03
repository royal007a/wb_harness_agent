# HA-0065 独立复审

2026-10-04，mymacclaude对固定e6e1fb9给出Approved，2 Low、2 Info。以下为
reviewer回报，不冒充作者重跑其探针。只读worktree、TestClient、临时SQLite。

- 指定两文件112 passed，测试SHA匹配。保留基线helper回0ee58a0，28 failed /
  32 passed，无导入错误；HTTP4/参数2/Store8/响应1/引用12/UTC1与作者证据一致。
- 非法/超长/Unicode after在Store前422；max原样空页、分页连续；三份Schema一致。
- 18突变杀死16；其余两项仍被后置日期解析或tzinfo检查拦截，非有效漏洞。
- 真实服务UTC时间、合法小数秒通过；24点、naive、非UTC、非法日历均拒。

## 后续

1. Low：参数化缺显式23:59:60负例；当前正则[0-5]和日期解析均拒绝，补专用向量
   可以防止未来替换解析器和正则时退化，不称现有实现会接受闰秒。
2. Low：Product ID的`$`锚在Python正则下可放过最后一个换行。全库类似用法需
   单独审计，不能直接换Python专用`\Z`而破坏JSON Schema的跨语言正则兼容。
3. Info：HTTP沿用FastAPI的宽松整数词法；1.0、前导空格、+5、下划线等可接受，
   规格已声明。不把此事视为新授权或更改查询转换规则。
4. Info：观测数、突变数、引用格式与真实部署的证据边界如实。

未验证：全量1095/verify未由reviewer复跑；真实序列耗尽、并发分页、客户端大整数
精度、双部署仍不在此批准范围。复审期间HA-0066主仓库改动是作者下一原子任务。
