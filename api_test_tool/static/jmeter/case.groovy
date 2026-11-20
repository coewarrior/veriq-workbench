SampleResult.setIgnore()
def c=new JsonSlurper().parseText(new String(Parameters.decodeBase64(),'UTF-8'))
def values=[:]
c.each{k,v->values[k]=v.kind=='unique'?(v.prefix?:'mvp_')+UUID.randomUUID().toString().replace('-',''):v.value}
vars.putObject('ws.values',values)
def jar=new CookieManager();jar.testStarted();vars.putObject('ws.cookies',jar)
vars.put('ws.case_ok','true')
