def step=(Map)vars.getObject('ws.step'), values=(Map)vars.getObject('ws.values')
def missing=new Object(), data=missing, code=prev.responseCode.isInteger()?prev.responseCode.toInteger():0
try{data=new JsonSlurper().parseText(prev.getResponseDataAsString())}catch(Exception ignored){}
def headers=[:],cookies=[:]
prev.responseHeaders.eachLine{line->def i=line.indexOf(':');if(i>0){def k=line.substring(0,i).trim().toLowerCase(),v=line.substring(i+1).trim();headers[k]=v;if(k=='set-cookie'){def kv=v.split(';',2)[0].split('=',2);if(kv.size()==2)cookies[kv[0]]=kv[1]}}}
def ok=code>=100 && code<600
try {
    def assertions=expand(step.assertions?:[],values)
    assertions.eachWithIndex{a,index->
        def actual=pointer(data,a.pointer?:'',missing),pass=false
        switch(a.kind) {
            case 'status':pass=code==a.expected;break
            case 'status_in':pass=a.expected.contains(code);break
            case 'status_not_in':pass=!a.expected.contains(code);break
            case 'json_exists':pass=!actual.is(missing);break
            case 'json_equal':pass=!actual.is(missing)&&equal(actual,a.expected);break
            case 'equals_variable':pass=!actual.is(missing)&&values.containsKey(a.variable)&&equal(actual,values[a.variable]);break
            case 'header_equal':pass=headers.containsKey(a.name.toLowerCase())&&equal(headers[a.name.toLowerCase()],a.expected);break
            case 'cookie_present':pass=cookies.containsKey(a.name)&&cookies[a.name]!='';break
            case 'json_schema':pass=!data.is(missing)&&schema(data,a.expected);break
            case 'response_schema':pass=schema(data.is(missing)?[status:code]:[status:code,json:data],a.expected);break
        }
        if(!pass){def failure=new AssertionResult(a.kind+':'+index);failure.setFailure(true);failure.setFailureMessage('预期不匹配：'+a.kind);prev.addAssertionResult(failure);ok=false}
    }
    if(code>=500 && !assertions.any{it.kind=='status'&&it.expected==code || it.kind=='status_in'&&it.expected.contains(code)})ok=false
    (step.extract?:[]).each{e->def v=e.from=='json'?pointer(data,e.pointer?:'',missing):e.from=='header'?(headers.containsKey(e.key.toLowerCase())?headers[e.key.toLowerCase()]:missing):(cookies.containsKey(e.key)?cookies[e.key]:missing);if(v.is(missing))ok=false;else values[e.name]=v}
}catch(Exception ignored){ok=false;def f=new AssertionResult('conversion');f.setFailure(true);f.setFailureMessage('变量或断言无法求值');prev.addAssertionResult(f)}
prev.setSuccessful(ok)
if(!ok){vars.put('ws.round_ok','false');if(step.cleanup){((AtomicLong)props.get('ws.cleanup_failed')).incrementAndGet();props.put('ws.stop','cleanup')}else vars.put('ws.case_ok','false')}
