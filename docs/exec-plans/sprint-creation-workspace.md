# R1工作台创作与持久任务历史

2026-10-30。Astra/low架构师返回完整有界合同，主控据此固定下面API（替换尚未实施的早期草案）。用户效果：表单→明确Completed素材→三模板方案→显式选择→后台真实MP4→预览/下载；刷新和重启可回查，不暗中重跑。按ADR-003，不等人评，无模型/下载/新费用。

## 固定API（前后端共同遵守）

- capability `creation-workspace-v1`；页面`/creation`，assets/creation.js、assets/creation.css。
- POST `/api/creation/plans`，严格 `{requestId,projectId,runIds,brief,fps}`。projectId取现有/api/projects返回的path作为注册ID，只接受discovery中项目；brief沿用CreativeBrief，fps整数1..120。
- POST `/api/creation/renders`，严格 `{requestId,planJobId,planId,width,height}`；项目/runs/报告从完成父任务继承，不接受EDL/sourcePath/projectPath/output。明确选择才渲染，不能重新规划偷换所选方案。
- 两类POST返回202 `{jobId,kind,status}`，kind=plan/render，status=pending/running/completed/failed/interrupted。同requestId同规范请求返回原job且不重复执行；同requestId不同内容409。requestId为浏览器生成32位小写hex，可按job同一严格ID规则。
- GET `/api/creation/jobs?projectId=...` 返回`{jobs:[Job...]}`，每项目最多最近100项并明确告知截断；GET `/api/creation/jobs/<jobId>` 返回Job。
- Job字段：jobId,kind,status,createdAt,updatedAt,projectId,parentJobId(无则null),error(null或{code,message})；完成plan另有plans数组（id/structure/scriptStatus/ready/gaps/segments含脚本草稿与区间/输出帧，不返回本地sourcePath）及brief/fps；完成render另有artifact。
- artifact固定 `{mediaType:"video/mp4",sizeBytes,sha256,previewUrl,downloadUrl}`；GET/HEAD `/api/creation/jobs/<jobId>/video`复用Range，`?download=1`只变Content-Disposition。只有完成render且回执/产物身份正确可服务。不接受客户端文件名/路径。
- 输入400、未知注册项目/任务404、请求ID/状态冲突409；后台失败只存稳定code/message，不堆栈/任意路径/原日志。

## 持久化/身份

服务端根固定`.cache/workspace/creations/`（必须在所有选定输入项目和原片目录之外）；jobs/<id>/request.json,status.json,input/brief.json,selection/,result/，服务端生成jobId，request不可变。持久请求摘要、父job及父回执SHA、结果回执SHA。来源仍只读原Store。

根级短OS锁只保护requestId去重/登记，不持锁做规划/渲染；复用ProjectWriterLock锁真实job目录，不能用锁文件存在表示进程存活。公开pending前先持job锁、完整落输入和状态，再启worker返回；锁覆盖终态写入。

状态临时文件+原子替换，复用已有限共享重试/路径检查。读取pending/running：锁忙保留状态；成功取得锁后持锁重读仍活动才interrupted。已完成校验原回执；损坏报告creation.artifact_invalid并禁下载，不重做。若终态落盘前已完成有效产物回执，可按该回执恢复completed。重启不自动规划/渲染；失败/中断保留，通过新requestId显式创建新任务。

plan调用现有execute_plan_creation(selection=None)。render核已完成父原plans回执SHA，select_edit_decision后独占写新的selection版本，再调用execute_render_creation。现有read_creation仅接受含已选EDL的目录，不可直接读plan-only目录。每次媒体访问由job→固定产物→最终回执SHA/大小构造MediaResource；拒绝链接、逃逸、跨任务替换及原分析目录输出。复用local_paths/锁/VerifiedMediaCache，不建通用任务框架。

## ownership

后端Sol/medium：独立creation-workspace-backend（base edc9756），ui/creation_jobs.py、必要infrastructure/creation_job_files.py、ui/server.py的路由/ASSETS/capability/生命周期，以及tests/test_creation_jobs.py、tests/test_creation_workspace_http.py。不写静态页面/公共文档。

前端独立Sol/medium：creation-workspace-frontend（base edc9756），ui/static/creation.html/js/css、index.html创作入口、app.js最小capability启用，tests/test_creation_workspace_browser.py。不写server/服务/公共文档。双方不是唯一开发者，不回退他人修改，不递归派发；接口调整先通知主控。公共文档主控负责。

## 页面与必要验证

页面复用项目/Completed选择，表单填写九字段Brief（不要求写JSON）；三方案卡显示片段/时长/缺口与草稿属性，ready才可选；选择和渲染按钮分开。显示历史/失败/中断原因，终态停轮询，加载和刷新不触发POST；旧响应不得覆盖当前项目/所选job。成片可播放/下载，桌面/窄屏可用，无脚本错误，所有素材文本用textContent安全呈现。

验证真实HTTP→规划→渲染→下载；同requestId并发只执行一次、不同内容409、锁忙不误中断、无owner活动任务中断；完成后新实例可读且零重跑；父plans篡改、产物替换、路径/链接/跨job拒绝；失败无视频。浏览器表单/三方案/缺口禁止/迟到/刷新历史/预览下载，集成后一次真实浏览器MP4闭环。只做受影响定向与静态检查，唯一Sol/high评估持久化/并发/来源边界；不重复已绿33项或整仓全量。

此切片不是正式Windows EXE、任意自然语言规划或7模式完整成片交付，按实际部分能力更新看板。

## 实际交付与验证

2026-10-30：前后端12个归属文件已主树集成（含短时长planner最终裁短区间去重和回归），Sol/high唯一评估PASS。修复固定完成SHA未落盘、活动恢复跨任务/父selection绑定及mkdir前链接检查；真实6秒/30秒HTTP渲染、Range/HEAD下载通过。根/子jobs目录链接均在写入前拒绝，不以更换测试输入绕过短预算问题。

主树受影响组57通过/1跳过（8.52秒，.cache/creation-workspace-main2.xml）；跳过为既有文件符号链接权限用例，不是新任务测试。第一轮54通过/2失败/1跳过保留main.xml：已直接补既有read重试的reading=True和回归，更新新增health capability的旧精确断言。Ruff通过，集成单行读取调用格式已整理，worker受影响mypy通过；未重复33项原生渲染或全量。

真实浏览器使用主树代码和原demo Completed run，主页点击入口→中文表单选素材→生成三方案→明确选择→后台生成6秒MP4→预览/实际下载，8,250,672字节且SHA匹配。桌面1366与窄屏390无横向溢出，页面脚本错误0；刷新后找回同成片，关闭服务新实例重开后同任务可读、POST为0、新worker为0，证明没有悄悄重渲染。记录.cache/creation-workspace-real-browser.json，截图real-desktop/mobile.png已查看。headless测试服务均已关闭，未改用户已有服务。前端历史日期改本机可读格式，中文选项隐藏内部枚举，未改异步/请求合同。

只增强P019/P021/P027/P028/P040既有部分能力，不提升为完整自然语言创作、完整渲染或正式EXE。51项仍10/12/29≈31%，首产品0/6/16≈14%；当前人工必做0项，原8项未来待办不变，无新费用或新债务。下一条制作主线字幕：独立creation-subtitles工作树3个纯映射/SRT文件已15测试通过，但尚未接公开导出/真实成片，不计功能进度，接续合同sprint-creation-subtitles.md。
