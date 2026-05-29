# 12-00 Gap Downstream Reference

文档版本：v1.0  
更新日期：2026-05-29  
依据文档：`12_gap_decisions_review.md`  
适用项目大版本：v1

## 1. 用途

本文保存从 `12_gap_decisions_review.md` 拆出的下游细化参考项。

这些项目不再视为 `00_layers.md`、`01-01-FR-reference.md` 或 `02_domain_core.md` 的缺口，但需要在对应下游设计中继续细化。

## 2. 本轮仍需下游细化的设计项

1. D-002/D-003/D-004：响应信封、错误码格式和 SSE 认证机制应由 `04_api_contracts.md` 固化。
2. D-007：手动论文补充的 API 载体、文件限制、批量上传和进度/失败项结构应由 API/Data 设计补齐。
3. D-008：关系库、向量库和图谱同步的 outbox/sync item、补偿任务和检索过滤规则应由 Data/Application 设计补齐。
4. D-009：文件与导出生命周期的保留时长、签名 URL 有效期、对象 key 和清理任务应由 Data/Ops/API 设计补齐。
5. D-011：Review P2 历史版本的差异、回退、标签、注释和接口交互应在启动 FR-036 时补齐。

## 3. 变更记录

| 版本 | 日期 | 变更内容 | 变更人 |
| --- | --- | --- | --- |
| v1.0 | 2026-05-29 | 从 `12_gap_decisions_review.md` 拆出下游细化参考项 | Codex |
