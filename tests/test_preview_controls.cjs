// Isolated UI-logic test. No browser, network, or OS clipboard is accessed.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const preview = process.argv[2];
if (!preview) throw new Error('Pass the generated preview HTML path');
const html = fs.readFileSync(path.resolve(preview), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
assert.ok(script, 'preview must have its own control script');
const motion = 'data:image/gif;base64,isolated-fixture';
const hero = {src:motion};
let clipboard;
const elements = {copy:{},motion:{},static:{},message:{textContent:''},
  article:{get innerHTML(){return `<section><img src="${hero.src}"></section>`;},innerText:'fixture'}};
const context = {
  document:{querySelector(selector){assert.equal(selector,'#article h1 img');return hero;},
    getElementById(id){assert.ok(elements[id],`unknown element ${id}`);return elements[id];}},
  navigator:{clipboard:{async write(items){clipboard=items;}}},
  ClipboardItem:class {constructor(data){this.data=data;}},Blob,
};
vm.runInNewContext(script,context,{timeout:1000});
(async()=>{
  elements.static.onclick();
  assert.equal(hero.src,'title.png');
  elements.motion.onclick();
  assert.equal(hero.src,motion);
  elements.static.onclick();
  await elements.copy.onclick();
  assert.equal(hero.src,motion);
  assert.match(await clipboard[0].data['text/html'].text(),/data:image\/gif/);
  console.log('3 preview control states passed (isolated logic, not browser QA).');
})().catch(error=>{console.error(error);process.exitCode=1;});
