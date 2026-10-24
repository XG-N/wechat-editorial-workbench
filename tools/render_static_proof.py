"""Draw a static mobile typesetting proof from our limited article vocabulary.

This is a Pillow document compositor, not a browser screenshot or WeChat test.
It never connects to a browser, executes JavaScript, or fetches remote assets.
"""
from pathlib import Path
import argparse
import re

from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

parser = argparse.ArgumentParser()
parser.add_argument('job', type=Path)
parser.add_argument('--width', type=int, default=375)
args = parser.parse_args()
job = args.job.resolve()
soup = BeautifulSoup((job / 'build/article.wechat.html').read_text(encoding='utf-8'), 'html.parser')
root = soup.section
if '#FFEFDB' not in root.get('style', ''):
    raise SystemExit('This proof compositor is scoped to the campus-warm layout')
if not 320 <= args.width <= 677:
    raise SystemExit('静态校样宽度范围为320至677 CSS像素')
scale, width = 2, args.width * 2
canvas = Image.new('RGB', (width, 20000), '#FFEFDB')
meta = __import__('json').loads((job / 'article.json').read_text(encoding='utf-8'))
frame = None
if meta.get('frame_background'):
    frame_path = (job / meta['frame_background']).resolve()
    if not frame_path.is_relative_to(job):
        raise ValueError('proof background outside job')
    with Image.open(frame_path) as src:
        frame = src.convert('RGBA').resize((width, round(src.height*width/src.width)), Image.Resampling.LANCZOS)
    for top in range(0, canvas.height, frame.height):
        canvas.paste(frame, (0, top), frame)
draw = ImageDraw.Draw(canvas)
regular = 'C:/Windows/Fonts/msyh.ttc' if 'sans-serif' in root.get('style', '') else 'C:/Windows/Fonts/simsun.ttc'
bold = 'C:/Windows/Fonts/msyhbd.ttc'


def value(style, key, default):
    match = re.search(r'(?:^|;)\s*' + re.escape(key) + r'\s*:\s*([\d.]+)', style)
    return float(match.group(1)) if match else default


def color(style, default):
    match = re.search(r'(?:^|;)\s*color\s*:\s*(#[0-9A-Fa-f]{6})', style)
    return match.group(1) if match else default


def box(style, key, reference=0, default=(0, 0, 0, 0)):
    """Limited CSS box lengths for this document: px, percentages, zero and auto."""
    result = list(default)
    sides = {'top': 0, 'right': 1, 'bottom': 2, 'left': 3}
    def length(token):
        if token == 'auto':
            return 0
        match = re.fullmatch(r'(-?[\d.]+)(px|%)?', token)
        if not match:
            raise ValueError('proof unsupported ' + key + ' length: ' + token)
        number, unit = float(match.group(1)), match.group(2)
        if unit is None and number != 0:
            raise ValueError('proof box length requires px or %: ' + token)
        return number * reference / 100 if unit == '%' else number
    pattern = r'(?:^|;)\s*' + re.escape(key) + r'(?:-(top|right|bottom|left))?\s*:\s*([^;]+)'
    for side, raw in re.findall(pattern, style):
        values = [length(token) for token in raw.strip().split()]
        if side:
            if len(values) != 1:
                raise ValueError('proof invalid ' + key + '-' + side)
            result[sides[side]] = values[0]
        elif len(values) == 1:
            result = values * 4
        elif len(values) == 2:
            result = [values[0], values[1], values[0], values[1]]
        elif len(values) == 3:
            result = [values[0], values[1], values[2], values[1]]
        elif len(values) == 4:
            result = values
        else:
            raise ValueError('proof invalid ' + key + ' box')
    return [v * scale for v in result]


def styled_width(style, available, default=None):
    actual = available if default is None else default
    match = re.search(r'(?:^|;)\s*width\s*:\s*([\d.]+)(px|%)\s*(?:;|$)', style)
    if match:
        actual = available * float(match.group(1)) / 100 if match.group(2) == '%' else float(match.group(1)) * scale
    maximum = re.search(r'(?:^|;)\s*max-width\s*:\s*([\d.]+)(px|%)\s*(?:;|$)', style)
    if maximum:
        limit = available * float(maximum.group(1)) / 100 if maximum.group(2) == '%' else float(maximum.group(1)) * scale
        actual = min(actual, limit)
    if actual <= 0:
        raise ValueError('proof non-positive content width')
    return actual


