"""Warm illustrated report layout, adapted from the user's campus-article reference.

The generated title background is separate from the unchanged body photographs.
This module has no browser, account, or publishing operations.
"""
from __future__ import annotations

import os
import hashlib
import math
from pathlib import Path
from urllib.parse import quote, urlparse

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps, ImageFilter


FONT = Path(os.environ.get('WECHAT_TITLE_FONT', 'C:/Windows/Fonts/msyhbd.ttc'))
CREAM = '#FFEFDB'
INK = '#7A1C0D'


def _local(job, name):
    if not isinstance(name, str) or not name or urlparse(name).scheme or Path(name).is_absolute():
        raise ValueError('插画背景必须使用文章目录内的相对路径')
    result = (Path(job) / name).resolve()
    if not result.is_relative_to(Path(job).resolve()):
        raise ValueError('插画背景路径超出文章目录')
    return result


def _wrap(text, font, width):
    lines = ['']
    for char in text:
        if lines[-1] and font.getlength(lines[-1] + char) > width:
            lines.append(char)
        else:
            lines[-1] += char
    return lines


def _title_fit(meta, width, maximum=82, minimum=44):
    title = meta['title']
    explicit = meta.get('hero_title_lines')
    if explicit is not None:
        if (not isinstance(explicit, list) or not explicit or len(explicit) > 3
                or any(not isinstance(line, str) or not line or '\n' in line for line in explicit)
                or ''.join(explicit) != title):
            raise ValueError('hero_title_lines须为最多三行，拼合后与主标题完全一致')
    for size in range(maximum, minimum - 1, -2):
        font = ImageFont.truetype(str(FONT), size)
        lines = explicit or _wrap(title, font, width)
        if len(lines) <= 3 and all(font.getlength(line) <= width for line in lines):
            return lines, font, size
    raise ValueError('标题过长，无法在暖色封面的安全区内完整显示')


def _small_fit(text, width, maximum=28, minimum=19):
    for size in range(maximum, minimum - 1, -1):
        font = ImageFont.truetype(str(FONT), size)
        if font.getlength(text) <= width:
            return font
    raise ValueError('副标题过长，无法在封面安全区内完整显示')


def _center(draw, y, text, font, color=INK, width=1000, x_offset=0):
    origin = ((width - font.getlength(text)) / 2 + x_offset, y)
    draw.text(origin, text, font=font, fill=color)
    return draw.textbbox(origin, text, font=font)


def _editorial_motion(base, phase):
    """Visible cloud/light movement stays below the always-readable title area."""
    overlay = Image.new('RGBA', base.size)
    painter = ImageDraw.Draw(overlay)
    glow = Image.new('RGBA', base.size)
    glow_draw = ImageDraw.Draw(glow)
    strength = .5 + .5 * math.sin(phase)
    radius = 70 + 12 * strength
    for size in range(round(radius), 0, -4):
        alpha = round((1-size/(radius+1)) * (28+25*strength))
        glow_draw.ellipse((722-size, 610-size, 722+size, 610+size), fill=(255, 226, 152, alpha))
    overlay = Image.alpha_composite(overlay, glow.filter(ImageFilter.GaussianBlur(5)))
    painter = ImageDraw.Draw(overlay)
    for cx, cy, offset in ((280, 552, 0), (825, 546, 2.1)):
        dx = 34 * math.sin(phase + offset)
        dy = 5 * math.cos(phase + offset)
        x, y = cx + dx, cy + dy
        pale = (255, 240, 199, 145)
        gold = (239, 190, 105, 140)
        painter.arc((x-94, y-11, x-25, y+29), 175, 355, fill=pale, width=3)
        painter.arc((x-42, y-31, x+34, y+24), 180, 355, fill=pale, width=3)
        painter.arc((x+11, y-5, x+85, y+29), 185, 360, fill=pale, width=3)
        painter.line([(x-142,y+28),(x+115,y+28),(x+139,y+22)],fill=pale,width=3)
        painter.line([(x-115,y+36),(x+90,y+36)],fill=gold,width=2)
    for index, (cx, cy) in enumerate(((87, 720), (925, 835), (114, 1032), (901, 1080))):
        x = cx + 12 * math.sin(phase + index)
        y = cy + 20 * math.cos(phase + index*.8)
        painter.polygon([(x,y-8),(x+5,y),(x,y+8),(x-5,y)],fill=(255,222,151,125))
    return Image.alpha_composite(base.convert('RGBA'), overlay).convert('RGB')


