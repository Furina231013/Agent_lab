## 1

**question**
默认的 Segment 长度和 overlap 分别是多少？

**expected_source_section**
4.1 默认切分长度

**expected_key_points**

* Segment 默认长度 420 字符
* 默认重叠长度 60 字符

**reference_answer**
默认 Segment 长度为 420 字符，默认 overlap 为 60 字符。

**error_type_hint**
A1 / R1

---

## 2

**question**
系统默认支持哪些文件类型？哪些不支持？

**expected_source_section**
3.1 支持的文件类型

**expected_key_points**

* 支持 `.md`
* 支持 `.txt`
* 支持 `.pdf`
* 不支持 `.docx`
* 不支持 `.html`
* 不支持 `.csv`
* 不支持图片文件

**reference_answer**
系统默认支持 `.md`、`.txt` 和 `.pdf`。不支持 `.docx`、`.html`、`.csv` 以及图片文件。

**error_type_hint**
A1 / A2

---

## 3

**question**
如果用户提交的是目录路径，而不是具体文件路径，系统应该怎么处理？

**expected_source_section**
3.2 导入路径规则

**expected_key_points**

* 要求路径必须指向具体文件
* 目录路径会返回导入警告
* 不会自动递归扫描全部文件
* 属于 I1 导入目标不明确

**reference_answer**
系统要求导入路径必须指向具体文件。如果用户提交目录路径，系统应返回导入警告，而不是自动递归扫描全部文件，这属于 I1 导入目标不明确。

**error_type_hint**
R1 / A2

---

## 4

**question**
PDF 在什么情况下会被标记为 I2？

**expected_source_section**
3.1 支持的文件类型

**expected_key_points**

* PDF 只提取文本层
* 不做 OCR
* 如果 PDF 没有可提取文本
* 标记为 I2 空文本导入失败

**reference_answer**
系统只提取 PDF 的文本层，不做 OCR。如果 PDF 没有可提取文本，就会被标记为 I2 空文本导入失败。

**error_type_hint**
A1 / A2

---

## 5

**question**
重复导入同一个文件时，系统如何判断是“重复导入”还是“更新导入”？

**expected_source_section**
3.3 重复导入规则

**expected_key_points**

* 24 小时内重复导入才触发该规则
* 先做内容摘要比对
* 差异低于 5% 记为重复导入
* 差异高于 5% 记为更新导入
* 5% 指字符级变化比例，不是语义相似度

**reference_answer**
如果同一个文件在 24 小时内被重复导入，系统会先做内容摘要比对。若差异低于 5%，记为重复导入；若差异高于 5%，记为更新导入。这里的 5% 指字符级变化比例，不是语义相似度。

**error_type_hint**
A1 / A2 / A3

---

## 6

**question**
长度小于多少的段落通常不会单独成为 Segment？

**expected_source_section**
4.3 短段合并规则

**expected_key_points**

* 小于 120 字符
* 通常不单独作为 Segment
* 除非是参数表标题 / 错误码标题 / 特殊告警标题

**reference_answer**
长度小于 120 字符的段落通常不会单独作为 Segment，而会与下一段合并；除非它是参数表标题、错误码标题或特殊告警标题。

**error_type_hint**
A1 / A2

---

## 7

**question**
为什么标题在切分后仍然要进入后续 Segment？

**expected_source_section**
4.2 标题优先规则

**expected_key_points**

* 如果文档有明确标题层级，标题应保留
* 标题要进入后续 Segment
* 标题被视为轻量语义锚点

**reference_answer**
如果文档存在明确标题层级，系统会优先保留标题并让标题进入后续 Segment，因为标题被视为轻量语义锚点，有助于后续检索和理解。

**error_type_hint**
R2 / A2

---

## 8

**question**
日志类型材料和普通文档的切分方式有什么不同？

**expected_source_section**
4.4 日志材料例外

**expected_key_points**

* 日志不采用普通段落切分
* 使用时间块切分
* 同一分钟连续日志优先视为同一块
* 单块上限 30 行
* 超过 30 行按错误堆栈边界切开

**reference_answer**
日志类型材料不采用普通段落切分，而采用时间块切分。同一分钟内的连续日志优先视为同一块，单块上限为 30 行；若超过 30 行，则按错误堆栈边界切开。

