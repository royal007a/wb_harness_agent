"use strict";
const workflowExample={nodes:[
{id:'start',type:'START',config:{}},
{id:'route',type:'CONDITION',config:{left:'{{start.input}}',operator:'contains',right:'退'}},
{id:'policy',type:'LLM',config:{prompt:'你是售后客服，没有给定公司政策时不能编造退款期限，请先澄清订单和问题：{{start.input}}'}},
{id:'general',type:'LLM',config:{prompt:'你是客服，友好回应；没有资料的产品事实不要编造：{{start.input}}'}},
{id:'end_policy',type:'END',config:{text:'{{policy.output}}'}},
{id:'end_general',type:'END',config:{text:'{{general.output}}'}}],edges:[
{source:'start',target:'route',condition:null},{source:'route',target:'policy',condition:true},
{source:'route',target:'general',condition:false},{source:'policy',target:'end_policy',condition:null},
{source:'general',target:'end_general',condition:null}]};
function resetWorkflow(){$('workflow-form').reset();$('workflow-id').value='';$('workflow-json').value=JSON.stringify(workflowExample,null,2);}
async function refreshWorkflows(){const data=await api('/workflows');const select=$('agent-workflow'),old=select.value;const empty=node('option','不使用工作流');empty.value='';select.replaceChildren(empty,...data.items.filter(w=>w.enabled).map(w=>{const o=node('option',w.name);o.value=w.id;return o;}));if(data.items.some(w=>w.id===old&&w.enabled))select.value=old;$('workflow-list').replaceChildren(...data.items.map(w=>{const c=node('div','', 'card');c.append(node('strong',w.name),node('p',w.nodes.length+'节点 · '+(w.enabled?'启用':'停用')),button('编辑',()=>{$('workflow-id').value=w.id;$('workflow-name').value=w.name;$('workflow-description').value=w.description;$('workflow-enabled').checked=w.enabled;$('workflow-json').value=JSON.stringify({nodes:w.nodes,edges:w.edges},null,2);}),button('执行记录',async()=>{$('workflow-runs').textContent=JSON.stringify((await api('/workflows/'+w.id+'/runs')).items,null,2);}),button('删除',async()=>{if(confirm('删除工作流配置？已有会话将拒绝继续执行，历史记录保留。')){await api('/workflows/'+w.id,'DELETE');await refreshWorkflows();}}));return c;}));}
$('workflow-form').onsubmit=async e=>{e.preventDefault();try{const definition=JSON.parse($('workflow-json').value);if(Object.keys(definition).sort().join(',')!=='edges,nodes')throw Error('JSON 只应包含 nodes、edges');const id=$('workflow-id').value;await api('/workflows'+(id?'/'+id:''),id?'PUT':'POST',{name:$('workflow-name').value,description:$('workflow-description').value,enabled:$('workflow-enabled').checked,...definition});await refreshWorkflows();status('工作流已保存；在 Agent 中绑定后新建会话试运行。');}catch(e){status(e.message);}};
$('workflow-format').onclick=()=>{try{$('workflow-json').value=JSON.stringify(JSON.parse($('workflow-json').value),null,2);}catch(e){status('JSON 格式不合法');}};
$('workflow-reset').onclick=resetWorkflow;resetWorkflow();refreshWorkflows().catch(e=>status(e.message));