def paragraph(node, x, y, w, heading=False, paint=True):
    text = node.get_text('', strip=True)
    if not text:
        return y
    style = node.get('style', '')
    actual_width = styled_width(style, w)
    if actual_width != w:
        x += (w-actual_width)/2
        w = actual_width
    size = round(value(style, 'font-size', 17 if heading else 16) * scale)
    font = ImageFont.truetype(bold if heading else regular, size)
    spacing = value(style, 'letter-spacing', .25) * scale
    height = round(size * value(style, 'line-height', 1.83))
    indent_rules = re.findall(r'text-indent\s*:\s*([^;]+)', style)
    indent = size * 2 if indent_rules and indent_rules[-1].strip() == '2em' else 0
    lines, current = [], ''
    for character in text:
        test = current + character
        limit = w - (indent if not lines else 0)
        if current and font.getlength(test) + spacing * max(0, len(test)-1) > limit:
            if character in '，。！？：；、）》」』】' or current[-1] in '（《「『【':
                carry = current[-1] + character
                current = current[:-1]
                if current:
                    lines.append(current)
                current = carry
            else:
                lines.append(current)
                current = character
        else:
            current = test
    if current:
        lines.append(current)
    margins = box(style, 'margin', w/scale, (18 if heading else 0, 0, 10 if heading else 11, 0))
    y += margins[0]
    for index, line in enumerate(lines):
        left = x + (indent if index == 0 else 0)
        gap = spacing
        if re.search(r'text-align\s*:\s*center', style):
            left = x + (w-font.getlength(line)-spacing*max(0, len(line)-1))/2
        elif 'text-align:justify' in style and index < len(lines)-1 and len(line) > 1:
            gap = max(spacing, (w - (indent if index == 0 else 0) - font.getlength(line)) / (len(line)-1))
        for character in line:
            if paint:
                draw.text((round(left), round(y)), character, font=font, fill=color(style, '#4D4A45'))
            left += font.getlength(character) + gap
        y += height
    return y + margins[2]


def image(node, x, y, w, paint=True):
    source = node.get('src', '')
    path = (job / 'build' / source).resolve()
    if not path.is_relative_to(job):
        raise ValueError('proof image outside job')
    if path.name == 'title.gif':
        path = path.with_name('title.png')
    style = node.get('style', '')
    margins = box(style, 'margin', w/scale)
    y += margins[0]
    with Image.open(path) as src:
        display_w = styled_width(style, w, min(w, src.width * scale))
        h = round(display_w * src.height / src.width)
        if paint:
            im = src.convert('RGBA').resize((round(display_w), h), Image.Resampling.LANCZOS)
            canvas.paste(im, (round(x + (w-display_w)/2), round(y)), im)
    return y + h + margins[2]


def section_background(style, x, top, w, bottom):
    """Equivalent solid/90-degree gradient fills for this document compositor."""
    if bottom <= top:
        return
    background = re.search(r'(?:^|;)\s*background(?:-color)?\s*:\s*(#[0-9A-Fa-f]{6})', style)
    if background:
        draw.rectangle((round(x), round(top), round(x+w), round(bottom)), fill=background.group(1))
    declaration = re.search(r'(?:^|;)\s*background-image\s*:\s*([^;]+)', style)
    if not declaration or declaration.group(1).strip() == 'none':
        return
    gradient = re.fullmatch(r'linear-gradient\(\s*90deg\s*,\s*(.+)\)', declaration.group(1).strip())
    if not gradient:
        raise ValueError('proof section supports a local solid fill or 90deg hex gradient only')
    stops = []
    for item in gradient.group(1).split(','):
        match = re.fullmatch(r'\s*(#[0-9A-Fa-f]{6})\s+([\d.]+)%\s*', item)
        if not match:
            raise ValueError('proof unsupported gradient stop: ' + item)
        rgb = tuple(int(match.group(1)[i:i+2], 16) for i in (1, 3, 5))
        stops.append((float(match.group(2))/100, rgb))
    if (len(stops) < 2 or stops[0][0] != 0 or stops[-1][0] != 1
            or any(stops[i][0] >= stops[i+1][0] for i in range(len(stops)-1))):
        raise ValueError('proof gradient stops must increase from 0% to 100%')
    columns = max(1, round(w))
    segment = 0
    for column in range(columns):
        progress = column/max(1, columns-1)
        while segment < len(stops)-2 and progress > stops[segment+1][0]:
            segment += 1
        a, ca = stops[segment]
        b, cb = stops[segment+1]
        fraction = (progress-a)/(b-a)
        shade = tuple(round(ca[i]+fraction*(cb[i]-ca[i])) for i in range(3))
        draw.line((round(x)+column, round(top), round(x)+column, round(bottom)), fill=shade)