**error_type_hint**
A1 / R2

---

## 9

**question**
Lookup 模式和 Explain 模式分别优先使用哪种一级检索器？

**expected_source_section**
5.1 一级检索策略

**expected_key_points**

* Lookup 优先 K-Search
* Explain 优先 V-Search

**reference_answer**
Lookup 模式默认优先执行 K-Search，Explain 模式默认优先执行 V-Search。

**error_type_hint**
A1 / R1

---

## 10

**question**
系统是不是只会执行优先级更高的那个检索器？

**expected_source_section**
5.2 双路召回规则

**expected_key_points**

* 不是
* 必须执行双路召回
* 即便 Lookup 也不能只跑关键词检索

**reference_answer**
不是。无论优先级如何，系统都必须执行双路召回。即便是 Lookup 模式，也不能只跑关键词检索。

**error_type_hint**
A1 / A2

---

## 11

**question**
K-Search 和 V-Search 默认各返回多少个候选？合并后最多保留多少个候选进入重排？

**expected_source_section**
5.2 双路召回规则

**expected_key_points**

* K-Search 返回前 4 个候选
* V-Search 返回前 6 个候选
* 合并后最多保留 7 个候选块进入重排

**reference_answer**
K-Search 默认返回前 4 个候选，V-Search 默认返回前 6 个候选；合并后最多保留 7 个候选块进入重排阶段。

**error_type_hint**
A1

---

## 12

**question**
什么情况下两个候选块会在重排前被视为重复并去重？

**expected_source_section**
5.3 重排前去重

**expected_key_points**

* 来自同一 Source Unit
* 文本重叠超过 70%
* 只保留得分更高者

**reference_answer**
如果两个候选块来自同一 Source Unit，且文本重叠超过 70%，则在重排前会被视为重复，只保留得分更高的那个。

**error_type_hint**
A1 / A2

---

## 13

**question**
标题加权在什么情况下生效？加多少分？

**expected_source_section**
5.4 标题加权

**expected_key_points**

* 候选块包含与问题显著相关的标题
* 标题命中至少一个问题关键词
* 标题长度不超过 24 个字符
* 增加 0.08 的排序分

**reference_answer**
如果候选块中包含与问题显著相关的标题，就会触发标题加权。显著相关的定义是标题命中至少一个问题关键词，且标题长度不超过 24 个字符。满足条件时，该块增加 0.08 的排序分。

**error_type_hint**
A1 / A2

---

## 14

**question**
默认会选取多少个 Evidence Block 进入回答阶段？在什么条件下可以扩展到 4 个？

**expected_source_section**
6.1 Evidence Block 选取数量

**expected_key_points**

* 默认 3 个
* 不是 5 个也不是 7 个
* 只有 Explain 模式才可能扩展到 4 个
* 且前 3 个块分属至少 2 个不同 Source Unit

**reference_answer**
进入回答阶段的 Evidence Block 默认数量是 3 个。只有在问题被识别为 Explain 模式，并且前 3 个块分属至少 2 个不同 Source Unit 时，才允许扩展到 4 个。

**error_type_hint**
A1 / A2 / R2

---

## 15

**question**
回答阶段的上下文总预算是多少？如果超限，裁剪顺序是什么？

**expected_source_section**
6.2 长度预算

**expected_key_points**

* 总预算 1600 字符
* 先裁剪最低分块
* 若仍超限，再裁剪每个块尾部冗余句
* 不允许裁掉标题行

**reference_answer**
回答阶段的上下文总预算默认为 1600 字符。如果超过预算，先裁剪最低分块；若仍超限，再裁剪每个块的尾部冗余句，但不允许裁掉标题行。

**error_type_hint**
A1 / A2

---

## 16

**question**
如果多个 Evidence Block 之间出现冲突，系统应该怎么做？

**expected_source_section**
6.3 冲突处理规则

**expected_key_points**

* 不得强行合并为单一结论
* 必须显式说明存在冲突
* 最终回答中加入固定提示语
* 提示语是“当前材料存在不一致描述，请结合来源进行确认。”