def _save_motion_gif(frames, path, duration):
    """Transparent deltas retain detailed paper art without repeating it per frame."""
    palette = frames[0].getpalette()
    deltas = []
    previous = frames[0]
    for frame in frames[1:]:
        red, green, blue = ImageChops.difference(previous.convert('RGB'), frame.convert('RGB')).split()
        changed = ImageChops.lighter(ImageChops.lighter(red, green), blue).point([0] + [255]*255)
        delta = Image.new('P', frame.size, 255)
        delta.putpalette(palette)
        delta.paste(frame, (0, 0), changed)
        delta.info['transparency'] = 255
        deltas.append(delta)
        previous = frame
    frames[0].save(path, save_all=True, append_images=deltas, duration=duration,
                   loop=0, disposal=1, transparency=255, optimize=False)


def make_hero(job, meta, photos, spec):
    """Write a portrait GIF/title PNG and a separately composed landscape cover.

    Requires meta.hero_background and title; optional hero_title_lines, hero_kicker,
    subtitle. The background must already be registered by the caller as generated.
    """
    if not FONT.is_file():
        raise ValueError('缺少中文标题字体，请设置WECHAT_TITLE_FONT')
    job = Path(job)
    background_path = _local(job, meta.get('hero_background'))
    if not background_path.is_file():
        raise ValueError('暖色插画背景文件不存在')
    with Image.open(background_path) as source:
        background = ImageOps.fit(source.convert('RGB'), (1000, 1260))
    out = job / 'build'
    out.mkdir(exist_ok=True)
    lines, font, font_size = _title_fit(meta, 850)
    kicker = meta.get('hero_kicker', spec.get('name', ''))
    kicker_font = _small_fit(kicker, 850, 30, 23)
    subtitle = meta.get('subtitle', '')
    subtitle_lines = meta.get('hero_subtitle_lines', [subtitle] if subtitle else [])
    if (not isinstance(subtitle_lines, list) or len(subtitle_lines) > 2
            or any(not isinstance(line, str) or not line or '\n' in line for line in subtitle_lines)
            or ''.join(subtitle_lines) != subtitle):
        raise ValueError('hero_subtitle_lines须最多两行，拼合后与副标题完全一致')
    split_subtitle = len(subtitle_lines) > 1
    subtitle_font = _small_fit(subtitle, 850, 26 if split_subtitle else 32, 22 if split_subtitle else 24)
    text_offset = float(meta.get('hero_text_offset', 0))
    if abs(text_offset) > 80:
        raise ValueError('标题偏移超出封面安全范围')

    base = background.copy()
    draw = ImageDraw.Draw(base)
    text_boxes = []
    if kicker:
        text_boxes.append(_center(draw, 116, kicker, kicker_font, '#713019', x_offset=text_offset))
    title_top = float(meta.get('hero_title_top', 205 if len(lines) <= 2 else 170))
    if not math.isfinite(title_top) or not 140 <= title_top <= 230:
        raise ValueError('主标题顶部须在封面140至230px之间')
    for index, line in enumerate(lines):
        text_boxes.append(_center(draw, title_top + index * (font_size + 24), line, font, x_offset=text_offset))
    for index, line in enumerate(subtitle_lines):
        text_boxes.append(_center(draw, title_top + len(lines) * (font_size + 24) + 24
                                 + index * (subtitle_font.size + 10),
                line, subtitle_font, '#713019', x_offset=text_offset))

    motion = meta.get('hero_motion', 'accent')
    if motion not in ('accent', 'editorial-motion'):
        raise ValueError('未知的首屏动效预设')
    if any(box[0] < 32 or box[2] > 968 or (motion == 'editorial-motion' and box[3] > 500)
           for box in text_boxes):
        raise ValueError('封面文字超出安全区域，请调整标题位置或缩短文字')
    count, duration = (32, 120) if motion == 'editorial-motion' else (28, 110)
    # The whole title stays visible; editorial movement never crosses its text area.
    frames = []
    palette = None
    for index in range(count):
        phase = 2*math.pi*index/count
        frame = _editorial_motion(base, phase) if motion == 'editorial-motion' else base.copy()
        painter = ImageDraw.Draw(frame)
        painter.rounded_rectangle((155, 1208, 845, 1212), radius=2, fill='#DDB58B')
        progress = (.5-.5*math.cos(phase)) if motion == 'editorial-motion' else index/(count-1)
        x = 155 + round((690 - 112) * progress)
        painter.rounded_rectangle((x, 1205, x + 112, 1215), radius=5, fill='#D86736')
        if palette is None:
            palette = frame.quantize(colors=128, dither=Image.Dither.NONE)
        frames.append(frame.quantize(palette=palette, dither=Image.Dither.NONE))
    if motion == 'editorial-motion':
        _save_motion_gif(frames, out / 'title.gif', duration)
    else:
        frames[0].save(out / 'title.gif', save_all=True, append_images=frames[1:],
                       duration=duration, loop=0, optimize=True, disposal=1)
    if (out / 'title.gif').stat().st_size > 2 * 1024 * 1024:
        raise ValueError('暖色主标题GIF超过2MB预算；请先优化背景尺寸或颜色')
    frames[0].convert('RGB').save(out / 'title.png')

    # Landscape cover has its own text layout. A center crop of the portrait
    # would remove the complete main title and is deliberately not used.
    cover = Image.new('RGB', (1000, 426), CREAM)
    art = ImageOps.fit(background, (420, 426), centering=(0.5, 0.8))
    cover.paste(art, (580, 0))
    painter = ImageDraw.Draw(cover)
    painter.rectangle((0, 0, 590, 426), fill=CREAM)
    painter.rectangle((0, 0, 1000, 7), fill='#E77F45')
    cover_lines, cover_font, cover_size = _title_fit(meta, 520, 62, 36)
    if kicker:
        painter.text((43, 39), kicker, font=ImageFont.truetype(str(FONT), 23), fill='#A3502D')
    for index, line in enumerate(cover_lines):
        painter.text((43, 113 + index * (cover_size + 15)), line, font=cover_font, fill=INK)
    if subtitle:
        sub = _small_fit(subtitle, 510, 20, 15)
        painter.text((43, 354), subtitle, font=sub, fill='#9C4F2C')
    cover.save(out / 'cover.jpg', quality=91, optimize=True)
    return {'frames': count, 'duration_ms': count*duration, 'motion': motion, 'font': str(FONT), 'font_size': font_size,
            'lines': lines, 'background_file': meta['hero_background'],
            'title_top': title_top, 'text_x_offset': text_offset, 'text_boxes': text_boxes,
            'subtitle_lines': subtitle_lines,
            'layout': 'campus-warm', 'dimensions': [1000, 1260],
            'static_region': [0, 0, 1000, 500] if motion == 'editorial-motion' else [0, 0, 1000, 1180],
            'cover_composition': 'separate_landscape'}


