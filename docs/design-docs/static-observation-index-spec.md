# 独立静态观察的离线导入与检索

2026-10-23设计，2026-10-24离线切片已交付；202通过／1符号链接权限skip，静态检查与唯一评估PASS，见[报告](../exec-plans/report-2026-10-24-static-observation-index.md)。来源是已有注册帧上的结构化观察声明；不把它称为自动识别，也不要求用户重做标注。旧候选精分析仍绑定SemanticEvent，此处独立保存没有动作事件的静态画面，不更改旧schema与V6动作保护。

## 有限交付

提供显式生产CLI `import-static-observations`与`search-static-observations`。导入只接受一个明确Completed run及精确collectionId的版本化本地声明包；搜索明确同run／collection与typed条件。观察有独立`kind=static_appearance`及observationId，返回同帧主体、部件、属性、注册帧路径／hash／源微秒、原片路径和声明provenance。结果不进入默认动作搜索、选片篮、benchmark或自动评分。

Domain新类型纯数据；Application负责身份核对与纯条件匹配、Store port；Infrastructure负责严格codec与项目本地独立SQLite；CLI装配只读原TimelineStore及新Store。旧timeline.sqlite3不迁移、不写入，新库固定在所选project内`static-observations.sqlite3`。新库没有预算、旧attempt或费用结算职责。

实现保留pipelineHash为可选输入，提供时精验；configHash与pipelineVersion必需。主查询格式为static-observation-query-v1，并严格兼容原typed manifest。来源partGroup只存声明元数据，查询partGroup为局部变量；同part冲突跨来源组检查。所有SQLite伴随文件含-journal在连接前检查链接；不承诺抵御连接后外部恶意替换路径。

## 声明与身份

新`static-observation-import-v1`包以一个不可变collection绑定runId、mediaId／source SHA、configHash与pipelineVersion。带有非空来源说明和来源payload SHA等声明provenance；这些仅说明导入来源，不能被视为提供方已核实元数据或账单。不得将来源费用记零；本地导入／搜索的新增模型请求数为0，visualVerified／humanLabels／qualityGate恒null。

一包至多1MiB、128条观察；每条只引用一个已注册图像，最多8主体／每主体16属性。包不接受任意文件路径、模型自算时间、原事件或candidate身份；evidenceId／hash／sourceUs须与当前Completed timeline精确一致，范围从注册时钟推导为`[t,t+1)`。观察ID从版本化collection、run／media、注册帧及局部观察ID确定，不能伪造原动作身份。

每collection一次原子发布整个包，重复同canonical包为无变化复用；同collection不同内容明确冲突，追加或改版使用新collectionId，不覆盖旧声明。SQLite只存此新能力，记录canonical payload／hash及必要观察行；重开须校验版本、payload和查询投影一致，损坏不可当空结果。整个发布事务成功或全不发布；同身份并发导入不重复，错误释放自己的资源。

## 匹配与保护

复用冻结静态词表、AttributeKind／Status、AttributeConstraint／QueryConstraint和显式part_group语义，不新增词表或用字符串交集猜属性。首版仅hair_color、clothing_color、clothing_shape、held_shape、held_class；拒action、effect及environment条件／属性，unknown主体不满足条件。

同一个观察帧、同一个actor须支持所有actor_all；同part_group须在同part上。uncertain、缺失、矛盾或unknown不能成为完整支持，不把不同主体、部件、帧或collection拼接。匹配结果只说明导入声明支持这些条件，真实外观准确性未知；稳定按源时间／观察ID／主体ID返回，不引入embedding、自由文本解释或新模型初始化。

## 验收与授权

真实SQLite构造Completed run且events为空，注册合成图像，通过生产CLI导入；另一进程重开搜索命中并返回静态类型及精确证据。验证同帧静态可用、单帧动作在旧V6仍拒绝、新入口不收动作、同人物／同部件AND与未知／矛盾边界。真实存储验证重复／并发／冲突／事务回滚、未知schema、损坏payload、缺图／hash／身份／时钟漂移和非Completed拒绝；旧DB与冻结prompt／费用／标注摘要不变。

只在新合成测试目录操作，无真实录像分析、旧任务重跑、上传、模型下载或预算变化。DSH开发调用依用户协作授权单列；真实静态观察生成或将来接Provider仍需具体录像与新增费用提案。F006/F009/F010保持false，真实素材尚无新增静态覆盖。UI混排、自动生成、跨帧身份与通用自然语言条件均留后续，不扩大本切片。
