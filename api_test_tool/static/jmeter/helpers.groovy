import groovy.json.JsonSlurper
import groovy.json.JsonOutput
import org.apache.jmeter.assertions.AssertionResult
import org.apache.jmeter.protocol.http.control.HeaderManager
import org.apache.jmeter.protocol.http.control.Header
import org.apache.jmeter.protocol.http.control.CookieManager
import java.util.concurrent.atomic.AtomicLong

Object expand(Object value, Map values) {
    if(value instanceof Map) return value.collectEntries { k,v -> [k,expand(v,values)] }
    if(value instanceof List) return value.collect { expand(it,values) }
    if(!(value instanceof String)) return value
    def whole=value =~ /^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$/
    if(whole.matches()) { def key=whole[0][1]; if(!values.containsKey(key)) throw new IllegalArgumentException('Missing variable'); return values[key] }
    return value.replaceAll(/\$\{([A-Za-z_][A-Za-z0-9_]*)\}/) { all,key ->
        if(!values.containsKey(key)) throw new IllegalArgumentException('Missing variable')
        def v=values[key]; if(v instanceof Map || v instanceof List)throw new IllegalArgumentException('Non-scalar variable'); String.valueOf(v)
    }
}
Object pointer(Object value,String path,Object missing) {
    if(path=='') return value
    for(def token:path.substring(1).split('/',-1)) {
        token=token.replace('~1','/').replace('~0','~')
        if(value instanceof Map && value.containsKey(token)) value=value[token]
        else if(value instanceof List && token==~ /0|[1-9][0-9]*/ && token.toBigInteger()<value.size()) value=value[token.toInteger()]
        else return missing
    }
    return value
}
boolean equal(Object a,Object b) {
    if(a==null || b==null) return a==null && b==null
    if(a instanceof Map && b instanceof Map) return a.keySet()==b.keySet() && a.every{k,v->equal(v,b[k])}
    if(a instanceof List && b instanceof List) return a.size()==b.size() && (0..<a.size()).every{equal(a[it],b[it])}
    if(a instanceof Number && b instanceof Number) return (a instanceof BigDecimal)==(b instanceof BigDecimal) && a==b
    return a.class==b.class && a==b
}
boolean matchesType(Object v,String t) {
    switch(t) {
        case 'object': return v instanceof Map
        case 'array': return v instanceof List
        case 'string': return v instanceof String
        case 'boolean': return v instanceof Boolean
        case 'null': return v==null
        case 'number': return v instanceof Number
        case 'integer': return v instanceof Number && new BigDecimal(v.toString()).stripTrailingZeros().scale()<=0
    }
    return false
}
boolean schema(Object v,Object s) {
    if(s instanceof Boolean) return s
    if(s.containsKey('type') && !(s.type instanceof List?s.type:[s.type]).any{matchesType(v,it)}) return false
    if(s.containsKey('enum') && !s.enum.any{equal(v,it)}) return false
    if(s.containsKey('const') && !equal(v,s.const)) return false
    if(v instanceof Map) {
        if(s.required && !s.required.every{v.containsKey(it)}) return false
        if((s.properties?:[:]).any{k,defn->v.containsKey(k) && !schema(v[k],defn)}) return false
        for(def k:v.keySet()) if(!(s.properties?:[:]).containsKey(k) && s.containsKey('additionalProperties') && !schema(v[k],s.additionalProperties)) return false
        if(s.containsKey('minProperties') && v.size()<s.minProperties || s.containsKey('maxProperties') && v.size()>s.maxProperties) return false
    }
    if(v instanceof List) {
        if(s.containsKey('minItems') && v.size()<s.minItems || s.containsKey('maxItems') && v.size()>s.maxItems) return false
        if(s.containsKey('items') && !v.every{schema(it,s.items)}) return false
        if(s.uniqueItems && v.withIndex().any{a,i->v.take(i).any{equal(a,it)}}) return false
    }
    if(v instanceof String) {
        def n=v.codePointCount(0,v.length())
        if(s.containsKey('minLength') && n<s.minLength || s.containsKey('maxLength') && n>s.maxLength) return false
    }
    if(v instanceof Number) {
        if(s.containsKey('minimum') && v<s.minimum || s.containsKey('maximum') && v>s.maximum) return false
        if(s.containsKey('exclusiveMinimum') && v<=s.exclusiveMinimum || s.containsKey('exclusiveMaximum') && v>=s.exclusiveMaximum) return false
    }
    if(s.allOf && !s.allOf.every{schema(v,it)}) return false
    if(s.anyOf && !s.anyOf.any{schema(v,it)}) return false
    if(s.oneOf && s.oneOf.count{schema(v,it)}!=1) return false
    if(s.containsKey('not') && schema(v,s.not)) return false
    return true
}
