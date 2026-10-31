# 缓存维护与测试媒体回收

缓存保留模型、下载资产和用户创作结果的原语义，自动回收仅作用于本次pytest确实创建的临时媒体目录，以及媒体渲染器自己新建的临时文件。不会清理`.cache/workspace`、模型、原片、分析证据、账单、人工记录或工作树源码。

## 阻止单次失控写盘

渲染器按可信输出尺寸和帧数估算临时文件预算，最低8MiB、单文件最高2GiB；同一个私有输出目录总量4GiB，磁盘保留2GiB。FFmpeg原生命令带`-fs`，进程另每50ms检查文件/目录/余量，结束后再检查，超限即失败并回收该新输出；FFmpeg因`-fs`零退出不意味着成功。正常帧数/时长/源SHA/解码核验继续执行。

这些是明确的资源上限；超大成片可能需要缩短单段或降低尺寸，页面会显示容量错误。不会把已截断文件登记成完成，不会修改原素材。失败或取消的NUT和连接文件由渲染器自己的finally回收。

## 测试完成即回收

`tests/conftest.py`不会为未使用tmp_path的测试创建目录；已有fixture完成teardown后，验证实际pytest基目录与`.cache`边界，回收可再生音视频。成功测试的媒体回收；失败测试保留小文件，≥1MiB媒体先记大小和前4096字节摘要再回收。JSON/XML/日志/文本和源代码保留，Windows不能独占打开的文件跳过，不跟随符号链接/junction。

需要临时查看测试媒体时，可只对一次命令设置`$env:GC_KEEP_TEST_MEDIA='1'`，结束后移除该环境变量。该开关不解除渲染期容量限制。人工实际QA截图/用户成片不在测试fixture范围，不受这个hook影响。

## 手工清理较旧的测试媒体

默认干跑；只接受已管理的`pytest-runs/<run>/tmp/test_*/...`精确媒体文件，至少24小时，无活跃pytest/FFmpeg，互斥锁和Windows独占删除保护。例子中的文件名需换成实际存在的已结束测试文件：

```powershell
./scripts/reclaim-cache.ps1 -RelativeFile 'pytest-runs/<run>/tmp/test_example0/part-000000.nut'
./scripts/reclaim-cache.ps1 -RelativeFile 'pytest-runs/<run>/tmp/test_example0/part-000000.nut' -Apply
```

审计在该测试目录的`media-reclamation.jsonl`，保留执行前大小/摘要和实际删除结果。路径穿越、链接、工作树、workspace和模型目录拒绝。不要递归删除整个.cache。

## 工作树与备份

活跃源码放`.worktrees/`，不放`.cache/`。主控/串行任务不需要额外工作树，只读代理不创建副本；并行写者最多三个活跃槽。完成集成后保留必要Git提交或最小补丁，再释放已完成工作树，不把整棵项目目录长期当备份。历史目录必须先确认来源、未提交内容及活跃状态，不能仅按名字删除。

事故证据与已释放58.29GiB的精确记录见[缓存事故](../exec-plans/sprint-cache-reclamation.md)。
