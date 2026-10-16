# 或许有用：前端展示素材与有效验收场景

版本：v1.0；日期：2026-10-16；项目大版本：v1。

这是非运行路径中的候选档案，不是新前端工程，也不是安全认证。没有 package、路由、Provider、API、页面、旧 mock 或 E2E 执行器。仅保存少量脱离旧模型仍可理解的片段；新项目可以全部舍弃。

## 提取结果

| 审查项 | 来源 | 实际留下的内容 | 明确舍弃 |
| --- | --- | --- | --- |
| F-X01 | `frontend/src/utils/format.ts:1` | `format.mjs` 日期格式函数；改为带年份、显式时区，空值/非法日期显示未知 | classNames 样板、Blob 下载、SSE、所有旧接口 |
| F-X02 | `frontend/src/components/Alert.tsx` | `display-fragments.html` 中图标＋文本布局；图标不参与读屏，普通提示采用 status | React/lucide 依赖、业务错误等级判断、自动文本插值 |
| F-X03 | `frontend/src/pages/SettingsPage.tsx:523` | HTML 中标题、说明、操作槽、空态外观 | 整个设置页、配置加载保存、硬编码示例配置、事件回调 |
| F-X04 | `frontend/components/InspectorPanel/InspectorPanel.tsx:78` | `format.mjs` 耗时片段；增加非有限值和负值保护，秒数向下取整 | 建议/依赖卡片不提取：价值有限且需引入新展示 DTO；前缀协议、七依赖键、阶段历史、诊断编排全部舍弃 |
| F-X05 | `frontend/src/styles.css` | `display-material.css` 调色变量、提示框、标题行、空态；作用域限定在 `.ui-material` | 全局 reset、工作台/状态类、页面布局、未使用表单/按钮样式 |
| T-X01 | `frontend/src/test/render.tsx` | 不提取；无旧路由或 Provider 的新档案不需要渲染辅助 | 原测试壳及其依赖 |
| T-R01～11 / F-R01～11 | 独立审查报告第 6、7 节 | `acceptance-scenarios.md` 留存有效规则及判定结果 | 旧协议断言、允许 200 的权限断言、无效拦截与仅 body 可见的测试 |

来源工作树字节摘要见 `sources.json`。基础提交仅供定位；工作树可能包含未提交修改，不能用基础提交替代提取时的字节摘要。完整源文件未复制到档案。

## 修正与边界

- 格式函数只接受含 Z 或 UTC 偏移的 ISO 时间戳；默认显示 Asia/Shanghai，可由调用者明确指定其他 IANA 时区。非法时区抛出 RangeError，不能默默改用机器时区。不承担服务端日期 Schema 校验。
- 日期格式依赖 Node/浏览器原生 Intl 与中文 ICU；不同 ICU 版本的分隔符可能不同。耗时按完整秒展示，未实现计时器、状态推导或新运行契约。
- HTML 是固定示例，没有插值和业务数据，不能证明动态消息已经脱敏；以后采用时必须使用文本节点，并由业务层决定受控严重性。长文本 CSS 使用 overflow-wrap，不截断诊断内容。
- CSS 仅为历史视觉素材，不是通过视觉或无障碍验收的新组件。没有启动浏览器、安装依赖或执行旧应用。

## 离线验证

在仓库根目录运行：

```sh
node --test archive/maybe_useful/ui_materials/format.test.mjs
```

覆盖非法/缺失/无时区/不存在日期、明确时区、跨年、闰日、非法时区、非有限与分数耗时。2026-10-16 实际运行：3 项测试通过，0 项失败。仅此测试可离线执行，验收场景文档不声称已经实现或通过。
