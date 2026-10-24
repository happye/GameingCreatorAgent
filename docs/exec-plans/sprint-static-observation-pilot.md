# 单注册帧parts-v2真实协议试验

2026-10-24，Phase 0／F010。前置工程已由fdd83d6交付并推送；本轮只执行已交付生产CLI，不重开DSH工程任务、不重投两个已完成工程请求。用户已明确答复“允许仅这一次，预算¥0.50”。

## 范围与当前状态

- 原28–29秒Atom样例的28.5秒登记帧，run `f601fb9b3e734d5ea188fc15c790acbb`，image `000057`，19264字节，SHA `8ff4d42cb20f96b16b56b016d2e385024d33217ddc27e007d071652de6dc12f7`。
- proposal `95880840d38ea2f6e6bda85427ecfab8806cab9ec02422b1bd3d4a449a5f2b59`；专属authorizationId `static-frame-pilot-v2-20261024-28500`，SHA `ab612b39cc6897c1c4ed99ddea8175efeaa6de94778706d1b7263ca19d85af44`。
- 目的地`https://api.deepseek.com/chat/completions`，deepseek-flash，parts-v2，1请求／1图，无重试。新增授权上限¥0.50，保守预留¥0.416；不借用旧余额或费用授权。
- 主控已通过生产loader与当前Completed／源／图验证，9受测源码SHA不变；进程凭证只核存在，未输出。唯一原Sol/high已独立核授权匹配PASS，未创建ledger／发图。真实ledger在前检尚不存在。
- 首次本地helper因Decimal('0.50')不是规范小数文本而在授权／账本写入前拒绝；仅改数值相同的Decimal('0.5')后通过。没有发生Provider调用，原提案与金额不变，失败保留。

## 执行与恢复纪律

Codex唯一执行者；同一评估者仅复核此次授权／实际typed结果与费用，不重审源码或复制测试。只发一次生产dispatch，外围先保存不可覆盖的dispatch intent及实际进程定位。未决／通信／结果不明只查同一进程和新静态账本，不重投。响应原文不落盘；只保存生产CLI的typed报告及白名单诊断／hash。

成功后只用本地resume与另一进程查询核读回，零新发送；失败／超时也保留attempt、未知占用和次数，不自动重试。922旧项目文件基线（排除SQLite共享内存）作前后比对，旧费用／原标注保持。

## 实际交付与费用

唯一生产dispatch已于2026-10-24 07:12:40–41 UTC完成，进程29700退出0；外围intent排他创建并fsync，launchCount1／automaticRetries0。HTTP200，attempt `attempt-205f8efdee85311c7190dfc57bfb4a13`，Provider requestId `65a76606-86e8-4288-b46d-79473c33eca2`，actualModel deepseek-flash。生成1主体／7条typed属性并发布集合`static-frame-pilot-v2-20261024`，集合hash `cba82e136f712d0699c3cf9bba020c281cd613a7b9c913cf9d3494573ac89005`。

输入1016／输出119／缓存输入0 tokens；冻结价格按周末offpeak估算¥0.001492。ledger的chargeStatus=known表示可计算金额，usage.costStatus=estimated／billingVerified=false，未核供应商账单。原¥0.416预留已由该估算额替代，不再占unknown；reservationCny字段保留历史值。一次请求已耗尽，余下金额不是第二次许可；历史unknown独立不变。

另三进程只做本地resume和两次查询：resume published／unchanged、providerRequestsSent0；按草案的同主体7条件命中1条，橙色＋上衣同部件条件命中0条，未把橙裤色拼给灰上衣。源时间28.5秒及原图片hash／evidence／partId读回一致。922旧文件前后及读回后SHA不变，新增7文件仅新静态库和新ledger／锁／attempt，无原响应落盘。唯一原Sol/high实际结果复核PASS（同角色，无重复源码评审）。

本次用户已收到：能生成／保存／检索草案；费用为估算、视觉仍未知；下一推进TD006特殊源时钟自动映射的离线切片，不新增API或重标要求。人类画面对错仍null，F006/F009/F010false。证据位于ignored `artifacts/dsh-static-generation-20261024/real-*`，人类授权引用为本次request_user_input_async call_8170e4dce3eb450c8bbf162c18421a3a item0明确答复。详见[报告](report-2026-10-24-static-observation-pilot.md)。

发布：文档9e8e525已本地提交；一次普通push于GitHub:443连接失败，远端仍e9361e2。不强推／循环重试；所有本机结果与授权／attempt已保留，后续实质节点再补推。