def element(node, x, y, w, paint=True):
    if not getattr(node, 'name', None):
        return y
    if node.name == 'img':
        return image(node, x, y, w, paint=paint)
    if node.name == 'p' and node.find('img'):
        margins = box(node.get('style', ''), 'margin', w/scale, (10, 0, 0, 0))
        return image(node.img, x, y+margins[0], w, paint=paint) + margins[2]
    if node.name in ('p', 'h2', 'h3'):
        return paragraph(node, x, y, w, node.name.startswith('h'), paint=paint)
    if node.name == 'table':
        rows = node.find_all('tr')
        cells = node.find_all('td')
        if len(rows) != 1 or len(cells) != 2:
            raise ValueError('proof supports a single-row two-cell composition only')
        margins = box(node.get('style', ''), 'margin', w/scale, (9, 0, 8, 0))
        cell_widths = [styled_width(cell.get('style', ''), w, w/2) for cell in cells]
        if abs(sum(cell_widths)-w) > 1:
            raise ValueError('proof two-cell table widths must fill one row')
        layouts = []
        left = x
        for index, cell in enumerate(cells):
            cell_w = cell_widths[index]
            padding = box(cell.get('style', ''), 'padding', w/scale)
            inner_w = cell_w-padding[1]-padding[3]
            if inner_w <= 0:
                raise ValueError('proof table padding leaves no image width')
            align_rule = re.search(r'(?:^|;)\s*vertical-align\s*:\s*([^;]+)', cell.get('style', ''))
            alignment = align_rule.group(1).strip().lower() if align_rule else 'top'
            if alignment not in ('top', 'middle', 'bottom'):
                raise ValueError('proof unsupported table vertical-align: ' + alignment)
            content_height = 0
            for child in cell.children:
                content_height = element(child, left+padding[3], content_height, inner_w, paint=False)
            layouts.append((cell, left, inner_w, padding, content_height, alignment))
            left += cell_w
        row_height = max(padding[0]+height+padding[2] for _, _, _, padding, height, _ in layouts)
        if paint:
            for cell, left, inner_w, padding, content_height, alignment in layouts:
                free_space = row_height-padding[0]-padding[2]-content_height
                offset = free_space/2 if alignment == 'middle' else free_space if alignment == 'bottom' else 0
                cy = y + margins[0] + padding[0] + offset
                for child in cell.children:
                    cy = element(child, left+padding[3], cy, inner_w)
        return y + margins[0] + row_height + margins[2]
    if node.name == 'blockquote':
        style = node.get('style', '')
        margins = box(style, 'margin', w/scale, (10, 0, 8, 0))
        padding = box(style, 'padding', w/scale, (8, 12, 8, 12))
        top = y + margins[0]
        children = [child for child in node.children if getattr(child, 'name', None)]
        if any(child.name not in ('p', 'h2', 'h3') for child in children):
            raise ValueError('proof blockquote supports styled paragraphs only')
        cy = top + padding[0]
        for child in children:
            cy = paragraph(child, x+padding[3], cy, w-padding[1]-padding[3], child.name.startswith('h'), paint=False)
        bottom = cy + padding[2]
        if not paint:
            return bottom + margins[2]
        background = re.search(r'(?:^|;)\s*background(?:-color)?\s*:\s*(#[0-9A-Fa-f]{6})', style)
        if background:
            draw.rectangle((round(x), round(top), round(x+w), round(bottom)), fill=background.group(1))
        for side in ('left', 'top', 'bottom'):
            rule = re.search(r'(?:^|;)\s*border-' + side + r'\s*:\s*([\d.]+)px\s+solid\s+(#[0-9A-Fa-f]{6})', style)
            if rule:
                thickness, shade = float(rule.group(1))*scale, rule.group(2)
                coords = ((x, top, x+thickness, bottom) if side == 'left' else
                          (x, top, x+w, top+thickness) if side == 'top' else
                          (x, bottom-thickness, x+w, bottom))
                draw.rectangle(tuple(round(v) for v in coords), fill=shade)
        cy = top + padding[0]
        for child in children:
            cy = paragraph(child, x+padding[3], cy, w-padding[1]-padding[3], child.name.startswith('h'))
        return bottom + margins[2]
    if node.name == 'section':
        style = node.get('style', '')
        margins = box(style, 'margin', w/scale)
        actual_w = styled_width(style, w)
        padding = box(style, 'padding', w/scale)
        left = x + (w-actual_w)/2
        top = y + margins[0]
        inner_w = actual_w-padding[1]-padding[3]
        if inner_w <= 0:
            raise ValueError('proof section padding leaves no content width')
        measured = top + padding[0]
        for child in node.children:
            measured = element(child, left+padding[3], measured, inner_w, paint=False)
        bottom = max(measured+padding[2], top+value(style, 'height', 0)*scale)
        if paint:
            section_background(style, left, top, actual_w, bottom)
            cursor = top + padding[0]
            for child in node.children:
                cursor = element(child, left+padding[3], cursor, inner_w)
        return bottom + margins[2]
    for child in node.children:
        y = element(child, x, y, w, paint=paint)
    return y


y = image(root.h1.img, 0, 0, width)
for child in root.children:
    if child is not root.h1:
        y = element(child, 0, y, width)
y += box(root.get('style', ''), 'padding', width/scale)[2]
if y >= canvas.height:
    raise ValueError('Static proof exceeds compositor height budget')
out = job / 'build' / ('静态版式校样.png' if args.width == 375 else f'静态版式校样-{args.width}.png')
canvas.crop((0, 0, width, round(y))).save(out, optimize=True)
print(str(out))
