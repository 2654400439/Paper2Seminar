---
name: tikz-module-diagram-layout
description: Use this skill when generating, revising, or validating TikZ module diagrams, system architecture diagrams, pipelines, attack chains, attribution diagrams, matrix/card summaries, or flowcharts, especially when the diagram contains Chinese text, long English terms, arrow labels, annotations, 4+ modules, or must be exported as a high-quality PNG/PDF without node, arrow, label, or text overlap.
---

# TikZ 模块图防重叠 Skill

目标：根据论文、笔记、PPT 内容或结构化说明生成可编译、可检查、适合放入 PPT/报告的 TikZ 图。优先保证模块、箭头、文字、标签、注释互不重叠；其次保证图像紧凑、清晰、美观。

## 工作流

1. **先做容量预算，再写 TikZ**。不要边写节点边让 TikZ 自动撑开布局。
2. **选择布局类型**：单行流程、双行蛇形、上下分层、左右对比、发散/汇聚、矩阵/表格、等宽卡片。
3. **预留独立通道**：节点通道、箭头通道、箭头标签通道、注释通道不要共用同一条窄空间。
4. **生成 standalone `.tex`**，使用固定节点宽度、高度、内边距、箭头样式和标签样式。
5. **必须编译和看图**：用 `xelatex` 编译，转 PNG 后肉眼检查。发现重叠就改布局，不只改字号。
6. **交付 `.tex`、`.pdf`、`.png`**。保留编译日志，便于追踪 overfull 或库缺失问题。

## 生成前容量预算

在动手写代码前，先内部完成这张表：

```text
节点数：
最长节点文本：
箭头数：
箭头标签数：
注释数：
是否有分组框/虚线框：
是否有矩阵/表格/卡片：
推荐布局：
预计宽高比：
主要重叠风险：
```

PPT 16:9 中，TikZ 主图有效区域按约 `12.5cm x 6.5cm` 估算。宽高比尽量不超过 `5.5:1`；超过时改双行、分层或卡片。

### 单行流程容量

```text
总宽度 = 节点宽度之和 + 箭头间距之和
```

| 节点数 | 推荐节点 `text width` | 推荐间距 | 单行适配性 |
|---:|---:|---:|---|
| 3 | 2.8-3.3cm | 0.9-1.2cm | 适合 |
| 4 | 2.4-2.9cm | 0.75-1.0cm | 勉强适合 |
| 5 | 2.0-2.35cm | 0.55-0.75cm | 只适合短词；优先双行 |
| 6+ | 不建议 | 不建议 | 改蛇形、分层或矩阵 |

规则：如果节点数 `>=5`，或任一节点超过 6 个中文字符 / 12 个英文字符，优先不要用单行流程。

### 文本宽度估算

所有非短词节点都必须设置 `text width`，不能只设置 `minimum width`。

```text
中文 text width ≈ 最长行中文字符数 x 0.32cm
英文 text width ≈ 最长行英文字符数 x 0.17cm
节点实际宽度 ≈ text width + 0.35cm
```

| 文本类型 | 推荐 `text width` | 推荐 `minimum height` |
|---|---:|---:|
| 2-4 个中文短词 | 1.6-2.0cm | 0.75cm |
| 5-8 个中文或中英混排 | 2.2-2.8cm | 0.9cm |
| 两到三行解释性短句 | 3.0-3.8cm | 1.1-1.5cm |
| 路径名、错误签名、长英文术语 | 3.2-4.6cm | 1.0-1.6cm |

## 布局选择

### 单行流程

适合 3-4 个短阶段、箭头标签少的流程。

要求：
- 每个节点设置 `text width`。
- 无标签箭头间距不少于 `0.65cm`。
- 有标签箭头间距不少于 `1.0cm`。
- 宽高比超过 `5.5:1` 时改双行。

### 双行蛇形

适合 5-7 个流程节点。优点是宽度明显下降，且第二行可容纳回流逻辑。

要求：
- 两行之间至少 `0.9cm`。
- 转折箭头用 `(a.south) -- (b.north)` 或 `|-`，不要穿过节点中心。
- 第二行的流向可以从右到左，但箭头方向必须清楚。

### 上下分层

适合“输入/处理/输出”、“观测/分析/结论”、“数据层/模型层/评估层”。

要求：
- 同层节点高度一致。
- 层间距不少于 `1.0cm`。
- 层标题放在分组框外侧，不要压住节点。

### 左右对比

适合“传统方法 vs 新方法”、“压缩前 vs 压缩后”、“风险来源 vs 缓解机制”。

要求：
- 左右区块之间至少 `1.2cm` 空白。
- 对应项保持同一 y 坐标。
- 对比箭头标签放在空白带中间，使用白底小字。

### 发散/汇聚

适合一个来源连接多个分支，或多个证据汇到结论。

