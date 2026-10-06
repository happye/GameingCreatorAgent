# 填写、保存和重新读取同画面对照记录

## 在本机填写

打开 `artifacts/detail-pilot-review-20261006/review-editor.html`。页面自带原六张画面、每组查询和旧版描述，旧意见可展开查看。它使用本地文件，不发模型请求或费用。记录页和日常检索工作台是独立入口。

新版有对应真实结果后，可分别选择：物品是否仍被误认成人物、标出的切镜是否真实、原正确描述是否保留、同一查询的片段是否可用。未核对的维度保持“未核对”，无需为了保存而全部选完。物品问题选择“仍有误认”表示发现错误；其他三个问题按各自文字选择，不合成整体通过分数。

填写判断前登记日期、填写人，并写明画面依据；也可选择本组新版的具体对象。当前两个新版请求尚未执行，判断与说明控件禁填；可以保存空记录和登记信息，新版结论仍为空。原三个描述确认与一个纠错无需重复标注。

点击“下载当前记录”，浏览器保存 `human-review-record.json`。下次用“载入已有记录”选择该文件，可继续填写；修改后须再次下载保存。页面会核对候选、两版结果和原画面等来源，不同结果、重复字段、错误对象或无结果的判断会被拒绝，原表单保持。浏览器里的载入不自动写回模型结果或检索标签。

## 生成记录页

按[对照页指南](./detail-pilot-comparison-guide.md)的原命令，额外添加 `--review-editor`，并换一个不存在的新输出目录。输出原三个对照文件和 `review-editor.html`。`--review-editor`须配合`--output-dir`，不能与`--dry-run`或`--review-file`同时使用。新版结果发布后重新生成记录页，旧页保留原来的来源快照。

## 核验并归档下载的记录

沿用同一命令的project/proposal/hash/legacy-report/feedback参数，将模式替换为：

```powershell
--review-file 'G:/Tools/ChatGPTRepo/GameingCreatorAgent/artifacts/my-review/human-review-record.json' --dry-run
```

这里的文件路径须指向实际保存的绝对路径。此模式重新读取原数据库、精确模型结果、注册图片、报告和反馈，再核对记录来源；成功仅表示来源与格式有效，不表示内容已通过。日期、填写人与判断须为本人实际输入，未填写保持null。

需要保存时，将`--dry-run`替换为`--output-dir 'G:/Tools/ChatGPTRepo/GameingCreatorAgent/artifacts/my-reviewed-bundle'`，目录须不存在且不包含源资料。生成五个文件：

| 文件 | 用途 |
| --- | --- |
| human-review-record.json | 规范化人工记录，可再载入和核验 |
| review-input.json | 原输入字节，保留原格式及来源摘要 |
| comparison.json | 本次核对的完整同画面对照快照 |
| review-summary.html | 可直接打开的原图与四维判断汇总 |
| review-provenance.json | 输入、记录和对照资料摘要与空质量门槛 |

不会覆盖原记录、图片、模型结果或费用账本。再次保存使用新目录；来源发生变化后，旧记录不会自动挂到新结果。

## 已验证的范围

原两组真实资料的空记录已完成保存、再次读取、桌面1366／手机390下载和载入往返；原六图字节、尺寸和源时间保持，缺新版结果的控件禁填，错误载入保留原表单。填写非空判断的交互使用工程fixture验证，真实新判断仍为零。记录来源验证与工程测试不证明模型理解改善，也不代替[独立检索人工验收](./human-acceptance-guide.md)。
