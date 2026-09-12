"""Bounded one-level fan-out, durable on the existing Task/Run state model."""
import copy
import json
import threading
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

from jsonschema import Draft202012Validator

from adapters.research_demo import COMPANIES, ROLES, ResearchDemoExecutor, fixture, evaluate
from .analysis import Problem, digest
from .store import now, uid, dumps
from .service import ROOT, TOOLS, DENY, TERMINAL, validate, local_task

ENGINE = 'engine_local_research_demo'
REQUEST = json.loads((ROOT / 'specs/v1/research-request.schema.json').read_text())


class Research:
    def __init__(self, service):
        self.service, self.store = service, service.store
        self.executor = ResearchDemoExecutor()
        self.slots = threading.BoundedSemaphore(3)

    def create(self, body, key):
        if list(Draft202012Validator(REQUEST).iter_errors(body)):
            raise Problem('VALIDATION_ERROR', '研究演示参数无效。', 422)
        count = len(body['companies']) * len(body['roles'])
        if body['max_steps'] < count + 1:
            raise Problem('BUDGET_EXCEEDED', '需预留每个子任务 1 步和父汇总 1 步。', 422)
        def create(db):
            assignments = []
            for company in body['companies']:
                for role in body['roles']:
                    raw = fixture(company, role, body['scenario'])
                    rid = 'res_' + digest(raw)
                    resource = {'id': rid, 'name': company + '-' + role + '-synthetic.json',
                                'sha256': digest(raw), 'size_bytes': len(raw), 'data_class': 'Public',
                                'row_count': 1, 'columns': [], 'encoding': 'utf-8', 'created_at': now()}
                    db.execute('INSERT OR IGNORE INTO resources VALUES(?,?,?)', (rid, dumps(resource), raw))
                    assignments.append({'company': company, 'role': role, 'resource_id': rid})
            task = local_task(assignments[0]['resource_id'], '离线多专项研究演示（非真实研报）', body['timeout_seconds'])
            task.update({'id': uid('task'), 'created_at': now(), 'agent_spec_version': 'local_research_demo@1'})
            task['context'] = {'resource_ids': [a['resource_id'] for a in assignments],
                               'variables': {'request': copy.deepcopy(body), 'assignments': assignments}}
            task['engine_policy']['engine_id'] = ENGINE
            task['limits']['max_turns'] = body['max_steps']
            task['limits']['max_input_tokens'] = count + 1
            validate('task', task)
            db.execute('INSERT INTO tasks VALUES(?,?)', (task['id'], dumps(task)))
            run = self.new_run(db, task)
            return {'task': task, 'initial_run': run}
        return self.service.idempotent('research', key, body, create)

    def new_run(self, db, task, based_on=None):
        assignments = task['context']['variables']['assignments']
        runs = self.store.listing('runs')
        if sum(r['status'] not in TERMINAL for r in runs) + len(assignments) + 1 > 32:
            raise Problem('RATE_LIMITED', '本地队列不足以容纳整棵运行树。', 429)
        if based_on and self.store.get('runs', based_on).get('parent_run_id'):
            raise Problem('VALIDATION_ERROR', '研究重跑只能引用根 Run。', 422)
        attempt = 1 + sum(r['task_id'] == task['id'] and not r.get('parent_run_id') for r in runs)
        policy = {'profile_id':'analysis_read_only', 'profile_version':1, 'allowed_tools':list(TOOLS),
                  'denied_capabilities':list(DENY), 'decision_digest':digest(dumps(task['requested_permissions']).encode())}
        root = {'id':uid('run'), 'task_id':task['id'], 'status':'queued', 'selected_engine':ENGINE,
                'selected_models':{}, 'effective_permissions':policy, 'effective_limits':copy.deepcopy(task['limits']),
                'attempt_number':attempt, 'based_on_run_id':based_on, 'latest_sequence':0, 'exit_reason':None,
                'created_at':now(), 'updated_at':now()}
        self.insert(db, root, {'mode':'deterministic_demo', 'child_count':len(assignments),
                               'reserved_steps':len(assignments)+1, 'executor_version':self.executor.version})
        for assignment in assignments:
            child = copy.deepcopy(root)
            child.update({'id':uid('run'), 'parent_run_id':root['id'], 'parent_step_id':uid('step'),
                          'latest_sequence':0, 'based_on_run_id':None})
            child['effective_permissions']['allowed_tools'] = ['resource.inspect']
            child['effective_permissions']['decision_digest'] = digest(dumps(child['effective_permissions']).encode())
            child['effective_limits']['max_turns'] = 1
            child['effective_limits']['max_input_tokens'] = 1
            self.insert(db, child, {'assignment':assignment, 'executor_version':self.executor.version})
            self.store.event(db, root, 'child.created', {'child_run_id':child['id'], **assignment}, child['parent_step_id'])
        return root

    def insert(self, db, run, data):
        validate('run', run)
        db.execute('INSERT INTO runs VALUES(?,?,?)', (run['id'], run['task_id'], dumps(run)))
        self.store.event(db, run, 'run.queued', data)

    def children(self, root_id):
        return list(reversed([r for r in self.store.listing('runs') if r.get('parent_run_id') == root_id]))

    def assignment(self, child):
        return self.store.events(child['id'])[0]['data']['assignment']

    def detail(self, root_id):
        with self.store.lock:
            root = self.store.get('runs', root_id)
            if root['selected_engine'] != ENGINE or root.get('parent_run_id'):
                raise Problem('NOT_FOUND', '研究根 Run 不存在。', 404)
            return {'run':root, 'task':self.store.get('tasks',root['task_id']),
                    'children':[{'run':c, 'assignment':self.assignment(c), 'artifacts':self.store.artifact_list(c['id'])}
                                for c in self.children(root_id)], 'artifacts':self.store.artifact_list(root_id),
                    'mode':'deterministic_demo', 'real_model':False}

    def finish(self, db, run, status, reason):
        if run['status'] in TERMINAL:
            return
        run['status'], run['exit_reason'] = status, reason
        self.store.event(db, run, 'run.' + status, {'exit_reason':reason})

    def cancel(self, run_id):
        with self.store.transaction() as db:
            run = self.store.get('runs',run_id)
            if run['status'] in TERMINAL:
                return run
            for child in self.children(run_id):
                self.finish(db, child, 'cancelled', 'PARENT_CANCELLED')
            self.finish(db, run, 'cancelled', 'USER_CANCELLED')
            return run

    def check(self, child_id):
        child = self.store.get('runs', child_id)
        self.service.check(child_id)
        if child.get('parent_run_id'):
            self.service.check(child['parent_run_id'])

    def publish(self, db, run, name, value, media='application/json'):
        body = value.encode() if isinstance(value,str) else dumps(value).encode()
        if len(body) > 65536:
            raise Problem('OUTPUT_LIMIT', '研究结果超过 64 KiB。')
        aid, step = uid('art'), uid('step')
        artifact = {'id':aid,'run_id':run['id'],'step_id':step,'name':name,'media_type':media,
                    'size_bytes':len(body),'sha256':digest(body),'data_class':'Public',
                    'validation_status':'passed','created_at':now()}
        validate('artifact',artifact)
        db.execute('INSERT INTO artifacts VALUES(?,?,?,?)',(aid,run['id'],dumps(artifact),body))
        self.store.event(db,run,'artifact.published',{'artifact_id':aid},step)
        return artifact

    def run_child(self, child_id):
        acquired = False
        execution_step = None
        try:
            while not acquired:
                self.check(child_id)
                acquired = self.slots.acquire(timeout=.05)
            with self.store.transaction() as db:
                self.check(child_id)
                child = self.store.get('runs',child_id)
                if child['status'] != 'queued':
                    return
                parent = self.store.get('runs',child['parent_run_id'])
                if not set(child['effective_permissions']['allowed_tools']) <= set(parent['effective_permissions']['allowed_tools']):
                    raise Problem('FORBIDDEN','子权限超过父权限。')
                if not set(parent['effective_permissions']['denied_capabilities']) <= set(child['effective_permissions']['denied_capabilities']):
                    raise Problem('FORBIDDEN','子任务移除了父拒绝项。')
                if any(v > parent['effective_limits'][k] for k,v in child['effective_limits'].items()):
                    raise Problem('BUDGET_EXCEEDED','子预算超过父预算。')
                if self.store.events(child_id)[0]['data']['executor_version'] != self.executor.version:
                    raise Problem('ADAPTER_VERSION_MISMATCH','执行器版本已变化。')
                child['status']='running'
                self.store.event(db,child,'run.started')
                execution_step=uid('step')
                self.store.event(db,child,'tool.call.started',{'tool':'resource.inspect'},execution_step)
            assignment = self.assignment(child)
            resource = self.store.get('resources',assignment['resource_id'])
            raw = self.store.raw(resource['id'])
            if digest(raw) != resource['sha256']:
                raise Problem('RESOURCE_INTEGRITY_ERROR','输入摘要不匹配。')
            context = {**assignment, 'input_bytes':raw, 'allowed_tools':copy.deepcopy(child['effective_permissions']['allowed_tools']),
                       'limits':copy.deepcopy(child['effective_limits'])}
            result = self.executor.run(context,lambda:self.check(child_id))
            # Validate against the immutable assigned source, not executor-provided
            # provenance. No arbitrary text can become a verified fact.
            if len(dumps(result).encode()) > 16384 or result != evaluate(raw,resource['id']):
                raise Problem('RESULT_INVALID','子结果或来源校验失败。')
            with self.store.transaction() as db:
                self.check(child_id)
                child = self.store.get('runs',child_id)
                self.store.event(db,child,'tool.call.completed',{'tool':'resource.inspect','steps_used':1},execution_step)
                artifact = self.publish(db,child,'result.json',result)
                self.store.event(db,child,'child.result.validated',{'artifact_id':artifact['id']},artifact['step_id'])
                self.finish(db,child,'succeeded','COMPLETED')
        except Exception as exc:
            with self.store.transaction() as db:
                child=self.store.get('runs',child_id)
                code=exc.code if isinstance(exc,Problem) else 'INTERNAL_ERROR'
                if execution_step and child['status'] not in TERMINAL:
                    self.store.event(db,child,'tool.call.failed',{'error_code':code,'tool':'resource.inspect'},execution_step)
                self.finish(db,child,'failed',code)
        finally:
            if acquired:
                self.slots.release()

    def execute(self, root_id):
        try:
            with self.store.transaction() as db:
                root=self.store.get('runs',root_id)
                if root['status']!='queued' or root.get('parent_run_id'):
                    return
                self.check(root_id)
                planned=self.children(root_id)
                for budget in ('max_turns','max_input_tokens','max_cost_minor'):
                    reserve=0 if budget=='max_cost_minor' else 1
                    if sum(c['effective_limits'][budget] for c in planned)+reserve > root['effective_limits'][budget]:
                        raise Problem('BUDGET_EXCEEDED','总预算不足以覆盖全部子任务预留。')
                root['status']='running'
                self.store.event(db,root,'run.started',{'mode':'deterministic_demo'})
                task=self.store.get('tasks',root['task_id'])
                request=task['context']['variables']['request']
            children=self.children(root_id)
            with ThreadPoolExecutor(max_workers=request['concurrency'],thread_name_prefix='research-child') as pool:
                pending={pool.submit(self.run_child,c['id']) for c in children if c['status']=='queued'}
                while pending:
                    _,pending=wait(pending,timeout=.05,return_when=FIRST_COMPLETED)
                    self.check(root_id)
                    failed=any(c['status'] in {'failed','cancelled','expired'} for c in self.children(root_id))
                    if failed and request['failure_policy']=='fail_parent':
                        self.fail_tree(root_id,'CHILD_FAILED')
            self.aggregate(root_id,request)
        except Exception as exc:
            self.fail_tree(root_id,exc.code if isinstance(exc,Problem) else 'INTERNAL_ERROR')

    def fail_tree(self, root_id, reason):
        with self.store.transaction() as db:
            root=self.store.get('runs',root_id)
            for child in self.children(root_id):
                self.finish(db,child,'cancelled','PARENT_STOPPED')
            status='expired' if root['status']=='queued' and reason=='TIMEOUT' else 'failed'
            self.finish(db,root,status,reason)

    def aggregate(self, root_id, request):
        with self.store.transaction() as db:
            self.check(root_id)
            root=self.store.get('runs',root_id)
            children=self.children(root_id)
            if any(c['status'] not in TERMINAL for c in children):
                raise Problem('CHILD_INCOMPLETE','仍有未结束子任务，不能提前汇总。')
            successful=[c for c in children if c['status']=='succeeded']
            failed=[c for c in children if c['status']!='succeeded']
            if not successful or (failed and request['failure_policy']=='fail_parent'):
                self.finish(db,root,'failed','CHILD_FAILED')
                return
            entries=[]
            for child in children:
                entry={'child_run_id':child['id'],**self.assignment(child),'status':child['status'],'exit_reason':child['exit_reason']}
                artifacts=self.store.artifact_list(child['id'])
                if artifacts:
                    artifact=artifacts[0]
                    body=db.execute('SELECT body FROM artifacts WHERE id=?',(artifact['id'],)).fetchone()[0]
                    if digest(body)!=artifact['sha256']:
                        raise Problem('ARTIFACT_INTEGRITY_ERROR','子产物摘要校验失败。')
                    result=json.loads(body)
                    entry.update({'artifact_id':artifact['id'],'sha256':artifact['sha256'],'summary':result['summary']})
                entries.append(entry)
            manifest={'mode':'deterministic_demo','real_model':False,'coverage':'partial' if failed else 'complete',
                      'root_run_id':root_id,'children':entries,'successful':len(successful),'failed':len(failed),
                      'usage':{'model_calls':0,'cost_minor':0,'steps_reserved':len(children)+1,
                               'steps_used':1+sum(any(e['event_type']=='run.started' for e in self.store.events(c['id'])) for c in children)},
                      'risk_assessment':'not_assessed','notice':'模拟资料与固定函数演示，不是实时研报或投资建议。'}
            self.publish(db,root,'research-manifest.json',manifest)
            lines=['# 多专项研究演示','',manifest['notice'],'','覆盖：'+manifest['coverage'],
                   '风险状态：未评估；缺失资料不能解释为无风险。','']
            for entry in entries:
                lines.extend(['## '+COMPANIES[entry['company']]+' / '+ROLES[entry['role']],
                              entry.get('summary','未获得有效结果：'+str(entry['exit_reason'])),
                              'Child Run: '+entry['child_run_id'],'来源资源: '+entry['resource_id'],''])
            self.publish(db,root,'research-report.md','\n'.join(lines),'text/markdown')
            self.store.event(db,root,'research.aggregated',{'coverage':manifest['coverage'],'successful':len(successful),'failed':len(failed)})
            self.finish(db,root,'succeeded','COMPLETED_WITH_WARNINGS' if failed else 'COMPLETED')

    def recover(self):
        for root in self.store.listing('runs'):
            if root['selected_engine']!=ENGINE or root.get('parent_run_id'):
                continue
            children=self.children(root['id'])
            if root['status']=='running' or any(c['status']=='running' for c in children):
                self.fail_tree(root['id'],'SERVER_RESTARTED')
            elif root['status'] in TERMINAL:
                self.fail_tree(root['id'],'SERVER_RESTARTED')
