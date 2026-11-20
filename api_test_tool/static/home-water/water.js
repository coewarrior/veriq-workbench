var Vc=Object.create;var Jl=Object.defineProperty;var Wc=Object.getOwnPropertyDescriptor;var Hc=Object.getOwnPropertyNames;var $c=Object.getPrototypeOf,Qc=Object.prototype.hasOwnProperty;var Ue=(e,t)=>()=>(t||e((t={exports:{}}).exports,t),t.exports);var Gc=(e,t,n,r)=>{if(t&&typeof t=="object"||typeof t=="function")for(let o of Hc(t))!Qc.call(e,o)&&o!==n&&Jl(e,o,{get:()=>t[o],enumerable:!(r=Wc(t,o))||r.enumerable});return e};var Ye=(e,t,n)=>(n=e!=null?Vc($c(e)):{},Gc(t||!e||!e.__esModule?Jl(n,"default",{value:e,enumerable:!0}):n,e));var da=Ue(C=>{"use strict";var pn=Symbol.for("react.element"),qc=Symbol.for("react.portal"),Zc=Symbol.for("react.fragment"),Xc=Symbol.for("react.strict_mode"),Yc=Symbol.for("react.profiler"),Kc=Symbol.for("react.provider"),Jc=Symbol.for("react.context"),ed=Symbol.for("react.forward_ref"),td=Symbol.for("react.suspense"),nd=Symbol.for("react.memo"),rd=Symbol.for("react.lazy"),ea=Symbol.iterator;function od(e){return e===null||typeof e!="object"?null:(e=ea&&e[ea]||e["@@iterator"],typeof e=="function"?e:null)}var ra={isMounted:function(){return!1},enqueueForceUpdate:function(){},enqueueReplaceState:function(){},enqueueSetState:function(){}},oa=Object.assign,ia={};function Ft(e,t,n){this.props=e,this.context=t,this.refs=ia,this.updater=n||ra}Ft.prototype.isReactComponent={};Ft.prototype.setState=function(e,t){if(typeof e!="object"&&typeof e!="function"&&e!=null)throw Error("setState(...): takes an object of state variables to update or a function which returns an object of state variables.");this.updater.enqueueSetState(this,e,t,"setState")};Ft.prototype.forceUpdate=function(e){this.updater.enqueueForceUpdate(this,e,"forceUpdate")};function la(){}la.prototype=Ft.prototype;function Lo(e,t,n){this.props=e,this.context=t,this.refs=ia,this.updater=n||ra}var Io=Lo.prototype=new la;Io.constructor=Lo;oa(Io,Ft.prototype);Io.isPureReactComponent=!0;var ta=Array.isArray,aa=Object.prototype.hasOwnProperty,bo={current:null},sa={key:!0,ref:!0,__self:!0,__source:!0};function ua(e,t,n){var r,o={},i=null,l=null;if(t!=null)for(r in t.ref!==void 0&&(l=t.ref),t.key!==void 0&&(i=""+t.key),t)aa.call(t,r)&&!sa.hasOwnProperty(r)&&(o[r]=t[r]);var a=arguments.length-2;if(a===1)o.children=n;else if(1<a){for(var s=Array(a),d=0;d<a;d++)s[d]=arguments[d+2];o.children=s}if(e&&e.defaultProps)for(r in a=e.defaultProps,a)o[r]===void 0&&(o[r]=a[r]);return{$$typeof:pn,type:e,key:i,ref:l,props:o,_owner:bo.current}}function id(e,t){return{$$typeof:pn,type:e.type,key:t,ref:e.ref,props:e.props,_owner:e._owner}}function Do(e){return typeof e=="object"&&e!==null&&e.$$typeof===pn}function ld(e){var t={"=":"=0",":":"=2"};return"$"+e.replace(/[=:]/g,function(n){return t[n]})}var na=/\/+/g;function Mo(e,t){return typeof e=="object"&&e!==null&&e.key!=null?ld(""+e.key):t.toString(36)}function lr(e,t,n,r,o){var i=typeof e;(i==="undefined"||i==="boolean")&&(e=null);var l=!1;if(e===null)l=!0;else switch(i){case"string":case"number":l=!0;break;case"object":switch(e.$$typeof){case pn:case qc:l=!0}}if(l)return l=e,o=o(l),e=r===""?"."+Mo(l,0):r,ta(o)?(n="",e!=null&&(n=e.replace(na,"$&/")+"/"),lr(o,t,n,"",function(d){return d})):o!=null&&(Do(o)&&(o=id(o,n+(!o.key||l&&l.key===o.key?"":(""+o.key).replace(na,"$&/")+"/")+e)),t.push(o)),1;if(l=0,r=r===""?".":r+":",ta(e))for(var a=0;a<e.length;a++){i=e[a];var s=r+Mo(i,a);l+=lr(i,t,n,s,o)}else if(s=od(e),typeof s=="function")for(e=s.call(e),a=0;!(i=e.next()).done;)i=i.value,s=r+Mo(i,a++),l+=lr(i,t,n,s,o);else if(i==="object")throw t=String(e),Error("Objects are not valid as a React child (found: "+(t==="[object Object]"?"object with keys {"+Object.keys(e).join(", ")+"}":t)+"). If you meant to render a collection of children, use an array instead.");return l}function ir(e,t,n){if(e==null)return e;var r=[],o=0;return lr(e,r,"","",function(i){return t.call(n,i,o++)}),r}function ad(e){if(e._status===-1){var t=e._result;t=t(),t.then(function(n){(e._status===0||e._status===-1)&&(e._status=1,e._result=n)},function(n){(e._status===0||e._status===-1)&&(e._status=2,e._result=n)}),e._status===-1&&(e._status=0,e._result=t)}if(e._status===1)return e._result.default;throw e._result}var te={current:null},ar={transition:null},sd={ReactCurrentDispatcher:te,ReactCurrentBatchConfig:ar,ReactCurrentOwner:bo};function ca(){throw Error("act(...) is not supported in production builds of React.")}C.Children={map:ir,forEach:function(e,t,n){ir(e,function(){t.apply(this,arguments)},n)},count:function(e){var t=0;return ir(e,function(){t++}),t},toArray:function(e){return ir(e,function(t){return t})||[]},only:function(e){if(!Do(e))throw Error("React.Children.only expected to receive a single React element child.");return e}};C.Component=Ft;C.Fragment=Zc;C.Profiler=Yc;C.PureComponent=Lo;C.StrictMode=Xc;C.Suspense=td;C.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED=sd;C.act=ca;C.cloneElement=function(e,t,n){if(e==null)throw Error("React.cloneElement(...): The argument must be a React element, but you passed "+e+".");var r=oa({},e.props),o=e.key,i=e.ref,l=e._owner;if(t!=null){if(t.ref!==void 0&&(i=t.ref,l=bo.current),t.key!==void 0&&(o=""+t.key),e.type&&e.type.defaultProps)var a=e.type.defaultProps;for(s in t)aa.call(t,s)&&!sa.hasOwnProperty(s)&&(r[s]=t[s]===void 0&&a!==void 0?a[s]:t[s])}var s=arguments.length-2;if(s===1)r.children=n;else if(1<s){a=Array(s);for(var d=0;d<s;d++)a[d]=arguments[d+2];r.children=a}return{$$typeof:pn,type:e.type,key:o,ref:i,props:r,_owner:l}};C.createContext=function(e){return e={$$typeof:Jc,_currentValue:e,_currentValue2:e,_threadCount:0,Provider:null,Consumer:null,_defaultValue:null,_globalName:null},e.Provider={$$typeof:Kc,_context:e},e.Consumer=e};C.createElement=ua;C.createFactory=function(e){var t=ua.bind(null,e);return t.type=e,t};C.createRef=function(){return{current:null}};C.forwardRef=function(e){return{$$typeof:ed,render:e}};C.isValidElement=Do;C.lazy=function(e){return{$$typeof:rd,_payload:{_status:-1,_result:e},_init:ad}};C.memo=function(e,t){return{$$typeof:nd,type:e,compare:t===void 0?null:t}};C.startTransition=function(e){var t=ar.transition;ar.transition={};try{e()}finally{ar.transition=t}};C.unstable_act=ca;C.useCallback=function(e,t){return te.current.useCallback(e,t)};C.useContext=function(e){return te.current.useContext(e)};C.useDebugValue=function(){};C.useDeferredValue=function(e){return te.current.useDeferredValue(e)};C.useEffect=function(e,t){return te.current.useEffect(e,t)};C.useId=function(){return te.current.useId()};C.useImperativeHandle=function(e,t,n){return te.current.useImperativeHandle(e,t,n)};C.useInsertionEffect=function(e,t){return te.current.useInsertionEffect(e,t)};C.useLayoutEffect=function(e,t){return te.current.useLayoutEffect(e,t)};C.useMemo=function(e,t){return te.current.useMemo(e,t)};C.useReducer=function(e,t,n){return te.current.useReducer(e,t,n)};C.useRef=function(e){return te.current.useRef(e)};C.useState=function(e){return te.current.useState(e)};C.useSyncExternalStore=function(e,t,n){return te.current.useSyncExternalStore(e,t,n)};C.useTransition=function(){return te.current.useTransition()};C.version="18.3.1"});var sr=Ue((Rf,fa)=>{"use strict";fa.exports=da()});var _a=Ue(R=>{"use strict";function Oo(e,t){var n=e.length;e.push(t);e:for(;0<n;){var r=n-1>>>1,o=e[r];if(0<ur(o,t))e[r]=t,e[n]=o,n=r;else break e}}function Ee(e){return e.length===0?null:e[0]}function dr(e){if(e.length===0)return null;var t=e[0],n=e.pop();if(n!==t){e[0]=n;e:for(var r=0,o=e.length,i=o>>>1;r<i;){var l=2*(r+1)-1,a=e[l],s=l+1,d=e[s];if(0>ur(a,n))s<o&&0>ur(d,a)?(e[r]=d,e[s]=n,r=s):(e[r]=a,e[l]=n,r=l);else if(s<o&&0>ur(d,n))e[r]=d,e[s]=n,r=s;else break e}}return t}function ur(e,t){var n=e.sortIndex-t.sortIndex;return n!==0?n:e.id-t.id}typeof performance=="object"&&typeof performance.now=="function"?(pa=performance,R.unstable_now=function(){return pa.now()}):(Fo=Date,ma=Fo.now(),R.unstable_now=function(){return Fo.now()-ma});var pa,Fo,ma,Le=[],Ke=[],ud=1,ve=null,X=3,fr=!1,xt=!1,hn=!1,va=typeof setTimeout=="function"?setTimeout:null,ya=typeof clearTimeout=="function"?clearTimeout:null,ha=typeof setImmediate<"u"?setImmediate:null;typeof navigator<"u"&&navigator.scheduling!==void 0&&navigator.scheduling.isInputPending!==void 0&&navigator.scheduling.isInputPending.bind(navigator.scheduling);function jo(e){for(var t=Ee(Ke);t!==null;){if(t.callback===null)dr(Ke);else if(t.startTime<=e)dr(Ke),t.sortIndex=t.expirationTime,Oo(Le,t);else break;t=Ee(Ke)}}function Bo(e){if(hn=!1,jo(e),!xt)if(Ee(Le)!==null)xt=!0,Wo(Vo);else{var t=Ee(Ke);t!==null&&Ho(Bo,t.startTime-e)}}function Vo(e,t){xt=!1,hn&&(hn=!1,ya(gn),gn=-1),fr=!0;var n=X;try{for(jo(t),ve=Ee(Le);ve!==null&&(!(ve.expirationTime>t)||e&&!ka());){var r=ve.callback;if(typeof r=="function"){ve.callback=null,X=ve.priorityLevel;var o=r(ve.expirationTime<=t);t=R.unstable_now(),typeof o=="function"?ve.callback=o:ve===Ee(Le)&&dr(Le),jo(t)}else dr(Le);ve=Ee(Le)}if(ve!==null)var i=!0;else{var l=Ee(Ke);l!==null&&Ho(Bo,l.startTime-t),i=!1}return i}finally{ve=null,X=n,fr=!1}}var pr=!1,cr=null,gn=-1,xa=5,wa=-1;function ka(){return!(R.unstable_now()-wa<xa)}function Ao(){if(cr!==null){var e=R.unstable_now();wa=e;var t=!0;try{t=cr(!0,e)}finally{t?mn():(pr=!1,cr=null)}}else pr=!1}var mn;typeof ha=="function"?mn=function(){ha(Ao)}:typeof MessageChannel<"u"?(Uo=new MessageChannel,ga=Uo.port2,Uo.port1.onmessage=Ao,mn=function(){ga.postMessage(null)}):mn=function(){va(Ao,0)};var Uo,ga;function Wo(e){cr=e,pr||(pr=!0,mn())}function Ho(e,t){gn=va(function(){e(R.unstable_now())},t)}R.unstable_IdlePriority=5;R.unstable_ImmediatePriority=1;R.unstable_LowPriority=4;R.unstable_NormalPriority=3;R.unstable_Profiling=null;R.unstable_UserBlockingPriority=2;R.unstable_cancelCallback=function(e){e.callback=null};R.unstable_continueExecution=function(){xt||fr||(xt=!0,Wo(Vo))};R.unstable_forceFrameRate=function(e){0>e||125<e?console.error("forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported"):xa=0<e?Math.floor(1e3/e):5};R.unstable_getCurrentPriorityLevel=function(){return X};R.unstable_getFirstCallbackNode=function(){return Ee(Le)};R.unstable_next=function(e){switch(X){case 1:case 2:case 3:var t=3;break;default:t=X}var n=X;X=t;try{return e()}finally{X=n}};R.unstable_pauseExecution=function(){};R.unstable_requestPaint=function(){};R.unstable_runWithPriority=function(e,t){switch(e){case 1:case 2:case 3:case 4:case 5:break;default:e=3}var n=X;X=e;try{return t()}finally{X=n}};R.unstable_scheduleCallback=function(e,t,n){var r=R.unstable_now();switch(typeof n=="object"&&n!==null?(n=n.delay,n=typeof n=="number"&&0<n?r+n:r):n=r,e){case 1:var o=-1;break;case 2:o=250;break;case 5:o=1073741823;break;case 4:o=1e4;break;default:o=5e3}return o=n+o,e={id:ud++,callback:t,priorityLevel:e,startTime:n,expirationTime:o,sortIndex:-1},n>r?(e.sortIndex=n,Oo(Ke,e),Ee(Le)===null&&e===Ee(Ke)&&(hn?(ya(gn),gn=-1):hn=!0,Ho(Bo,n-r))):(e.sortIndex=o,Oo(Le,e),xt||fr||(xt=!0,Wo(Vo))),e};R.unstable_shouldYield=ka;R.unstable_wrapCallback=function(e){var t=X;return function(){var n=X;X=t;try{return e.apply(this,arguments)}finally{X=n}}}});var Ea=Ue((Lf,Sa)=>{"use strict";Sa.exports=_a()});var zc=Ue(he=>{"use strict";var cd=sr(),pe=Ea();function v(e){for(var t="https://reactjs.org/docs/error-decoder.html?invariant="+e,n=1;n<arguments.length;n++)t+="&args[]="+encodeURIComponent(arguments[n]);return"Minified React error #"+e+"; visit "+t+" for the full message or use the non-minified dev environment for full errors and additional helpful warnings."}var Ms=new Set,Un={};function Lt(e,t){rn(e,t),rn(e+"Capture",t)}function rn(e,t){for(Un[e]=t,e=0;e<t.length;e++)Ms.add(t[e])}var He=!(typeof window>"u"||typeof window.document>"u"||typeof window.document.createElement>"u"),pi=Object.prototype.hasOwnProperty,dd=/^[:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD][:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\-.0-9\u00B7\u0300-\u036F\u203F-\u2040]*$/,Ta={},Ca={};function fd(e){return pi.call(Ca,e)?!0:pi.call(Ta,e)?!1:dd.test(e)?Ca[e]=!0:(Ta[e]=!0,!1)}function pd(e,t,n,r){if(n!==null&&n.type===0)return!1;switch(typeof t){case"function":case"symbol":return!0;case"boolean":return r?!1:n!==null?!n.acceptsBooleans:(e=e.toLowerCase().slice(0,5),e!=="data-"&&e!=="aria-");default:return!1}}function md(e,t,n,r){if(t===null||typeof t>"u"||pd(e,t,n,r))return!0;if(r)return!1;if(n!==null)switch(n.type){case 3:return!t;case 4:return t===!1;case 5:return isNaN(t);case 6:return isNaN(t)||1>t}return!1}function oe(e,t,n,r,o,i,l){this.acceptsBooleans=t===2||t===3||t===4,this.attributeName=r,this.attributeNamespace=o,this.mustUseProperty=n,this.propertyName=e,this.type=t,this.sanitizeURL=i,this.removeEmptyString=l}var Z={};"children dangerouslySetInnerHTML defaultValue defaultChecked innerHTML suppressContentEditableWarning suppressHydrationWarning style".split(" ").forEach(function(e){Z[e]=new oe(e,0,!1,e,null,!1,!1)});[["acceptCharset","accept-charset"],["className","class"],["htmlFor","for"],["httpEquiv","http-equiv"]].forEach(function(e){var t=e[0];Z[t]=new oe(t,1,!1,e[1],null,!1,!1)});["contentEditable","draggable","spellCheck","value"].forEach(function(e){Z[e]=new oe(e,2,!1,e.toLowerCase(),null,!1,!1)});["autoReverse","externalResourcesRequired","focusable","preserveAlpha"].forEach(function(e){Z[e]=new oe(e,2,!1,e,null,!1,!1)});"allowFullScreen async autoFocus autoPlay controls default defer disabled disablePictureInPicture disableRemotePlayback formNoValidate hidden loop noModule noValidate open playsInline readOnly required reversed scoped seamless itemScope".split(" ").forEach(function(e){Z[e]=new oe(e,3,!1,e.toLowerCase(),null,!1,!1)});["checked","multiple","muted","selected"].forEach(function(e){Z[e]=new oe(e,3,!0,e,null,!1,!1)});["capture","download"].forEach(function(e){Z[e]=new oe(e,4,!1,e,null,!1,!1)});["cols","rows","size","span"].forEach(function(e){Z[e]=new oe(e,6,!1,e,null,!1,!1)});["rowSpan","start"].forEach(function(e){Z[e]=new oe(e,5,!1,e.toLowerCase(),null,!1,!1)});var il=/[\-:]([a-z])/g;function ll(e){return e[1].toUpperCase()}"accent-height alignment-baseline arabic-form baseline-shift cap-height clip-path clip-rule color-interpolation color-interpolation-filters color-profile color-rendering dominant-baseline enable-background fill-opacity fill-rule flood-color flood-opacity font-family font-size font-size-adjust font-stretch font-style font-variant font-weight glyph-name glyph-orientation-horizontal glyph-orientation-vertical horiz-adv-x horiz-origin-x image-rendering letter-spacing lighting-color marker-end marker-mid marker-start overline-position overline-thickness paint-order panose-1 pointer-events rendering-intent shape-rendering stop-color stop-opacity strikethrough-position strikethrough-thickness stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity stroke-width text-anchor text-decoration text-rendering underline-position underline-thickness unicode-bidi unicode-range units-per-em v-alphabetic v-hanging v-ideographic v-mathematical vector-effect vert-adv-y vert-origin-x vert-origin-y word-spacing writing-mode xmlns:xlink x-height".split(" ").forEach(function(e){var t=e.replace(il,ll);Z[t]=new oe(t,1,!1,e,null,!1,!1)});"xlink:actuate xlink:arcrole xlink:role xlink:show xlink:title xlink:type".split(" ").forEach(function(e){var t=e.replace(il,ll);Z[t]=new oe(t,1,!1,e,"http://www.w3.org/1999/xlink",!1,!1)});["xml:base","xml:lang","xml:space"].forEach(function(e){var t=e.replace(il,ll);Z[t]=new oe(t,1,!1,e,"http://www.w3.org/XML/1998/namespace",!1,!1)});["tabIndex","crossOrigin"].forEach(function(e){Z[e]=new oe(e,1,!1,e.toLowerCase(),null,!1,!1)});Z.xlinkHref=new oe("xlinkHref",1,!1,"xlink:href","http://www.w3.org/1999/xlink",!0,!1);["src","href","action","formAction"].forEach(function(e){Z[e]=new oe(e,1,!1,e.toLowerCase(),null,!0,!0)});function al(e,t,n,r){var o=Z.hasOwnProperty(t)?Z[t]:null;(o!==null?o.type!==0:r||!(2<t.length)||t[0]!=="o"&&t[0]!=="O"||t[1]!=="n"&&t[1]!=="N")&&(md(t,n,o,r)&&(n=null),r||o===null?fd(t)&&(n===null?e.removeAttribute(t):e.setAttribute(t,""+n)):o.mustUseProperty?e[o.propertyName]=n===null?o.type===3?!1:"":n:(t=o.attributeName,r=o.attributeNamespace,n===null?e.removeAttribute(t):(o=o.type,n=o===3||o===4&&n===!0?"":""+n,r?e.setAttributeNS(r,t,n):e.setAttribute(t,n))))}var qe=cd.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED,mr=Symbol.for("react.element"),Ot=Symbol.for("react.portal"),jt=Symbol.for("react.fragment"),sl=Symbol.for("react.strict_mode"),mi=Symbol.for("react.profiler"),Ls=Symbol.for("react.provider"),Is=Symbol.for("react.context"),ul=Symbol.for("react.forward_ref"),hi=Symbol.for("react.suspense"),gi=Symbol.for("react.suspense_list"),cl=Symbol.for("react.memo"),et=Symbol.for("react.lazy");Symbol.for("react.scope");Symbol.for("react.debug_trace_mode");var bs=Symbol.for("react.offscreen");Symbol.for("react.legacy_hidden");Symbol.for("react.cache");Symbol.for("react.tracing_marker");var Pa=Symbol.iterator;function vn(e){return e===null||typeof e!="object"?null:(e=Pa&&e[Pa]||e["@@iterator"],typeof e=="function"?e:null)}var U=Object.assign,$o;function Tn(e){if($o===void 0)try{throw Error()}catch(n){var t=n.stack.trim().match(/\n( *(at )?)/);$o=t&&t[1]||""}return`
`+$o+e}var Qo=!1;function Go(e,t){if(!e||Qo)return"";Qo=!0;var n=Error.prepareStackTrace;Error.prepareStackTrace=void 0;try{if(t)if(t=function(){throw Error()},Object.defineProperty(t.prototype,"props",{set:function(){throw Error()}}),typeof Reflect=="object"&&Reflect.construct){try{Reflect.construct(t,[])}catch(d){var r=d}Reflect.construct(e,[],t)}else{try{t.call()}catch(d){r=d}e.call(t.prototype)}else{try{throw Error()}catch(d){r=d}e()}}catch(d){if(d&&r&&typeof d.stack=="string"){for(var o=d.stack.split(`
`),i=r.stack.split(`
`),l=o.length-1,a=i.length-1;1<=l&&0<=a&&o[l]!==i[a];)a--;for(;1<=l&&0<=a;l--,a--)if(o[l]!==i[a]){if(l!==1||a!==1)do if(l--,a--,0>a||o[l]!==i[a]){var s=`
`+o[l].replace(" at new "," at ");return e.displayName&&s.includes("<anonymous>")&&(s=s.replace("<anonymous>",e.displayName)),s}while(1<=l&&0<=a);break}}}finally{Qo=!1,Error.prepareStackTrace=n}return(e=e?e.displayName||e.name:"")?Tn(e):""}function hd(e){switch(e.tag){case 5:return Tn(e.type);case 16:return Tn("Lazy");case 13:return Tn("Suspense");case 19:return Tn("SuspenseList");case 0:case 2:case 15:return e=Go(e.type,!1),e;case 11:return e=Go(e.type.render,!1),e;case 1:return e=Go(e.type,!0),e;default:return""}}function vi(e){if(e==null)return null;if(typeof e=="function")return e.displayName||e.name||null;if(typeof e=="string")return e;switch(e){case jt:return"Fragment";case Ot:return"Portal";case mi:return"Profiler";case sl:return"StrictMode";case hi:return"Suspense";case gi:return"SuspenseList"}if(typeof e=="object")switch(e.$$typeof){case Is:return(e.displayName||"Context")+".Consumer";case Ls:return(e._context.displayName||"Context")+".Provider";case ul:var t=e.render;return e=e.displayName,e||(e=t.displayName||t.name||"",e=e!==""?"ForwardRef("+e+")":"ForwardRef"),e;case cl:return t=e.displayName||null,t!==null?t:vi(e.type)||"Memo";case et:t=e._payload,e=e._init;try{return vi(e(t))}catch{}}return null}function gd(e){var t=e.type;switch(e.tag){case 24:return"Cache";case 9:return(t.displayName||"Context")+".Consumer";case 10:return(t._context.displayName||"Context")+".Provider";case 18:return"DehydratedFragment";case 11:return e=t.render,e=e.displayName||e.name||"",t.displayName||(e!==""?"ForwardRef("+e+")":"ForwardRef");case 7:return"Fragment";case 5:return t;case 4:return"Portal";case 3:return"Root";case 6:return"Text";case 16:return vi(t);case 8:return t===sl?"StrictMode":"Mode";case 22:return"Offscreen";case 12:return"Profiler";case 21:return"Scope";case 13:return"Suspense";case 19:return"SuspenseList";case 25:return"TracingMarker";case 1:case 0:case 17:case 2:case 14:case 15:if(typeof t=="function")return t.displayName||t.name||null;if(typeof t=="string")return t}return null}function mt(e){switch(typeof e){case"boolean":case"number":case"string":case"undefined":return e;case"object":return e;default:return""}}function Ds(e){var t=e.type;return(e=e.nodeName)&&e.toLowerCase()==="input"&&(t==="checkbox"||t==="radio")}function vd(e){var t=Ds(e)?"checked":"value",n=Object.getOwnPropertyDescriptor(e.constructor.prototype,t),r=""+e[t];if(!e.hasOwnProperty(t)&&typeof n<"u"&&typeof n.get=="function"&&typeof n.set=="function"){var o=n.get,i=n.set;return Object.defineProperty(e,t,{configurable:!0,get:function(){return o.call(this)},set:function(l){r=""+l,i.call(this,l)}}),Object.defineProperty(e,t,{enumerable:n.enumerable}),{getValue:function(){return r},setValue:function(l){r=""+l},stopTracking:function(){e._valueTracker=null,delete e[t]}}}}function hr(e){e._valueTracker||(e._valueTracker=vd(e))}function Fs(e){if(!e)return!1;var t=e._valueTracker;if(!t)return!0;var n=t.getValue(),r="";return e&&(r=Ds(e)?e.checked?"true":"false":e.value),e=r,e!==n?(t.setValue(e),!0):!1}function Wr(e){if(e=e||(typeof document<"u"?document:void 0),typeof e>"u")return null;try{return e.activeElement||e.body}catch{return e.body}}function yi(e,t){var n=t.checked;return U({},t,{defaultChecked:void 0,defaultValue:void 0,value:void 0,checked:n??e._wrapperState.initialChecked})}function za(e,t){var n=t.defaultValue==null?"":t.defaultValue,r=t.checked!=null?t.checked:t.defaultChecked;n=mt(t.value!=null?t.value:n),e._wrapperState={initialChecked:r,initialValue:n,controlled:t.type==="checkbox"||t.type==="radio"?t.checked!=null:t.value!=null}}function As(e,t){t=t.checked,t!=null&&al(e,"checked",t,!1)}function xi(e,t){As(e,t);var n=mt(t.value),r=t.type;if(n!=null)r==="number"?(n===0&&e.value===""||e.value!=n)&&(e.value=""+n):e.value!==""+n&&(e.value=""+n);else if(r==="submit"||r==="reset"){e.removeAttribute("value");return}t.hasOwnProperty("value")?wi(e,t.type,n):t.hasOwnProperty("defaultValue")&&wi(e,t.type,mt(t.defaultValue)),t.checked==null&&t.defaultChecked!=null&&(e.defaultChecked=!!t.defaultChecked)}function Na(e,t,n){if(t.hasOwnProperty("value")||t.hasOwnProperty("defaultValue")){var r=t.type;if(!(r!=="submit"&&r!=="reset"||t.value!==void 0&&t.value!==null))return;t=""+e._wrapperState.initialValue,n||t===e.value||(e.value=t),e.defaultValue=t}n=e.name,n!==""&&(e.name=""),e.defaultChecked=!!e._wrapperState.initialChecked,n!==""&&(e.name=n)}function wi(e,t,n){(t!=="number"||Wr(e.ownerDocument)!==e)&&(n==null?e.defaultValue=""+e._wrapperState.initialValue:e.defaultValue!==""+n&&(e.defaultValue=""+n))}var Cn=Array.isArray;function Yt(e,t,n,r){if(e=e.options,t){t={};for(var o=0;o<n.length;o++)t["$"+n[o]]=!0;for(n=0;n<e.length;n++)o=t.hasOwnProperty("$"+e[n].value),e[n].selected!==o&&(e[n].selected=o),o&&r&&(e[n].defaultSelected=!0)}else{for(n=""+mt(n),t=null,o=0;o<e.length;o++){if(e[o].value===n){e[o].selected=!0,r&&(e[o].defaultSelected=!0);return}t!==null||e[o].disabled||(t=e[o])}t!==null&&(t.selected=!0)}}function ki(e,t){if(t.dangerouslySetInnerHTML!=null)throw Error(v(91));return U({},t,{value:void 0,defaultValue:void 0,children:""+e._wrapperState.initialValue})}function Ra(e,t){var n=t.value;if(n==null){if(n=t.children,t=t.defaultValue,n!=null){if(t!=null)throw Error(v(92));if(Cn(n)){if(1<n.length)throw Error(v(93));n=n[0]}t=n}t==null&&(t=""),n=t}e._wrapperState={initialValue:mt(n)}}function Us(e,t){var n=mt(t.value),r=mt(t.defaultValue);n!=null&&(n=""+n,n!==e.value&&(e.value=n),t.defaultValue==null&&e.defaultValue!==n&&(e.defaultValue=n)),r!=null&&(e.defaultValue=""+r)}function Ma(e){var t=e.textContent;t===e._wrapperState.initialValue&&t!==""&&t!==null&&(e.value=t)}function Os(e){switch(e){case"svg":return"http://www.w3.org/2000/svg";case"math":return"http://www.w3.org/1998/Math/MathML";default:return"http://www.w3.org/1999/xhtml"}}function _i(e,t){return e==null||e==="http://www.w3.org/1999/xhtml"?Os(t):e==="http://www.w3.org/2000/svg"&&t==="foreignObject"?"http://www.w3.org/1999/xhtml":e}var gr,js=(function(e){return typeof MSApp<"u"&&MSApp.execUnsafeLocalFunction?function(t,n,r,o){MSApp.execUnsafeLocalFunction(function(){return e(t,n,r,o)})}:e})(function(e,t){if(e.namespaceURI!=="http://www.w3.org/2000/svg"||"innerHTML"in e)e.innerHTML=t;else{for(gr=gr||document.createElement("div"),gr.innerHTML="<svg>"+t.valueOf().toString()+"</svg>",t=gr.firstChild;e.firstChild;)e.removeChild(e.firstChild);for(;t.firstChild;)e.appendChild(t.firstChild)}});function On(e,t){if(t){var n=e.firstChild;if(n&&n===e.lastChild&&n.nodeType===3){n.nodeValue=t;return}}e.textContent=t}var Nn={animationIterationCount:!0,aspectRatio:!0,borderImageOutset:!0,borderImageSlice:!0,borderImageWidth:!0,boxFlex:!0,boxFlexGroup:!0,boxOrdinalGroup:!0,columnCount:!0,columns:!0,flex:!0,flexGrow:!0,flexPositive:!0,flexShrink:!0,flexNegative:!0,flexOrder:!0,gridArea:!0,gridRow:!0,gridRowEnd:!0,gridRowSpan:!0,gridRowStart:!0,gridColumn:!0,gridColumnEnd:!0,gridColumnSpan:!0,gridColumnStart:!0,fontWeight:!0,lineClamp:!0,lineHeight:!0,opacity:!0,order:!0,orphans:!0,tabSize:!0,widows:!0,zIndex:!0,zoom:!0,fillOpacity:!0,floodOpacity:!0,stopOpacity:!0,strokeDasharray:!0,strokeDashoffset:!0,strokeMiterlimit:!0,strokeOpacity:!0,strokeWidth:!0},yd=["Webkit","ms","Moz","O"];Object.keys(Nn).forEach(function(e){yd.forEach(function(t){t=t+e.charAt(0).toUpperCase()+e.substring(1),Nn[t]=Nn[e]})});function Bs(e,t,n){return t==null||typeof t=="boolean"||t===""?"":n||typeof t!="number"||t===0||Nn.hasOwnProperty(e)&&Nn[e]?(""+t).trim():t+"px"}function Vs(e,t){e=e.style;for(var n in t)if(t.hasOwnProperty(n)){var r=n.indexOf("--")===0,o=Bs(n,t[n],r);n==="float"&&(n="cssFloat"),r?e.setProperty(n,o):e[n]=o}}var xd=U({menuitem:!0},{area:!0,base:!0,br:!0,col:!0,embed:!0,hr:!0,img:!0,input:!0,keygen:!0,link:!0,meta:!0,param:!0,source:!0,track:!0,wbr:!0});function Si(e,t){if(t){if(xd[e]&&(t.children!=null||t.dangerouslySetInnerHTML!=null))throw Error(v(137,e));if(t.dangerouslySetInnerHTML!=null){if(t.children!=null)throw Error(v(60));if(typeof t.dangerouslySetInnerHTML!="object"||!("__html"in t.dangerouslySetInnerHTML))throw Error(v(61))}if(t.style!=null&&typeof t.style!="object")throw Error(v(62))}}function Ei(e,t){if(e.indexOf("-")===-1)return typeof t.is=="string";switch(e){case"annotation-xml":case"color-profile":case"font-face":case"font-face-src":case"font-face-uri":case"font-face-format":case"font-face-name":case"missing-glyph":return!1;default:return!0}}var Ti=null;function dl(e){return e=e.target||e.srcElement||window,e.correspondingUseElement&&(e=e.correspondingUseElement),e.nodeType===3?e.parentNode:e}var Ci=null,Kt=null,Jt=null;function La(e){if(e=rr(e)){if(typeof Ci!="function")throw Error(v(280));var t=e.stateNode;t&&(t=yo(t),Ci(e.stateNode,e.type,t))}}function Ws(e){Kt?Jt?Jt.push(e):Jt=[e]:Kt=e}function Hs(){if(Kt){var e=Kt,t=Jt;if(Jt=Kt=null,La(e),t)for(e=0;e<t.length;e++)La(t[e])}}function $s(e,t){return e(t)}function Qs(){}var qo=!1;function Gs(e,t,n){if(qo)return e(t,n);qo=!0;try{return $s(e,t,n)}finally{qo=!1,(Kt!==null||Jt!==null)&&(Qs(),Hs())}}function jn(e,t){var n=e.stateNode;if(n===null)return null;var r=yo(n);if(r===null)return null;n=r[t];e:switch(t){case"onClick":case"onClickCapture":case"onDoubleClick":case"onDoubleClickCapture":case"onMouseDown":case"onMouseDownCapture":case"onMouseMove":case"onMouseMoveCapture":case"onMouseUp":case"onMouseUpCapture":case"onMouseEnter":(r=!r.disabled)||(e=e.type,r=!(e==="button"||e==="input"||e==="select"||e==="textarea")),e=!r;break e;default:e=!1}if(e)return null;if(n&&typeof n!="function")throw Error(v(231,t,typeof n));return n}var Pi=!1;if(He)try{At={},Object.defineProperty(At,"passive",{get:function(){Pi=!0}}),window.addEventListener("test",At,At),window.removeEventListener("test",At,At)}catch{Pi=!1}var At;function wd(e,t,n,r,o,i,l,a,s){var d=Array.prototype.slice.call(arguments,3);try{t.apply(n,d)}catch(p){this.onError(p)}}var Rn=!1,Hr=null,$r=!1,zi=null,kd={onError:function(e){Rn=!0,Hr=e}};function _d(e,t,n,r,o,i,l,a,s){Rn=!1,Hr=null,wd.apply(kd,arguments)}function Sd(e,t,n,r,o,i,l,a,s){if(_d.apply(this,arguments),Rn){if(Rn){var d=Hr;Rn=!1,Hr=null}else throw Error(v(198));$r||($r=!0,zi=d)}}function It(e){var t=e,n=e;if(e.alternate)for(;t.return;)t=t.return;else{e=t;do t=e,(t.flags&4098)!==0&&(n=t.return),e=t.return;while(e)}return t.tag===3?n:null}function qs(e){if(e.tag===13){var t=e.memoizedState;if(t===null&&(e=e.alternate,e!==null&&(t=e.memoizedState)),t!==null)return t.dehydrated}return null}function Ia(e){if(It(e)!==e)throw Error(v(188))}function Ed(e){var t=e.alternate;if(!t){if(t=It(e),t===null)throw Error(v(188));return t!==e?null:e}for(var n=e,r=t;;){var o=n.return;if(o===null)break;var i=o.alternate;if(i===null){if(r=o.return,r!==null){n=r;continue}break}if(o.child===i.child){for(i=o.child;i;){if(i===n)return Ia(o),e;if(i===r)return Ia(o),t;i=i.sibling}throw Error(v(188))}if(n.return!==r.return)n=o,r=i;else{for(var l=!1,a=o.child;a;){if(a===n){l=!0,n=o,r=i;break}if(a===r){l=!0,r=o,n=i;break}a=a.sibling}if(!l){for(a=i.child;a;){if(a===n){l=!0,n=i,r=o;break}if(a===r){l=!0,r=i,n=o;break}a=a.sibling}if(!l)throw Error(v(189))}}if(n.alternate!==r)throw Error(v(190))}if(n.tag!==3)throw Error(v(188));return n.stateNode.current===n?e:t}function Zs(e){return e=Ed(e),e!==null?Xs(e):null}function Xs(e){if(e.tag===5||e.tag===6)return e;for(e=e.child;e!==null;){var t=Xs(e);if(t!==null)return t;e=e.sibling}return null}var Ys=pe.unstable_scheduleCallback,ba=pe.unstable_cancelCallback,Td=pe.unstable_shouldYield,Cd=pe.unstable_requestPaint,j=pe.unstable_now,Pd=pe.unstable_getCurrentPriorityLevel,fl=pe.unstable_ImmediatePriority,Ks=pe.unstable_UserBlockingPriority,Qr=pe.unstable_NormalPriority,zd=pe.unstable_LowPriority,Js=pe.unstable_IdlePriority,mo=null,Fe=null;function Nd(e){if(Fe&&typeof Fe.onCommitFiberRoot=="function")try{Fe.onCommitFiberRoot(mo,e,void 0,(e.current.flags&128)===128)}catch{}}var Ne=Math.clz32?Math.clz32:Ld,Rd=Math.log,Md=Math.LN2;function Ld(e){return e>>>=0,e===0?32:31-(Rd(e)/Md|0)|0}var vr=64,yr=4194304;function Pn(e){switch(e&-e){case 1:return 1;case 2:return 2;case 4:return 4;case 8:return 8;case 16:return 16;case 32:return 32;case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:return e&4194240;case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:return e&130023424;case 134217728:return 134217728;case 268435456:return 268435456;case 536870912:return 536870912;case 1073741824:return 1073741824;default:return e}}function Gr(e,t){var n=e.pendingLanes;if(n===0)return 0;var r=0,o=e.suspendedLanes,i=e.pingedLanes,l=n&268435455;if(l!==0){var a=l&~o;a!==0?r=Pn(a):(i&=l,i!==0&&(r=Pn(i)))}else l=n&~o,l!==0?r=Pn(l):i!==0&&(r=Pn(i));if(r===0)return 0;if(t!==0&&t!==r&&(t&o)===0&&(o=r&-r,i=t&-t,o>=i||o===16&&(i&4194240)!==0))return t;if((r&4)!==0&&(r|=n&16),t=e.entangledLanes,t!==0)for(e=e.entanglements,t&=r;0<t;)n=31-Ne(t),o=1<<n,r|=e[n],t&=~o;return r}function Id(e,t){switch(e){case 1:case 2:case 4:return t+250;case 8:case 16:case 32:case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:return t+5e3;case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:return-1;case 134217728:case 268435456:case 536870912:case 1073741824:return-1;default:return-1}}function bd(e,t){for(var n=e.suspendedLanes,r=e.pingedLanes,o=e.expirationTimes,i=e.pendingLanes;0<i;){var l=31-Ne(i),a=1<<l,s=o[l];s===-1?((a&n)===0||(a&r)!==0)&&(o[l]=Id(a,t)):s<=t&&(e.expiredLanes|=a),i&=~a}}function Ni(e){return e=e.pendingLanes&-1073741825,e!==0?e:e&1073741824?1073741824:0}function eu(){var e=vr;return vr<<=1,(vr&4194240)===0&&(vr=64),e}function Zo(e){for(var t=[],n=0;31>n;n++)t.push(e);return t}function tr(e,t,n){e.pendingLanes|=t,t!==536870912&&(e.suspendedLanes=0,e.pingedLanes=0),e=e.eventTimes,t=31-Ne(t),e[t]=n}function Dd(e,t){var n=e.pendingLanes&~t;e.pendingLanes=t,e.suspendedLanes=0,e.pingedLanes=0,e.expiredLanes&=t,e.mutableReadLanes&=t,e.entangledLanes&=t,t=e.entanglements;var r=e.eventTimes;for(e=e.expirationTimes;0<n;){var o=31-Ne(n),i=1<<o;t[o]=0,r[o]=-1,e[o]=-1,n&=~i}}function pl(e,t){var n=e.entangledLanes|=t;for(e=e.entanglements;n;){var r=31-Ne(n),o=1<<r;o&t|e[r]&t&&(e[r]|=t),n&=~o}}var N=0;function tu(e){return e&=-e,1<e?4<e?(e&268435455)!==0?16:536870912:4:1}var nu,ml,ru,ou,iu,Ri=!1,xr=[],lt=null,at=null,st=null,Bn=new Map,Vn=new Map,nt=[],Fd="mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset submit".split(" ");function Da(e,t){switch(e){case"focusin":case"focusout":lt=null;break;case"dragenter":case"dragleave":at=null;break;case"mouseover":case"mouseout":st=null;break;case"pointerover":case"pointerout":Bn.delete(t.pointerId);break;case"gotpointercapture":case"lostpointercapture":Vn.delete(t.pointerId)}}function yn(e,t,n,r,o,i){return e===null||e.nativeEvent!==i?(e={blockedOn:t,domEventName:n,eventSystemFlags:r,nativeEvent:i,targetContainers:[o]},t!==null&&(t=rr(t),t!==null&&ml(t)),e):(e.eventSystemFlags|=r,t=e.targetContainers,o!==null&&t.indexOf(o)===-1&&t.push(o),e)}function Ad(e,t,n,r,o){switch(t){case"focusin":return lt=yn(lt,e,t,n,r,o),!0;case"dragenter":return at=yn(at,e,t,n,r,o),!0;case"mouseover":return st=yn(st,e,t,n,r,o),!0;case"pointerover":var i=o.pointerId;return Bn.set(i,yn(Bn.get(i)||null,e,t,n,r,o)),!0;case"gotpointercapture":return i=o.pointerId,Vn.set(i,yn(Vn.get(i)||null,e,t,n,r,o)),!0}return!1}function lu(e){var t=_t(e.target);if(t!==null){var n=It(t);if(n!==null){if(t=n.tag,t===13){if(t=qs(n),t!==null){e.blockedOn=t,iu(e.priority,function(){ru(n)});return}}else if(t===3&&n.stateNode.current.memoizedState.isDehydrated){e.blockedOn=n.tag===3?n.stateNode.containerInfo:null;return}}}e.blockedOn=null}function Ir(e){if(e.blockedOn!==null)return!1;for(var t=e.targetContainers;0<t.length;){var n=Mi(e.domEventName,e.eventSystemFlags,t[0],e.nativeEvent);if(n===null){n=e.nativeEvent;var r=new n.constructor(n.type,n);Ti=r,n.target.dispatchEvent(r),Ti=null}else return t=rr(n),t!==null&&ml(t),e.blockedOn=n,!1;t.shift()}return!0}function Fa(e,t,n){Ir(e)&&n.delete(t)}function Ud(){Ri=!1,lt!==null&&Ir(lt)&&(lt=null),at!==null&&Ir(at)&&(at=null),st!==null&&Ir(st)&&(st=null),Bn.forEach(Fa),Vn.forEach(Fa)}function xn(e,t){e.blockedOn===t&&(e.blockedOn=null,Ri||(Ri=!0,pe.unstable_scheduleCallback(pe.unstable_NormalPriority,Ud)))}function Wn(e){function t(o){return xn(o,e)}if(0<xr.length){xn(xr[0],e);for(var n=1;n<xr.length;n++){var r=xr[n];r.blockedOn===e&&(r.blockedOn=null)}}for(lt!==null&&xn(lt,e),at!==null&&xn(at,e),st!==null&&xn(st,e),Bn.forEach(t),Vn.forEach(t),n=0;n<nt.length;n++)r=nt[n],r.blockedOn===e&&(r.blockedOn=null);for(;0<nt.length&&(n=nt[0],n.blockedOn===null);)lu(n),n.blockedOn===null&&nt.shift()}var en=qe.ReactCurrentBatchConfig,qr=!0;function Od(e,t,n,r){var o=N,i=en.transition;en.transition=null;try{N=1,hl(e,t,n,r)}finally{N=o,en.transition=i}}function jd(e,t,n,r){var o=N,i=en.transition;en.transition=null;try{N=4,hl(e,t,n,r)}finally{N=o,en.transition=i}}function hl(e,t,n,r){if(qr){var o=Mi(e,t,n,r);if(o===null)ni(e,t,r,Zr,n),Da(e,r);else if(Ad(o,e,t,n,r))r.stopPropagation();else if(Da(e,r),t&4&&-1<Fd.indexOf(e)){for(;o!==null;){var i=rr(o);if(i!==null&&nu(i),i=Mi(e,t,n,r),i===null&&ni(e,t,r,Zr,n),i===o)break;o=i}o!==null&&r.stopPropagation()}else ni(e,t,r,null,n)}}var Zr=null;function Mi(e,t,n,r){if(Zr=null,e=dl(r),e=_t(e),e!==null)if(t=It(e),t===null)e=null;else if(n=t.tag,n===13){if(e=qs(t),e!==null)return e;e=null}else if(n===3){if(t.stateNode.current.memoizedState.isDehydrated)return t.tag===3?t.stateNode.containerInfo:null;e=null}else t!==e&&(e=null);return Zr=e,null}function au(e){switch(e){case"cancel":case"click":case"close":case"contextmenu":case"copy":case"cut":case"auxclick":case"dblclick":case"dragend":case"dragstart":case"drop":case"focusin":case"focusout":case"input":case"invalid":case"keydown":case"keypress":case"keyup":case"mousedown":case"mouseup":case"paste":case"pause":case"play":case"pointercancel":case"pointerdown":case"pointerup":case"ratechange":case"reset":case"resize":case"seeked":case"submit":case"touchcancel":case"touchend":case"touchstart":case"volumechange":case"change":case"selectionchange":case"textInput":case"compositionstart":case"compositionend":case"compositionupdate":case"beforeblur":case"afterblur":case"beforeinput":case"blur":case"fullscreenchange":case"focus":case"hashchange":case"popstate":case"select":case"selectstart":return 1;case"drag":case"dragenter":case"dragexit":case"dragleave":case"dragover":case"mousemove":case"mouseout":case"mouseover":case"pointermove":case"pointerout":case"pointerover":case"scroll":case"toggle":case"touchmove":case"wheel":case"mouseenter":case"mouseleave":case"pointerenter":case"pointerleave":return 4;case"message":switch(Pd()){case fl:return 1;case Ks:return 4;case Qr:case zd:return 16;case Js:return 536870912;default:return 16}default:return 16}}var ot=null,gl=null,br=null;function su(){if(br)return br;var e,t=gl,n=t.length,r,o="value"in ot?ot.value:ot.textContent,i=o.length;for(e=0;e<n&&t[e]===o[e];e++);var l=n-e;for(r=1;r<=l&&t[n-r]===o[i-r];r++);return br=o.slice(e,1<r?1-r:void 0)}function Dr(e){var t=e.keyCode;return"charCode"in e?(e=e.charCode,e===0&&t===13&&(e=13)):e=t,e===10&&(e=13),32<=e||e===13?e:0}function wr(){return!0}function Aa(){return!1}function me(e){function t(n,r,o,i,l){this._reactName=n,this._targetInst=o,this.type=r,this.nativeEvent=i,this.target=l,this.currentTarget=null;for(var a in e)e.hasOwnProperty(a)&&(n=e[a],this[a]=n?n(i):i[a]);return this.isDefaultPrevented=(i.defaultPrevented!=null?i.defaultPrevented:i.returnValue===!1)?wr:Aa,this.isPropagationStopped=Aa,this}return U(t.prototype,{preventDefault:function(){this.defaultPrevented=!0;var n=this.nativeEvent;n&&(n.preventDefault?n.preventDefault():typeof n.returnValue!="unknown"&&(n.returnValue=!1),this.isDefaultPrevented=wr)},stopPropagation:function(){var n=this.nativeEvent;n&&(n.stopPropagation?n.stopPropagation():typeof n.cancelBubble!="unknown"&&(n.cancelBubble=!0),this.isPropagationStopped=wr)},persist:function(){},isPersistent:wr}),t}var dn={eventPhase:0,bubbles:0,cancelable:0,timeStamp:function(e){return e.timeStamp||Date.now()},defaultPrevented:0,isTrusted:0},vl=me(dn),nr=U({},dn,{view:0,detail:0}),Bd=me(nr),Xo,Yo,wn,ho=U({},nr,{screenX:0,screenY:0,clientX:0,clientY:0,pageX:0,pageY:0,ctrlKey:0,shiftKey:0,altKey:0,metaKey:0,getModifierState:yl,button:0,buttons:0,relatedTarget:function(e){return e.relatedTarget===void 0?e.fromElement===e.srcElement?e.toElement:e.fromElement:e.relatedTarget},movementX:function(e){return"movementX"in e?e.movementX:(e!==wn&&(wn&&e.type==="mousemove"?(Xo=e.screenX-wn.screenX,Yo=e.screenY-wn.screenY):Yo=Xo=0,wn=e),Xo)},movementY:function(e){return"movementY"in e?e.movementY:Yo}}),Ua=me(ho),Vd=U({},ho,{dataTransfer:0}),Wd=me(Vd),Hd=U({},nr,{relatedTarget:0}),Ko=me(Hd),$d=U({},dn,{animationName:0,elapsedTime:0,pseudoElement:0}),Qd=me($d),Gd=U({},dn,{clipboardData:function(e){return"clipboardData"in e?e.clipboardData:window.clipboardData}}),qd=me(Gd),Zd=U({},dn,{data:0}),Oa=me(Zd),Xd={Esc:"Escape",Spacebar:" ",Left:"ArrowLeft",Up:"ArrowUp",Right:"ArrowRight",Down:"ArrowDown",Del:"Delete",Win:"OS",Menu:"ContextMenu",Apps:"ContextMenu",Scroll:"ScrollLock",MozPrintableKey:"Unidentified"},Yd={8:"Backspace",9:"Tab",12:"Clear",13:"Enter",16:"Shift",17:"Control",18:"Alt",19:"Pause",20:"CapsLock",27:"Escape",32:" ",33:"PageUp",34:"PageDown",35:"End",36:"Home",37:"ArrowLeft",38:"ArrowUp",39:"ArrowRight",40:"ArrowDown",45:"Insert",46:"Delete",112:"F1",113:"F2",114:"F3",115:"F4",116:"F5",117:"F6",118:"F7",119:"F8",120:"F9",121:"F10",122:"F11",123:"F12",144:"NumLock",145:"ScrollLock",224:"Meta"},Kd={Alt:"altKey",Control:"ctrlKey",Meta:"metaKey",Shift:"shiftKey"};function Jd(e){var t=this.nativeEvent;return t.getModifierState?t.getModifierState(e):(e=Kd[e])?!!t[e]:!1}function yl(){return Jd}var e0=U({},nr,{key:function(e){if(e.key){var t=Xd[e.key]||e.key;if(t!=="Unidentified")return t}return e.type==="keypress"?(e=Dr(e),e===13?"Enter":String.fromCharCode(e)):e.type==="keydown"||e.type==="keyup"?Yd[e.keyCode]||"Unidentified":""},code:0,location:0,ctrlKey:0,shiftKey:0,altKey:0,metaKey:0,repeat:0,locale:0,getModifierState:yl,charCode:function(e){return e.type==="keypress"?Dr(e):0},keyCode:function(e){return e.type==="keydown"||e.type==="keyup"?e.keyCode:0},which:function(e){return e.type==="keypress"?Dr(e):e.type==="keydown"||e.type==="keyup"?e.keyCode:0}}),t0=me(e0),n0=U({},ho,{pointerId:0,width:0,height:0,pressure:0,tangentialPressure:0,tiltX:0,tiltY:0,twist:0,pointerType:0,isPrimary:0}),ja=me(n0),r0=U({},nr,{touches:0,targetTouches:0,changedTouches:0,altKey:0,metaKey:0,ctrlKey:0,shiftKey:0,getModifierState:yl}),o0=me(r0),i0=U({},dn,{propertyName:0,elapsedTime:0,pseudoElement:0}),l0=me(i0),a0=U({},ho,{deltaX:function(e){return"deltaX"in e?e.deltaX:"wheelDeltaX"in e?-e.wheelDeltaX:0},deltaY:function(e){return"deltaY"in e?e.deltaY:"wheelDeltaY"in e?-e.wheelDeltaY:"wheelDelta"in e?-e.wheelDelta:0},deltaZ:0,deltaMode:0}),s0=me(a0),u0=[9,13,27,32],xl=He&&"CompositionEvent"in window,Mn=null;He&&"documentMode"in document&&(Mn=document.documentMode);var c0=He&&"TextEvent"in window&&!Mn,uu=He&&(!xl||Mn&&8<Mn&&11>=Mn),Ba=" ",Va=!1;function cu(e,t){switch(e){case"keyup":return u0.indexOf(t.keyCode)!==-1;case"keydown":return t.keyCode!==229;case"keypress":case"mousedown":case"focusout":return!0;default:return!1}}function du(e){return e=e.detail,typeof e=="object"&&"data"in e?e.data:null}var Bt=!1;function d0(e,t){switch(e){case"compositionend":return du(t);case"keypress":return t.which!==32?null:(Va=!0,Ba);case"textInput":return e=t.data,e===Ba&&Va?null:e;default:return null}}function f0(e,t){if(Bt)return e==="compositionend"||!xl&&cu(e,t)?(e=su(),br=gl=ot=null,Bt=!1,e):null;switch(e){case"paste":return null;case"keypress":if(!(t.ctrlKey||t.altKey||t.metaKey)||t.ctrlKey&&t.altKey){if(t.char&&1<t.char.length)return t.char;if(t.which)return String.fromCharCode(t.which)}return null;case"compositionend":return uu&&t.locale!=="ko"?null:t.data;default:return null}}var p0={color:!0,date:!0,datetime:!0,"datetime-local":!0,email:!0,month:!0,number:!0,password:!0,range:!0,search:!0,tel:!0,text:!0,time:!0,url:!0,week:!0};function Wa(e){var t=e&&e.nodeName&&e.nodeName.toLowerCase();return t==="input"?!!p0[e.type]:t==="textarea"}function fu(e,t,n,r){Ws(r),t=Xr(t,"onChange"),0<t.length&&(n=new vl("onChange","change",null,n,r),e.push({event:n,listeners:t}))}var Ln=null,Hn=null;function m0(e){Su(e,0)}function go(e){var t=Ht(e);if(Fs(t))return e}function h0(e,t){if(e==="change")return t}var pu=!1;He&&(He?(_r="oninput"in document,_r||(Jo=document.createElement("div"),Jo.setAttribute("oninput","return;"),_r=typeof Jo.oninput=="function"),kr=_r):kr=!1,pu=kr&&(!document.documentMode||9<document.documentMode));var kr,_r,Jo;function Ha(){Ln&&(Ln.detachEvent("onpropertychange",mu),Hn=Ln=null)}function mu(e){if(e.propertyName==="value"&&go(Hn)){var t=[];fu(t,Hn,e,dl(e)),Gs(m0,t)}}function g0(e,t,n){e==="focusin"?(Ha(),Ln=t,Hn=n,Ln.attachEvent("onpropertychange",mu)):e==="focusout"&&Ha()}function v0(e){if(e==="selectionchange"||e==="keyup"||e==="keydown")return go(Hn)}function y0(e,t){if(e==="click")return go(t)}function x0(e,t){if(e==="input"||e==="change")return go(t)}function w0(e,t){return e===t&&(e!==0||1/e===1/t)||e!==e&&t!==t}var Me=typeof Object.is=="function"?Object.is:w0;function $n(e,t){if(Me(e,t))return!0;if(typeof e!="object"||e===null||typeof t!="object"||t===null)return!1;var n=Object.keys(e),r=Object.keys(t);if(n.length!==r.length)return!1;for(r=0;r<n.length;r++){var o=n[r];if(!pi.call(t,o)||!Me(e[o],t[o]))return!1}return!0}function $a(e){for(;e&&e.firstChild;)e=e.firstChild;return e}function Qa(e,t){var n=$a(e);e=0;for(var r;n;){if(n.nodeType===3){if(r=e+n.textContent.length,e<=t&&r>=t)return{node:n,offset:t-e};e=r}e:{for(;n;){if(n.nextSibling){n=n.nextSibling;break e}n=n.parentNode}n=void 0}n=$a(n)}}function hu(e,t){return e&&t?e===t?!0:e&&e.nodeType===3?!1:t&&t.nodeType===3?hu(e,t.parentNode):"contains"in e?e.contains(t):e.compareDocumentPosition?!!(e.compareDocumentPosition(t)&16):!1:!1}function gu(){for(var e=window,t=Wr();t instanceof e.HTMLIFrameElement;){try{var n=typeof t.contentWindow.location.href=="string"}catch{n=!1}if(n)e=t.contentWindow;else break;t=Wr(e.document)}return t}function wl(e){var t=e&&e.nodeName&&e.nodeName.toLowerCase();return t&&(t==="input"&&(e.type==="text"||e.type==="search"||e.type==="tel"||e.type==="url"||e.type==="password")||t==="textarea"||e.contentEditable==="true")}function k0(e){var t=gu(),n=e.focusedElem,r=e.selectionRange;if(t!==n&&n&&n.ownerDocument&&hu(n.ownerDocument.documentElement,n)){if(r!==null&&wl(n)){if(t=r.start,e=r.end,e===void 0&&(e=t),"selectionStart"in n)n.selectionStart=t,n.selectionEnd=Math.min(e,n.value.length);else if(e=(t=n.ownerDocument||document)&&t.defaultView||window,e.getSelection){e=e.getSelection();var o=n.textContent.length,i=Math.min(r.start,o);r=r.end===void 0?i:Math.min(r.end,o),!e.extend&&i>r&&(o=r,r=i,i=o),o=Qa(n,i);var l=Qa(n,r);o&&l&&(e.rangeCount!==1||e.anchorNode!==o.node||e.anchorOffset!==o.offset||e.focusNode!==l.node||e.focusOffset!==l.offset)&&(t=t.createRange(),t.setStart(o.node,o.offset),e.removeAllRanges(),i>r?(e.addRange(t),e.extend(l.node,l.offset)):(t.setEnd(l.node,l.offset),e.addRange(t)))}}for(t=[],e=n;e=e.parentNode;)e.nodeType===1&&t.push({element:e,left:e.scrollLeft,top:e.scrollTop});for(typeof n.focus=="function"&&n.focus(),n=0;n<t.length;n++)e=t[n],e.element.scrollLeft=e.left,e.element.scrollTop=e.top}}var _0=He&&"documentMode"in document&&11>=document.documentMode,Vt=null,Li=null,In=null,Ii=!1;function Ga(e,t,n){var r=n.window===n?n.document:n.nodeType===9?n:n.ownerDocument;Ii||Vt==null||Vt!==Wr(r)||(r=Vt,"selectionStart"in r&&wl(r)?r={start:r.selectionStart,end:r.selectionEnd}:(r=(r.ownerDocument&&r.ownerDocument.defaultView||window).getSelection(),r={anchorNode:r.anchorNode,anchorOffset:r.anchorOffset,focusNode:r.focusNode,focusOffset:r.focusOffset}),In&&$n(In,r)||(In=r,r=Xr(Li,"onSelect"),0<r.length&&(t=new vl("onSelect","select",null,t,n),e.push({event:t,listeners:r}),t.target=Vt)))}function Sr(e,t){var n={};return n[e.toLowerCase()]=t.toLowerCase(),n["Webkit"+e]="webkit"+t,n["Moz"+e]="moz"+t,n}var Wt={animationend:Sr("Animation","AnimationEnd"),animationiteration:Sr("Animation","AnimationIteration"),animationstart:Sr("Animation","AnimationStart"),transitionend:Sr("Transition","TransitionEnd")},ei={},vu={};He&&(vu=document.createElement("div").style,"AnimationEvent"in window||(delete Wt.animationend.animation,delete Wt.animationiteration.animation,delete Wt.animationstart.animation),"TransitionEvent"in window||delete Wt.transitionend.transition);function vo(e){if(ei[e])return ei[e];if(!Wt[e])return e;var t=Wt[e],n;for(n in t)if(t.hasOwnProperty(n)&&n in vu)return ei[e]=t[n];return e}var yu=vo("animationend"),xu=vo("animationiteration"),wu=vo("animationstart"),ku=vo("transitionend"),_u=new Map,qa="abort auxClick cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(" ");function gt(e,t){_u.set(e,t),Lt(t,[e])}for(Er=0;Er<qa.length;Er++)Tr=qa[Er],Za=Tr.toLowerCase(),Xa=Tr[0].toUpperCase()+Tr.slice(1),gt(Za,"on"+Xa);var Tr,Za,Xa,Er;gt(yu,"onAnimationEnd");gt(xu,"onAnimationIteration");gt(wu,"onAnimationStart");gt("dblclick","onDoubleClick");gt("focusin","onFocus");gt("focusout","onBlur");gt(ku,"onTransitionEnd");rn("onMouseEnter",["mouseout","mouseover"]);rn("onMouseLeave",["mouseout","mouseover"]);rn("onPointerEnter",["pointerout","pointerover"]);rn("onPointerLeave",["pointerout","pointerover"]);Lt("onChange","change click focusin focusout input keydown keyup selectionchange".split(" "));Lt("onSelect","focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(" "));Lt("onBeforeInput",["compositionend","keypress","textInput","paste"]);Lt("onCompositionEnd","compositionend focusout keydown keypress keyup mousedown".split(" "));Lt("onCompositionStart","compositionstart focusout keydown keypress keyup mousedown".split(" "));Lt("onCompositionUpdate","compositionupdate focusout keydown keypress keyup mousedown".split(" "));var zn="abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(" "),S0=new Set("cancel close invalid load scroll toggle".split(" ").concat(zn));function Ya(e,t,n){var r=e.type||"unknown-event";e.currentTarget=n,Sd(r,t,void 0,e),e.currentTarget=null}function Su(e,t){t=(t&4)!==0;for(var n=0;n<e.length;n++){var r=e[n],o=r.event;r=r.listeners;e:{var i=void 0;if(t)for(var l=r.length-1;0<=l;l--){var a=r[l],s=a.instance,d=a.currentTarget;if(a=a.listener,s!==i&&o.isPropagationStopped())break e;Ya(o,a,d),i=s}else for(l=0;l<r.length;l++){if(a=r[l],s=a.instance,d=a.currentTarget,a=a.listener,s!==i&&o.isPropagationStopped())break e;Ya(o,a,d),i=s}}}if($r)throw e=zi,$r=!1,zi=null,e}function L(e,t){var n=t[Ui];n===void 0&&(n=t[Ui]=new Set);var r=e+"__bubble";n.has(r)||(Eu(t,e,2,!1),n.add(r))}function ti(e,t,n){var r=0;t&&(r|=4),Eu(n,e,r,t)}var Cr="_reactListening"+Math.random().toString(36).slice(2);function Qn(e){if(!e[Cr]){e[Cr]=!0,Ms.forEach(function(n){n!=="selectionchange"&&(S0.has(n)||ti(n,!1,e),ti(n,!0,e))});var t=e.nodeType===9?e:e.ownerDocument;t===null||t[Cr]||(t[Cr]=!0,ti("selectionchange",!1,t))}}function Eu(e,t,n,r){switch(au(t)){case 1:var o=Od;break;case 4:o=jd;break;default:o=hl}n=o.bind(null,t,n,e),o=void 0,!Pi||t!=="touchstart"&&t!=="touchmove"&&t!=="wheel"||(o=!0),r?o!==void 0?e.addEventListener(t,n,{capture:!0,passive:o}):e.addEventListener(t,n,!0):o!==void 0?e.addEventListener(t,n,{passive:o}):e.addEventListener(t,n,!1)}function ni(e,t,n,r,o){var i=r;if((t&1)===0&&(t&2)===0&&r!==null)e:for(;;){if(r===null)return;var l=r.tag;if(l===3||l===4){var a=r.stateNode.containerInfo;if(a===o||a.nodeType===8&&a.parentNode===o)break;if(l===4)for(l=r.return;l!==null;){var s=l.tag;if((s===3||s===4)&&(s=l.stateNode.containerInfo,s===o||s.nodeType===8&&s.parentNode===o))return;l=l.return}for(;a!==null;){if(l=_t(a),l===null)return;if(s=l.tag,s===5||s===6){r=i=l;continue e}a=a.parentNode}}r=r.return}Gs(function(){var d=i,p=dl(n),h=[];e:{var m=_u.get(e);if(m!==void 0){var y=vl,w=e;switch(e){case"keypress":if(Dr(n)===0)break e;case"keydown":case"keyup":y=t0;break;case"focusin":w="focus",y=Ko;break;case"focusout":w="blur",y=Ko;break;case"beforeblur":case"afterblur":y=Ko;break;case"click":if(n.button===2)break e;case"auxclick":case"dblclick":case"mousedown":case"mousemove":case"mouseup":case"mouseout":case"mouseover":case"contextmenu":y=Ua;break;case"drag":case"dragend":case"dragenter":case"dragexit":case"dragleave":case"dragover":case"dragstart":case"drop":y=Wd;break;case"touchcancel":case"touchend":case"touchmove":case"touchstart":y=o0;break;case yu:case xu:case wu:y=Qd;break;case ku:y=l0;break;case"scroll":y=Bd;break;case"wheel":y=s0;break;case"copy":case"cut":case"paste":y=qd;break;case"gotpointercapture":case"lostpointercapture":case"pointercancel":case"pointerdown":case"pointermove":case"pointerout":case"pointerover":case"pointerup":y=ja}var x=(t&4)!==0,b=!x&&e==="scroll",c=x?m!==null?m+"Capture":null:m;x=[];for(var u=d,f;u!==null;){f=u;var g=f.stateNode;if(f.tag===5&&g!==null&&(f=g,c!==null&&(g=jn(u,c),g!=null&&x.push(Gn(u,g,f)))),b)break;u=u.return}0<x.length&&(m=new y(m,w,null,n,p),h.push({event:m,listeners:x}))}}if((t&7)===0){e:{if(m=e==="mouseover"||e==="pointerover",y=e==="mouseout"||e==="pointerout",m&&n!==Ti&&(w=n.relatedTarget||n.fromElement)&&(_t(w)||w[$e]))break e;if((y||m)&&(m=p.window===p?p:(m=p.ownerDocument)?m.defaultView||m.parentWindow:window,y?(w=n.relatedTarget||n.toElement,y=d,w=w?_t(w):null,w!==null&&(b=It(w),w!==b||w.tag!==5&&w.tag!==6)&&(w=null)):(y=null,w=d),y!==w)){if(x=Ua,g="onMouseLeave",c="onMouseEnter",u="mouse",(e==="pointerout"||e==="pointerover")&&(x=ja,g="onPointerLeave",c="onPointerEnter",u="pointer"),b=y==null?m:Ht(y),f=w==null?m:Ht(w),m=new x(g,u+"leave",y,n,p),m.target=b,m.relatedTarget=f,g=null,_t(p)===d&&(x=new x(c,u+"enter",w,n,p),x.target=f,x.relatedTarget=b,g=x),b=g,y&&w)t:{for(x=y,c=w,u=0,f=x;f;f=Ut(f))u++;for(f=0,g=c;g;g=Ut(g))f++;for(;0<u-f;)x=Ut(x),u--;for(;0<f-u;)c=Ut(c),f--;for(;u--;){if(x===c||c!==null&&x===c.alternate)break t;x=Ut(x),c=Ut(c)}x=null}else x=null;y!==null&&Ka(h,m,y,x,!1),w!==null&&b!==null&&Ka(h,b,w,x,!0)}}e:{if(m=d?Ht(d):window,y=m.nodeName&&m.nodeName.toLowerCase(),y==="select"||y==="input"&&m.type==="file")var _=h0;else if(Wa(m))if(pu)_=x0;else{_=v0;var S=g0}else(y=m.nodeName)&&y.toLowerCase()==="input"&&(m.type==="checkbox"||m.type==="radio")&&(_=y0);if(_&&(_=_(e,d))){fu(h,_,n,p);break e}S&&S(e,m,d),e==="focusout"&&(S=m._wrapperState)&&S.controlled&&m.type==="number"&&wi(m,"number",m.value)}switch(S=d?Ht(d):window,e){case"focusin":(Wa(S)||S.contentEditable==="true")&&(Vt=S,Li=d,In=null);break;case"focusout":In=Li=Vt=null;break;case"mousedown":Ii=!0;break;case"contextmenu":case"mouseup":case"dragend":Ii=!1,Ga(h,n,p);break;case"selectionchange":if(_0)break;case"keydown":case"keyup":Ga(h,n,p)}var E;if(xl)e:{switch(e){case"compositionstart":var T="onCompositionStart";break e;case"compositionend":T="onCompositionEnd";break e;case"compositionupdate":T="onCompositionUpdate";break e}T=void 0}else Bt?cu(e,n)&&(T="onCompositionEnd"):e==="keydown"&&n.keyCode===229&&(T="onCompositionStart");T&&(uu&&n.locale!=="ko"&&(Bt||T!=="onCompositionStart"?T==="onCompositionEnd"&&Bt&&(E=su()):(ot=p,gl="value"in ot?ot.value:ot.textContent,Bt=!0)),S=Xr(d,T),0<S.length&&(T=new Oa(T,e,null,n,p),h.push({event:T,listeners:S}),E?T.data=E:(E=du(n),E!==null&&(T.data=E)))),(E=c0?d0(e,n):f0(e,n))&&(d=Xr(d,"onBeforeInput"),0<d.length&&(p=new Oa("onBeforeInput","beforeinput",null,n,p),h.push({event:p,listeners:d}),p.data=E))}Su(h,t)})}function Gn(e,t,n){return{instance:e,listener:t,currentTarget:n}}function Xr(e,t){for(var n=t+"Capture",r=[];e!==null;){var o=e,i=o.stateNode;o.tag===5&&i!==null&&(o=i,i=jn(e,n),i!=null&&r.unshift(Gn(e,i,o)),i=jn(e,t),i!=null&&r.push(Gn(e,i,o))),e=e.return}return r}function Ut(e){if(e===null)return null;do e=e.return;while(e&&e.tag!==5);return e||null}function Ka(e,t,n,r,o){for(var i=t._reactName,l=[];n!==null&&n!==r;){var a=n,s=a.alternate,d=a.stateNode;if(s!==null&&s===r)break;a.tag===5&&d!==null&&(a=d,o?(s=jn(n,i),s!=null&&l.unshift(Gn(n,s,a))):o||(s=jn(n,i),s!=null&&l.push(Gn(n,s,a)))),n=n.return}l.length!==0&&e.push({event:t,listeners:l})}var E0=/\r\n?/g,T0=/\u0000|\uFFFD/g;function Ja(e){return(typeof e=="string"?e:""+e).replace(E0,`
`).replace(T0,"")}function Pr(e,t,n){if(t=Ja(t),Ja(e)!==t&&n)throw Error(v(425))}function Yr(){}var bi=null,Di=null;function Fi(e,t){return e==="textarea"||e==="noscript"||typeof t.children=="string"||typeof t.children=="number"||typeof t.dangerouslySetInnerHTML=="object"&&t.dangerouslySetInnerHTML!==null&&t.dangerouslySetInnerHTML.__html!=null}var Ai=typeof setTimeout=="function"?setTimeout:void 0,C0=typeof clearTimeout=="function"?clearTimeout:void 0,es=typeof Promise=="function"?Promise:void 0,P0=typeof queueMicrotask=="function"?queueMicrotask:typeof es<"u"?function(e){return es.resolve(null).then(e).catch(z0)}:Ai;function z0(e){setTimeout(function(){throw e})}function ri(e,t){var n=t,r=0;do{var o=n.nextSibling;if(e.removeChild(n),o&&o.nodeType===8)if(n=o.data,n==="/$"){if(r===0){e.removeChild(o),Wn(t);return}r--}else n!=="$"&&n!=="$?"&&n!=="$!"||r++;n=o}while(n);Wn(t)}function ut(e){for(;e!=null;e=e.nextSibling){var t=e.nodeType;if(t===1||t===3)break;if(t===8){if(t=e.data,t==="$"||t==="$!"||t==="$?")break;if(t==="/$")return null}}return e}function ts(e){e=e.previousSibling;for(var t=0;e;){if(e.nodeType===8){var n=e.data;if(n==="$"||n==="$!"||n==="$?"){if(t===0)return e;t--}else n==="/$"&&t++}e=e.previousSibling}return null}var fn=Math.random().toString(36).slice(2),De="__reactFiber$"+fn,qn="__reactProps$"+fn,$e="__reactContainer$"+fn,Ui="__reactEvents$"+fn,N0="__reactListeners$"+fn,R0="__reactHandles$"+fn;function _t(e){var t=e[De];if(t)return t;for(var n=e.parentNode;n;){if(t=n[$e]||n[De]){if(n=t.alternate,t.child!==null||n!==null&&n.child!==null)for(e=ts(e);e!==null;){if(n=e[De])return n;e=ts(e)}return t}e=n,n=e.parentNode}return null}function rr(e){return e=e[De]||e[$e],!e||e.tag!==5&&e.tag!==6&&e.tag!==13&&e.tag!==3?null:e}function Ht(e){if(e.tag===5||e.tag===6)return e.stateNode;throw Error(v(33))}function yo(e){return e[qn]||null}var Oi=[],$t=-1;function vt(e){return{current:e}}function I(e){0>$t||(e.current=Oi[$t],Oi[$t]=null,$t--)}function M(e,t){$t++,Oi[$t]=e.current,e.current=t}var ht={},ee=vt(ht),ae=vt(!1),Pt=ht;function on(e,t){var n=e.type.contextTypes;if(!n)return ht;var r=e.stateNode;if(r&&r.__reactInternalMemoizedUnmaskedChildContext===t)return r.__reactInternalMemoizedMaskedChildContext;var o={},i;for(i in n)o[i]=t[i];return r&&(e=e.stateNode,e.__reactInternalMemoizedUnmaskedChildContext=t,e.__reactInternalMemoizedMaskedChildContext=o),o}function se(e){return e=e.childContextTypes,e!=null}function Kr(){I(ae),I(ee)}function ns(e,t,n){if(ee.current!==ht)throw Error(v(168));M(ee,t),M(ae,n)}function Tu(e,t,n){var r=e.stateNode;if(t=t.childContextTypes,typeof r.getChildContext!="function")return n;r=r.getChildContext();for(var o in r)if(!(o in t))throw Error(v(108,gd(e)||"Unknown",o));return U({},n,r)}function Jr(e){return e=(e=e.stateNode)&&e.__reactInternalMemoizedMergedChildContext||ht,Pt=ee.current,M(ee,e),M(ae,ae.current),!0}function rs(e,t,n){var r=e.stateNode;if(!r)throw Error(v(169));n?(e=Tu(e,t,Pt),r.__reactInternalMemoizedMergedChildContext=e,I(ae),I(ee),M(ee,e)):I(ae),M(ae,n)}var je=null,xo=!1,oi=!1;function Cu(e){je===null?je=[e]:je.push(e)}function M0(e){xo=!0,Cu(e)}function yt(){if(!oi&&je!==null){oi=!0;var e=0,t=N;try{var n=je;for(N=1;e<n.length;e++){var r=n[e];do r=r(!0);while(r!==null)}je=null,xo=!1}catch(o){throw je!==null&&(je=je.slice(e+1)),Ys(fl,yt),o}finally{N=t,oi=!1}}return null}var Qt=[],Gt=0,eo=null,to=0,ye=[],xe=0,zt=null,Be=1,Ve="";function wt(e,t){Qt[Gt++]=to,Qt[Gt++]=eo,eo=e,to=t}function Pu(e,t,n){ye[xe++]=Be,ye[xe++]=Ve,ye[xe++]=zt,zt=e;var r=Be;e=Ve;var o=32-Ne(r)-1;r&=~(1<<o),n+=1;var i=32-Ne(t)+o;if(30<i){var l=o-o%5;i=(r&(1<<l)-1).toString(32),r>>=l,o-=l,Be=1<<32-Ne(t)+o|n<<o|r,Ve=i+e}else Be=1<<i|n<<o|r,Ve=e}function kl(e){e.return!==null&&(wt(e,1),Pu(e,1,0))}function _l(e){for(;e===eo;)eo=Qt[--Gt],Qt[Gt]=null,to=Qt[--Gt],Qt[Gt]=null;for(;e===zt;)zt=ye[--xe],ye[xe]=null,Ve=ye[--xe],ye[xe]=null,Be=ye[--xe],ye[xe]=null}var fe=null,de=null,D=!1,ze=null;function zu(e,t){var n=we(5,null,null,0);n.elementType="DELETED",n.stateNode=t,n.return=e,t=e.deletions,t===null?(e.deletions=[n],e.flags|=16):t.push(n)}function os(e,t){switch(e.tag){case 5:var n=e.type;return t=t.nodeType!==1||n.toLowerCase()!==t.nodeName.toLowerCase()?null:t,t!==null?(e.stateNode=t,fe=e,de=ut(t.firstChild),!0):!1;case 6:return t=e.pendingProps===""||t.nodeType!==3?null:t,t!==null?(e.stateNode=t,fe=e,de=null,!0):!1;case 13:return t=t.nodeType!==8?null:t,t!==null?(n=zt!==null?{id:Be,overflow:Ve}:null,e.memoizedState={dehydrated:t,treeContext:n,retryLane:1073741824},n=we(18,null,null,0),n.stateNode=t,n.return=e,e.child=n,fe=e,de=null,!0):!1;default:return!1}}function ji(e){return(e.mode&1)!==0&&(e.flags&128)===0}function Bi(e){if(D){var t=de;if(t){var n=t;if(!os(e,t)){if(ji(e))throw Error(v(418));t=ut(n.nextSibling);var r=fe;t&&os(e,t)?zu(r,n):(e.flags=e.flags&-4097|2,D=!1,fe=e)}}else{if(ji(e))throw Error(v(418));e.flags=e.flags&-4097|2,D=!1,fe=e}}}function is(e){for(e=e.return;e!==null&&e.tag!==5&&e.tag!==3&&e.tag!==13;)e=e.return;fe=e}function zr(e){if(e!==fe)return!1;if(!D)return is(e),D=!0,!1;var t;if((t=e.tag!==3)&&!(t=e.tag!==5)&&(t=e.type,t=t!=="head"&&t!=="body"&&!Fi(e.type,e.memoizedProps)),t&&(t=de)){if(ji(e))throw Nu(),Error(v(418));for(;t;)zu(e,t),t=ut(t.nextSibling)}if(is(e),e.tag===13){if(e=e.memoizedState,e=e!==null?e.dehydrated:null,!e)throw Error(v(317));e:{for(e=e.nextSibling,t=0;e;){if(e.nodeType===8){var n=e.data;if(n==="/$"){if(t===0){de=ut(e.nextSibling);break e}t--}else n!=="$"&&n!=="$!"&&n!=="$?"||t++}e=e.nextSibling}de=null}}else de=fe?ut(e.stateNode.nextSibling):null;return!0}function Nu(){for(var e=de;e;)e=ut(e.nextSibling)}function ln(){de=fe=null,D=!1}function Sl(e){ze===null?ze=[e]:ze.push(e)}var L0=qe.ReactCurrentBatchConfig;function kn(e,t,n){if(e=n.ref,e!==null&&typeof e!="function"&&typeof e!="object"){if(n._owner){if(n=n._owner,n){if(n.tag!==1)throw Error(v(309));var r=n.stateNode}if(!r)throw Error(v(147,e));var o=r,i=""+e;return t!==null&&t.ref!==null&&typeof t.ref=="function"&&t.ref._stringRef===i?t.ref:(t=function(l){var a=o.refs;l===null?delete a[i]:a[i]=l},t._stringRef=i,t)}if(typeof e!="string")throw Error(v(284));if(!n._owner)throw Error(v(290,e))}return e}function Nr(e,t){throw e=Object.prototype.toString.call(t),Error(v(31,e==="[object Object]"?"object with keys {"+Object.keys(t).join(", ")+"}":e))}function ls(e){var t=e._init;return t(e._payload)}function Ru(e){function t(c,u){if(e){var f=c.deletions;f===null?(c.deletions=[u],c.flags|=16):f.push(u)}}function n(c,u){if(!e)return null;for(;u!==null;)t(c,u),u=u.sibling;return null}function r(c,u){for(c=new Map;u!==null;)u.key!==null?c.set(u.key,u):c.set(u.index,u),u=u.sibling;return c}function o(c,u){return c=pt(c,u),c.index=0,c.sibling=null,c}function i(c,u,f){return c.index=f,e?(f=c.alternate,f!==null?(f=f.index,f<u?(c.flags|=2,u):f):(c.flags|=2,u)):(c.flags|=1048576,u)}function l(c){return e&&c.alternate===null&&(c.flags|=2),c}function a(c,u,f,g){return u===null||u.tag!==6?(u=di(f,c.mode,g),u.return=c,u):(u=o(u,f),u.return=c,u)}function s(c,u,f,g){var _=f.type;return _===jt?p(c,u,f.props.children,g,f.key):u!==null&&(u.elementType===_||typeof _=="object"&&_!==null&&_.$$typeof===et&&ls(_)===u.type)?(g=o(u,f.props),g.ref=kn(c,u,f),g.return=c,g):(g=Vr(f.type,f.key,f.props,null,c.mode,g),g.ref=kn(c,u,f),g.return=c,g)}function d(c,u,f,g){return u===null||u.tag!==4||u.stateNode.containerInfo!==f.containerInfo||u.stateNode.implementation!==f.implementation?(u=fi(f,c.mode,g),u.return=c,u):(u=o(u,f.children||[]),u.return=c,u)}function p(c,u,f,g,_){return u===null||u.tag!==7?(u=Ct(f,c.mode,g,_),u.return=c,u):(u=o(u,f),u.return=c,u)}function h(c,u,f){if(typeof u=="string"&&u!==""||typeof u=="number")return u=di(""+u,c.mode,f),u.return=c,u;if(typeof u=="object"&&u!==null){switch(u.$$typeof){case mr:return f=Vr(u.type,u.key,u.props,null,c.mode,f),f.ref=kn(c,null,u),f.return=c,f;case Ot:return u=fi(u,c.mode,f),u.return=c,u;case et:var g=u._init;return h(c,g(u._payload),f)}if(Cn(u)||vn(u))return u=Ct(u,c.mode,f,null),u.return=c,u;Nr(c,u)}return null}function m(c,u,f,g){var _=u!==null?u.key:null;if(typeof f=="string"&&f!==""||typeof f=="number")return _!==null?null:a(c,u,""+f,g);if(typeof f=="object"&&f!==null){switch(f.$$typeof){case mr:return f.key===_?s(c,u,f,g):null;case Ot:return f.key===_?d(c,u,f,g):null;case et:return _=f._init,m(c,u,_(f._payload),g)}if(Cn(f)||vn(f))return _!==null?null:p(c,u,f,g,null);Nr(c,f)}return null}function y(c,u,f,g,_){if(typeof g=="string"&&g!==""||typeof g=="number")return c=c.get(f)||null,a(u,c,""+g,_);if(typeof g=="object"&&g!==null){switch(g.$$typeof){case mr:return c=c.get(g.key===null?f:g.key)||null,s(u,c,g,_);case Ot:return c=c.get(g.key===null?f:g.key)||null,d(u,c,g,_);case et:var S=g._init;return y(c,u,f,S(g._payload),_)}if(Cn(g)||vn(g))return c=c.get(f)||null,p(u,c,g,_,null);Nr(u,g)}return null}function w(c,u,f,g){for(var _=null,S=null,E=u,T=u=0,H=null;E!==null&&T<f.length;T++){E.index>T?(H=E,E=null):H=E.sibling;var z=m(c,E,f[T],g);if(z===null){E===null&&(E=H);break}e&&E&&z.alternate===null&&t(c,E),u=i(z,u,T),S===null?_=z:S.sibling=z,S=z,E=H}if(T===f.length)return n(c,E),D&&wt(c,T),_;if(E===null){for(;T<f.length;T++)E=h(c,f[T],g),E!==null&&(u=i(E,u,T),S===null?_=E:S.sibling=E,S=E);return D&&wt(c,T),_}for(E=r(c,E);T<f.length;T++)H=y(E,c,T,f[T],g),H!==null&&(e&&H.alternate!==null&&E.delete(H.key===null?T:H.key),u=i(H,u,T),S===null?_=H:S.sibling=H,S=H);return e&&E.forEach(function(Xe){return t(c,Xe)}),D&&wt(c,T),_}function x(c,u,f,g){var _=vn(f);if(typeof _!="function")throw Error(v(150));if(f=_.call(f),f==null)throw Error(v(151));for(var S=_=null,E=u,T=u=0,H=null,z=f.next();E!==null&&!z.done;T++,z=f.next()){E.index>T?(H=E,E=null):H=E.sibling;var Xe=m(c,E,z.value,g);if(Xe===null){E===null&&(E=H);break}e&&E&&Xe.alternate===null&&t(c,E),u=i(Xe,u,T),S===null?_=Xe:S.sibling=Xe,S=Xe,E=H}if(z.done)return n(c,E),D&&wt(c,T),_;if(E===null){for(;!z.done;T++,z=f.next())z=h(c,z.value,g),z!==null&&(u=i(z,u,T),S===null?_=z:S.sibling=z,S=z);return D&&wt(c,T),_}for(E=r(c,E);!z.done;T++,z=f.next())z=y(E,c,T,z.value,g),z!==null&&(e&&z.alternate!==null&&E.delete(z.key===null?T:z.key),u=i(z,u,T),S===null?_=z:S.sibling=z,S=z);return e&&E.forEach(function(Bc){return t(c,Bc)}),D&&wt(c,T),_}function b(c,u,f,g){if(typeof f=="object"&&f!==null&&f.type===jt&&f.key===null&&(f=f.props.children),typeof f=="object"&&f!==null){switch(f.$$typeof){case mr:e:{for(var _=f.key,S=u;S!==null;){if(S.key===_){if(_=f.type,_===jt){if(S.tag===7){n(c,S.sibling),u=o(S,f.props.children),u.return=c,c=u;break e}}else if(S.elementType===_||typeof _=="object"&&_!==null&&_.$$typeof===et&&ls(_)===S.type){n(c,S.sibling),u=o(S,f.props),u.ref=kn(c,S,f),u.return=c,c=u;break e}n(c,S);break}else t(c,S);S=S.sibling}f.type===jt?(u=Ct(f.props.children,c.mode,g,f.key),u.return=c,c=u):(g=Vr(f.type,f.key,f.props,null,c.mode,g),g.ref=kn(c,u,f),g.return=c,c=g)}return l(c);case Ot:e:{for(S=f.key;u!==null;){if(u.key===S)if(u.tag===4&&u.stateNode.containerInfo===f.containerInfo&&u.stateNode.implementation===f.implementation){n(c,u.sibling),u=o(u,f.children||[]),u.return=c,c=u;break e}else{n(c,u);break}else t(c,u);u=u.sibling}u=fi(f,c.mode,g),u.return=c,c=u}return l(c);case et:return S=f._init,b(c,u,S(f._payload),g)}if(Cn(f))return w(c,u,f,g);if(vn(f))return x(c,u,f,g);Nr(c,f)}return typeof f=="string"&&f!==""||typeof f=="number"?(f=""+f,u!==null&&u.tag===6?(n(c,u.sibling),u=o(u,f),u.return=c,c=u):(n(c,u),u=di(f,c.mode,g),u.return=c,c=u),l(c)):n(c,u)}return b}var an=Ru(!0),Mu=Ru(!1),no=vt(null),ro=null,qt=null,El=null;function Tl(){El=qt=ro=null}function Cl(e){var t=no.current;I(no),e._currentValue=t}function Vi(e,t,n){for(;e!==null;){var r=e.alternate;if((e.childLanes&t)!==t?(e.childLanes|=t,r!==null&&(r.childLanes|=t)):r!==null&&(r.childLanes&t)!==t&&(r.childLanes|=t),e===n)break;e=e.return}}function tn(e,t){ro=e,El=qt=null,e=e.dependencies,e!==null&&e.firstContext!==null&&((e.lanes&t)!==0&&(le=!0),e.firstContext=null)}function _e(e){var t=e._currentValue;if(El!==e)if(e={context:e,memoizedValue:t,next:null},qt===null){if(ro===null)throw Error(v(308));qt=e,ro.dependencies={lanes:0,firstContext:e}}else qt=qt.next=e;return t}var St=null;function Pl(e){St===null?St=[e]:St.push(e)}function Lu(e,t,n,r){var o=t.interleaved;return o===null?(n.next=n,Pl(t)):(n.next=o.next,o.next=n),t.interleaved=n,Qe(e,r)}function Qe(e,t){e.lanes|=t;var n=e.alternate;for(n!==null&&(n.lanes|=t),n=e,e=e.return;e!==null;)e.childLanes|=t,n=e.alternate,n!==null&&(n.childLanes|=t),n=e,e=e.return;return n.tag===3?n.stateNode:null}var tt=!1;function zl(e){e.updateQueue={baseState:e.memoizedState,firstBaseUpdate:null,lastBaseUpdate:null,shared:{pending:null,interleaved:null,lanes:0},effects:null}}function Iu(e,t){e=e.updateQueue,t.updateQueue===e&&(t.updateQueue={baseState:e.baseState,firstBaseUpdate:e.firstBaseUpdate,lastBaseUpdate:e.lastBaseUpdate,shared:e.shared,effects:e.effects})}function We(e,t){return{eventTime:e,lane:t,tag:0,payload:null,callback:null,next:null}}function ct(e,t,n){var r=e.updateQueue;if(r===null)return null;if(r=r.shared,(P&2)!==0){var o=r.pending;return o===null?t.next=t:(t.next=o.next,o.next=t),r.pending=t,Qe(e,n)}return o=r.interleaved,o===null?(t.next=t,Pl(r)):(t.next=o.next,o.next=t),r.interleaved=t,Qe(e,n)}function Fr(e,t,n){if(t=t.updateQueue,t!==null&&(t=t.shared,(n&4194240)!==0)){var r=t.lanes;r&=e.pendingLanes,n|=r,t.lanes=n,pl(e,n)}}function as(e,t){var n=e.updateQueue,r=e.alternate;if(r!==null&&(r=r.updateQueue,n===r)){var o=null,i=null;if(n=n.firstBaseUpdate,n!==null){do{var l={eventTime:n.eventTime,lane:n.lane,tag:n.tag,payload:n.payload,callback:n.callback,next:null};i===null?o=i=l:i=i.next=l,n=n.next}while(n!==null);i===null?o=i=t:i=i.next=t}else o=i=t;n={baseState:r.baseState,firstBaseUpdate:o,lastBaseUpdate:i,shared:r.shared,effects:r.effects},e.updateQueue=n;return}e=n.lastBaseUpdate,e===null?n.firstBaseUpdate=t:e.next=t,n.lastBaseUpdate=t}function oo(e,t,n,r){var o=e.updateQueue;tt=!1;var i=o.firstBaseUpdate,l=o.lastBaseUpdate,a=o.shared.pending;if(a!==null){o.shared.pending=null;var s=a,d=s.next;s.next=null,l===null?i=d:l.next=d,l=s;var p=e.alternate;p!==null&&(p=p.updateQueue,a=p.lastBaseUpdate,a!==l&&(a===null?p.firstBaseUpdate=d:a.next=d,p.lastBaseUpdate=s))}if(i!==null){var h=o.baseState;l=0,p=d=s=null,a=i;do{var m=a.lane,y=a.eventTime;if((r&m)===m){p!==null&&(p=p.next={eventTime:y,lane:0,tag:a.tag,payload:a.payload,callback:a.callback,next:null});e:{var w=e,x=a;switch(m=t,y=n,x.tag){case 1:if(w=x.payload,typeof w=="function"){h=w.call(y,h,m);break e}h=w;break e;case 3:w.flags=w.flags&-65537|128;case 0:if(w=x.payload,m=typeof w=="function"?w.call(y,h,m):w,m==null)break e;h=U({},h,m);break e;case 2:tt=!0}}a.callback!==null&&a.lane!==0&&(e.flags|=64,m=o.effects,m===null?o.effects=[a]:m.push(a))}else y={eventTime:y,lane:m,tag:a.tag,payload:a.payload,callback:a.callback,next:null},p===null?(d=p=y,s=h):p=p.next=y,l|=m;if(a=a.next,a===null){if(a=o.shared.pending,a===null)break;m=a,a=m.next,m.next=null,o.lastBaseUpdate=m,o.shared.pending=null}}while(!0);if(p===null&&(s=h),o.baseState=s,o.firstBaseUpdate=d,o.lastBaseUpdate=p,t=o.shared.interleaved,t!==null){o=t;do l|=o.lane,o=o.next;while(o!==t)}else i===null&&(o.shared.lanes=0);Rt|=l,e.lanes=l,e.memoizedState=h}}function ss(e,t,n){if(e=t.effects,t.effects=null,e!==null)for(t=0;t<e.length;t++){var r=e[t],o=r.callback;if(o!==null){if(r.callback=null,r=n,typeof o!="function")throw Error(v(191,o));o.call(r)}}}var or={},Ae=vt(or),Zn=vt(or),Xn=vt(or);function Et(e){if(e===or)throw Error(v(174));return e}function Nl(e,t){switch(M(Xn,t),M(Zn,e),M(Ae,or),e=t.nodeType,e){case 9:case 11:t=(t=t.documentElement)?t.namespaceURI:_i(null,"");break;default:e=e===8?t.parentNode:t,t=e.namespaceURI||null,e=e.tagName,t=_i(t,e)}I(Ae),M(Ae,t)}function sn(){I(Ae),I(Zn),I(Xn)}function bu(e){Et(Xn.current);var t=Et(Ae.current),n=_i(t,e.type);t!==n&&(M(Zn,e),M(Ae,n))}function Rl(e){Zn.current===e&&(I(Ae),I(Zn))}var F=vt(0);function io(e){for(var t=e;t!==null;){if(t.tag===13){var n=t.memoizedState;if(n!==null&&(n=n.dehydrated,n===null||n.data==="$?"||n.data==="$!"))return t}else if(t.tag===19&&t.memoizedProps.revealOrder!==void 0){if((t.flags&128)!==0)return t}else if(t.child!==null){t.child.return=t,t=t.child;continue}if(t===e)break;for(;t.sibling===null;){if(t.return===null||t.return===e)return null;t=t.return}t.sibling.return=t.return,t=t.sibling}return null}var ii=[];function Ml(){for(var e=0;e<ii.length;e++)ii[e]._workInProgressVersionPrimary=null;ii.length=0}var Ar=qe.ReactCurrentDispatcher,li=qe.ReactCurrentBatchConfig,Nt=0,A=null,V=null,$=null,lo=!1,bn=!1,Yn=0,I0=0;function Y(){throw Error(v(321))}function Ll(e,t){if(t===null)return!1;for(var n=0;n<t.length&&n<e.length;n++)if(!Me(e[n],t[n]))return!1;return!0}function Il(e,t,n,r,o,i){if(Nt=i,A=t,t.memoizedState=null,t.updateQueue=null,t.lanes=0,Ar.current=e===null||e.memoizedState===null?A0:U0,e=n(r,o),bn){i=0;do{if(bn=!1,Yn=0,25<=i)throw Error(v(301));i+=1,$=V=null,t.updateQueue=null,Ar.current=O0,e=n(r,o)}while(bn)}if(Ar.current=ao,t=V!==null&&V.next!==null,Nt=0,$=V=A=null,lo=!1,t)throw Error(v(300));return e}function bl(){var e=Yn!==0;return Yn=0,e}function be(){var e={memoizedState:null,baseState:null,baseQueue:null,queue:null,next:null};return $===null?A.memoizedState=$=e:$=$.next=e,$}function Se(){if(V===null){var e=A.alternate;e=e!==null?e.memoizedState:null}else e=V.next;var t=$===null?A.memoizedState:$.next;if(t!==null)$=t,V=e;else{if(e===null)throw Error(v(310));V=e,e={memoizedState:V.memoizedState,baseState:V.baseState,baseQueue:V.baseQueue,queue:V.queue,next:null},$===null?A.memoizedState=$=e:$=$.next=e}return $}function Kn(e,t){return typeof t=="function"?t(e):t}function ai(e){var t=Se(),n=t.queue;if(n===null)throw Error(v(311));n.lastRenderedReducer=e;var r=V,o=r.baseQueue,i=n.pending;if(i!==null){if(o!==null){var l=o.next;o.next=i.next,i.next=l}r.baseQueue=o=i,n.pending=null}if(o!==null){i=o.next,r=r.baseState;var a=l=null,s=null,d=i;do{var p=d.lane;if((Nt&p)===p)s!==null&&(s=s.next={lane:0,action:d.action,hasEagerState:d.hasEagerState,eagerState:d.eagerState,next:null}),r=d.hasEagerState?d.eagerState:e(r,d.action);else{var h={lane:p,action:d.action,hasEagerState:d.hasEagerState,eagerState:d.eagerState,next:null};s===null?(a=s=h,l=r):s=s.next=h,A.lanes|=p,Rt|=p}d=d.next}while(d!==null&&d!==i);s===null?l=r:s.next=a,Me(r,t.memoizedState)||(le=!0),t.memoizedState=r,t.baseState=l,t.baseQueue=s,n.lastRenderedState=r}if(e=n.interleaved,e!==null){o=e;do i=o.lane,A.lanes|=i,Rt|=i,o=o.next;while(o!==e)}else o===null&&(n.lanes=0);return[t.memoizedState,n.dispatch]}function si(e){var t=Se(),n=t.queue;if(n===null)throw Error(v(311));n.lastRenderedReducer=e;var r=n.dispatch,o=n.pending,i=t.memoizedState;if(o!==null){n.pending=null;var l=o=o.next;do i=e(i,l.action),l=l.next;while(l!==o);Me(i,t.memoizedState)||(le=!0),t.memoizedState=i,t.baseQueue===null&&(t.baseState=i),n.lastRenderedState=i}return[i,r]}function Du(){}function Fu(e,t){var n=A,r=Se(),o=t(),i=!Me(r.memoizedState,o);if(i&&(r.memoizedState=o,le=!0),r=r.queue,Dl(Ou.bind(null,n,r,e),[e]),r.getSnapshot!==t||i||$!==null&&$.memoizedState.tag&1){if(n.flags|=2048,Jn(9,Uu.bind(null,n,r,o,t),void 0,null),Q===null)throw Error(v(349));(Nt&30)!==0||Au(n,t,o)}return o}function Au(e,t,n){e.flags|=16384,e={getSnapshot:t,value:n},t=A.updateQueue,t===null?(t={lastEffect:null,stores:null},A.updateQueue=t,t.stores=[e]):(n=t.stores,n===null?t.stores=[e]:n.push(e))}function Uu(e,t,n,r){t.value=n,t.getSnapshot=r,ju(t)&&Bu(e)}function Ou(e,t,n){return n(function(){ju(t)&&Bu(e)})}function ju(e){var t=e.getSnapshot;e=e.value;try{var n=t();return!Me(e,n)}catch{return!0}}function Bu(e){var t=Qe(e,1);t!==null&&Re(t,e,1,-1)}function us(e){var t=be();return typeof e=="function"&&(e=e()),t.memoizedState=t.baseState=e,e={pending:null,interleaved:null,lanes:0,dispatch:null,lastRenderedReducer:Kn,lastRenderedState:e},t.queue=e,e=e.dispatch=F0.bind(null,A,e),[t.memoizedState,e]}function Jn(e,t,n,r){return e={tag:e,create:t,destroy:n,deps:r,next:null},t=A.updateQueue,t===null?(t={lastEffect:null,stores:null},A.updateQueue=t,t.lastEffect=e.next=e):(n=t.lastEffect,n===null?t.lastEffect=e.next=e:(r=n.next,n.next=e,e.next=r,t.lastEffect=e)),e}function Vu(){return Se().memoizedState}function Ur(e,t,n,r){var o=be();A.flags|=e,o.memoizedState=Jn(1|t,n,void 0,r===void 0?null:r)}function wo(e,t,n,r){var o=Se();r=r===void 0?null:r;var i=void 0;if(V!==null){var l=V.memoizedState;if(i=l.destroy,r!==null&&Ll(r,l.deps)){o.memoizedState=Jn(t,n,i,r);return}}A.flags|=e,o.memoizedState=Jn(1|t,n,i,r)}function cs(e,t){return Ur(8390656,8,e,t)}function Dl(e,t){return wo(2048,8,e,t)}function Wu(e,t){return wo(4,2,e,t)}function Hu(e,t){return wo(4,4,e,t)}function $u(e,t){if(typeof t=="function")return e=e(),t(e),function(){t(null)};if(t!=null)return e=e(),t.current=e,function(){t.current=null}}function Qu(e,t,n){return n=n!=null?n.concat([e]):null,wo(4,4,$u.bind(null,t,e),n)}function Fl(){}function Gu(e,t){var n=Se();t=t===void 0?null:t;var r=n.memoizedState;return r!==null&&t!==null&&Ll(t,r[1])?r[0]:(n.memoizedState=[e,t],e)}function qu(e,t){var n=Se();t=t===void 0?null:t;var r=n.memoizedState;return r!==null&&t!==null&&Ll(t,r[1])?r[0]:(e=e(),n.memoizedState=[e,t],e)}function Zu(e,t,n){return(Nt&21)===0?(e.baseState&&(e.baseState=!1,le=!0),e.memoizedState=n):(Me(n,t)||(n=eu(),A.lanes|=n,Rt|=n,e.baseState=!0),t)}function b0(e,t){var n=N;N=n!==0&&4>n?n:4,e(!0);var r=li.transition;li.transition={};try{e(!1),t()}finally{N=n,li.transition=r}}function Xu(){return Se().memoizedState}function D0(e,t,n){var r=ft(e);if(n={lane:r,action:n,hasEagerState:!1,eagerState:null,next:null},Yu(e))Ku(t,n);else if(n=Lu(e,t,n,r),n!==null){var o=re();Re(n,e,r,o),Ju(n,t,r)}}function F0(e,t,n){var r=ft(e),o={lane:r,action:n,hasEagerState:!1,eagerState:null,next:null};if(Yu(e))Ku(t,o);else{var i=e.alternate;if(e.lanes===0&&(i===null||i.lanes===0)&&(i=t.lastRenderedReducer,i!==null))try{var l=t.lastRenderedState,a=i(l,n);if(o.hasEagerState=!0,o.eagerState=a,Me(a,l)){var s=t.interleaved;s===null?(o.next=o,Pl(t)):(o.next=s.next,s.next=o),t.interleaved=o;return}}catch{}finally{}n=Lu(e,t,o,r),n!==null&&(o=re(),Re(n,e,r,o),Ju(n,t,r))}}function Yu(e){var t=e.alternate;return e===A||t!==null&&t===A}function Ku(e,t){bn=lo=!0;var n=e.pending;n===null?t.next=t:(t.next=n.next,n.next=t),e.pending=t}function Ju(e,t,n){if((n&4194240)!==0){var r=t.lanes;r&=e.pendingLanes,n|=r,t.lanes=n,pl(e,n)}}var ao={readContext:_e,useCallback:Y,useContext:Y,useEffect:Y,useImperativeHandle:Y,useInsertionEffect:Y,useLayoutEffect:Y,useMemo:Y,useReducer:Y,useRef:Y,useState:Y,useDebugValue:Y,useDeferredValue:Y,useTransition:Y,useMutableSource:Y,useSyncExternalStore:Y,useId:Y,unstable_isNewReconciler:!1},A0={readContext:_e,useCallback:function(e,t){return be().memoizedState=[e,t===void 0?null:t],e},useContext:_e,useEffect:cs,useImperativeHandle:function(e,t,n){return n=n!=null?n.concat([e]):null,Ur(4194308,4,$u.bind(null,t,e),n)},useLayoutEffect:function(e,t){return Ur(4194308,4,e,t)},useInsertionEffect:function(e,t){return Ur(4,2,e,t)},useMemo:function(e,t){var n=be();return t=t===void 0?null:t,e=e(),n.memoizedState=[e,t],e},useReducer:function(e,t,n){var r=be();return t=n!==void 0?n(t):t,r.memoizedState=r.baseState=t,e={pending:null,interleaved:null,lanes:0,dispatch:null,lastRenderedReducer:e,lastRenderedState:t},r.queue=e,e=e.dispatch=D0.bind(null,A,e),[r.memoizedState,e]},useRef:function(e){var t=be();return e={current:e},t.memoizedState=e},useState:us,useDebugValue:Fl,useDeferredValue:function(e){return be().memoizedState=e},useTransition:function(){var e=us(!1),t=e[0];return e=b0.bind(null,e[1]),be().memoizedState=e,[t,e]},useMutableSource:function(){},useSyncExternalStore:function(e,t,n){var r=A,o=be();if(D){if(n===void 0)throw Error(v(407));n=n()}else{if(n=t(),Q===null)throw Error(v(349));(Nt&30)!==0||Au(r,t,n)}o.memoizedState=n;var i={value:n,getSnapshot:t};return o.queue=i,cs(Ou.bind(null,r,i,e),[e]),r.flags|=2048,Jn(9,Uu.bind(null,r,i,n,t),void 0,null),n},useId:function(){var e=be(),t=Q.identifierPrefix;if(D){var n=Ve,r=Be;n=(r&~(1<<32-Ne(r)-1)).toString(32)+n,t=":"+t+"R"+n,n=Yn++,0<n&&(t+="H"+n.toString(32)),t+=":"}else n=I0++,t=":"+t+"r"+n.toString(32)+":";return e.memoizedState=t},unstable_isNewReconciler:!1},U0={readContext:_e,useCallback:Gu,useContext:_e,useEffect:Dl,useImperativeHandle:Qu,useInsertionEffect:Wu,useLayoutEffect:Hu,useMemo:qu,useReducer:ai,useRef:Vu,useState:function(){return ai(Kn)},useDebugValue:Fl,useDeferredValue:function(e){var t=Se();return Zu(t,V.memoizedState,e)},useTransition:function(){var e=ai(Kn)[0],t=Se().memoizedState;return[e,t]},useMutableSource:Du,useSyncExternalStore:Fu,useId:Xu,unstable_isNewReconciler:!1},O0={readContext:_e,useCallback:Gu,useContext:_e,useEffect:Dl,useImperativeHandle:Qu,useInsertionEffect:Wu,useLayoutEffect:Hu,useMemo:qu,useReducer:si,useRef:Vu,useState:function(){return si(Kn)},useDebugValue:Fl,useDeferredValue:function(e){var t=Se();return V===null?t.memoizedState=e:Zu(t,V.memoizedState,e)},useTransition:function(){var e=si(Kn)[0],t=Se().memoizedState;return[e,t]},useMutableSource:Du,useSyncExternalStore:Fu,useId:Xu,unstable_isNewReconciler:!1};function Ce(e,t){if(e&&e.defaultProps){t=U({},t),e=e.defaultProps;for(var n in e)t[n]===void 0&&(t[n]=e[n]);return t}return t}function Wi(e,t,n,r){t=e.memoizedState,n=n(r,t),n=n==null?t:U({},t,n),e.memoizedState=n,e.lanes===0&&(e.updateQueue.baseState=n)}var ko={isMounted:function(e){return(e=e._reactInternals)?It(e)===e:!1},enqueueSetState:function(e,t,n){e=e._reactInternals;var r=re(),o=ft(e),i=We(r,o);i.payload=t,n!=null&&(i.callback=n),t=ct(e,i,o),t!==null&&(Re(t,e,o,r),Fr(t,e,o))},enqueueReplaceState:function(e,t,n){e=e._reactInternals;var r=re(),o=ft(e),i=We(r,o);i.tag=1,i.payload=t,n!=null&&(i.callback=n),t=ct(e,i,o),t!==null&&(Re(t,e,o,r),Fr(t,e,o))},enqueueForceUpdate:function(e,t){e=e._reactInternals;var n=re(),r=ft(e),o=We(n,r);o.tag=2,t!=null&&(o.callback=t),t=ct(e,o,r),t!==null&&(Re(t,e,r,n),Fr(t,e,r))}};function ds(e,t,n,r,o,i,l){return e=e.stateNode,typeof e.shouldComponentUpdate=="function"?e.shouldComponentUpdate(r,i,l):t.prototype&&t.prototype.isPureReactComponent?!$n(n,r)||!$n(o,i):!0}function ec(e,t,n){var r=!1,o=ht,i=t.contextType;return typeof i=="object"&&i!==null?i=_e(i):(o=se(t)?Pt:ee.current,r=t.contextTypes,i=(r=r!=null)?on(e,o):ht),t=new t(n,i),e.memoizedState=t.state!==null&&t.state!==void 0?t.state:null,t.updater=ko,e.stateNode=t,t._reactInternals=e,r&&(e=e.stateNode,e.__reactInternalMemoizedUnmaskedChildContext=o,e.__reactInternalMemoizedMaskedChildContext=i),t}function fs(e,t,n,r){e=t.state,typeof t.componentWillReceiveProps=="function"&&t.componentWillReceiveProps(n,r),typeof t.UNSAFE_componentWillReceiveProps=="function"&&t.UNSAFE_componentWillReceiveProps(n,r),t.state!==e&&ko.enqueueReplaceState(t,t.state,null)}function Hi(e,t,n,r){var o=e.stateNode;o.props=n,o.state=e.memoizedState,o.refs={},zl(e);var i=t.contextType;typeof i=="object"&&i!==null?o.context=_e(i):(i=se(t)?Pt:ee.current,o.context=on(e,i)),o.state=e.memoizedState,i=t.getDerivedStateFromProps,typeof i=="function"&&(Wi(e,t,i,n),o.state=e.memoizedState),typeof t.getDerivedStateFromProps=="function"||typeof o.getSnapshotBeforeUpdate=="function"||typeof o.UNSAFE_componentWillMount!="function"&&typeof o.componentWillMount!="function"||(t=o.state,typeof o.componentWillMount=="function"&&o.componentWillMount(),typeof o.UNSAFE_componentWillMount=="function"&&o.UNSAFE_componentWillMount(),t!==o.state&&ko.enqueueReplaceState(o,o.state,null),oo(e,n,o,r),o.state=e.memoizedState),typeof o.componentDidMount=="function"&&(e.flags|=4194308)}function un(e,t){try{var n="",r=t;do n+=hd(r),r=r.return;while(r);var o=n}catch(i){o=`
Error generating stack: `+i.message+`
`+i.stack}return{value:e,source:t,stack:o,digest:null}}function ui(e,t,n){return{value:e,source:null,stack:n??null,digest:t??null}}function $i(e,t){try{console.error(t.value)}catch(n){setTimeout(function(){throw n})}}var j0=typeof WeakMap=="function"?WeakMap:Map;function tc(e,t,n){n=We(-1,n),n.tag=3,n.payload={element:null};var r=t.value;return n.callback=function(){uo||(uo=!0,tl=r),$i(e,t)},n}function nc(e,t,n){n=We(-1,n),n.tag=3;var r=e.type.getDerivedStateFromError;if(typeof r=="function"){var o=t.value;n.payload=function(){return r(o)},n.callback=function(){$i(e,t)}}var i=e.stateNode;return i!==null&&typeof i.componentDidCatch=="function"&&(n.callback=function(){$i(e,t),typeof r!="function"&&(dt===null?dt=new Set([this]):dt.add(this));var l=t.stack;this.componentDidCatch(t.value,{componentStack:l!==null?l:""})}),n}function ps(e,t,n){var r=e.pingCache;if(r===null){r=e.pingCache=new j0;var o=new Set;r.set(t,o)}else o=r.get(t),o===void 0&&(o=new Set,r.set(t,o));o.has(n)||(o.add(n),e=ef.bind(null,e,t,n),t.then(e,e))}function ms(e){do{var t;if((t=e.tag===13)&&(t=e.memoizedState,t=t!==null?t.dehydrated!==null:!0),t)return e;e=e.return}while(e!==null);return null}function hs(e,t,n,r,o){return(e.mode&1)===0?(e===t?e.flags|=65536:(e.flags|=128,n.flags|=131072,n.flags&=-52805,n.tag===1&&(n.alternate===null?n.tag=17:(t=We(-1,1),t.tag=2,ct(n,t,1))),n.lanes|=1),e):(e.flags|=65536,e.lanes=o,e)}var B0=qe.ReactCurrentOwner,le=!1;function ne(e,t,n,r){t.child=e===null?Mu(t,null,n,r):an(t,e.child,n,r)}function gs(e,t,n,r,o){n=n.render;var i=t.ref;return tn(t,o),r=Il(e,t,n,r,i,o),n=bl(),e!==null&&!le?(t.updateQueue=e.updateQueue,t.flags&=-2053,e.lanes&=~o,Ge(e,t,o)):(D&&n&&kl(t),t.flags|=1,ne(e,t,r,o),t.child)}function vs(e,t,n,r,o){if(e===null){var i=n.type;return typeof i=="function"&&!Hl(i)&&i.defaultProps===void 0&&n.compare===null&&n.defaultProps===void 0?(t.tag=15,t.type=i,rc(e,t,i,r,o)):(e=Vr(n.type,null,r,t,t.mode,o),e.ref=t.ref,e.return=t,t.child=e)}if(i=e.child,(e.lanes&o)===0){var l=i.memoizedProps;if(n=n.compare,n=n!==null?n:$n,n(l,r)&&e.ref===t.ref)return Ge(e,t,o)}return t.flags|=1,e=pt(i,r),e.ref=t.ref,e.return=t,t.child=e}function rc(e,t,n,r,o){if(e!==null){var i=e.memoizedProps;if($n(i,r)&&e.ref===t.ref)if(le=!1,t.pendingProps=r=i,(e.lanes&o)!==0)(e.flags&131072)!==0&&(le=!0);else return t.lanes=e.lanes,Ge(e,t,o)}return Qi(e,t,n,r,o)}function oc(e,t,n){var r=t.pendingProps,o=r.children,i=e!==null?e.memoizedState:null;if(r.mode==="hidden")if((t.mode&1)===0)t.memoizedState={baseLanes:0,cachePool:null,transitions:null},M(Xt,ce),ce|=n;else{if((n&1073741824)===0)return e=i!==null?i.baseLanes|n:n,t.lanes=t.childLanes=1073741824,t.memoizedState={baseLanes:e,cachePool:null,transitions:null},t.updateQueue=null,M(Xt,ce),ce|=e,null;t.memoizedState={baseLanes:0,cachePool:null,transitions:null},r=i!==null?i.baseLanes:n,M(Xt,ce),ce|=r}else i!==null?(r=i.baseLanes|n,t.memoizedState=null):r=n,M(Xt,ce),ce|=r;return ne(e,t,o,n),t.child}function ic(e,t){var n=t.ref;(e===null&&n!==null||e!==null&&e.ref!==n)&&(t.flags|=512,t.flags|=2097152)}function Qi(e,t,n,r,o){var i=se(n)?Pt:ee.current;return i=on(t,i),tn(t,o),n=Il(e,t,n,r,i,o),r=bl(),e!==null&&!le?(t.updateQueue=e.updateQueue,t.flags&=-2053,e.lanes&=~o,Ge(e,t,o)):(D&&r&&kl(t),t.flags|=1,ne(e,t,n,o),t.child)}function ys(e,t,n,r,o){if(se(n)){var i=!0;Jr(t)}else i=!1;if(tn(t,o),t.stateNode===null)Or(e,t),ec(t,n,r),Hi(t,n,r,o),r=!0;else if(e===null){var l=t.stateNode,a=t.memoizedProps;l.props=a;var s=l.context,d=n.contextType;typeof d=="object"&&d!==null?d=_e(d):(d=se(n)?Pt:ee.current,d=on(t,d));var p=n.getDerivedStateFromProps,h=typeof p=="function"||typeof l.getSnapshotBeforeUpdate=="function";h||typeof l.UNSAFE_componentWillReceiveProps!="function"&&typeof l.componentWillReceiveProps!="function"||(a!==r||s!==d)&&fs(t,l,r,d),tt=!1;var m=t.memoizedState;l.state=m,oo(t,r,l,o),s=t.memoizedState,a!==r||m!==s||ae.current||tt?(typeof p=="function"&&(Wi(t,n,p,r),s=t.memoizedState),(a=tt||ds(t,n,a,r,m,s,d))?(h||typeof l.UNSAFE_componentWillMount!="function"&&typeof l.componentWillMount!="function"||(typeof l.componentWillMount=="function"&&l.componentWillMount(),typeof l.UNSAFE_componentWillMount=="function"&&l.UNSAFE_componentWillMount()),typeof l.componentDidMount=="function"&&(t.flags|=4194308)):(typeof l.componentDidMount=="function"&&(t.flags|=4194308),t.memoizedProps=r,t.memoizedState=s),l.props=r,l.state=s,l.context=d,r=a):(typeof l.componentDidMount=="function"&&(t.flags|=4194308),r=!1)}else{l=t.stateNode,Iu(e,t),a=t.memoizedProps,d=t.type===t.elementType?a:Ce(t.type,a),l.props=d,h=t.pendingProps,m=l.context,s=n.contextType,typeof s=="object"&&s!==null?s=_e(s):(s=se(n)?Pt:ee.current,s=on(t,s));var y=n.getDerivedStateFromProps;(p=typeof y=="function"||typeof l.getSnapshotBeforeUpdate=="function")||typeof l.UNSAFE_componentWillReceiveProps!="function"&&typeof l.componentWillReceiveProps!="function"||(a!==h||m!==s)&&fs(t,l,r,s),tt=!1,m=t.memoizedState,l.state=m,oo(t,r,l,o);var w=t.memoizedState;a!==h||m!==w||ae.current||tt?(typeof y=="function"&&(Wi(t,n,y,r),w=t.memoizedState),(d=tt||ds(t,n,d,r,m,w,s)||!1)?(p||typeof l.UNSAFE_componentWillUpdate!="function"&&typeof l.componentWillUpdate!="function"||(typeof l.componentWillUpdate=="function"&&l.componentWillUpdate(r,w,s),typeof l.UNSAFE_componentWillUpdate=="function"&&l.UNSAFE_componentWillUpdate(r,w,s)),typeof l.componentDidUpdate=="function"&&(t.flags|=4),typeof l.getSnapshotBeforeUpdate=="function"&&(t.flags|=1024)):(typeof l.componentDidUpdate!="function"||a===e.memoizedProps&&m===e.memoizedState||(t.flags|=4),typeof l.getSnapshotBeforeUpdate!="function"||a===e.memoizedProps&&m===e.memoizedState||(t.flags|=1024),t.memoizedProps=r,t.memoizedState=w),l.props=r,l.state=w,l.context=s,r=d):(typeof l.componentDidUpdate!="function"||a===e.memoizedProps&&m===e.memoizedState||(t.flags|=4),typeof l.getSnapshotBeforeUpdate!="function"||a===e.memoizedProps&&m===e.memoizedState||(t.flags|=1024),r=!1)}return Gi(e,t,n,r,i,o)}function Gi(e,t,n,r,o,i){ic(e,t);var l=(t.flags&128)!==0;if(!r&&!l)return o&&rs(t,n,!1),Ge(e,t,i);r=t.stateNode,B0.current=t;var a=l&&typeof n.getDerivedStateFromError!="function"?null:r.render();return t.flags|=1,e!==null&&l?(t.child=an(t,e.child,null,i),t.child=an(t,null,a,i)):ne(e,t,a,i),t.memoizedState=r.state,o&&rs(t,n,!0),t.child}function lc(e){var t=e.stateNode;t.pendingContext?ns(e,t.pendingContext,t.pendingContext!==t.context):t.context&&ns(e,t.context,!1),Nl(e,t.containerInfo)}function xs(e,t,n,r,o){return ln(),Sl(o),t.flags|=256,ne(e,t,n,r),t.child}var qi={dehydrated:null,treeContext:null,retryLane:0};function Zi(e){return{baseLanes:e,cachePool:null,transitions:null}}function ac(e,t,n){var r=t.pendingProps,o=F.current,i=!1,l=(t.flags&128)!==0,a;if((a=l)||(a=e!==null&&e.memoizedState===null?!1:(o&2)!==0),a?(i=!0,t.flags&=-129):(e===null||e.memoizedState!==null)&&(o|=1),M(F,o&1),e===null)return Bi(t),e=t.memoizedState,e!==null&&(e=e.dehydrated,e!==null)?((t.mode&1)===0?t.lanes=1:e.data==="$!"?t.lanes=8:t.lanes=1073741824,null):(l=r.children,e=r.fallback,i?(r=t.mode,i=t.child,l={mode:"hidden",children:l},(r&1)===0&&i!==null?(i.childLanes=0,i.pendingProps=l):i=Eo(l,r,0,null),e=Ct(e,r,n,null),i.return=t,e.return=t,i.sibling=e,t.child=i,t.child.memoizedState=Zi(n),t.memoizedState=qi,e):Al(t,l));if(o=e.memoizedState,o!==null&&(a=o.dehydrated,a!==null))return V0(e,t,l,r,a,o,n);if(i){i=r.fallback,l=t.mode,o=e.child,a=o.sibling;var s={mode:"hidden",children:r.children};return(l&1)===0&&t.child!==o?(r=t.child,r.childLanes=0,r.pendingProps=s,t.deletions=null):(r=pt(o,s),r.subtreeFlags=o.subtreeFlags&14680064),a!==null?i=pt(a,i):(i=Ct(i,l,n,null),i.flags|=2),i.return=t,r.return=t,r.sibling=i,t.child=r,r=i,i=t.child,l=e.child.memoizedState,l=l===null?Zi(n):{baseLanes:l.baseLanes|n,cachePool:null,transitions:l.transitions},i.memoizedState=l,i.childLanes=e.childLanes&~n,t.memoizedState=qi,r}return i=e.child,e=i.sibling,r=pt(i,{mode:"visible",children:r.children}),(t.mode&1)===0&&(r.lanes=n),r.return=t,r.sibling=null,e!==null&&(n=t.deletions,n===null?(t.deletions=[e],t.flags|=16):n.push(e)),t.child=r,t.memoizedState=null,r}function Al(e,t){return t=Eo({mode:"visible",children:t},e.mode,0,null),t.return=e,e.child=t}function Rr(e,t,n,r){return r!==null&&Sl(r),an(t,e.child,null,n),e=Al(t,t.pendingProps.children),e.flags|=2,t.memoizedState=null,e}function V0(e,t,n,r,o,i,l){if(n)return t.flags&256?(t.flags&=-257,r=ui(Error(v(422))),Rr(e,t,l,r)):t.memoizedState!==null?(t.child=e.child,t.flags|=128,null):(i=r.fallback,o=t.mode,r=Eo({mode:"visible",children:r.children},o,0,null),i=Ct(i,o,l,null),i.flags|=2,r.return=t,i.return=t,r.sibling=i,t.child=r,(t.mode&1)!==0&&an(t,e.child,null,l),t.child.memoizedState=Zi(l),t.memoizedState=qi,i);if((t.mode&1)===0)return Rr(e,t,l,null);if(o.data==="$!"){if(r=o.nextSibling&&o.nextSibling.dataset,r)var a=r.dgst;return r=a,i=Error(v(419)),r=ui(i,r,void 0),Rr(e,t,l,r)}if(a=(l&e.childLanes)!==0,le||a){if(r=Q,r!==null){switch(l&-l){case 4:o=2;break;case 16:o=8;break;case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:o=32;break;case 536870912:o=268435456;break;default:o=0}o=(o&(r.suspendedLanes|l))!==0?0:o,o!==0&&o!==i.retryLane&&(i.retryLane=o,Qe(e,o),Re(r,e,o,-1))}return Wl(),r=ui(Error(v(421))),Rr(e,t,l,r)}return o.data==="$?"?(t.flags|=128,t.child=e.child,t=tf.bind(null,e),o._reactRetry=t,null):(e=i.treeContext,de=ut(o.nextSibling),fe=t,D=!0,ze=null,e!==null&&(ye[xe++]=Be,ye[xe++]=Ve,ye[xe++]=zt,Be=e.id,Ve=e.overflow,zt=t),t=Al(t,r.children),t.flags|=4096,t)}function ws(e,t,n){e.lanes|=t;var r=e.alternate;r!==null&&(r.lanes|=t),Vi(e.return,t,n)}function ci(e,t,n,r,o){var i=e.memoizedState;i===null?e.memoizedState={isBackwards:t,rendering:null,renderingStartTime:0,last:r,tail:n,tailMode:o}:(i.isBackwards=t,i.rendering=null,i.renderingStartTime=0,i.last=r,i.tail=n,i.tailMode=o)}function sc(e,t,n){var r=t.pendingProps,o=r.revealOrder,i=r.tail;if(ne(e,t,r.children,n),r=F.current,(r&2)!==0)r=r&1|2,t.flags|=128;else{if(e!==null&&(e.flags&128)!==0)e:for(e=t.child;e!==null;){if(e.tag===13)e.memoizedState!==null&&ws(e,n,t);else if(e.tag===19)ws(e,n,t);else if(e.child!==null){e.child.return=e,e=e.child;continue}if(e===t)break e;for(;e.sibling===null;){if(e.return===null||e.return===t)break e;e=e.return}e.sibling.return=e.return,e=e.sibling}r&=1}if(M(F,r),(t.mode&1)===0)t.memoizedState=null;else switch(o){case"forwards":for(n=t.child,o=null;n!==null;)e=n.alternate,e!==null&&io(e)===null&&(o=n),n=n.sibling;n=o,n===null?(o=t.child,t.child=null):(o=n.sibling,n.sibling=null),ci(t,!1,o,n,i);break;case"backwards":for(n=null,o=t.child,t.child=null;o!==null;){if(e=o.alternate,e!==null&&io(e)===null){t.child=o;break}e=o.sibling,o.sibling=n,n=o,o=e}ci(t,!0,n,null,i);break;case"together":ci(t,!1,null,null,void 0);break;default:t.memoizedState=null}return t.child}function Or(e,t){(t.mode&1)===0&&e!==null&&(e.alternate=null,t.alternate=null,t.flags|=2)}function Ge(e,t,n){if(e!==null&&(t.dependencies=e.dependencies),Rt|=t.lanes,(n&t.childLanes)===0)return null;if(e!==null&&t.child!==e.child)throw Error(v(153));if(t.child!==null){for(e=t.child,n=pt(e,e.pendingProps),t.child=n,n.return=t;e.sibling!==null;)e=e.sibling,n=n.sibling=pt(e,e.pendingProps),n.return=t;n.sibling=null}return t.child}function W0(e,t,n){switch(t.tag){case 3:lc(t),ln();break;case 5:bu(t);break;case 1:se(t.type)&&Jr(t);break;case 4:Nl(t,t.stateNode.containerInfo);break;case 10:var r=t.type._context,o=t.memoizedProps.value;M(no,r._currentValue),r._currentValue=o;break;case 13:if(r=t.memoizedState,r!==null)return r.dehydrated!==null?(M(F,F.current&1),t.flags|=128,null):(n&t.child.childLanes)!==0?ac(e,t,n):(M(F,F.current&1),e=Ge(e,t,n),e!==null?e.sibling:null);M(F,F.current&1);break;case 19:if(r=(n&t.childLanes)!==0,(e.flags&128)!==0){if(r)return sc(e,t,n);t.flags|=128}if(o=t.memoizedState,o!==null&&(o.rendering=null,o.tail=null,o.lastEffect=null),M(F,F.current),r)break;return null;case 22:case 23:return t.lanes=0,oc(e,t,n)}return Ge(e,t,n)}var uc,Xi,cc,dc;uc=function(e,t){for(var n=t.child;n!==null;){if(n.tag===5||n.tag===6)e.appendChild(n.stateNode);else if(n.tag!==4&&n.child!==null){n.child.return=n,n=n.child;continue}if(n===t)break;for(;n.sibling===null;){if(n.return===null||n.return===t)return;n=n.return}n.sibling.return=n.return,n=n.sibling}};Xi=function(){};cc=function(e,t,n,r){var o=e.memoizedProps;if(o!==r){e=t.stateNode,Et(Ae.current);var i=null;switch(n){case"input":o=yi(e,o),r=yi(e,r),i=[];break;case"select":o=U({},o,{value:void 0}),r=U({},r,{value:void 0}),i=[];break;case"textarea":o=ki(e,o),r=ki(e,r),i=[];break;default:typeof o.onClick!="function"&&typeof r.onClick=="function"&&(e.onclick=Yr)}Si(n,r);var l;n=null;for(d in o)if(!r.hasOwnProperty(d)&&o.hasOwnProperty(d)&&o[d]!=null)if(d==="style"){var a=o[d];for(l in a)a.hasOwnProperty(l)&&(n||(n={}),n[l]="")}else d!=="dangerouslySetInnerHTML"&&d!=="children"&&d!=="suppressContentEditableWarning"&&d!=="suppressHydrationWarning"&&d!=="autoFocus"&&(Un.hasOwnProperty(d)?i||(i=[]):(i=i||[]).push(d,null));for(d in r){var s=r[d];if(a=o?.[d],r.hasOwnProperty(d)&&s!==a&&(s!=null||a!=null))if(d==="style")if(a){for(l in a)!a.hasOwnProperty(l)||s&&s.hasOwnProperty(l)||(n||(n={}),n[l]="");for(l in s)s.hasOwnProperty(l)&&a[l]!==s[l]&&(n||(n={}),n[l]=s[l])}else n||(i||(i=[]),i.push(d,n)),n=s;else d==="dangerouslySetInnerHTML"?(s=s?s.__html:void 0,a=a?a.__html:void 0,s!=null&&a!==s&&(i=i||[]).push(d,s)):d==="children"?typeof s!="string"&&typeof s!="number"||(i=i||[]).push(d,""+s):d!=="suppressContentEditableWarning"&&d!=="suppressHydrationWarning"&&(Un.hasOwnProperty(d)?(s!=null&&d==="onScroll"&&L("scroll",e),i||a===s||(i=[])):(i=i||[]).push(d,s))}n&&(i=i||[]).push("style",n);var d=i;(t.updateQueue=d)&&(t.flags|=4)}};dc=function(e,t,n,r){n!==r&&(t.flags|=4)};function _n(e,t){if(!D)switch(e.tailMode){case"hidden":t=e.tail;for(var n=null;t!==null;)t.alternate!==null&&(n=t),t=t.sibling;n===null?e.tail=null:n.sibling=null;break;case"collapsed":n=e.tail;for(var r=null;n!==null;)n.alternate!==null&&(r=n),n=n.sibling;r===null?t||e.tail===null?e.tail=null:e.tail.sibling=null:r.sibling=null}}function K(e){var t=e.alternate!==null&&e.alternate.child===e.child,n=0,r=0;if(t)for(var o=e.child;o!==null;)n|=o.lanes|o.childLanes,r|=o.subtreeFlags&14680064,r|=o.flags&14680064,o.return=e,o=o.sibling;else for(o=e.child;o!==null;)n|=o.lanes|o.childLanes,r|=o.subtreeFlags,r|=o.flags,o.return=e,o=o.sibling;return e.subtreeFlags|=r,e.childLanes=n,t}function H0(e,t,n){var r=t.pendingProps;switch(_l(t),t.tag){case 2:case 16:case 15:case 0:case 11:case 7:case 8:case 12:case 9:case 14:return K(t),null;case 1:return se(t.type)&&Kr(),K(t),null;case 3:return r=t.stateNode,sn(),I(ae),I(ee),Ml(),r.pendingContext&&(r.context=r.pendingContext,r.pendingContext=null),(e===null||e.child===null)&&(zr(t)?t.flags|=4:e===null||e.memoizedState.isDehydrated&&(t.flags&256)===0||(t.flags|=1024,ze!==null&&(ol(ze),ze=null))),Xi(e,t),K(t),null;case 5:Rl(t);var o=Et(Xn.current);if(n=t.type,e!==null&&t.stateNode!=null)cc(e,t,n,r,o),e.ref!==t.ref&&(t.flags|=512,t.flags|=2097152);else{if(!r){if(t.stateNode===null)throw Error(v(166));return K(t),null}if(e=Et(Ae.current),zr(t)){r=t.stateNode,n=t.type;var i=t.memoizedProps;switch(r[De]=t,r[qn]=i,e=(t.mode&1)!==0,n){case"dialog":L("cancel",r),L("close",r);break;case"iframe":case"object":case"embed":L("load",r);break;case"video":case"audio":for(o=0;o<zn.length;o++)L(zn[o],r);break;case"source":L("error",r);break;case"img":case"image":case"link":L("error",r),L("load",r);break;case"details":L("toggle",r);break;case"input":za(r,i),L("invalid",r);break;case"select":r._wrapperState={wasMultiple:!!i.multiple},L("invalid",r);break;case"textarea":Ra(r,i),L("invalid",r)}Si(n,i),o=null;for(var l in i)if(i.hasOwnProperty(l)){var a=i[l];l==="children"?typeof a=="string"?r.textContent!==a&&(i.suppressHydrationWarning!==!0&&Pr(r.textContent,a,e),o=["children",a]):typeof a=="number"&&r.textContent!==""+a&&(i.suppressHydrationWarning!==!0&&Pr(r.textContent,a,e),o=["children",""+a]):Un.hasOwnProperty(l)&&a!=null&&l==="onScroll"&&L("scroll",r)}switch(n){case"input":hr(r),Na(r,i,!0);break;case"textarea":hr(r),Ma(r);break;case"select":case"option":break;default:typeof i.onClick=="function"&&(r.onclick=Yr)}r=o,t.updateQueue=r,r!==null&&(t.flags|=4)}else{l=o.nodeType===9?o:o.ownerDocument,e==="http://www.w3.org/1999/xhtml"&&(e=Os(n)),e==="http://www.w3.org/1999/xhtml"?n==="script"?(e=l.createElement("div"),e.innerHTML="<script><\/script>",e=e.removeChild(e.firstChild)):typeof r.is=="string"?e=l.createElement(n,{is:r.is}):(e=l.createElement(n),n==="select"&&(l=e,r.multiple?l.multiple=!0:r.size&&(l.size=r.size))):e=l.createElementNS(e,n),e[De]=t,e[qn]=r,uc(e,t,!1,!1),t.stateNode=e;e:{switch(l=Ei(n,r),n){case"dialog":L("cancel",e),L("close",e),o=r;break;case"iframe":case"object":case"embed":L("load",e),o=r;break;case"video":case"audio":for(o=0;o<zn.length;o++)L(zn[o],e);o=r;break;case"source":L("error",e),o=r;break;case"img":case"image":case"link":L("error",e),L("load",e),o=r;break;case"details":L("toggle",e),o=r;break;case"input":za(e,r),o=yi(e,r),L("invalid",e);break;case"option":o=r;break;case"select":e._wrapperState={wasMultiple:!!r.multiple},o=U({},r,{value:void 0}),L("invalid",e);break;case"textarea":Ra(e,r),o=ki(e,r),L("invalid",e);break;default:o=r}Si(n,o),a=o;for(i in a)if(a.hasOwnProperty(i)){var s=a[i];i==="style"?Vs(e,s):i==="dangerouslySetInnerHTML"?(s=s?s.__html:void 0,s!=null&&js(e,s)):i==="children"?typeof s=="string"?(n!=="textarea"||s!=="")&&On(e,s):typeof s=="number"&&On(e,""+s):i!=="suppressContentEditableWarning"&&i!=="suppressHydrationWarning"&&i!=="autoFocus"&&(Un.hasOwnProperty(i)?s!=null&&i==="onScroll"&&L("scroll",e):s!=null&&al(e,i,s,l))}switch(n){case"input":hr(e),Na(e,r,!1);break;case"textarea":hr(e),Ma(e);break;case"option":r.value!=null&&e.setAttribute("value",""+mt(r.value));break;case"select":e.multiple=!!r.multiple,i=r.value,i!=null?Yt(e,!!r.multiple,i,!1):r.defaultValue!=null&&Yt(e,!!r.multiple,r.defaultValue,!0);break;default:typeof o.onClick=="function"&&(e.onclick=Yr)}switch(n){case"button":case"input":case"select":case"textarea":r=!!r.autoFocus;break e;case"img":r=!0;break e;default:r=!1}}r&&(t.flags|=4)}t.ref!==null&&(t.flags|=512,t.flags|=2097152)}return K(t),null;case 6:if(e&&t.stateNode!=null)dc(e,t,e.memoizedProps,r);else{if(typeof r!="string"&&t.stateNode===null)throw Error(v(166));if(n=Et(Xn.current),Et(Ae.current),zr(t)){if(r=t.stateNode,n=t.memoizedProps,r[De]=t,(i=r.nodeValue!==n)&&(e=fe,e!==null))switch(e.tag){case 3:Pr(r.nodeValue,n,(e.mode&1)!==0);break;case 5:e.memoizedProps.suppressHydrationWarning!==!0&&Pr(r.nodeValue,n,(e.mode&1)!==0)}i&&(t.flags|=4)}else r=(n.nodeType===9?n:n.ownerDocument).createTextNode(r),r[De]=t,t.stateNode=r}return K(t),null;case 13:if(I(F),r=t.memoizedState,e===null||e.memoizedState!==null&&e.memoizedState.dehydrated!==null){if(D&&de!==null&&(t.mode&1)!==0&&(t.flags&128)===0)Nu(),ln(),t.flags|=98560,i=!1;else if(i=zr(t),r!==null&&r.dehydrated!==null){if(e===null){if(!i)throw Error(v(318));if(i=t.memoizedState,i=i!==null?i.dehydrated:null,!i)throw Error(v(317));i[De]=t}else ln(),(t.flags&128)===0&&(t.memoizedState=null),t.flags|=4;K(t),i=!1}else ze!==null&&(ol(ze),ze=null),i=!0;if(!i)return t.flags&65536?t:null}return(t.flags&128)!==0?(t.lanes=n,t):(r=r!==null,r!==(e!==null&&e.memoizedState!==null)&&r&&(t.child.flags|=8192,(t.mode&1)!==0&&(e===null||(F.current&1)!==0?W===0&&(W=3):Wl())),t.updateQueue!==null&&(t.flags|=4),K(t),null);case 4:return sn(),Xi(e,t),e===null&&Qn(t.stateNode.containerInfo),K(t),null;case 10:return Cl(t.type._context),K(t),null;case 17:return se(t.type)&&Kr(),K(t),null;case 19:if(I(F),i=t.memoizedState,i===null)return K(t),null;if(r=(t.flags&128)!==0,l=i.rendering,l===null)if(r)_n(i,!1);else{if(W!==0||e!==null&&(e.flags&128)!==0)for(e=t.child;e!==null;){if(l=io(e),l!==null){for(t.flags|=128,_n(i,!1),r=l.updateQueue,r!==null&&(t.updateQueue=r,t.flags|=4),t.subtreeFlags=0,r=n,n=t.child;n!==null;)i=n,e=r,i.flags&=14680066,l=i.alternate,l===null?(i.childLanes=0,i.lanes=e,i.child=null,i.subtreeFlags=0,i.memoizedProps=null,i.memoizedState=null,i.updateQueue=null,i.dependencies=null,i.stateNode=null):(i.childLanes=l.childLanes,i.lanes=l.lanes,i.child=l.child,i.subtreeFlags=0,i.deletions=null,i.memoizedProps=l.memoizedProps,i.memoizedState=l.memoizedState,i.updateQueue=l.updateQueue,i.type=l.type,e=l.dependencies,i.dependencies=e===null?null:{lanes:e.lanes,firstContext:e.firstContext}),n=n.sibling;return M(F,F.current&1|2),t.child}e=e.sibling}i.tail!==null&&j()>cn&&(t.flags|=128,r=!0,_n(i,!1),t.lanes=4194304)}else{if(!r)if(e=io(l),e!==null){if(t.flags|=128,r=!0,n=e.updateQueue,n!==null&&(t.updateQueue=n,t.flags|=4),_n(i,!0),i.tail===null&&i.tailMode==="hidden"&&!l.alternate&&!D)return K(t),null}else 2*j()-i.renderingStartTime>cn&&n!==1073741824&&(t.flags|=128,r=!0,_n(i,!1),t.lanes=4194304);i.isBackwards?(l.sibling=t.child,t.child=l):(n=i.last,n!==null?n.sibling=l:t.child=l,i.last=l)}return i.tail!==null?(t=i.tail,i.rendering=t,i.tail=t.sibling,i.renderingStartTime=j(),t.sibling=null,n=F.current,M(F,r?n&1|2:n&1),t):(K(t),null);case 22:case 23:return Vl(),r=t.memoizedState!==null,e!==null&&e.memoizedState!==null!==r&&(t.flags|=8192),r&&(t.mode&1)!==0?(ce&1073741824)!==0&&(K(t),t.subtreeFlags&6&&(t.flags|=8192)):K(t),null;case 24:return null;case 25:return null}throw Error(v(156,t.tag))}function $0(e,t){switch(_l(t),t.tag){case 1:return se(t.type)&&Kr(),e=t.flags,e&65536?(t.flags=e&-65537|128,t):null;case 3:return sn(),I(ae),I(ee),Ml(),e=t.flags,(e&65536)!==0&&(e&128)===0?(t.flags=e&-65537|128,t):null;case 5:return Rl(t),null;case 13:if(I(F),e=t.memoizedState,e!==null&&e.dehydrated!==null){if(t.alternate===null)throw Error(v(340));ln()}return e=t.flags,e&65536?(t.flags=e&-65537|128,t):null;case 19:return I(F),null;case 4:return sn(),null;case 10:return Cl(t.type._context),null;case 22:case 23:return Vl(),null;case 24:return null;default:return null}}var Mr=!1,J=!1,Q0=typeof WeakSet=="function"?WeakSet:Set,k=null;function Zt(e,t){var n=e.ref;if(n!==null)if(typeof n=="function")try{n(null)}catch(r){O(e,t,r)}else n.current=null}function Yi(e,t,n){try{n()}catch(r){O(e,t,r)}}var ks=!1;function G0(e,t){if(bi=qr,e=gu(),wl(e)){if("selectionStart"in e)var n={start:e.selectionStart,end:e.selectionEnd};else e:{n=(n=e.ownerDocument)&&n.defaultView||window;var r=n.getSelection&&n.getSelection();if(r&&r.rangeCount!==0){n=r.anchorNode;var o=r.anchorOffset,i=r.focusNode;r=r.focusOffset;try{n.nodeType,i.nodeType}catch{n=null;break e}var l=0,a=-1,s=-1,d=0,p=0,h=e,m=null;t:for(;;){for(var y;h!==n||o!==0&&h.nodeType!==3||(a=l+o),h!==i||r!==0&&h.nodeType!==3||(s=l+r),h.nodeType===3&&(l+=h.nodeValue.length),(y=h.firstChild)!==null;)m=h,h=y;for(;;){if(h===e)break t;if(m===n&&++d===o&&(a=l),m===i&&++p===r&&(s=l),(y=h.nextSibling)!==null)break;h=m,m=h.parentNode}h=y}n=a===-1||s===-1?null:{start:a,end:s}}else n=null}n=n||{start:0,end:0}}else n=null;for(Di={focusedElem:e,selectionRange:n},qr=!1,k=t;k!==null;)if(t=k,e=t.child,(t.subtreeFlags&1028)!==0&&e!==null)e.return=t,k=e;else for(;k!==null;){t=k;try{var w=t.alternate;if((t.flags&1024)!==0)switch(t.tag){case 0:case 11:case 15:break;case 1:if(w!==null){var x=w.memoizedProps,b=w.memoizedState,c=t.stateNode,u=c.getSnapshotBeforeUpdate(t.elementType===t.type?x:Ce(t.type,x),b);c.__reactInternalSnapshotBeforeUpdate=u}break;case 3:var f=t.stateNode.containerInfo;f.nodeType===1?f.textContent="":f.nodeType===9&&f.documentElement&&f.removeChild(f.documentElement);break;case 5:case 6:case 4:case 17:break;default:throw Error(v(163))}}catch(g){O(t,t.return,g)}if(e=t.sibling,e!==null){e.return=t.return,k=e;break}k=t.return}return w=ks,ks=!1,w}function Dn(e,t,n){var r=t.updateQueue;if(r=r!==null?r.lastEffect:null,r!==null){var o=r=r.next;do{if((o.tag&e)===e){var i=o.destroy;o.destroy=void 0,i!==void 0&&Yi(t,n,i)}o=o.next}while(o!==r)}}function _o(e,t){if(t=t.updateQueue,t=t!==null?t.lastEffect:null,t!==null){var n=t=t.next;do{if((n.tag&e)===e){var r=n.create;n.destroy=r()}n=n.next}while(n!==t)}}function Ki(e){var t=e.ref;if(t!==null){var n=e.stateNode;switch(e.tag){case 5:e=n;break;default:e=n}typeof t=="function"?t(e):t.current=e}}function fc(e){var t=e.alternate;t!==null&&(e.alternate=null,fc(t)),e.child=null,e.deletions=null,e.sibling=null,e.tag===5&&(t=e.stateNode,t!==null&&(delete t[De],delete t[qn],delete t[Ui],delete t[N0],delete t[R0])),e.stateNode=null,e.return=null,e.dependencies=null,e.memoizedProps=null,e.memoizedState=null,e.pendingProps=null,e.stateNode=null,e.updateQueue=null}function pc(e){return e.tag===5||e.tag===3||e.tag===4}function _s(e){e:for(;;){for(;e.sibling===null;){if(e.return===null||pc(e.return))return null;e=e.return}for(e.sibling.return=e.return,e=e.sibling;e.tag!==5&&e.tag!==6&&e.tag!==18;){if(e.flags&2||e.child===null||e.tag===4)continue e;e.child.return=e,e=e.child}if(!(e.flags&2))return e.stateNode}}function Ji(e,t,n){var r=e.tag;if(r===5||r===6)e=e.stateNode,t?n.nodeType===8?n.parentNode.insertBefore(e,t):n.insertBefore(e,t):(n.nodeType===8?(t=n.parentNode,t.insertBefore(e,n)):(t=n,t.appendChild(e)),n=n._reactRootContainer,n!=null||t.onclick!==null||(t.onclick=Yr));else if(r!==4&&(e=e.child,e!==null))for(Ji(e,t,n),e=e.sibling;e!==null;)Ji(e,t,n),e=e.sibling}function el(e,t,n){var r=e.tag;if(r===5||r===6)e=e.stateNode,t?n.insertBefore(e,t):n.appendChild(e);else if(r!==4&&(e=e.child,e!==null))for(el(e,t,n),e=e.sibling;e!==null;)el(e,t,n),e=e.sibling}var G=null,Pe=!1;function Je(e,t,n){for(n=n.child;n!==null;)mc(e,t,n),n=n.sibling}function mc(e,t,n){if(Fe&&typeof Fe.onCommitFiberUnmount=="function")try{Fe.onCommitFiberUnmount(mo,n)}catch{}switch(n.tag){case 5:J||Zt(n,t);case 6:var r=G,o=Pe;G=null,Je(e,t,n),G=r,Pe=o,G!==null&&(Pe?(e=G,n=n.stateNode,e.nodeType===8?e.parentNode.removeChild(n):e.removeChild(n)):G.removeChild(n.stateNode));break;case 18:G!==null&&(Pe?(e=G,n=n.stateNode,e.nodeType===8?ri(e.parentNode,n):e.nodeType===1&&ri(e,n),Wn(e)):ri(G,n.stateNode));break;case 4:r=G,o=Pe,G=n.stateNode.containerInfo,Pe=!0,Je(e,t,n),G=r,Pe=o;break;case 0:case 11:case 14:case 15:if(!J&&(r=n.updateQueue,r!==null&&(r=r.lastEffect,r!==null))){o=r=r.next;do{var i=o,l=i.destroy;i=i.tag,l!==void 0&&((i&2)!==0||(i&4)!==0)&&Yi(n,t,l),o=o.next}while(o!==r)}Je(e,t,n);break;case 1:if(!J&&(Zt(n,t),r=n.stateNode,typeof r.componentWillUnmount=="function"))try{r.props=n.memoizedProps,r.state=n.memoizedState,r.componentWillUnmount()}catch(a){O(n,t,a)}Je(e,t,n);break;case 21:Je(e,t,n);break;case 22:n.mode&1?(J=(r=J)||n.memoizedState!==null,Je(e,t,n),J=r):Je(e,t,n);break;default:Je(e,t,n)}}function Ss(e){var t=e.updateQueue;if(t!==null){e.updateQueue=null;var n=e.stateNode;n===null&&(n=e.stateNode=new Q0),t.forEach(function(r){var o=nf.bind(null,e,r);n.has(r)||(n.add(r),r.then(o,o))})}}function Te(e,t){var n=t.deletions;if(n!==null)for(var r=0;r<n.length;r++){var o=n[r];try{var i=e,l=t,a=l;e:for(;a!==null;){switch(a.tag){case 5:G=a.stateNode,Pe=!1;break e;case 3:G=a.stateNode.containerInfo,Pe=!0;break e;case 4:G=a.stateNode.containerInfo,Pe=!0;break e}a=a.return}if(G===null)throw Error(v(160));mc(i,l,o),G=null,Pe=!1;var s=o.alternate;s!==null&&(s.return=null),o.return=null}catch(d){O(o,t,d)}}if(t.subtreeFlags&12854)for(t=t.child;t!==null;)hc(t,e),t=t.sibling}function hc(e,t){var n=e.alternate,r=e.flags;switch(e.tag){case 0:case 11:case 14:case 15:if(Te(t,e),Ie(e),r&4){try{Dn(3,e,e.return),_o(3,e)}catch(x){O(e,e.return,x)}try{Dn(5,e,e.return)}catch(x){O(e,e.return,x)}}break;case 1:Te(t,e),Ie(e),r&512&&n!==null&&Zt(n,n.return);break;case 5:if(Te(t,e),Ie(e),r&512&&n!==null&&Zt(n,n.return),e.flags&32){var o=e.stateNode;try{On(o,"")}catch(x){O(e,e.return,x)}}if(r&4&&(o=e.stateNode,o!=null)){var i=e.memoizedProps,l=n!==null?n.memoizedProps:i,a=e.type,s=e.updateQueue;if(e.updateQueue=null,s!==null)try{a==="input"&&i.type==="radio"&&i.name!=null&&As(o,i),Ei(a,l);var d=Ei(a,i);for(l=0;l<s.length;l+=2){var p=s[l],h=s[l+1];p==="style"?Vs(o,h):p==="dangerouslySetInnerHTML"?js(o,h):p==="children"?On(o,h):al(o,p,h,d)}switch(a){case"input":xi(o,i);break;case"textarea":Us(o,i);break;case"select":var m=o._wrapperState.wasMultiple;o._wrapperState.wasMultiple=!!i.multiple;var y=i.value;y!=null?Yt(o,!!i.multiple,y,!1):m!==!!i.multiple&&(i.defaultValue!=null?Yt(o,!!i.multiple,i.defaultValue,!0):Yt(o,!!i.multiple,i.multiple?[]:"",!1))}o[qn]=i}catch(x){O(e,e.return,x)}}break;case 6:if(Te(t,e),Ie(e),r&4){if(e.stateNode===null)throw Error(v(162));o=e.stateNode,i=e.memoizedProps;try{o.nodeValue=i}catch(x){O(e,e.return,x)}}break;case 3:if(Te(t,e),Ie(e),r&4&&n!==null&&n.memoizedState.isDehydrated)try{Wn(t.containerInfo)}catch(x){O(e,e.return,x)}break;case 4:Te(t,e),Ie(e);break;case 13:Te(t,e),Ie(e),o=e.child,o.flags&8192&&(i=o.memoizedState!==null,o.stateNode.isHidden=i,!i||o.alternate!==null&&o.alternate.memoizedState!==null||(jl=j())),r&4&&Ss(e);break;case 22:if(p=n!==null&&n.memoizedState!==null,e.mode&1?(J=(d=J)||p,Te(t,e),J=d):Te(t,e),Ie(e),r&8192){if(d=e.memoizedState!==null,(e.stateNode.isHidden=d)&&!p&&(e.mode&1)!==0)for(k=e,p=e.child;p!==null;){for(h=k=p;k!==null;){switch(m=k,y=m.child,m.tag){case 0:case 11:case 14:case 15:Dn(4,m,m.return);break;case 1:Zt(m,m.return);var w=m.stateNode;if(typeof w.componentWillUnmount=="function"){r=m,n=m.return;try{t=r,w.props=t.memoizedProps,w.state=t.memoizedState,w.componentWillUnmount()}catch(x){O(r,n,x)}}break;case 5:Zt(m,m.return);break;case 22:if(m.memoizedState!==null){Ts(h);continue}}y!==null?(y.return=m,k=y):Ts(h)}p=p.sibling}e:for(p=null,h=e;;){if(h.tag===5){if(p===null){p=h;try{o=h.stateNode,d?(i=o.style,typeof i.setProperty=="function"?i.setProperty("display","none","important"):i.display="none"):(a=h.stateNode,s=h.memoizedProps.style,l=s!=null&&s.hasOwnProperty("display")?s.display:null,a.style.display=Bs("display",l))}catch(x){O(e,e.return,x)}}}else if(h.tag===6){if(p===null)try{h.stateNode.nodeValue=d?"":h.memoizedProps}catch(x){O(e,e.return,x)}}else if((h.tag!==22&&h.tag!==23||h.memoizedState===null||h===e)&&h.child!==null){h.child.return=h,h=h.child;continue}if(h===e)break e;for(;h.sibling===null;){if(h.return===null||h.return===e)break e;p===h&&(p=null),h=h.return}p===h&&(p=null),h.sibling.return=h.return,h=h.sibling}}break;case 19:Te(t,e),Ie(e),r&4&&Ss(e);break;case 21:break;default:Te(t,e),Ie(e)}}function Ie(e){var t=e.flags;if(t&2){try{e:{for(var n=e.return;n!==null;){if(pc(n)){var r=n;break e}n=n.return}throw Error(v(160))}switch(r.tag){case 5:var o=r.stateNode;r.flags&32&&(On(o,""),r.flags&=-33);var i=_s(e);el(e,i,o);break;case 3:case 4:var l=r.stateNode.containerInfo,a=_s(e);Ji(e,a,l);break;default:throw Error(v(161))}}catch(s){O(e,e.return,s)}e.flags&=-3}t&4096&&(e.flags&=-4097)}function q0(e,t,n){k=e,gc(e,t,n)}function gc(e,t,n){for(var r=(e.mode&1)!==0;k!==null;){var o=k,i=o.child;if(o.tag===22&&r){var l=o.memoizedState!==null||Mr;if(!l){var a=o.alternate,s=a!==null&&a.memoizedState!==null||J;a=Mr;var d=J;if(Mr=l,(J=s)&&!d)for(k=o;k!==null;)l=k,s=l.child,l.tag===22&&l.memoizedState!==null?Cs(o):s!==null?(s.return=l,k=s):Cs(o);for(;i!==null;)k=i,gc(i,t,n),i=i.sibling;k=o,Mr=a,J=d}Es(e,t,n)}else(o.subtreeFlags&8772)!==0&&i!==null?(i.return=o,k=i):Es(e,t,n)}}function Es(e){for(;k!==null;){var t=k;if((t.flags&8772)!==0){var n=t.alternate;try{if((t.flags&8772)!==0)switch(t.tag){case 0:case 11:case 15:J||_o(5,t);break;case 1:var r=t.stateNode;if(t.flags&4&&!J)if(n===null)r.componentDidMount();else{var o=t.elementType===t.type?n.memoizedProps:Ce(t.type,n.memoizedProps);r.componentDidUpdate(o,n.memoizedState,r.__reactInternalSnapshotBeforeUpdate)}var i=t.updateQueue;i!==null&&ss(t,i,r);break;case 3:var l=t.updateQueue;if(l!==null){if(n=null,t.child!==null)switch(t.child.tag){case 5:n=t.child.stateNode;break;case 1:n=t.child.stateNode}ss(t,l,n)}break;case 5:var a=t.stateNode;if(n===null&&t.flags&4){n=a;var s=t.memoizedProps;switch(t.type){case"button":case"input":case"select":case"textarea":s.autoFocus&&n.focus();break;case"img":s.src&&(n.src=s.src)}}break;case 6:break;case 4:break;case 12:break;case 13:if(t.memoizedState===null){var d=t.alternate;if(d!==null){var p=d.memoizedState;if(p!==null){var h=p.dehydrated;h!==null&&Wn(h)}}}break;case 19:case 17:case 21:case 22:case 23:case 25:break;default:throw Error(v(163))}J||t.flags&512&&Ki(t)}catch(m){O(t,t.return,m)}}if(t===e){k=null;break}if(n=t.sibling,n!==null){n.return=t.return,k=n;break}k=t.return}}function Ts(e){for(;k!==null;){var t=k;if(t===e){k=null;break}var n=t.sibling;if(n!==null){n.return=t.return,k=n;break}k=t.return}}function Cs(e){for(;k!==null;){var t=k;try{switch(t.tag){case 0:case 11:case 15:var n=t.return;try{_o(4,t)}catch(s){O(t,n,s)}break;case 1:var r=t.stateNode;if(typeof r.componentDidMount=="function"){var o=t.return;try{r.componentDidMount()}catch(s){O(t,o,s)}}var i=t.return;try{Ki(t)}catch(s){O(t,i,s)}break;case 5:var l=t.return;try{Ki(t)}catch(s){O(t,l,s)}}}catch(s){O(t,t.return,s)}if(t===e){k=null;break}var a=t.sibling;if(a!==null){a.return=t.return,k=a;break}k=t.return}}var Z0=Math.ceil,so=qe.ReactCurrentDispatcher,Ul=qe.ReactCurrentOwner,ke=qe.ReactCurrentBatchConfig,P=0,Q=null,B=null,q=0,ce=0,Xt=vt(0),W=0,er=null,Rt=0,So=0,Ol=0,Fn=null,ie=null,jl=0,cn=1/0,Oe=null,uo=!1,tl=null,dt=null,Lr=!1,it=null,co=0,An=0,nl=null,jr=-1,Br=0;function re(){return(P&6)!==0?j():jr!==-1?jr:jr=j()}function ft(e){return(e.mode&1)===0?1:(P&2)!==0&&q!==0?q&-q:L0.transition!==null?(Br===0&&(Br=eu()),Br):(e=N,e!==0||(e=window.event,e=e===void 0?16:au(e.type)),e)}function Re(e,t,n,r){if(50<An)throw An=0,nl=null,Error(v(185));tr(e,n,r),((P&2)===0||e!==Q)&&(e===Q&&((P&2)===0&&(So|=n),W===4&&rt(e,q)),ue(e,r),n===1&&P===0&&(t.mode&1)===0&&(cn=j()+500,xo&&yt()))}function ue(e,t){var n=e.callbackNode;bd(e,t);var r=Gr(e,e===Q?q:0);if(r===0)n!==null&&ba(n),e.callbackNode=null,e.callbackPriority=0;else if(t=r&-r,e.callbackPriority!==t){if(n!=null&&ba(n),t===1)e.tag===0?M0(Ps.bind(null,e)):Cu(Ps.bind(null,e)),P0(function(){(P&6)===0&&yt()}),n=null;else{switch(tu(r)){case 1:n=fl;break;case 4:n=Ks;break;case 16:n=Qr;break;case 536870912:n=Js;break;default:n=Qr}n=Ec(n,vc.bind(null,e))}e.callbackPriority=t,e.callbackNode=n}}function vc(e,t){if(jr=-1,Br=0,(P&6)!==0)throw Error(v(327));var n=e.callbackNode;if(nn()&&e.callbackNode!==n)return null;var r=Gr(e,e===Q?q:0);if(r===0)return null;if((r&30)!==0||(r&e.expiredLanes)!==0||t)t=fo(e,r);else{t=r;var o=P;P|=2;var i=xc();(Q!==e||q!==t)&&(Oe=null,cn=j()+500,Tt(e,t));do try{K0();break}catch(a){yc(e,a)}while(!0);Tl(),so.current=i,P=o,B!==null?t=0:(Q=null,q=0,t=W)}if(t!==0){if(t===2&&(o=Ni(e),o!==0&&(r=o,t=rl(e,o))),t===1)throw n=er,Tt(e,0),rt(e,r),ue(e,j()),n;if(t===6)rt(e,r);else{if(o=e.current.alternate,(r&30)===0&&!X0(o)&&(t=fo(e,r),t===2&&(i=Ni(e),i!==0&&(r=i,t=rl(e,i))),t===1))throw n=er,Tt(e,0),rt(e,r),ue(e,j()),n;switch(e.finishedWork=o,e.finishedLanes=r,t){case 0:case 1:throw Error(v(345));case 2:kt(e,ie,Oe);break;case 3:if(rt(e,r),(r&130023424)===r&&(t=jl+500-j(),10<t)){if(Gr(e,0)!==0)break;if(o=e.suspendedLanes,(o&r)!==r){re(),e.pingedLanes|=e.suspendedLanes&o;break}e.timeoutHandle=Ai(kt.bind(null,e,ie,Oe),t);break}kt(e,ie,Oe);break;case 4:if(rt(e,r),(r&4194240)===r)break;for(t=e.eventTimes,o=-1;0<r;){var l=31-Ne(r);i=1<<l,l=t[l],l>o&&(o=l),r&=~i}if(r=o,r=j()-r,r=(120>r?120:480>r?480:1080>r?1080:1920>r?1920:3e3>r?3e3:4320>r?4320:1960*Z0(r/1960))-r,10<r){e.timeoutHandle=Ai(kt.bind(null,e,ie,Oe),r);break}kt(e,ie,Oe);break;case 5:kt(e,ie,Oe);break;default:throw Error(v(329))}}}return ue(e,j()),e.callbackNode===n?vc.bind(null,e):null}function rl(e,t){var n=Fn;return e.current.memoizedState.isDehydrated&&(Tt(e,t).flags|=256),e=fo(e,t),e!==2&&(t=ie,ie=n,t!==null&&ol(t)),e}function ol(e){ie===null?ie=e:ie.push.apply(ie,e)}function X0(e){for(var t=e;;){if(t.flags&16384){var n=t.updateQueue;if(n!==null&&(n=n.stores,n!==null))for(var r=0;r<n.length;r++){var o=n[r],i=o.getSnapshot;o=o.value;try{if(!Me(i(),o))return!1}catch{return!1}}}if(n=t.child,t.subtreeFlags&16384&&n!==null)n.return=t,t=n;else{if(t===e)break;for(;t.sibling===null;){if(t.return===null||t.return===e)return!0;t=t.return}t.sibling.return=t.return,t=t.sibling}}return!0}function rt(e,t){for(t&=~Ol,t&=~So,e.suspendedLanes|=t,e.pingedLanes&=~t,e=e.expirationTimes;0<t;){var n=31-Ne(t),r=1<<n;e[n]=-1,t&=~r}}function Ps(e){if((P&6)!==0)throw Error(v(327));nn();var t=Gr(e,0);if((t&1)===0)return ue(e,j()),null;var n=fo(e,t);if(e.tag!==0&&n===2){var r=Ni(e);r!==0&&(t=r,n=rl(e,r))}if(n===1)throw n=er,Tt(e,0),rt(e,t),ue(e,j()),n;if(n===6)throw Error(v(345));return e.finishedWork=e.current.alternate,e.finishedLanes=t,kt(e,ie,Oe),ue(e,j()),null}function Bl(e,t){var n=P;P|=1;try{return e(t)}finally{P=n,P===0&&(cn=j()+500,xo&&yt())}}function Mt(e){it!==null&&it.tag===0&&(P&6)===0&&nn();var t=P;P|=1;var n=ke.transition,r=N;try{if(ke.transition=null,N=1,e)return e()}finally{N=r,ke.transition=n,P=t,(P&6)===0&&yt()}}function Vl(){ce=Xt.current,I(Xt)}function Tt(e,t){e.finishedWork=null,e.finishedLanes=0;var n=e.timeoutHandle;if(n!==-1&&(e.timeoutHandle=-1,C0(n)),B!==null)for(n=B.return;n!==null;){var r=n;switch(_l(r),r.tag){case 1:r=r.type.childContextTypes,r!=null&&Kr();break;case 3:sn(),I(ae),I(ee),Ml();break;case 5:Rl(r);break;case 4:sn();break;case 13:I(F);break;case 19:I(F);break;case 10:Cl(r.type._context);break;case 22:case 23:Vl()}n=n.return}if(Q=e,B=e=pt(e.current,null),q=ce=t,W=0,er=null,Ol=So=Rt=0,ie=Fn=null,St!==null){for(t=0;t<St.length;t++)if(n=St[t],r=n.interleaved,r!==null){n.interleaved=null;var o=r.next,i=n.pending;if(i!==null){var l=i.next;i.next=o,r.next=l}n.pending=r}St=null}return e}function yc(e,t){do{var n=B;try{if(Tl(),Ar.current=ao,lo){for(var r=A.memoizedState;r!==null;){var o=r.queue;o!==null&&(o.pending=null),r=r.next}lo=!1}if(Nt=0,$=V=A=null,bn=!1,Yn=0,Ul.current=null,n===null||n.return===null){W=1,er=t,B=null;break}e:{var i=e,l=n.return,a=n,s=t;if(t=q,a.flags|=32768,s!==null&&typeof s=="object"&&typeof s.then=="function"){var d=s,p=a,h=p.tag;if((p.mode&1)===0&&(h===0||h===11||h===15)){var m=p.alternate;m?(p.updateQueue=m.updateQueue,p.memoizedState=m.memoizedState,p.lanes=m.lanes):(p.updateQueue=null,p.memoizedState=null)}var y=ms(l);if(y!==null){y.flags&=-257,hs(y,l,a,i,t),y.mode&1&&ps(i,d,t),t=y,s=d;var w=t.updateQueue;if(w===null){var x=new Set;x.add(s),t.updateQueue=x}else w.add(s);break e}else{if((t&1)===0){ps(i,d,t),Wl();break e}s=Error(v(426))}}else if(D&&a.mode&1){var b=ms(l);if(b!==null){(b.flags&65536)===0&&(b.flags|=256),hs(b,l,a,i,t),Sl(un(s,a));break e}}i=s=un(s,a),W!==4&&(W=2),Fn===null?Fn=[i]:Fn.push(i),i=l;do{switch(i.tag){case 3:i.flags|=65536,t&=-t,i.lanes|=t;var c=tc(i,s,t);as(i,c);break e;case 1:a=s;var u=i.type,f=i.stateNode;if((i.flags&128)===0&&(typeof u.getDerivedStateFromError=="function"||f!==null&&typeof f.componentDidCatch=="function"&&(dt===null||!dt.has(f)))){i.flags|=65536,t&=-t,i.lanes|=t;var g=nc(i,a,t);as(i,g);break e}}i=i.return}while(i!==null)}kc(n)}catch(_){t=_,B===n&&n!==null&&(B=n=n.return);continue}break}while(!0)}function xc(){var e=so.current;return so.current=ao,e===null?ao:e}function Wl(){(W===0||W===3||W===2)&&(W=4),Q===null||(Rt&268435455)===0&&(So&268435455)===0||rt(Q,q)}function fo(e,t){var n=P;P|=2;var r=xc();(Q!==e||q!==t)&&(Oe=null,Tt(e,t));do try{Y0();break}catch(o){yc(e,o)}while(!0);if(Tl(),P=n,so.current=r,B!==null)throw Error(v(261));return Q=null,q=0,W}function Y0(){for(;B!==null;)wc(B)}function K0(){for(;B!==null&&!Td();)wc(B)}function wc(e){var t=Sc(e.alternate,e,ce);e.memoizedProps=e.pendingProps,t===null?kc(e):B=t,Ul.current=null}function kc(e){var t=e;do{var n=t.alternate;if(e=t.return,(t.flags&32768)===0){if(n=H0(n,t,ce),n!==null){B=n;return}}else{if(n=$0(n,t),n!==null){n.flags&=32767,B=n;return}if(e!==null)e.flags|=32768,e.subtreeFlags=0,e.deletions=null;else{W=6,B=null;return}}if(t=t.sibling,t!==null){B=t;return}B=t=e}while(t!==null);W===0&&(W=5)}function kt(e,t,n){var r=N,o=ke.transition;try{ke.transition=null,N=1,J0(e,t,n,r)}finally{ke.transition=o,N=r}return null}function J0(e,t,n,r){do nn();while(it!==null);if((P&6)!==0)throw Error(v(327));n=e.finishedWork;var o=e.finishedLanes;if(n===null)return null;if(e.finishedWork=null,e.finishedLanes=0,n===e.current)throw Error(v(177));e.callbackNode=null,e.callbackPriority=0;var i=n.lanes|n.childLanes;if(Dd(e,i),e===Q&&(B=Q=null,q=0),(n.subtreeFlags&2064)===0&&(n.flags&2064)===0||Lr||(Lr=!0,Ec(Qr,function(){return nn(),null})),i=(n.flags&15990)!==0,(n.subtreeFlags&15990)!==0||i){i=ke.transition,ke.transition=null;var l=N;N=1;var a=P;P|=4,Ul.current=null,G0(e,n),hc(n,e),k0(Di),qr=!!bi,Di=bi=null,e.current=n,q0(n,e,o),Cd(),P=a,N=l,ke.transition=i}else e.current=n;if(Lr&&(Lr=!1,it=e,co=o),i=e.pendingLanes,i===0&&(dt=null),Nd(n.stateNode,r),ue(e,j()),t!==null)for(r=e.onRecoverableError,n=0;n<t.length;n++)o=t[n],r(o.value,{componentStack:o.stack,digest:o.digest});if(uo)throw uo=!1,e=tl,tl=null,e;return(co&1)!==0&&e.tag!==0&&nn(),i=e.pendingLanes,(i&1)!==0?e===nl?An++:(An=0,nl=e):An=0,yt(),null}function nn(){if(it!==null){var e=tu(co),t=ke.transition,n=N;try{if(ke.transition=null,N=16>e?16:e,it===null)var r=!1;else{if(e=it,it=null,co=0,(P&6)!==0)throw Error(v(331));var o=P;for(P|=4,k=e.current;k!==null;){var i=k,l=i.child;if((k.flags&16)!==0){var a=i.deletions;if(a!==null){for(var s=0;s<a.length;s++){var d=a[s];for(k=d;k!==null;){var p=k;switch(p.tag){case 0:case 11:case 15:Dn(8,p,i)}var h=p.child;if(h!==null)h.return=p,k=h;else for(;k!==null;){p=k;var m=p.sibling,y=p.return;if(fc(p),p===d){k=null;break}if(m!==null){m.return=y,k=m;break}k=y}}}var w=i.alternate;if(w!==null){var x=w.child;if(x!==null){w.child=null;do{var b=x.sibling;x.sibling=null,x=b}while(x!==null)}}k=i}}if((i.subtreeFlags&2064)!==0&&l!==null)l.return=i,k=l;else e:for(;k!==null;){if(i=k,(i.flags&2048)!==0)switch(i.tag){case 0:case 11:case 15:Dn(9,i,i.return)}var c=i.sibling;if(c!==null){c.return=i.return,k=c;break e}k=i.return}}var u=e.current;for(k=u;k!==null;){l=k;var f=l.child;if((l.subtreeFlags&2064)!==0&&f!==null)f.return=l,k=f;else e:for(l=u;k!==null;){if(a=k,(a.flags&2048)!==0)try{switch(a.tag){case 0:case 11:case 15:_o(9,a)}}catch(_){O(a,a.return,_)}if(a===l){k=null;break e}var g=a.sibling;if(g!==null){g.return=a.return,k=g;break e}k=a.return}}if(P=o,yt(),Fe&&typeof Fe.onPostCommitFiberRoot=="function")try{Fe.onPostCommitFiberRoot(mo,e)}catch{}r=!0}return r}finally{N=n,ke.transition=t}}return!1}function zs(e,t,n){t=un(n,t),t=tc(e,t,1),e=ct(e,t,1),t=re(),e!==null&&(tr(e,1,t),ue(e,t))}function O(e,t,n){if(e.tag===3)zs(e,e,n);else for(;t!==null;){if(t.tag===3){zs(t,e,n);break}else if(t.tag===1){var r=t.stateNode;if(typeof t.type.getDerivedStateFromError=="function"||typeof r.componentDidCatch=="function"&&(dt===null||!dt.has(r))){e=un(n,e),e=nc(t,e,1),t=ct(t,e,1),e=re(),t!==null&&(tr(t,1,e),ue(t,e));break}}t=t.return}}function ef(e,t,n){var r=e.pingCache;r!==null&&r.delete(t),t=re(),e.pingedLanes|=e.suspendedLanes&n,Q===e&&(q&n)===n&&(W===4||W===3&&(q&130023424)===q&&500>j()-jl?Tt(e,0):Ol|=n),ue(e,t)}function _c(e,t){t===0&&((e.mode&1)===0?t=1:(t=yr,yr<<=1,(yr&130023424)===0&&(yr=4194304)));var n=re();e=Qe(e,t),e!==null&&(tr(e,t,n),ue(e,n))}function tf(e){var t=e.memoizedState,n=0;t!==null&&(n=t.retryLane),_c(e,n)}function nf(e,t){var n=0;switch(e.tag){case 13:var r=e.stateNode,o=e.memoizedState;o!==null&&(n=o.retryLane);break;case 19:r=e.stateNode;break;default:throw Error(v(314))}r!==null&&r.delete(t),_c(e,n)}var Sc;Sc=function(e,t,n){if(e!==null)if(e.memoizedProps!==t.pendingProps||ae.current)le=!0;else{if((e.lanes&n)===0&&(t.flags&128)===0)return le=!1,W0(e,t,n);le=(e.flags&131072)!==0}else le=!1,D&&(t.flags&1048576)!==0&&Pu(t,to,t.index);switch(t.lanes=0,t.tag){case 2:var r=t.type;Or(e,t),e=t.pendingProps;var o=on(t,ee.current);tn(t,n),o=Il(null,t,r,e,o,n);var i=bl();return t.flags|=1,typeof o=="object"&&o!==null&&typeof o.render=="function"&&o.$$typeof===void 0?(t.tag=1,t.memoizedState=null,t.updateQueue=null,se(r)?(i=!0,Jr(t)):i=!1,t.memoizedState=o.state!==null&&o.state!==void 0?o.state:null,zl(t),o.updater=ko,t.stateNode=o,o._reactInternals=t,Hi(t,r,e,n),t=Gi(null,t,r,!0,i,n)):(t.tag=0,D&&i&&kl(t),ne(null,t,o,n),t=t.child),t;case 16:r=t.elementType;e:{switch(Or(e,t),e=t.pendingProps,o=r._init,r=o(r._payload),t.type=r,o=t.tag=of(r),e=Ce(r,e),o){case 0:t=Qi(null,t,r,e,n);break e;case 1:t=ys(null,t,r,e,n);break e;case 11:t=gs(null,t,r,e,n);break e;case 14:t=vs(null,t,r,Ce(r.type,e),n);break e}throw Error(v(306,r,""))}return t;case 0:return r=t.type,o=t.pendingProps,o=t.elementType===r?o:Ce(r,o),Qi(e,t,r,o,n);case 1:return r=t.type,o=t.pendingProps,o=t.elementType===r?o:Ce(r,o),ys(e,t,r,o,n);case 3:e:{if(lc(t),e===null)throw Error(v(387));r=t.pendingProps,i=t.memoizedState,o=i.element,Iu(e,t),oo(t,r,null,n);var l=t.memoizedState;if(r=l.element,i.isDehydrated)if(i={element:r,isDehydrated:!1,cache:l.cache,pendingSuspenseBoundaries:l.pendingSuspenseBoundaries,transitions:l.transitions},t.updateQueue.baseState=i,t.memoizedState=i,t.flags&256){o=un(Error(v(423)),t),t=xs(e,t,r,n,o);break e}else if(r!==o){o=un(Error(v(424)),t),t=xs(e,t,r,n,o);break e}else for(de=ut(t.stateNode.containerInfo.firstChild),fe=t,D=!0,ze=null,n=Mu(t,null,r,n),t.child=n;n;)n.flags=n.flags&-3|4096,n=n.sibling;else{if(ln(),r===o){t=Ge(e,t,n);break e}ne(e,t,r,n)}t=t.child}return t;case 5:return bu(t),e===null&&Bi(t),r=t.type,o=t.pendingProps,i=e!==null?e.memoizedProps:null,l=o.children,Fi(r,o)?l=null:i!==null&&Fi(r,i)&&(t.flags|=32),ic(e,t),ne(e,t,l,n),t.child;case 6:return e===null&&Bi(t),null;case 13:return ac(e,t,n);case 4:return Nl(t,t.stateNode.containerInfo),r=t.pendingProps,e===null?t.child=an(t,null,r,n):ne(e,t,r,n),t.child;case 11:return r=t.type,o=t.pendingProps,o=t.elementType===r?o:Ce(r,o),gs(e,t,r,o,n);case 7:return ne(e,t,t.pendingProps,n),t.child;case 8:return ne(e,t,t.pendingProps.children,n),t.child;case 12:return ne(e,t,t.pendingProps.children,n),t.child;case 10:e:{if(r=t.type._context,o=t.pendingProps,i=t.memoizedProps,l=o.value,M(no,r._currentValue),r._currentValue=l,i!==null)if(Me(i.value,l)){if(i.children===o.children&&!ae.current){t=Ge(e,t,n);break e}}else for(i=t.child,i!==null&&(i.return=t);i!==null;){var a=i.dependencies;if(a!==null){l=i.child;for(var s=a.firstContext;s!==null;){if(s.context===r){if(i.tag===1){s=We(-1,n&-n),s.tag=2;var d=i.updateQueue;if(d!==null){d=d.shared;var p=d.pending;p===null?s.next=s:(s.next=p.next,p.next=s),d.pending=s}}i.lanes|=n,s=i.alternate,s!==null&&(s.lanes|=n),Vi(i.return,n,t),a.lanes|=n;break}s=s.next}}else if(i.tag===10)l=i.type===t.type?null:i.child;else if(i.tag===18){if(l=i.return,l===null)throw Error(v(341));l.lanes|=n,a=l.alternate,a!==null&&(a.lanes|=n),Vi(l,n,t),l=i.sibling}else l=i.child;if(l!==null)l.return=i;else for(l=i;l!==null;){if(l===t){l=null;break}if(i=l.sibling,i!==null){i.return=l.return,l=i;break}l=l.return}i=l}ne(e,t,o.children,n),t=t.child}return t;case 9:return o=t.type,r=t.pendingProps.children,tn(t,n),o=_e(o),r=r(o),t.flags|=1,ne(e,t,r,n),t.child;case 14:return r=t.type,o=Ce(r,t.pendingProps),o=Ce(r.type,o),vs(e,t,r,o,n);case 15:return rc(e,t,t.type,t.pendingProps,n);case 17:return r=t.type,o=t.pendingProps,o=t.elementType===r?o:Ce(r,o),Or(e,t),t.tag=1,se(r)?(e=!0,Jr(t)):e=!1,tn(t,n),ec(t,r,o),Hi(t,r,o,n),Gi(null,t,r,!0,e,n);case 19:return sc(e,t,n);case 22:return oc(e,t,n)}throw Error(v(156,t.tag))};function Ec(e,t){return Ys(e,t)}function rf(e,t,n,r){this.tag=e,this.key=n,this.sibling=this.child=this.return=this.stateNode=this.type=this.elementType=null,this.index=0,this.ref=null,this.pendingProps=t,this.dependencies=this.memoizedState=this.updateQueue=this.memoizedProps=null,this.mode=r,this.subtreeFlags=this.flags=0,this.deletions=null,this.childLanes=this.lanes=0,this.alternate=null}function we(e,t,n,r){return new rf(e,t,n,r)}function Hl(e){return e=e.prototype,!(!e||!e.isReactComponent)}function of(e){if(typeof e=="function")return Hl(e)?1:0;if(e!=null){if(e=e.$$typeof,e===ul)return 11;if(e===cl)return 14}return 2}function pt(e,t){var n=e.alternate;return n===null?(n=we(e.tag,t,e.key,e.mode),n.elementType=e.elementType,n.type=e.type,n.stateNode=e.stateNode,n.alternate=e,e.alternate=n):(n.pendingProps=t,n.type=e.type,n.flags=0,n.subtreeFlags=0,n.deletions=null),n.flags=e.flags&14680064,n.childLanes=e.childLanes,n.lanes=e.lanes,n.child=e.child,n.memoizedProps=e.memoizedProps,n.memoizedState=e.memoizedState,n.updateQueue=e.updateQueue,t=e.dependencies,n.dependencies=t===null?null:{lanes:t.lanes,firstContext:t.firstContext},n.sibling=e.sibling,n.index=e.index,n.ref=e.ref,n}function Vr(e,t,n,r,o,i){var l=2;if(r=e,typeof e=="function")Hl(e)&&(l=1);else if(typeof e=="string")l=5;else e:switch(e){case jt:return Ct(n.children,o,i,t);case sl:l=8,o|=8;break;case mi:return e=we(12,n,t,o|2),e.elementType=mi,e.lanes=i,e;case hi:return e=we(13,n,t,o),e.elementType=hi,e.lanes=i,e;case gi:return e=we(19,n,t,o),e.elementType=gi,e.lanes=i,e;case bs:return Eo(n,o,i,t);default:if(typeof e=="object"&&e!==null)switch(e.$$typeof){case Ls:l=10;break e;case Is:l=9;break e;case ul:l=11;break e;case cl:l=14;break e;case et:l=16,r=null;break e}throw Error(v(130,e==null?e:typeof e,""))}return t=we(l,n,t,o),t.elementType=e,t.type=r,t.lanes=i,t}function Ct(e,t,n,r){return e=we(7,e,r,t),e.lanes=n,e}function Eo(e,t,n,r){return e=we(22,e,r,t),e.elementType=bs,e.lanes=n,e.stateNode={isHidden:!1},e}function di(e,t,n){return e=we(6,e,null,t),e.lanes=n,e}function fi(e,t,n){return t=we(4,e.children!==null?e.children:[],e.key,t),t.lanes=n,t.stateNode={containerInfo:e.containerInfo,pendingChildren:null,implementation:e.implementation},t}function lf(e,t,n,r,o){this.tag=t,this.containerInfo=e,this.finishedWork=this.pingCache=this.current=this.pendingChildren=null,this.timeoutHandle=-1,this.callbackNode=this.pendingContext=this.context=null,this.callbackPriority=0,this.eventTimes=Zo(0),this.expirationTimes=Zo(-1),this.entangledLanes=this.finishedLanes=this.mutableReadLanes=this.expiredLanes=this.pingedLanes=this.suspendedLanes=this.pendingLanes=0,this.entanglements=Zo(0),this.identifierPrefix=r,this.onRecoverableError=o,this.mutableSourceEagerHydrationData=null}function $l(e,t,n,r,o,i,l,a,s){return e=new lf(e,t,n,a,s),t===1?(t=1,i===!0&&(t|=8)):t=0,i=we(3,null,null,t),e.current=i,i.stateNode=e,i.memoizedState={element:r,isDehydrated:n,cache:null,transitions:null,pendingSuspenseBoundaries:null},zl(i),e}function af(e,t,n){var r=3<arguments.length&&arguments[3]!==void 0?arguments[3]:null;return{$$typeof:Ot,key:r==null?null:""+r,children:e,containerInfo:t,implementation:n}}function Tc(e){if(!e)return ht;e=e._reactInternals;e:{if(It(e)!==e||e.tag!==1)throw Error(v(170));var t=e;do{switch(t.tag){case 3:t=t.stateNode.context;break e;case 1:if(se(t.type)){t=t.stateNode.__reactInternalMemoizedMergedChildContext;break e}}t=t.return}while(t!==null);throw Error(v(171))}if(e.tag===1){var n=e.type;if(se(n))return Tu(e,n,t)}return t}function Cc(e,t,n,r,o,i,l,a,s){return e=$l(n,r,!0,e,o,i,l,a,s),e.context=Tc(null),n=e.current,r=re(),o=ft(n),i=We(r,o),i.callback=t??null,ct(n,i,o),e.current.lanes=o,tr(e,o,r),ue(e,r),e}function To(e,t,n,r){var o=t.current,i=re(),l=ft(o);return n=Tc(n),t.context===null?t.context=n:t.pendingContext=n,t=We(i,l),t.payload={element:e},r=r===void 0?null:r,r!==null&&(t.callback=r),e=ct(o,t,l),e!==null&&(Re(e,o,l,i),Fr(e,o,l)),l}function po(e){if(e=e.current,!e.child)return null;switch(e.child.tag){case 5:return e.child.stateNode;default:return e.child.stateNode}}function Ns(e,t){if(e=e.memoizedState,e!==null&&e.dehydrated!==null){var n=e.retryLane;e.retryLane=n!==0&&n<t?n:t}}function Ql(e,t){Ns(e,t),(e=e.alternate)&&Ns(e,t)}function sf(){return null}var Pc=typeof reportError=="function"?reportError:function(e){console.error(e)};function Gl(e){this._internalRoot=e}Co.prototype.render=Gl.prototype.render=function(e){var t=this._internalRoot;if(t===null)throw Error(v(409));To(e,t,null,null)};Co.prototype.unmount=Gl.prototype.unmount=function(){var e=this._internalRoot;if(e!==null){this._internalRoot=null;var t=e.containerInfo;Mt(function(){To(null,e,null,null)}),t[$e]=null}};function Co(e){this._internalRoot=e}Co.prototype.unstable_scheduleHydration=function(e){if(e){var t=ou();e={blockedOn:null,target:e,priority:t};for(var n=0;n<nt.length&&t!==0&&t<nt[n].priority;n++);nt.splice(n,0,e),n===0&&lu(e)}};function ql(e){return!(!e||e.nodeType!==1&&e.nodeType!==9&&e.nodeType!==11)}function Po(e){return!(!e||e.nodeType!==1&&e.nodeType!==9&&e.nodeType!==11&&(e.nodeType!==8||e.nodeValue!==" react-mount-point-unstable "))}function Rs(){}function uf(e,t,n,r,o){if(o){if(typeof r=="function"){var i=r;r=function(){var d=po(l);i.call(d)}}var l=Cc(t,r,e,0,null,!1,!1,"",Rs);return e._reactRootContainer=l,e[$e]=l.current,Qn(e.nodeType===8?e.parentNode:e),Mt(),l}for(;o=e.lastChild;)e.removeChild(o);if(typeof r=="function"){var a=r;r=function(){var d=po(s);a.call(d)}}var s=$l(e,0,!1,null,null,!1,!1,"",Rs);return e._reactRootContainer=s,e[$e]=s.current,Qn(e.nodeType===8?e.parentNode:e),Mt(function(){To(t,s,n,r)}),s}function zo(e,t,n,r,o){var i=n._reactRootContainer;if(i){var l=i;if(typeof o=="function"){var a=o;o=function(){var s=po(l);a.call(s)}}To(t,l,e,o)}else l=uf(n,t,e,o,r);return po(l)}nu=function(e){switch(e.tag){case 3:var t=e.stateNode;if(t.current.memoizedState.isDehydrated){var n=Pn(t.pendingLanes);n!==0&&(pl(t,n|1),ue(t,j()),(P&6)===0&&(cn=j()+500,yt()))}break;case 13:Mt(function(){var r=Qe(e,1);if(r!==null){var o=re();Re(r,e,1,o)}}),Ql(e,1)}};ml=function(e){if(e.tag===13){var t=Qe(e,134217728);if(t!==null){var n=re();Re(t,e,134217728,n)}Ql(e,134217728)}};ru=function(e){if(e.tag===13){var t=ft(e),n=Qe(e,t);if(n!==null){var r=re();Re(n,e,t,r)}Ql(e,t)}};ou=function(){return N};iu=function(e,t){var n=N;try{return N=e,t()}finally{N=n}};Ci=function(e,t,n){switch(t){case"input":if(xi(e,n),t=n.name,n.type==="radio"&&t!=null){for(n=e;n.parentNode;)n=n.parentNode;for(n=n.querySelectorAll("input[name="+JSON.stringify(""+t)+'][type="radio"]'),t=0;t<n.length;t++){var r=n[t];if(r!==e&&r.form===e.form){var o=yo(r);if(!o)throw Error(v(90));Fs(r),xi(r,o)}}}break;case"textarea":Us(e,n);break;case"select":t=n.value,t!=null&&Yt(e,!!n.multiple,t,!1)}};$s=Bl;Qs=Mt;var cf={usingClientEntryPoint:!1,Events:[rr,Ht,yo,Ws,Hs,Bl]},Sn={findFiberByHostInstance:_t,bundleType:0,version:"18.3.1",rendererPackageName:"react-dom"},df={bundleType:Sn.bundleType,version:Sn.version,rendererPackageName:Sn.rendererPackageName,rendererConfig:Sn.rendererConfig,overrideHookState:null,overrideHookStateDeletePath:null,overrideHookStateRenamePath:null,overrideProps:null,overridePropsDeletePath:null,overridePropsRenamePath:null,setErrorHandler:null,setSuspenseHandler:null,scheduleUpdate:null,currentDispatcherRef:qe.ReactCurrentDispatcher,findHostInstanceByFiber:function(e){return e=Zs(e),e===null?null:e.stateNode},findFiberByHostInstance:Sn.findFiberByHostInstance||sf,findHostInstancesForRefresh:null,scheduleRefresh:null,scheduleRoot:null,setRefreshHandler:null,getCurrentFiber:null,reconcilerVersion:"18.3.1-next-f1338f8080-20240426"};if(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__<"u"&&(En=__REACT_DEVTOOLS_GLOBAL_HOOK__,!En.isDisabled&&En.supportsFiber))try{mo=En.inject(df),Fe=En}catch{}var En;he.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED=cf;he.createPortal=function(e,t){var n=2<arguments.length&&arguments[2]!==void 0?arguments[2]:null;if(!ql(t))throw Error(v(200));return af(e,t,null,n)};he.createRoot=function(e,t){if(!ql(e))throw Error(v(299));var n=!1,r="",o=Pc;return t!=null&&(t.unstable_strictMode===!0&&(n=!0),t.identifierPrefix!==void 0&&(r=t.identifierPrefix),t.onRecoverableError!==void 0&&(o=t.onRecoverableError)),t=$l(e,1,!1,null,null,n,!1,r,o),e[$e]=t.current,Qn(e.nodeType===8?e.parentNode:e),new Gl(t)};he.findDOMNode=function(e){if(e==null)return null;if(e.nodeType===1)return e;var t=e._reactInternals;if(t===void 0)throw typeof e.render=="function"?Error(v(188)):(e=Object.keys(e).join(","),Error(v(268,e)));return e=Zs(t),e=e===null?null:e.stateNode,e};he.flushSync=function(e){return Mt(e)};he.hydrate=function(e,t,n){if(!Po(t))throw Error(v(200));return zo(null,e,t,!0,n)};he.hydrateRoot=function(e,t,n){if(!ql(e))throw Error(v(405));var r=n!=null&&n.hydratedSources||null,o=!1,i="",l=Pc;if(n!=null&&(n.unstable_strictMode===!0&&(o=!0),n.identifierPrefix!==void 0&&(i=n.identifierPrefix),n.onRecoverableError!==void 0&&(l=n.onRecoverableError)),t=Cc(t,null,e,1,n??null,o,!1,i,l),e[$e]=t.current,Qn(e),r)for(e=0;e<r.length;e++)n=r[e],o=n._getVersion,o=o(n._source),t.mutableSourceEagerHydrationData==null?t.mutableSourceEagerHydrationData=[n,o]:t.mutableSourceEagerHydrationData.push(n,o);return new Co(t)};he.render=function(e,t,n){if(!Po(t))throw Error(v(200));return zo(null,e,t,!1,n)};he.unmountComponentAtNode=function(e){if(!Po(e))throw Error(v(40));return e._reactRootContainer?(Mt(function(){zo(null,null,e,!1,function(){e._reactRootContainer=null,e[$e]=null})}),!0):!1};he.unstable_batchedUpdates=Bl;he.unstable_renderSubtreeIntoContainer=function(e,t,n,r){if(!Po(n))throw Error(v(200));if(e==null||e._reactInternals===void 0)throw Error(v(38));return zo(e,t,n,!1,r)};he.version="18.3.1-next-f1338f8080-20240426"});var Mc=Ue((bf,Rc)=>{"use strict";function Nc(){if(!(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__>"u"||typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE!="function"))try{__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(Nc)}catch(e){console.error(e)}}Nc(),Rc.exports=zc()});var Ic=Ue(Zl=>{"use strict";var Lc=Mc();Zl.createRoot=Lc.createRoot,Zl.hydrateRoot=Lc.hydrateRoot;var Df});var Fc=Ue(No=>{"use strict";var pf=sr(),mf=Symbol.for("react.element"),hf=Symbol.for("react.fragment"),gf=Object.prototype.hasOwnProperty,vf=pf.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,yf={key:!0,ref:!0,__self:!0,__source:!0};function Dc(e,t,n){var r,o={},i=null,l=null;n!==void 0&&(i=""+n),t.key!==void 0&&(i=""+t.key),t.ref!==void 0&&(l=t.ref);for(r in t)gf.call(t,r)&&!yf.hasOwnProperty(r)&&(o[r]=t[r]);if(e&&e.defaultProps)for(r in t=e.defaultProps,t)o[r]===void 0&&(o[r]=t[r]);return{$$typeof:mf,type:e,key:i,ref:l,props:o,_owner:vf.current}}No.Fragment=hf;No.jsx=Dc;No.jsxs=Dc});var bt=Ue((Of,Ac)=>{"use strict";Ac.exports=Fc()});var Oc=Ye(Ic(),1);var ge=Ye(sr(),1);var bc=`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Elemental Marks \u2014 \u6C34\u30FB\u96F7\u30FB\u708E</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #060708;
    --line: rgba(255,255,255,.07);
    --ink: #e8e4dc;
    --dim: rgba(232,228,220,.42);
    --faint: rgba(232,228,220,.22);
    --water: #6cd3ff;
    --bolt: #aab4ff;
    --fire: #ff9d6b;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    background: var(--bg);
    color: var(--ink);
    font-family: "JetBrains Mono", monospace;
    overflow: hidden;
  }
  header {
    position: fixed; inset: 0 0 auto 0; z-index: 10;
    display: flex; justify-content: space-between; align-items: baseline;
    padding: 18px 22px;
    pointer-events: none;
    mix-blend-mode: screen;
  }
  header .brand {
    font-family: "Inter", "Hiragino Sans", sans-serif; font-weight: 500;
    font-size: 15px; letter-spacing: normal; text-transform: uppercase;
  }
  header .brand em { font-style: normal; color: var(--dim); margin-left: .8em; letter-spacing: normal; }

  main { display: flex; height: 100dvh; }
  .panel {
    position: relative; flex: 1 1 0; min-width: 0;
    transition: flex .7s cubic-bezier(.22,1,.36,1);
    border-left: 1px solid var(--line);
    opacity: 0; transform: translateY(14px);
    animation: reveal 1.1s cubic-bezier(.22,1,.36,1) forwards;
  }
  .panel:first-child { border-left: 0; }
  .panel:nth-child(1) { animation-delay: .05s; }
  .panel:nth-child(2) { animation-delay: .18s; }
  .panel:nth-child(3) { animation-delay: .31s; }
  @keyframes reveal { to { opacity: 1; transform: none; } }
  @media (hover:hover) and (min-width: 761px) {
    .panel:hover { flex: 1.4 1 0; }
  }
  .panel canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }

  .info {
    position: absolute; left: 22px; bottom: 20px; z-index: 5;
    pointer-events: none;
  }
  .info .romaji {
    font-size: 10px; letter-spacing: normal; color: var(--faint);
    margin-bottom: 10px; text-transform: uppercase;
  }
  .info h2 {
    font-family: "Inter", "Hiragino Sans", sans-serif; font-weight: 500;
    font-size: clamp(20px, 2.2vw, 30px); letter-spacing: normal;
    color: var(--ink);
  }
  .info .tech {
    margin-top: 8px; font-size: 10px; letter-spacing: normal;
    color: var(--dim); max-width: 30ch; line-height: 1.7;
  }
  .kanji {
    position: absolute; top: 46px; right: 18px; z-index: 5;
    font-family: "Inter", "Hiragino Sans", "Yu Gothic", sans-serif; font-weight: 800;
    font-size: clamp(64px, 8vw, 120px); line-height: 1;
    color: transparent;
    -webkit-text-stroke: 1px var(--accent, rgba(255,255,255,.25));
    opacity: .55; pointer-events: none;
    transition: opacity .5s, color .5s;
  }
  .panel:hover .kanji { opacity: .95; color: var(--accent); -webkit-text-stroke: 0; text-shadow: 0 0 34px var(--accent); }
  .panel[data-fx="water"]     { --accent: var(--water); }
  .panel[data-fx="lightning"] { --accent: var(--bolt); }
  .panel[data-fx="fire"]      { --accent: var(--fire); }

  .hint {
    position: fixed; bottom: 18px; right: 22px;
    z-index: 10; font-size: 9px; letter-spacing: normal; color: var(--faint);
    text-transform: uppercase; pointer-events: none; white-space: nowrap;
    animation: pulse 4s ease-in-out infinite;
  }
  @keyframes pulse { 50% { opacity: .35; } }

  .fail {
    position: absolute; inset: 0; display: none; place-items: center;
    font-size: 11px; letter-spacing: normal; color: var(--dim); text-align: center;
  }

  @media (max-width: 760px) {
    body { overflow-y: auto; }
    main { flex-direction: column; height: auto; }
    .panel { height: 72dvh; border-left: 0; border-top: 1px solid var(--line); }
    .hint { display: none; }
  }
  @media (prefers-reduced-motion: reduce) {
    .panel { animation-duration: .01s; }
    .hint { animation: none; }
  }