def _photo_parts(root, photo):
    matches = [image for image in root.find_all('img')
               if image.get('src') in (photo['file'], '../' + photo['file'])]
    if len(matches) != 1:
        raise ValueError('双图组合的照片必须在正文独立出现一次：' + photo['id'])
    image = matches[0]
    wrapper = image.parent if image.parent.name == 'p' else image
    if wrapper is not image and wrapper.get_text(strip=True):
        raise ValueError('双图组合仅支持独立的图片段落：' + photo['id'])
    caption = wrapper.find_next_sibling()
    if caption is None or caption.name != 'p' or '｜摄影：' not in caption.get_text():
        raise ValueError('双图照片缺少原来源图注：' + photo['id'])
    return image, wrapper, caption


def _pair_photos(soup, root, meta, photos, job=None):
    staggered = meta.get('body_layout') == 'ornament-staggered'
    rhythm = meta.get('body_layout') == 'editorial-rhythm'
    tables = []
    used = set()
    registry = {photo['id']: photo for photo in photos}
    for pair in meta.get('photo_duos' if rhythm else 'photo_pairs', []):
        if not isinstance(pair, list) or len(pair) != 2 or pair[0] == pair[1]:
            raise ValueError('photo_pairs每组必须为两个不同照片ID')
        if any(identifier not in registry or identifier in used for identifier in pair):
            raise ValueError('双图照片ID缺失或在多组中重复')
        parts = [_photo_parts(root, registry[identifier]) for identifier in pair]
        if rhythm:
            if parts[0][2].find_next_sibling() is not parts[1][1]:
                raise ValueError('同题双图须在源稿相邻，不能跨段落或跨章节搬图')
            if job is None:
                raise ValueError('同题双图需要文章目录核对照片比例')
            ratios = []
            for identifier in pair:
                with Image.open(_local(job, registry[identifier]['file'])) as picture:
                    ratios.append(picture.height / picture.width)
            if abs(ratios[0] - ratios[1]) > .2:
                raise ValueError('同题双图需使用相近纵横比，避免一张照片过小或悬空')
        order = list(root.find_all('img'))
        anchor = min(parts, key=lambda part: order.index(part[0]))[1]
        table = soup.new_tag('table')
        table['style'] = 'width:100%;table-layout:fixed;border-collapse:collapse;border:0;margin:9px 0 13px;'
        if rhythm:
            table['style'] = 'width:100%;table-layout:fixed;border-collapse:collapse;border:0;margin:12px 0 0;'
        row = soup.new_tag('tr')
        table.append(row)
        tables.append(table)
        anchor.insert_before(table)
        for index, (image, wrapper, caption) in enumerate(parts):
            cell = soup.new_tag('td')
            cell_width = ((52 if index == 0 else 48) if rhythm else
                          (36 if index == 0 else 64) if staggered else 50)
            cell['style'] = (f'width:{cell_width}%;vertical-align:top;border:0;text-indent:0;'
                             + ('padding:0 5px 0 0;' if index == 0 else
                                'padding:16px 0 0 5px;' if staggered or rhythm else 'padding:0 0 0 5px;'))
            image.extract()
            image['style'] = 'width:100%;max-width:100%;height:auto;display:block;margin:0 auto;box-sizing:border-box;border:1px solid #E8D8C5;border-radius:0;'
            cell.append(image)
            if wrapper is not image:
                wrapper.decompose()
            caption.extract()
            caption['style'] = ('font-size:10.5px;line-height:1.65;color:#8B7868;margin:5px 0 0;'
                                'text-indent:0;letter-spacing:0;word-break:break-word;text-align:left;')
            cell.append(caption)
            row.append(cell)
        used.update(pair)
    return tables


