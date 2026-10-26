# A01至A03精确基线证据

文档版本：v1.0
更新日期：2026-10-21

本目录记录文档任务的字节基线和核验结果，不是应用代码或测试环境。审查范围与限制见[工作单](../../a01_a03_design_closure_2026-10-21.md)。

- [manifest.json](manifest.json)：输入/输出文件SHA-256、字节数、HEAD对象及初始工作区；标记Agent限定核对、人类审核未记录。
- [input.patch](input.patch)：相对指定HEAD的任务开始时已有差异，含当时未跟踪清单。
- [output.patch](output.patch)：相对同一HEAD的任务结束文档内容，包含本轮新文档；不是只包含本轮修改的差异。
- [validation.md](validation.md)：文档检查、摘要与重建核验结果。

补丁是审查证据，不应应用到当前脏工作树。复原时使用空临时目录，逐文件从manifest指定HEAD读取被记录的原内容，再分别应用input或output补丁；两者是同一HEAD的独立快照，不依次叠加。新文件由补丁添加，已存在文件依Git对象和补丁恢复；核验每个文件SHA-256。

manifest及本目录文件不纳入其自身快照，避免自引用摘要；manifest单独记录两个patch的摘要。当前工作单等交付文件在输出清单中，但只链接本目录，不内嵌manifest摘要。后续提交可将本目录和对应文档一同固定在Git历史；本轮未创建提交。

机器兼容比较点为manifest指定HEAD的contracts/p0.openapi.json及其SHA-256；本轮未改该JSON。可以通过`git show <manifest中的head>:contracts/p0.openapi.json`提取旧内容到临时文件，再用04-03命令比较未来新版本。不能将当前JSON复制为旧文件再自比，不能把Agent的局部检查升级成人类批准或完整HTTP验收。