**reference_answer**
如果多个 Evidence Block 的内容互相冲突，系统不得强行合并为单一结论，而应显式说明存在冲突。最终回答中必须加入固定提示语：“当前材料存在不一致描述，请结合来源进行确认。”

**error_type_hint**
A1 / A3

---

## 17

**question**
Response Frame 必须包含哪四部分？

**expected_source_section**
7.1 Response Frame 固定结构

**expected_key_points**

* 结论
* 依据
* 来源
* 不确定性说明

**reference_answer**
Response Frame 必须包含四部分：结论、依据、来源、不确定性说明。

**error_type_hint**
A1

---

## 18

**question**
Lookup 模式回答“默认切分长度是多少”时，系统应该更偏向哪种表达方式？

**expected_source_section**
7.2 Lookup 模式输出要求

**expected_key_points**

* 结论应尽量短
* 优先给明确事实
* 若是数值必须直接写出数值
* 不要先讲背景再讲答案

**reference_answer**
Lookup 模式下，系统应直接给出明确事实，例如直接回答“默认切分长度为 420 字符”，而不是先铺垫背景再给答案。

**error_type_hint**
A2

---

## 19

**question**
什么情况下系统应该触发降级回答？

**expected_source_section**
9.1 何时触发降级

**expected_key_points**

* 前 3 个候选块最高分低于 0.42
* 或 Evidence Block 少于 2 个
* 或存在明显冲突且无法判断哪个来源更可信

**reference_answer**
如果前 3 个候选块的最高分低于 0.42，或者 Evidence Block 少于 2 个，或者存在明显冲突且无法判断哪个来源更可信，系统应触发降级回答。

**error_type_hint**
A1 / A2

---

## 20

**question**
v1.0 是否已经把日志类 Source Unit 的单块上限改成了 24 行？

**expected_source_section**
13. 版本说明

**expected_key_points**

* 还没有生效
* v1.0 是计划版本
* 当前生效值仍然是 30 行

**reference_answer**
没有。文档说明 v1.0 计划将日志类 Source Unit 的单块上限从 30 行改为 24 行，但该规则尚未生效，当前生效值仍然是 30 行。

**error_type_hint**
A1 / A3 / R2

## 21

**question**
EdgeNote 会不会把整个目录直接当成一个 Source Unit 导入？

**expected_source_section**
2.1 Source Unit
3.2 导入路径规则

**expected_key_points**

* 不会
* 目录不是 Source Unit
* 目录中的文件要逐个识别后才算独立 Source Unit
* 导入路径应指向具体文件

**reference_answer**
不会。目录本身不是 Source Unit，只有目录中的文件被逐个识别后，每个文件才算独立 Source Unit。同时系统要求导入路径必须指向具体文件。

**error_type_hint**
R1 / A2

---

## 22

**question**
系统最终回答时，引用的材料块是不是所有检索到的 Segment 都会进入回答阶段？

**expected_source_section**
2.3 Evidence Block
6.1 Evidence Block 选取数量

**expected_key_points**

* 不是
* Evidence Block 来自 Segment
* 但不是所有 Segment 都能成为 Evidence Block
* 默认只选 3 个进入回答阶段

**reference_answer**
不是。Evidence Block 必须来自某个 Segment，但不是所有 Segment 都会进入回答阶段。默认情况下，进入回答阶段的 Evidence Block 数量是 3 个。

**error_type_hint**
A2 / R2

---

## 23

**question**
如果用户问“哪个参数是默认值”，这类问题更接近 Lookup 还是 Explain？

**expected_source_section**
2.4 Query Mode

**expected_key_points**

* 属于 Lookup
* “默认值”属于确定事实查找

**reference_answer**
这类问题更接近 Lookup 模式，因为“默认值”属于确定事实的查找。

**error_type_hint**
A1

---

## 24

**question**
如果用户问“为什么系统保留标题”，这类问题默认属于哪种 Query Mode？

**expected_source_section**
2.4 Query Mode
4.2 标题优先规则

**expected_key_points**

* 属于 Explain
* “为什么”默认归为 Explain

**reference_answer**
这类问题默认属于 Explain 模式，因为带有“为什么”的问题通常被视为解释原因或机制的问题。

**error_type_hint**
A1