要求：
- 分支目标之间垂直间距不少于 `0.95cm`。
- 多条边汇聚到同一目标时，尽量不要每条边都带标签。
- 如果必须标注，把标签放在线束外侧，或把结论写进目标节点。
- 汇聚边可以连接到目标框不同高度：`(target.west |- source.east)`。

### 矩阵/表格/等宽卡片

适合分类比较、指标分组、实验条件、能力清单。

要求：
- 表格/卡片使用固定列宽和行高。
- 每个格子设置 `text width`。
- 5 列以上且每列长句较多时，不要硬做紧凑表格，改等宽卡片。
- 底部说明单独放在卡片下方 `6-8mm`，不要放在表格内部。

## TikZ 基础模板

优先使用 standalone，中文内容用 `ctex`。

```latex
\documentclass[tikz,border=8pt]{standalone}
\usepackage{ctex}
\usetikzlibrary{arrows.meta,positioning,fit,calc,shapes.geometric}
\begin{document}
\begin{tikzpicture}[
  font=\small,
  node distance=8mm and 10mm,
  box/.style={
    rounded corners=2pt, draw=blue!65, fill=blue!8, very thick,
    align=center, text width=2.6cm, minimum height=0.95cm,
    inner xsep=3pt, inner ysep=3pt
  },
  resultbox/.style={
    rounded corners=2pt, draw=green!45!black, fill=green!8, very thick,
    align=center, text width=2.8cm, minimum height=1.0cm,
    inner xsep=3pt, inner ysep=3pt
  },
  edge/.style={-{Stealth[length=2.5mm]}, thick, shorten >=2pt, shorten <=2pt},
  elabel/.style={font=\scriptsize, align=center, fill=white, inner sep=1.2pt, midway, above=2pt},
  note/.style={font=\scriptsize, align=center, text=gray!75}
]
% nodes and edges here
\end{tikzpicture}
\end{document}
```

## 节点规则

- 对所有模块节点设置 `align=center`、`text width`、`minimum height`、`inner xsep`、`inner ysep`。
- 主节点字体一般用 `\small`；卡片内容多时可以局部用 `\scriptsize`，不要先靠缩小字号解决布局问题。
- 长英文术语主动换行，不要让 TikZ 自动断词。
- 代码、错误签名、配置键、路径名用 `\texttt{}`，并转义 `_` 为 `\_`。
- 不要使用 TikZ 内置键作为样式名，例如 `out`、`in`、`to`。用 `resultbox`、`outbox`、`riskbox`、`decisionbox`。
- 节点颜色用于表达语义：普通流程蓝/灰，风险红，机制橙，结果绿。不要让颜色承担布局功能。

## 箭头与标签规则

- 箭头从节点边界出入：用 `(a.east) -- (b.west)`、`(a.south) |- (b.west)`，不要从中心穿过。
- 所有箭头使用 `shorten >=2pt, shorten <=2pt`，避免箭头头部贴到边框。
- 短标签用 `node[elabel] {text}`。
- 长标签拆成两行，或写进节点，不要贴在箭头上。
- 反馈箭头走外侧，用 `bend left/right` 或 `|-`，不要穿过主流程。
- 多条边汇聚时，优先删除边标签，把机制或数值写进源/目标节点。

安全写法：

```latex
\draw[edge] (a.east) -- node[elabel, pos=0.5] {extract} (b.west);
\draw[edge] (c.south) |- node[elabel, pos=0.75] {feedback} (a.west);
\draw[edge] (src.east) -- (dst.west |- src.east);
```

## 注释与分组框规则

- 注释必须有独立通道，距离最近节点至少 `6mm`。
- 不要用未验证的绝对坐标放注释。
- 推荐用锚点计算注释位置：

```latex
\node[note] at ($(a.south)!0.5!(b.south)+(0,-8mm)$)
  {short note};
```

- 凡使用 `$()` 坐标计算，必须加载 `calc`。
- 对插值坐标不要使用 `right=... of $(a)!0.5!(b)$`；TikZ 会把它当零宽点，不能为新节点预留空间。改用：

```latex
\node[resultbox] (r) at ($(a.east)!0.5!(b.east)+(34mm,0)$) {Result};
```

- 分组框用 `fit` 时，`inner sep` 至少 `3-4mm`。标签放在框外侧。

## 常用布局片段

### 4 节点单行流程

```latex
\node[box] (a) {Input};
\node[box, right=of a] (b) {Feature\\extraction};
\node[box, right=of b] (c) {Model\\inference};
\node[resultbox, right=of c] (d) {Decision};
\draw[edge] (a) -- (b);
\draw[edge] (b) -- (c);
\draw[edge] (c) -- (d);
```

### 5 节点双行蛇形

```latex
\node[box] (a) {Collect};
\node[box, right=of a] (b) {Parse};
\node[box, right=of b] (c) {Extract};
\node[box, below=of c] (d) {Score};
\node[resultbox, left=of d] (e) {Report};
\draw[edge] (a) -- (b);
\draw[edge] (b) -- (c);
\draw[edge] (c) -- (d);
\draw[edge] (d) -- (e);
```

