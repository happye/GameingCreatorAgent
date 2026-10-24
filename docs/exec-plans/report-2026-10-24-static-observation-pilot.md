# 单登记帧parts-v2真实协议试验

2026-10-24，Phase 0／F010。原28.5秒登记画面已按新授权唯一发送一次，真实接口接受parts-v2格式，草案已保存并由其他进程检索读回。它提供的是可回看的模型声明；真人画面对错仍未判断。

## 使用结果

deepseek-flash返回1个主体、7条typed属性：红发、灰色上衣、橙色裤子、长杆状武器。以上均为模型声明，不是新增人工标签。按这7个条件同主体查询命中1条；要求同一件衣物同时为橙色与上衣时命中0条，未把裤子颜色拼给上衣。图片身份、28.5秒源时刻及部件ID保持。

新进程运行本地resume返回published／unchanged，新增发送0；两次新进程查询均零模型调用。922旧项目文件（不含SQLite共享内存）在发送前后及读回后SHA不变；原费用账本、12条标注／纠正和录像字节保持。原长钟馗269成功／3缺口、469观察及旧费用不变。

## 授权、实际费用与证据

| 项目 | 实际事实 |
| --- | --- |
| 新许可 | 用户明确“允许仅这一次，预算¥0.50”；原28.5秒登记图＋parts-v2提示词，1请求／1图，无重试 |
| 目的地／模型 | https://api.deepseek.com/chat/completions；requested／actual均deepseek-flash |
| 发送 | 1次，HTTP200；requestId `65a76606-86e8-4288-b46d-79473c33eca2` |
| 用量 | 输入1016／输出119／缓存输入0 tokens |
| 费用 | 按冻结deepseek-flash-cny-2026-10-04周末offpeak估算¥0.001492；未核供应商账单 |
| 预留 | 原¥0.416已由该估算金额替代；历史reservation字段保留，不再作本次unknown占用 |
| 次数 | 本授权1次已用尽；余下金额不允许再发送，历史unknown不变 |
| 发布 | collection static-frame-pilot-v2-20261024，1条观察／1主体／7属性 |

proposalHash `95880840d38ea2f6e6bda85427ecfab8806cab9ec02422b1bd3d4a449a5f2b59`，authorizationId `static-frame-pilot-v2-20261024-28500`，authorizationSha256 `ab612b39cc6897c1c4ed99ddea8175efeaa6de94778706d1b7263ca19d85af44`，attempt `attempt-205f8efdee85311c7190dfc57bfb4a13`。冻结图片SHA `8ff4d42cb20f96b16b56b016d2e385024d33217ddc27e007d071652de6dc12f7`，响应仅存hash／大小及typed结果，未保存原HTTP／视觉JSON正文。

Codex唯一执行已交付生产CLI；原Sol/high独立核授权及实际结果PASS，未新增DSH工程请求或重复源码测试。执行前9受测源码SHA一致，生产源码仍fdd83d6。原¥0.50文本的本地规范金额校验失败发生于发图前，不是Provider重试；完整经过见[sprint](sprint-static-observation-pilot.md)。

本机ignored `artifacts/dsh-static-generation-20261024/`保存不可覆盖的real-dispatch-intent/process/completion、typed stdout、real-local-resume、两查询、922文件摘要对比和独评记录。ledger chargeStatus=known只说明已有可计算金额；usage.costStatus=estimated、billingVerified=false。静态查询报告的sourceCostStatus=unknown沿原只读声明合同，不代表新的扣费或费用丢失；实际估算在独立generation attempt／ledger。

## 保留门槛与下一项

visualVerified、humanLabels和qualityGate保持null；F006/F009/F010false。一次真实协议成功不证明准确率或Top10可用率，不要求重标原样例。旧DSH STOP_PENDING保留，无再次cancel／杀共享Host／重投旧任务。

继续原Phase 0路线：独立真实质量仍依赖原来源分组／事前参考与固定Top10人评；不重复催相同待办。可独立开发的下一切片为TD006特殊源时钟自动映射，先只读定位并冻结有限合同，再由DSH唯一写者实施及浏览器验收，无新录像API或人工依赖。
