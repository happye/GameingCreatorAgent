# 描述反馈原报告核验 Worker

2026-10-06；owner detail_cost_history；沿用`.worktrees/detail-feedback` / `codex/detail-feedback`，基于09dae6f。仅独占新增application/detail_description_report.py、tests/test_detail_description_report.py和本文；旧DTO三文件冻结，root拥有reader/UI及公共文档，其他编辑不回写。

## 用户效果、接口与自审

进一步确认人工接受/拒绝对应原报告里的同一个候选、已完成请求、精确描述和目标，阻止格式合法但借用另一候选或被改动payload的反馈。反馈仍只针对描述，报告其他字段保留且不解读为属性或U10验收，不改旧输出。

`validate_description_report(feedback: DescriptionFeedback, report_text: str) -> None`纯函数，成功无返回，缺失/损坏/冲突均ValueError。最多1MiB UTF-8和128报告case，拒绝所有层次重复JSON字段、重复case和payload重复shot/actor；只核对必要身份和目标结构，不重新解码CandidateDetail。

先只读真实pilot-report确认schema actor-detail-pilot-report-v1、44,429字节，两attempt.status实际是小写completed，payloadJson是UTF-8 JSON字符串。逐反馈case核验报告SHA、同caseId唯一、run/event/request完全一致、completed attempt同request/payloadHash、payloadJson原文本UTF-8 SHA一致、payload run/event一致、shot/actor目标存在且不重复。不canonicalize payload再算hash，不依赖报告其他字段猜质量通过。

下一步补身份置换、假hash、payload改动、目标缺失与重复字段等反例，验证真实旧报告/反馈通过，定向Ruff/mypy/pytest后提交新三文件供root只读reader调用。无I/O、Provider、DB或费用请求。

## 已实现、验证和已汇报

现在合法反馈还必须获得原报告逐条核验：相同caseId但借用另一候选、未完成attempt、假payload hash、描述原文改动、目标不存在或只藏在metadata字段中，都不能当作真实人工结论。报告SHA正确也不足以通过；报告与payload里的候选身份、实际原文本hash和明确目标都要一致。相同actor ID在不同shot中仍合法，目标按两段身份区分；shot-1/left等通用合法ID支持。

新增**76项**回归，覆盖成功、保留其他报告字段但不扩大验收、错schema/缺必要字段/非法类型、同caseId换候选、重复case、attempt状态大小写和未完成、request/payload hash错、payload原文/空白改动、重新绑定全部SHA后仍拒绝外来run/event、缺/重复/错位shot/actor目标、目标只在metadata存在、转义后重复JSON字段、嵌套payload重复字段、128/129case、1MiB精确边界、非法Unicode/JSON/非有限数字/过深输入、未类型化feedback以及零I/O。结构反例按需重算报告和payload SHA，确保真正检查内层防线，而非只命中外层SHA失配。

隔离环境命令均先env.ps1、root .venv Python -B、own src/cache/basetemp：

```powershell
G:\Tools\ChatGPTRepo\GameingCreatorAgent\.venv\Scripts\python.exe -B -m pytest tests/test_detail_description_report.py tests/test_detail_description_feedback.py tests/test_architecture.py --basetemp=.cache/feedback-runs/report-first -o cache_dir=.cache/feedback-pytest-cache --tb=short -W error
```

联合**190 passed / 0 skip，0.45s**，新报告测试独立**76 passed，0.21s**，均-W error；Ruff格式/lint及新Application模块mypy通过。首轮mypy发现两个loop复用变量名带来的Optional收窄冲突，改用matched_case后通过；没有放松业务验证。只读同伴源审无阻断缺口，未声称其运行了tests。

真实旧ignored报告与反馈按read_bytes().decode('utf-8')只读传入校验，**2 cases / 4明确描述目标全部通过**，没有Provider请求。源human-feedback SHA `3e905114975a5a566c1cfe8af4932cda593013d7f357a1fdce7d002b507fe5aa`和原pilot-report SHA `367bbc2eb270fa8c859962804392decd6c4494af4b05abc4adef3d17385ccfec`前后一致。root reader必须保留原字节换行，不能read_text默认换行规范化后再对原报告SHA。

已向root报告用户得到的保护、原报告实际验证、工程反例和剩余范围。下一步root合入此新增三文件，在reader里调用校验，更新HTTP fixtures并验证页面三接受/一拒绝和损坏来源报错，再执行完整verify及公共交接。该函数不完整解码CandidateDetail；最终typed detail+实际payload projection仍由既有模块守住，不改变模型结果、matcher、属性/U10验收或费用。本worker提交后冻结，旧DTO三文件与root代码均未修改。
