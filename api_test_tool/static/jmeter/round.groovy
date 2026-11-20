SampleResult.setIgnore()
synchronized(props) {
    if(!props.get('ws.started')) {
        props.put('ws.started',System.currentTimeMillis())
        props.put('ws.rounds',new AtomicLong())
        props.put('ws.finished',new AtomicLong())
        props.put('ws.passed',new AtomicLong())
        props.put('ws.cleanup_failed',new AtomicLong())
    }
}
def now=System.currentTimeMillis()
if(new File('stop.request').exists() || props.get('ws.stop') || now-(long)props.get('ws.started')>=Long.parseLong(props.getProperty('ws.duration'))*1000 || ((AtomicLong)props.get('ws.rounds')).getAndIncrement()>=Long.parseLong(props.getProperty('ws.rounds_limit'))) {
    ctx.getThread().stop();return
}
vars.put('ws.round_ok','true')
