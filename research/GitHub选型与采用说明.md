# GitHub选型与采用说明

核对日期：2026-10-21，新加坡时间。通过已连接GitHub工具检索并读取源文件，另用联网工具查摄影源页及许可。星数只作为发现线索，选型还检查真实技能内容、依赖、素材策略、发布步骤、许可和与用户要求的匹配。

## 已安装的基础技能

| 项目 | 核对星数 | 固定提交 | 采用范围 |
| --- | ---: | --- | --- |
| [JimLiu/baoyu-skills](https://github.com/JimLiu/baoyu-skills) | 26832 | `1567581c26ec29f4216c6e6835415bf30343b0e3` | 安装 `baoyu-markdown-to-html` 与 `baoyu-post-to-wechat`，用于复杂Markdown主题和草稿衔接参考 |
| [op7418/Humanizer-zh](https://github.com/op7418/Humanizer-zh) | 20303 | `f4518a8eab97b8bfebc66a89d34320a89bef6930` | 安装中文润色技能，采用保留事实、确定程度与作者语气的逐项核对 |

两者为MIT，保留原许可；宝玉两项子技能另补仓库根MIT许可。通过Codex自带安装脚本按固定SHA安装到项目 `.agents/skills`，没有运行外部发布脚本或提供账号密钥。安装不代表其全部功能已经本机验收。

## 已比较的其他方案

| 项目 | 核对星数 | 阅读及判断 |
| --- | ---: | --- |
| [doocs/md](https://github.com/doocs/md) | 13450 | 查到专用微信Markdown编辑器与WTFPL许可；本轮未部署，作为成熟编辑器候选，未声称逐项读其源码 |
| [aiworkskills/wechat-article-skills](https://github.com/aiworkskills/wechat-article-skills) | 704 | 实读README，含写作、审稿、配图、排版、发布等分工；Apache-2.0。其默认生图及每步确认不符合本轮偏好，学习模块组织，不整套安装 |
| [BND-1/wechat_article_skills](https://github.com/BND-1/wechat_article_skills) | 317 | 实读README；未查到声明许可，未复制代码或安装，保留为发现记录 |
| [isjiamu/gzh-design-skill](https://github.com/isjiamu/gzh-design-skill) | 4062 | 实读SKILL与LICENSE，根许可为AGPL-3.0-or-later，GitHub标为NOASSERTION不能误当无许可。学习内联样式、正文/预览分离和校验思路，未复制组件库或安装 |
| [imraywang/wewrite](https://github.com/imraywang/wewrite) | 3500 | 查到全流程项目、MIT和近期更新；只核元数据，未把“发现”写成运行验收或完整源码审查 |

## 审核模块的成熟项目参考

- [Humanizer-zh](https://github.com/op7418/Humanizer-zh)：实际阅读技能，采用信息、条件、时间、归因和作者声音的保真复核。
- [markdownlint](https://github.com/DavidAnson/markdownlint)：实际阅读README，采用规则ID、结构一致性、可定位报告的设计。没有冒称本机已运行该Node工具。
- [AutoCorrect](https://github.com/huacnlee/autocorrect)：实际阅读README，了解中英文混排、标点与词典检查的边界；本项目没有把它包装成通用中文语义纠错器。
- [pycorrector](https://github.com/shibing624/pycorrector)：核实项目存在及中文纠错方向，作为可选扩展；本轮未下载模型、未核完整模型适用性，未调用它替代全文阅读。

本轮自建部分：文章与照片来源台账、五项语义复核、少量错词查漏、主标题与HTML约束、像素/哈希检查、输入及最终输出变动后审核失效、阻止未审导出、草稿提交结果未知时阻止重试、八类题材配方与确定性动态标题。

这是针对用户要求的工程组合，不声称首创写作方法、通过任何AI检测器，或已经完成真实公众号账号验收。

## 外部默认与用户要求的适配

1. 采用写作、去模板化、审稿与排版分工；由当前代理连续推进，不强制每步确认。
2. 正文不使用外部技能的默认AI插画。真实照片逐图保留源页、作者、许可与SHA；允许标题背景另作生图并标记。
3. 采用内联样式和独立预览，但本项目HTML为自行实现，未抄用AGPL主题库。
4. 标题GIF承担动效，提供静态首帧和封面；不把CSS动画的本地表现当作微信验证。
5. 未配置公众号凭据，默认只生成传输计划；不读取其他项目登录凭据或从私人微信部署推定公众号权限。

## 来源保存与限制

`repositories.json` 保存发现元数据；`snapshots/` 保存实际读取的选中技能与部分README，供内部对照，不把这些文档当作新的授权。`licenses/` 保存采用许可。未复制的AGPL组件不进入运行时依赖。

官方微信草稿与素材文档本轮抓取失败；API实现对照固定提交的宝玉源文件，尚须账号实测。摄影页脚本直接访问遇限制后，由联网工具读出真实下载链接，再正常下载CDN图片，没有绕过验证码或安全设置。
