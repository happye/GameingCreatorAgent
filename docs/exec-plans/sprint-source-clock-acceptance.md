# 特殊源时钟的验收回看资格与浏览器验证

2026-10-23，Phase 0／TD006。当前不是已证实的浏览器错播：规范源时间已按PTS减asset origin实现，原片参考对非零origin或不同流起点保守禁用自动取时；候选评审只检查origin，资格不一致。交付是将候选评审对未经联调时钟的自动回看条件对齐，并用真实短合成片验证两入口的安全手动退化及零起点自动播放。保留未来时钟映射功能缺口，不猜补偿公式，不用测试通过宣称人评准确。

Codex合同／测试／公共docs／Git；原生DSH唯一写`application/benchmark_review.py`、`tests/test_benchmark_review.py`及新`tests/test_benchmark_source_clock_browser.py`。已有Luna/high定位完成；唯一Sol/high评估源时钟／人工判断身份边界。不得反向导入benchmark_reference_review形成循环；资格保持现有bool字段，原API／冻结／评分／时间区间不变，无JS新功能或代理转码。

测试要求：FFmpeg生成零起点、真实非零PTS和异步A/V起点的短片，probe证明fixture时钟确实不同；由真实构造器产生context再用项目Chromium检查自动取时／播放按钮与原片链接、手动区间保存，至少保留零起点seek／末尾暂停对照。不得只手改context标志充当真实构造器验证。所有内容为合成夹具，不用用户视频／标注，不进行模型调用，不新增真实人评。

同目录workspace `f4395711-a8fb-49a3-ad95-7305ce9ea1e8`；新task `gamingcreator-source-clock-20261023`，session `codex-e56e7df0-ed06-4054-8602-833e984bb533`。基线main `958f70c`（包含此前文档与TD014，已正常推送）。上轮task已交付，不重投。主控实现后绑定真实testPlan唯一运行pytest；DSH可在新忽略目录做有界合成FFmpeg／probe准备，不跑pytest／verify，不改依赖／运行时。

已交付：候选页保守资格已对齐，两真实构造器／三类真实probe时钟／Chromium手动与自动路径验证通过。初轮64通过后，唯一评估发现零起点断言不能排除自然播完，原对话定向补强事件证据；最终64通过、0失败／错误／跳过，Ruff／格式／mypy与唯一Sol/high R1–R5 PASS。详见[交付报告](report-2026-10-23-source-clock-acceptance.md)。

最终rev5合同eba7b74d3ceabd1c49317d32704880d5842a0d22bb3a2ba61b084281728ab6ac，run 08cebe6d-c2f4-421b-a9d7-55bd15985f90／55ff0da7-501c-46d5-b9a1-9149658de890；receipt CLI在文档／Git变化前重读有效，摘要与实际测试文件绑定于artifacts/dsh-source-clock-20261023/validated-source.json。rev4参数脚本索引错误未运行，rev5先核完整argv再执行，不重投模型请求。两逻辑请求均COMPLETED。

已向用户汇报：现在正常录像可可靠验证自动回看，特殊时钟保留手动核对及已填资料；此为保守资格一致性，不是已证实错播修复，也未实现非零自动映射。F006/F009/F010false、长钟馗三缺口、费用及标注不变，无新增用户操作要求。下一TD009独立静态观察离线切片已有Astra/low只读设计，待新合同及同workspace新对话实施；自动生成和真实质量不在本轮结论内。