</style>
</head>
<body>

<header>
  <div class="brand">Elemental Marks<em>\u6C34 \u96F7 \u708E</em></div>
</header>

<main>
  <section class="panel" data-fx="water">
    <canvas></canvas>
    <div class="kanji">\u6C34</div>
    <div class="info">
      <div class="romaji">Sui \u2014 Water</div>
      <h2>OpenAI</h2>
      <p class="tech">ping-pong wave equation \xB7 gradient refraction of the mark</p>
    </div>
    <div class="fail">WEBGL2 FLOAT BUFFERS UNAVAILABLE</div>
  </section>

  <section class="panel" data-fx="lightning">
    <canvas></canvas>
    <div class="kanji">\u96F7</div>
    <div class="info">
      <div class="romaji">Rai \u2014 Lightning</div>
      <h2>Anthropic</h2>
      <p class="tech">contour distance field \xB7 fBm zigzag arcs crawling the outline</p>
    </div>
    <div class="fail">WEBGL2 UNAVAILABLE</div>
  </section>

  <section class="panel" data-fx="fire">
    <canvas></canvas>
    <div class="kanji">\u708E</div>
    <div class="info">
      <div class="romaji">En \u2014 Flame</div>
      <h2>Claude</h2>
      <p class="tech">noise ribbons licking upward from the edge \xB7 rising embers</p>
    </div>
    <div class="fail">WEBGL2 UNAVAILABLE</div>
  </section>
