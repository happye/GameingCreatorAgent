# ADR-005 工作台运行时源码身份

2026-11-07，采用；实现及完整门禁仍按对应sprint记录。

## 问题与决策

同仓库旧进程也有相同application/apiVersion/repository，启动器会复用它。旧Python的路由表不含新版Studio模块，磁盘JS却已更新，因而可能导入404。不能把修改过的磁盘当作旧进程已重载，也不能为升级自动停止用户旧服务。

选择共享stdlib源码指纹，不选手工capability版本号。服务在create_server时固定实际包根路径及相对源码路径/内容SHA；health只返回固定快照。启动器在仓库/端口mutex内独立选择开发src或便携site-packages，直接执行预期模块算身份，再将真正启动进程的PYTHONPATH指向该checkout，比较version/packageRoot/sha256及原PID/repository条件。旧响应或不匹配的占用端口拒绝复用，提示指定空闲端口，保留旧服务。

指纹仅包内源码/前端文本资产。walk先剪隐藏/cache及symlink/junction目录，读前解析路径仍须在规范化包根内；包根/祖先junction允许，不能顺着包内链接读取用户文件或陷入循环。文件按相对路径排序，长度与内容参加摘要，不依赖mtime。没有新Provider、费用、账本或用户数据写入。

## 边界与验收

这是启动时磁盘快照与兼容性检查，不是签名、恶意进程认证或原子部署。导入与固定快照之间的并发源码替换不保证所有Python对象来自同一版本；本批不引入部署锁框架。原setup/verify工具链检查保持，原启动器仅有环境存在检查，没有删减门禁。

测试须覆盖真实空闲端口启动/同PID复用、旧health/错hash/同hash错checkout拒绝且旧PID仍活、dev与portable布局，以及已启动health在磁盘JS/Py变化后保持快照。真实NTFS外部目录/循环/祖先链接回归必需；链接清理只解除链接自身。两个候选中只实现指纹路线，未保留替代capability实现。
