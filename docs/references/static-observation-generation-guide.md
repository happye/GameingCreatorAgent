# 从一张登记画面生成静态观察草案

2026-10-24。离线工程已通过正式检查与独立评估，结果见[交付报告](../exec-plans/report-2026-10-24-static-observation-generation.md)。后续已按具体新¥0.50许可唯一执行原28.5秒登记帧的真实试验，HTTP200、发布／另进程查询及本地恢复通过，估算¥0.001492，视觉仍未验证；见[试验报告](../exec-plans/report-2026-10-24-static-observation-pilot.md)。该一次许可已用尽，不允许按剩余金额追加。

这个入口补上已有[静态导入与检索](static-observation-guide.md)之前的自动生成环节。可以选一张Completed录像中已登记的画面，生成主体、衣物和持有物的静态草案，再用已有typed条件查询。它不生成动作事件，不剪视频；模型声明仍需另行核验，不能当作人类已确认的画面事实。

## 先冻结画面，不调用模型

`--project`指已有分析项目目录，里面有`timeline.sqlite3`，不是这个源码仓库的目录。其他字段的作用：

| 字段 | 填什么／为什么 |
| --- | --- |
| `--run` | 明确选择的Completed版本ID；不能取尚有覆盖缺口的旧run |
| `--collection` | 本次独立静态集合的ID；发布后相同集合不能改成另一份内容 |
| `--evidence` | 此run已登记的图片证据ID；程序会核对图片字节与源时间，不接受任意图片路径冒充 |
| `--output` | 已存在目录里的新proposal文件路径；只创建一次，同内容可复用，异内容不覆盖 |

以下为占位示例，先替换为实际已有记录；无需重新标注：

```powershell
. ./scripts/env.ps1
& ./.venv/Scripts/python.exe -B -m gamingcreator prepare-static-observation-generation `
  --project '<已有分析项目目录>' --run '<Completed版本ID>' `
  --collection '<新集合ID>' --evidence '<已登记图片证据ID>' `
  --output '<已存在目录>\proposal.json'
```

prepare只读本地来源并保存冻结提案，不建立人类授权、不预留预算、不发图。提案固定图片hash和源时间、项目／数据库／账本位置、run/collection、模型／prompt/schema/profile/词表／参数和价格身份。重复提案字节一致时返回unchanged。

## 真实执行需要具体的新授权

已有视频、旧分析余额、旧精分析授权或开发模型许可都不授权此处发图。需要真实单帧试验时，协作者先列出具体proposal、图片／hash、接口目的地、参数、价格快照、一次请求／一张图及新增金额上限；用户明确允许后再保存对应授权记录，不要求用户手写合同JSON。测试里的授权不能用于真实素材。

授权限定明确proposal和项目，含独立authorizationId、内容hash、有限正CNY上限、请求数1／图片数1以及显式allowModel声明。校验授权文件只是校验本地声明，不是密码学证明真人同意。

```powershell
# 仅在上述具体授权已完成后使用；此步骤可能产生真实费用。
& ./.venv/Scripts/python.exe -B -m gamingcreator dispatch-static-observation-generation `
  --project '<同一个分析项目目录>' --proposal '<冻结提案路径>' `
  --authorization '<该提案的真实授权路径>'
```

主体和部件关系必须在当前帧内明确。棕色短裤和白色外套不应合成棕色外套；左右手的两个物品不应拼成同一持有物。条件检索核对的是保存声明内部的同主体／同部件关系，视觉准确性仍未知。

## 中断后只恢复本地工作

```powershell
& ./.venv/Scripts/python.exe -B -m gamingcreator resume-static-observation-generation `
  --project '<同一个分析项目目录>' --proposal '<原冻结提案路径>' `
  --authorization '<原授权路径>'
```

resume不构造发送任务、不重新发图。结果已可靠保存时，仅补本地结算／发布；只留下planned或无法确认响应时，保留未知金额占用、请求和图片次数。不要通过换collection、输出目录、复制授权、删除账本或改同一authorizationId的内容重置额度。不同新授权是独立许可，不释放原来的unknown，也不授权重发同一个proposal。

账本固定在分析项目的`.static-observation-generation/ledger`。账本或尝试文件损坏时停止并保留原件；版本、来源、图片或源时钟漂移也拒绝。先核恢复所需的原版本／来源，不能用新提案覆盖旧尝试。

| 状态 | 表示什么 |
| --- | --- |
| `published` | 草案已写入不可变静态集合，可另进程查询；不代表模型看对 |
| `no_observations` | 合法空主体，仍保留真实单帧记录；没有伪造主体 |
| `unknown` | 发送或结果状态不明，保留占用，不能自动重试 |
| `failed`／`cancelled` | 此次尝试结束，原记录和费用未知保留，不自动重试 |
| `nothing_to_resume` | 没有既有尝试，恢复不会新建一次调用 |

`providerRequestsSent`只数本次操作，不是历史总次数；resume显示0不表示以前没发过。known费用按实际估价记录，超授权上限不截断；unknown不是零费用。程序保存typed结果、调用metadata、响应hash／大小和白名单诊断，禁止落盘原视觉响应或任意HTTP正文。

查询沿用`search-static-observations --project ... --run ... --collection ... --input ...`，参见原[使用指南](static-observation-guide.md)。F006/F009/F010仍未通过，真实Provider接受性、外观准确性及独立人评不由工程测试替代；本轮不需要重做已有标注。