</main>

<div class="hint">move \u2014 \u89E6\u308C\u3066\u307F\u3066 \u2014 press</div>

<script type="module">
'use strict';
const workspaceBrand = new Image();
workspaceBrand.src = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMjggMTI4Ij48ZGVmcz48bGluZWFyR3JhZGllbnQgaWQ9ImciIHgxPSIuMSIgeTE9IjAiIHgyPSIuOSIgeTI9IjEiIGdyYWRpZW50VW5pdHM9Im9iamVjdEJvdW5kaW5nQm94Ij48c3RvcCBzdG9wLWNvbG9yPSIjNGQ2OWY0Ii8+PHN0b3Agb2Zmc2V0PSIxIiBzdG9wLWNvbG9yPSIjNmZmMmViIi8+PC9saW5lYXJHcmFkaWVudD48L2RlZnM+PGVsbGlwc2UgY3g9IjY0IiBjeT0iNjQiIHJ4PSI0OSIgcnk9IjIzIiB0cmFuc2Zvcm09InJvdGF0ZSgtMzUgNjQgNjQpIiBmaWxsPSJub25lIiBzdHJva2U9InVybCgjZykiIHN0cm9rZS13aWR0aD0iOCIvPjxwYXRoIGQ9Ik0zOCAzMGMxMi0xMiAzNC0xMCA0NyA1czIxIDM4IDcgNTQiIGZpbGw9Im5vbmUiIHN0cm9rZT0iIzYyODVmZiIgc3Ryb2tlLXdpZHRoPSI3IiBzdHJva2UtbGluZWNhcD0icm91bmQiLz48cGF0aCBkPSJtNTMgNjMgOCA4IDE1LTE3IiBmaWxsPSJub25lIiBzdHJva2U9IiNlOGZjZmYiIHN0cm9rZS13aWR0aD0iOCIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+PGNpcmNsZSBjeD0iMTAxIiBjeT0iMzkiIHI9IjgiIGZpbGw9IiNhZGY4ZmYiLz48L3N2Zz4=";
await workspaceBrand.decode();