---

## 25

**question**
Response Frame 是不是可以自由组织，只要意思完整就行？

**expected_source_section**
2.5 Response Frame
7.1 Response Frame 固定结构

**expected_key_points**

* 不可以自由组织
* 必须按固定结构
* 必须包含四部分

**reference_answer**
不可以。Response Frame 是固定输出结构，最终回答必须包含结论、依据、来源和不确定性说明这四部分。

**error_type_hint**
A1 / A2

---

## 26

**question**
系统是不是支持把图片里的文字识别出来后再纳入 PDF 处理？

**expected_source_section**
3.1 支持的文件类型
13. 版本说明

**expected_key_points**

* 当前不支持
* PDF 只提取文本层
* 不做 OCR
* OCR 支持尚未纳入当前版本

**reference_answer**
当前不支持。系统对 PDF 只提取文本层，不做 OCR；同时 OCR 支持也尚未纳入当前版本范围。

**error_type_hint**
A1 / A3

---

## 27

**question**
如果一个 PDF 没有文本层，但里面是扫描图片，系统会怎么处理？

**expected_source_section**
3.1 支持的文件类型

**expected_key_points**

* 不做 OCR
* 没有可提取文本时
* 标记为 I2 空文本导入失败

**reference_answer**
如果 PDF 没有可提取文本，而内容只是扫描图片，系统不会做 OCR，而会将其标记为 I2 空文本导入失败。

**error_type_hint**
A1 / A2

---

## 28

**question**
24 小时外再次导入同一文件，还适用那套 5% 差异规则吗？

**expected_source_section**
3.3 重复导入规则

**expected_key_points**

* 文档明确写的是 24 小时内重复导入才触发该规则
* 对 24 小时外情况，文档未明示同样规则

**reference_answer**
文档明确说明的是“同一个文件在 24 小时内被重复导入”时才使用 5% 差异规则。对于 24 小时外再次导入的情况，当前文档没有明确写出同样的处理规则。

**error_type_hint**
A2 / F2

---

## 29

**question**
文档切分时，是不是一律每 420 个字符硬切一次？

**expected_source_section**
4.1 默认切分长度

**expected_key_points**

* 不是一律硬切
* 优先按段落边界处理
* 只有单段超过 420 字符才允许强制截断

**reference_answer**
不是。系统优先按段落边界处理，只有在单段超过 420 字符时，才允许强制截断。

**error_type_hint**
A1 / A2

---

## 30

**question**
如果一个很短的段落是错误码标题，它会不会被强制和下一段合并？

**expected_source_section**
4.3 短段合并规则

**expected_key_points**

* 不一定会合并
* 小于 120 字符通常不单独成段
* 但错误码标题属于例外，可以单独作为 Segment

**reference_answer**
不会被强制合并。虽然长度小于 120 字符的段落通常不单独作为 Segment，但错误码标题属于例外情况，可以单独保留。

**error_type_hint**
A1 / A2

---

## 31

**question**
日志切分时，“同一分钟连续日志优先视为同一块”是什么意思？是不是跨分钟就不优先合并了？

**expected_source_section**
4.4 日志材料例外

**expected_key_points**

* 同一分钟内连续日志优先视为同一块
* 文档只明确这个优先规则
* 跨分钟不属于该优先条件

**reference_answer**
文档明确规定的是：同一分钟内的连续日志优先视为同一块。这意味着“同一分钟”是优先合并条件；跨分钟情况不属于这个优先条件。

**error_type_hint**
A2 / R2

---

## 32

**question**
Lookup 模式是不是完全不使用向量检索？

**expected_source_section**
5.1 一级检索策略
5.2 双路召回规则

**expected_key_points**

* 不是
* Lookup 只是优先 K-Search
* 仍然必须执行双路召回
* 不能放弃向量检索

**reference_answer**
不是。Lookup 模式只是优先执行 K-Search，但系统仍然必须执行双路召回，不能完全放弃向量检索。

**error_type_hint**
A1

---

## 33

**question**
Explain 模式是不是一定优先保留 4 个 Evidence Block？

**expected_source_section**
6.1 Evidence Block 选取数量
12.1 常见误解

**expected_key_points**

