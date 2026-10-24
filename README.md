# 公众号制作工作台

让 AI 编程代理协助制作微信公众号图文：从主题与事实核对，到自然写作、真实摄影配图、动态标题、紧凑排版、审核和本地交付。

写作与语义审核由当前对话中的代理完成；Python 工具负责可重复的排版、媒体生成、来源记录、指纹校验与导出。不需要额外配置写作 API。

![示例动态标题](posts/2026-10-22-campus-style-study/build/title.gif)

## 功能

- 八类题材：校园活动、科技科普、城市文旅、项目产品、生活随笔、公益服务、热点解读、读书文化。
- 真实摄影台账：作者、源页、许可、原件与使用件 SHA-256；图库图标注为氛围图。
- 动态标题 GIF、静态 PNG 和封面 JPEG，第一帧保留完整标题。
- 内联样式正文与独立预览，支持照片组合、章节图位和生成装饰。
- 五项语义复核、双轮校对记录、错误/提示分级；输入、引擎或输出变化使旧复核失效。
- 默认只生成草稿传输计划；具备账号权限和明确授权后可调用草稿接口，没有群发命令。

## 快速开始

建议 Python 3.10+。默认中文字体适配 Windows；其他系统请通过 `WECHAT_TITLE_FONT` 指向有使用依据的中文字体文件。Pillow 静态校样工具依赖 Windows 字体。

```powershell
git clone https://github.com/XG-N/wechat-editorial-workbench.git
cd wechat-editorial-workbench
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python tools/wechat.py themes
python tools/wechat.py init posts/my-article --theme science --topic "你的标题"
```

在支持本地技能的代理中打开项目，读取 `skills/wechat-editorial-pipeline/SKILL.md`。也可使用以下任务描述：

> 用公众号工作台做一篇【主题】推文，面向【读者】。核实材料，使用真实摄影和可追溯来源，完成自然写作、动态标题、紧凑排版与双轮校对，交付本地预览和审核报告。

填写 `article.md`、`article.json`、`facts.json` 与 `photos.json` 后：

```powershell
python tools/wechat.py build posts/my-article
python tools/wechat.py fingerprint posts/my-article
python tools/wechat.py audit posts/my-article
python tools/wechat.py export posts/my-article
python tools/wechat.py draft posts/my-article
```

`build` 会生成待审预览；存在未审项时为 `blocked`。完成实际复核、记录当前指纹与依据后，`audit` 为 `ready_for_draft` 才能导出。不要为了清除阻止状态伪填通过。

## 示例

`posts/2026-10-22-campus-style-study/` 包含《给周末留一段慢走的时间》。五张真实摄影分别记录来源，背景和点缀单独标记为生成装饰，不代表真实地点或活动。

下载 Release ZIP 并解压，打开示例的 `build/preview.html` 查看本地效果。GitHub 文件页不会执行 HTML。可重新构建：

```powershell
python tools/wechat.py build posts/2026-10-22-campus-style-study
```

公开副本移除了本机绝对路径，并重置示例复核状态。预览用于展示排版；使用者须对当前文件重新审核，不能继承原工作区的通过记录。

## 目录与手册

| 路径 | 内容 |
| --- | --- |
| `skills/wechat-editorial-pipeline/` | 主技能、主题注册表、制作手册、排版引擎 |
| `.agents/skills/` | 八类题材、独立审稿及采用的第三方技能 |
| `tools/` | 命令入口、技能安装、源码打包 |
| `tests/` | 离线行为测试、隔离预览逻辑测试 |
| `posts/` | 文章、素材来源、预览 |
| `research/` | 固定来源、采用范围、第三方许可 |

[十模块规范](skills/wechat-editorial-pipeline/references/modules.md) · [题材手册](skills/wechat-editorial-pipeline/references/topic-playbooks.md) · [图文节奏](skills/wechat-editorial-pipeline/references/photo-layout-rhythm.md) · [审核](skills/wechat-editorial-pipeline/references/review.md) · [草稿衔接](skills/wechat-editorial-pipeline/references/publishing.md)

## 验证与打包

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
node tests/test_preview_controls.cjs posts/2026-10-22-campus-style-study/build/preview.html
python tools/package_workbench.py --output ../wechat-editorial-workbench.zip
```

Python 测试使用隔离数据和接口替身；Node 测试验证控制逻辑，不代表真实浏览器或微信客户端验收。打包工具收集已由 Git 跟踪的文件；从 Release 解压后如需重新打包，应先初始化 Git 并检查待跟踪清单。源码打包与文章审核导出是两个操作。

## 草稿接口与状态

`draft` 默认 dry-run。`draft --upload` 需要明确授权、真实署名、具有接口权限的公众号账号，以及自行设置的 `WECHAT_APP_ID`、`WECHAT_APP_SECRET`。不要提交密钥、登录态、Cookie 或 `.env`。

本仓库没有提供公众号凭据；示例未完成真实账号上传、手机效果或公开发布验收。本地预览、后台草稿、手机效果和公开发布须分别核验。上传结果未知时先读回核对，避免重复草稿。

## 来源与许可

采用的 `JimLiu/baoyu-skills` 和 `op7418/Humanizer-zh` 保留其 MIT 许可与固定来源，详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。未采用仓库快照、用户参考截图、本机配置、临时硬件控制、历史包和内部过程回执未收入公开版。

本项目原创代码与文档采用 [Apache-2.0](LICENSE) 开源许可，作者为 **XG-N**，原始仓库为 **https://github.com/XG-N/wechat-editorial-workbench**。

**再分发本项目或其衍生版本时，必须注明并保留适用的来源、版权和署名声明，提供许可证副本，并按 Apache-2.0 第 4 节保留 [NOTICE](NOTICE) 中的适用归属信息；修改过的文件须标明修改。** 可在随附 NOTICE、源码、说明文档或通常展示第三方声明的界面中保留来源。不将修改版冒充为原作者的官方版本。

用于公开演示、教程、论文或项目介绍时，也请在说明中引用以下来源（推荐引用格式）：

> XG-N. 公众号制作工作台（WeChat Editorial Workbench）. https://github.com/XG-N/wechat-editorial-workbench

上述公开引用为项目倡议；Apache-2.0 不要求单纯下载、私人使用或工具生成的每篇文章都额外展示署名。本项目没有添加非标准的使用限制，适用义务以许可证正文为准。

第三方技能保持其 MIT 许可；摄影按各自来源许可使用，不随软件重新授权。摄影作者、源页、许可链接和哈希见示例 `photos.json`，不要将第三方素材归为项目原创。
