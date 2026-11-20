"""Static registration and short calls for the native REPL's existing memory.

No eval, local code import, browser bridge, persisted page handle or credentials.
The caller installs the literal source once in its own native tool session.
"""
def native_runtime_package(call_source, executor_ref, receipt_file, *, browser_mode='cua'):
    import hashlib
    source = NATIVE_BROWSER_TEMPLATE + NATIVE_OBSERVATION_SEND_TEMPLATE + call_source
    key = hashlib.sha256((source if browser_mode == 'cua' else browser_mode + source).encode()).hexdigest()
    registration = (NATIVE_BROWSER_TEMPLATE + '\n' + NATIVE_OBSERVATION_SEND_TEMPLATE + '\n'
        + 'var nativeLoadedCases = typeof nativeLoadedCases === "undefined" ? new Map() : nativeLoadedCases;\n'
        + 'nativeLoadedCases.set(' + json.dumps(key) + ', ((nativeBrowserCase,nativeSendObservation,nativeFinishTask,nativeReadObservationReceipt) => '
        + 'async function({tab:nativeTab,case_id:nativeCaseId,directory}) {\n'
        + 'const nativeEmit = observation => nativeSendObservation(directory,observation);\n'
        + call_source + '\n})(nativeBrowserCase,nativeSendObservation,nativeFinishTask,nativeReadObservationReceipt));\n'
        + 'await (await import("node:fs/promises")).writeFile(' + json.dumps(str(receipt_file))
        + ',JSON.stringify({key:' + json.dumps(key) + ',executor_ref:' + json.dumps(executor_ref)
        + ',loaded_at:new Date().toISOString()}),{encoding:"utf8",mode:0o600});\n'
        + 'nodeRepl.write({runtime_loaded:true,key:' + json.dumps(key) + '});')
    return {'key': key, 'registration_source': registration, 'receipt_file': str(receipt_file)}


def native_runtime_call(key, directory, *, library=False, entry_url=None, browser_mode='cua'):
    if entry_url is not None and library and browser_mode != 'isolated':
        raise ValueError('未知业务的公共函数加载不能自动打开并执行用例')
    guard = ('if(typeof nativeLoadedCases==="undefined"||!nativeLoadedCases.has(' + json.dumps(key)
        + '))throw new Error("Native session reset: reinstall the verified static routine before business");\n'
    )
    acquire = ('var nativeTab=await nativeBrowserEnvironment.enter(' + json.dumps(entry_url) + ');\n'
               if browser_mode == 'isolated' else
               'var nativeTab=await cua.createBrowserTab("iab",' + json.dumps(entry_url) + ',{visible:false});\n')
    body = (
        'var nativeFinish=close=>nativeFinishTask({close,directory:' + json.dumps(str(directory)) + '});\n'
        + 'var nativeReceipt=(id,options)=>nativeReadObservationReceipt(' + json.dumps(str(directory)) + ',id,options);\n'
        + (acquire if entry_url is not None else '')
        + ('var nativeCurrent=' if library else 'var nativeSummary=') + 'await nativeLoadedCases.get(' + json.dumps(key)
        + ')({tab:nativeTab,case_id:nativeCaseId,directory:' + json.dumps(str(directory)) + '});\n'
        + ('var nativeBrowserCase=nativeCurrent.run;var nativeEmit=nativeCurrent.emit;'
           if library else 'nodeRepl.write(nativeSummary);'))
    if library:
        return guard + body
    # Actual native boundaries, captured without changing the cached function or
    # asking a model to reconstruct timestamps from its session transcript.
    return (guard + 'var nativeCallTiming={case_id:nativeCaseId,started_at:new Date().toISOString()};\ntry{\n' + body
        + '\n}catch(error){nativeCallTiming.error=String(error);throw error;}finally{\n'
        + 'nativeCallTiming.finished_at=new Date().toISOString();\n'
        + 'try{await (await import("node:fs/promises")).writeFile('
        + json.dumps(str(Path(directory) / 'native-call-timing-')) + '+Date.now()+"-"+Math.random().toString(16).slice(2)+".json"'
        + ',JSON.stringify(nativeCallTiming),{encoding:"utf8",mode:0o600});}'
        + 'catch(error){nodeRepl.write({timing_warning:String(error)});}\n}')
