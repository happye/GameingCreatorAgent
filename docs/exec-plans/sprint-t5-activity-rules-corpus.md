# Sprint T5：TD020 活动规则句式覆盖

**状态（2026-11-01）：已推送 origin/main ba7827d。** 在 `tests/activity_rules_corpus.py` 建立 ≥60 条真实风格语料（多阶段时间、截止到、自…起、全角数字、不少于/至少/≥/≧、禁止/不得/请勿、OCR「秒→杪」），逐条期望写入 `tests/test_activity_rules_corpus.py`。扩展 `application/activity_rules.py`：自…起…至/到、OCR 杪→秒、≧/≦、截止时间标签；仅有截止日、多阶段或延期等无法唯一确定的写法保持字段为空（未识别），不猜测。

## Acceptance

- [x] ≥60 条独立样例语料 + 逐条期望
- [x] 覆盖任务所列句式类别
- [x] 识别不了 → 未识别（字段 None），不猜
- [x] TD020 状态更新

## Verification

```text
pytest tests/test_activity_rules_corpus.py tests/test_activity_rules.py -p no:cacheprovider --basetemp .cache/pt-t5 -q
```

## Non-claims

不用模型做二次核对（需另行许可）；不宣称已覆盖世间全部活动文案；非常规营销字段名仍可能未识别。