def _ornament(soup, job, identifier, photos, width, margin):
    """Use a registered transparent illustration without treating it as photography."""
    matches = [photo for photo in photos if photo.get('id') == identifier]
    if len(matches) != 1:
        raise ValueError('正文点缀须在photos中唯一登记：' + str(identifier))
    record = matches[0]
    if (record.get('kind') != 'generated-decoration' or record.get('usage') != 'decoration_only'
            or not record.get('generation_tool') or not record.get('authenticity_basis')):
        raise ValueError('点缀须标明生成插画、实际工具和decoration_only用途')
    if job is None:
        raise ValueError('正文点缀需要文章目录job核对素材')
    path = _local(job, record.get('file'))
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != record.get('sha256'):
        raise ValueError('正文点缀缺失或SHA-256与登记不一致')
    with Image.open(path) as picture:
        if path.suffix.lower() != '.png' or picture.mode != 'RGBA' or picture.getchannel('A').getextrema()[0] != 0:
            raise ValueError('正文点缀须为保留透明背景的RGBA PNG')
    section = soup.new_tag('section')
    section['style'] = 'margin:' + margin + ';padding:0;text-align:center;line-height:1;'
    image = soup.new_tag('img', src='../' + path.relative_to(Path(job).resolve()).as_posix(),
                         alt=record.get('caption', '生成装饰插画'))
    image['style'] = f'width:{width}px;max-width:100%;height:auto;display:block;margin:0 auto;border:0;border-radius:0;'
    section.append(image)
    return section


