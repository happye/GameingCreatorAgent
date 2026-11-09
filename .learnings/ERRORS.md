
## 2026-11-08 PowerShell搜索与浏览器测试

rg文件通配符用目录加-g，不猜测文件名。Playwright同步上下文内不可直接调用含asyncio.run的服务方法；通过真实HTTP查询编辑结果。组合label含select选项时用明确控件定位；失败日志保留，定位修复后重新验证。

## 2026-11-08 Studio回归适配与导入检查

完整门禁5093过4失败7跳：旧模糊label匹配新增复制按钮，旧刷新清稿预期与持久草稿冲突，人民币符号字形不同，import子串误命中knowledge-import路由。修测试时保留费用金额/确认前零调用与迟到隔离断言。导入正则前界不可排除斜线，否则漏掉合法注释后from；保留无空格/注释语法安全回归。源业务字节未改。

## 2026-11-08 异步确认工具调用

request_user_input_async是直接工具，不在functions.exec的tools对象；误调用返回TypeError后改用直接工具成功展示。accepted表示已展示问题，不能当作用户同意；本次Provider真实发送保持0。

## 2026-11-09 额度耗尽与验证恢复

用户要求低额度停止但未及时收尾，原验证随会话失效且无终态。改从当前线程JSONL的rate_limits读取实际余量，12%预留收尾、约10%按用户要求暂停；不由累计token猜百分比。长验证用Hidden独立pwsh，逐项日志及退出JSON，恢复先核OS进程/终态，不重启活任务。verify可选PreserveRuns只保留现场，不删减门禁。

## 2026-11-09 本机连接队列与远端推送

Studio首次加载多模块时，默认Python 3.13监听队列仅5；延迟accept的真实模块连接突发回归在旧配置超时，128队列通过，保留新旧XML。不能仅凭Playwright标签超时增加等待或宣称业务失败；先捕获console/requestfailed/body。GitHub直连失败但Windows已有本机代理可用，单次git -c http.proxy使用现有端点即可推送，不修改全局配置或费用Provider的trust_env边界。搜索命令仍须目录加-g，避免重复猜文件名/PowerShell通配参数。

## 2026-11-09 音频采样器与中途门禁汇报

完整门禁终态有3失败，但中途监控错误报告无失败；进度尾部PASS不能代表前面无失败。后续以父控直接扫描全日志终态词、保存快照标识和最终XML/exit为准，禁用彩色日志；独立监控摘要只作提示。HOOK_CAPTURE仍用ScriptProcessor，600ms主线程阻塞回归测得0.02957而非0.1；换AudioWorklet保留原0.4秒采样及阈值，并核渲染帧连续性。共享页面的hook若断言提前退出，fixture须finally卸载，否则残留2个audio污染后续清理测试。原/新证据保留，不把测试采样修复冒称业务音频修复；循环边界的实际短暂缺口仍由不变断言检验。
