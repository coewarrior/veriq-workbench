vars.put('ws.send','false')
try {
    def step=new JsonSlurper().parseText(new String(Parameters.decodeBase64(),'UTF-8'))
    vars.putObject('ws.step',step)
    if(!step.cleanup && vars.get('ws.case_ok')!='true') { SampleResult.setIgnore();return }
    def req=expand(step.request,(Map)vars.getObject('ws.values'))
    def path=req.path
    if(!(path instanceof String) || !path.startsWith('/') || path.startsWith('//') || path.contains('\\') || path.contains('#') || path.contains('..') || path.find(/[\x00-\x20]/)) throw new IllegalArgumentException('Invalid request path')
    if(req.containsKey('raw_body') && !(req.raw_body instanceof String))throw new IllegalArgumentException('Raw body must be text')
    req.headers=(req.headers?:[:])
    req.headers.each{k,v->if(!(v instanceof String) || (k+v).find(/[\r\n]/))throw new IllegalArgumentException('Invalid header')}
    vars.putObject('ws.request',req)
    vars.put('ws.send','true')
    SampleResult.setIgnore()
} catch(Exception ignored) {
    SampleResult.setSuccessful(false);SampleResult.setResponseCode('PREPARATION_ERROR');SampleResult.setResponseMessage('请求参数或变量无法转换；未发送请求')
    vars.put('ws.case_ok','false');vars.put('ws.round_ok','false')
    if(((Map)vars.getObject('ws.step'))?.cleanup) {((AtomicLong)props.get('ws.cleanup_failed')).incrementAndGet();props.put('ws.stop','cleanup')}
}
