"""Generate topic-specific skills and maintained playbooks from the topic registry."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / 'skills/wechat-editorial-pipeline'
themes = json.loads((SKILL / 'assets/themes.json').read_text(encoding='utf-8'))
book = ['# 八类主题制作手册', '', '按当前题材只读取对应章节。各配方是制作建议，真实材料和用户要求优先。', '']
for key, theme in themes.items():
    sections = [f'# {theme["name"]}推文流程', '',
        '先确定文章用途和读者，再根据下列材料与结构制作。没有的事实保留缺口，不用模板补造。', '',
        '## 最少需要的事实', '']
    sections += ['- ' + x for x in theme['required_facts']]
    sections += ['', '## 两种可用结构', ''] + ['- ' + x for x in theme['structures']]
    sections += ['', '## 写作与去模板化', ''] + ['- ' + x for x in theme['writing']]
    sections += ['', '## 真实照片检索', ''] + ['- ' + x for x in theme['photo_queries']]
    sections += ['', '源页与许可逐张核对；下载原图并看图。图库是氛围，不能冒充活动现场、产品客户或到访记录。', '',
        '## 版式配方', '', theme['layout'], '',
        '动态主标题用完整首帧、缓慢局部装饰、主题背景与静态备份；正文不依赖网页动画。', '',
        '## 专项审核', ''] + ['- ' + x for x in theme['review']]
    sections += ['', '再完成通用五项语义复核：事实、自然文风、首轮校对、最终校对和照片。指纹变化后重新核对。', '',
        '## 可直接使用的制作指令', '',
        f'请围绕【主题】制作一篇面向【读者】的{theme["name"]}公众号文章。先核实材料和文章状态，选择本手册中适合的结构；缺少关键事实时只暂停依赖部分。正文自然具体，不编经历、引语、数字或效果；用真实且有使用依据的摄影配图。制作主标题GIF、适配背景和紧凑排版，做双轮全文校对与来源审核，交付预览、审核报告和可追溯文件包。', '',
        '## 交付与下一步', '',
        '正文Markdown、元数据、事实台账、照片清单、动态/静态标题、微信正文片段、预览、审核报告与SHA清单。实际后台草稿和手机效果必须分别核验，不能从本地通过推断。']
    if key == 'campus':
        sections[2:2] = ['用户给校园报道截图或要求暖色插画与白内页时，读取项目 `skills/wechat-editorial-pipeline/references/campus-warm-layout.md`，可选campus-warm版式；不得移用参考人物、活动事实、署名或二维码。', '']
    body = '\n'.join(sections) + '\n'
    book += [f'## {key} · {theme["name"]}', '', body.replace('# ', '### ', 1), '']
    folder = ROOT / '.agents/skills' / ('wechat-topic-' + key)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'SKILL.md').write_text(f'---\nname: wechat-topic-{key}\ndescription: 制作{theme["name"]}类微信公众号图文，处理该题材的选题、事实、自然写作、真实配图、动态标题和专项审核。\n---\n\n' + body +
        '\n执行通用工具与审核时，读取项目 `skills/wechat-editorial-pipeline/SKILL.md`，并使用 `tools/wechat.py`。用户只要求一个环节时完成该环节，不擅自上传或发布。\n', encoding='utf-8')
(SKILL / 'references/topic-playbooks.md').write_text('\n'.join(book), encoding='utf-8')
print(json.dumps({'topic_skills': list(themes), 'playbook': str(SKILL / 'references/topic-playbooks.md')}, ensure_ascii=False))