def _quote_companion(soup, root, meta, photos, job):
    companion = meta.get('quote_photo')
    if not companion:
        return
    if not isinstance(companion, dict) or not companion.get('id') or not companion.get('quote'):
        raise ValueError('quote_photo需要照片ID与源稿已有短引文')
    registered = [p for p in photos if p.get('id') == companion['id'] and p.get('kind') == 'photo']
    quotes = [q for q in root.find_all('blockquote') if q.get_text(strip=True) == companion['quote']]
    if len(registered) != 1 or len(quotes) != 1:
        raise ValueError('照片与短引文须在源稿中唯一出现，不生成替代文案')
    matches = root.find_all('img', src='../' + registered[0]['file'])
    if len(matches) != 1 or matches[0].parent.name != 'p':
        raise ValueError('引文配图须为未参加其他组合的独立摄影')
    image = matches[0]
    wrapper = image.parent
    caption = wrapper.find_next_sibling()
    quote = quotes[0]
    if quote.find_next_sibling() is not wrapper or caption is None or caption.name != 'p':
        raise ValueError('照片须在源稿紧跟已有短引文，不跨正文段落搬图')
    table = soup.new_tag('table')
    table['style'] = 'width:100%;table-layout:fixed;border-collapse:collapse;border:0;margin:14px 0 0;'
    row = soup.new_tag('tr')
    table.append(row)
    quote.insert_before(table)
    left = soup.new_tag('td')
    left['style'] = 'width:48%;vertical-align:top;padding:0 6px 0 0;border:0;text-indent:0;'
    right = soup.new_tag('td')
    right['style'] = 'width:52%;vertical-align:middle;padding:0 0 0 6px;border:0;text-indent:0;'
    image.extract()
    image['style'] = 'width:100%;max-width:100%;height:auto;display:block;margin:0 auto;box-sizing:border-box;border:1px solid #E6D8C5;border-radius:2px;'
    left.append(image)
    wrapper.decompose()
    quote.extract()
    quote['style'] = 'margin:0;padding:0;background-color:#FFFFFF;border:0;'
    for paragraph in quote.find_all('p'):
        paragraph['style'] = 'font-size:16px;font-weight:500;line-height:1.8;color:#985335;letter-spacing:0.25px;text-indent:0;text-align:center;margin:0;'
    right.append(quote)
    leaf = meta.get('body_ornaments', {}).get('quote')
    if leaf:
        right.append(_ornament(soup, job, leaf, photos, 38, '10px 0 0'))
    row.extend([left, right])
    caption.extract()
    caption['style'] = 'font-size:11.5px;line-height:1.5;color:#827563;margin:6px 0 14px;text-indent:0;letter-spacing:0;text-align:left;'
    table.insert_after(caption)


