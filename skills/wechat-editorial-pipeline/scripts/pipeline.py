"""Inspectable local WeChat production pipeline. Writing/review are performed by the agent.

No credentials or language-model calls are hidden in this program. Only `draft --upload`
sends a checked article to WeChat. There is deliberately no mass-send endpoint.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import html
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import sys
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse, unquote

import mistune
import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageOps

BASE = Path(__file__).resolve().parents[1]
TZ = timezone(timedelta(hours=8))
FONT = Path(os.environ.get('WECHAT_TITLE_FONT', 'C:/Windows/Fonts/msyhbd.ttc'))
REVIEW_STAGES = ('facts', 'natural_style', 'proofread_first', 'proofread_final', 'photos')
TYPO = {'按步就班': '按部就班', '再接再励': '再接再厉', '一愁莫展': '一筹莫展',
        '迫不急待': '迫不及待', '相辅相承': '相辅相成', '一如继往': '一如既往',
        '美仑美奂': '美轮美奂', '默守成规': '墨守成规', '谈笑风声': '谈笑风生',
        '不径而走': '不胫而走', '趋之若骛': '趋之若鹜', '穿流不息': '川流不息'}
ALLOWED_TAGS = {'section', 'h1', 'h2', 'h3', 'p', 'span', 'strong', 'em', 'a', 'img',
                'blockquote', 'ul', 'ol', 'li', 'pre', 'code', 'br', 'hr', 'table',
                'thead', 'tbody', 'tr', 'th', 'td', 'del'}
CSS_URL = re.compile(r'''url\(\s*(['"]?)(.*?)\1\s*\)''')


def now():
    return datetime.now(TZ).isoformat(timespec='seconds')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def local(job, name):
    """Reject input paths escaping the job, including Windows absolute paths."""
    if urlparse(name).scheme or Path(name).is_absolute() or re.match(r'^[A-Za-z]:', name):
        raise ValueError('本地素材路径必须相对于文章目录')
    path = (job / name).resolve()
    if not path.is_relative_to(job.resolve()):
        raise ValueError('素材路径超出文章目录')
    return path


def themes():
    return read_json(BASE / 'assets/themes.json')


def campus_layout():
    spec = importlib.util.spec_from_file_location('wechat_campus_layout', BASE / 'scripts/campus_layout.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_fingerprint(job):
    records = {}
    for name in ('article.md', 'article.json', 'photos.json', 'facts.json'):
        records[name] = digest(job / name) if (job / name).is_file() else None
    for photo in read_json(job / 'photos.json') if (job / 'photos.json').exists() else []:
        for key in ('file', 'original_file'):
            if photo.get(key):
                path = local(job, photo[key])
                records[photo[key]] = digest(path) if path.is_file() else None
    for key in ('assets/themes.json',):
        records['engine:' + key] = digest(BASE / key)
    for script in sorted((BASE / 'scripts').glob('*.py')):
        records['engine:' + script.name] = digest(script)
    for name in ('article.wechat.html', 'preview.html', 'title.gif', 'title.png', 'cover.jpg'):
        path = job / 'build' / name
        records['output:' + name] = digest(path) if path.is_file() else None
    return hashlib.sha256(json.dumps(records, sort_keys=True).encode()).hexdigest()


def init_job(job, theme, topic):
    if job.exists():
        raise ValueError('文章目录已经存在；请换一个名称，避免覆盖')
    job.mkdir(parents=True)
    spec = themes()[theme]
    write_json(job / 'article.json', {'title': topic, 'subtitle': '', 'theme': theme,
        'author': '', 'summary': '', 'hero_photo': '', 'source_url': '', 'status': 'draft'})
    (job / 'article.md').write_text(f'# {topic}\n\n', encoding='utf-8')
    write_json(job / 'photos.json', [])
    write_json(job / 'facts.json', {'sources': [], 'claims': []})
    write_json(job / 'review.json', {'input_sha256': '', 'reviewer': '',
        'stages': {s: {'status': 'pending', 'notes': ''} for s in REVIEW_STAGES},
        'findings': [], 'wechat_verified': False})
    brief = f'# 制作任务\n\n主题：{topic}\n题材：{spec["name"]}\n\n'
    brief += '## 必需材料\n\n' + '\n'.join('- ' + x for x in spec['required_facts'])
    brief += '\n\n## 可选文章结构\n\n' + '\n'.join('- ' + x for x in spec['structures'])
    brief += '\n\n## 写作要求\n\n' + '\n'.join('- ' + x for x in spec['writing'])
    brief += '\n\n## 配图检索起点\n\n' + '\n'.join('- ' + x for x in spec['photo_queries'])
    brief += '\n\n按技能 references/modules.md 完成采集、写作、去模板化、双轮校对、配图和排版。\n'
    (job / '任务书.md').write_text(brief, encoding='utf-8')


def download_photo(job, page, author, photo_id, license_name, license_url, image_url=None):
    """Download the og:image advertised by an inspected source page, never a search thumbnail."""
    if not re.fullmatch(r'[a-z0-9-]+', photo_id):
        raise ValueError('照片编号只允许小写字母、数字与连字符')
    if urlparse(page).scheme != 'https':
        raise ValueError('素材来源必须使用 HTTPS')
    manifest = read_json(job / 'photos.json')
    if any(p['id'] == photo_id for p in manifest):
        raise ValueError('照片编号已存在；禁止覆盖原下载件')
    if image_url is None:
        response = requests.get(page, timeout=30, headers={'User-Agent': 'Mozilla/5.0'})
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        tag = soup.find('meta', attrs={'property': 'og:image'})
        if not tag or not tag.get('content'):
            raise ValueError('来源页没有可追溯的 og:image；可传入联网工具已从源页读到的 --image-url，不猜链接')
        image_url = tag['content']
    if urlparse(image_url).scheme != 'https':
        raise ValueError('图片地址必须使用 HTTPS')
    folder = job / 'photos'
    folder.mkdir(exist_ok=True)
    original = folder / f'{photo_id}.source'
    if original.exists():
        raise ValueError('原下载文件已存在，未覆盖')
    with requests.get(image_url, timeout=30, stream=True) as res:
        res.raise_for_status()
        if not res.headers.get('Content-Type', '').startswith('image/'):
            raise ValueError('来源返回的不是图片')
        chunks = []
        size = 0
        for chunk in res.iter_content(65536):
            size += len(chunk)
            if size > 25 * 1024 * 1024:
                raise ValueError('图片超过本流程25MB下载预算')
            chunks.append(chunk)
    original.write_bytes(b''.join(chunks))
    with Image.open(original) as src:
        image = ImageOps.exif_transpose(src).convert('RGB')
        original_size = list(image.size)
        image.thumbnail((1440, 1440))
        output = folder / f'{photo_id}.jpg'
        image.save(output, quality=88, optimize=True)
    manifest.append({'id': photo_id, 'file': output.relative_to(job).as_posix(),
        'original_file': original.relative_to(job).as_posix(), 'kind': 'photo',
        'source_page': page, 'download_url': image_url, 'author': author,
        'license': license_name, 'license_url': license_url, 'retrieved_at': now(),
        'original_dimensions': original_size, 'sha256': digest(output),
        'original_sha256': digest(original), 'source_checked': False,
        'visual_checked': False, 'authenticity_basis': '', 'caption': '',
        'usage': 'illustrative', 'edit': 'EXIF方向校正、等比缩小与JPEG编码；未生成或替换场景元素'})
    write_json(job / 'photos.json', manifest)
    return output


def title_lines(title, font, width):
    lines = ['']
    for char in title:
        if font.getlength(lines[-1] + char) > width:
            lines.append(char)
        else:
            lines[-1] += char
    return lines


def make_hero(job, meta, photos, spec):
    if meta.get('layout') == 'campus-warm':
        background = next((p for p in photos if p['id'] == meta['hero_photo']), None)
        if background is None or background.get('file') != meta.get('hero_background'):
            raise ValueError('暖色封面背景必须与已登记的hero_photo素材一致')
        if digest(local(job, background['file'])) != background.get('sha256'):
            raise ValueError('暖色封面背景SHA-256不一致')
        return campus_layout().make_hero(job, meta, photos, spec)
    if not FONT.is_file():
        raise ValueError('缺少支持中文的标题字体；设置 WECHAT_TITLE_FONT 后重试')
    photo = next((p for p in photos if p['id'] == meta['hero_photo']), None)
    if photo is None:
        raise ValueError('hero_photo 必须指向已登记的照片')
    out = job / 'build'
    out.mkdir(exist_ok=True)
    width, height = 1000, 540
    with Image.open(local(job, photo['file'])) as src:
        bg = ImageOps.fit(src.convert('RGB'), (width, height)).convert('RGBA')
    # Photo is used only as a decorative title background. Body copies are unaltered.
    overlay = Image.new('RGBA', bg.size)
    pixels = ImageDraw.Draw(overlay)
    for x in range(width):
        pixels.line((x, 0, x, height), fill=(12, 29, 25, int(218 - 100 * x / width)))
    bg = Image.alpha_composite(bg, overlay)
    font_size = 62
    while font_size >= 36:
        font = ImageFont.truetype(str(FONT), font_size)
        lines = title_lines(meta['title'], font, 840)
        if len(lines) <= 3:
            break
        font_size -= 2
    if len(lines) > 3:
        raise ValueError('标题过长，无法在封面安全区内清晰显示')
    small = ImageFont.truetype(str(FONT), 23)
    frames = []
    palette = None
    for frame in range(28):
        im = bg.copy()
        d = ImageDraw.Draw(im)
        d.text((64, 57), spec['name'], font=small, fill='#E9E5CD')
        top = 152 if len(lines) <= 2 else 119
        for index, line in enumerate(lines):
            d.text((64, top + index * (font_size + 17)), line, font=font, fill='white',
                   stroke_width=1, stroke_fill=(0, 0, 0, 80))
        subtitle = meta.get('subtitle', '')
        if small.getlength(subtitle) > 850:
            raise ValueError('副标题超出安全区，请缩短')
        d.text((64, 424), subtitle, font=small, fill='#F1F1E9')
        # A slow, non-flashing moving accent. The complete title is visible in frame 0.
        d.rounded_rectangle((64, 487, 930, 491), 2, fill='#8B9C83')
        x = 64 + int((866 - 150) * frame / 27)
        d.rounded_rectangle((x, 484, x + 150, 494), 5, fill=spec['motion'])
        rgb = im.convert('RGB')
        if palette is None:
            palette = rgb.quantize(colors=96, dither=Image.Dither.NONE)
        # Quantize every frame, including frame 0, through the same color mapping.
        # Adaptive first-frame assignments otherwise cause a color jump at each loop.
        frames.append(rgb.quantize(palette=palette, dither=Image.Dither.NONE))
    frames[0].save(out / 'title.gif', save_all=True, append_images=frames[1:],
                   duration=110, loop=0, optimize=True, disposal=1)
    frames[0].convert('RGB').save(out / 'title.png')
    cover = ImageOps.fit(frames[0].convert('RGB'), (1000, 426))
    cover.save(out / 'cover.jpg', quality=91, optimize=True)
    return {'frames': len(frames), 'duration_ms': 3080, 'font': str(FONT),
            'font_size': font_size, 'lines': lines, 'source_photo': photo['id']}


def render_article(job, meta, photos, spec, hero):
    md = (job / 'article.md').read_text(encoding='utf-8-sig')
    soup = BeautifulSoup(mistune.create_markdown(escape=True, plugins=['table'])(md), 'html.parser')
    h1 = soup.find('h1')
    if not h1 or h1.get_text().strip() != meta['title']:
        raise ValueError('Markdown首个主标题必须与 article.json 的title完全一致')
    h1.clear()
    img = soup.new_tag('img', src='title.gif', alt=meta['title'])
    h1.append(img)
    by_file = {p['file']: p for p in photos}
    for image in list(soup.find_all('img')):
        if image is img:
            continue
        src = image.get('src', '')
        if src not in by_file:
            raise ValueError('正文图片未登记来源：' + src)
        photo = by_file[src]
        image['src'] = '../' + src
        image['alt'] = photo['caption']
        caption = soup.new_tag('p')
        caption['style'] = 'margin:7px 0 18px;font-size:12px;line-height:1.65;color:#74776e;'
        caption.string = f'{photo["caption"]}｜摄影：{photo["author"]} / {urlparse(photo["source_page"]).netloc}'
        parent = image.parent if image.parent.name == 'p' else image
        parent.insert_after(caption)
    styles = {
        'h1': 'margin:0 0 16px;font-size:24px;line-height:1.3;',
        'h2': f'margin:26px 0 12px;padding:7px 0 7px 12px;border-left:4px solid {spec["accent"]};font-size:20px;line-height:1.5;color:{spec["accent"]};',
        'h3': f'margin:20px 0 9px;font-size:17px;line-height:1.6;color:{spec["accent"]};',
        'p': 'margin:0 0 14px;font-size:16px;line-height:1.85;letter-spacing:0.3px;word-break:break-word;',
        'img': 'max-width:100%;height:auto;display:block;margin:0 auto;border-radius:3px;',
        'blockquote': f'margin:16px 0;padding:13px 15px;background:{spec["panel"]};border-left:3px solid {spec["accent"]};',
        'ul': 'margin:8px 0 16px;padding-left:23px;', 'ol': 'margin:8px 0 16px;padding-left:25px;',
        'li': 'font-size:16px;line-height:1.85;margin:0 0 7px;',
        'strong': f'font-weight:700;color:{spec["accent"]};',
        'a': f'color:{spec["accent"]};text-decoration:underline;word-break:break-all;',
        'pre': 'margin:14px 0;padding:12px;background:#ecefe9;font-size:13px;line-height:1.6;white-space:pre-wrap;word-break:break-all;',
        'code': 'font-family:Consolas,monospace;font-size:0.9em;',
        'table': 'border-collapse:collapse;width:100%;font-size:14px;line-height:1.6;margin:14px 0;',
        'th': 'border:1px solid #cbd1c7;padding:7px;text-align:left;background:#edf0e9;',
        'td': 'border:1px solid #cbd1c7;padding:7px;word-break:break-word;',
        'hr': 'border:0;border-top:1px solid #d8ded3;margin:21px 0;'}
    for tag in soup.find_all(True):
        if tag.name not in ALLOWED_TAGS:
            raise ValueError('不支持的正文标签：' + tag.name)
        attrs = {k: v for k, v in tag.attrs.items() if k in ('src', 'href', 'alt', 'title', 'style')}
        if 'href' in attrs and urlparse(attrs['href']).scheme not in ('https', 'http'):
            raise ValueError('正文链接只支持HTTP(S)')
        tag.attrs = attrs
        if 'style' not in tag.attrs and tag.name in styles:
            tag['style'] = styles[tag.name]
    # Explicit leaf spans are compatible with the editor's rich-text paste model.
    for text in list(soup.find_all(string=True)):
        if text.strip() and text.parent.name not in ('span', 'code', 'pre'):
            leaf = soup.new_tag('span')
            leaf['leaf'] = ''
            text.wrap(leaf)
    root = soup.new_tag('section')
    root['style'] = f'max-width:677px;margin:0 auto;padding:0 18px 20px;box-sizing:border-box;background-color:{spec["background"]};color:#30382f;font-family:-apple-system,BlinkMacSystemFont,"Microsoft YaHei",sans-serif;'
    for item in list(soup.contents):
        root.append(item.extract())
    footer = soup.new_tag('p')
    footer['style'] = 'font-size:12px;line-height:1.7;color:#74776e;margin:22px 0 0;'
    body_photos = [p for p in photos if p['file'] in by_file and any(i.get('src') == '../' + p['file'] for i in root.find_all('img'))]
    uses = {p.get('usage') for p in body_photos}
    footer.string = ('正文照片为来源明确的摄影作品，仅作氛围示意；拍摄地与文章所述场景不作对应。' if uses == {'illustrative'} else
                     '正文图注标明素材用途；图库摄影不作真实活动现场记录，具体来源与使用依据按图片清单保留。')
    root.append(footer)
    if meta.get('layout') == 'campus-warm':
        campus_layout().style_article(soup, root, meta, photos, job=job)
    fragment = str(root)
    (job / 'build/article.wechat.html').write_text(fragment, encoding='utf-8')
    # Embedding is for local preview/clipboard staging only. API uploads replace local URLs.
    embedded = BeautifulSoup(fragment, 'html.parser')
    for image in embedded.find_all('img'):
        path = (job / 'build' / image['src']).resolve()
        if not path.is_relative_to(job.resolve()):
            raise ValueError('预览图片路径超出文章目录')
        mime = {'.gif': 'image/gif', '.png': 'image/png'}.get(path.suffix.lower(), 'image/jpeg')
        image['src'] = f'data:{mime};base64,' + base64.b64encode(path.read_bytes()).decode()
    def embed_background(match):
        path = (job / 'build' / unquote(match.group(2))).resolve()
        if not path.is_relative_to(job.resolve()) or not path.is_file():
            raise ValueError('预览背景超出文章目录或文件不存在')
        mime = 'image/png' if path.suffix.lower() == '.png' else 'image/jpeg'
        return "url('data:" + mime + ';base64,' + base64.b64encode(path.read_bytes()).decode() + "')"
    for node in embedded.find_all(style=True):
        if CSS_URL.search(node['style']):
            node['style'] = CSS_URL.sub(embed_background, node['style'])
    preview = '''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>推文预览</title><style>body{margin:0;padding:16px 0;background:#dce0d6}nav{max-width:677px;margin:0 auto 12px;padding:0 18px;font:14px/1.6 sans-serif;box-sizing:border-box}button{padding:8px 14px;cursor:pointer}#article{max-width:677px;margin:auto}small{display:block;margin-top:6px}</style></head><body><nav><button id="copy">复制动态正文</button> <button id="motion">播放首屏动效</button> <button id="static">静态查看</button><small>本地预览；照片需在公众号上传后替换。本地动效通过不代表微信客户端已验收。</small><output id="message"></output></nav><main id="article">''' + str(embedded) + '''</main><script>
const heroImage=document.querySelector('#article h1 img');const animatedHero=heroImage.src;
document.getElementById('copy').onclick=async()=>{const el=document.getElementById('article');heroImage.src=animatedHero;try{await navigator.clipboard.write([new ClipboardItem({'text/html':new Blob([el.innerHTML],{type:'text/html'}),'text/plain':new Blob([el.innerText],{type:'text/plain'})})]);document.getElementById('message').textContent='已复制。请粘贴后上传照片并核对动效。'}catch(e){const r=document.createRange();r.selectNodeContents(el);const s=getSelection();s.removeAllRanges();s.addRange(r);document.execCommand('copy');document.getElementById('message').textContent='已尝试复制；请在编辑器核对。'}};
document.getElementById('motion').onclick=()=>{heroImage.src=animatedHero;document.getElementById('message').textContent='正在播放首屏动效';};
document.getElementById('static').onclick=()=>{heroImage.src='title.png';document.getElementById('message').textContent='静态查看；复制正文时保留动效';};
</script></body></html>'''
    (job / 'build/preview.html').write_text(preview, encoding='utf-8')
    write_json(job / 'build/render.json', {'generated_at': now(), 'hero': hero,
        'theme': meta['theme'], 'input_sha256': source_fingerprint(job),
        'wechat_client_verified': False})


def audit(job):
    issues = []
    def add(rule, message, severity='error', file='article.md', line=None):
        issues.append({'rule': rule, 'severity': severity, 'file': file, 'line': line, 'message': message})
    meta = read_json(job / 'article.json')
    photos = read_json(job / 'photos.json')
    md = (job / 'article.md').read_text(encoding='utf-8-sig')
    soup = BeautifulSoup(mistune.create_markdown(escape=True)(md), 'html.parser')
    for n, line in enumerate(md.splitlines(), 1):
        for wrong, correct in TYPO.items():
            if wrong in line:
                add('ZH001', f'疑似错别字：{wrong}，请核对是否应为“{correct}”', line=n)
        if re.search(r'\{\{.+?\}\}|TODO|待补|待填写|占位|待插入', line, re.I):
            add('CONTENT001', '正文存在草稿或占位残留', line=n)
        if re.search(r'希望这.*帮助|作为.*语言模型|以下是.*文章|让我们拭目以待', line):
            add('STYLE001', '存在聊天残留或套话，请结合语义处理', 'warning', line=n)
    headings = soup.find_all(re.compile('^h[1-6]$'))
    if len(soup.find_all('h1')) != 1 or not headings or headings[0].get_text().strip() != meta.get('title'):
        add('STRUCT001', '需要且只能有一个与元数据一致的主标题')
    previous = 1
    for heading in headings:
        level = int(heading.name[1])
        if level > previous + 1:
            add('STRUCT002', '标题层级跳跃')
        previous = level
    if not meta.get('summary') or len(meta.get('summary', '')) > 120:
        add('META001', '需要1至120字摘要', file='article.json')
    if not 1 <= len(meta.get('title', '')) <= 64:
        add('META002', '标题必须为1至64字', file='article.json')
    if meta.get('theme') not in themes():
        add('THEME001', '未注册的主题', file='article.json')
    ids = [p.get('id') for p in photos]
    if len(set(ids)) != len(ids):
        add('PHOTO001', '照片编号重复', file='photos.json')
    refs = {im.get('src') for im in soup.find_all('img')}
    by_file = {p.get('file'): p for p in photos}
    for ref in refs:
        if ref not in by_file:
            add('PHOTO002', f'正文照片未登记：{ref}', file='photos.json')
    for photo in photos:
        if photo.get('file') not in refs and photo.get('id') != meta.get('hero_photo'):
            continue
        body_use = photo.get('file') in refs
        if body_use and photo.get('kind') != 'photo':
            add('PHOTO003', '正文及本示例标题照片必须登记为真实摄影，不能使用生图替代', file='photos.json')
        if not body_use and photo.get('kind') == 'generated-background':
            if not photo.get('generation_tool') or not photo.get('authenticity_basis'):
                add('PHOTO010', '生成背景须记录实际工具与生成身份', file='photos.json')
            continue
        for field in ('source_page', 'author', 'license', 'license_url', 'caption', 'authenticity_basis'):
            if not photo.get(field):
                add('PHOTO004', f'{photo.get("id")} 缺少 {field}', file='photos.json')
        for field in ('source_page', 'license_url'):
            if urlparse(photo.get(field, '')).scheme != 'https':
                add('PHOTO005', f'{field} 必须为HTTPS来源地址', file='photos.json')
        if not photo.get('source_checked') or not photo.get('visual_checked'):
            add('PHOTO006', f'{photo.get("id")} 尚未核对来源与图像', file='photos.json')
        for field, hash_field in (('file', 'sha256'), ('original_file', 'original_sha256')):
            try:
                path = local(job, photo[field])
                if not path.is_file() or digest(path) != photo.get(hash_field):
                    add('PHOTO007', '照片缺失或SHA-256发生变化：' + photo[field], file='photos.json')
                if field == 'file' and path.is_file():
                    with Image.open(path) as image:
                        if image.width < 720:
                            add('PHOTO008', '照片宽度低于720像素：' + photo[field], file='photos.json')
            except (ValueError, KeyError) as e:
                add('PHOTO009', str(e), file='photos.json')
    facts = read_json(job / 'facts.json')
    sources = {s.get('id'): s for s in facts.get('sources', [])}
    for claim in facts.get('claims', []):
        if not claim.get('text') or claim['text'] not in md:
            add('FACT001', '事实台账中的主张未在正文找到', file='facts.json')
        if not claim.get('sources') or any(s not in sources for s in claim.get('sources', [])):
            add('FACT002', '事实主张缺少已登记信源', file='facts.json')
    for source in sources.values():
        if not source.get('url', '').startswith('https://') or not source.get('checked_at'):
            add('FACT003', '信源缺少HTTPS链接或核对时间', file='facts.json')
    builds = job / 'build'
    if not (builds / 'article.wechat.html').exists():
        add('BUILD001', '尚未构建微信正文片段', file='build/')
    else:
        fragment = (builds / 'article.wechat.html').read_text(encoding='utf-8')
        tree = BeautifulSoup(fragment, 'html.parser')
        for tag in tree.find_all(True):
            if tag.name not in ALLOWED_TAGS or any(k.startswith('on') or k in ('id', 'class') for k in tag.attrs):
                add('HTML001', '正文包含不支持的标签或属性', file='build/article.wechat.html')
            style = tag.get('style', '')
            if re.search(r'@keyframes|animation:|position\s*:|display\s*:\s*grid|var\(', style):
                add('HTML002', '正文不能依赖网页专用布局或动画', file='build/article.wechat.html')
            if re.search(r'(?:margin|padding)(?:-top|-bottom)?\s*:\s*(?:[5-9]\d|\d{3,})px', style):
                add('LAYOUT001', '存在大间距，需要重新检查留白', file='build/article.wechat.html')
        # Verify source text survives transformation, excluding H1 replaced by its title GIF.
        source_copy = BeautifulSoup(str(soup), 'html.parser')
        for tag in source_copy.find_all('h1'):
            tag.decompose()
        compact = lambda s: re.sub(r'\s+', '', s)
        rendered = compact(tree.get_text())
        for block in source_copy.find_all(['p', 'h2', 'h3', 'li', 'th', 'td']):
            text = compact(block.get_text())
            if text and text not in rendered:
                add('HTML003', '排版遗漏正文：' + text[:35], file='build/article.wechat.html')
        if read_json(builds / 'render.json').get('input_sha256') != source_fingerprint(job):
            add('BUILD002', '输入或引擎变化后未重新构建', file='build/render.json')
    gif = builds / 'title.gif'
    if not gif.exists():
        add('MOTION001', '缺少动态主标题', file='build/title.gif')
    else:
        with Image.open(gif) as image:
            if getattr(image, 'n_frames', 1) < 2:
                add('MOTION002', '主标题GIF没有动画帧', file='build/title.gif')
        if gif.stat().st_size > 2 * 1024 * 1024:
            add('MOTION003', '标题GIF超过本地2MB预算', file='build/title.gif')
    fingerprint = source_fingerprint(job)
    review = read_json(job / 'review.json') if (job / 'review.json').exists() else {}
    if review.get('input_sha256') != fingerprint:
        add('REVIEW001', '复核记录未绑定当前输入与引擎；不得沿用旧通过状态', file='review.json')
    if not review.get('reviewer'):
        add('REVIEW002', '没有实际复核者', file='review.json')
    for stage in REVIEW_STAGES:
        item = review.get('stages', {}).get(stage, {})
        if item.get('status') != 'pass' or not item.get('notes'):
            add('REVIEW003', f'{stage} 尚未实际复核并记录依据', file='review.json')
    for finding in review.get('findings', []):
        if finding.get('status') not in ('resolved', 'accepted_with_reason'):
            add('REVIEW004', '仍有未关闭的语义审核问题', file='review.json')
    warnings = [i for i in issues if i['severity'] == 'warning']
    acknowledged = set(review.get('acknowledged_warnings', []))
    for issue in warnings:
        if issue['rule'] not in acknowledged:
            add('REVIEW005', f'尚未处置提示：{issue["rule"]}', file='review.json')
    report = {'generated_at': now(), 'input_sha256': fingerprint,
        'status': 'blocked' if any(i['severity'] == 'error' for i in issues) else 'ready_for_draft',
        'issues': issues, 'error_count': sum(i['severity'] == 'error' for i in issues),
        'warning_count': len(warnings), 'wechat_client_verified': review.get('wechat_verified') is True,
        'scope': '机器检查加已记录的代理语义校对；不证明绝对零错字或微信客户端兼容'}
    write_json(builds / 'audit.json', report)
    lines = ['# 推文审核报告', '', f'状态：{report["status"]}',
        f'错误：{report["error_count"]}；提示：{report["warning_count"]}',
        f'输入指纹：`{fingerprint}`', '', '| 等级 | 规则 | 文件/行 | 问题 |', '| --- | --- | --- | --- |']
    lines += [f'| {i["severity"]} | {i["rule"]} | {i["file"]}:{i.get("line") or ""} | {i["message"]} |' for i in issues]
    lines += ['', report['scope'], '', '微信后台、手机预览和最终发布状态分别记录，不由本报告代替。']
    (builds / '审核报告.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report


def build(job):
    meta = read_json(job / 'article.json')
    photos = read_json(job / 'photos.json')
    spec = themes()[meta['theme']]
    hero = make_hero(job, meta, photos, spec)
    render_article(job, meta, photos, spec, hero)
    return audit(job)


def export(job):
    report = audit(job)
    if report['status'] != 'ready_for_draft':
        raise ValueError('审核未通过，不能导出交付包；查看 build/审核报告.md')
    fingerprint = report['input_sha256']
    folder = job / ('delivery-' + fingerprint[:12])
    if folder.exists():
        raise ValueError('本指纹的交付包已存在，未覆盖；修改后请重新审核')
    folder.mkdir()
    for name in ('article.md', 'article.json', 'photos.json', 'facts.json', 'review.json', 'build', 'photos', 'designs'):
        src = job / name
        if name == 'designs' and not src.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, folder / name)
        else:
            shutil.copy2(src, folder / name)
    write_json(folder / 'manifest.json', {p.relative_to(folder).as_posix(): digest(p)
        for p in folder.rglob('*') if p.is_file()})
    return folder


def create_draft(job, upload=False):
    report = audit(job)
    if report['status'] != 'ready_for_draft':
        raise ValueError('审核未通过，草稿传输已阻止')
    meta = read_json(job / 'article.json')
    if upload and not meta.get('author'):
        raise ValueError('上传前需要用户提供实际署名；本流程不捏造身份')
    plan = {'status': 'dry_run', 'title': meta['title'], 'summary': meta['summary'],
        'input_sha256': report['input_sha256'], 'endpoint': 'https://api.weixin.qq.com/cgi-bin/draft/add',
        'html': str(job / 'build/article.wechat.html'), 'cover': str(job / 'build/cover.jpg'),
        'public_publish': False, 'credential_names': ['WECHAT_APP_ID', 'WECHAT_APP_SECRET']}
    if not upload:
        write_json(job / 'build/draft-plan.json', plan)
        return plan
    receipt = job / 'build/draft-receipt.json'
    if receipt.exists() and read_json(receipt).get('input_sha256') == report['input_sha256']:
        raise ValueError('当前内容已有草稿回执，不重复上传；先核对该草稿')
    progress = job / 'build/upload-progress.json'
    if progress.exists():
        previous = read_json(progress)
        if previous.get('input_sha256') == report['input_sha256'] and previous.get('status') == 'about_to_add_draft':
            raise ValueError('上次新增草稿结果未知，先核对后台；本工具不会自动重复提交')
    appid, secret = os.getenv('WECHAT_APP_ID'), os.getenv('WECHAT_APP_SECRET')
    if not appid or not secret:
        raise ValueError('没有公众号API凭据；可继续使用已登录Edge的后台路径')
    session = requests.Session()
    def api(endpoint, *, data=None, files=None, payload=None):
        # Never propagate exception strings containing secret-bearing request URLs.
        try:
            params = {'access_token': token}
            if endpoint.endswith('add_material'):
                params['type'] = 'image'
            response = session.post('https://api.weixin.qq.com/cgi-bin/' + endpoint,
                params=params, data=data if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                files=files, headers={'Content-Type': 'application/json; charset=utf-8'} if payload is not None else None,
                timeout=40)
            response.raise_for_status()
            result = response.json()
        except Exception:
            raise ValueError('微信请求未确认完成；核对后台后再重试，避免重复草稿') from None
        if result.get('errcode', 0):
            raise ValueError(f'微信接口 {endpoint} 返回错误码 {result["errcode"]}；按官方文档核对权限与IP白名单')
        return result
    try:
        response = session.get('https://api.weixin.qq.com/cgi-bin/token', params={
            'grant_type': 'client_credential', 'appid': appid, 'secret': secret}, timeout=30)
        response.raise_for_status()
        result = response.json()
        token = result.get('access_token')
        if not token:
            raise ValueError()
    except Exception:
        raise ValueError('微信凭据或网络校验失败；没有保存或输出密钥') from None
    content = BeautifulSoup((job / 'build/article.wechat.html').read_text(encoding='utf-8'), 'html.parser')
    uploads = []
    for image in content.find_all('img'):
        path = (job / 'build' / image['src']).resolve()
        if not path.is_relative_to(job.resolve()):
            raise ValueError('上传图片超出文章目录')
        # uploadimg only supports JPEG/PNG. Animated GIF uses permanent image material.
        endpoint = 'material/add_material' if path.suffix.lower() == '.gif' else 'media/uploadimg'
        with path.open('rb') as stream:
            result = api(endpoint, files={'media': (path.name, stream)})
        if not result.get('url'):
            raise ValueError('微信未返回图片URL；本次草稿未提交')
        image['src'] = result['url']
        uploads.append({'local': path.name, 'url': result['url']})
    background_uploads = []
    for node in content.find_all(style=True):
        style = node['style']
        for match in list(CSS_URL.finditer(style)):
            path = (job / 'build' / unquote(match.group(2))).resolve()
            if not path.is_relative_to(job.resolve()) or not path.is_file():
                raise ValueError('上传背景超出文章目录或文件不存在')
            with path.open('rb') as stream:
                result = api('media/uploadimg', files={'media': (path.name, stream)})
            if not result.get('url'):
                raise ValueError('微信未返回背景素材URL；本次草稿未提交')
            node['style'] = node['style'].replace(match.group(0), "url('" + result['url'] + "')")
            background_uploads.append({'local': path.name, 'url': result['url']})
    with (job / 'build/cover.jpg').open('rb') as stream:
        cover = api('material/add_material', files={'media': ('cover.jpg', stream)})
    article = {'title': meta['title'], 'author': meta['author'], 'digest': meta['summary'],
        'content': str(content), 'thumb_media_id': cover['media_id'],
        'need_open_comment': 0, 'only_fans_can_comment': 0}
    if meta.get('source_url'):
        article['content_source_url'] = meta['source_url']
    # Persist upload progress before the non-idempotent draft call.
    write_json(job / 'build/upload-progress.json', {'input_sha256': report['input_sha256'],
        'status': 'about_to_add_draft', 'images': uploads, 'backgrounds': background_uploads, 'at': now()})
    result = api('draft/add', payload={'articles': [article]})
    if not result.get('media_id'):
        raise ValueError('微信未返回草稿media_id；先在后台核对，不自动重复提交')
    plan.update(status='draft_created', media_id=result['media_id'], uploaded_at=now(), images=uploads, backgrounds=background_uploads,
                readback_verified=False)
    write_json(receipt, plan)
    write_json(progress, {'input_sha256': report['input_sha256'], 'status': 'draft_created',
        'media_id': result['media_id'], 'at': now()})
    try:
        readback = api('draft/get', payload={'media_id': result['media_id']})
        items = readback.get('news_item', [])
        returned_images = BeautifulSoup(items[0].get('content', ''), 'html.parser').find_all('img') if items else []
        returned_urls = [im.get('src', '') for im in returned_images]
        plan['readback_title_matches'] = bool(items and items[0].get('title') == meta['title'])
        plan['readback_image_count'] = len(returned_images)
        plan['readback_images_match'] = returned_urls == [im['url'] for im in uploads]
        returned_backgrounds = [match.group(2) for node in BeautifulSoup(items[0].get('content', ''), 'html.parser').find_all(style=True) for match in CSS_URL.finditer(node['style'])] if items else []
        plan['readback_backgrounds_match'] = returned_backgrounds == [bg['url'] for bg in background_uploads]
        plan['readback_verified'] = plan['readback_title_matches'] and plan['readback_images_match'] and plan['readback_backgrounds_match']
        plan['readback_scope'] = '草稿标题、图片及背景素材URL与数量顺序；不等于视觉或动效验收'
        plan['visual_verified'] = False
    except ValueError:
        plan['readback_note'] = '新增草稿成功，读回未确认；先到后台核对，不重复提交'
    write_json(receipt, plan)
    return plan


def main():
    parser = argparse.ArgumentParser(description='公众号制作、排版、审核与草稿工具')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('themes')
    p = sub.add_parser('init'); p.add_argument('job', type=Path); p.add_argument('--theme', choices=list(themes()), required=True); p.add_argument('--topic', required=True)
    p = sub.add_parser('photo'); p.add_argument('job', type=Path); p.add_argument('--page', required=True); p.add_argument('--author', required=True); p.add_argument('--id', required=True); p.add_argument('--license', required=True); p.add_argument('--license-url', required=True); p.add_argument('--image-url', help='仅限已从源页核实的原图URL')
    for command in ('fingerprint', 'build', 'audit', 'export', 'draft'):
        p = sub.add_parser(command); p.add_argument('job', type=Path)
        if command == 'draft': p.add_argument('--upload', action='store_true')
    args = parser.parse_args()
    if args.command == 'themes': result = {k: v['name'] for k, v in themes().items()}
    elif args.command == 'init': init_job(args.job.resolve(), args.theme, args.topic); result = {'job': str(args.job.resolve())}
    elif args.command == 'photo': result = str(download_photo(args.job.resolve(), args.page, args.author, args.id, args.license, args.license_url, args.image_url))
    elif args.command == 'fingerprint': result = source_fingerprint(args.job.resolve())
    elif args.command == 'build': result = build(args.job.resolve())
    elif args.command == 'audit': result = audit(args.job.resolve())
    elif args.command == 'export': result = str(export(args.job.resolve()))
    else: result = create_draft(args.job.resolve(), args.upload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if isinstance(result, dict) and result.get('status') == 'blocked':
        return 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, requests.RequestException) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
