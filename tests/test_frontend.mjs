// Isolated DOM/fetch simulation: no browser, no server, no model request.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../frontend/index.html', import.meta.url), 'utf8');
const source = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map();
for (const match of html.matchAll(/id="([^"]+)"/g)) {
  elements.set(match[1], {value:'', textContent:'', hidden:false, checked:true, disabled:false,
    files:[], style:{}, children:[], appendChild(child){this.children.push(child);}});
}
elements.get('templateOptions').hidden = true;
elements.get('version').value = 'EPI-EWB204+';
elements.get('panel').value = 'front';
elements.get('question').value = '识别 CH1 输出';
elements.get('image').files = [{name:'test.png'}];
const entries = ['sdg2000x', 'sdm3055x_e', 'sds2000x_hd'].map(name =>
  JSON.parse(fs.readFileSync(new URL(`../backend/device_templates/templates/${name}.json`, import.meta.url), 'utf8')));
let sent, nextMode='qwen', sessions=0;
class FormDataStub {fields=new Map(); append(k,v){this.fields.set(k,v);}}
const context = vm.createContext({
  document:{querySelector(selector){return elements.get(selector.slice(1));}, createElement(){return {};}},
  crypto:{randomUUID(){return `session-${++sessions}`;}}, FormData:FormDataStub,
  URL:{createObjectURL(){return 'blob:test';}},
  async fetch(url, options){
    let data;
    if(url==='/api/device-templates') data={templates:entries};
    else if(url==='/api/health') data={demo_mode:true};
    else {
      assert.equal(url, '/api/analyze'); sent=options.body.fields;
      const template=entries.find(t=>t.template_id===sent.get('template_id'));
      data={mode:nextMode, state:{observations:{components:[]}}, guidance:'测试指导',
        decision:{goal:'测试', status:'GUIDANCE', questions:[], evidence_sufficient:false},
        template:template?{id:template.template_id,name:template.display_name,panel:sent.get('panel'),
          applied:nextMode==='qwen',references_included:sent.get('include_references')==='true'}:{} };
    }
    return {ok:true, async json(){return data;}};
  },
});
vm.runInContext(source, context);
await new Promise(resolve => setImmediate(resolve));
assert.equal(elements.get('template').children.length, 3);
assert.match(elements.get('modeNotice').textContent, /不会调用视觉模型/);
elements.get('template').value = 'siglent_sdg2000x';
elements.get('template').onchange();
assert.equal(elements.get('version').value, 'SDG2000X');
assert.equal(elements.get('templateOptions').hidden, false);
await elements.get('form').onsubmit({preventDefault(){}});
assert.equal(sent.get('template_id'), 'siglent_sdg2000x');
assert.equal(sent.get('panel'), 'front');
assert.equal(sent.get('include_references'), 'true');
assert.match(elements.get('templateResult').textContent, /已用于模型请求/);
assert.equal(elements.get('submit').disabled, false);
elements.get('references').checked = false;
elements.get('panel').value = 'rear';
nextMode = 'demo';
await elements.get('form').onsubmit({preventDefault(){}});
assert.equal(sent.get('include_references'), 'false');
assert.equal(sent.get('panel'), 'rear');
assert.match(elements.get('templateResult').textContent, /演示模式未调用模型/);
assert.match(elements.get('status').textContent, /非真实照片识别/);
const oldSession = sent.get('session_id');
elements.get('template').value = 'siglent_sds2000x_hd';
elements.get('template').onchange();
assert.equal(elements.get('version').value, 'SDS2000X HD');
assert.equal(vm.runInContext('history.length', context), 0);
assert.notEqual(vm.runInContext('sessionId', context), oldSession);
elements.get('template').value = '';
elements.get('template').onchange();
assert.equal(elements.get('version').value, 'EPI-EWB204+');
assert.equal(elements.get('templateOptions').hidden, true);
console.log('Frontend checks passed: catalog, selection, upload fields, result mode, history reset, old flow.');
