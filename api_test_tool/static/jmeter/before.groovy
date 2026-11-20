def req=(Map)vars.getObject('ws.request')
def base=new URI(props.getProperty('ws.base'))
def query=[]
(req.params?:[:]).each{k,v->(v instanceof List?v:[v]).each{item->if(item!=null)query.add(URLEncoder.encode(k.toString(),'UTF-8')+'='+URLEncoder.encode(item.toString(),'UTF-8'))}}
def full=base.rawPath+req.path+(query? (req.path.contains('?')?'&':'?')+query.join('&'):'')
sampler.setProtocol(base.scheme);sampler.setDomain(base.host);sampler.setPort(base.port<0?(base.scheme=='https'?443:80):base.port)
sampler.setPath(full);sampler.setMethod(req.method);sampler.setContentEncoding('UTF-8');sampler.setFollowRedirects(false);sampler.setAutoRedirects(false)
sampler.setConnectTimeout('5000');sampler.setResponseTimeout('10000')
sampler.getArguments().removeAllArguments()
def hm=new HeaderManager();req.headers.each{k,v->hm.add(new Header(k,v))}
if(req.containsKey('json') || req.containsKey('raw_body')) {
    def body=req.containsKey('json')?JsonOutput.toJson(req.json):req.raw_body
    sampler.addNonEncodedArgument('',body,'');sampler.setPostBodyRaw(true)
    if(req.containsKey('json') && !req.headers.keySet().any{it.equalsIgnoreCase('Content-Type')})hm.add(new Header('Content-Type','application/json'))
} else sampler.setPostBodyRaw(false)
sampler.setHeaderManager(hm)
def jar=(CookieManager)vars.getObject('ws.cookies');if(req.session==false){jar=new CookieManager();jar.testStarted()};sampler.setCookieManager(jar)
