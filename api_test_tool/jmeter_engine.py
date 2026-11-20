"""Compile reviewed HTTP chains to Apache JMeter and consume its CSV measurements."""
from __future__ import annotations
import base64
import csv
import json
import math
import os
from pathlib import Path
import shutil
import shlex
import socket
import ssl
import subprocess
import threading
import time
from datetime import datetime, timezone
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET
import zipfile
from .execution import Redactor, validate_bundle
from .load_report import render_load_report

SCRIPTS=Path(__file__).parent/'static'/'jmeter'
SCHEMA_KEYS={'type','properties','required','additionalProperties','items','minItems','maxItems','uniqueItems','minLength','maxLength','minimum','maximum','exclusiveMinimum','exclusiveMaximum','enum','const','allOf','anyOf','oneOf','not','minProperties','maxProperties','title','description','default','examples','$schema','$id'}


def capabilities():
    return {'available':bool(shutil.which(os.environ.get('JMETER_BIN','jmeter'))),
            'max_virtual_users':int(os.environ.get('JMETER_MAX_USERS','10000')), 'engine':'jmeter', 'version':'5.6.3'}


def configuration(data):
    if not isinstance(data,dict) or data.get('enabled') is not True:raise ValueError('请先开启压测')
    limits={'virtual_users':(10,1,capabilities()['max_virtual_users']),'duration_seconds':(30,1,86400),
            'ramp_up_seconds':(5,0,86400),'think_time_ms':(200,0,60000),'max_rounds':(1000,1,10000000)}
    result={'engine':'jmeter'}
    for name,(default,low,high) in limits.items():
        value=data.get(name,default)
        if type(value) is not int or not low<=value<=high:raise ValueError(f'{name} 须为 {low}～{high} 的整数')
        result[name]=value
    if result['ramp_up_seconds']>result['duration_seconds']:raise ValueError('升压时间不能超过持续时间')
    return result


def schema_supported(s):
    if isinstance(s,bool):return
    unknown=set(s)-SCHEMA_KEYS
    if unknown:raise ValueError('JMeter 尚不支持这些 Schema 关键字：'+', '.join(sorted(unknown)))
    if isinstance(s.get('items'),list):raise ValueError('JMeter 暂不支持元组式 items Schema')
    if '$schema' in s and not any(x in s['$schema'] for x in ('draft-07','2019-09','2020-12')):raise ValueError('JMeter Schema 支持 draft-07 / 2019-09 / 2020-12')
    for v in s.get('properties',{}).values():schema_supported(v)
    for key in ('items','additionalProperties','not'):
        if key in s:schema_supported(s[key])
    for key in ('allOf','anyOf','oneOf'):
        for v in s.get(key,[]):schema_supported(v)


def selected_cases(bundle,ids):
    if not isinstance(ids,list) or any(not isinstance(cid,str) for cid in ids):raise ValueError('用例编号必须为字符串列表')
    chosen=[c for c in bundle['cases'] if c['id'] in ids]
    if not ids or len(chosen)!=len(set(ids)) or any(c.get('state')!='READY' for c in chosen):raise ValueError('请选择已核对且可执行的用例')
    selected={**bundle,'cases':chosen}
    errors=validate_bundle(selected)
    if errors:raise ValueError('用例校验未通过：'+errors[0]['message'])
    if bundle.get('web',{}).get('trusted_cleanup'):raise ValueError('这些用例依赖本地数据库清理，暂不能直接转换成 JMeter；请提供 HTTP 清理步骤或独立的压测数据方案')
    for c in chosen:
        for step in c.get('steps',[])+c.get('cleanup_steps',[]):
            for a in step.get('assertions',[]):
                if a['kind'] in {'json_schema','response_schema'}:schema_supported(a['expected'])
    return chosen


def prop(node,key,value,kind='stringProp'):
    ET.SubElement(node,kind,{'name':key}).text=str(value).lower() if isinstance(value,bool) else str(value)


def element(parent,tag,name,**attrs):
    node=ET.SubElement(parent,tag,{'guiclass':attrs.pop('guiclass','TestBeanGUI'),'testclass':tag,'testname':name,'enabled':'true',**attrs})
    tree=ET.SubElement(parent,'hashTree')
    return node,tree