def _frame_background_style(job, meta, photos):
    name = meta.get('frame_background')
    if not name:
        return ''
    if job is None:
        raise ValueError('正文纹理背景需要文章目录job以核对素材')
    path = _local(job, name)
    if not path.is_file():
        raise ValueError('正文纹理背景文件不存在')
    registered = []
    for photo in photos:
        try:
            if _local(job, photo.get('file')) == path:
                registered.append(photo)
        except ValueError:
            continue
    if len(registered) != 1:
        raise ValueError('正文纹理背景须在photos中唯一登记')
    record = registered[0]
    tool = record.get('generation_tool')
    if record.get('kind') != 'generated-background' or not isinstance(tool, str) or not tool.strip():
        raise ValueError('正文纹理须标明generated-background与实际生图工具')
    if hashlib.sha256(path.read_bytes()).hexdigest() != record.get('sha256'):
        raise ValueError('正文纹理背景SHA-256与登记不一致')
    relative = path.relative_to(Path(job).resolve()).as_posix()
    source = quote('../' + relative, safe='/-._~')
    return ("background-image:url('" + source + "');background-size:100% auto;"
            'background-repeat:repeat-y;')


def style_article(soup, root, meta, photos, job=None):
    """Restyle an existing section in-place without removing text or photo credits.

    Call after the common renderer has inserted the photo captions and footer,
    but before it serializes HTML or embeds images. No classes or IDs are added.
    A supplied frame_background requires job and a matching generated asset record.
    """
    frame_style = _frame_background_style(job, meta, photos)
    body_layout = meta.get('body_layout', 'classic')
    if body_layout not in ('classic', 'ornament-staggered', 'editorial-flow', 'editorial-rhythm'):
        raise ValueError('未知的正文版式预设')
    staggered = body_layout == 'ornament-staggered'
    rhythm = body_layout == 'editorial-rhythm'
    flow = body_layout in ('editorial-flow', 'editorial-rhythm')
    if not rhythm and (meta.get('photo_duos') or meta.get('quote_photo')):
        raise ValueError('photo_duos与quote_photo仅用于editorial-rhythm，避免遗留组合指令被忽略')
    if flow and meta.get('photo_pairs'):
        raise ValueError('editorial-flow按源稿图位依次展示单图，请清空photo_pairs')
    ornaments = meta.get('body_ornaments', {})
    if not isinstance(ornaments, dict) or set(ornaments) - {'intro', 'photo', 'quote'}:
        raise ValueError('body_ornaments仅支持intro、photo与quote点缀位置')
    if ornaments.get('quote') and not (rhythm and meta.get('quote_photo')):
        raise ValueError('引文点缀需要editorial-rhythm中的已有引文配图')
    title = root.find('h1')
    if title is None or title.find('img') is None:
        raise ValueError('暖色版式需要已有动态主标题')
    photo_tables = _pair_photos(soup, root, meta, photos, job=job)
    registry = {photo['file']: photo for photo in photos if photo.get('kind') == 'photo'}
    caption_ids = set()
    credits = []
    portrait_images = []
    for image in root.find_all('img'):
        source = image.get('src', '')
        photo = registry.get(source[3:] if source.startswith('../') else source)
        if photo is None:
            continue
        wrapper = image.parent if image.parent.name == 'p' else image
        caption = wrapper.find_next_sibling()
        if caption is None or caption.name != 'p' or '｜摄影：' not in caption.get_text():
            raise ValueError('摄影图注或来源信息缺失，不能只缩短后丢弃来源')
        label = '①②③④⑤⑥⑦⑧⑨'[len(credits)] if len(credits) < 9 else str(len(credits)+1)
        caption.clear()
        leaf = soup.new_tag('span')
        leaf['leaf'] = ''
        leaf.string = label + ' ' + photo['caption'].removesuffix('，氛围配图')
        caption.append(leaf)
        caption_ids.add(id(caption))
        credits.append((label, photo))
        dimensions = photo.get('original_dimensions', [])
        if job is not None:
            with Image.open(_local(job, photo['file'])) as picture:
                dimensions = picture.size
        if len(dimensions) == 2 and dimensions[1] > dimensions[0] and image.find_parent('td') is None:
            portrait_images.append((image, caption))
    for paragraph in root.find_all('p'):
        text = paragraph.get_text(strip=True)
        if id(paragraph) in caption_ids:
            paragraph['style'] = 'font-size:12px;line-height:1.55;color:#756B60;margin:6px 0 13px;text-indent:0;letter-spacing:0;text-align:left;'
            if flow:
                paragraph['style'] = 'font-size:11.5px;line-height:1.5;color:#827563;margin:6px 0 12px;text-indent:0;letter-spacing:0;text-align:left;'
        elif paragraph.find('img'):
            paragraph['style'] = 'margin:10px 0 0;text-indent:0;line-height:1;'
        elif text.startswith(('正文照片为', '正文图注标明')):
            paragraph['style'] = 'font-size:11px;line-height:1.7;color:#8B7868;margin:17px 0 0;text-indent:0;letter-spacing:0.2px;text-align:left;'
            if ornaments:
                paragraph.append(' 页内小插画为生成装饰。')
        else:
            paragraph['style'] = 'font-size:17px;font-weight:400;line-height:1.83;color:#363A35;letter-spacing:0.25px;text-indent:2em;text-align:justify;margin:0 0 12px;word-break:break-word;'
            if staggered:
                paragraph['style'] = 'font-size:17px;font-weight:400;line-height:1.88;color:#363A35;letter-spacing:0.35px;text-indent:2em;text-align:justify;margin:0 0 10px;word-break:break-word;'
            if flow:
                paragraph['style'] = 'font-size:17px;font-weight:400;line-height:1.85;color:#363A35;letter-spacing:0.2px;text-indent:2em;text-align:justify;margin:0 0 10px;word-break:break-word;'
            if paragraph.find_parent(['blockquote', 'li', 'td']) is not None:
                paragraph['style'] += 'text-indent:0;'
    for heading in root.find_all(['h2', 'h3']):
        heading['style'] = 'font-size:18px;line-height:1.6;font-weight:600;color:#982410;margin:18px 0 9px;padding:0;border:0;text-align:left;'
        if flow:
            heading['style'] = 'font-size:18px;line-height:1.6;font-weight:600;color:#8B3724;margin:20px 0 10px;padding:0 0 5px;border:0;border-bottom:1px solid #EEDFC9;text-align:left;'
    for quote in root.find_all('blockquote'):
        quote['style'] = 'margin:12px 0;padding:9px 12px;background-color:#FFF5E8;border-left:2px solid #DF9667;'
        if staggered or flow:
            quote['style'] = 'margin:14px 0;padding:9px 6px;background-color:#FFFFFF;border-top:1px solid #E8D8C5;border-bottom:1px solid #E8D8C5;'
            for paragraph in quote.find_all('p'):
                paragraph['style'] = 'font-size:16px;font-weight:500;line-height:1.8;color:#985335;letter-spacing:0.25px;text-indent:0;text-align:center;margin:0;'
    for image in root.find_all('img'):
        if image.find_parent('h1') is None and image.find_parent('td') is None:
            image['style'] = 'max-width:100%;height:auto;display:block;margin:0 auto;box-sizing:border-box;border:1px solid #DE6B3B;border-radius:3px;'
            if flow:
                image['style'] = 'width:100%;max-width:100%;height:auto;display:block;margin:0 auto;box-sizing:border-box;border:1px solid #E6D8C5;border-radius:2px;'
    for image, caption in portrait_images:
        if flow:
            image['style'] = 'width:72%;max-width:300px;height:auto;display:block;margin:0 auto;box-sizing:border-box;border:1px solid #E6D8C5;border-radius:2px;'
            caption['style'] += 'width:72%;max-width:300px;margin:6px auto 14px;'
        else:
            image['style'] = 'width:68%;max-width:320px;height:auto;display:block;margin:0 auto;box-sizing:border-box;border:1px solid #DE6B3B;border-radius:3px;'
            caption['style'] += 'width:68%;max-width:320px;margin:6px auto 14px;'
    if rhythm:
        for table in photo_tables:
            captions = table.find_all('p')
            combined = soup.new_tag('p')
            combined['style'] = 'font-size:11.5px;line-height:1.6;color:#827563;margin:6px 0 14px;text-indent:0;letter-spacing:0;text-align:left;'
            leaf = soup.new_tag('span')
            leaf['leaf'] = ''
            leaf.string = '；'.join(caption.get_text(strip=True) for caption in captions)
            combined.append(leaf)
            for caption in captions:
                caption.decompose()
            table.insert_after(combined)
        _quote_companion(soup, root, meta, photos, job)
    if ornaments.get('photo'):
        if not photo_tables:
            raise ValueError('照片点缀需要已有双图组合')
        photo_tables[0].find('td').append(_ornament(soup, job, ornaments['photo'], photos, 46, '4px 0 0'))
    title['style'] = 'margin:0;padding:0;font-size:24px;line-height:1.3;'
    title.img['style'] = 'width:100%;max-width:100%;height:auto;display:block;margin:0;border:0;border-radius:0;'

    title.extract()
    panel = soup.new_tag('section')
    panel['style'] = ('width:90%;margin:0 5%;padding:' + ('12px' if staggered else '18px')
                      + ' 4% 22px;box-sizing:border-box;background-color:#FFFFFF;')
    content = panel
    if flow:
        panel['style'] = ('width:94%;margin:0 3%;padding:0 1.25% 22px;box-sizing:border-box;'
                          'background-color:#FFF7EB;background-image:linear-gradient(90deg,'
                          '#FFF1DC 0%,#FFFDF8 3%,#FFFFFF 6%,#FFFFFF 94%,#FFFDF8 97%,#FFF1DC 100%);')
        content = soup.new_tag('section')
        content['style'] = 'padding:12px 4% 18px;box-sizing:border-box;'
        panel.append(content)
    if ornaments.get('intro'):
        ornament = _ornament(soup, job, ornaments['intro'], photos, 76, '0 0 8px')
    else:
        ornament = soup.new_tag('section')
        ornament['style'] = 'width:34px;height:2px;margin:0 auto 14px;background-color:#D86A3B;'
    content.append(ornament)
    for item in list(root.contents):
        content.append(item.extract())
    root['style'] = 'max-width:677px;margin:0 auto;padding:0 0 22px;box-sizing:border-box;background-color:#FFEFDB;color:#363A35;font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei","Noto Sans CJK SC",Arial,sans-serif;'
    if frame_style:
        root['style'] += frame_style
    root.append(title)
    root.append(panel)
    if credits:
        section = soup.new_tag('section')
        section['style'] = 'margin:16px 0 0;padding:12px 0 0;border-top:1px solid #E8D8C5;'
        label = soup.new_tag('p')
        label['style'] = 'font-size:12px;font-weight:600;line-height:1.7;color:#756B60;margin:0 0 5px;text-indent:0;'
        label.string = '摄影来源'
        section.append(label)
        for number, photo in credits:
            line = soup.new_tag('p')
            line['style'] = 'font-size:11.5px;line-height:1.7;color:#756B60;margin:0 0 5px;text-indent:0;letter-spacing:0;word-break:break-word;'
            leaf = soup.new_tag('span')
            leaf['leaf'] = ''
            leaf.string = number + ' 摄影：' + photo['author'] + ' · ' + urlparse(photo['source_page']).netloc + ' · '
            line.append(leaf)
            for index, (text, url) in enumerate((('原图', photo['source_page']), ('许可', photo['license_url']))):
                if index:
                    line.append(' · ')
                link = soup.new_tag('a', href=url)
                link['style'] = 'color:#8F553B;text-decoration:underline;'
                link.string = text
                line.append(link)
            section.append(line)
        content.append(section)
    if meta.get('author'):
        author = soup.new_tag('p')
        author['style'] = 'font-size:12px;line-height:1.8;text-align:center;margin:16px 5% 0;color:#6E5140;text-indent:0;'
        leaf = soup.new_tag('span')
        leaf['leaf'] = ''
        leaf.string = '作者：' + str(meta['author'])
        author.append(leaf)
        root.append(author)
    return root