/* ---------------- logo paths (simple-icons, viewBox 0 0 24 24) ---------------- */
const LOGO_PATHS = {
  openai: "M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z",
  anthropic: "M17.3041 3.541h-3.6718l6.696 16.918H24Zm-10.6082 0L0 20.459h3.7442l1.3693-3.5527h7.0052l1.3693 3.5528h3.7442L10.5363 3.5409Zm-.3712 10.2232 2.2914-5.9456 2.2914 5.9456Z",
  claude: "m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z"
};

/* ---------------- rasterize -> SDF (chamfer) + edge point extraction ---------------- */
const SDF_SIZE = 512;
const SDF_SPREAD = 128;          // px each side of the edge
const D_RANGE = SDF_SPREAD * 2 / SDF_SIZE; // decoded sdf span in mask-uv units

function rasterizeLogo(pathStr) {
  const c = document.createElement('canvas');
  c.width = c.height = SDF_SIZE;
  const ctx = c.getContext('2d');
  if (pathStr === LOGO_PATHS.openai) {
    const box = SDF_SIZE * 0.60, off = (SDF_SIZE - box) / 2;
    ctx.drawImage(workspaceBrand, off, off, box, box);
    return ctx.getImageData(0, 0, SDF_SIZE, SDF_SIZE);
  }
  const box = SDF_SIZE * 0.60;
  const s = box / 24;
  const off = (SDF_SIZE - box) / 2;
  ctx.setTransform(s, 0, 0, s, off, off);
  ctx.fillStyle = '#fff';
  ctx.fill(new Path2D(pathStr));
  return ctx.getImageData(0, 0, SDF_SIZE, SDF_SIZE);
}

