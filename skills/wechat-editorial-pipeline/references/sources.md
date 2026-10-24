# 运行时参考与适配

- [op7418/Humanizer-zh](https://github.com/op7418/Humanizer-zh)，MIT，固定提交 `f4518a8eab97b8bfebc66a89d34320a89bef6930`。参考其事实、确定程度与作者声音保真。当前项目已安装；在其他项目未找到时，使用本包模块与审核规则，不能假定技能已安装。
- [JimLiu/baoyu-skills](https://github.com/JimLiu/baoyu-skills)，MIT，固定提交 `1567581c26ec29f4216c6e6835415bf30343b0e3`。项目安装Markdown排版和公众号草稿两项技能；本包自己的确定性脚本不依赖它们运行。
- [markdownlint](https://github.com/DavidAnson/markdownlint) 与 [AutoCorrect](https://github.com/huacnlee/autocorrect)：参考结构检查、问题编号、混排与标点检查思路。本包没有冒称实际调用了这两个工具。
- [pycorrector](https://github.com/shibing624/pycorrector)：可选的中文纠错扩展方向，未自动下载模型。

项目的完整比较与采用边界保存在 `research/GitHub选型与采用说明.md`。本包脚本、版式与主题是本轮按用户要求自行实现，未复制未声明许可的代码或AGPL主题组件。

使用其他人的技能时，以当前用户范围为准。默认生图不能替代正文真实摄影；逐步确认习惯不能代替当前已授权的自动制作；技能里的发布命令不自动构成对外发送授权。
