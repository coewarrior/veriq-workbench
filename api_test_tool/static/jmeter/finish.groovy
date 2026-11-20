SampleResult.setIgnore()
((AtomicLong)props.get('ws.finished')).incrementAndGet()
if(vars.get('ws.round_ok')=='true')((AtomicLong)props.get('ws.passed')).incrementAndGet()
synchronized(props) {
    new File('rounds.json').text=JsonOutput.toJson([started:props.get('ws.started'),finished:((AtomicLong)props.get('ws.finished')).get(),passed:((AtomicLong)props.get('ws.passed')).get(),cleanup_failed:((AtomicLong)props.get('ws.cleanup_failed')).get(),reason:props.get('ws.stop')])
}
def until=System.currentTimeMillis()+Long.parseLong(props.getProperty('ws.think'))
while(System.currentTimeMillis()<until && !new File('stop.request').exists() && !props.get('ws.stop'))Thread.sleep(Math.min(100,until-System.currentTimeMillis()))