function chamfer(d, w, h) {
  const D1 = 1, D2 = Math.SQRT2;
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
    const i = y * w + x; let v = d[i];
    if (x > 0) v = Math.min(v, d[i - 1] + D1);
    if (y > 0) {
      v = Math.min(v, d[i - w] + D1);
      if (x > 0) v = Math.min(v, d[i - w - 1] + D2);
      if (x < w - 1) v = Math.min(v, d[i - w + 1] + D2);
    }
    d[i] = v;
  }
  for (let y = h - 1; y >= 0; y--) for (let x = w - 1; x >= 0; x--) {
    const i = y * w + x; let v = d[i];
    if (x < w - 1) v = Math.min(v, d[i + 1] + D1);
    if (y < h - 1) {
      v = Math.min(v, d[i + w] + D1);
      if (x < w - 1) v = Math.min(v, d[i + w + 1] + D2);
      if (x > 0) v = Math.min(v, d[i + w - 1] + D2);
    }
    d[i] = v;
  }
}

function buildSDF(img) {
  const n = SDF_SIZE * SDF_SIZE;
  const dOut = new Float32Array(n), dIn = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const inside = img.data[i * 4 + 3] > 127;
    dOut[i] = inside ? 0 : 1e9;
    dIn[i]  = inside ? 1e9 : 0;
  }
  chamfer(dOut, SDF_SIZE, SDF_SIZE);
  chamfer(dIn, SDF_SIZE, SDF_SIZE);
  const enc = new Uint8Array(n);
  for (let i = 0; i < n; i++) {
    const d = dOut[i] - dIn[i]; // + outside, - inside
    enc[i] = Math.max(0, Math.min(255, Math.round((0.5 + 0.5 * d / SDF_SPREAD) * 255)));
  }
  return enc;
}