* 不是
* 默认仍是 3 个
* 只有满足条件时才可扩展到 4 个
* 条件是 Explain 模式且前 3 块分属至少 2 个不同 Source Unit

**reference_answer**
不是。Explain 模式默认仍然使用 3 个 Evidence Block，只有在 Explain 模式下且前 3 个块分属至少 2 个不同 Source Unit 时，才允许扩展到 4 个。

**error_type_hint**
A1 / A2

---

## 34

**question**
系统在进入回答前，最多会把多少个候选块送入重排阶段？

**expected_source_section**
5.2 双路召回规则

**expected_key_points**

* 合并后最多保留 7 个候选块进入重排阶段

**reference_answer**
系统在双路召回合并后，最多保留 7 个候选块进入重排阶段。

**error_type_hint**
A1

---

## 35

**question**
如果两个候选块来自不同的 Source Unit，但文本内容非常像，文档里有没有规定这时也要按 70% 重叠去重？

**expected_source_section**
5.3 重排前去重

**expected_key_points**

* 文档规定的去重条件包括“来自同一 Source Unit”
* 对不同 Source Unit 的相似块，当前规则未明确要求按同样标准去重

**reference_answer**
当前文档规定的去重条件之一是两个候选块必须来自同一 Source Unit，并且文本重叠超过 70%。对于来自不同 Source Unit 但内容相似的候选块，文档没有明确规定也按相同标准去重。

**error_type_hint**
A2 / F2

---

## 36

**question**
标题加权是不是只要标题比较短就会生效？

**expected_source_section**
5.4 标题加权

**expected_key_points**

* 不是
* 还必须与问题显著相关
* 标题要命中至少一个问题关键词
* 且标题长度不超过 24 字符

**reference_answer**
不是。标题加权不只是看标题短不短，还要求标题与问题显著相关，也就是标题命中至少一个问题关键词，并且标题长度不超过 24 个字符。

**error_type_hint**
A1 / A2

---

## 37

**question**
上下文超预算时，系统会优先裁掉哪类内容？

**expected_source_section**
6.2 长度预算

**expected_key_points**

* 先裁剪最低分块
* 不是先裁标题
* 若仍超限，再裁剪各块尾部冗余句

**reference_answer**
当上下文超预算时，系统会先裁剪最低分块；如果仍然超限，再裁剪每个块尾部的冗余句，而不是先裁标题。

**error_type_hint**
A1

---

## 38

**question**
如果上下文预算不够，标题能不能被删掉来腾空间？

**expected_source_section**
6.2 长度预算
12.3 常见误解

**expected_key_points**

* 不能
* 不允许裁掉标题行

**reference_answer**
不能。文档明确规定，预算裁剪时不允许裁掉标题行。

**error_type_hint**
A1 / A3

---

## 39

**question**
系统发现多个来源说法冲突时，会不会自动挑一个更像常识的说法输出？

**expected_source_section**
6.3 冲突处理规则
7.4 禁止行为

**expected_key_points**

* 不会
* 不得强行合并为单一结论
* 必须显式说明冲突
* 不应凭常识补全或替代来源内容

**reference_answer**
不会。系统在发现多个来源冲突时，不得强行合并成单一结论，而应显式说明存在冲突，也不能凭常识补全材料中不存在的结论。

**error_type_hint**
A1 / A2 / A3

---

## 40

**question**
在 Lookup 模式下，如果答案是默认值或数值，输出风格上最重要的要求是什么？

**expected_source_section**
7.2 Lookup 模式输出要求

**expected_key_points**

* 结论尽量短
* 优先给出明确事实
* 若是数值必须直接写出数值
* 不要先讲背景再讲答案

**reference_answer**
Lookup 模式下，最重要的是直接给出明确事实。如果答案是默认值或数值，就应直接写出数值，并尽量保持结论简短，不要先讲背景再讲答案。

**error_type_hint**
A2

---

## 41

**question**
Explain 模式输出时，如果涉及步骤，最多允许列多少步？

**expected_source_section**
7.3 Explain 模式输出要求

**expected_key_points**

* 最多列 4 步

**reference_answer**
Explain 模式下，如果回答涉及步骤，最多允许列 4 步。

