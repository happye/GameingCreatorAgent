# Sprint T13：清理 src/gamingcreator 下 __pycache__

**状态（2026-11-01）：已推送 docs 4e28c31**

## 目标

清理未加 -B 运行留下的 src/gamingcreator/**/__pycache__；确认 gitignore；只删 pyc／pycache，不动 .cache 或其他树。

## 核查

- .gitignore 已有：
  - __pycache__/
  - *.py[cod]
- git ls-files src/gamingcreator：**0** 条 __pycache__／.pyc／.pyo 被跟踪（无需 git rm --cached）。
- git check-ignore：样例路径命中 __pycache__/ 规则。

## 清理结果（本机，2026-11-01）

删除 **6** 个目录、内含 **106** 个 .pyc（含 3.12／3.13 混杂）：

- src/gamingcreator/__pycache__
- src/gamingcreator/application/__pycache__
- src/gamingcreator/cli/__pycache__
- src/gamingcreator/domain/__pycache__
- src/gamingcreator/infrastructure/__pycache__
- src/gamingcreator/ui/__pycache__

清理后 
glob('*.pyc')／__pycache__ 均为 0。工作区无相关 diff（忽略项，未入库）。未触碰 .cache、.codex/agents/*.toml、测试或其他包路径。

## 建议

日常继续 . ./scripts/env.ps1（含 PYTHONDONTWRITEBYTECODE=1）并 python -B；verify／pytest 亦应避免往源码树写 pyc。

## Acceptance

- [x] gitignore 已确认覆盖
- [x] 仅删除 src/gamingcreator 下 pycache／pyc；无跟踪项需 untrack
- [x] 文档记录发现与删除数量
- [x] T13 ✅ 推送

## Verification

`	ext
# 应无输出
Get-ChildItem -Recurse src/gamingcreator -Filter __pycache__ -Directory
Get-ChildItem -Recurse src/gamingcreator -Filter *.pyc -File
git ls-files 'src/gamingcreator/**/__pycache__' 'src/gamingcreator/**/*.pyc'
`
