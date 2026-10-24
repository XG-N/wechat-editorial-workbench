import importlib.util
import json
from pathlib import Path
import shutil

from bs4 import BeautifulSoup
from PIL import Image
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('pipeline', ROOT / 'skills/wechat-editorial-pipeline/scripts/pipeline.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


@pytest.fixture
def job(tmp_path):
    target = tmp_path / 'job'
    p.init_job(target, 'life', '验证真实照片与标题')
    photo = target / 'photos/test.jpg'
    photo.parent.mkdir()
    Image.new('RGB', (1000, 650), '#405945').save(photo)
    original = photo.with_suffix('.source')
    shutil.copy2(photo, original)
    p.write_json(target / 'photos.json', [{'id': 'test', 'file': 'photos/test.jpg',
        'original_file': 'photos/test.source', 'kind': 'photo', 'author': 'fixture',
        'source_page': 'https://example.org/fixture-photo', 'license': 'fixture-only',
        'license_url': 'https://example.org/fixture-license', 'caption': '纯色测试夹具，不是交付照片',
        'authenticity_basis': 'isolated synthetic fixture, never production material',
        'source_checked': True, 'visual_checked': True, 'usage': 'illustrative',
        'sha256': p.digest(photo), 'original_sha256': p.digest(original)}])
    meta = p.read_json(target / 'article.json')
    meta.update(summary='隔离测试数据。', hero_photo='test', author='fixture')
    p.write_json(target / 'article.json', meta)
    (target / 'article.md').write_text('# 验证真实照片与标题\n\n这是隔离测试，编号 A-12。\n\n## 文字完整保留\n\n保留范围与条件。\n\n![夹具](photos/test.jpg)\n', encoding='utf-8')
    p.build(target)
    return target


def mark_reviewed(job):
    p.write_json(job / 'review.json', {'input_sha256': p.source_fingerprint(job),
        'reviewer': 'test fixture, not an actual editorial review',
        'stages': {s: {'status': 'pass', 'notes': 'isolated behavioral test fixture'} for s in p.REVIEW_STAGES},
        'findings': [], 'acknowledged_warnings': [], 'wechat_verified': False})


def test_missing_review_blocks_export_and_upload(job):
    assert p.audit(job)['status'] == 'blocked'
    with pytest.raises(ValueError, match='审核未通过'):
        p.export(job)
    with pytest.raises(ValueError, match='审核未通过'):
        p.create_draft(job, upload=True)


def test_reviewed_bundle_exports_with_correct_hashes(job):
    mark_reviewed(job)
    assert p.audit(job)['status'] == 'ready_for_draft'
    folder = p.export(job)
    assert all(p.digest(folder / name) == sha for name, sha in p.read_json(folder / 'manifest.json').items())


def test_changed_source_invalidates_review(job):
    mark_reviewed(job)
    with (job / 'article.md').open('a', encoding='utf-8') as stream:
        stream.write('\n新增事实。\n')
    codes = {i['rule'] for i in p.audit(job)['issues']}
    assert {'REVIEW001', 'BUILD002'} <= codes


def test_changed_render_invalidates_review(job):
    mark_reviewed(job)
    path = job / 'build/article.wechat.html'
    path.write_text(path.read_text(encoding='utf-8') + '<p>篡改后的断言</p>', encoding='utf-8')
    assert p.audit(job)['status'] == 'blocked'


def test_changed_photo_is_rejected(job):
    mark_reviewed(job)
    with (job / 'photos/test.jpg').open('ab') as stream:
        stream.write(b'changed')
    assert 'PHOTO007' in {i['rule'] for i in p.audit(job)['issues']}


def test_generated_body_photo_is_rejected(job):
    photos = p.read_json(job / 'photos.json')
    photos[0]['kind'] = 'generated-background'
    p.write_json(job / 'photos.json', photos)
    assert 'PHOTO003' in {i['rule'] for i in p.audit(job)['issues']}


def test_title_is_complete_and_gif_actually_moves(job):
    info = p.read_json(job / 'build/render.json')['hero']
    assert ''.join(info['lines']) == p.read_json(job / 'article.json')['title']
    with Image.open(job / 'build/title.gif') as image:
        first = image.convert('RGB').tobytes()
        assert image.n_frames >= 2
        image.seek(image.n_frames - 1)
        assert first != image.convert('RGB').tobytes()
    assert (job / 'build/title.gif').stat().st_size <= 2 * 1024 * 1024


def test_animated_title_background_does_not_jump(job):
    image = Image.new('RGB', (100, 70))
    image.putdata([((x * 3 + y * 7) % 256, (x * 11 + y * 2) % 256,
                    (x * 5 + y * 13) % 256) for y in range(70) for x in range(100)])
    image.resize((1000, 650)).save(job / 'photos/test.jpg', quality=90)
    meta = p.read_json(job / 'article.json')
    p.make_hero(job, meta, p.read_json(job / 'photos.json'), p.themes()['life'])
    with Image.open(job / 'build/title.gif') as gif:
        background = gif.convert('RGB').crop((0, 0, 1000, 470)).tobytes()
        for index in (1, 2, gif.n_frames - 1):
            gif.seek(index)
            assert gif.convert('RGB').crop((0, 0, 1000, 470)).tobytes() == background


def test_raw_html_cannot_execute_in_fragment(job):
    path = job / 'article.md'
    path.write_text(path.read_text(encoding='utf-8') + '\n<script>alert(1)</script>\n', encoding='utf-8')
    p.build(job)
    tree = BeautifulSoup((job / 'build/article.wechat.html').read_text(encoding='utf-8'), 'html.parser')
    assert tree.find('script') is None
    assert '<script>alert(1)</script>' in tree.get_text()


def test_paths_cannot_escape_job(job):
    for name in ('../outside.jpg', 'C:/private.jpg', 'https://example.org/image.jpg'):
        with pytest.raises(ValueError):
            p.local(job, name)


def test_pending_draft_call_is_not_repeated(job):
    mark_reviewed(job)
    p.write_json(job / 'build/upload-progress.json', {'input_sha256': p.source_fingerprint(job), 'status': 'about_to_add_draft'})
    with pytest.raises(ValueError, match='结果未知'):
        p.create_draft(job, upload=True)


def test_dry_run_does_not_need_or_send_credentials(job, monkeypatch):
    mark_reviewed(job)
    monkeypatch.delenv('WECHAT_APP_ID', raising=False)
    monkeypatch.delenv('WECHAT_APP_SECRET', raising=False)
    def forbidden(*a, **kw):
        raise AssertionError('dry-run must not use the network')
    monkeypatch.setattr(p.requests, 'Session', forbidden)
    assert p.create_draft(job)['status'] == 'dry_run'


def fake_session(job, fail_add=False, wrong_images=False, strip_background=False):
    calls = []
    submitted = {}
    class Response:
        def __init__(self, data): self.data = data
        def raise_for_status(self): pass
        def json(self): return self.data
    class Session:
        def get(self, url, **kwargs):
            calls.append(('get', url))
            return Response({'access_token': 'fake-token-only'})
        def post(self, url, **kwargs):
            calls.append(('post', url))
            if url.endswith('/draft/add'):
                body = json.loads(kwargs['data'])
                submitted.update(body['articles'][0])
                assert body['articles'][0]['title'] == p.read_json(job / 'article.json')['title']
                assert 'fake-secret-only' not in body['articles'][0]['content']
                if fail_add: raise p.requests.Timeout('isolated unknown-result fixture')
                return Response({'media_id': 'fake-draft-id'})
            if url.endswith('/draft/get'):
                content = submitted.get('content', '')
                if wrong_images:
                    content = '<p><img src="a"><img src="b"></p>'
                if strip_background:
                    content = p.re.sub(r'background-image:[^;]+;?', '', content)
                return Response({'news_item': [{'title': p.read_json(job / 'article.json')['title'],
                    'content': content}]})
            if url.endswith('/material/add_material'):
                return Response({'media_id': 'fake-material', 'url': 'https://mmbiz.qpic.cn/fake.gif'})
            return Response({'url': 'https://mmbiz.qpic.cn/fake.jpg'})
    return Session, calls


def test_api_draft_upload_and_readback_without_public_send(job, monkeypatch):
    mark_reviewed(job)
    session, calls = fake_session(job)
    monkeypatch.setattr(p.requests, 'Session', session)
    monkeypatch.setenv('WECHAT_APP_ID', 'fake-app-only')
    monkeypatch.setenv('WECHAT_APP_SECRET', 'fake-secret-only')
    result = p.create_draft(job, upload=True)
    assert result['media_id'] == 'fake-draft-id' and result['readback_verified']
    assert result['readback_image_count'] == 2
    assert result['visual_verified'] is False
    assert not any('freepublish' in url or 'mass/send' in url for _, url in calls)
    assert 'fake-secret-only' not in (job / 'build/draft-receipt.json').read_text(encoding='utf-8')
    with pytest.raises(ValueError, match='已有草稿回执'):
        p.create_draft(job, upload=True)


def test_matching_title_and_count_do_not_verify_wrong_images(job, monkeypatch):
    mark_reviewed(job)
    session, calls = fake_session(job, wrong_images=True)
    monkeypatch.setattr(p.requests, 'Session', session)
    monkeypatch.setenv('WECHAT_APP_ID', 'fake-app-only')
    monkeypatch.setenv('WECHAT_APP_SECRET', 'fake-secret-only')
    result = p.create_draft(job, upload=True)
    assert result['readback_title_matches'] and result['readback_image_count'] == 2
    assert result['readback_images_match'] is False
    assert result['readback_verified'] is False and result['visual_verified'] is False


def test_uncertain_draft_submit_requires_readback_before_retry(job, monkeypatch):
    mark_reviewed(job)
    session, calls = fake_session(job, fail_add=True)
    monkeypatch.setattr(p.requests, 'Session', session)
    monkeypatch.setenv('WECHAT_APP_ID', 'fake-app-only')
    monkeypatch.setenv('WECHAT_APP_SECRET', 'fake-secret-only')
    with pytest.raises(ValueError, match='未确认完成'):
        p.create_draft(job, upload=True)
    with pytest.raises(ValueError, match='结果未知'):
        p.create_draft(job, upload=True)
    assert sum(url.endswith('/draft/add') for _, url in calls) == 1


def test_typo_placeholder_and_claim_source_are_caught(job):
    path = job / 'article.md'
    path.write_text(path.read_text(encoding='utf-8') + '\n再接再励，{{待填姓名}}。\n', encoding='utf-8')
    p.write_json(job / 'facts.json', {'sources': [], 'claims': [{'text': '再接再励', 'sources': ['missing']} ]})
    codes = {i['rule'] for i in p.audit(job)['issues']}
    assert {'ZH001', 'CONTENT001', 'FACT002'} <= codes


@pytest.mark.parametrize('theme', list(p.themes()))
def test_eight_topics_have_operable_briefs(tmp_path, theme):
    target = tmp_path / theme
    p.init_job(target, theme, '通用主题验证')
    brief = (target / '任务书.md').read_text(encoding='utf-8')
    assert p.themes()[theme]['name'] in brief
    assert len(p.themes()[theme]['structures']) >= 2
    assert all((target / name).is_file() for name in ('article.md', 'article.json', 'facts.json', 'photos.json', 'review.json'))


@pytest.mark.parametrize('theme', list(p.themes()))
def test_all_eight_layouts_build_and_preserve_text(job, theme):
    meta = p.read_json(job / 'article.json')
    meta['theme'] = theme
    p.write_json(job / 'article.json', meta)
    p.build(job)
    tree = BeautifulSoup((job / 'build/article.wechat.html').read_text(encoding='utf-8'), 'html.parser')
    assert p.themes()[theme]['background'] in tree.section['style']
    assert '保留范围与条件。' in tree.get_text()
    assert len(tree.find_all('img')) == 2


def test_campus_warm_preserves_text_and_pairs_real_photos(job):
    meta = p.read_json(job / 'article.json')
    meta.update(layout='campus-warm', hero_background='photos/test.jpg',
                hero_title_lines=['验证真实', '照片与标题'], author='', photo_pairs=[['test', 'second']])
    p.write_json(job / 'article.json', meta)
    photos = p.read_json(job / 'photos.json')
    second = dict(photos[0], id='second', file='photos/second.jpg', author='second-fixture')
    shutil.copy2(job / 'photos/test.jpg', job / 'photos/second.jpg')
    photos.append(second)
    p.write_json(job / 'photos.json', photos)
    with (job / 'article.md').open('a', encoding='utf-8') as stream:
        stream.write('\n![第二夹具](photos/second.jpg)\n\n保留最后一段。\n')
    p.build(job)
    tree = BeautifulSoup((job / 'build/article.wechat.html').read_text(encoding='utf-8'), 'html.parser')
    assert '#FFEFDB' in tree.section['style']
    assert '#FFFFFF' in tree.section.find('section')['style']
    assert len(tree.find_all('img')) == 3
    tables = tree.find_all('table')
    assert len(tables) == 1 and len(tables[0].find_all('td')) == 2
    assert '保留范围与条件。' in tree.get_text() and '保留最后一段。' in tree.get_text()
    assert 'second-fixture' in tree.get_text()
    assert '作者：' not in tree.get_text() and '二维码' not in tree.get_text()
    with Image.open(job / 'build/title.gif') as image:
        assert image.size == (1000, 1260) and image.n_frames == 28
        fixed = image.convert('RGB').crop((0, 0, 1000, 1180)).tobytes()
        image.seek(27)
        assert fixed == image.convert('RGB').crop((0, 0, 1000, 1180)).tobytes()


def test_campus_warm_rejects_wrong_title_lines_and_unregistered_background(job):
    meta = p.read_json(job / 'article.json')
    meta.update(layout='campus-warm', hero_background='photos/test.jpg', hero_title_lines=['别的标题'])
    with pytest.raises(ValueError, match='主标题完全一致'):
        p.make_hero(job, meta, p.read_json(job / 'photos.json'), p.themes()['life'])
    meta['hero_background'] = '../outside.png'
    with pytest.raises(ValueError, match='已登记'):
        p.make_hero(job, meta, p.read_json(job / 'photos.json'), p.themes()['life'])


def test_supporting_layout_change_invalidates_review(job, tmp_path, monkeypatch):
    mark_reviewed(job)
    replacement = tmp_path / 'skill-copy'
    shutil.copytree(p.BASE, replacement, ignore=shutil.ignore_patterns('__pycache__'))
    monkeypatch.setattr(p, 'BASE', replacement)
    assert p.audit(job)['status'] == 'ready_for_draft'
    with (replacement / 'scripts/campus_layout.py').open('a', encoding='utf-8') as stream:
        stream.write('\n# changed layout renderer\n')
    assert p.audit(job)['status'] == 'blocked'


def add_frame(job):
    frame = job / 'photos/frame.jpg'
    shutil.copy2(job / 'photos/test.jpg', frame)
    meta = p.read_json(job / 'article.json')
    meta.update(layout='campus-warm', hero_background='photos/test.jpg', frame_background='photos/frame.jpg')
    p.write_json(job / 'article.json', meta)
    photos = p.read_json(job / 'photos.json')
    photos.append({'id': 'frame', 'file': 'photos/frame.jpg', 'kind': 'generated-background',
        'generation_tool': 'isolated test fixture', 'sha256': p.digest(frame), 'authenticity_basis': 'test fixture'})
    p.write_json(job / 'photos.json', photos)
    p.build(job)


def test_campus_frame_embeds_without_becoming_a_body_photo(job):
    add_frame(job)
    fragment = BeautifulSoup((job / 'build/article.wechat.html').read_text(encoding='utf-8'), 'html.parser')
    preview = BeautifulSoup((job / 'build/preview.html').read_text(encoding='utf-8'), 'html.parser')
    assert "url('../photos/frame.jpg')" in fragment.section['style']
    assert 'background-color:#FFEFDB' in fragment.section['style']
    assert len(fragment.find_all('img')) == 2
    assert 'url(\'data:image/jpeg;base64,' in preview.find('main').section['style']


@pytest.mark.parametrize('stripped', [False, True])
def test_draft_readback_checks_background_material(job, monkeypatch, stripped):
    add_frame(job)
    mark_reviewed(job)
    session, calls = fake_session(job, strip_background=stripped)
    monkeypatch.setattr(p.requests, 'Session', session)
    monkeypatch.setenv('WECHAT_APP_ID', 'fake-app-only')
    monkeypatch.setenv('WECHAT_APP_SECRET', 'fake-secret-only')
    result = p.create_draft(job, upload=True)
    assert len(result['backgrounds']) == 1
    assert result['readback_title_matches'] and result['readback_images_match']
    assert result['readback_backgrounds_match'] is (not stripped)
    assert result['readback_verified'] is (not stripped)
    assert result['visual_verified'] is False


def test_editorial_cover_motion_is_visible_and_title_is_stable(job):
    meta = p.read_json(job / 'article.json')
    meta.update(layout='campus-warm', hero_background='photos/test.jpg', hero_motion='editorial-motion',
                hero_title_top=185, hero_text_offset=80, subtitle='从熟悉的路口出发，不必赶往下一站',
                hero_subtitle_lines=['从熟悉的路口出发，', '不必赶往下一站'])
    info = p.make_hero(job, meta, p.read_json(job / 'photos.json'), p.themes()['life'])
    assert info['frames'] == 32 and info['duration_ms'] == 3840
    assert all(box[0] >= 32 and box[2] <= 968 and box[3] <= 500 for box in info['text_boxes'])
    assert ''.join(info['subtitle_lines']) == meta['subtitle']
    from PIL import ImageChops
    with Image.open(job / 'build/title.gif') as gif:
        assert gif.n_frames == 32
        first = gif.convert('RGB')
        still_title = first.crop((0,0,1000,500)).tobytes()
        duration = 0
        for index in range(gif.n_frames):
            gif.seek(index)
            assert gif.convert('RGBA').getchannel('A').getextrema() == (255,255)
            assert gif.convert('RGB').crop((0,0,1000,500)).tobytes() == still_title
            duration += gif.info['duration']
        gif.seek(8)
        delta = ImageChops.difference(first, gif.convert('RGB'))
        red, green, blue = delta.split()
        histogram = ImageChops.lighter(ImageChops.lighter(red,green),blue).histogram()
        assert sum(histogram[1:]) > 10000
        assert duration == info['duration_ms']
    assert (job / 'build/title.gif').stat().st_size < 2*1024*1024


def test_typography_and_portrait_photo_preserve_full_sources(job):
    meta=p.read_json(job/'article.json')
    meta.update(layout='campus-warm',hero_background='photos/test.jpg')
    p.write_json(job/'article.json',meta)
    portrait=job/'photos/portrait.jpg'
    Image.new('RGB',(800,1200),'#567654').save(portrait)
    photos=p.read_json(job/'photos.json')
    photos.append(dict(photos[0],id='portrait',file='photos/portrait.jpg',sha256=p.digest(portrait),author='Portrait Photographer'))
    p.write_json(job/'photos.json',photos)
    with (job/'article.md').open('a',encoding='utf-8') as stream:
        stream.write('\n![竖图夹具](photos/portrait.jpg)\n')
    p.build(job)
    tree=BeautifulSoup((job/'build/article.wechat.html').read_text(encoding='utf-8'),'html.parser')
    assert 'sans-serif' in tree.section['style']
    assert any('font-size:17px' in node.get('style','') and 'letter-spacing:0.25px' in node.get('style','') for node in tree.find_all('p'))
    picture=tree.find('img',src='../photos/portrait.jpg')
    assert 'width:68%' in picture['style'] and 'max-width:320px' in picture['style']
    assert tree.get_text().count('Portrait Photographer')==1
    assert '摄影来源' in tree.get_text()
    assert len(tree.find_all('img'))==3
    assert tree.find('a',href='https://example.org/fixture-license') is not None


def test_transparent_decorations_keep_photography_and_mime_distinct(job):
    meta = p.read_json(job / 'article.json')
    meta.update(layout='campus-warm', hero_background='photos/test.jpg',
                body_layout='ornament-staggered', photo_pairs=[['test', 'second']],
                body_ornaments={'intro': 'ornament', 'photo': 'ornament'})
    p.write_json(job / 'article.json', meta)
    photos = p.read_json(job / 'photos.json')
    second = job / 'photos/second.jpg'
    Image.new('RGB', (1200, 760), '#647342').save(second)
    photos.append(dict(photos[0], id='second', file='photos/second.jpg',
                       sha256=p.digest(second), author='Second Photographer'))
    ornament = job / 'designs/ornament.png'
    ornament.parent.mkdir()
    Image.new('RGBA', (90, 60), (180, 70, 30, 120)).save(ornament)
    with Image.open(ornament) as im:
        im.putpixel((0, 0), (0, 0, 0, 0))
        im.save(ornament)
    photos.append({'id': 'ornament', 'file': 'designs/ornament.png',
                   'kind': 'generated-decoration', 'usage': 'decoration_only',
                   'generation_tool': 'isolated test fixture',
                   'authenticity_basis': 'not a photograph', 'sha256': p.digest(ornament)})
    p.write_json(job / 'photos.json', photos)
    with (job / 'article.md').open('a', encoding='utf-8') as stream:
        stream.write('\n![另一张测试图](photos/second.jpg)\n')
    p.build(job)
    tree = BeautifulSoup((job / 'build/article.wechat.html').read_text(encoding='utf-8'), 'html.parser')
    assert len(tree.find_all('img', src='../designs/ornament.png')) == 2
    assert tree.get_text().count('Second Photographer') == 1
    assert tree.find('a', href=photos[1]['source_page']) is not None
    assert p.digest(second) == photos[1]['sha256']
    preview = BeautifulSoup((job / 'build/preview.html').read_text(encoding='utf-8'), 'html.parser')
    assert len([im for im in preview.find_all('img') if im['src'].startswith('data:image/png;')]) == 2
    # A claimed photograph cannot be smuggled into the decorative-only path.
    photos[-1]['kind'] = 'photo'
    p.write_json(job / 'photos.json', photos)
    with pytest.raises(ValueError, match='点缀须标明'):
        p.build(job)


def test_editorial_flow_keeps_photos_in_their_source_sections(job):
    meta = p.read_json(job / 'article.json')
    meta.update(layout='campus-warm', hero_background='photos/test.jpg',
                body_layout='editorial-flow', photo_pairs=[])
    p.write_json(job / 'article.json', meta)
    second = job / 'photos/second.jpg'
    Image.new('RGB', (1100, 700), '#645C42').save(second)
    photos = p.read_json(job / 'photos.json')
    photos.append(dict(photos[0], id='second', file='photos/second.jpg',
                       sha256=p.digest(second), author='Section Photographer'))
    p.write_json(job / 'photos.json', photos)
    (job / 'article.md').write_text('# 验证真实照片与标题\n\n开头文字。\n\n![开头图](photos/test.jpg)\n\n'
        '## 中途观察\n\n中途文字。\n\n![中途图](photos/second.jpg)\n\n## 回程\n\n回程文字。\n', encoding='utf-8')
    p.build(job)
    tree = BeautifulSoup((job / 'build/article.wechat.html').read_text(encoding='utf-8'), 'html.parser')
    photo = tree.find('img', src='../photos/second.jpg')
    assert photo.find_previous('h2').get_text() == '中途观察'
    assert photo.find_next('h2').get_text() == '回程'
    assert tree.find('table') is None
    assert tree.get_text().count('Section Photographer') == 1
    assert 'HTML003' not in {issue['rule'] for issue in p.audit(job)['issues']}
    # A stale layout instruction must not silently regroup photos across sections.
    meta['photo_pairs'] = [['test', 'second']]
    p.write_json(job / 'article.json', meta)
    with pytest.raises(ValueError, match='清空photo_pairs'):
        p.build(job)


def test_editorial_rhythm_preserves_text_sources_and_local_compositions(job):
    meta = p.read_json(job / 'article.json')
    quote = '散步可以没有一个值得汇报的结果。'
    meta.update(layout='campus-warm', hero_background='photos/test.jpg', body_layout='editorial-rhythm',
                photo_pairs=[], photo_duos=[['a', 'b']], quote_photo={'id': 'test', 'quote': quote},
                body_ornaments={'quote': 'leaf'})
    p.write_json(job / 'article.json', meta)
    photos = p.read_json(job / 'photos.json')
    for identifier in ('a', 'b'):
        path = job / f'photos/{identifier}.jpg'
        Image.new('RGB', (800, 1200), '#68764D').save(path)
        photos.append(dict(photos[0], id=identifier, file=f'photos/{identifier}.jpg',
                           sha256=p.digest(path), author=f'Photographer {identifier}'))
    leaf = job / 'designs/leaf.png'
    leaf.parent.mkdir()
    im = Image.new('RGBA', (80, 60), (180, 70, 30, 120))
    im.putpixel((0, 0), (0, 0, 0, 0)); im.save(leaf)
    photos.append({'id': 'leaf', 'file': 'designs/leaf.png', 'kind': 'generated-decoration',
                   'usage': 'decoration_only', 'generation_tool': 'isolated test fixture',
                   'authenticity_basis': 'fixture, not photography', 'sha256': p.digest(leaf)})
    p.write_json(job / 'photos.json', photos)
    (job / 'article.md').write_text('# 验证真实照片与标题\n\n开头文字。\n\n## 观察\n\n'
        '观察前段。\n\n![A](photos/a.jpg)\n\n![B](photos/b.jpg)\n\n观察后段。\n\n'
        f'## 停步\n\n路线文字。\n\n> {quote}\n\n![长椅夹具](photos/test.jpg)\n\n朋友文字。\n', encoding='utf-8')
    p.build(job)
    tree = BeautifulSoup((job / 'build/article.wechat.html').read_text(encoding='utf-8'), 'html.parser')
    tables = tree.find_all('table')
    assert len(tables) == 2 and len(tables[0].find_all('img')) == 2
    assert tables[0].find_previous('h2').get_text() == '观察'
    assert tables[1].find_previous('h2').get_text() == '停步'
    assert tables[1].get_text().count(quote) == 1 and tree.get_text().count(quote) == 1
    assert len(tables[1].find_all('img')) == 2  # one photograph and one declared decoration
    assert [t.get_text() for t in tree.find_all('p') if '朋友文字。' in t.get_text()] == ['朋友文字。']
    for photo in photos[:3]:
        assert len(tree.find_all('img', src='../' + photo['file'])) == 1
        assert tree.get_text().count('摄影：' + photo['author'] + ' ·') == 1
        assert tree.find('a', href=photo['source_page']) and tree.find('a', href=photo['license_url'])
    assert 'HTML003' not in {issue['rule'] for issue in p.audit(job)['issues']}
    # Layout must refuse crossing a source paragraph rather than silently move a photograph.
    path = job / 'article.md'
    path.write_text(path.read_text(encoding='utf-8').replace('![B]', '不应跨越的正文。\n\n![B]'), encoding='utf-8')
    with pytest.raises(ValueError, match='须在源稿相邻'):
        p.build(job)


def test_editorial_rhythm_refuses_a_fabricated_or_distant_quote(job):
    meta = p.read_json(job / 'article.json')
    meta.update(layout='campus-warm', hero_background='photos/test.jpg', body_layout='editorial-rhythm',
                photo_pairs=[], quote_photo={'id': 'test', 'quote': '源稿不存在的短句。'})
    p.write_json(job / 'article.json', meta)
    with pytest.raises(ValueError, match='源稿中唯一出现'):
        p.build(job)