/* contour pixels + outward normals, in y-up mask uv */
function edgePoints(img) {
  const S = SDF_SIZE, pts = [];
  const a = (x, y) => img.data[(y * S + x) * 4 + 3] > 127;
  for (let y = 1; y < S - 1; y++) {
    for (let x = 1; x < S - 1; x++) {
      if (!a(x, y)) continue;
      const l = a(x - 1, y), r = a(x + 1, y), u = a(x, y - 1), dn = a(x, y + 1);
      if (l && r && u && dn) continue;
      const gx = (r ? 1 : 0) - (l ? 1 : 0);
      const gy = (dn ? 1 : 0) - (u ? 1 : 0);
      let nx = -gx, ny = gy;                 // outward, y flipped to y-up
      const len = Math.hypot(nx, ny);
      if (!len) { nx = 0; ny = 1; } else { nx /= len; ny /= len; }
      pts.push((x + 0.5) / S, 1 - (y + 0.5) / S, nx, ny);
    }
  }
  return pts;
}

function makeParticleData(pts, count) {
  const data = new Float32Array(count * 5);
  const nPts = pts.length / 4;
  for (let i = 0; i < count; i++) {
    const j = (Math.random() * nPts) | 0;
    data[i * 5]     = pts[j * 4];
    data[i * 5 + 1] = pts[j * 4 + 1];
    data[i * 5 + 2] = pts[j * 4 + 2];
    data[i * 5 + 3] = pts[j * 4 + 3];
    data[i * 5 + 4] = Math.random() * 100 + i * 0.618;
  }
  return data;
}