**error_type_hint**
A1

---

## 42

**question**
Explain 模式能不能使用“可能是”“大概是”这种模糊表述？

**expected_source_section**
7.3 Explain 模式输出要求

**expected_key_points**

* 一般不允许
* 除非材料本身就不确定

**reference_answer**
一般不允许。Explain 模式不应使用“可能是”“大概是”这类无来源的模糊表达，除非材料本身就不确定。

**error_type_hint**
A1 / A2

---

## 43

**question**
“A2” 代表哪类错误？

**expected_source_section**
8.4 A 类：回答错误

**expected_key_points**

* A2 = 结论正确但依据不足

**reference_answer**
A2 表示“结论正确但依据不足”。

**error_type_hint**
A1

---

## 44

**question**
如果系统本来应该降级，却没有降级，这属于哪类错误？

**expected_source_section**
8.5 F 类：回退错误

**expected_key_points**

* F1
* 应降级却未降级

**reference_answer**
这种情况属于 F1，也就是“应降级却未降级”。

**error_type_hint**
A1

---

## 45

**question**
如果已经降级了，但系统仍然输出了很强的确定性结论，这属于什么错误？

**expected_source_section**
8.5 F 类：回退错误

**expected_key_points**

* F2
* 降级后仍输出强结论

**reference_answer**
这属于 F2，也就是“降级后仍输出强结论”。

**error_type_hint**
A1

---

## 46

**question**
当系统触发降级回答后，是否就完全不能给用户任何候选事实了？

**expected_source_section**
9.2 降级后的行为
9.3 特别说明

**expected_key_points**

* 不是完全不能
* 若是 Lookup 模式触发降级
* 仍然必须给出最接近材料的候选事实
* 但要明确标记为未确认

**reference_answer**
不是。如果是 Lookup 模式触发降级，系统仍然必须给出最接近材料的候选事实，但要明确标记为“未确认”。

**error_type_hint**
A2 / F2

---

## 47

**question**
单机模式下一次导入超过 15 个 Source Unit，会不会被系统强制拒绝？

**expected_source_section**
10.1 文档导入约束

**expected_key_points**

* 不会强制拒绝
* 系统会提示建议分批导入
* 15 是建议上限，不是硬性拒绝阈值

**reference_answer**
不会被强制拒绝。单次导入超过 15 个 Source Unit 时，系统会提示“建议分批导入”，但不会强制拒绝。

**error_type_hint**
A1 / A2

---

## 48

**question**
单机模式下，纯检索和检索加回答的目标延迟分别是多少？

**expected_source_section**
10.2 查询延迟目标

**expected_key_points**

* 纯检索 < 0.8 秒
* 检索 + 回答 < 4.5 秒
* 这是目标值，不是强制 SLA

**reference_answer**
单机模式下，纯检索的目标延迟是小于 0.8 秒，检索加回答的目标延迟是小于 4.5 秒。这些是目标值，而不是强制 SLA。

**error_type_hint**
A1

---

## 49

**question**
索引刷新是在每处理完一个 Segment 后立即进行，还是在一次 ingest 完成后统一刷新？

**expected_source_section**
10.3 索引刷新规则

**expected_key_points**

* 不是每个 Segment 都刷新
* 默认在一次 ingest 完成后统一刷新索引
* 原因是避免频繁小写入导致索引状态不稳定

**reference_answer**
系统不是在每处理完一个 Segment 后立即刷新索引，而是默认在一次 ingest 完成后统一刷新索引，这样可以避免频繁小写入导致索引状态不稳定。

**error_type_hint**
A1 / A2

---

## 50

**question**
当前版本已经支持哪些高级能力，哪些还没有纳入？

**expected_source_section**
13. 版本说明

**expected_key_points**

* 当前版本尚未纳入：

  * 多用户权限
  * OCR 支持
  * 图表解析
  * 跨设备索引同步
  * 自动术语表学习
* 当前文档是 v0.9 单机规范草案

**reference_answer**
当前文档是 v0.9 单机规范草案。尚未纳入本版本的高级能力包括：多用户权限、OCR 支持、图表解析、跨设备索引同步，以及自动术语表学习。

**error_type_hint**
A1 / A3