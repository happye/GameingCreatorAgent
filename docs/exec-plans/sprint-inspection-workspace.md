# 本地检查工作台基础功能

更新时间：2026-10-04（Asia/Hong_Kong）。状态：技术验收通过，F007 true；F006人工质量门槛仍false。

## 范围与归属

用户要求Codex接续Grok已有界面并补齐基础功能。按原总方案§12实现素材/视频/查询三栏及源时间轴，依据ADR-002授权；新分析仍通过CLI。没有加入MP4渲染、发布、商业结算或正式桌面EXE。

root负责HTTP/媒体服务、公共storage port、集成、真实浏览器验证和共享文档；inspection_frontend在独立worktree只改ui/static三个文件及own sprint，ui_review只读审查。Grok改动全部保留；本轮workers已冻结。

检查点：32d5a3b保留并验证Grok基线；82e4020后端；9fcbdec集成0d9e3c5页面；614c10d集成3e5c8e2前端修复。最终版本/推送状态见HANDOFF及git。

## 实现

- 项目/运行发现、已完成/失败状态、源名/时长、阶段和费用。缺价目或unverified调用保留unknown，已知部分不冒充全额。
- 原视频GET/HEAD及单Range/416；只通过run/evidence登记身份映射文件，项目目录及DB实际路径留在仓库，文件SHA校验缓存随身份变化失效。
- 证据单条SQL读取避免每张图片重扫源视频；完整时间线校验不削弱。媒体URL保留相对project表示，前端准确核对身份。
- 候选/事件定位和源区间结束暂停，证据缩略图/弹窗、WAV、转录、文本/标签过滤；候选rank和源时间排序分别保留。
- 片段篮按project/run保存于localStorage，跨查询保留来源，导出前匹配当前run事件/候选。JSON/CSV保留SHA/configHash、微秒、事实、证据、原查询/模式/版本；拒绝过期区间且防CSV公式注入。
- 安全DOM文本、严格CSP、请求取消/版本核对避免旧响应覆盖；取消连接正常关闭，不重复写错误响应。静态资源随wheel打包，运行页面不需Node或浏览器测试包。

## 修复与失败证据

Grok基线verify先因运行时收据漂移失败：28个stdlib pyc从已验证归档逐项恢复，收据/解释器/系统设置未改；恢复后561passed/0skip。原HTTP错误将CLI ExitCode写为HTTP状态，已复现并修复为有效4xx/5xx+JSON exitCode。

Range缓存初测发现Windows CRT fstat丢失亚秒精度且读取会改变atime；改为高精度Path.stat加句柄dev/ino/size比对，忽略atime，立即等长变更回归通过。只读审查指出DB链接越界、证据99次hash和未知价格错计，均修复并加入测试。

初次真实浏览器由于absolute project URL与前端relative身份不一致拒绝视频，已修并有HTTP回归。严格CSP下字符串wait_for_function触发unsafe-eval，测试采用debugger轮询，没有放宽页面CSP。片段篮reload初测失败原因是页面默认另一Completed run；重选原run后恢复通过，不跨run混用片段。

最终启动发现Windows默认SO_REUSEADDR允许两项旧/新HTTP服务同时监听8765，浏览器仍命中旧模块。核对两项本仓库UI进程身份后重启，仅停止这些预览；服务增加SO_EXCLUSIVEADDRUSE与重复监听回归。最终端口仅一个监听，projects/inspect返回新版真实视频URL及费用字段。GitHub首次连接失败，进程内HTTP/1.1重试成功，未修改全局Git配置。

## 最终验证

- `./scripts/verify.ps1`：582 passed、1 skipped（33.38s），Ruff73文件、mypy48文件、CLI和重复离线wheel通过。Windows缺文件symlink权限跳过该真实链接fixture，另有canonical实际路径回归通过。
- wheel SHA256 `9af66ee95055d99d88caf56d299d6a1d2b9070ab451bbb00318ae2f48d378210`，50项包含app.js/index.html/style.css，无模型、DLL、源视频、DB/缓存。
- 前端独立Chromium21项合成交互检查通过；详细范围见sprint-inspection-frontend。390px移动页面无横向溢出，缩略图限制高度。
- `scripts/validate-inspection-ui.py --project artifacts/demo-phase0 --run f76f5d6495314c04ae04083614d4afd6`及英文查询各通过：真实95.175874s PV加载，111事件/3候选，28–29s准确暂停在29s，证据图自然宽度非零，JSON/CSV区间/身份/证据匹配，筛选不改rank，无关hybrid为空，同run篮子恢复，0 JS错误。Chromium153.0.8010.12；报告/下载/截图在ignored artifacts/inspection-ui-validation和英文目录。qualityGate=null。
- 五项用户/系统环境和Python注册表指纹不变；本轮没有付费API请求。可选Playwright1.63.0/锁41包在.venv，浏览器及工具在.tools/browsers；未安装系统依赖/浏览器或使用用户profile。

## 接续

使用run-ui.ps1与user-manual；运行不需要ui-test，验证脚本为显式可选检查。新机不含ignored素材/DB/权重。浏览器原视频编码支持和非零PTS/不同音视频起点尚未联调（TD006）；现有PV通过不能证明全部容器时钟准确。

F007只是本地检查技术合同。F006仍需独立人工U10、长会话性能/成本及pure semantic负例校准；TD001/TD005仍open。来源和边界已同步README、AGENTS、工程/产品规格、架构、quickstart、testing-guide、API、feature_list、assignments和HANDOFF。工具适配器通过共享AGENTS读取，不重复复制状态。