/* ---------------- shaders ---------------- */
const VERT = \`#version 300 es
out vec2 vUv;
void main(){
  vec2 p = vec2(float((gl_VertexID << 1) & 2), float(gl_VertexID & 2));
  vUv = p;
  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
}\`;

const GLSL_COMMON = \`
precision highp float;
uniform sampler2D uSDF;
uniform float uTime;
uniform float uAspect;
uniform vec2  uScale;
uniform vec2  uShift;
uniform vec3  uPointer; // uv.xy, active
in vec2 vUv;
out vec4 frag;

float hash21(vec2 p){
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
float vnoise(vec2 p){
  vec2 i = floor(p), f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float a = hash21(i), b = hash21(i + vec2(1,0));
  float c = hash21(i + vec2(0,1)), d = hash21(i + vec2(1,1));
  return mix(mix(a,b,f.x), mix(c,d,f.x), f.y);
}
float fbm(vec2 p){
  float v = 0.0, a = 0.5;
  mat2 r = mat2(0.8, -0.6, 0.6, 0.8);
  for (int i = 0; i < 5; i++){ v += a * vnoise(p); p = r * p * 2.03; a *= 0.5; }
  return v;
}
/* signed distance in mask-uv units; extended analytically past the texture
   border so out-of-range samples keep growing instead of clamping (kills
   the rectangular clamp artifacts) */
float sdf(vec2 uv){
  vec2 m = 0.5 + (uv - 0.5 - uShift) * uScale;
  vec2 mc = clamp(m, 0.0, 1.0);
  float d = (texture(uSDF, vec2(mc.x, 1.0 - mc.y)).r - 0.5) * \${D_RANGE.toFixed(4)};
  return d + length(m - mc);
}
float edgeFade(vec2 uv){
  return smoothstep(0.0, 0.05, uv.x) * smoothstep(1.0, 0.95, uv.x)
       * smoothstep(0.0, 0.05, uv.y) * smoothstep(1.0, 0.95, uv.y);
}
\`;

/* water simulation step (ping-pong, r = h, g = h_prev) */
const FRAG_SIM = \`#version 300 es
precision highp float;
uniform sampler2D uState;
uniform vec2 uTexel;
uniform vec3 uDrop; // sim-uv.xy, strength
in vec2 vUv;
out vec4 frag;
void main(){
  vec2 s = texture(uState, vUv).rg;
  float l = texture(uState, vUv - vec2(uTexel.x, 0.0)).r;
  float r = texture(uState, vUv + vec2(uTexel.x, 0.0)).r;
  float u = texture(uState, vUv + vec2(0.0, uTexel.y)).r;
  float d = texture(uState, vUv - vec2(0.0, uTexel.y)).r;
  float next = (l + r + u + d) * 0.5 - s.g;
  next *= 0.984;
  if (uDrop.z != 0.0){
    float dd = distance(vUv, uDrop.xy);
    next += uDrop.z * exp(-dd * dd * 3800.0);
  }
  frag = vec4(next, s.r, 0.0, 1.0);
}\`;

const FRAG_WATER = \`#version 300 es
\${GLSL_COMMON}
uniform sampler2D uState;
uniform vec2 uSimTexel;
/* cover-map panel uv into the square sim so rings stay circular on screen */
vec2 simUV(vec2 uv){
  return 0.5 + (uv - 0.5) * vec2(uAspect, 1.0) / max(uAspect, 1.0);
}
void main(){
  vec2 suv = simUV(vUv);
  float h  = texture(uState, suv).r;
  float hx = texture(uState, suv + vec2(uSimTexel.x, 0.0)).r - texture(uState, suv - vec2(uSimTexel.x, 0.0)).r;
  float hy = texture(uState, suv + vec2(0.0, uSimTexel.y)).r - texture(uState, suv - vec2(0.0, uSimTexel.y)).r;
  vec2 grad = vec2(hx, hy);
  vec3 nrm = normalize(vec3(-grad * 30.0, 1.0));

  vec2 ruv = vUv + grad * 0.22;          // refracted lookup
  float d  = sdf(ruv);

  // deep water base
  vec3 col = mix(vec3(0.006, 0.030, 0.055), vec3(0.012, 0.078, 0.125), vUv.y * 0.8 + h * 0.25);
  col += vec3(0.02, 0.10, 0.13) * fbm(vUv * vec2(uAspect, 1.0) * 3.0 + uTime * 0.05) * 0.3;

  // the mark, seen through the surface
  float logo = smoothstep(0.005, -0.005, d);
  float glow = exp(-max(d, 0.0) / 0.09) * 0.26;
  vec3 markCol = mix(vec3(0.55, 0.92, 1.0), vec3(0.95, 1.0, 1.0), logo * 0.6);
  col += markCol * (logo * 0.92 + glow);

  // ripple shading: crests bright, troughs barely darker
  col += vec3(0.09, 0.30, 0.40) * clamp(h * 1.8, -0.06, 1.0);
  col += vec3(0.25, 0.55, 0.65) * pow(clamp(h * 2.6, 0.0, 1.0), 2.0) * 0.5;

  // specular glint
  vec3 L = normalize(vec3(-0.35, 0.55, 0.75));
  vec3 H = normalize(L + vec3(0.0, 0.0, 1.0));
  float spec = pow(max(dot(nrm, H), 0.0), 150.0);
  col += spec * vec3(0.65, 0.9, 1.0) * 0.9;

  col *= 0.35 + 0.65 * edgeFade(vUv);
  col += (hash21(vUv * 617.0 + uTime) - 0.5) / 128.0;
  frag = vec4(col, 1.0);
}\`;

const FRAG_LIGHTNING = \`#version 300 es
\${GLSL_COMMON}
void main(){
  float t = uTime;
  float d = sdf(vUv);
  vec2 pp = vUv * vec2(uAspect, 1.0);

  // storm backdrop
  vec3 col = vec3(0.010, 0.011, 0.024);
  col += vec3(0.035, 0.04, 0.075) * fbm(pp * 2.2 + vec2(t * 0.04, t * 0.01));

  // occasional sheet flash
  float slot = floor(t * 0.45);
  float ph   = fract(t * 0.45);
  float big  = step(0.68, hash21(vec2(slot, 3.7))) * exp(-ph * 16.0);

  // the mark: dark slate body, lit by flashes
  float inside = smoothstep(0.005, -0.005, d);
  vec3 body = vec3(0.055, 0.06, 0.10) + big * vec3(0.55, 0.58, 0.85);
  col = mix(col, body, inside);
  float rim = exp(-abs(d) / 0.012) * 0.5;
  col += rim * vec3(0.35, 0.4, 0.8);

  // pointer draws the storm closer
  vec2 dp = (vUv - uPointer.xy) * vec2(uAspect, 1.0);
  float pb = 1.0 + 2.4 * uPointer.z * exp(-dot(dp, dp) * 34.0);

  // fBm zigzag arcs crawling the contour
  float fade = edgeFade(vUv);
  for (int i = 0; i < 3; i++){
    float fi = float(i);
    float n  = fbm(pp * mix(3.0, 8.0, fi / 2.0) + vec2(t * (1.2 + fi * 0.9), fi * 19.3)) - 0.5;
    float e  = abs(d + n * 0.11);
    float fl = hash21(vec2(floor(t * (6.0 + fi * 3.0)), fi));
    fl = mix(0.15, 1.0, smoothstep(0.25, 0.95, fl));
    float bolt = pow(0.0042 * pb / (e + 0.0022), 1.35) * fl;
    bolt = min(bolt, 6.0);
    col += bolt * mix(vec3(0.38, 0.42, 1.0), vec3(0.92, 0.9, 1.0), fi / 2.0) * fade;
  }
  // tight white core arc
  float n0 = fbm(pp * 5.0 + vec2(t * 2.4, 7.7)) - 0.5;
  float e0 = abs(d + n0 * 0.10);
  float corefl = mix(0.25, 1.15, hash21(vec2(floor(t * 9.0), 11.0)));
  col += min(pow(0.0026 * pb / (e0 + 0.0016), 1.6), 8.0) * corefl * vec3(1.0) * fade;

  col += big * vec3(0.30, 0.32, 0.55) * (0.25 + 0.75 * inside);
  col = col / (1.0 + col * 0.18);
  col *= 0.4 + 0.6 * edgeFade(vUv);
  col += (hash21(vUv * 431.0 + uTime) - 0.5) / 128.0;
  frag = vec4(col, 1.0);
}\`;

const FRAG_FIRE = \`#version 300 es
\${GLSL_COMMON}
uniform float uWind;

vec3 fireRamp(float x){
  x = clamp(x, 0.0, 1.0);
  vec3 c = mix(vec3(0.0), vec3(0.45, 0.06, 0.02), smoothstep(0.02, 0.30, x));
  c = mix(c, vec3(0.95, 0.34, 0.08), smoothstep(0.28, 0.55, x));
  c = mix(c, vec3(1.0, 0.68, 0.22), smoothstep(0.52, 0.78, x));
  c = mix(c, vec3(1.0, 0.97, 0.88), smoothstep(0.78, 0.97, x));
  return c;
}

void main(){
  float t = uTime;
  float d0 = sdf(vUv);
  vec2 pp = vUv * vec2(uAspect, 1.0);

  // which way is "up and away" from the mark (wide epsilon: the gradient
  // creases on the medial axis between rays and narrow sampling bands there)
  float e = 0.012;
  vec2 g = vec2(sdf(vUv + vec2(e, 0.0)) - sdf(vUv - vec2(e, 0.0)),
                sdf(vUv + vec2(0.0, e)) - sdf(vUv - vec2(0.0, e)));
  float upw = smoothstep(-0.2, 0.9, normalize(g + 1e-5).y);

  // pointer stokes the flame
  vec2 dp = (vUv - uPointer.xy) * vec2(uAspect, 1.0);
  float stoke = uPointer.z * exp(-dot(dp, dp) * 26.0);

  // thin tongues: x-squashed scrolling fBm, advected progressively with
  // height so flames stay attached at the edge and lick upward
  float n1 = fbm(vec2(pp.x * 12.0,        pp.y * 3.0  - t * 2.1));
  float n2 = fbm(vec2(pp.x * 6.0 + 41.3,  pp.y * 1.7  - t * 1.25));
  float d0f = d0 + (hash21(vUv * 771.0 + t * 1.3) - 0.5) * 0.004;
  float rise = max(0.0, n1 * 1.15 + n2 * 0.65 - 0.5) * 1.3;  // many columns ~0, few run hot
  float adv  = smoothstep(-0.03, 0.22, d0f);     // 0 at the edge, grows above
  float lick = 0.30 * (1.0 + stoke * 0.8);
  vec2 offs = vec2((n2 - 0.5) * 0.05 + uWind * 0.05, -rise * lick * adv);
  float df = sdf(vUv + offs);
  df += (hash21(vUv * 997.0 + uTime) - 0.5) * 0.004;  // dither the 8-bit field

  float heat = clamp(1.0 - df / 0.07, 0.0, 1.0);
  heat *= mix(0.1, 1.0, upw);
  heat *= 1.0 - 0.45 * smoothstep(0.08, 0.26, d0f);  // gentle thinning with height
  float tongue = smoothstep(0.25, 0.70, heat);   // sharp separated licks
  float body   = pow(heat, 2.2) * 0.45;          // faint haze beneath them
  float f = max(tongue, body) * (0.95 + 0.25 * stoke);

  vec3 col = vec3(0.012, 0.006, 0.004);
  col += fireRamp(f * (1.05 - 0.4 * smoothstep(0.02, 0.25, d0)));  // white base, orange tips

  // white-hot mark with a warm halo, like paper mid-combustion
  float inside = smoothstep(0.004, -0.004, d0);
  float core   = smoothstep(0.0, -0.02, d0);
  vec3 markCol = mix(vec3(1.0, 0.92, 0.78), vec3(1.0, 1.0, 0.98), core);
  col = mix(col, markCol, inside);
  col += exp(-max(d0, 0.0) / 0.035) * vec3(1.0, 0.55, 0.22) * 0.35 * (1.0 - inside * 0.9);
  col += exp(-max(d0, 0.0) / 0.12)  * vec3(0.55, 0.14, 0.03) * 0.35 * (0.6 + 0.4 * n2);

  col = col / (1.0 + col * 0.12);
  col *= 0.35 + 0.65 * edgeFade(vUv);
  col += (hash21(vUv * 523.0 + uTime) - 0.5) / 128.0;
  frag = vec4(col, 1.0);
}\`;

/* ---------------- particles: stateless GPU point sprites off the contour ---------------- */
const PART_VERT = \`#version 300 es
precision highp float;
layout(location=0) in vec2 aPos;    // spawn point, y-up mask uv
layout(location=1) in vec2 aNorm;   // outward contour normal
layout(location=2) in float aSeed;
uniform float uTime;
uniform vec2  uScale;
uniform vec2  uShift;
uniform float uDpr;
uniform float uWind;
uniform vec4  uCfgA;  // travel, lifeMin, lifeMax, alongNormal
uniform vec4  uCfgB;  // wiggle, sizeMin, sizeMax, sparse
out float vFade;
out float vMixC;
float h1(float n){ return fract(sin(n) * 43758.5453); }
void main(){
  float hs   = h1(aSeed * 1.31);
  float life = mix(uCfgA.y, uCfgA.z, hs);
  float tt   = uTime / life + aSeed * 13.7;
  float ph   = fract(tt);
  float cyc  = floor(tt);
  float r1 = h1(aSeed + cyc * 0.317);
  float r2 = h1(aSeed * 2.13 + cyc * 0.771);
  float on = step(uCfgB.w, r2);

  vec2 dir = normalize(mix(vec2(0.0, 1.0), aNorm, uCfgA.w) + (vec2(r1, h1(r1 * 7.0)) - 0.5) * 0.8);
  float trav = uCfgA.x * (0.45 + 0.9 * r1);
  vec2 p = aPos + aNorm * 0.004 + dir * trav * ph;
  p.x += sin(ph * 10.0 + r1 * 40.0 + uTime * 0.5) * uCfgB.x * ph;
  p.x += uWind * 0.08 * ph;

  vec2 uv = 0.5 + uShift + (p - 0.5) / uScale;
  vFade = on * smoothstep(0.0, 0.12, ph) * smoothstep(1.0, 0.5, ph) * mix(0.35, 1.0, r2);
  vMixC = h1(aSeed * 3.7 + cyc);
  gl_Position = vec4(uv * 2.0 - 1.0, 0.0, 1.0);
  gl_PointSize = mix(uCfgB.y, uCfgB.z, h1(aSeed * 5.11 + cyc)) * uDpr * (1.0 - 0.45 * ph);
}\`;

const PART_FRAG = \`#version 300 es
precision highp float;
uniform vec3 uColA;
uniform vec3 uColB;
in float vFade;
in float vMixC;
out vec4 frag;
void main(){
  vec2 q = gl_PointCoord * 2.0 - 1.0;
  float r2 = dot(q, q);
  if (r2 > 1.0) discard;
  float a = exp(-r2 * 3.5) * (1.0 - r2);
  frag = vec4(mix(uColA, uColB, vMixC) * a * vFade, 1.0);
}\`;

/* ---------------- GL helpers ---------------- */
function compile(gl, type, src) {
  const sh = gl.createShader(type);
  gl.shaderSource(sh, src);
  gl.compileShader(sh);
  if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
    console.error(gl.getShaderInfoLog(sh), src);
    return null;
  }
  return sh;
}
function program(gl, vertSrc, fragSrc) {
  const p = gl.createProgram();
  const vs = compile(gl, gl.VERTEX_SHADER, vertSrc);
  const fs = compile(gl, gl.FRAGMENT_SHADER, fragSrc);
  if (!vs || !fs) return null;
  gl.attachShader(p, vs); gl.attachShader(p, fs);
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
    console.error(gl.getProgramInfoLog(p));
    return null;
  }
  return p;
}

const DPR = Math.min(window.devicePixelRatio || 1, 1.75);
const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
const SIM_RES = 512;

class Panel {
  constructor(el, fragSrc, logo, opts) {
    this.el = el;
    this.canvas = el.querySelector('canvas');
    this.opts = opts;
    this.pointer = { x: 0.5, y: 0.5, active: 0 };
    this.wind = 0;
    this.windTarget = 0;
    this.dropQueue = [];
    this.nextAutoDrop = 0.6;
    this.needsResize = false;
    this.ok = false;

    const gl = this.canvas.getContext('webgl2', { alpha: false, antialias: false });
    if (!gl) return this.fail();
    this.gl = gl;

    this.prog = program(gl, VERT, fragSrc);
    if (!this.prog) return this.fail();
    this.uni = {};
    for (const n of ['uSDF','uTime','uAspect','uScale','uShift','uPointer','uState','uSimTexel','uWind'])
      this.uni[n] = gl.getUniformLocation(this.prog, n);

    // sdf texture
    this.sdfTex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, this.sdfTex);
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.R8, SDF_SIZE, SDF_SIZE, 0, gl.RED, gl.UNSIGNED_BYTE, logo.sdf);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);

    if (opts.sim) {
      if (!gl.getExtension('EXT_color_buffer_float')) return this.fail();
      this.simProg = program(gl, VERT, FRAG_SIM);
      if (!this.simProg) return this.fail();
      this.simUni = {
        uState: gl.getUniformLocation(this.simProg, 'uState'),
        uTexel: gl.getUniformLocation(this.simProg, 'uTexel'),
        uDrop:  gl.getUniformLocation(this.simProg, 'uDrop'),
      };
      this.simTex = []; this.simFbo = [];
      for (let i = 0; i < 2; i++) {
        const t = gl.createTexture();
        gl.bindTexture(gl.TEXTURE_2D, t);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RG16F, SIM_RES, SIM_RES, 0, gl.RG, gl.HALF_FLOAT, null);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
        gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
        const f = gl.createFramebuffer();
        gl.bindFramebuffer(gl.FRAMEBUFFER, f);
        gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
        this.simTex.push(t); this.simFbo.push(f);
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      this.simSrc = 0;
    }

    // particle system
    const P = opts.particles;
    if (P) {
      this.partProg = program(gl, PART_VERT, PART_FRAG);
      if (!this.partProg) return this.fail();
      this.partUni = {};
      for (const n of ['uTime','uScale','uShift','uDpr','uWind','uCfgA','uCfgB','uColA','uColB'])
        this.partUni[n] = gl.getUniformLocation(this.partProg, n);
      const data = makeParticleData(logo.edges, P.count);
      this.partVao = gl.createVertexArray();
      gl.bindVertexArray(this.partVao);
      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 20, 0);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 20, 8);
      gl.enableVertexAttribArray(2);
      gl.vertexAttribPointer(2, 1, gl.FLOAT, false, 20, 16);
      gl.bindVertexArray(null);
    }

    this.resize();
    // resize inside the rAF (before drawing), never in the RO callback \u2014
    // RO fires after rAF, so resizing there clears the canvas post-draw
    // and every hover transition frame paints black
    new ResizeObserver(() => {
      if (REDUCED) this.resize(); else this.needsResize = true;
    }).observe(el);
    this.bindPointer();
    this.ok = true;
  }

  fail() {
    this.el.querySelector('.fail').style.display = 'grid';
    this.canvas.style.display = 'none';
  }

  resize() {
    const r = this.el.getBoundingClientRect();
    const w = Math.max(2, Math.round(r.width * DPR));
    const h = Math.max(2, Math.round(r.height * DPR));
    if (this.canvas.width !== w || this.canvas.height !== h) {
      this.canvas.width = w; this.canvas.height = h;
    }
    this.aspect = w / h;
    // Reserve clear space for the brand: left of desktop cards, above phone cards.
    if (this.opts.sim) this.opts.shift = r.width <= 900 ? [0, 0.23] : [-0.28, 0];
    if (REDUCED && this.ok) this.draw(0.001);
  }

  bindPointer() {
    const uv = e => {
      const r = this.el.getBoundingClientRect();
      return { x: (e.clientX - r.left) / r.width, y: 1 - (e.clientY - r.top) / r.height };
    };
    let last = null, lastT = 0;
    this.el.addEventListener('pointermove', e => {
      const p = uv(e), now = performance.now();
      this.pointer.x = p.x; this.pointer.y = p.y; this.pointer.active = 1;
      if (last) {
        const dt = Math.max(8, now - lastT);
        const dx = p.x - last.x, dy = p.y - last.y;
        const speed = Math.hypot(dx, dy) / (dt / 1000);
        if (this.opts.sim && speed > 0.05 && this.dropQueue.length < 6)
          this.dropQueue.push({ x: p.x, y: p.y, s: Math.min(speed * 0.14, 0.55) });
        this.windTarget = Math.max(-1, Math.min(1, dx / (dt / 1000) * 0.55));
      }
      last = p; lastT = now;
    });
    this.el.addEventListener('pointerdown', e => {
      const p = uv(e);
      if (this.opts.sim) this.dropQueue.push({ x: p.x, y: p.y, s: 0.9 });
      this.pointer.x = p.x; this.pointer.y = p.y; this.pointer.active = 1.6;
    });
    this.el.addEventListener('pointerup', () => { this.pointer.active = 1; });
    this.el.addEventListener('pointerleave', () => { this.pointer.active = 0; last = null; this.windTarget = 0; });
  }

  /* panel uv -> square sim uv (must match simUV() in the water shader) */
  toSimUV(x, y) {
    const a = this.aspect, m = Math.max(a, 1);
    return { x: 0.5 + (x - 0.5) * a / m, y: 0.5 + (y - 0.5) / m };
  }

  stepSim(t) {
    const gl = this.gl;
    if (t > this.nextAutoDrop) {
      this.dropQueue.push({ x: 0.12 + Math.random() * 0.76, y: 0.12 + Math.random() * 0.76, s: 0.12 + Math.random() * 0.3 });
      this.nextAutoDrop = t + 0.5 + Math.random() * 1.4;
    }
    gl.useProgram(this.simProg);
    gl.viewport(0, 0, SIM_RES, SIM_RES);
    gl.uniform2f(this.simUni.uTexel, 1 / SIM_RES, 1 / SIM_RES);
    for (let i = 0; i < 2; i++) {
      const drop = this.dropQueue.shift();
      if (drop) {
        const s = this.toSimUV(drop.x, drop.y);
        gl.uniform3f(this.simUni.uDrop, s.x, s.y, drop.s);
      } else {
        gl.uniform3f(this.simUni.uDrop, 0, 0, 0);
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER, this.simFbo[1 - this.simSrc]);
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, this.simTex[this.simSrc]);
      gl.uniform1i(this.simUni.uState, 1);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      this.simSrc = 1 - this.simSrc;
    }
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
  }

  scaleVec() {
    const zoom = this.opts.zoom, a = this.aspect;
    const fit = Math.min(a, 1);
    return [(a / fit) * zoom, (1 / fit) * zoom];
  }

  draw(t) {
    const gl = this.gl;
    if (this.needsResize) { this.needsResize = false; this.resize(); }
    if (this.opts.sim) this.stepSim(t);

    this.wind += (this.windTarget - this.wind) * 0.04;
    this.windTarget *= 0.97;

    gl.useProgram(this.prog);
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);

    const sc = this.scaleVec();
    gl.uniform1f(this.uni.uTime, t);
    gl.uniform1f(this.uni.uAspect, this.aspect);
    gl.uniform2f(this.uni.uScale, sc[0], sc[1]);
    gl.uniform2f(this.uni.uShift, this.opts.shift[0], this.opts.shift[1]);
    gl.uniform3f(this.uni.uPointer, this.pointer.x, this.pointer.y, this.pointer.active);
    if (this.uni.uWind) gl.uniform1f(this.uni.uWind, this.wind);

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.sdfTex);
    gl.uniform1i(this.uni.uSDF, 0);
    if (this.opts.sim) {
      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, this.simTex[this.simSrc]);
      gl.uniform1i(this.uni.uState, 1);
      gl.uniform2f(this.uni.uSimTexel, 1 / SIM_RES, 1 / SIM_RES);
    }
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    const P = this.opts.particles;
    if (P) {
      gl.useProgram(this.partProg);
      gl.uniform1f(this.partUni.uTime, t);
      gl.uniform2f(this.partUni.uScale, sc[0], sc[1]);
      gl.uniform2f(this.partUni.uShift, this.opts.shift[0], this.opts.shift[1]);
      gl.uniform1f(this.partUni.uDpr, DPR);
      gl.uniform1f(this.partUni.uWind, this.wind);
      gl.uniform4f(this.partUni.uCfgA, P.travel, P.lifeMin, P.lifeMax, P.alongNormal);
      gl.uniform4f(this.partUni.uCfgB, P.wiggle, P.sizeMin, P.sizeMax, P.sparse);
      gl.uniform3f(this.partUni.uColA, P.colA[0], P.colA[1], P.colA[2]);
      gl.uniform3f(this.partUni.uColB, P.colB[0], P.colB[1], P.colB[2]);
      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE);
      gl.bindVertexArray(this.partVao);
      gl.drawArrays(gl.POINTS, 0, P.count);
      gl.bindVertexArray(null);
      gl.disable(gl.BLEND);
    }
  }
}

/* ---------------- boot ---------------- */
function buildLogo(path) {
  const img = rasterizeLogo(path);
  return { sdf: buildSDF(img), edges: edgePoints(img) };
}
const logos = {
  openai: buildLogo(LOGO_PATHS.openai),
  anthropic: buildLogo(LOGO_PATHS.anthropic),
  claude: buildLogo(LOGO_PATHS.claude),
};

const panels = [
  new Panel(document.querySelector('[data-fx="water"]'), FRAG_WATER, logos.openai, {
    sim: true, zoom: 1.06, shift: [0, 0],
    particles: {
      count: 160, travel: 0.10, lifeMin: 4.0, lifeMax: 8.0, alongNormal: 0.15,
      wiggle: 0.02, sizeMin: 1.5, sizeMax: 3.5, sparse: 0.5,
      colA: [0.10, 0.24, 0.30], colB: [0.22, 0.40, 0.48],
    },
  }),
  new Panel(document.querySelector('[data-fx="lightning"]'), FRAG_LIGHTNING, logos.anthropic, {
    sim: false, zoom: 1.10, shift: [0, 0],
    particles: {
      count: 240, travel: 0.055, lifeMin: 0.3, lifeMax: 0.9, alongNormal: 1.0,
      wiggle: 0.015, sizeMin: 1.2, sizeMax: 2.6, sparse: 0.8,
      colA: [0.45, 0.50, 1.0], colB: [0.95, 0.95, 1.0],
    },
  }),
  new Panel(document.querySelector('[data-fx="fire"]'), FRAG_FIRE, logos.claude, {
    sim: false, zoom: 1.16, shift: [0, -0.04],
    particles: {
      count: 420, travel: 0.30, lifeMin: 1.4, lifeMax: 3.0, alongNormal: 0.35,
      wiggle: 0.035, sizeMin: 1.6, sizeMax: 4.5, sparse: 0.55,
      colA: [1.0, 0.62, 0.28], colB: [1.0, 0.30, 0.10],
    },
  }),
].filter(p => p.ok);

window.addEventListener('message', event => {
  if (event.source !== parent || event.data?.type !== 'workspace-water-pointer') return;
  const { kind, x, y } = event.data;
  if (!['pointermove', 'pointerdown', 'pointerup', 'pointerleave'].includes(kind) || !Number.isFinite(x) || !Number.isFinite(y)) return;
  const el = document.querySelector('[data-fx="water"]');
  const r = el.getBoundingClientRect();
  el.dispatchEvent(new PointerEvent(kind, {clientX:r.left + Math.max(0, Math.min(1, x)) * r.width, clientY:r.top + Math.max(0, Math.min(1, y)) * r.height}));
});
const t0 = performance.now();
function loop() {
  const t = (performance.now() - t0) / 1000;
  for (const p of panels) p.draw(t);
  requestAnimationFrame(loop);
}
if (!REDUCED) requestAnimationFrame(loop);
else for (const p of panels) p.draw(0.001);
<\/script>
</body>
</html>
`;var Xl=Ye(bt(),1),xf=["water","lightning","fire"],Ze={variant:"water",speed:1,size:1,particleAmount:1,opacity:1,hue:0,saturation:1,brightness:1},wf={water:"Water",lightning:"Lightning",fire:"Fire"},kf={water:1.56,lightning:1.66,fire:1.82},_f={water:"1.06",lightning:"1.10",fire:"1.16"},Sf={water:160,lightning:360,fire:560},Ef={water:160,lightning:240,fire:420},Tf=[[`const SDF_SIZE = 512;
const SDF_SPREAD = 128;`,`const SDF_SIZE = 768;
const SDF_SPREAD = 192;`],["const DPR = Math.min(window.devicePixelRatio || 1, 1.75);","const DPR = Math.min(Math.max(window.devicePixelRatio || 1, 1.5), 2.25);"],["sim: false, zoom: 1.16, shift: [0, -0.04],","sim: false, zoom: 1.16, shift: [0, -0.11],"],[`  float inside = smoothstep(0.005, -0.005, d);
  vec3 body = vec3(0.055, 0.06, 0.10) + big * vec3(0.55, 0.58, 0.85);
  col = mix(col, body, inside);
  float rim = exp(-abs(d) / 0.012) * 0.5;`,`  float inside = smoothstep(0.0025, -0.0025, d);
  vec3 body = vec3(0.055, 0.06, 0.10) + big * vec3(0.55, 0.58, 0.85);
  col = mix(col, body, inside);
  float rim = exp(-abs(d) / 0.0075) * 0.56;`],[`  // fBm zigzag arcs crawling the contour
  float fade = edgeFade(vUv);
  for (int i = 0; i < 3; i++){
    float fi = float(i);
    float n  = fbm(pp * mix(3.0, 8.0, fi / 2.0) + vec2(t * (1.2 + fi * 0.9), fi * 19.3)) - 0.5;
    float e  = abs(d + n * 0.11);
    float fl = hash21(vec2(floor(t * (6.0 + fi * 3.0)), fi));
    fl = mix(0.15, 1.0, smoothstep(0.25, 0.95, fl));
    float bolt = pow(0.0042 * pb / (e + 0.0022), 1.35) * fl;
    bolt = min(bolt, 6.0);
    col += bolt * mix(vec3(0.38, 0.42, 1.0), vec3(0.92, 0.9, 1.0), fi / 2.0) * fade;
  }
  // tight white core arc
  float n0 = fbm(pp * 5.0 + vec2(t * 2.4, 7.7)) - 0.5;
  float e0 = abs(d + n0 * 0.10);
  float corefl = mix(0.25, 1.15, hash21(vec2(floor(t * 9.0), 11.0)));
  col += min(pow(0.0026 * pb / (e0 + 0.0016), 1.6), 8.0) * corefl * vec3(1.0) * fade;`,`  // Layered contour arcs: broad current, hairline filaments, and short-lived forks.
  float fade = edgeFade(vUv);
  for (int i = 0; i < 5; i++){
    float fi = float(i);
    float layer = fi / 4.0;
    float coarse = fbm(pp * mix(4.0, 13.0, layer) + vec2(t * (1.3 + fi * 0.78), fi * 17.7)) - 0.5;
    float detail = fbm(pp * mix(17.0, 31.0, layer) + vec2(-t * (2.9 + fi * 0.55), fi * 31.7)) - 0.5;
    float n = coarse * mix(0.82, 0.58, layer) + detail * mix(0.18, 0.42, layer);
    float e = abs(d + n * mix(0.09, 0.038, layer));
    float fl = hash21(vec2(floor(t * (7.0 + fi * 3.4)), fi));
    fl = mix(0.12, 1.0, smoothstep(0.22, 0.94, fl));
    float width = mix(0.0034, 0.0012, layer);
    float bolt = pow(width * pb / (e + mix(0.0018, 0.0008, layer)), mix(1.42, 1.78, layer)) * fl;
    bolt = min(bolt, 7.0);
    col += bolt * mix(vec3(0.34, 0.39, 1.0), vec3(0.96, 0.94, 1.0), pow(layer, 0.75)) * fade;
  }

  // A white primary channel with a displaced secondary fork.
  float n0 = fbm(pp * 6.5 + vec2(t * 2.8, 7.7)) - 0.5;
  n0 += (fbm(pp * 23.0 + vec2(-t * 4.1, 18.2)) - 0.5) * 0.22;
  float e0 = abs(d + n0 * 0.075);
  float corefl = mix(0.22, 1.2, hash21(vec2(floor(t * 10.0), 11.0)));
  col += min(pow(0.00175 * pb / (e0 + 0.0009), 1.78), 9.0) * corefl * vec3(1.0) * fade;

  float branchNoise = fbm(pp * 16.0 + vec2(t * 3.7, -13.4)) - 0.5;
  float branchEdge = abs(d + n0 * 0.052 + branchNoise * 0.026);
  float branchLife = smoothstep(0.35, 0.92, hash21(vec2(floor(t * 13.0), 23.0)));
  col += min(pow(0.0011 * pb / (branchEdge + 0.00075), 1.72), 5.0)
       * branchLife * vec3(0.64, 0.70, 1.0) * fade;`],[`  // thin tongues: x-squashed scrolling fBm, advected progressively with
  // height so flames stay attached at the edge and lick upward
  float n1 = fbm(vec2(pp.x * 12.0,        pp.y * 3.0  - t * 2.1));
  float n2 = fbm(vec2(pp.x * 6.0 + 41.3,  pp.y * 1.7  - t * 1.25));
  float d0f = d0 + (hash21(vUv * 771.0 + t * 1.3) - 0.5) * 0.004;
  float rise = max(0.0, n1 * 1.15 + n2 * 0.65 - 0.5) * 1.3;  // many columns ~0, few run hot
  float adv  = smoothstep(-0.03, 0.22, d0f);     // 0 at the edge, grows above
  float lick = 0.30 * (1.0 + stoke * 0.8);
  vec2 offs = vec2((n2 - 0.5) * 0.05 + uWind * 0.05, -rise * lick * adv);
  float df = sdf(vUv + offs);
  df += (hash21(vUv * 997.0 + uTime) - 0.5) * 0.004;  // dither the 8-bit field

  float heat = clamp(1.0 - df / 0.07, 0.0, 1.0);
  heat *= mix(0.1, 1.0, upw);
  heat *= 1.0 - 0.45 * smoothstep(0.08, 0.26, d0f);  // gentle thinning with height
  float tongue = smoothstep(0.25, 0.70, heat);   // sharp separated licks
  float body   = pow(heat, 2.2) * 0.45;          // faint haze beneath them
  float f = max(tongue, body) * (0.95 + 0.25 * stoke);`,`  // Three frequency bands split the fire into attached tongues, fine wisps, and hot veins.
  float n1 = fbm(vec2(pp.x * 11.0,        pp.y * 3.2 - t * 2.2));
  float n2 = fbm(vec2(pp.x * 6.5 + 41.3,  pp.y * 1.8 - t * 1.3));
  float n3 = fbm(vec2(pp.x * 27.0 - t * 0.7, pp.y * 7.5 - t * 4.0));
  float d0f = d0 + (hash21(vUv * 771.0 + t * 1.3) - 0.5) * 0.0025;
  float rise = max(0.0, n1 * 0.98 + n2 * 0.54 + n3 * 0.38 - 0.58) * 1.48;
  float adv  = smoothstep(-0.025, 0.24, d0f);
  float lick = 0.31 * (1.0 + stoke * 0.82);
  vec2 offs = vec2((n2 - 0.5) * 0.042 + (n3 - 0.5) * 0.018 + uWind * 0.05, -rise * lick * adv);
  float df = sdf(vUv + offs);
  float micro = fbm(pp * vec2(34.0, 9.0) + vec2(t * 1.1, -t * 5.2));
  df += (micro - 0.5) * 0.011 * adv;
  df += (hash21(vUv * 997.0 + uTime) - 0.5) * 0.0025;

  float heat = clamp(1.0 - df / 0.064, 0.0, 1.0);
  heat *= mix(0.08, 1.0, upw);
  heat *= 1.0 - 0.52 * smoothstep(0.07, 0.27, d0f);
  heat *= 0.84 + n3 * 0.24;
  float tongue = smoothstep(0.29, 0.69, heat);
  float filament = smoothstep(0.58, 0.91, heat + (n3 - 0.5) * 0.20);
  float split = smoothstep(0.38, 0.82, n3) * smoothstep(0.015, 0.23, d0f);
  float body = pow(heat, 2.35) * 0.36;
  float f = max(max(tongue * (0.72 + 0.28 * n3), filament * split * 0.88), body)
          * (0.95 + 0.25 * stoke);`],[`  col += fireRamp(f * (1.05 - 0.4 * smoothstep(0.02, 0.25, d0)));  // white base, orange tips

  // white-hot mark with a warm halo, like paper mid-combustion
  float inside = smoothstep(0.004, -0.004, d0);
  float core   = smoothstep(0.0, -0.02, d0);`,`  col += fireRamp(f * (1.05 - 0.4 * smoothstep(0.02, 0.25, d0)));
  float vein = pow(clamp(1.0 - abs(df) / 0.026, 0.0, 1.0), 3.2)
             * smoothstep(0.55, 0.9, n3) * upw * (0.35 + 0.65 * adv);
  col += fireRamp(0.82) * vein * 0.34;

  // A crisp white-hot mark with a restrained warm halo.
  float inside = smoothstep(0.0025, -0.0025, d0);
  float core   = smoothstep(0.0, -0.016, d0);`],[`  col += exp(-max(d0, 0.0) / 0.035) * vec3(1.0, 0.55, 0.22) * 0.35 * (1.0 - inside * 0.9);
  col += exp(-max(d0, 0.0) / 0.12)  * vec3(0.55, 0.14, 0.03) * 0.35 * (0.6 + 0.4 * n2);`,`  col += exp(-max(d0, 0.0) / 0.026) * vec3(1.0, 0.55, 0.22) * 0.30 * (1.0 - inside * 0.92);
  col += exp(-max(d0, 0.0) / 0.09)  * vec3(0.55, 0.14, 0.03) * 0.28 * (0.55 + 0.45 * n2);`],[`count: 240, travel: 0.055, lifeMin: 0.3, lifeMax: 0.9, alongNormal: 1.0,
      wiggle: 0.015, sizeMin: 1.2, sizeMax: 2.6, sparse: 0.8,`,`count: 240, travel: 0.075, lifeMin: 0.28, lifeMax: 0.82, alongNormal: 0.92,
      wiggle: 0.022, sizeMin: 0.8, sizeMax: 2.0, sparse: 0.72,`],[`count: 420, travel: 0.30, lifeMin: 1.4, lifeMax: 3.0, alongNormal: 0.35,
      wiggle: 0.035, sizeMin: 1.6, sizeMax: 4.5, sparse: 0.55,`,`count: 420, travel: 0.34, lifeMin: 1.1, lifeMax: 2.7, alongNormal: 0.30,
      wiggle: 0.046, sizeMin: 0.9, sizeMax: 3.6, sparse: 0.42,`]];function Dt(e,t,n){return Math.min(n,Math.max(t,e))}function Cf(e){return Tf.reduce((t,[n,r])=>t.replace(n,r),e)}function Pf(e,t,n){let r=kf[e]/Dt(t,.65,1.5),o=Math.max(0,Math.round(Sf[e]*Dt(n,0,2))),i=`<style data-elements-focus>
html, body, main { width: 100%; height: 100%; margin: 0; overflow: hidden; background: #060708; }
header, .hint, .info, .kanji { display: none !important; }
main { display: block; }
.panel { display: none; }
.panel[data-fx="${e}"] {
  position: absolute;
  inset: 0;
  display: block;
  width: 100%;
  height: 100%;
  border: 0;
  opacity: 1;
  transform: none;
  animation: none;
}
.panel[data-fx="${e}"] canvas { width: 100%; height: 100%; }
</style>`;return Cf(bc).replace(/<link[^>]+fonts\.googleapis\.com[^>]*>/gi,"").replace(/<link[^>]+fonts\.gstatic\.com[^>]*>/gi,"").replace("</head>",`${i}<script data-elements-controls>
(function () {
  var nativeNow = performance.now.bind(performance);
  var last = nativeNow();
  var virtual = last;
  var state = { speed: 1, paused: false };
  window.__ELEMENTS_PAUSED = false;
  performance.now = function () {
    var real = nativeNow();
    if (!state.paused) virtual += (real - last) * state.speed;
    last = real;
    return virtual;
  };
  window.addEventListener('message', function (event) {
    if (!event.data || event.data.type !== 'elements-controls') return;
    var next = event.data.controls || {};
    if (Number.isFinite(next.speed)) state.speed = Math.max(0, Math.min(3, next.speed));
    state.paused = Boolean(next.paused);
    window.__ELEMENTS_PAUSED = state.paused;
  });
})();
<\/script></head>`).replace(new RegExp(`count: ${Ef[e]}`),`count: ${o}`).replace(`zoom: ${_f[e]}`,`zoom: ${r.toFixed(4)}`).replace("for (const p of panels) p.draw(t);","if (!window.__ELEMENTS_PAUSED) for (const p of panels) p.draw(t);")}function Yl({variant:e=Ze.variant,speed:t=Ze.speed,size:n=Ze.size,particleAmount:r=Ze.particleAmount,opacity:o=Ze.opacity,hue:i=Ze.hue,saturation:l=Ze.saturation,brightness:a=Ze.brightness,className:s="",style:d}){let p=(0,ge.useRef)(null),[h,m]=(0,ge.useState)(!0),[y,w]=(0,ge.useState)(()=>typeof document>"u"||!document.hidden),x=xf.includes(e)?e:Ze.variant,b=Dt(t,0,3),c=!h||!y,u=(0,ge.useMemo)(()=>Pf(x,n,r),[r,x,n]),f=(0,ge.useCallback)(()=>{p.current?.contentWindow?.postMessage({type:"elements-controls",controls:{speed:b,paused:c}},"*")},[c,b]);return(0,ge.useEffect)(()=>{let g=p.current;if(!g||typeof IntersectionObserver>"u")return;let _=new IntersectionObserver(([S])=>m(S?.isIntersecting??!0));return _.observe(g),()=>_.disconnect()},[]),(0,ge.useEffect)(()=>{if(typeof document>"u")return;let g=()=>w(!document.hidden);return document.addEventListener("visibilitychange",g),()=>document.removeEventListener("visibilitychange",g)},[]),(0,ge.useEffect)(()=>{f()},[f,u]),(0,Xl.jsx)("div",{className:`threeui-background elements${s?` ${s}`:""}`,"data-element":x,style:{background:"#060708",pointerEvents:"auto",...d},children:(0,Xl.jsx)("iframe",{ref:p,title:`${wf[x]} element background`,srcDoc:u,sandbox:"allow-scripts",onLoad:f,"aria-hidden":"true",tabIndex:-1,style:{position:"absolute",inset:0,display:"block",width:"100%",height:"100%",border:0,background:"#060708",opacity:Dt(o,.05,1),filter:`hue-rotate(${Dt(i,-180,180)}deg) saturate(${Dt(l,0,2)}) brightness(${Dt(a,.35,1.8)})`}})})}var Kl=Ye(bt(),1);function Uc(){return(0,Kl.jsx)("div",{className:"shader-frame",children:(0,Kl.jsx)(Yl,{variant:"water",speed:1,size:1,particleAmount:1,hue:0,saturation:1,brightness:1,opacity:1})})}var jc=Ye(bt(),1),Ro=document.getElementById("home-water");if(Ro){let e=(0,Oc.createRoot)(Ro);e.render((0,jc.jsx)(Uc,{}));let t=r=>{let o=Ro.getBoundingClientRect();!o.width||!o.height||Ro.querySelector("iframe")?.contentWindow?.postMessage({type:"workspace-water-pointer",kind:r.type,x:(r.clientX-o.left)/o.width,y:(r.clientY-o.top)/o.height},"*")},n=["pointermove","pointerdown","pointerup","pointerleave"];n.forEach(r=>document.addEventListener(r,t,{capture:!0,passive:!0})),window.addEventListener("pagehide",r=>{r.persisted||(n.forEach(o=>document.removeEventListener(o,t,!0)),e.unmount())},{once:!0})}
/*! For license information please see water.js.LEGAL.txt */
