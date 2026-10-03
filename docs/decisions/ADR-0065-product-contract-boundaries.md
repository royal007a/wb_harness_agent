# ADR-0065：Product的可取值范围必须匹配存储边界

状态：实现与离线验证完成，待固定提交独立复审及双部署；基线0ee58a0。

after的旧声明只有minimum=0，但SQLite参数最多signed int64；合法声明值可导致
OverflowError/500。采用明确的0..2^63-1范围，HTTP入口与Store双重检查，静态/动态/
源Schema均公布相同上界；不截断、钳制或返回伪空页。最大合法值仍是合法空页。

同时收紧Event与Artifact的Product引用格式；补齐HA-0062审查发现的422信封、
Task详情required、retryable const及UTC检查器负例，并用突变证明测试有效。
不因能解析正例就认定Schema足够严格。ID格式不替代引用完整性，UTC输出子集不
等于完整RFC3339实现。错误request_id一致性另有任务边界，不混进此更改。

验收：specs/testing/PRODUCT_CONTRACT_BOUNDARIES.md。
