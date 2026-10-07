# 多段录像一次准备

把录像清单交给程序，它会在同一项目中逐段抽帧、提取音轨并保存任务。一段坏录像不会让后面的录像白等；明确续跑同一批次时，已经准备好的素材先核对原文件，再直接复用。准备全程在本机进行，不需要API密钥或ASR权重，不调用模型，也不上传图片或预留费用。完成后任务等待另行分析，还不能搜索其中的内容。

## 创建批次

复制[清单示例](../../templates/media-batch-input.example.json)，每段录像填写一个不同的`id`和本地`path`。一批接受1–100段、清单最多1MiB；相对路径以**清单所在文件夹**为起点。不能重复同一路径。中文和空格可以直接填写，文件须为UTF-8，带BOM也可读取。

```json
{
  "schemaVersion": "media-batch-input-v1",
  "items": [
    {"id": "第一场录制", "path": "../GameVideos/session-001.mp4"},
    {"id": "第二场录制", "path": "../GameVideos/session-002.mp4"}
  ]
}
```

在仓库根目录，用项目已有PowerShell 7执行：

```powershell
./scripts/prepare-media-batch.ps1 -Project artifacts/my-project -InputPath templates/my-recordings.json -Config config.example.json -MaxCostCny 5
```

`MaxCostCny`是**每个任务以后分析的上限**，不是整批总额、费用估算或付费授权。这次准备不会扣款或增加预留。`Config`沿用单段准备的schemaVersion 2配置；原模型、提示词、采样和上限随批次保存，续跑不能替换。

开始处理前会在`<项目>/media-batches/<batchId>/`保存原清单、配置、固定任务ID和校验回执。处理过程中终端错误输出给出批次ID和已检查项数；最终标准输出是`media-batch-result-v1`结果。需要中途找回批次，可以查看该目录。

## 同批次继续

修好尚未登记的坏文件、恢复机器环境或取消之后，只传原项目和批次ID：

```powershell
./scripts/prepare-media-batch.ps1 -Project artifacts/my-project -Resume <batch-id>
```

这会重新核对每一项。已准备的任务不重新提取；准备未完成的任务继续使用最初分配的ID。原输入清单或配置文件移走后，续跑仍读取项目中的副本；不要编辑冻结副本或`state.json`。已登记原视频或抽取画面被改动、项目写入失败时，批次停止并保留原任务，不将其当作普通坏录像略过。多个进程不能同时写同批次或同项目。

单个坏视频、媒体工具超时记为失败后继续后面的项；取消则停止剩余项。默认每段3600秒，可用`-TimeoutSeconds 7200`显式加长，包括续跑。它合计检查本段探测、提取和核对已用时间，不能强制中断正在进行的SQLite／文件校验，因此不承诺严格的整个命令墙钟上限。

原计划刚保存、项目数据库尚未创建就中断的批次，当前不能直接续跑（TD013）；保留该目录作依据，恢复环境后重新提交清单。已有任务的批次按原ID恢复，不因状态未及时写入而重复创建。

## 读懂每项结果

| 状态 | 意义与后续 |
| --- | --- |
| `prepared` | 画面和音轨已保存，等待另行分析 |
| `failed` | 本项失败；看`errorCode`，保留任务后明确续跑 |
| `pending` | 本次尚未处理 |
| `cancelled` | 本次被取消，可明确续跑 |
| `coverage_blocked` | 已保存，但请求／上传帧上限不足；没有分析命令，调整配置另起任务 |
| `analysis_started` | 任务已进入模型分析，批次只报告现状，模型任务沿原分析入口处理 |

`verifiedThisInvocation=false`意味着本次停止前没有重新检查该项，其旧状态不能冒充本次验证。`reusedPreparedTasks`计数本次复用的已准备任务；`attempts`为批次准备尝试，实际媒体阶段次数保存在原任务中。`finished`／退出0意味着离线检查完成，可能包含已经开始分析的任务；`partial`／退出2表示有坏素材或覆盖不足。存储／环境问题分别退出5／3，取消退出130。没有输出完整结果时也须保留原批次，不能猜测所有任务成功。

当前存储以内容SHA识别素材，同一字节内容位于不同路径时可能报告素材身份冲突并停止；本入口不会自行合并来源。任务清单可通过`list-tasks.ps1 -Project <项目>`或工作台“查看素材任务”查看。每个可覆盖任务的`result.nextCommand`只是后续`analyze --resume`参数，准备程序不会执行；实际分析须另行具备环境、凭据和相应费用／上传授权。

真实三段开发录像的准备／坏文件修复续跑证据见[本轮交付](../exec-plans/sprint-media-batch-preparation.md)。这些录像是已有开发PV，没有进行新的模型分析或独立人工验收，F006门槛仍未通过。
