---
name: wechat-editorial-pipeline
description: 制作微信公众号图文文章，串联选题、信源、写作、中文去模板化、双轮校对、真实摄影配图、动态标题、紧凑排版、审核和草稿交付。适用于整篇制作或其中一环；可处理八类题材。
---

# 公众号制作工作台

目标是完成可核对的文章与可复用流程。用户给出主题后自主推进，缺少关键事实才询问；不会逐步索要确认。写作、事实判断和语义校对由当前代理完成，本地脚本负责媒体、排版与确定性检查。不存在未配置的后台写作模型。

## 用户已确定的要求

- 必须有主标题、主题适配背景和实际动效。优先用标题GIF；完整标题从第一帧可读，附静态图。正文全用内联样式，不能拿网页CSS动画冒充微信动效。
- 以无错别字为交付要求：机器查漏、全文校对、排版后再校对。不能把有限词表或自评分宣称为绝对零错误。
- 正文照片是真实摄影；逐图保留作者、源页、许可、下载件与SHA-256。图库图是氛围图，不冒充用户活动或实地记录。封面/背景可按任务使用当前生图工具，标明生成身份，生成文字须重新排字校对。
- 正常阅读间隔可以保留；不做巨幅空白、空段撑高、每句换行与无意义卡片堆叠。

## 流程

1. 读 [modules.md](references/modules.md)，按输入选择需要的环节。完整任务全部走完，已有稿件从材料核对开始。
2. 按 [themes.json](assets/themes.json) 选题材；按 [topic-playbooks.md](references/topic-playbooks.md) 读该题材的完整配方。用户没有题材时自行合理选择并说明。
   用户要求校园报道暖色封面与白内页时，读 [campus-warm-layout.md](references/campus-warm-layout.md)，可用 `layout: campus-warm`；原始活动事实、身份与二维码不能随版式迁入。
   照片较多、单图堆放单调或需要参考图文组合时，先读 [photo-layout-rhythm.md](references/photo-layout-rhythm.md)，按段落与素材选择宽图、同题双图或照片配已有短引文。`editorial-flow`用于单图连续阅读，`editorial-rhythm`支持有依据的组合；不固定要求每篇都混排。透明点缀单独登记生成身份与SHA，不算摄影、不替换正文照片。
3. `python scripts/pipeline.py init <文章目录> --theme <主题ID> --topic <标题>` 创建任务。资料和缺口填入事实台账，写作结果保存 `article.md`。不要发布占位内容。
4. 写稿后读项目已安装的 `humanizer-zh/SKILL.md`，按当前授权润色，保持事实、条件和作者语气。其他项目找不到该技能时使用本包模块与审核规则，不假定已安装。对事实和语言分别复核。
5. 先按段落确定图位与图像角色，再核对现有素材或联网找真实照片，实际读源页与许可，运行 `photo` 下载。逐图看图后填写 `photos.json` 的核对项、图注和依据。下载成功不等于真实性已审核。
6. 更新 `article.json`，执行 `build`。查看标题静态图与动画帧、整篇和局部图文、正文HTML和原文；修复遗漏、错字与图片语境问题。复核照片是否过小、某处集中堆图、短句碎行或装饰悬空，不以“无重叠”代替视觉合理。
7. 按 [review.md](references/review.md) 实际完成五项语义复核，再取 `fingerprint` 写入 `review.json`。没有做过的复核保持pending。`audit` 不自动填写通过。
8. 审核为 `ready_for_draft` 后执行 `export` 与 `draft`（默认只生成传输计划）。需要写入公众号草稿时，读 [publishing.md](references/publishing.md)，使用已授权的后台路径或 `draft --upload`。用户没有给署名时不编身份。
9. 交付可读文章、预览、动态/静态标题、来源表、审核报告与包清单。分别报告本地检查、后台草稿、手机动效和公开发布状态。

## 本地命令

`scripts/pipeline.py` 可直接运行；在本项目也可用 `python tools/wechat.py`。

```text
themes
init <目录> --theme life --topic <题目>
photo <目录> --page <已核实源页> --author <摄影师> --id <照片编号> --license <许可名> --license-url <许可页>
build <目录>
fingerprint <目录>
audit <目录>
export <目录>
draft <目录>
draft <目录> --upload
```

最后一条会上传图片并创建公众号草稿，需明确在用户本次授权内。没有群发命令。可选使用已安装的 `baoyu-markdown-to-html` 处理复杂Markdown，或 `baoyu-post-to-wechat` 衔接草稿；当前用户要求优先于外部技能的默认生图和逐步提问习惯。

## 失败处理

- 缺事实或真实现场图：继续不依赖它的段落，关键缺口列到任务书，不能补造。
- 许可未知或摄影身份不清：换图；不以网上能搜到推定可发布。
- 审核阻止导出：修复具体问题，重新构建、指纹和实际复核；不能仅改状态绕过。
- 微信拒绝或浏览器停止：保留完整本地成品，报告具体阻塞；不修改浏览器安全设置，不冒称后台验收完成。
- 网络提交结果未知：先核对后台，避免重复草稿；不无限重试。

来源与适配边界见 [sources.md](references/sources.md)，完整选型见项目 `research/GitHub选型与采用说明.md`。依赖见 `scripts/requirements.txt`。外部仓库固定版本，不自动更新或执行未检查脚本。