### 双流水线

```latex
\node[box] (src) {Targets};
\node[box, right=14mm of src, yshift=10mm] (a1) {Path A\\traffic};
\node[box, right=of a1] (a2) {Attack\\evaluation};
\node[box, right=14mm of src, yshift=-10mm] (b1) {Path B\\profiling};
\node[box, right=of b1] (b2) {QoS\\metrics};
\node[resultbox] (r) at ($(a2.east)!0.5!(b2.east)+(32mm,0)$) {Alignment\\analysis};
\draw[edge] (src.east) -- (a1.west);
\draw[edge] (src.east) -- (b1.west);
\draw[edge] (a1) -- (a2);
\draw[edge] (b1) -- (b2);
\draw[edge] (a2.east) -- (r.west |- a2.east);
\draw[edge] (b2.east) -- (r.west |- b2.east);
```

### 等宽卡片

```latex
card/.style={
  rounded corners=2pt, draw=blue!65, fill=blue!6, very thick,
  align=center, text width=2.55cm, minimum height=3.2cm,
  inner xsep=4pt, inner ysep=5pt
}
\node[card] (c1) {Category A\\[2mm] item 1\\item 2\\item 3};
\node[card, right=6mm of c1] (c2) {Category B\\[2mm] item 1\\item 2\\item 3};
```

## 编译与验证

每张图都必须实际编译和检查：

```powershell
xelatex -interaction=nonstopmode -halt-on-error figure.tex
pdftoppm -png -r 220 figure.pdf figure
Move-Item -Force figure-1.png figure.png
Select-String -Path figure.log -Pattern 'Overfull|Underfull|Missing|Error|Warning'
```

必须肉眼检查 PNG：
- 节点文字是否贴边或溢出。
- 箭头是否穿过文字。
- 箭头标签是否压线、压边框、压节点。
- 注释是否占用主通道。
- 多条汇聚箭头头部是否挤成一团。
- 宽高比是否过扁，放入 PPT 后是否还能读清。

如果检查失败，优先改布局和通道，不要只缩小字体。

## 常见坏味道与修复

| 坏味道 | 风险 | 修复 |
|---|---|---|
| 只写 `minimum width` 不写 `text width` | 长文本横向撑爆节点 | 所有非短词节点设置 `text width` |
| 5 个以上节点全部 `right=of` | 图过宽，后续必重叠 | 改双行蛇形、分层或卡片 |
| 箭头标签使用普通 `node[above]` | 标签贴线、贴边框 | 定义 `elabel`，加白底和 `above=2pt` |
| 长标签贴在汇聚边上 | 标签挤在目标入口 | 把结论写进节点，边只保留方向 |
| 注释用随手绝对坐标 | 文本变化后压住节点或箭头 | 用锚点或 `calc` 坐标建立独立注释通道 |
| 代码/路径/错误签名直接写 | `_` 编译错误或长 token 溢出 | 用 `\texttt{}` 并转义 `_`，主动换行 |
| 表格行高不足 | 多行文本压边框 | 增大 `minimum height` 并同步拉开坐标/`row sep` |
| 强行复刻复杂论文表格 | 单元格拥挤、底注重叠 | 改等宽卡片或分层摘要 |
| 自定义样式名叫 `out`/`in` | 与 TikZ 内置路径键冲突 | 改为 `resultbox`、`riskbox` 等 |
| 使用 `$()` 坐标但未加载 `calc` | 编译报库缺失 | 加 `\usetikzlibrary{calc}` |
| `right=of $(a)!0.5!(b)$` | 新节点可能压住前一组节点 | 用 `at ($(a.east)!0.5!(b.east)+(距离,0)$)` |
| 分组虚线框贴节点太近 | 框线压文字或标签 | `inner sep >= 3mm`，标签放框外 |

## 最终交付清单

交付前确认：

- `.tex` 可用 `xelatex` 无错误编译。
- `.pdf` 和 `.png` 均已生成。
- 日志没有关键 `Overfull`、`Missing`、`Error`、`Warning`。
- PNG 肉眼检查无模块、箭头、文字、标签、注释重叠。
- 图像宽高比适合目标页面；过扁则已改双行/分层/卡片。
- 复杂机制和数值结论尽量写进节点，避免堆在箭头边上。

## 可直接使用的 agent 提示

```text
请根据给定内容生成一张 TikZ 模块图。生成前先做容量预算，选择合适布局，避免节点、箭头、标签和注释重叠。所有模块节点必须设置 text width、minimum height、inner xsep、inner ysep；箭头使用 shorten >=2pt 和 shorten <=2pt；箭头标签使用白底小字。若节点数 >=5 或最长文本较长，优先使用双行蛇形、分层、矩阵或等宽卡片。生成 standalone TikZ 源码后必须编译为 PDF/PNG，检查日志和渲染图，如有重叠则调整布局直到可用。
```