def script(parent,kind,name,file,params=''):
    node,tree=element(parent,kind,name)
    for key,value in [('scriptLanguage','groovy'),('filename',file+'.groovy'),('parameters',params),('cacheKey','true'),('script','')]:prop(node,key,value)
    return tree


def encoded(value):return base64.b64encode(json.dumps(value,ensure_ascii=False).encode()).decode()


def write_plan(bundle,environment,directory,config,ids,addresses=()):
    cases=selected_cases(bundle,ids)
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o700)
    root=ET.Element('jmeterTestPlan',{'version':'1.2','properties':'5.0','jmeter':'5.6.3'})
    tree=ET.SubElement(root,'hashTree');test,tree=element(tree,'TestPlan','API 测试台压测计划',guiclass='TestPlanGui')
    prop(test,'TestPlan.serialize_threadgroups',False,'boolProp')
    tg,tree=element(tree,'ThreadGroup','并发用户',guiclass='ThreadGroupGui')
    prop(tg,'ThreadGroup.num_threads',config['virtual_users']);prop(tg,'ThreadGroup.ramp_time',config['ramp_up_seconds'])
    prop(tg,'ThreadGroup.on_sample_error','continue');prop(tg,'ThreadGroup.scheduler',False,'boolProp')
    loop=ET.SubElement(tg,'elementProp',{'name':'ThreadGroup.main_controller','elementType':'LoopController','guiclass':'LoopControlPanel','testclass':'LoopController','testname':'循环','enabled':'true'})
    prop(loop,'LoopController.loops',-1);prop(loop,'LoopController.continue_forever',True,'boolProp')
    if addresses:
        dns,_=element(tree,'DNSCacheManager','固定已核准的目标解析')
        prop(dns,'DNSCacheManager.isCustomResolver',True,'boolProp');prop(dns,'DNSCacheManager.clearEachIteration',False,'boolProp')
        hosts=ET.SubElement(dns,'collectionProp',{'name':'DNSCacheManager.hosts'})
        host=ET.SubElement(hosts,'elementProp',{'name':urlsplit(environment['base_url']).hostname,'elementType':'StaticHost'})
        prop(host,'StaticHost.Name',urlsplit(environment['base_url']).hostname);prop(host,'StaticHost.Address',','.join(addresses))
    script(tree,'JSR223Sampler','CONTROL:round','round')
    for ci,c in enumerate(cases):
        script(tree,'JSR223Sampler',f'CONTROL:case:{ci}','case',encoded(c.get('variables',{})))
        for cleanup,steps in ((False,c.get('steps',[])),(True,c.get('cleanup_steps',[]))):
            for si,step in enumerate(steps):
                script(tree,'JSR223Sampler',f'CONTROL:prepare:{ci}:{si}','prepare',encoded({**step,'cleanup':cleanup}))
                guard,gtree=element(tree,'IfController','有请求且前置成功',guiclass='IfControllerPanel')
                prop(guard,'IfController.condition',"${__groovy(vars.get('ws.send') == 'true')}")
                prop(guard,'IfController.useExpression',True,'boolProp')
                request,rtree=element(gtree,'HTTPSamplerProxy',f'{"CLEANUP" if cleanup else "HTTP"}:{ci}:{si}',guiclass='HttpTestSampleGui')
                prop(request,'HTTPSampler.implementation','HttpClient4')
                script(rtree,'JSR223PreProcessor','构造请求','before')
                script(rtree,'JSR223PostProcessor','检查响应并提取变量','after')
    script(tree,'JSR223Sampler','CONTROL:finish','finish')
    ET.indent(root)
    ET.ElementTree(root).write(directory/'plan.jmx',encoding='utf-8',xml_declaration=True)
    for name in ('round','case','prepare','before','after','finish'):
        (directory/(name+'.groovy')).write_text(SCRIPTS.joinpath('helpers.groovy').read_text()+'\n'+SCRIPTS.joinpath(name+'.groovy').read_text())
    properties={'ws.base':environment['base_url'],'ws.duration':config['duration_seconds'],'ws.think':config['think_time_ms'],'ws.rounds_limit':config['max_rounds'],
                'jmeterengine.nongui.port':0,'jmeter.save.saveservice.output_format':'csv','jmeter.save.saveservice.timestamp_format':'ms',
                'jmeter.save.saveservice.print_field_names':'true','jmeter.save.saveservice.autoflush':'true',
                'jmeter.save.saveservice.response_message':'false','jmeter.save.saveservice.url':'false','jmeter.save.saveservice.assertion_results_failure_message':'true',
                'httpsampler.max_bytes_to_store_per_request':1048576,'httpclient4.retrycount':0,'sampleresult.timestamp.start':'true'}
    (directory/'run.properties').write_text('\n'.join(f'{k}={v}' for k,v in properties.items())+'\n')
    with zipfile.ZipFile(directory/'plan.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for name in ['plan.jmx','run.properties']+[n+'.groovy' for n in ('round','case','prepare','before','after','finish')]:archive.write(directory/name,name)
        archive.writestr('README.txt','Apache JMeter 5.6.3 / Java 17+\n在此目录执行：jmeter -n -t plan.jmx -q run.properties -l samples.jtl -j jmeter.log\n创建 stop.request 文件可停止新轮次；在途链路继续清理。计划包含当前用例的参数和凭据，请妥善保存。\n')


def parse_results(path,config,environment,ids,started_at,wall_elapsed,stop_reason):
    samples=[];controls=[]
    if path.exists():
        with path.open(newline='') as f:
            for row in csv.DictReader(f):
                try:
                    sample={'at':int(row['timeStamp']),'elapsed':float(row['elapsed']),'ok':row['success']=='true','label':row['label'],'code':row['responseCode'],'threads':int(row.get('allThreads',0))}
                except (ValueError,KeyError):continue
                if sample['label'].startswith(('HTTP:','CLEANUP:')):samples.append(sample)
                elif not sample['ok']:controls.append(sample)
    epochs=[s['at'] for s in samples];start=min(epochs) if epochs else 0
    end=max((s['at']+s['elapsed'] for s in samples),default=start)
    elapsed=max(.001,(end-start)/1000) if samples else wall_elapsed
    series={};latencies=[];codes={}
    for s in samples:
        sec=int((s['at']+s['elapsed']-start)/1000)
        point=series.setdefault(sec,{'second':sec,'requests':0,'failed':0,'_latencies':[],'active_threads':0})
        point['requests']+=1;point['failed']+=int(not s['ok']);point['active_threads']=max(point['active_threads'],s['threads'])
        codes[s['code']]=codes.get(s['code'],0)+1
        if s['code'].isdigit():latencies.append(s['elapsed']);point['_latencies'].append(s['elapsed'])
    def percentiles(values):
        values.sort()
        return {**{name:values[max(0,math.ceil(p*len(values))-1)] if values else None for name,p in [('p50',.5),('p95',.95),('p99',.99)]},'count':len(values),'max':max(values) if values else None}
    for p in series.values():p['latency_ms']=percentiles(p.pop('_latencies'))
    rounds={}
    try:rounds=json.loads(path.with_name('rounds.json').read_text())
    except (OSError,ValueError):pass
    failed=sum(not s['ok'] for s in samples)
    return {'kind':'load','engine':'jmeter','engine_version':'5.6.3','started_at':started_at,'finished_at':datetime.now(timezone.utc).isoformat(),
            'environment':{k:environment[k] for k in ('name','base_url')},'config':config,'case_ids':ids,
            'requests_sent':len(samples),'requests_failed':failed,'error_rate':failed/len(samples) if samples else 0,
            'elapsed_seconds':round(elapsed,3),'wall_elapsed_seconds':round(wall_elapsed,3),'requests_per_second':round(len(samples)/max(elapsed,.001),3),
            'latency_ms':percentiles(latencies),'status_codes':codes,'series':sorted(series.values(),key=lambda p:p['second']),'series_basis':'request_completed',
            'rounds_finished':rounds.get('finished',0),'rounds_passed':rounds.get('passed',0),'cleanup_failures':rounds.get('cleanup_failed',0),
            'engine_errors':len(controls),'stop_reason':stop_reason if not rounds.get('reason') else '清理失败，已停止新增轮次',
            'failure_samples':[s for s in samples if not s['ok']][:20],
            'measurement':'由 Apache JMeter 独立 Java 进程发压。请求包括前置、业务及 HTTP 清理；RPS 按首个请求开始至最后请求完成的采样窗口计算，不含引擎启动时间。耗时分位数只含收到 HTTP 响应的请求。未通过包括断言失败和连接错误；控制步骤异常单独记录。停止或达到时长后停止新轮次，在途链路继续清理。'}


def run_jmeter(bundle,environment,output_dir,config,*,case_ids,progress=lambda _:None,stop=None,addresses=()):
    binary=shutil.which(os.environ.get('JMETER_BIN','jmeter'))
    if not binary:raise ValueError('JMeter 未安装，请联系管理员完成执行引擎部署')
    stop=stop or threading.Event();out=Path(output_dir);private=out/'jmeter';private.mkdir(parents=True,exist_ok=True)
    target=urlsplit(environment['base_url'])
    if target.scheme=='https':
        try:
            with socket.create_connection(((addresses or (target.hostname,))[0],target.port or 443),timeout=10) as raw:
                with ssl.create_default_context().wrap_socket(raw,server_hostname=target.hostname): pass
        except (OSError,ssl.SSLError): raise ValueError('目标 HTTPS 证书或连接预检失败，未启动 JMeter') from None
    write_plan(bundle,environment,private,config,case_ids,addresses)
    started_at=datetime.now(timezone.utc).isoformat();started=time.monotonic()
    jar=Path(binary).resolve().parent/'ApacheJMeter.jar'
    if not jar.is_file(): raise ValueError('JMeter 安装目录不完整，缺少 ApacheJMeter.jar')
    java=str(Path(os.environ['JAVA_HOME'])/'bin'/'java') if os.environ.get('JAVA_HOME') else shutil.which('java')
    if not java: raise ValueError('Java 运行环境未安装')
    command=[java,*shlex.split(os.environ.get('JMETER_HEAP','-Xms128m -Xmx4g')),'-Xss256k','-XX:ActiveProcessorCount=8','-Djava.awt.headless=true',
             '-jar',str(jar),'-n','-t','plan.jmx','-q','run.properties','-l','samples.jtl','-j','jmeter.log']
    env={k:v for k,v in os.environ.items() if k in {'PATH','JAVA_HOME','LANG','LC_ALL','TMPDIR'}}
    env.update(HOME=str(private),HEAP=os.environ.get('JMETER_HEAP','-Xms128m -Xmx4g'),JVM_ARGS='-Xss256k -XX:ActiveProcessorCount=8 -Djava.awt.headless=true')
    progress(f"正在启动 Apache JMeter：{config['virtual_users']} 个用户，升压 {config['ramp_up_seconds']} 秒，持续 {config['duration_seconds']} 秒")
    grace=max(180,30+15*sum(len(c.get('steps',[]))+len(c.get('cleanup_steps',[])) for c in bundle['cases'] if c['id'] in case_ids))
    reason='达到设定时长或轮次上限';forced=False;last_report=0
    with (private/'console.log').open('w') as log:
        process=subprocess.Popen(command,cwd=private,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        try:
            while process.poll() is None:
                elapsed=time.monotonic()-started
                if stop.is_set():
                    (private/'stop.request').touch();reason='用户停止；在途链路已完成清理'
                if (private/'samples.jtl').exists() and (private/'samples.jtl').stat().st_size>256*1024*1024:
                    (private/'stop.request').touch();reason='结果文件达到执行节点保存容量，停止新轮次'
                if elapsed-last_report>=5:
                    progress(f'JMeter 执行中，已用时 {int(elapsed)} 秒'+('；正在等待在途链路清理' if stop.is_set() else ''))
                    last_report=elapsed
                if elapsed>config['duration_seconds']+grace:
                    process.terminate();forced=True;reason='JMeter 未能按时退出，任务被终止；在途清理可能未完成'
                    try:process.wait(timeout=15)
                    except subprocess.TimeoutExpired:process.kill()
                    break
                time.sleep(.25)
            process.wait()
        finally:
            if process.poll() is None:process.kill();process.wait()
    result=parse_results(private/'samples.jtl',config,environment,case_ids,started_at,time.monotonic()-started,reason)
    result['engine_exit_code']=process.returncode
    result['engine_status']='failed' if process.returncode or forced or result['engine_errors'] or not result['requests_sent'] else 'completed'
    if result['engine_status']=='failed' and not forced:result['stop_reason']='JMeter 执行未完成或控制步骤异常，请检查计划和执行节点资源；已保留收到的测量结果'
    result=Redactor().snapshot(result)
    out.joinpath('result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    out.joinpath('bundle.json').write_text(json.dumps(Redactor().snapshot(bundle),ensure_ascii=False,indent=2))
    out.joinpath('index.html').write_text(render_load_report(result))
    return result
