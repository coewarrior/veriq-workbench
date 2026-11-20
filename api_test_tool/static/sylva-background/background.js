var kd=Object.create;var ul=Object.defineProperty;var Sd=Object.getOwnPropertyDescriptor;var Ed=Object.getOwnPropertyNames;var zd=Object.getPrototypeOf,Td=Object.prototype.hasOwnProperty;var De=(e,t)=>()=>(t||e((t={exports:{}}).exports,t),t.exports);var Rd=(e,t,n,r)=>{if(t&&typeof t=="object"||typeof t=="function")for(let a of Ed(t))!Td.call(e,a)&&a!==n&&ul(e,a,{get:()=>t[a],enumerable:!(r=Sd(t,a))||r.enumerable});return e};var ce=(e,t,n)=>(n=e!=null?kd(zd(e)):{},Rd(t||!e||!e.__esModule?ul(n,"default",{value:e,enumerable:!0}):n,e));var xl=De(T=>{"use strict";var pn=Symbol.for("react.element"),_d=Symbol.for("react.portal"),Cd=Symbol.for("react.fragment"),Pd=Symbol.for("react.strict_mode"),Ld=Symbol.for("react.profiler"),Ad=Symbol.for("react.provider"),Md=Symbol.for("react.context"),$d=Symbol.for("react.forward_ref"),Hd=Symbol.for("react.suspense"),Fd=Symbol.for("react.memo"),Nd=Symbol.for("react.lazy"),cl=Symbol.iterator;function Dd(e){return e===null||typeof e!="object"?null:(e=cl&&e[cl]||e["@@iterator"],typeof e=="function"?e:null)}var pl={isMounted:function(){return!1},enqueueForceUpdate:function(){},enqueueReplaceState:function(){},enqueueSetState:function(){}},fl=Object.assign,gl={};function Ht(e,t,n){this.props=e,this.context=t,this.refs=gl,this.updater=n||pl}Ht.prototype.isReactComponent={};Ht.prototype.setState=function(e,t){if(typeof e!="object"&&typeof e!="function"&&e!=null)throw Error("setState(...): takes an object of state variables to update or a function which returns an object of state variables.");this.updater.enqueueSetState(this,e,t,"setState")};Ht.prototype.forceUpdate=function(e){this.updater.enqueueForceUpdate(this,e,"forceUpdate")};function ml(){}ml.prototype=Ht.prototype;function Ma(e,t,n){this.props=e,this.context=t,this.refs=gl,this.updater=n||pl}var $a=Ma.prototype=new ml;$a.constructor=Ma;fl($a,Ht.prototype);$a.isPureReactComponent=!0;var dl=Array.isArray,vl=Object.prototype.hasOwnProperty,Ha={current:null},wl={key:!0,ref:!0,__self:!0,__source:!0};function yl(e,t,n){var r,a={},i=null,o=null;if(t!=null)for(r in t.ref!==void 0&&(o=t.ref),t.key!==void 0&&(i=""+t.key),t)vl.call(t,r)&&!wl.hasOwnProperty(r)&&(a[r]=t[r]);var l=arguments.length-2;if(l===1)a.children=n;else if(1<l){for(var s=Array(l),c=0;c<l;c++)s[c]=arguments[c+2];a.children=s}if(e&&e.defaultProps)for(r in l=e.defaultProps,l)a[r]===void 0&&(a[r]=l[r]);return{$$typeof:pn,type:e,key:i,ref:o,props:a,_owner:Ha.current}}function Od(e,t){return{$$typeof:pn,type:e.type,key:t,ref:e.ref,props:e.props,_owner:e._owner}}function Fa(e){return typeof e=="object"&&e!==null&&e.$$typeof===pn}function Wd(e){var t={"=":"=0",":":"=2"};return"$"+e.replace(/[=:]/g,function(n){return t[n]})}var hl=/\/+/g;function Aa(e,t){return typeof e=="object"&&e!==null&&e.key!=null?Wd(""+e.key):t.toString(36)}function lr(e,t,n,r,a){var i=typeof e;(i==="undefined"||i==="boolean")&&(e=null);var o=!1;if(e===null)o=!0;else switch(i){case"string":case"number":o=!0;break;case"object":switch(e.$$typeof){case pn:case _d:o=!0}}if(o)return o=e,a=a(o),e=r===""?"."+Aa(o,0):r,dl(a)?(n="",e!=null&&(n=e.replace(hl,"$&/")+"/"),lr(a,t,n,"",function(c){return c})):a!=null&&(Fa(a)&&(a=Od(a,n+(!a.key||o&&o.key===a.key?"":(""+a.key).replace(hl,"$&/")+"/")+e)),t.push(a)),1;if(o=0,r=r===""?".":r+":",dl(e))for(var l=0;l<e.length;l++){i=e[l];var s=r+Aa(i,l);o+=lr(i,t,n,s,a)}else if(s=Dd(e),typeof s=="function")for(e=s.call(e),l=0;!(i=e.next()).done;)i=i.value,s=r+Aa(i,l++),o+=lr(i,t,n,s,a);else if(i==="object")throw t=String(e),Error("Objects are not valid as a React child (found: "+(t==="[object Object]"?"object with keys {"+Object.keys(e).join(", ")+"}":t)+"). If you meant to render a collection of children, use an array instead.");return o}function or(e,t,n){if(e==null)return e;var r=[],a=0;return lr(e,r,"","",function(i){return t.call(n,i,a++)}),r}function Id(e){if(e._status===-1){var t=e._result;t=t(),t.then(function(n){(e._status===0||e._status===-1)&&(e._status=1,e._result=n)},function(n){(e._status===0||e._status===-1)&&(e._status=2,e._result=n)}),e._status===-1&&(e._status=0,e._result=t)}if(e._status===1)return e._result.default;throw e._result}var te={current:null},sr={transition:null},Bd={ReactCurrentDispatcher:te,ReactCurrentBatchConfig:sr,ReactCurrentOwner:Ha};function bl(){throw Error("act(...) is not supported in production builds of React.")}T.Children={map:or,forEach:function(e,t,n){or(e,function(){t.apply(this,arguments)},n)},count:function(e){var t=0;return or(e,function(){t++}),t},toArray:function(e){return or(e,function(t){return t})||[]},only:function(e){if(!Fa(e))throw Error("React.Children.only expected to receive a single React element child.");return e}};T.Component=Ht;T.Fragment=Cd;T.Profiler=Ld;T.PureComponent=Ma;T.StrictMode=Pd;T.Suspense=Hd;T.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED=Bd;T.act=bl;T.cloneElement=function(e,t,n){if(e==null)throw Error("React.cloneElement(...): The argument must be a React element, but you passed "+e+".");var r=fl({},e.props),a=e.key,i=e.ref,o=e._owner;if(t!=null){if(t.ref!==void 0&&(i=t.ref,o=Ha.current),t.key!==void 0&&(a=""+t.key),e.type&&e.type.defaultProps)var l=e.type.defaultProps;for(s in t)vl.call(t,s)&&!wl.hasOwnProperty(s)&&(r[s]=t[s]===void 0&&l!==void 0?l[s]:t[s])}var s=arguments.length-2;if(s===1)r.children=n;else if(1<s){l=Array(s);for(var c=0;c<s;c++)l[c]=arguments[c+2];r.children=l}return{$$typeof:pn,type:e.type,key:a,ref:i,props:r,_owner:o}};T.createContext=function(e){return e={$$typeof:Md,_currentValue:e,_currentValue2:e,_threadCount:0,Provider:null,Consumer:null,_defaultValue:null,_globalName:null},e.Provider={$$typeof:Ad,_context:e},e.Consumer=e};T.createElement=yl;T.createFactory=function(e){var t=yl.bind(null,e);return t.type=e,t};T.createRef=function(){return{current:null}};T.forwardRef=function(e){return{$$typeof:$d,render:e}};T.isValidElement=Fa;T.lazy=function(e){return{$$typeof:Nd,_payload:{_status:-1,_result:e},_init:Id}};T.memo=function(e,t){return{$$typeof:Fd,type:e,compare:t===void 0?null:t}};T.startTransition=function(e){var t=sr.transition;sr.transition={};try{e()}finally{sr.transition=t}};T.unstable_act=bl;T.useCallback=function(e,t){return te.current.useCallback(e,t)};T.useContext=function(e){return te.current.useContext(e)};T.useDebugValue=function(){};T.useDeferredValue=function(e){return te.current.useDeferredValue(e)};T.useEffect=function(e,t){return te.current.useEffect(e,t)};T.useId=function(){return te.current.useId()};T.useImperativeHandle=function(e,t,n){return te.current.useImperativeHandle(e,t,n)};T.useInsertionEffect=function(e,t){return te.current.useInsertionEffect(e,t)};T.useLayoutEffect=function(e,t){return te.current.useLayoutEffect(e,t)};T.useMemo=function(e,t){return te.current.useMemo(e,t)};T.useReducer=function(e,t,n){return te.current.useReducer(e,t,n)};T.useRef=function(e){return te.current.useRef(e)};T.useState=function(e){return te.current.useState(e)};T.useSyncExternalStore=function(e,t,n){return te.current.useSyncExternalStore(e,t,n)};T.useTransition=function(){return te.current.useTransition()};T.version="18.3.1"});var Oe=De((bp,kl)=>{"use strict";kl.exports=xl()});var Al=De(P=>{"use strict";function Wa(e,t){var n=e.length;e.push(t);e:for(;0<n;){var r=n-1>>>1,a=e[r];if(0<ur(a,t))e[r]=t,e[n]=a,n=r;else break e}}function Ee(e){return e.length===0?null:e[0]}function dr(e){if(e.length===0)return null;var t=e[0],n=e.pop();if(n!==t){e[0]=n;e:for(var r=0,a=e.length,i=a>>>1;r<i;){var o=2*(r+1)-1,l=e[o],s=o+1,c=e[s];if(0>ur(l,n))s<a&&0>ur(c,l)?(e[r]=c,e[s]=n,r=s):(e[r]=l,e[o]=n,r=o);else if(s<a&&0>ur(c,n))e[r]=c,e[s]=n,r=s;else break e}}return t}function ur(e,t){var n=e.sortIndex-t.sortIndex;return n!==0?n:e.id-t.id}typeof performance=="object"&&typeof performance.now=="function"?(Sl=performance,P.unstable_now=function(){return Sl.now()}):(Na=Date,El=Na.now(),P.unstable_now=function(){return Na.now()-El});var Sl,Na,El,Ae=[],Qe=[],Ud=1,ve=null,X=3,hr=!1,yt=!1,gn=!1,Rl=typeof setTimeout=="function"?setTimeout:null,_l=typeof clearTimeout=="function"?clearTimeout:null,zl=typeof setImmediate<"u"?setImmediate:null;typeof navigator<"u"&&navigator.scheduling!==void 0&&navigator.scheduling.isInputPending!==void 0&&navigator.scheduling.isInputPending.bind(navigator.scheduling);function Ia(e){for(var t=Ee(Qe);t!==null;){if(t.callback===null)dr(Qe);else if(t.startTime<=e)dr(Qe),t.sortIndex=t.expirationTime,Wa(Ae,t);else break;t=Ee(Qe)}}function Ba(e){if(gn=!1,Ia(e),!yt)if(Ee(Ae)!==null)yt=!0,Va(Ua);else{var t=Ee(Qe);t!==null&&qa(Ba,t.startTime-e)}}function Ua(e,t){yt=!1,gn&&(gn=!1,_l(mn),mn=-1),hr=!0;var n=X;try{for(Ia(t),ve=Ee(Ae);ve!==null&&(!(ve.expirationTime>t)||e&&!Ll());){var r=ve.callback;if(typeof r=="function"){ve.callback=null,X=ve.priorityLevel;var a=r(ve.expirationTime<=t);t=P.unstable_now(),typeof a=="function"?ve.callback=a:ve===Ee(Ae)&&dr(Ae),Ia(t)}else dr(Ae);ve=Ee(Ae)}if(ve!==null)var i=!0;else{var o=Ee(Qe);o!==null&&qa(Ba,o.startTime-t),i=!1}return i}finally{ve=null,X=n,hr=!1}}var pr=!1,cr=null,mn=-1,Cl=5,Pl=-1;function Ll(){return!(P.unstable_now()-Pl<Cl)}function Da(){if(cr!==null){var e=P.unstable_now();Pl=e;var t=!0;try{t=cr(!0,e)}finally{t?fn():(pr=!1,cr=null)}}else pr=!1}var fn;typeof zl=="function"?fn=function(){zl(Da)}:typeof MessageChannel<"u"?(Oa=new MessageChannel,Tl=Oa.port2,Oa.port1.onmessage=Da,fn=function(){Tl.postMessage(null)}):fn=function(){Rl(Da,0)};var Oa,Tl;function Va(e){cr=e,pr||(pr=!0,fn())}function qa(e,t){mn=Rl(function(){e(P.unstable_now())},t)}P.unstable_IdlePriority=5;P.unstable_ImmediatePriority=1;P.unstable_LowPriority=4;P.unstable_NormalPriority=3;P.unstable_Profiling=null;P.unstable_UserBlockingPriority=2;P.unstable_cancelCallback=function(e){e.callback=null};P.unstable_continueExecution=function(){yt||hr||(yt=!0,Va(Ua))};P.unstable_forceFrameRate=function(e){0>e||125<e?console.error("forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported"):Cl=0<e?Math.floor(1e3/e):5};P.unstable_getCurrentPriorityLevel=function(){return X};P.unstable_getFirstCallbackNode=function(){return Ee(Ae)};P.unstable_next=function(e){switch(X){case 1:case 2:case 3:var t=3;break;default:t=X}var n=X;X=t;try{return e()}finally{X=n}};P.unstable_pauseExecution=function(){};P.unstable_requestPaint=function(){};P.unstable_runWithPriority=function(e,t){switch(e){case 1:case 2:case 3:case 4:case 5:break;default:e=3}var n=X;X=e;try{return t()}finally{X=n}};P.unstable_scheduleCallback=function(e,t,n){var r=P.unstable_now();switch(typeof n=="object"&&n!==null?(n=n.delay,n=typeof n=="number"&&0<n?r+n:r):n=r,e){case 1:var a=-1;break;case 2:a=250;break;case 5:a=1073741823;break;case 4:a=1e4;break;default:a=5e3}return a=n+a,e={id:Ud++,callback:t,priorityLevel:e,startTime:n,expirationTime:a,sortIndex:-1},n>r?(e.sortIndex=n,Wa(Qe,e),Ee(Ae)===null&&e===Ee(Qe)&&(gn?(_l(mn),mn=-1):gn=!0,qa(Ba,n-r))):(e.sortIndex=a,Wa(Ae,e),yt||hr||(yt=!0,Va(Ua))),e};P.unstable_shouldYield=Ll;P.unstable_wrapCallback=function(e){var t=X;return function(){var n=X;X=t;try{return e.apply(this,arguments)}finally{X=n}}}});var $l=De((kp,Ml)=>{"use strict";Ml.exports=Al()});var Dc=De(me=>{"use strict";var Vd=Oe(),fe=$l();function v(e){for(var t="https://reactjs.org/docs/error-decoder.html?invariant="+e,n=1;n<arguments.length;n++)t+="&args[]="+encodeURIComponent(arguments[n]);return"Minified React error #"+e+"; visit "+t+" for the full message or use the non-minified dev environment for full errors and additional helpful warnings."}var Is=new Set,Dn={};function At(e,t){nn(e,t),nn(e+"Capture",t)}function nn(e,t){for(Dn[e]=t,e=0;e<t.length;e++)Is.add(t[e])}var qe=!(typeof window>"u"||typeof window.document>"u"||typeof window.document.createElement>"u"),fi=Object.prototype.hasOwnProperty,qd=/^[:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD][:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\-.0-9\u00B7\u0300-\u036F\u203F-\u2040]*$/,Hl={},Fl={};function jd(e){return fi.call(Fl,e)?!0:fi.call(Hl,e)?!1:qd.test(e)?Fl[e]=!0:(Hl[e]=!0,!1)}function Gd(e,t,n,r){if(n!==null&&n.type===0)return!1;switch(typeof t){case"function":case"symbol":return!0;case"boolean":return r?!1:n!==null?!n.acceptsBooleans:(e=e.toLowerCase().slice(0,5),e!=="data-"&&e!=="aria-");default:return!1}}function Kd(e,t,n,r){if(t===null||typeof t>"u"||Gd(e,t,n,r))return!0;if(r)return!1;if(n!==null)switch(n.type){case 3:return!t;case 4:return t===!1;case 5:return isNaN(t);case 6:return isNaN(t)||1>t}return!1}function ae(e,t,n,r,a,i,o){this.acceptsBooleans=t===2||t===3||t===4,this.attributeName=r,this.attributeNamespace=a,this.mustUseProperty=n,this.propertyName=e,this.type=t,this.sanitizeURL=i,this.removeEmptyString=o}var Y={};"children dangerouslySetInnerHTML defaultValue defaultChecked innerHTML suppressContentEditableWarning suppressHydrationWarning style".split(" ").forEach(function(e){Y[e]=new ae(e,0,!1,e,null,!1,!1)});[["acceptCharset","accept-charset"],["className","class"],["htmlFor","for"],["httpEquiv","http-equiv"]].forEach(function(e){var t=e[0];Y[t]=new ae(t,1,!1,e[1],null,!1,!1)});["contentEditable","draggable","spellCheck","value"].forEach(function(e){Y[e]=new ae(e,2,!1,e.toLowerCase(),null,!1,!1)});["autoReverse","externalResourcesRequired","focusable","preserveAlpha"].forEach(function(e){Y[e]=new ae(e,2,!1,e,null,!1,!1)});"allowFullScreen async autoFocus autoPlay controls default defer disabled disablePictureInPicture disableRemotePlayback formNoValidate hidden loop noModule noValidate open playsInline readOnly required reversed scoped seamless itemScope".split(" ").forEach(function(e){Y[e]=new ae(e,3,!1,e.toLowerCase(),null,!1,!1)});["checked","multiple","muted","selected"].forEach(function(e){Y[e]=new ae(e,3,!0,e,null,!1,!1)});["capture","download"].forEach(function(e){Y[e]=new ae(e,4,!1,e,null,!1,!1)});["cols","rows","size","span"].forEach(function(e){Y[e]=new ae(e,6,!1,e,null,!1,!1)});["rowSpan","start"].forEach(function(e){Y[e]=new ae(e,5,!1,e.toLowerCase(),null,!1,!1)});var oo=/[\-:]([a-z])/g;function lo(e){return e[1].toUpperCase()}"accent-height alignment-baseline arabic-form baseline-shift cap-height clip-path clip-rule color-interpolation color-interpolation-filters color-profile color-rendering dominant-baseline enable-background fill-opacity fill-rule flood-color flood-opacity font-family font-size font-size-adjust font-stretch font-style font-variant font-weight glyph-name glyph-orientation-horizontal glyph-orientation-vertical horiz-adv-x horiz-origin-x image-rendering letter-spacing lighting-color marker-end marker-mid marker-start overline-position overline-thickness paint-order panose-1 pointer-events rendering-intent shape-rendering stop-color stop-opacity strikethrough-position strikethrough-thickness stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity stroke-width text-anchor text-decoration text-rendering underline-position underline-thickness unicode-bidi unicode-range units-per-em v-alphabetic v-hanging v-ideographic v-mathematical vector-effect vert-adv-y vert-origin-x vert-origin-y word-spacing writing-mode xmlns:xlink x-height".split(" ").forEach(function(e){var t=e.replace(oo,lo);Y[t]=new ae(t,1,!1,e,null,!1,!1)});"xlink:actuate xlink:arcrole xlink:role xlink:show xlink:title xlink:type".split(" ").forEach(function(e){var t=e.replace(oo,lo);Y[t]=new ae(t,1,!1,e,"http://www.w3.org/1999/xlink",!1,!1)});["xml:base","xml:lang","xml:space"].forEach(function(e){var t=e.replace(oo,lo);Y[t]=new ae(t,1,!1,e,"http://www.w3.org/XML/1998/namespace",!1,!1)});["tabIndex","crossOrigin"].forEach(function(e){Y[e]=new ae(e,1,!1,e.toLowerCase(),null,!1,!1)});Y.xlinkHref=new ae("xlinkHref",1,!1,"xlink:href","http://www.w3.org/1999/xlink",!0,!1);["src","href","action","formAction"].forEach(function(e){Y[e]=new ae(e,1,!1,e.toLowerCase(),null,!0,!0)});function so(e,t,n,r){var a=Y.hasOwnProperty(t)?Y[t]:null;(a!==null?a.type!==0:r||!(2<t.length)||t[0]!=="o"&&t[0]!=="O"||t[1]!=="n"&&t[1]!=="N")&&(Kd(t,n,a,r)&&(n=null),r||a===null?jd(t)&&(n===null?e.removeAttribute(t):e.setAttribute(t,""+n)):a.mustUseProperty?e[a.propertyName]=n===null?a.type===3?!1:"":n:(t=a.attributeName,r=a.attributeNamespace,n===null?e.removeAttribute(t):(a=a.type,n=a===3||a===4&&n===!0?"":""+n,r?e.setAttributeNS(r,t,n):e.setAttribute(t,n))))}var Ye=Vd.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED,fr=Symbol.for("react.element"),Dt=Symbol.for("react.portal"),Ot=Symbol.for("react.fragment"),uo=Symbol.for("react.strict_mode"),gi=Symbol.for("react.profiler"),Bs=Symbol.for("react.provider"),Us=Symbol.for("react.context"),co=Symbol.for("react.forward_ref"),mi=Symbol.for("react.suspense"),vi=Symbol.for("react.suspense_list"),ho=Symbol.for("react.memo"),Je=Symbol.for("react.lazy");Symbol.for("react.scope");Symbol.for("react.debug_trace_mode");var Vs=Symbol.for("react.offscreen");Symbol.for("react.legacy_hidden");Symbol.for("react.cache");Symbol.for("react.tracing_marker");var Nl=Symbol.iterator;function vn(e){return e===null||typeof e!="object"?null:(e=Nl&&e[Nl]||e["@@iterator"],typeof e=="function"?e:null)}var O=Object.assign,ja;function zn(e){if(ja===void 0)try{throw Error()}catch(n){var t=n.stack.trim().match(/\n( *(at )?)/);ja=t&&t[1]||""}return`
`+ja+e}var Ga=!1;function Ka(e,t){if(!e||Ga)return"";Ga=!0;var n=Error.prepareStackTrace;Error.prepareStackTrace=void 0;try{if(t)if(t=function(){throw Error()},Object.defineProperty(t.prototype,"props",{set:function(){throw Error()}}),typeof Reflect=="object"&&Reflect.construct){try{Reflect.construct(t,[])}catch(c){var r=c}Reflect.construct(e,[],t)}else{try{t.call()}catch(c){r=c}e.call(t.prototype)}else{try{throw Error()}catch(c){r=c}e()}}catch(c){if(c&&r&&typeof c.stack=="string"){for(var a=c.stack.split(`
`),i=r.stack.split(`
`),o=a.length-1,l=i.length-1;1<=o&&0<=l&&a[o]!==i[l];)l--;for(;1<=o&&0<=l;o--,l--)if(a[o]!==i[l]){if(o!==1||l!==1)do if(o--,l--,0>l||a[o]!==i[l]){var s=`
`+a[o].replace(" at new "," at ");return e.displayName&&s.includes("<anonymous>")&&(s=s.replace("<anonymous>",e.displayName)),s}while(1<=o&&0<=l);break}}}finally{Ga=!1,Error.prepareStackTrace=n}return(e=e?e.displayName||e.name:"")?zn(e):""}function Yd(e){switch(e.tag){case 5:return zn(e.type);case 16:return zn("Lazy");case 13:return zn("Suspense");case 19:return zn("SuspenseList");case 0:case 2:case 15:return e=Ka(e.type,!1),e;case 11:return e=Ka(e.type.render,!1),e;case 1:return e=Ka(e.type,!0),e;default:return""}}function wi(e){if(e==null)return null;if(typeof e=="function")return e.displayName||e.name||null;if(typeof e=="string")return e;switch(e){case Ot:return"Fragment";case Dt:return"Portal";case gi:return"Profiler";case uo:return"StrictMode";case mi:return"Suspense";case vi:return"SuspenseList"}if(typeof e=="object")switch(e.$$typeof){case Us:return(e.displayName||"Context")+".Consumer";case Bs:return(e._context.displayName||"Context")+".Provider";case co:var t=e.render;return e=e.displayName,e||(e=t.displayName||t.name||"",e=e!==""?"ForwardRef("+e+")":"ForwardRef"),e;case ho:return t=e.displayName||null,t!==null?t:wi(e.type)||"Memo";case Je:t=e._payload,e=e._init;try{return wi(e(t))}catch{}}return null}function Xd(e){var t=e.type;switch(e.tag){case 24:return"Cache";case 9:return(t.displayName||"Context")+".Consumer";case 10:return(t._context.displayName||"Context")+".Provider";case 18:return"DehydratedFragment";case 11:return e=t.render,e=e.displayName||e.name||"",t.displayName||(e!==""?"ForwardRef("+e+")":"ForwardRef");case 7:return"Fragment";case 5:return t;case 4:return"Portal";case 3:return"Root";case 6:return"Text";case 16:return wi(t);case 8:return t===uo?"StrictMode":"Mode";case 22:return"Offscreen";case 12:return"Profiler";case 21:return"Scope";case 13:return"Suspense";case 19:return"SuspenseList";case 25:return"TracingMarker";case 1:case 0:case 17:case 2:case 14:case 15:if(typeof t=="function")return t.displayName||t.name||null;if(typeof t=="string")return t}return null}function pt(e){switch(typeof e){case"boolean":case"number":case"string":case"undefined":return e;case"object":return e;default:return""}}function qs(e){var t=e.type;return(e=e.nodeName)&&e.toLowerCase()==="input"&&(t==="checkbox"||t==="radio")}function Qd(e){var t=qs(e)?"checked":"value",n=Object.getOwnPropertyDescriptor(e.constructor.prototype,t),r=""+e[t];if(!e.hasOwnProperty(t)&&typeof n<"u"&&typeof n.get=="function"&&typeof n.set=="function"){var a=n.get,i=n.set;return Object.defineProperty(e,t,{configurable:!0,get:function(){return a.call(this)},set:function(o){r=""+o,i.call(this,o)}}),Object.defineProperty(e,t,{enumerable:n.enumerable}),{getValue:function(){return r},setValue:function(o){r=""+o},stopTracking:function(){e._valueTracker=null,delete e[t]}}}}function gr(e){e._valueTracker||(e._valueTracker=Qd(e))}function js(e){if(!e)return!1;var t=e._valueTracker;if(!t)return!0;var n=t.getValue(),r="";return e&&(r=qs(e)?e.checked?"true":"false":e.value),e=r,e!==n?(t.setValue(e),!0):!1}function Ur(e){if(e=e||(typeof document<"u"?document:void 0),typeof e>"u")return null;try{return e.activeElement||e.body}catch{return e.body}}function yi(e,t){var n=t.checked;return O({},t,{defaultChecked:void 0,defaultValue:void 0,value:void 0,checked:n??e._wrapperState.initialChecked})}function Dl(e,t){var n=t.defaultValue==null?"":t.defaultValue,r=t.checked!=null?t.checked:t.defaultChecked;n=pt(t.value!=null?t.value:n),e._wrapperState={initialChecked:r,initialValue:n,controlled:t.type==="checkbox"||t.type==="radio"?t.checked!=null:t.value!=null}}function Gs(e,t){t=t.checked,t!=null&&so(e,"checked",t,!1)}function bi(e,t){Gs(e,t);var n=pt(t.value),r=t.type;if(n!=null)r==="number"?(n===0&&e.value===""||e.value!=n)&&(e.value=""+n):e.value!==""+n&&(e.value=""+n);else if(r==="submit"||r==="reset"){e.removeAttribute("value");return}t.hasOwnProperty("value")?xi(e,t.type,n):t.hasOwnProperty("defaultValue")&&xi(e,t.type,pt(t.defaultValue)),t.checked==null&&t.defaultChecked!=null&&(e.defaultChecked=!!t.defaultChecked)}function Ol(e,t,n){if(t.hasOwnProperty("value")||t.hasOwnProperty("defaultValue")){var r=t.type;if(!(r!=="submit"&&r!=="reset"||t.value!==void 0&&t.value!==null))return;t=""+e._wrapperState.initialValue,n||t===e.value||(e.value=t),e.defaultValue=t}n=e.name,n!==""&&(e.name=""),e.defaultChecked=!!e._wrapperState.initialChecked,n!==""&&(e.name=n)}function xi(e,t,n){(t!=="number"||Ur(e.ownerDocument)!==e)&&(n==null?e.defaultValue=""+e._wrapperState.initialValue:e.defaultValue!==""+n&&(e.defaultValue=""+n))}var Tn=Array.isArray;function Xt(e,t,n,r){if(e=e.options,t){t={};for(var a=0;a<n.length;a++)t["$"+n[a]]=!0;for(n=0;n<e.length;n++)a=t.hasOwnProperty("$"+e[n].value),e[n].selected!==a&&(e[n].selected=a),a&&r&&(e[n].defaultSelected=!0)}else{for(n=""+pt(n),t=null,a=0;a<e.length;a++){if(e[a].value===n){e[a].selected=!0,r&&(e[a].defaultSelected=!0);return}t!==null||e[a].disabled||(t=e[a])}t!==null&&(t.selected=!0)}}function ki(e,t){if(t.dangerouslySetInnerHTML!=null)throw Error(v(91));return O({},t,{value:void 0,defaultValue:void 0,children:""+e._wrapperState.initialValue})}function Wl(e,t){var n=t.value;if(n==null){if(n=t.children,t=t.defaultValue,n!=null){if(t!=null)throw Error(v(92));if(Tn(n)){if(1<n.length)throw Error(v(93));n=n[0]}t=n}t==null&&(t=""),n=t}e._wrapperState={initialValue:pt(n)}}function Ks(e,t){var n=pt(t.value),r=pt(t.defaultValue);n!=null&&(n=""+n,n!==e.value&&(e.value=n),t.defaultValue==null&&e.defaultValue!==n&&(e.defaultValue=n)),r!=null&&(e.defaultValue=""+r)}function Il(e){var t=e.textContent;t===e._wrapperState.initialValue&&t!==""&&t!==null&&(e.value=t)}function Ys(e){switch(e){case"svg":return"http://www.w3.org/2000/svg";case"math":return"http://www.w3.org/1998/Math/MathML";default:return"http://www.w3.org/1999/xhtml"}}function Si(e,t){return e==null||e==="http://www.w3.org/1999/xhtml"?Ys(t):e==="http://www.w3.org/2000/svg"&&t==="foreignObject"?"http://www.w3.org/1999/xhtml":e}var mr,Xs=(function(e){return typeof MSApp<"u"&&MSApp.execUnsafeLocalFunction?function(t,n,r,a){MSApp.execUnsafeLocalFunction(function(){return e(t,n,r,a)})}:e})(function(e,t){if(e.namespaceURI!=="http://www.w3.org/2000/svg"||"innerHTML"in e)e.innerHTML=t;else{for(mr=mr||document.createElement("div"),mr.innerHTML="<svg>"+t.valueOf().toString()+"</svg>",t=mr.firstChild;e.firstChild;)e.removeChild(e.firstChild);for(;t.firstChild;)e.appendChild(t.firstChild)}});function On(e,t){if(t){var n=e.firstChild;if(n&&n===e.lastChild&&n.nodeType===3){n.nodeValue=t;return}}e.textContent=t}var Cn={animationIterationCount:!0,aspectRatio:!0,borderImageOutset:!0,borderImageSlice:!0,borderImageWidth:!0,boxFlex:!0,boxFlexGroup:!0,boxOrdinalGroup:!0,columnCount:!0,columns:!0,flex:!0,flexGrow:!0,flexPositive:!0,flexShrink:!0,flexNegative:!0,flexOrder:!0,gridArea:!0,gridRow:!0,gridRowEnd:!0,gridRowSpan:!0,gridRowStart:!0,gridColumn:!0,gridColumnEnd:!0,gridColumnSpan:!0,gridColumnStart:!0,fontWeight:!0,lineClamp:!0,lineHeight:!0,opacity:!0,order:!0,orphans:!0,tabSize:!0,widows:!0,zIndex:!0,zoom:!0,fillOpacity:!0,floodOpacity:!0,stopOpacity:!0,strokeDasharray:!0,strokeDashoffset:!0,strokeMiterlimit:!0,strokeOpacity:!0,strokeWidth:!0},Zd=["Webkit","ms","Moz","O"];Object.keys(Cn).forEach(function(e){Zd.forEach(function(t){t=t+e.charAt(0).toUpperCase()+e.substring(1),Cn[t]=Cn[e]})});function Qs(e,t,n){return t==null||typeof t=="boolean"||t===""?"":n||typeof t!="number"||t===0||Cn.hasOwnProperty(e)&&Cn[e]?(""+t).trim():t+"px"}function Zs(e,t){e=e.style;for(var n in t)if(t.hasOwnProperty(n)){var r=n.indexOf("--")===0,a=Qs(n,t[n],r);n==="float"&&(n="cssFloat"),r?e.setProperty(n,a):e[n]=a}}var Jd=O({menuitem:!0},{area:!0,base:!0,br:!0,col:!0,embed:!0,hr:!0,img:!0,input:!0,keygen:!0,link:!0,meta:!0,param:!0,source:!0,track:!0,wbr:!0});function Ei(e,t){if(t){if(Jd[e]&&(t.children!=null||t.dangerouslySetInnerHTML!=null))throw Error(v(137,e));if(t.dangerouslySetInnerHTML!=null){if(t.children!=null)throw Error(v(60));if(typeof t.dangerouslySetInnerHTML!="object"||!("__html"in t.dangerouslySetInnerHTML))throw Error(v(61))}if(t.style!=null&&typeof t.style!="object")throw Error(v(62))}}function zi(e,t){if(e.indexOf("-")===-1)return typeof t.is=="string";switch(e){case"annotation-xml":case"color-profile":case"font-face":case"font-face-src":case"font-face-uri":case"font-face-format":case"font-face-name":case"missing-glyph":return!1;default:return!0}}var Ti=null;function po(e){return e=e.target||e.srcElement||window,e.correspondingUseElement&&(e=e.correspondingUseElement),e.nodeType===3?e.parentNode:e}var Ri=null,Qt=null,Zt=null;function Bl(e){if(e=rr(e)){if(typeof Ri!="function")throw Error(v(280));var t=e.stateNode;t&&(t=va(t),Ri(e.stateNode,e.type,t))}}function Js(e){Qt?Zt?Zt.push(e):Zt=[e]:Qt=e}function eu(){if(Qt){var e=Qt,t=Zt;if(Zt=Qt=null,Bl(e),t)for(e=0;e<t.length;e++)Bl(t[e])}}function tu(e,t){return e(t)}function nu(){}var Ya=!1;function ru(e,t,n){if(Ya)return e(t,n);Ya=!0;try{return tu(e,t,n)}finally{Ya=!1,(Qt!==null||Zt!==null)&&(nu(),eu())}}function Wn(e,t){var n=e.stateNode;if(n===null)return null;var r=va(n);if(r===null)return null;n=r[t];e:switch(t){case"onClick":case"onClickCapture":case"onDoubleClick":case"onDoubleClickCapture":case"onMouseDown":case"onMouseDownCapture":case"onMouseMove":case"onMouseMoveCapture":case"onMouseUp":case"onMouseUpCapture":case"onMouseEnter":(r=!r.disabled)||(e=e.type,r=!(e==="button"||e==="input"||e==="select"||e==="textarea")),e=!r;break e;default:e=!1}if(e)return null;if(n&&typeof n!="function")throw Error(v(231,t,typeof n));return n}var _i=!1;if(qe)try{Ft={},Object.defineProperty(Ft,"passive",{get:function(){_i=!0}}),window.addEventListener("test",Ft,Ft),window.removeEventListener("test",Ft,Ft)}catch{_i=!1}var Ft;function e0(e,t,n,r,a,i,o,l,s){var c=Array.prototype.slice.call(arguments,3);try{t.apply(n,c)}catch(f){this.onError(f)}}var Pn=!1,Vr=null,qr=!1,Ci=null,t0={onError:function(e){Pn=!0,Vr=e}};function n0(e,t,n,r,a,i,o,l,s){Pn=!1,Vr=null,e0.apply(t0,arguments)}function r0(e,t,n,r,a,i,o,l,s){if(n0.apply(this,arguments),Pn){if(Pn){var c=Vr;Pn=!1,Vr=null}else throw Error(v(198));qr||(qr=!0,Ci=c)}}function Mt(e){var t=e,n=e;if(e.alternate)for(;t.return;)t=t.return;else{e=t;do t=e,(t.flags&4098)!==0&&(n=t.return),e=t.return;while(e)}return t.tag===3?n:null}function au(e){if(e.tag===13){var t=e.memoizedState;if(t===null&&(e=e.alternate,e!==null&&(t=e.memoizedState)),t!==null)return t.dehydrated}return null}function Ul(e){if(Mt(e)!==e)throw Error(v(188))}function a0(e){var t=e.alternate;if(!t){if(t=Mt(e),t===null)throw Error(v(188));return t!==e?null:e}for(var n=e,r=t;;){var a=n.return;if(a===null)break;var i=a.alternate;if(i===null){if(r=a.return,r!==null){n=r;continue}break}if(a.child===i.child){for(i=a.child;i;){if(i===n)return Ul(a),e;if(i===r)return Ul(a),t;i=i.sibling}throw Error(v(188))}if(n.return!==r.return)n=a,r=i;else{for(var o=!1,l=a.child;l;){if(l===n){o=!0,n=a,r=i;break}if(l===r){o=!0,r=a,n=i;break}l=l.sibling}if(!o){for(l=i.child;l;){if(l===n){o=!0,n=i,r=a;break}if(l===r){o=!0,r=i,n=a;break}l=l.sibling}if(!o)throw Error(v(189))}}if(n.alternate!==r)throw Error(v(190))}if(n.tag!==3)throw Error(v(188));return n.stateNode.current===n?e:t}function iu(e){return e=a0(e),e!==null?ou(e):null}function ou(e){if(e.tag===5||e.tag===6)return e;for(e=e.child;e!==null;){var t=ou(e);if(t!==null)return t;e=e.sibling}return null}var lu=fe.unstable_scheduleCallback,Vl=fe.unstable_cancelCallback,i0=fe.unstable_shouldYield,o0=fe.unstable_requestPaint,I=fe.unstable_now,l0=fe.unstable_getCurrentPriorityLevel,fo=fe.unstable_ImmediatePriority,su=fe.unstable_UserBlockingPriority,jr=fe.unstable_NormalPriority,s0=fe.unstable_LowPriority,uu=fe.unstable_IdlePriority,pa=null,Fe=null;function u0(e){if(Fe&&typeof Fe.onCommitFiberRoot=="function")try{Fe.onCommitFiberRoot(pa,e,void 0,(e.current.flags&128)===128)}catch{}}var Ce=Math.clz32?Math.clz32:h0,c0=Math.log,d0=Math.LN2;function h0(e){return e>>>=0,e===0?32:31-(c0(e)/d0|0)|0}var vr=64,wr=4194304;function Rn(e){switch(e&-e){case 1:return 1;case 2:return 2;case 4:return 4;case 8:return 8;case 16:return 16;case 32:return 32;case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:return e&4194240;case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:return e&130023424;case 134217728:return 134217728;case 268435456:return 268435456;case 536870912:return 536870912;case 1073741824:return 1073741824;default:return e}}function Gr(e,t){var n=e.pendingLanes;if(n===0)return 0;var r=0,a=e.suspendedLanes,i=e.pingedLanes,o=n&268435455;if(o!==0){var l=o&~a;l!==0?r=Rn(l):(i&=o,i!==0&&(r=Rn(i)))}else o=n&~a,o!==0?r=Rn(o):i!==0&&(r=Rn(i));if(r===0)return 0;if(t!==0&&t!==r&&(t&a)===0&&(a=r&-r,i=t&-t,a>=i||a===16&&(i&4194240)!==0))return t;if((r&4)!==0&&(r|=n&16),t=e.entangledLanes,t!==0)for(e=e.entanglements,t&=r;0<t;)n=31-Ce(t),a=1<<n,r|=e[n],t&=~a;return r}function p0(e,t){switch(e){case 1:case 2:case 4:return t+250;case 8:case 16:case 32:case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:return t+5e3;case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:return-1;case 134217728:case 268435456:case 536870912:case 1073741824:return-1;default:return-1}}function f0(e,t){for(var n=e.suspendedLanes,r=e.pingedLanes,a=e.expirationTimes,i=e.pendingLanes;0<i;){var o=31-Ce(i),l=1<<o,s=a[o];s===-1?((l&n)===0||(l&r)!==0)&&(a[o]=p0(l,t)):s<=t&&(e.expiredLanes|=l),i&=~l}}function Pi(e){return e=e.pendingLanes&-1073741825,e!==0?e:e&1073741824?1073741824:0}function cu(){var e=vr;return vr<<=1,(vr&4194240)===0&&(vr=64),e}function Xa(e){for(var t=[],n=0;31>n;n++)t.push(e);return t}function tr(e,t,n){e.pendingLanes|=t,t!==536870912&&(e.suspendedLanes=0,e.pingedLanes=0),e=e.eventTimes,t=31-Ce(t),e[t]=n}function g0(e,t){var n=e.pendingLanes&~t;e.pendingLanes=t,e.suspendedLanes=0,e.pingedLanes=0,e.expiredLanes&=t,e.mutableReadLanes&=t,e.entangledLanes&=t,t=e.entanglements;var r=e.eventTimes;for(e=e.expirationTimes;0<n;){var a=31-Ce(n),i=1<<a;t[a]=0,r[a]=-1,e[a]=-1,n&=~i}}function go(e,t){var n=e.entangledLanes|=t;for(e=e.entanglements;n;){var r=31-Ce(n),a=1<<r;a&t|e[r]&t&&(e[r]|=t),n&=~a}}var C=0;function du(e){return e&=-e,1<e?4<e?(e&268435455)!==0?16:536870912:4:1}var hu,mo,pu,fu,gu,Li=!1,yr=[],it=null,ot=null,lt=null,In=new Map,Bn=new Map,tt=[],m0="mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset submit".split(" ");function ql(e,t){switch(e){case"focusin":case"focusout":it=null;break;case"dragenter":case"dragleave":ot=null;break;case"mouseover":case"mouseout":lt=null;break;case"pointerover":case"pointerout":In.delete(t.pointerId);break;case"gotpointercapture":case"lostpointercapture":Bn.delete(t.pointerId)}}function wn(e,t,n,r,a,i){return e===null||e.nativeEvent!==i?(e={blockedOn:t,domEventName:n,eventSystemFlags:r,nativeEvent:i,targetContainers:[a]},t!==null&&(t=rr(t),t!==null&&mo(t)),e):(e.eventSystemFlags|=r,t=e.targetContainers,a!==null&&t.indexOf(a)===-1&&t.push(a),e)}function v0(e,t,n,r,a){switch(t){case"focusin":return it=wn(it,e,t,n,r,a),!0;case"dragenter":return ot=wn(ot,e,t,n,r,a),!0;case"mouseover":return lt=wn(lt,e,t,n,r,a),!0;case"pointerover":var i=a.pointerId;return In.set(i,wn(In.get(i)||null,e,t,n,r,a)),!0;case"gotpointercapture":return i=a.pointerId,Bn.set(i,wn(Bn.get(i)||null,e,t,n,r,a)),!0}return!1}function mu(e){var t=kt(e.target);if(t!==null){var n=Mt(t);if(n!==null){if(t=n.tag,t===13){if(t=au(n),t!==null){e.blockedOn=t,gu(e.priority,function(){pu(n)});return}}else if(t===3&&n.stateNode.current.memoizedState.isDehydrated){e.blockedOn=n.tag===3?n.stateNode.containerInfo:null;return}}}e.blockedOn=null}function Mr(e){if(e.blockedOn!==null)return!1;for(var t=e.targetContainers;0<t.length;){var n=Ai(e.domEventName,e.eventSystemFlags,t[0],e.nativeEvent);if(n===null){n=e.nativeEvent;var r=new n.constructor(n.type,n);Ti=r,n.target.dispatchEvent(r),Ti=null}else return t=rr(n),t!==null&&mo(t),e.blockedOn=n,!1;t.shift()}return!0}function jl(e,t,n){Mr(e)&&n.delete(t)}function w0(){Li=!1,it!==null&&Mr(it)&&(it=null),ot!==null&&Mr(ot)&&(ot=null),lt!==null&&Mr(lt)&&(lt=null),In.forEach(jl),Bn.forEach(jl)}function yn(e,t){e.blockedOn===t&&(e.blockedOn=null,Li||(Li=!0,fe.unstable_scheduleCallback(fe.unstable_NormalPriority,w0)))}function Un(e){function t(a){return yn(a,e)}if(0<yr.length){yn(yr[0],e);for(var n=1;n<yr.length;n++){var r=yr[n];r.blockedOn===e&&(r.blockedOn=null)}}for(it!==null&&yn(it,e),ot!==null&&yn(ot,e),lt!==null&&yn(lt,e),In.forEach(t),Bn.forEach(t),n=0;n<tt.length;n++)r=tt[n],r.blockedOn===e&&(r.blockedOn=null);for(;0<tt.length&&(n=tt[0],n.blockedOn===null);)mu(n),n.blockedOn===null&&tt.shift()}var Jt=Ye.ReactCurrentBatchConfig,Kr=!0;function y0(e,t,n,r){var a=C,i=Jt.transition;Jt.transition=null;try{C=1,vo(e,t,n,r)}finally{C=a,Jt.transition=i}}function b0(e,t,n,r){var a=C,i=Jt.transition;Jt.transition=null;try{C=4,vo(e,t,n,r)}finally{C=a,Jt.transition=i}}function vo(e,t,n,r){if(Kr){var a=Ai(e,t,n,r);if(a===null)ri(e,t,r,Yr,n),ql(e,r);else if(v0(a,e,t,n,r))r.stopPropagation();else if(ql(e,r),t&4&&-1<m0.indexOf(e)){for(;a!==null;){var i=rr(a);if(i!==null&&hu(i),i=Ai(e,t,n,r),i===null&&ri(e,t,r,Yr,n),i===a)break;a=i}a!==null&&r.stopPropagation()}else ri(e,t,r,null,n)}}var Yr=null;function Ai(e,t,n,r){if(Yr=null,e=po(r),e=kt(e),e!==null)if(t=Mt(e),t===null)e=null;else if(n=t.tag,n===13){if(e=au(t),e!==null)return e;e=null}else if(n===3){if(t.stateNode.current.memoizedState.isDehydrated)return t.tag===3?t.stateNode.containerInfo:null;e=null}else t!==e&&(e=null);return Yr=e,null}function vu(e){switch(e){case"cancel":case"click":case"close":case"contextmenu":case"copy":case"cut":case"auxclick":case"dblclick":case"dragend":case"dragstart":case"drop":case"focusin":case"focusout":case"input":case"invalid":case"keydown":case"keypress":case"keyup":case"mousedown":case"mouseup":case"paste":case"pause":case"play":case"pointercancel":case"pointerdown":case"pointerup":case"ratechange":case"reset":case"resize":case"seeked":case"submit":case"touchcancel":case"touchend":case"touchstart":case"volumechange":case"change":case"selectionchange":case"textInput":case"compositionstart":case"compositionend":case"compositionupdate":case"beforeblur":case"afterblur":case"beforeinput":case"blur":case"fullscreenchange":case"focus":case"hashchange":case"popstate":case"select":case"selectstart":return 1;case"drag":case"dragenter":case"dragexit":case"dragleave":case"dragover":case"mousemove":case"mouseout":case"mouseover":case"pointermove":case"pointerout":case"pointerover":case"scroll":case"toggle":case"touchmove":case"wheel":case"mouseenter":case"mouseleave":case"pointerenter":case"pointerleave":return 4;case"message":switch(l0()){case fo:return 1;case su:return 4;case jr:case s0:return 16;case uu:return 536870912;default:return 16}default:return 16}}var rt=null,wo=null,$r=null;function wu(){if($r)return $r;var e,t=wo,n=t.length,r,a="value"in rt?rt.value:rt.textContent,i=a.length;for(e=0;e<n&&t[e]===a[e];e++);var o=n-e;for(r=1;r<=o&&t[n-r]===a[i-r];r++);return $r=a.slice(e,1<r?1-r:void 0)}function Hr(e){var t=e.keyCode;return"charCode"in e?(e=e.charCode,e===0&&t===13&&(e=13)):e=t,e===10&&(e=13),32<=e||e===13?e:0}function br(){return!0}function Gl(){return!1}function ge(e){function t(n,r,a,i,o){this._reactName=n,this._targetInst=a,this.type=r,this.nativeEvent=i,this.target=o,this.currentTarget=null;for(var l in e)e.hasOwnProperty(l)&&(n=e[l],this[l]=n?n(i):i[l]);return this.isDefaultPrevented=(i.defaultPrevented!=null?i.defaultPrevented:i.returnValue===!1)?br:Gl,this.isPropagationStopped=Gl,this}return O(t.prototype,{preventDefault:function(){this.defaultPrevented=!0;var n=this.nativeEvent;n&&(n.preventDefault?n.preventDefault():typeof n.returnValue!="unknown"&&(n.returnValue=!1),this.isDefaultPrevented=br)},stopPropagation:function(){var n=this.nativeEvent;n&&(n.stopPropagation?n.stopPropagation():typeof n.cancelBubble!="unknown"&&(n.cancelBubble=!0),this.isPropagationStopped=br)},persist:function(){},isPersistent:br}),t}var cn={eventPhase:0,bubbles:0,cancelable:0,timeStamp:function(e){return e.timeStamp||Date.now()},defaultPrevented:0,isTrusted:0},yo=ge(cn),nr=O({},cn,{view:0,detail:0}),x0=ge(nr),Qa,Za,bn,fa=O({},nr,{screenX:0,screenY:0,clientX:0,clientY:0,pageX:0,pageY:0,ctrlKey:0,shiftKey:0,altKey:0,metaKey:0,getModifierState:bo,button:0,buttons:0,relatedTarget:function(e){return e.relatedTarget===void 0?e.fromElement===e.srcElement?e.toElement:e.fromElement:e.relatedTarget},movementX:function(e){return"movementX"in e?e.movementX:(e!==bn&&(bn&&e.type==="mousemove"?(Qa=e.screenX-bn.screenX,Za=e.screenY-bn.screenY):Za=Qa=0,bn=e),Qa)},movementY:function(e){return"movementY"in e?e.movementY:Za}}),Kl=ge(fa),k0=O({},fa,{dataTransfer:0}),S0=ge(k0),E0=O({},nr,{relatedTarget:0}),Ja=ge(E0),z0=O({},cn,{animationName:0,elapsedTime:0,pseudoElement:0}),T0=ge(z0),R0=O({},cn,{clipboardData:function(e){return"clipboardData"in e?e.clipboardData:window.clipboardData}}),_0=ge(R0),C0=O({},cn,{data:0}),Yl=ge(C0),P0={Esc:"Escape",Spacebar:" ",Left:"ArrowLeft",Up:"ArrowUp",Right:"ArrowRight",Down:"ArrowDown",Del:"Delete",Win:"OS",Menu:"ContextMenu",Apps:"ContextMenu",Scroll:"ScrollLock",MozPrintableKey:"Unidentified"},L0={8:"Backspace",9:"Tab",12:"Clear",13:"Enter",16:"Shift",17:"Control",18:"Alt",19:"Pause",20:"CapsLock",27:"Escape",32:" ",33:"PageUp",34:"PageDown",35:"End",36:"Home",37:"ArrowLeft",38:"ArrowUp",39:"ArrowRight",40:"ArrowDown",45:"Insert",46:"Delete",112:"F1",113:"F2",114:"F3",115:"F4",116:"F5",117:"F6",118:"F7",119:"F8",120:"F9",121:"F10",122:"F11",123:"F12",144:"NumLock",145:"ScrollLock",224:"Meta"},A0={Alt:"altKey",Control:"ctrlKey",Meta:"metaKey",Shift:"shiftKey"};function M0(e){var t=this.nativeEvent;return t.getModifierState?t.getModifierState(e):(e=A0[e])?!!t[e]:!1}function bo(){return M0}var $0=O({},nr,{key:function(e){if(e.key){var t=P0[e.key]||e.key;if(t!=="Unidentified")return t}return e.type==="keypress"?(e=Hr(e),e===13?"Enter":String.fromCharCode(e)):e.type==="keydown"||e.type==="keyup"?L0[e.keyCode]||"Unidentified":""},code:0,location:0,ctrlKey:0,shiftKey:0,altKey:0,metaKey:0,repeat:0,locale:0,getModifierState:bo,charCode:function(e){return e.type==="keypress"?Hr(e):0},keyCode:function(e){return e.type==="keydown"||e.type==="keyup"?e.keyCode:0},which:function(e){return e.type==="keypress"?Hr(e):e.type==="keydown"||e.type==="keyup"?e.keyCode:0}}),H0=ge($0),F0=O({},fa,{pointerId:0,width:0,height:0,pressure:0,tangentialPressure:0,tiltX:0,tiltY:0,twist:0,pointerType:0,isPrimary:0}),Xl=ge(F0),N0=O({},nr,{touches:0,targetTouches:0,changedTouches:0,altKey:0,metaKey:0,ctrlKey:0,shiftKey:0,getModifierState:bo}),D0=ge(N0),O0=O({},cn,{propertyName:0,elapsedTime:0,pseudoElement:0}),W0=ge(O0),I0=O({},fa,{deltaX:function(e){return"deltaX"in e?e.deltaX:"wheelDeltaX"in e?-e.wheelDeltaX:0},deltaY:function(e){return"deltaY"in e?e.deltaY:"wheelDeltaY"in e?-e.wheelDeltaY:"wheelDelta"in e?-e.wheelDelta:0},deltaZ:0,deltaMode:0}),B0=ge(I0),U0=[9,13,27,32],xo=qe&&"CompositionEvent"in window,Ln=null;qe&&"documentMode"in document&&(Ln=document.documentMode);var V0=qe&&"TextEvent"in window&&!Ln,yu=qe&&(!xo||Ln&&8<Ln&&11>=Ln),Ql=" ",Zl=!1;function bu(e,t){switch(e){case"keyup":return U0.indexOf(t.keyCode)!==-1;case"keydown":return t.keyCode!==229;case"keypress":case"mousedown":case"focusout":return!0;default:return!1}}function xu(e){return e=e.detail,typeof e=="object"&&"data"in e?e.data:null}var Wt=!1;function q0(e,t){switch(e){case"compositionend":return xu(t);case"keypress":return t.which!==32?null:(Zl=!0,Ql);case"textInput":return e=t.data,e===Ql&&Zl?null:e;default:return null}}function j0(e,t){if(Wt)return e==="compositionend"||!xo&&bu(e,t)?(e=wu(),$r=wo=rt=null,Wt=!1,e):null;switch(e){case"paste":return null;case"keypress":if(!(t.ctrlKey||t.altKey||t.metaKey)||t.ctrlKey&&t.altKey){if(t.char&&1<t.char.length)return t.char;if(t.which)return String.fromCharCode(t.which)}return null;case"compositionend":return yu&&t.locale!=="ko"?null:t.data;default:return null}}var G0={color:!0,date:!0,datetime:!0,"datetime-local":!0,email:!0,month:!0,number:!0,password:!0,range:!0,search:!0,tel:!0,text:!0,time:!0,url:!0,week:!0};function Jl(e){var t=e&&e.nodeName&&e.nodeName.toLowerCase();return t==="input"?!!G0[e.type]:t==="textarea"}function ku(e,t,n,r){Js(r),t=Xr(t,"onChange"),0<t.length&&(n=new yo("onChange","change",null,n,r),e.push({event:n,listeners:t}))}var An=null,Vn=null;function K0(e){Mu(e,0)}function ga(e){var t=Ut(e);if(js(t))return e}function Y0(e,t){if(e==="change")return t}var Su=!1;qe&&(qe?(kr="oninput"in document,kr||(ei=document.createElement("div"),ei.setAttribute("oninput","return;"),kr=typeof ei.oninput=="function"),xr=kr):xr=!1,Su=xr&&(!document.documentMode||9<document.documentMode));var xr,kr,ei;function es(){An&&(An.detachEvent("onpropertychange",Eu),Vn=An=null)}function Eu(e){if(e.propertyName==="value"&&ga(Vn)){var t=[];ku(t,Vn,e,po(e)),ru(K0,t)}}function X0(e,t,n){e==="focusin"?(es(),An=t,Vn=n,An.attachEvent("onpropertychange",Eu)):e==="focusout"&&es()}function Q0(e){if(e==="selectionchange"||e==="keyup"||e==="keydown")return ga(Vn)}function Z0(e,t){if(e==="click")return ga(t)}function J0(e,t){if(e==="input"||e==="change")return ga(t)}function eh(e,t){return e===t&&(e!==0||1/e===1/t)||e!==e&&t!==t}var Le=typeof Object.is=="function"?Object.is:eh;function qn(e,t){if(Le(e,t))return!0;if(typeof e!="object"||e===null||typeof t!="object"||t===null)return!1;var n=Object.keys(e),r=Object.keys(t);if(n.length!==r.length)return!1;for(r=0;r<n.length;r++){var a=n[r];if(!fi.call(t,a)||!Le(e[a],t[a]))return!1}return!0}function ts(e){for(;e&&e.firstChild;)e=e.firstChild;return e}function ns(e,t){var n=ts(e);e=0;for(var r;n;){if(n.nodeType===3){if(r=e+n.textContent.length,e<=t&&r>=t)return{node:n,offset:t-e};e=r}e:{for(;n;){if(n.nextSibling){n=n.nextSibling;break e}n=n.parentNode}n=void 0}n=ts(n)}}function zu(e,t){return e&&t?e===t?!0:e&&e.nodeType===3?!1:t&&t.nodeType===3?zu(e,t.parentNode):"contains"in e?e.contains(t):e.compareDocumentPosition?!!(e.compareDocumentPosition(t)&16):!1:!1}function Tu(){for(var e=window,t=Ur();t instanceof e.HTMLIFrameElement;){try{var n=typeof t.contentWindow.location.href=="string"}catch{n=!1}if(n)e=t.contentWindow;else break;t=Ur(e.document)}return t}function ko(e){var t=e&&e.nodeName&&e.nodeName.toLowerCase();return t&&(t==="input"&&(e.type==="text"||e.type==="search"||e.type==="tel"||e.type==="url"||e.type==="password")||t==="textarea"||e.contentEditable==="true")}function th(e){var t=Tu(),n=e.focusedElem,r=e.selectionRange;if(t!==n&&n&&n.ownerDocument&&zu(n.ownerDocument.documentElement,n)){if(r!==null&&ko(n)){if(t=r.start,e=r.end,e===void 0&&(e=t),"selectionStart"in n)n.selectionStart=t,n.selectionEnd=Math.min(e,n.value.length);else if(e=(t=n.ownerDocument||document)&&t.defaultView||window,e.getSelection){e=e.getSelection();var a=n.textContent.length,i=Math.min(r.start,a);r=r.end===void 0?i:Math.min(r.end,a),!e.extend&&i>r&&(a=r,r=i,i=a),a=ns(n,i);var o=ns(n,r);a&&o&&(e.rangeCount!==1||e.anchorNode!==a.node||e.anchorOffset!==a.offset||e.focusNode!==o.node||e.focusOffset!==o.offset)&&(t=t.createRange(),t.setStart(a.node,a.offset),e.removeAllRanges(),i>r?(e.addRange(t),e.extend(o.node,o.offset)):(t.setEnd(o.node,o.offset),e.addRange(t)))}}for(t=[],e=n;e=e.parentNode;)e.nodeType===1&&t.push({element:e,left:e.scrollLeft,top:e.scrollTop});for(typeof n.focus=="function"&&n.focus(),n=0;n<t.length;n++)e=t[n],e.element.scrollLeft=e.left,e.element.scrollTop=e.top}}var nh=qe&&"documentMode"in document&&11>=document.documentMode,It=null,Mi=null,Mn=null,$i=!1;function rs(e,t,n){var r=n.window===n?n.document:n.nodeType===9?n:n.ownerDocument;$i||It==null||It!==Ur(r)||(r=It,"selectionStart"in r&&ko(r)?r={start:r.selectionStart,end:r.selectionEnd}:(r=(r.ownerDocument&&r.ownerDocument.defaultView||window).getSelection(),r={anchorNode:r.anchorNode,anchorOffset:r.anchorOffset,focusNode:r.focusNode,focusOffset:r.focusOffset}),Mn&&qn(Mn,r)||(Mn=r,r=Xr(Mi,"onSelect"),0<r.length&&(t=new yo("onSelect","select",null,t,n),e.push({event:t,listeners:r}),t.target=It)))}function Sr(e,t){var n={};return n[e.toLowerCase()]=t.toLowerCase(),n["Webkit"+e]="webkit"+t,n["Moz"+e]="moz"+t,n}var Bt={animationend:Sr("Animation","AnimationEnd"),animationiteration:Sr("Animation","AnimationIteration"),animationstart:Sr("Animation","AnimationStart"),transitionend:Sr("Transition","TransitionEnd")},ti={},Ru={};qe&&(Ru=document.createElement("div").style,"AnimationEvent"in window||(delete Bt.animationend.animation,delete Bt.animationiteration.animation,delete Bt.animationstart.animation),"TransitionEvent"in window||delete Bt.transitionend.transition);function ma(e){if(ti[e])return ti[e];if(!Bt[e])return e;var t=Bt[e],n;for(n in t)if(t.hasOwnProperty(n)&&n in Ru)return ti[e]=t[n];return e}var _u=ma("animationend"),Cu=ma("animationiteration"),Pu=ma("animationstart"),Lu=ma("transitionend"),Au=new Map,as="abort auxClick cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(" ");function gt(e,t){Au.set(e,t),At(t,[e])}for(Er=0;Er<as.length;Er++)zr=as[Er],is=zr.toLowerCase(),os=zr[0].toUpperCase()+zr.slice(1),gt(is,"on"+os);var zr,is,os,Er;gt(_u,"onAnimationEnd");gt(Cu,"onAnimationIteration");gt(Pu,"onAnimationStart");gt("dblclick","onDoubleClick");gt("focusin","onFocus");gt("focusout","onBlur");gt(Lu,"onTransitionEnd");nn("onMouseEnter",["mouseout","mouseover"]);nn("onMouseLeave",["mouseout","mouseover"]);nn("onPointerEnter",["pointerout","pointerover"]);nn("onPointerLeave",["pointerout","pointerover"]);At("onChange","change click focusin focusout input keydown keyup selectionchange".split(" "));At("onSelect","focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(" "));At("onBeforeInput",["compositionend","keypress","textInput","paste"]);At("onCompositionEnd","compositionend focusout keydown keypress keyup mousedown".split(" "));At("onCompositionStart","compositionstart focusout keydown keypress keyup mousedown".split(" "));At("onCompositionUpdate","compositionupdate focusout keydown keypress keyup mousedown".split(" "));var _n="abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(" "),rh=new Set("cancel close invalid load scroll toggle".split(" ").concat(_n));function ls(e,t,n){var r=e.type||"unknown-event";e.currentTarget=n,r0(r,t,void 0,e),e.currentTarget=null}function Mu(e,t){t=(t&4)!==0;for(var n=0;n<e.length;n++){var r=e[n],a=r.event;r=r.listeners;e:{var i=void 0;if(t)for(var o=r.length-1;0<=o;o--){var l=r[o],s=l.instance,c=l.currentTarget;if(l=l.listener,s!==i&&a.isPropagationStopped())break e;ls(a,l,c),i=s}else for(o=0;o<r.length;o++){if(l=r[o],s=l.instance,c=l.currentTarget,l=l.listener,s!==i&&a.isPropagationStopped())break e;ls(a,l,c),i=s}}}if(qr)throw e=Ci,qr=!1,Ci=null,e}function A(e,t){var n=t[Oi];n===void 0&&(n=t[Oi]=new Set);var r=e+"__bubble";n.has(r)||($u(t,e,2,!1),n.add(r))}function ni(e,t,n){var r=0;t&&(r|=4),$u(n,e,r,t)}var Tr="_reactListening"+Math.random().toString(36).slice(2);function jn(e){if(!e[Tr]){e[Tr]=!0,Is.forEach(function(n){n!=="selectionchange"&&(rh.has(n)||ni(n,!1,e),ni(n,!0,e))});var t=e.nodeType===9?e:e.ownerDocument;t===null||t[Tr]||(t[Tr]=!0,ni("selectionchange",!1,t))}}function $u(e,t,n,r){switch(vu(t)){case 1:var a=y0;break;case 4:a=b0;break;default:a=vo}n=a.bind(null,t,n,e),a=void 0,!_i||t!=="touchstart"&&t!=="touchmove"&&t!=="wheel"||(a=!0),r?a!==void 0?e.addEventListener(t,n,{capture:!0,passive:a}):e.addEventListener(t,n,!0):a!==void 0?e.addEventListener(t,n,{passive:a}):e.addEventListener(t,n,!1)}function ri(e,t,n,r,a){var i=r;if((t&1)===0&&(t&2)===0&&r!==null)e:for(;;){if(r===null)return;var o=r.tag;if(o===3||o===4){var l=r.stateNode.containerInfo;if(l===a||l.nodeType===8&&l.parentNode===a)break;if(o===4)for(o=r.return;o!==null;){var s=o.tag;if((s===3||s===4)&&(s=o.stateNode.containerInfo,s===a||s.nodeType===8&&s.parentNode===a))return;o=o.return}for(;l!==null;){if(o=kt(l),o===null)return;if(s=o.tag,s===5||s===6){r=i=o;continue e}l=l.parentNode}}r=r.return}ru(function(){var c=i,f=po(n),g=[];e:{var p=Au.get(e);if(p!==void 0){var w=yo,y=e;switch(e){case"keypress":if(Hr(n)===0)break e;case"keydown":case"keyup":w=H0;break;case"focusin":y="focus",w=Ja;break;case"focusout":y="blur",w=Ja;break;case"beforeblur":case"afterblur":w=Ja;break;case"click":if(n.button===2)break e;case"auxclick":case"dblclick":case"mousedown":case"mousemove":case"mouseup":case"mouseout":case"mouseover":case"contextmenu":w=Kl;break;case"drag":case"dragend":case"dragenter":case"dragexit":case"dragleave":case"dragover":case"dragstart":case"drop":w=S0;break;case"touchcancel":case"touchend":case"touchmove":case"touchstart":w=D0;break;case _u:case Cu:case Pu:w=T0;break;case Lu:w=W0;break;case"scroll":w=x0;break;case"wheel":w=B0;break;case"copy":case"cut":case"paste":w=_0;break;case"gotpointercapture":case"lostpointercapture":case"pointercancel":case"pointerdown":case"pointermove":case"pointerout":case"pointerover":case"pointerup":w=Xl}var b=(t&4)!==0,H=!b&&e==="scroll",h=b?p!==null?p+"Capture":null:p;b=[];for(var u=c,d;u!==null;){d=u;var m=d.stateNode;if(d.tag===5&&m!==null&&(d=m,h!==null&&(m=Wn(u,h),m!=null&&b.push(Gn(u,m,d)))),H)break;u=u.return}0<b.length&&(p=new w(p,y,null,n,f),g.push({event:p,listeners:b}))}}if((t&7)===0){e:{if(p=e==="mouseover"||e==="pointerover",w=e==="mouseout"||e==="pointerout",p&&n!==Ti&&(y=n.relatedTarget||n.fromElement)&&(kt(y)||y[je]))break e;if((w||p)&&(p=f.window===f?f:(p=f.ownerDocument)?p.defaultView||p.parentWindow:window,w?(y=n.relatedTarget||n.toElement,w=c,y=y?kt(y):null,y!==null&&(H=Mt(y),y!==H||y.tag!==5&&y.tag!==6)&&(y=null)):(w=null,y=c),w!==y)){if(b=Kl,m="onMouseLeave",h="onMouseEnter",u="mouse",(e==="pointerout"||e==="pointerover")&&(b=Xl,m="onPointerLeave",h="onPointerEnter",u="pointer"),H=w==null?p:Ut(w),d=y==null?p:Ut(y),p=new b(m,u+"leave",w,n,f),p.target=H,p.relatedTarget=d,m=null,kt(f)===c&&(b=new b(h,u+"enter",y,n,f),b.target=d,b.relatedTarget=H,m=b),H=m,w&&y)t:{for(b=w,h=y,u=0,d=b;d;d=Nt(d))u++;for(d=0,m=h;m;m=Nt(m))d++;for(;0<u-d;)b=Nt(b),u--;for(;0<d-u;)h=Nt(h),d--;for(;u--;){if(b===h||h!==null&&b===h.alternate)break t;b=Nt(b),h=Nt(h)}b=null}else b=null;w!==null&&ss(g,p,w,b,!1),y!==null&&H!==null&&ss(g,H,y,b,!0)}}e:{if(p=c?Ut(c):window,w=p.nodeName&&p.nodeName.toLowerCase(),w==="select"||w==="input"&&p.type==="file")var k=Y0;else if(Jl(p))if(Su)k=J0;else{k=Q0;var S=X0}else(w=p.nodeName)&&w.toLowerCase()==="input"&&(p.type==="checkbox"||p.type==="radio")&&(k=Z0);if(k&&(k=k(e,c))){ku(g,k,n,f);break e}S&&S(e,p,c),e==="focusout"&&(S=p._wrapperState)&&S.controlled&&p.type==="number"&&xi(p,"number",p.value)}switch(S=c?Ut(c):window,e){case"focusin":(Jl(S)||S.contentEditable==="true")&&(It=S,Mi=c,Mn=null);break;case"focusout":Mn=Mi=It=null;break;case"mousedown":$i=!0;break;case"contextmenu":case"mouseup":case"dragend":$i=!1,rs(g,n,f);break;case"selectionchange":if(nh)break;case"keydown":case"keyup":rs(g,n,f)}var E;if(xo)e:{switch(e){case"compositionstart":var z="onCompositionStart";break e;case"compositionend":z="onCompositionEnd";break e;case"compositionupdate":z="onCompositionUpdate";break e}z=void 0}else Wt?bu(e,n)&&(z="onCompositionEnd"):e==="keydown"&&n.keyCode===229&&(z="onCompositionStart");z&&(yu&&n.locale!=="ko"&&(Wt||z!=="onCompositionStart"?z==="onCompositionEnd"&&Wt&&(E=wu()):(rt=f,wo="value"in rt?rt.value:rt.textContent,Wt=!0)),S=Xr(c,z),0<S.length&&(z=new Yl(z,e,null,n,f),g.push({event:z,listeners:S}),E?z.data=E:(E=xu(n),E!==null&&(z.data=E)))),(E=V0?q0(e,n):j0(e,n))&&(c=Xr(c,"onBeforeInput"),0<c.length&&(f=new Yl("onBeforeInput","beforeinput",null,n,f),g.push({event:f,listeners:c}),f.data=E))}Mu(g,t)})}function Gn(e,t,n){return{instance:e,listener:t,currentTarget:n}}function Xr(e,t){for(var n=t+"Capture",r=[];e!==null;){var a=e,i=a.stateNode;a.tag===5&&i!==null&&(a=i,i=Wn(e,n),i!=null&&r.unshift(Gn(e,i,a)),i=Wn(e,t),i!=null&&r.push(Gn(e,i,a))),e=e.return}return r}function Nt(e){if(e===null)return null;do e=e.return;while(e&&e.tag!==5);return e||null}function ss(e,t,n,r,a){for(var i=t._reactName,o=[];n!==null&&n!==r;){var l=n,s=l.alternate,c=l.stateNode;if(s!==null&&s===r)break;l.tag===5&&c!==null&&(l=c,a?(s=Wn(n,i),s!=null&&o.unshift(Gn(n,s,l))):a||(s=Wn(n,i),s!=null&&o.push(Gn(n,s,l)))),n=n.return}o.length!==0&&e.push({event:t,listeners:o})}var ah=/\r\n?/g,ih=/\u0000|\uFFFD/g;function us(e){return(typeof e=="string"?e:""+e).replace(ah,`
`).replace(ih,"")}function Rr(e,t,n){if(t=us(t),us(e)!==t&&n)throw Error(v(425))}function Qr(){}var Hi=null,Fi=null;function Ni(e,t){return e==="textarea"||e==="noscript"||typeof t.children=="string"||typeof t.children=="number"||typeof t.dangerouslySetInnerHTML=="object"&&t.dangerouslySetInnerHTML!==null&&t.dangerouslySetInnerHTML.__html!=null}var Di=typeof setTimeout=="function"?setTimeout:void 0,oh=typeof clearTimeout=="function"?clearTimeout:void 0,cs=typeof Promise=="function"?Promise:void 0,lh=typeof queueMicrotask=="function"?queueMicrotask:typeof cs<"u"?function(e){return cs.resolve(null).then(e).catch(sh)}:Di;function sh(e){setTimeout(function(){throw e})}function ai(e,t){var n=t,r=0;do{var a=n.nextSibling;if(e.removeChild(n),a&&a.nodeType===8)if(n=a.data,n==="/$"){if(r===0){e.removeChild(a),Un(t);return}r--}else n!=="$"&&n!=="$?"&&n!=="$!"||r++;n=a}while(n);Un(t)}function st(e){for(;e!=null;e=e.nextSibling){var t=e.nodeType;if(t===1||t===3)break;if(t===8){if(t=e.data,t==="$"||t==="$!"||t==="$?")break;if(t==="/$")return null}}return e}function ds(e){e=e.previousSibling;for(var t=0;e;){if(e.nodeType===8){var n=e.data;if(n==="$"||n==="$!"||n==="$?"){if(t===0)return e;t--}else n==="/$"&&t++}e=e.previousSibling}return null}var dn=Math.random().toString(36).slice(2),He="__reactFiber$"+dn,Kn="__reactProps$"+dn,je="__reactContainer$"+dn,Oi="__reactEvents$"+dn,uh="__reactListeners$"+dn,ch="__reactHandles$"+dn;function kt(e){var t=e[He];if(t)return t;for(var n=e.parentNode;n;){if(t=n[je]||n[He]){if(n=t.alternate,t.child!==null||n!==null&&n.child!==null)for(e=ds(e);e!==null;){if(n=e[He])return n;e=ds(e)}return t}e=n,n=e.parentNode}return null}function rr(e){return e=e[He]||e[je],!e||e.tag!==5&&e.tag!==6&&e.tag!==13&&e.tag!==3?null:e}function Ut(e){if(e.tag===5||e.tag===6)return e.stateNode;throw Error(v(33))}function va(e){return e[Kn]||null}var Wi=[],Vt=-1;function mt(e){return{current:e}}function M(e){0>Vt||(e.current=Wi[Vt],Wi[Vt]=null,Vt--)}function L(e,t){Vt++,Wi[Vt]=e.current,e.current=t}var ft={},ee=mt(ft),le=mt(!1),Rt=ft;function rn(e,t){var n=e.type.contextTypes;if(!n)return ft;var r=e.stateNode;if(r&&r.__reactInternalMemoizedUnmaskedChildContext===t)return r.__reactInternalMemoizedMaskedChildContext;var a={},i;for(i in n)a[i]=t[i];return r&&(e=e.stateNode,e.__reactInternalMemoizedUnmaskedChildContext=t,e.__reactInternalMemoizedMaskedChildContext=a),a}function se(e){return e=e.childContextTypes,e!=null}function Zr(){M(le),M(ee)}function hs(e,t,n){if(ee.current!==ft)throw Error(v(168));L(ee,t),L(le,n)}function Hu(e,t,n){var r=e.stateNode;if(t=t.childContextTypes,typeof r.getChildContext!="function")return n;r=r.getChildContext();for(var a in r)if(!(a in t))throw Error(v(108,Xd(e)||"Unknown",a));return O({},n,r)}function Jr(e){return e=(e=e.stateNode)&&e.__reactInternalMemoizedMergedChildContext||ft,Rt=ee.current,L(ee,e),L(le,le.current),!0}function ps(e,t,n){var r=e.stateNode;if(!r)throw Error(v(169));n?(e=Hu(e,t,Rt),r.__reactInternalMemoizedMergedChildContext=e,M(le),M(ee),L(ee,e)):M(le),L(le,n)}var Ie=null,wa=!1,ii=!1;function Fu(e){Ie===null?Ie=[e]:Ie.push(e)}function dh(e){wa=!0,Fu(e)}function vt(){if(!ii&&Ie!==null){ii=!0;var e=0,t=C;try{var n=Ie;for(C=1;e<n.length;e++){var r=n[e];do r=r(!0);while(r!==null)}Ie=null,wa=!1}catch(a){throw Ie!==null&&(Ie=Ie.slice(e+1)),lu(fo,vt),a}finally{C=t,ii=!1}}return null}var qt=[],jt=0,ea=null,ta=0,we=[],ye=0,_t=null,Be=1,Ue="";function bt(e,t){qt[jt++]=ta,qt[jt++]=ea,ea=e,ta=t}function Nu(e,t,n){we[ye++]=Be,we[ye++]=Ue,we[ye++]=_t,_t=e;var r=Be;e=Ue;var a=32-Ce(r)-1;r&=~(1<<a),n+=1;var i=32-Ce(t)+a;if(30<i){var o=a-a%5;i=(r&(1<<o)-1).toString(32),r>>=o,a-=o,Be=1<<32-Ce(t)+a|n<<a|r,Ue=i+e}else Be=1<<i|n<<a|r,Ue=e}function So(e){e.return!==null&&(bt(e,1),Nu(e,1,0))}function Eo(e){for(;e===ea;)ea=qt[--jt],qt[jt]=null,ta=qt[--jt],qt[jt]=null;for(;e===_t;)_t=we[--ye],we[ye]=null,Ue=we[--ye],we[ye]=null,Be=we[--ye],we[ye]=null}var pe=null,he=null,$=!1,_e=null;function Du(e,t){var n=be(5,null,null,0);n.elementType="DELETED",n.stateNode=t,n.return=e,t=e.deletions,t===null?(e.deletions=[n],e.flags|=16):t.push(n)}function fs(e,t){switch(e.tag){case 5:var n=e.type;return t=t.nodeType!==1||n.toLowerCase()!==t.nodeName.toLowerCase()?null:t,t!==null?(e.stateNode=t,pe=e,he=st(t.firstChild),!0):!1;case 6:return t=e.pendingProps===""||t.nodeType!==3?null:t,t!==null?(e.stateNode=t,pe=e,he=null,!0):!1;case 13:return t=t.nodeType!==8?null:t,t!==null?(n=_t!==null?{id:Be,overflow:Ue}:null,e.memoizedState={dehydrated:t,treeContext:n,retryLane:1073741824},n=be(18,null,null,0),n.stateNode=t,n.return=e,e.child=n,pe=e,he=null,!0):!1;default:return!1}}function Ii(e){return(e.mode&1)!==0&&(e.flags&128)===0}function Bi(e){if($){var t=he;if(t){var n=t;if(!fs(e,t)){if(Ii(e))throw Error(v(418));t=st(n.nextSibling);var r=pe;t&&fs(e,t)?Du(r,n):(e.flags=e.flags&-4097|2,$=!1,pe=e)}}else{if(Ii(e))throw Error(v(418));e.flags=e.flags&-4097|2,$=!1,pe=e}}}function gs(e){for(e=e.return;e!==null&&e.tag!==5&&e.tag!==3&&e.tag!==13;)e=e.return;pe=e}function _r(e){if(e!==pe)return!1;if(!$)return gs(e),$=!0,!1;var t;if((t=e.tag!==3)&&!(t=e.tag!==5)&&(t=e.type,t=t!=="head"&&t!=="body"&&!Ni(e.type,e.memoizedProps)),t&&(t=he)){if(Ii(e))throw Ou(),Error(v(418));for(;t;)Du(e,t),t=st(t.nextSibling)}if(gs(e),e.tag===13){if(e=e.memoizedState,e=e!==null?e.dehydrated:null,!e)throw Error(v(317));e:{for(e=e.nextSibling,t=0;e;){if(e.nodeType===8){var n=e.data;if(n==="/$"){if(t===0){he=st(e.nextSibling);break e}t--}else n!=="$"&&n!=="$!"&&n!=="$?"||t++}e=e.nextSibling}he=null}}else he=pe?st(e.stateNode.nextSibling):null;return!0}function Ou(){for(var e=he;e;)e=st(e.nextSibling)}function an(){he=pe=null,$=!1}function zo(e){_e===null?_e=[e]:_e.push(e)}var hh=Ye.ReactCurrentBatchConfig;function xn(e,t,n){if(e=n.ref,e!==null&&typeof e!="function"&&typeof e!="object"){if(n._owner){if(n=n._owner,n){if(n.tag!==1)throw Error(v(309));var r=n.stateNode}if(!r)throw Error(v(147,e));var a=r,i=""+e;return t!==null&&t.ref!==null&&typeof t.ref=="function"&&t.ref._stringRef===i?t.ref:(t=function(o){var l=a.refs;o===null?delete l[i]:l[i]=o},t._stringRef=i,t)}if(typeof e!="string")throw Error(v(284));if(!n._owner)throw Error(v(290,e))}return e}function Cr(e,t){throw e=Object.prototype.toString.call(t),Error(v(31,e==="[object Object]"?"object with keys {"+Object.keys(t).join(", ")+"}":e))}function ms(e){var t=e._init;return t(e._payload)}function Wu(e){function t(h,u){if(e){var d=h.deletions;d===null?(h.deletions=[u],h.flags|=16):d.push(u)}}function n(h,u){if(!e)return null;for(;u!==null;)t(h,u),u=u.sibling;return null}function r(h,u){for(h=new Map;u!==null;)u.key!==null?h.set(u.key,u):h.set(u.index,u),u=u.sibling;return h}function a(h,u){return h=ht(h,u),h.index=0,h.sibling=null,h}function i(h,u,d){return h.index=d,e?(d=h.alternate,d!==null?(d=d.index,d<u?(h.flags|=2,u):d):(h.flags|=2,u)):(h.flags|=1048576,u)}function o(h){return e&&h.alternate===null&&(h.flags|=2),h}function l(h,u,d,m){return u===null||u.tag!==6?(u=hi(d,h.mode,m),u.return=h,u):(u=a(u,d),u.return=h,u)}function s(h,u,d,m){var k=d.type;return k===Ot?f(h,u,d.props.children,m,d.key):u!==null&&(u.elementType===k||typeof k=="object"&&k!==null&&k.$$typeof===Je&&ms(k)===u.type)?(m=a(u,d.props),m.ref=xn(h,u,d),m.return=h,m):(m=Br(d.type,d.key,d.props,null,h.mode,m),m.ref=xn(h,u,d),m.return=h,m)}function c(h,u,d,m){return u===null||u.tag!==4||u.stateNode.containerInfo!==d.containerInfo||u.stateNode.implementation!==d.implementation?(u=pi(d,h.mode,m),u.return=h,u):(u=a(u,d.children||[]),u.return=h,u)}function f(h,u,d,m,k){return u===null||u.tag!==7?(u=Tt(d,h.mode,m,k),u.return=h,u):(u=a(u,d),u.return=h,u)}function g(h,u,d){if(typeof u=="string"&&u!==""||typeof u=="number")return u=hi(""+u,h.mode,d),u.return=h,u;if(typeof u=="object"&&u!==null){switch(u.$$typeof){case fr:return d=Br(u.type,u.key,u.props,null,h.mode,d),d.ref=xn(h,null,u),d.return=h,d;case Dt:return u=pi(u,h.mode,d),u.return=h,u;case Je:var m=u._init;return g(h,m(u._payload),d)}if(Tn(u)||vn(u))return u=Tt(u,h.mode,d,null),u.return=h,u;Cr(h,u)}return null}function p(h,u,d,m){var k=u!==null?u.key:null;if(typeof d=="string"&&d!==""||typeof d=="number")return k!==null?null:l(h,u,""+d,m);if(typeof d=="object"&&d!==null){switch(d.$$typeof){case fr:return d.key===k?s(h,u,d,m):null;case Dt:return d.key===k?c(h,u,d,m):null;case Je:return k=d._init,p(h,u,k(d._payload),m)}if(Tn(d)||vn(d))return k!==null?null:f(h,u,d,m,null);Cr(h,d)}return null}function w(h,u,d,m,k){if(typeof m=="string"&&m!==""||typeof m=="number")return h=h.get(d)||null,l(u,h,""+m,k);if(typeof m=="object"&&m!==null){switch(m.$$typeof){case fr:return h=h.get(m.key===null?d:m.key)||null,s(u,h,m,k);case Dt:return h=h.get(m.key===null?d:m.key)||null,c(u,h,m,k);case Je:var S=m._init;return w(h,u,d,S(m._payload),k)}if(Tn(m)||vn(m))return h=h.get(d)||null,f(u,h,m,k,null);Cr(u,m)}return null}function y(h,u,d,m){for(var k=null,S=null,E=u,z=u=0,F=null;E!==null&&z<d.length;z++){E.index>z?(F=E,E=null):F=E.sibling;var _=p(h,E,d[z],m);if(_===null){E===null&&(E=F);break}e&&E&&_.alternate===null&&t(h,E),u=i(_,u,z),S===null?k=_:S.sibling=_,S=_,E=F}if(z===d.length)return n(h,E),$&&bt(h,z),k;if(E===null){for(;z<d.length;z++)E=g(h,d[z],m),E!==null&&(u=i(E,u,z),S===null?k=E:S.sibling=E,S=E);return $&&bt(h,z),k}for(E=r(h,E);z<d.length;z++)F=w(E,h,z,d[z],m),F!==null&&(e&&F.alternate!==null&&E.delete(F.key===null?z:F.key),u=i(F,u,z),S===null?k=F:S.sibling=F,S=F);return e&&E.forEach(function(Xe){return t(h,Xe)}),$&&bt(h,z),k}function b(h,u,d,m){var k=vn(d);if(typeof k!="function")throw Error(v(150));if(d=k.call(d),d==null)throw Error(v(151));for(var S=k=null,E=u,z=u=0,F=null,_=d.next();E!==null&&!_.done;z++,_=d.next()){E.index>z?(F=E,E=null):F=E.sibling;var Xe=p(h,E,_.value,m);if(Xe===null){E===null&&(E=F);break}e&&E&&Xe.alternate===null&&t(h,E),u=i(Xe,u,z),S===null?k=Xe:S.sibling=Xe,S=Xe,E=F}if(_.done)return n(h,E),$&&bt(h,z),k;if(E===null){for(;!_.done;z++,_=d.next())_=g(h,_.value,m),_!==null&&(u=i(_,u,z),S===null?k=_:S.sibling=_,S=_);return $&&bt(h,z),k}for(E=r(h,E);!_.done;z++,_=d.next())_=w(E,h,z,_.value,m),_!==null&&(e&&_.alternate!==null&&E.delete(_.key===null?z:_.key),u=i(_,u,z),S===null?k=_:S.sibling=_,S=_);return e&&E.forEach(function(xd){return t(h,xd)}),$&&bt(h,z),k}function H(h,u,d,m){if(typeof d=="object"&&d!==null&&d.type===Ot&&d.key===null&&(d=d.props.children),typeof d=="object"&&d!==null){switch(d.$$typeof){case fr:e:{for(var k=d.key,S=u;S!==null;){if(S.key===k){if(k=d.type,k===Ot){if(S.tag===7){n(h,S.sibling),u=a(S,d.props.children),u.return=h,h=u;break e}}else if(S.elementType===k||typeof k=="object"&&k!==null&&k.$$typeof===Je&&ms(k)===S.type){n(h,S.sibling),u=a(S,d.props),u.ref=xn(h,S,d),u.return=h,h=u;break e}n(h,S);break}else t(h,S);S=S.sibling}d.type===Ot?(u=Tt(d.props.children,h.mode,m,d.key),u.return=h,h=u):(m=Br(d.type,d.key,d.props,null,h.mode,m),m.ref=xn(h,u,d),m.return=h,h=m)}return o(h);case Dt:e:{for(S=d.key;u!==null;){if(u.key===S)if(u.tag===4&&u.stateNode.containerInfo===d.containerInfo&&u.stateNode.implementation===d.implementation){n(h,u.sibling),u=a(u,d.children||[]),u.return=h,h=u;break e}else{n(h,u);break}else t(h,u);u=u.sibling}u=pi(d,h.mode,m),u.return=h,h=u}return o(h);case Je:return S=d._init,H(h,u,S(d._payload),m)}if(Tn(d))return y(h,u,d,m);if(vn(d))return b(h,u,d,m);Cr(h,d)}return typeof d=="string"&&d!==""||typeof d=="number"?(d=""+d,u!==null&&u.tag===6?(n(h,u.sibling),u=a(u,d),u.return=h,h=u):(n(h,u),u=hi(d,h.mode,m),u.return=h,h=u),o(h)):n(h,u)}return H}var on=Wu(!0),Iu=Wu(!1),na=mt(null),ra=null,Gt=null,To=null;function Ro(){To=Gt=ra=null}function _o(e){var t=na.current;M(na),e._currentValue=t}function Ui(e,t,n){for(;e!==null;){var r=e.alternate;if((e.childLanes&t)!==t?(e.childLanes|=t,r!==null&&(r.childLanes|=t)):r!==null&&(r.childLanes&t)!==t&&(r.childLanes|=t),e===n)break;e=e.return}}function en(e,t){ra=e,To=Gt=null,e=e.dependencies,e!==null&&e.firstContext!==null&&((e.lanes&t)!==0&&(oe=!0),e.firstContext=null)}function ke(e){var t=e._currentValue;if(To!==e)if(e={context:e,memoizedValue:t,next:null},Gt===null){if(ra===null)throw Error(v(308));Gt=e,ra.dependencies={lanes:0,firstContext:e}}else Gt=Gt.next=e;return t}var St=null;function Co(e){St===null?St=[e]:St.push(e)}function Bu(e,t,n,r){var a=t.interleaved;return a===null?(n.next=n,Co(t)):(n.next=a.next,a.next=n),t.interleaved=n,Ge(e,r)}function Ge(e,t){e.lanes|=t;var n=e.alternate;for(n!==null&&(n.lanes|=t),n=e,e=e.return;e!==null;)e.childLanes|=t,n=e.alternate,n!==null&&(n.childLanes|=t),n=e,e=e.return;return n.tag===3?n.stateNode:null}var et=!1;function Po(e){e.updateQueue={baseState:e.memoizedState,firstBaseUpdate:null,lastBaseUpdate:null,shared:{pending:null,interleaved:null,lanes:0},effects:null}}function Uu(e,t){e=e.updateQueue,t.updateQueue===e&&(t.updateQueue={baseState:e.baseState,firstBaseUpdate:e.firstBaseUpdate,lastBaseUpdate:e.lastBaseUpdate,shared:e.shared,effects:e.effects})}function Ve(e,t){return{eventTime:e,lane:t,tag:0,payload:null,callback:null,next:null}}function ut(e,t,n){var r=e.updateQueue;if(r===null)return null;if(r=r.shared,(R&2)!==0){var a=r.pending;return a===null?t.next=t:(t.next=a.next,a.next=t),r.pending=t,Ge(e,n)}return a=r.interleaved,a===null?(t.next=t,Co(r)):(t.next=a.next,a.next=t),r.interleaved=t,Ge(e,n)}function Fr(e,t,n){if(t=t.updateQueue,t!==null&&(t=t.shared,(n&4194240)!==0)){var r=t.lanes;r&=e.pendingLanes,n|=r,t.lanes=n,go(e,n)}}function vs(e,t){var n=e.updateQueue,r=e.alternate;if(r!==null&&(r=r.updateQueue,n===r)){var a=null,i=null;if(n=n.firstBaseUpdate,n!==null){do{var o={eventTime:n.eventTime,lane:n.lane,tag:n.tag,payload:n.payload,callback:n.callback,next:null};i===null?a=i=o:i=i.next=o,n=n.next}while(n!==null);i===null?a=i=t:i=i.next=t}else a=i=t;n={baseState:r.baseState,firstBaseUpdate:a,lastBaseUpdate:i,shared:r.shared,effects:r.effects},e.updateQueue=n;return}e=n.lastBaseUpdate,e===null?n.firstBaseUpdate=t:e.next=t,n.lastBaseUpdate=t}function aa(e,t,n,r){var a=e.updateQueue;et=!1;var i=a.firstBaseUpdate,o=a.lastBaseUpdate,l=a.shared.pending;if(l!==null){a.shared.pending=null;var s=l,c=s.next;s.next=null,o===null?i=c:o.next=c,o=s;var f=e.alternate;f!==null&&(f=f.updateQueue,l=f.lastBaseUpdate,l!==o&&(l===null?f.firstBaseUpdate=c:l.next=c,f.lastBaseUpdate=s))}if(i!==null){var g=a.baseState;o=0,f=c=s=null,l=i;do{var p=l.lane,w=l.eventTime;if((r&p)===p){f!==null&&(f=f.next={eventTime:w,lane:0,tag:l.tag,payload:l.payload,callback:l.callback,next:null});e:{var y=e,b=l;switch(p=t,w=n,b.tag){case 1:if(y=b.payload,typeof y=="function"){g=y.call(w,g,p);break e}g=y;break e;case 3:y.flags=y.flags&-65537|128;case 0:if(y=b.payload,p=typeof y=="function"?y.call(w,g,p):y,p==null)break e;g=O({},g,p);break e;case 2:et=!0}}l.callback!==null&&l.lane!==0&&(e.flags|=64,p=a.effects,p===null?a.effects=[l]:p.push(l))}else w={eventTime:w,lane:p,tag:l.tag,payload:l.payload,callback:l.callback,next:null},f===null?(c=f=w,s=g):f=f.next=w,o|=p;if(l=l.next,l===null){if(l=a.shared.pending,l===null)break;p=l,l=p.next,p.next=null,a.lastBaseUpdate=p,a.shared.pending=null}}while(!0);if(f===null&&(s=g),a.baseState=s,a.firstBaseUpdate=c,a.lastBaseUpdate=f,t=a.shared.interleaved,t!==null){a=t;do o|=a.lane,a=a.next;while(a!==t)}else i===null&&(a.shared.lanes=0);Pt|=o,e.lanes=o,e.memoizedState=g}}function ws(e,t,n){if(e=t.effects,t.effects=null,e!==null)for(t=0;t<e.length;t++){var r=e[t],a=r.callback;if(a!==null){if(r.callback=null,r=n,typeof a!="function")throw Error(v(191,a));a.call(r)}}}var ar={},Ne=mt(ar),Yn=mt(ar),Xn=mt(ar);function Et(e){if(e===ar)throw Error(v(174));return e}function Lo(e,t){switch(L(Xn,t),L(Yn,e),L(Ne,ar),e=t.nodeType,e){case 9:case 11:t=(t=t.documentElement)?t.namespaceURI:Si(null,"");break;default:e=e===8?t.parentNode:t,t=e.namespaceURI||null,e=e.tagName,t=Si(t,e)}M(Ne),L(Ne,t)}function ln(){M(Ne),M(Yn),M(Xn)}function Vu(e){Et(Xn.current);var t=Et(Ne.current),n=Si(t,e.type);t!==n&&(L(Yn,e),L(Ne,n))}function Ao(e){Yn.current===e&&(M(Ne),M(Yn))}var N=mt(0);function ia(e){for(var t=e;t!==null;){if(t.tag===13){var n=t.memoizedState;if(n!==null&&(n=n.dehydrated,n===null||n.data==="$?"||n.data==="$!"))return t}else if(t.tag===19&&t.memoizedProps.revealOrder!==void 0){if((t.flags&128)!==0)return t}else if(t.child!==null){t.child.return=t,t=t.child;continue}if(t===e)break;for(;t.sibling===null;){if(t.return===null||t.return===e)return null;t=t.return}t.sibling.return=t.return,t=t.sibling}return null}var oi=[];function Mo(){for(var e=0;e<oi.length;e++)oi[e]._workInProgressVersionPrimary=null;oi.length=0}var Nr=Ye.ReactCurrentDispatcher,li=Ye.ReactCurrentBatchConfig,Ct=0,D=null,U=null,q=null,oa=!1,$n=!1,Qn=0,ph=0;function Q(){throw Error(v(321))}function $o(e,t){if(t===null)return!1;for(var n=0;n<t.length&&n<e.length;n++)if(!Le(e[n],t[n]))return!1;return!0}function Ho(e,t,n,r,a,i){if(Ct=i,D=t,t.memoizedState=null,t.updateQueue=null,t.lanes=0,Nr.current=e===null||e.memoizedState===null?vh:wh,e=n(r,a),$n){i=0;do{if($n=!1,Qn=0,25<=i)throw Error(v(301));i+=1,q=U=null,t.updateQueue=null,Nr.current=yh,e=n(r,a)}while($n)}if(Nr.current=la,t=U!==null&&U.next!==null,Ct=0,q=U=D=null,oa=!1,t)throw Error(v(300));return e}function Fo(){var e=Qn!==0;return Qn=0,e}function $e(){var e={memoizedState:null,baseState:null,baseQueue:null,queue:null,next:null};return q===null?D.memoizedState=q=e:q=q.next=e,q}function Se(){if(U===null){var e=D.alternate;e=e!==null?e.memoizedState:null}else e=U.next;var t=q===null?D.memoizedState:q.next;if(t!==null)q=t,U=e;else{if(e===null)throw Error(v(310));U=e,e={memoizedState:U.memoizedState,baseState:U.baseState,baseQueue:U.baseQueue,queue:U.queue,next:null},q===null?D.memoizedState=q=e:q=q.next=e}return q}function Zn(e,t){return typeof t=="function"?t(e):t}function si(e){var t=Se(),n=t.queue;if(n===null)throw Error(v(311));n.lastRenderedReducer=e;var r=U,a=r.baseQueue,i=n.pending;if(i!==null){if(a!==null){var o=a.next;a.next=i.next,i.next=o}r.baseQueue=a=i,n.pending=null}if(a!==null){i=a.next,r=r.baseState;var l=o=null,s=null,c=i;do{var f=c.lane;if((Ct&f)===f)s!==null&&(s=s.next={lane:0,action:c.action,hasEagerState:c.hasEagerState,eagerState:c.eagerState,next:null}),r=c.hasEagerState?c.eagerState:e(r,c.action);else{var g={lane:f,action:c.action,hasEagerState:c.hasEagerState,eagerState:c.eagerState,next:null};s===null?(l=s=g,o=r):s=s.next=g,D.lanes|=f,Pt|=f}c=c.next}while(c!==null&&c!==i);s===null?o=r:s.next=l,Le(r,t.memoizedState)||(oe=!0),t.memoizedState=r,t.baseState=o,t.baseQueue=s,n.lastRenderedState=r}if(e=n.interleaved,e!==null){a=e;do i=a.lane,D.lanes|=i,Pt|=i,a=a.next;while(a!==e)}else a===null&&(n.lanes=0);return[t.memoizedState,n.dispatch]}function ui(e){var t=Se(),n=t.queue;if(n===null)throw Error(v(311));n.lastRenderedReducer=e;var r=n.dispatch,a=n.pending,i=t.memoizedState;if(a!==null){n.pending=null;var o=a=a.next;do i=e(i,o.action),o=o.next;while(o!==a);Le(i,t.memoizedState)||(oe=!0),t.memoizedState=i,t.baseQueue===null&&(t.baseState=i),n.lastRenderedState=i}return[i,r]}function qu(){}function ju(e,t){var n=D,r=Se(),a=t(),i=!Le(r.memoizedState,a);if(i&&(r.memoizedState=a,oe=!0),r=r.queue,No(Yu.bind(null,n,r,e),[e]),r.getSnapshot!==t||i||q!==null&&q.memoizedState.tag&1){if(n.flags|=2048,Jn(9,Ku.bind(null,n,r,a,t),void 0,null),j===null)throw Error(v(349));(Ct&30)!==0||Gu(n,t,a)}return a}function Gu(e,t,n){e.flags|=16384,e={getSnapshot:t,value:n},t=D.updateQueue,t===null?(t={lastEffect:null,stores:null},D.updateQueue=t,t.stores=[e]):(n=t.stores,n===null?t.stores=[e]:n.push(e))}function Ku(e,t,n,r){t.value=n,t.getSnapshot=r,Xu(t)&&Qu(e)}function Yu(e,t,n){return n(function(){Xu(t)&&Qu(e)})}function Xu(e){var t=e.getSnapshot;e=e.value;try{var n=t();return!Le(e,n)}catch{return!0}}function Qu(e){var t=Ge(e,1);t!==null&&Pe(t,e,1,-1)}function ys(e){var t=$e();return typeof e=="function"&&(e=e()),t.memoizedState=t.baseState=e,e={pending:null,interleaved:null,lanes:0,dispatch:null,lastRenderedReducer:Zn,lastRenderedState:e},t.queue=e,e=e.dispatch=mh.bind(null,D,e),[t.memoizedState,e]}function Jn(e,t,n,r){return e={tag:e,create:t,destroy:n,deps:r,next:null},t=D.updateQueue,t===null?(t={lastEffect:null,stores:null},D.updateQueue=t,t.lastEffect=e.next=e):(n=t.lastEffect,n===null?t.lastEffect=e.next=e:(r=n.next,n.next=e,e.next=r,t.lastEffect=e)),e}function Zu(){return Se().memoizedState}function Dr(e,t,n,r){var a=$e();D.flags|=e,a.memoizedState=Jn(1|t,n,void 0,r===void 0?null:r)}function ya(e,t,n,r){var a=Se();r=r===void 0?null:r;var i=void 0;if(U!==null){var o=U.memoizedState;if(i=o.destroy,r!==null&&$o(r,o.deps)){a.memoizedState=Jn(t,n,i,r);return}}D.flags|=e,a.memoizedState=Jn(1|t,n,i,r)}function bs(e,t){return Dr(8390656,8,e,t)}function No(e,t){return ya(2048,8,e,t)}function Ju(e,t){return ya(4,2,e,t)}function ec(e,t){return ya(4,4,e,t)}function tc(e,t){if(typeof t=="function")return e=e(),t(e),function(){t(null)};if(t!=null)return e=e(),t.current=e,function(){t.current=null}}function nc(e,t,n){return n=n!=null?n.concat([e]):null,ya(4,4,tc.bind(null,t,e),n)}function Do(){}function rc(e,t){var n=Se();t=t===void 0?null:t;var r=n.memoizedState;return r!==null&&t!==null&&$o(t,r[1])?r[0]:(n.memoizedState=[e,t],e)}function ac(e,t){var n=Se();t=t===void 0?null:t;var r=n.memoizedState;return r!==null&&t!==null&&$o(t,r[1])?r[0]:(e=e(),n.memoizedState=[e,t],e)}function ic(e,t,n){return(Ct&21)===0?(e.baseState&&(e.baseState=!1,oe=!0),e.memoizedState=n):(Le(n,t)||(n=cu(),D.lanes|=n,Pt|=n,e.baseState=!0),t)}function fh(e,t){var n=C;C=n!==0&&4>n?n:4,e(!0);var r=li.transition;li.transition={};try{e(!1),t()}finally{C=n,li.transition=r}}function oc(){return Se().memoizedState}function gh(e,t,n){var r=dt(e);if(n={lane:r,action:n,hasEagerState:!1,eagerState:null,next:null},lc(e))sc(t,n);else if(n=Bu(e,t,n,r),n!==null){var a=re();Pe(n,e,r,a),uc(n,t,r)}}function mh(e,t,n){var r=dt(e),a={lane:r,action:n,hasEagerState:!1,eagerState:null,next:null};if(lc(e))sc(t,a);else{var i=e.alternate;if(e.lanes===0&&(i===null||i.lanes===0)&&(i=t.lastRenderedReducer,i!==null))try{var o=t.lastRenderedState,l=i(o,n);if(a.hasEagerState=!0,a.eagerState=l,Le(l,o)){var s=t.interleaved;s===null?(a.next=a,Co(t)):(a.next=s.next,s.next=a),t.interleaved=a;return}}catch{}finally{}n=Bu(e,t,a,r),n!==null&&(a=re(),Pe(n,e,r,a),uc(n,t,r))}}function lc(e){var t=e.alternate;return e===D||t!==null&&t===D}function sc(e,t){$n=oa=!0;var n=e.pending;n===null?t.next=t:(t.next=n.next,n.next=t),e.pending=t}function uc(e,t,n){if((n&4194240)!==0){var r=t.lanes;r&=e.pendingLanes,n|=r,t.lanes=n,go(e,n)}}var la={readContext:ke,useCallback:Q,useContext:Q,useEffect:Q,useImperativeHandle:Q,useInsertionEffect:Q,useLayoutEffect:Q,useMemo:Q,useReducer:Q,useRef:Q,useState:Q,useDebugValue:Q,useDeferredValue:Q,useTransition:Q,useMutableSource:Q,useSyncExternalStore:Q,useId:Q,unstable_isNewReconciler:!1},vh={readContext:ke,useCallback:function(e,t){return $e().memoizedState=[e,t===void 0?null:t],e},useContext:ke,useEffect:bs,useImperativeHandle:function(e,t,n){return n=n!=null?n.concat([e]):null,Dr(4194308,4,tc.bind(null,t,e),n)},useLayoutEffect:function(e,t){return Dr(4194308,4,e,t)},useInsertionEffect:function(e,t){return Dr(4,2,e,t)},useMemo:function(e,t){var n=$e();return t=t===void 0?null:t,e=e(),n.memoizedState=[e,t],e},useReducer:function(e,t,n){var r=$e();return t=n!==void 0?n(t):t,r.memoizedState=r.baseState=t,e={pending:null,interleaved:null,lanes:0,dispatch:null,lastRenderedReducer:e,lastRenderedState:t},r.queue=e,e=e.dispatch=gh.bind(null,D,e),[r.memoizedState,e]},useRef:function(e){var t=$e();return e={current:e},t.memoizedState=e},useState:ys,useDebugValue:Do,useDeferredValue:function(e){return $e().memoizedState=e},useTransition:function(){var e=ys(!1),t=e[0];return e=fh.bind(null,e[1]),$e().memoizedState=e,[t,e]},useMutableSource:function(){},useSyncExternalStore:function(e,t,n){var r=D,a=$e();if($){if(n===void 0)throw Error(v(407));n=n()}else{if(n=t(),j===null)throw Error(v(349));(Ct&30)!==0||Gu(r,t,n)}a.memoizedState=n;var i={value:n,getSnapshot:t};return a.queue=i,bs(Yu.bind(null,r,i,e),[e]),r.flags|=2048,Jn(9,Ku.bind(null,r,i,n,t),void 0,null),n},useId:function(){var e=$e(),t=j.identifierPrefix;if($){var n=Ue,r=Be;n=(r&~(1<<32-Ce(r)-1)).toString(32)+n,t=":"+t+"R"+n,n=Qn++,0<n&&(t+="H"+n.toString(32)),t+=":"}else n=ph++,t=":"+t+"r"+n.toString(32)+":";return e.memoizedState=t},unstable_isNewReconciler:!1},wh={readContext:ke,useCallback:rc,useContext:ke,useEffect:No,useImperativeHandle:nc,useInsertionEffect:Ju,useLayoutEffect:ec,useMemo:ac,useReducer:si,useRef:Zu,useState:function(){return si(Zn)},useDebugValue:Do,useDeferredValue:function(e){var t=Se();return ic(t,U.memoizedState,e)},useTransition:function(){var e=si(Zn)[0],t=Se().memoizedState;return[e,t]},useMutableSource:qu,useSyncExternalStore:ju,useId:oc,unstable_isNewReconciler:!1},yh={readContext:ke,useCallback:rc,useContext:ke,useEffect:No,useImperativeHandle:nc,useInsertionEffect:Ju,useLayoutEffect:ec,useMemo:ac,useReducer:ui,useRef:Zu,useState:function(){return ui(Zn)},useDebugValue:Do,useDeferredValue:function(e){var t=Se();return U===null?t.memoizedState=e:ic(t,U.memoizedState,e)},useTransition:function(){var e=ui(Zn)[0],t=Se().memoizedState;return[e,t]},useMutableSource:qu,useSyncExternalStore:ju,useId:oc,unstable_isNewReconciler:!1};function Te(e,t){if(e&&e.defaultProps){t=O({},t),e=e.defaultProps;for(var n in e)t[n]===void 0&&(t[n]=e[n]);return t}return t}function Vi(e,t,n,r){t=e.memoizedState,n=n(r,t),n=n==null?t:O({},t,n),e.memoizedState=n,e.lanes===0&&(e.updateQueue.baseState=n)}var ba={isMounted:function(e){return(e=e._reactInternals)?Mt(e)===e:!1},enqueueSetState:function(e,t,n){e=e._reactInternals;var r=re(),a=dt(e),i=Ve(r,a);i.payload=t,n!=null&&(i.callback=n),t=ut(e,i,a),t!==null&&(Pe(t,e,a,r),Fr(t,e,a))},enqueueReplaceState:function(e,t,n){e=e._reactInternals;var r=re(),a=dt(e),i=Ve(r,a);i.tag=1,i.payload=t,n!=null&&(i.callback=n),t=ut(e,i,a),t!==null&&(Pe(t,e,a,r),Fr(t,e,a))},enqueueForceUpdate:function(e,t){e=e._reactInternals;var n=re(),r=dt(e),a=Ve(n,r);a.tag=2,t!=null&&(a.callback=t),t=ut(e,a,r),t!==null&&(Pe(t,e,r,n),Fr(t,e,r))}};function xs(e,t,n,r,a,i,o){return e=e.stateNode,typeof e.shouldComponentUpdate=="function"?e.shouldComponentUpdate(r,i,o):t.prototype&&t.prototype.isPureReactComponent?!qn(n,r)||!qn(a,i):!0}function cc(e,t,n){var r=!1,a=ft,i=t.contextType;return typeof i=="object"&&i!==null?i=ke(i):(a=se(t)?Rt:ee.current,r=t.contextTypes,i=(r=r!=null)?rn(e,a):ft),t=new t(n,i),e.memoizedState=t.state!==null&&t.state!==void 0?t.state:null,t.updater=ba,e.stateNode=t,t._reactInternals=e,r&&(e=e.stateNode,e.__reactInternalMemoizedUnmaskedChildContext=a,e.__reactInternalMemoizedMaskedChildContext=i),t}function ks(e,t,n,r){e=t.state,typeof t.componentWillReceiveProps=="function"&&t.componentWillReceiveProps(n,r),typeof t.UNSAFE_componentWillReceiveProps=="function"&&t.UNSAFE_componentWillReceiveProps(n,r),t.state!==e&&ba.enqueueReplaceState(t,t.state,null)}function qi(e,t,n,r){var a=e.stateNode;a.props=n,a.state=e.memoizedState,a.refs={},Po(e);var i=t.contextType;typeof i=="object"&&i!==null?a.context=ke(i):(i=se(t)?Rt:ee.current,a.context=rn(e,i)),a.state=e.memoizedState,i=t.getDerivedStateFromProps,typeof i=="function"&&(Vi(e,t,i,n),a.state=e.memoizedState),typeof t.getDerivedStateFromProps=="function"||typeof a.getSnapshotBeforeUpdate=="function"||typeof a.UNSAFE_componentWillMount!="function"&&typeof a.componentWillMount!="function"||(t=a.state,typeof a.componentWillMount=="function"&&a.componentWillMount(),typeof a.UNSAFE_componentWillMount=="function"&&a.UNSAFE_componentWillMount(),t!==a.state&&ba.enqueueReplaceState(a,a.state,null),aa(e,n,a,r),a.state=e.memoizedState),typeof a.componentDidMount=="function"&&(e.flags|=4194308)}function sn(e,t){try{var n="",r=t;do n+=Yd(r),r=r.return;while(r);var a=n}catch(i){a=`
Error generating stack: `+i.message+`
`+i.stack}return{value:e,source:t,stack:a,digest:null}}function ci(e,t,n){return{value:e,source:null,stack:n??null,digest:t??null}}function ji(e,t){try{console.error(t.value)}catch(n){setTimeout(function(){throw n})}}var bh=typeof WeakMap=="function"?WeakMap:Map;function dc(e,t,n){n=Ve(-1,n),n.tag=3,n.payload={element:null};var r=t.value;return n.callback=function(){ua||(ua=!0,no=r),ji(e,t)},n}function hc(e,t,n){n=Ve(-1,n),n.tag=3;var r=e.type.getDerivedStateFromError;if(typeof r=="function"){var a=t.value;n.payload=function(){return r(a)},n.callback=function(){ji(e,t)}}var i=e.stateNode;return i!==null&&typeof i.componentDidCatch=="function"&&(n.callback=function(){ji(e,t),typeof r!="function"&&(ct===null?ct=new Set([this]):ct.add(this));var o=t.stack;this.componentDidCatch(t.value,{componentStack:o!==null?o:""})}),n}function Ss(e,t,n){var r=e.pingCache;if(r===null){r=e.pingCache=new bh;var a=new Set;r.set(t,a)}else a=r.get(t),a===void 0&&(a=new Set,r.set(t,a));a.has(n)||(a.add(n),e=$h.bind(null,e,t,n),t.then(e,e))}function Es(e){do{var t;if((t=e.tag===13)&&(t=e.memoizedState,t=t!==null?t.dehydrated!==null:!0),t)return e;e=e.return}while(e!==null);return null}function zs(e,t,n,r,a){return(e.mode&1)===0?(e===t?e.flags|=65536:(e.flags|=128,n.flags|=131072,n.flags&=-52805,n.tag===1&&(n.alternate===null?n.tag=17:(t=Ve(-1,1),t.tag=2,ut(n,t,1))),n.lanes|=1),e):(e.flags|=65536,e.lanes=a,e)}var xh=Ye.ReactCurrentOwner,oe=!1;function ne(e,t,n,r){t.child=e===null?Iu(t,null,n,r):on(t,e.child,n,r)}function Ts(e,t,n,r,a){n=n.render;var i=t.ref;return en(t,a),r=Ho(e,t,n,r,i,a),n=Fo(),e!==null&&!oe?(t.updateQueue=e.updateQueue,t.flags&=-2053,e.lanes&=~a,Ke(e,t,a)):($&&n&&So(t),t.flags|=1,ne(e,t,r,a),t.child)}function Rs(e,t,n,r,a){if(e===null){var i=n.type;return typeof i=="function"&&!jo(i)&&i.defaultProps===void 0&&n.compare===null&&n.defaultProps===void 0?(t.tag=15,t.type=i,pc(e,t,i,r,a)):(e=Br(n.type,null,r,t,t.mode,a),e.ref=t.ref,e.return=t,t.child=e)}if(i=e.child,(e.lanes&a)===0){var o=i.memoizedProps;if(n=n.compare,n=n!==null?n:qn,n(o,r)&&e.ref===t.ref)return Ke(e,t,a)}return t.flags|=1,e=ht(i,r),e.ref=t.ref,e.return=t,t.child=e}function pc(e,t,n,r,a){if(e!==null){var i=e.memoizedProps;if(qn(i,r)&&e.ref===t.ref)if(oe=!1,t.pendingProps=r=i,(e.lanes&a)!==0)(e.flags&131072)!==0&&(oe=!0);else return t.lanes=e.lanes,Ke(e,t,a)}return Gi(e,t,n,r,a)}function fc(e,t,n){var r=t.pendingProps,a=r.children,i=e!==null?e.memoizedState:null;if(r.mode==="hidden")if((t.mode&1)===0)t.memoizedState={baseLanes:0,cachePool:null,transitions:null},L(Yt,de),de|=n;else{if((n&1073741824)===0)return e=i!==null?i.baseLanes|n:n,t.lanes=t.childLanes=1073741824,t.memoizedState={baseLanes:e,cachePool:null,transitions:null},t.updateQueue=null,L(Yt,de),de|=e,null;t.memoizedState={baseLanes:0,cachePool:null,transitions:null},r=i!==null?i.baseLanes:n,L(Yt,de),de|=r}else i!==null?(r=i.baseLanes|n,t.memoizedState=null):r=n,L(Yt,de),de|=r;return ne(e,t,a,n),t.child}function gc(e,t){var n=t.ref;(e===null&&n!==null||e!==null&&e.ref!==n)&&(t.flags|=512,t.flags|=2097152)}function Gi(e,t,n,r,a){var i=se(n)?Rt:ee.current;return i=rn(t,i),en(t,a),n=Ho(e,t,n,r,i,a),r=Fo(),e!==null&&!oe?(t.updateQueue=e.updateQueue,t.flags&=-2053,e.lanes&=~a,Ke(e,t,a)):($&&r&&So(t),t.flags|=1,ne(e,t,n,a),t.child)}function _s(e,t,n,r,a){if(se(n)){var i=!0;Jr(t)}else i=!1;if(en(t,a),t.stateNode===null)Or(e,t),cc(t,n,r),qi(t,n,r,a),r=!0;else if(e===null){var o=t.stateNode,l=t.memoizedProps;o.props=l;var s=o.context,c=n.contextType;typeof c=="object"&&c!==null?c=ke(c):(c=se(n)?Rt:ee.current,c=rn(t,c));var f=n.getDerivedStateFromProps,g=typeof f=="function"||typeof o.getSnapshotBeforeUpdate=="function";g||typeof o.UNSAFE_componentWillReceiveProps!="function"&&typeof o.componentWillReceiveProps!="function"||(l!==r||s!==c)&&ks(t,o,r,c),et=!1;var p=t.memoizedState;o.state=p,aa(t,r,o,a),s=t.memoizedState,l!==r||p!==s||le.current||et?(typeof f=="function"&&(Vi(t,n,f,r),s=t.memoizedState),(l=et||xs(t,n,l,r,p,s,c))?(g||typeof o.UNSAFE_componentWillMount!="function"&&typeof o.componentWillMount!="function"||(typeof o.componentWillMount=="function"&&o.componentWillMount(),typeof o.UNSAFE_componentWillMount=="function"&&o.UNSAFE_componentWillMount()),typeof o.componentDidMount=="function"&&(t.flags|=4194308)):(typeof o.componentDidMount=="function"&&(t.flags|=4194308),t.memoizedProps=r,t.memoizedState=s),o.props=r,o.state=s,o.context=c,r=l):(typeof o.componentDidMount=="function"&&(t.flags|=4194308),r=!1)}else{o=t.stateNode,Uu(e,t),l=t.memoizedProps,c=t.type===t.elementType?l:Te(t.type,l),o.props=c,g=t.pendingProps,p=o.context,s=n.contextType,typeof s=="object"&&s!==null?s=ke(s):(s=se(n)?Rt:ee.current,s=rn(t,s));var w=n.getDerivedStateFromProps;(f=typeof w=="function"||typeof o.getSnapshotBeforeUpdate=="function")||typeof o.UNSAFE_componentWillReceiveProps!="function"&&typeof o.componentWillReceiveProps!="function"||(l!==g||p!==s)&&ks(t,o,r,s),et=!1,p=t.memoizedState,o.state=p,aa(t,r,o,a);var y=t.memoizedState;l!==g||p!==y||le.current||et?(typeof w=="function"&&(Vi(t,n,w,r),y=t.memoizedState),(c=et||xs(t,n,c,r,p,y,s)||!1)?(f||typeof o.UNSAFE_componentWillUpdate!="function"&&typeof o.componentWillUpdate!="function"||(typeof o.componentWillUpdate=="function"&&o.componentWillUpdate(r,y,s),typeof o.UNSAFE_componentWillUpdate=="function"&&o.UNSAFE_componentWillUpdate(r,y,s)),typeof o.componentDidUpdate=="function"&&(t.flags|=4),typeof o.getSnapshotBeforeUpdate=="function"&&(t.flags|=1024)):(typeof o.componentDidUpdate!="function"||l===e.memoizedProps&&p===e.memoizedState||(t.flags|=4),typeof o.getSnapshotBeforeUpdate!="function"||l===e.memoizedProps&&p===e.memoizedState||(t.flags|=1024),t.memoizedProps=r,t.memoizedState=y),o.props=r,o.state=y,o.context=s,r=c):(typeof o.componentDidUpdate!="function"||l===e.memoizedProps&&p===e.memoizedState||(t.flags|=4),typeof o.getSnapshotBeforeUpdate!="function"||l===e.memoizedProps&&p===e.memoizedState||(t.flags|=1024),r=!1)}return Ki(e,t,n,r,i,a)}function Ki(e,t,n,r,a,i){gc(e,t);var o=(t.flags&128)!==0;if(!r&&!o)return a&&ps(t,n,!1),Ke(e,t,i);r=t.stateNode,xh.current=t;var l=o&&typeof n.getDerivedStateFromError!="function"?null:r.render();return t.flags|=1,e!==null&&o?(t.child=on(t,e.child,null,i),t.child=on(t,null,l,i)):ne(e,t,l,i),t.memoizedState=r.state,a&&ps(t,n,!0),t.child}function mc(e){var t=e.stateNode;t.pendingContext?hs(e,t.pendingContext,t.pendingContext!==t.context):t.context&&hs(e,t.context,!1),Lo(e,t.containerInfo)}function Cs(e,t,n,r,a){return an(),zo(a),t.flags|=256,ne(e,t,n,r),t.child}var Yi={dehydrated:null,treeContext:null,retryLane:0};function Xi(e){return{baseLanes:e,cachePool:null,transitions:null}}function vc(e,t,n){var r=t.pendingProps,a=N.current,i=!1,o=(t.flags&128)!==0,l;if((l=o)||(l=e!==null&&e.memoizedState===null?!1:(a&2)!==0),l?(i=!0,t.flags&=-129):(e===null||e.memoizedState!==null)&&(a|=1),L(N,a&1),e===null)return Bi(t),e=t.memoizedState,e!==null&&(e=e.dehydrated,e!==null)?((t.mode&1)===0?t.lanes=1:e.data==="$!"?t.lanes=8:t.lanes=1073741824,null):(o=r.children,e=r.fallback,i?(r=t.mode,i=t.child,o={mode:"hidden",children:o},(r&1)===0&&i!==null?(i.childLanes=0,i.pendingProps=o):i=Sa(o,r,0,null),e=Tt(e,r,n,null),i.return=t,e.return=t,i.sibling=e,t.child=i,t.child.memoizedState=Xi(n),t.memoizedState=Yi,e):Oo(t,o));if(a=e.memoizedState,a!==null&&(l=a.dehydrated,l!==null))return kh(e,t,o,r,l,a,n);if(i){i=r.fallback,o=t.mode,a=e.child,l=a.sibling;var s={mode:"hidden",children:r.children};return(o&1)===0&&t.child!==a?(r=t.child,r.childLanes=0,r.pendingProps=s,t.deletions=null):(r=ht(a,s),r.subtreeFlags=a.subtreeFlags&14680064),l!==null?i=ht(l,i):(i=Tt(i,o,n,null),i.flags|=2),i.return=t,r.return=t,r.sibling=i,t.child=r,r=i,i=t.child,o=e.child.memoizedState,o=o===null?Xi(n):{baseLanes:o.baseLanes|n,cachePool:null,transitions:o.transitions},i.memoizedState=o,i.childLanes=e.childLanes&~n,t.memoizedState=Yi,r}return i=e.child,e=i.sibling,r=ht(i,{mode:"visible",children:r.children}),(t.mode&1)===0&&(r.lanes=n),r.return=t,r.sibling=null,e!==null&&(n=t.deletions,n===null?(t.deletions=[e],t.flags|=16):n.push(e)),t.child=r,t.memoizedState=null,r}function Oo(e,t){return t=Sa({mode:"visible",children:t},e.mode,0,null),t.return=e,e.child=t}function Pr(e,t,n,r){return r!==null&&zo(r),on(t,e.child,null,n),e=Oo(t,t.pendingProps.children),e.flags|=2,t.memoizedState=null,e}function kh(e,t,n,r,a,i,o){if(n)return t.flags&256?(t.flags&=-257,r=ci(Error(v(422))),Pr(e,t,o,r)):t.memoizedState!==null?(t.child=e.child,t.flags|=128,null):(i=r.fallback,a=t.mode,r=Sa({mode:"visible",children:r.children},a,0,null),i=Tt(i,a,o,null),i.flags|=2,r.return=t,i.return=t,r.sibling=i,t.child=r,(t.mode&1)!==0&&on(t,e.child,null,o),t.child.memoizedState=Xi(o),t.memoizedState=Yi,i);if((t.mode&1)===0)return Pr(e,t,o,null);if(a.data==="$!"){if(r=a.nextSibling&&a.nextSibling.dataset,r)var l=r.dgst;return r=l,i=Error(v(419)),r=ci(i,r,void 0),Pr(e,t,o,r)}if(l=(o&e.childLanes)!==0,oe||l){if(r=j,r!==null){switch(o&-o){case 4:a=2;break;case 16:a=8;break;case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:a=32;break;case 536870912:a=268435456;break;default:a=0}a=(a&(r.suspendedLanes|o))!==0?0:a,a!==0&&a!==i.retryLane&&(i.retryLane=a,Ge(e,a),Pe(r,e,a,-1))}return qo(),r=ci(Error(v(421))),Pr(e,t,o,r)}return a.data==="$?"?(t.flags|=128,t.child=e.child,t=Hh.bind(null,e),a._reactRetry=t,null):(e=i.treeContext,he=st(a.nextSibling),pe=t,$=!0,_e=null,e!==null&&(we[ye++]=Be,we[ye++]=Ue,we[ye++]=_t,Be=e.id,Ue=e.overflow,_t=t),t=Oo(t,r.children),t.flags|=4096,t)}function Ps(e,t,n){e.lanes|=t;var r=e.alternate;r!==null&&(r.lanes|=t),Ui(e.return,t,n)}function di(e,t,n,r,a){var i=e.memoizedState;i===null?e.memoizedState={isBackwards:t,rendering:null,renderingStartTime:0,last:r,tail:n,tailMode:a}:(i.isBackwards=t,i.rendering=null,i.renderingStartTime=0,i.last=r,i.tail=n,i.tailMode=a)}function wc(e,t,n){var r=t.pendingProps,a=r.revealOrder,i=r.tail;if(ne(e,t,r.children,n),r=N.current,(r&2)!==0)r=r&1|2,t.flags|=128;else{if(e!==null&&(e.flags&128)!==0)e:for(e=t.child;e!==null;){if(e.tag===13)e.memoizedState!==null&&Ps(e,n,t);else if(e.tag===19)Ps(e,n,t);else if(e.child!==null){e.child.return=e,e=e.child;continue}if(e===t)break e;for(;e.sibling===null;){if(e.return===null||e.return===t)break e;e=e.return}e.sibling.return=e.return,e=e.sibling}r&=1}if(L(N,r),(t.mode&1)===0)t.memoizedState=null;else switch(a){case"forwards":for(n=t.child,a=null;n!==null;)e=n.alternate,e!==null&&ia(e)===null&&(a=n),n=n.sibling;n=a,n===null?(a=t.child,t.child=null):(a=n.sibling,n.sibling=null),di(t,!1,a,n,i);break;case"backwards":for(n=null,a=t.child,t.child=null;a!==null;){if(e=a.alternate,e!==null&&ia(e)===null){t.child=a;break}e=a.sibling,a.sibling=n,n=a,a=e}di(t,!0,n,null,i);break;case"together":di(t,!1,null,null,void 0);break;default:t.memoizedState=null}return t.child}function Or(e,t){(t.mode&1)===0&&e!==null&&(e.alternate=null,t.alternate=null,t.flags|=2)}function Ke(e,t,n){if(e!==null&&(t.dependencies=e.dependencies),Pt|=t.lanes,(n&t.childLanes)===0)return null;if(e!==null&&t.child!==e.child)throw Error(v(153));if(t.child!==null){for(e=t.child,n=ht(e,e.pendingProps),t.child=n,n.return=t;e.sibling!==null;)e=e.sibling,n=n.sibling=ht(e,e.pendingProps),n.return=t;n.sibling=null}return t.child}function Sh(e,t,n){switch(t.tag){case 3:mc(t),an();break;case 5:Vu(t);break;case 1:se(t.type)&&Jr(t);break;case 4:Lo(t,t.stateNode.containerInfo);break;case 10:var r=t.type._context,a=t.memoizedProps.value;L(na,r._currentValue),r._currentValue=a;break;case 13:if(r=t.memoizedState,r!==null)return r.dehydrated!==null?(L(N,N.current&1),t.flags|=128,null):(n&t.child.childLanes)!==0?vc(e,t,n):(L(N,N.current&1),e=Ke(e,t,n),e!==null?e.sibling:null);L(N,N.current&1);break;case 19:if(r=(n&t.childLanes)!==0,(e.flags&128)!==0){if(r)return wc(e,t,n);t.flags|=128}if(a=t.memoizedState,a!==null&&(a.rendering=null,a.tail=null,a.lastEffect=null),L(N,N.current),r)break;return null;case 22:case 23:return t.lanes=0,fc(e,t,n)}return Ke(e,t,n)}var yc,Qi,bc,xc;yc=function(e,t){for(var n=t.child;n!==null;){if(n.tag===5||n.tag===6)e.appendChild(n.stateNode);else if(n.tag!==4&&n.child!==null){n.child.return=n,n=n.child;continue}if(n===t)break;for(;n.sibling===null;){if(n.return===null||n.return===t)return;n=n.return}n.sibling.return=n.return,n=n.sibling}};Qi=function(){};bc=function(e,t,n,r){var a=e.memoizedProps;if(a!==r){e=t.stateNode,Et(Ne.current);var i=null;switch(n){case"input":a=yi(e,a),r=yi(e,r),i=[];break;case"select":a=O({},a,{value:void 0}),r=O({},r,{value:void 0}),i=[];break;case"textarea":a=ki(e,a),r=ki(e,r),i=[];break;default:typeof a.onClick!="function"&&typeof r.onClick=="function"&&(e.onclick=Qr)}Ei(n,r);var o;n=null;for(c in a)if(!r.hasOwnProperty(c)&&a.hasOwnProperty(c)&&a[c]!=null)if(c==="style"){var l=a[c];for(o in l)l.hasOwnProperty(o)&&(n||(n={}),n[o]="")}else c!=="dangerouslySetInnerHTML"&&c!=="children"&&c!=="suppressContentEditableWarning"&&c!=="suppressHydrationWarning"&&c!=="autoFocus"&&(Dn.hasOwnProperty(c)?i||(i=[]):(i=i||[]).push(c,null));for(c in r){var s=r[c];if(l=a?.[c],r.hasOwnProperty(c)&&s!==l&&(s!=null||l!=null))if(c==="style")if(l){for(o in l)!l.hasOwnProperty(o)||s&&s.hasOwnProperty(o)||(n||(n={}),n[o]="");for(o in s)s.hasOwnProperty(o)&&l[o]!==s[o]&&(n||(n={}),n[o]=s[o])}else n||(i||(i=[]),i.push(c,n)),n=s;else c==="dangerouslySetInnerHTML"?(s=s?s.__html:void 0,l=l?l.__html:void 0,s!=null&&l!==s&&(i=i||[]).push(c,s)):c==="children"?typeof s!="string"&&typeof s!="number"||(i=i||[]).push(c,""+s):c!=="suppressContentEditableWarning"&&c!=="suppressHydrationWarning"&&(Dn.hasOwnProperty(c)?(s!=null&&c==="onScroll"&&A("scroll",e),i||l===s||(i=[])):(i=i||[]).push(c,s))}n&&(i=i||[]).push("style",n);var c=i;(t.updateQueue=c)&&(t.flags|=4)}};xc=function(e,t,n,r){n!==r&&(t.flags|=4)};function kn(e,t){if(!$)switch(e.tailMode){case"hidden":t=e.tail;for(var n=null;t!==null;)t.alternate!==null&&(n=t),t=t.sibling;n===null?e.tail=null:n.sibling=null;break;case"collapsed":n=e.tail;for(var r=null;n!==null;)n.alternate!==null&&(r=n),n=n.sibling;r===null?t||e.tail===null?e.tail=null:e.tail.sibling=null:r.sibling=null}}function Z(e){var t=e.alternate!==null&&e.alternate.child===e.child,n=0,r=0;if(t)for(var a=e.child;a!==null;)n|=a.lanes|a.childLanes,r|=a.subtreeFlags&14680064,r|=a.flags&14680064,a.return=e,a=a.sibling;else for(a=e.child;a!==null;)n|=a.lanes|a.childLanes,r|=a.subtreeFlags,r|=a.flags,a.return=e,a=a.sibling;return e.subtreeFlags|=r,e.childLanes=n,t}function Eh(e,t,n){var r=t.pendingProps;switch(Eo(t),t.tag){case 2:case 16:case 15:case 0:case 11:case 7:case 8:case 12:case 9:case 14:return Z(t),null;case 1:return se(t.type)&&Zr(),Z(t),null;case 3:return r=t.stateNode,ln(),M(le),M(ee),Mo(),r.pendingContext&&(r.context=r.pendingContext,r.pendingContext=null),(e===null||e.child===null)&&(_r(t)?t.flags|=4:e===null||e.memoizedState.isDehydrated&&(t.flags&256)===0||(t.flags|=1024,_e!==null&&(io(_e),_e=null))),Qi(e,t),Z(t),null;case 5:Ao(t);var a=Et(Xn.current);if(n=t.type,e!==null&&t.stateNode!=null)bc(e,t,n,r,a),e.ref!==t.ref&&(t.flags|=512,t.flags|=2097152);else{if(!r){if(t.stateNode===null)throw Error(v(166));return Z(t),null}if(e=Et(Ne.current),_r(t)){r=t.stateNode,n=t.type;var i=t.memoizedProps;switch(r[He]=t,r[Kn]=i,e=(t.mode&1)!==0,n){case"dialog":A("cancel",r),A("close",r);break;case"iframe":case"object":case"embed":A("load",r);break;case"video":case"audio":for(a=0;a<_n.length;a++)A(_n[a],r);break;case"source":A("error",r);break;case"img":case"image":case"link":A("error",r),A("load",r);break;case"details":A("toggle",r);break;case"input":Dl(r,i),A("invalid",r);break;case"select":r._wrapperState={wasMultiple:!!i.multiple},A("invalid",r);break;case"textarea":Wl(r,i),A("invalid",r)}Ei(n,i),a=null;for(var o in i)if(i.hasOwnProperty(o)){var l=i[o];o==="children"?typeof l=="string"?r.textContent!==l&&(i.suppressHydrationWarning!==!0&&Rr(r.textContent,l,e),a=["children",l]):typeof l=="number"&&r.textContent!==""+l&&(i.suppressHydrationWarning!==!0&&Rr(r.textContent,l,e),a=["children",""+l]):Dn.hasOwnProperty(o)&&l!=null&&o==="onScroll"&&A("scroll",r)}switch(n){case"input":gr(r),Ol(r,i,!0);break;case"textarea":gr(r),Il(r);break;case"select":case"option":break;default:typeof i.onClick=="function"&&(r.onclick=Qr)}r=a,t.updateQueue=r,r!==null&&(t.flags|=4)}else{o=a.nodeType===9?a:a.ownerDocument,e==="http://www.w3.org/1999/xhtml"&&(e=Ys(n)),e==="http://www.w3.org/1999/xhtml"?n==="script"?(e=o.createElement("div"),e.innerHTML="<script><\/script>",e=e.removeChild(e.firstChild)):typeof r.is=="string"?e=o.createElement(n,{is:r.is}):(e=o.createElement(n),n==="select"&&(o=e,r.multiple?o.multiple=!0:r.size&&(o.size=r.size))):e=o.createElementNS(e,n),e[He]=t,e[Kn]=r,yc(e,t,!1,!1),t.stateNode=e;e:{switch(o=zi(n,r),n){case"dialog":A("cancel",e),A("close",e),a=r;break;case"iframe":case"object":case"embed":A("load",e),a=r;break;case"video":case"audio":for(a=0;a<_n.length;a++)A(_n[a],e);a=r;break;case"source":A("error",e),a=r;break;case"img":case"image":case"link":A("error",e),A("load",e),a=r;break;case"details":A("toggle",e),a=r;break;case"input":Dl(e,r),a=yi(e,r),A("invalid",e);break;case"option":a=r;break;case"select":e._wrapperState={wasMultiple:!!r.multiple},a=O({},r,{value:void 0}),A("invalid",e);break;case"textarea":Wl(e,r),a=ki(e,r),A("invalid",e);break;default:a=r}Ei(n,a),l=a;for(i in l)if(l.hasOwnProperty(i)){var s=l[i];i==="style"?Zs(e,s):i==="dangerouslySetInnerHTML"?(s=s?s.__html:void 0,s!=null&&Xs(e,s)):i==="children"?typeof s=="string"?(n!=="textarea"||s!=="")&&On(e,s):typeof s=="number"&&On(e,""+s):i!=="suppressContentEditableWarning"&&i!=="suppressHydrationWarning"&&i!=="autoFocus"&&(Dn.hasOwnProperty(i)?s!=null&&i==="onScroll"&&A("scroll",e):s!=null&&so(e,i,s,o))}switch(n){case"input":gr(e),Ol(e,r,!1);break;case"textarea":gr(e),Il(e);break;case"option":r.value!=null&&e.setAttribute("value",""+pt(r.value));break;case"select":e.multiple=!!r.multiple,i=r.value,i!=null?Xt(e,!!r.multiple,i,!1):r.defaultValue!=null&&Xt(e,!!r.multiple,r.defaultValue,!0);break;default:typeof a.onClick=="function"&&(e.onclick=Qr)}switch(n){case"button":case"input":case"select":case"textarea":r=!!r.autoFocus;break e;case"img":r=!0;break e;default:r=!1}}r&&(t.flags|=4)}t.ref!==null&&(t.flags|=512,t.flags|=2097152)}return Z(t),null;case 6:if(e&&t.stateNode!=null)xc(e,t,e.memoizedProps,r);else{if(typeof r!="string"&&t.stateNode===null)throw Error(v(166));if(n=Et(Xn.current),Et(Ne.current),_r(t)){if(r=t.stateNode,n=t.memoizedProps,r[He]=t,(i=r.nodeValue!==n)&&(e=pe,e!==null))switch(e.tag){case 3:Rr(r.nodeValue,n,(e.mode&1)!==0);break;case 5:e.memoizedProps.suppressHydrationWarning!==!0&&Rr(r.nodeValue,n,(e.mode&1)!==0)}i&&(t.flags|=4)}else r=(n.nodeType===9?n:n.ownerDocument).createTextNode(r),r[He]=t,t.stateNode=r}return Z(t),null;case 13:if(M(N),r=t.memoizedState,e===null||e.memoizedState!==null&&e.memoizedState.dehydrated!==null){if($&&he!==null&&(t.mode&1)!==0&&(t.flags&128)===0)Ou(),an(),t.flags|=98560,i=!1;else if(i=_r(t),r!==null&&r.dehydrated!==null){if(e===null){if(!i)throw Error(v(318));if(i=t.memoizedState,i=i!==null?i.dehydrated:null,!i)throw Error(v(317));i[He]=t}else an(),(t.flags&128)===0&&(t.memoizedState=null),t.flags|=4;Z(t),i=!1}else _e!==null&&(io(_e),_e=null),i=!0;if(!i)return t.flags&65536?t:null}return(t.flags&128)!==0?(t.lanes=n,t):(r=r!==null,r!==(e!==null&&e.memoizedState!==null)&&r&&(t.child.flags|=8192,(t.mode&1)!==0&&(e===null||(N.current&1)!==0?V===0&&(V=3):qo())),t.updateQueue!==null&&(t.flags|=4),Z(t),null);case 4:return ln(),Qi(e,t),e===null&&jn(t.stateNode.containerInfo),Z(t),null;case 10:return _o(t.type._context),Z(t),null;case 17:return se(t.type)&&Zr(),Z(t),null;case 19:if(M(N),i=t.memoizedState,i===null)return Z(t),null;if(r=(t.flags&128)!==0,o=i.rendering,o===null)if(r)kn(i,!1);else{if(V!==0||e!==null&&(e.flags&128)!==0)for(e=t.child;e!==null;){if(o=ia(e),o!==null){for(t.flags|=128,kn(i,!1),r=o.updateQueue,r!==null&&(t.updateQueue=r,t.flags|=4),t.subtreeFlags=0,r=n,n=t.child;n!==null;)i=n,e=r,i.flags&=14680066,o=i.alternate,o===null?(i.childLanes=0,i.lanes=e,i.child=null,i.subtreeFlags=0,i.memoizedProps=null,i.memoizedState=null,i.updateQueue=null,i.dependencies=null,i.stateNode=null):(i.childLanes=o.childLanes,i.lanes=o.lanes,i.child=o.child,i.subtreeFlags=0,i.deletions=null,i.memoizedProps=o.memoizedProps,i.memoizedState=o.memoizedState,i.updateQueue=o.updateQueue,i.type=o.type,e=o.dependencies,i.dependencies=e===null?null:{lanes:e.lanes,firstContext:e.firstContext}),n=n.sibling;return L(N,N.current&1|2),t.child}e=e.sibling}i.tail!==null&&I()>un&&(t.flags|=128,r=!0,kn(i,!1),t.lanes=4194304)}else{if(!r)if(e=ia(o),e!==null){if(t.flags|=128,r=!0,n=e.updateQueue,n!==null&&(t.updateQueue=n,t.flags|=4),kn(i,!0),i.tail===null&&i.tailMode==="hidden"&&!o.alternate&&!$)return Z(t),null}else 2*I()-i.renderingStartTime>un&&n!==1073741824&&(t.flags|=128,r=!0,kn(i,!1),t.lanes=4194304);i.isBackwards?(o.sibling=t.child,t.child=o):(n=i.last,n!==null?n.sibling=o:t.child=o,i.last=o)}return i.tail!==null?(t=i.tail,i.rendering=t,i.tail=t.sibling,i.renderingStartTime=I(),t.sibling=null,n=N.current,L(N,r?n&1|2:n&1),t):(Z(t),null);case 22:case 23:return Vo(),r=t.memoizedState!==null,e!==null&&e.memoizedState!==null!==r&&(t.flags|=8192),r&&(t.mode&1)!==0?(de&1073741824)!==0&&(Z(t),t.subtreeFlags&6&&(t.flags|=8192)):Z(t),null;case 24:return null;case 25:return null}throw Error(v(156,t.tag))}function zh(e,t){switch(Eo(t),t.tag){case 1:return se(t.type)&&Zr(),e=t.flags,e&65536?(t.flags=e&-65537|128,t):null;case 3:return ln(),M(le),M(ee),Mo(),e=t.flags,(e&65536)!==0&&(e&128)===0?(t.flags=e&-65537|128,t):null;case 5:return Ao(t),null;case 13:if(M(N),e=t.memoizedState,e!==null&&e.dehydrated!==null){if(t.alternate===null)throw Error(v(340));an()}return e=t.flags,e&65536?(t.flags=e&-65537|128,t):null;case 19:return M(N),null;case 4:return ln(),null;case 10:return _o(t.type._context),null;case 22:case 23:return Vo(),null;case 24:return null;default:return null}}var Lr=!1,J=!1,Th=typeof WeakSet=="function"?WeakSet:Set,x=null;function Kt(e,t){var n=e.ref;if(n!==null)if(typeof n=="function")try{n(null)}catch(r){W(e,t,r)}else n.current=null}function Zi(e,t,n){try{n()}catch(r){W(e,t,r)}}var Ls=!1;function Rh(e,t){if(Hi=Kr,e=Tu(),ko(e)){if("selectionStart"in e)var n={start:e.selectionStart,end:e.selectionEnd};else e:{n=(n=e.ownerDocument)&&n.defaultView||window;var r=n.getSelection&&n.getSelection();if(r&&r.rangeCount!==0){n=r.anchorNode;var a=r.anchorOffset,i=r.focusNode;r=r.focusOffset;try{n.nodeType,i.nodeType}catch{n=null;break e}var o=0,l=-1,s=-1,c=0,f=0,g=e,p=null;t:for(;;){for(var w;g!==n||a!==0&&g.nodeType!==3||(l=o+a),g!==i||r!==0&&g.nodeType!==3||(s=o+r),g.nodeType===3&&(o+=g.nodeValue.length),(w=g.firstChild)!==null;)p=g,g=w;for(;;){if(g===e)break t;if(p===n&&++c===a&&(l=o),p===i&&++f===r&&(s=o),(w=g.nextSibling)!==null)break;g=p,p=g.parentNode}g=w}n=l===-1||s===-1?null:{start:l,end:s}}else n=null}n=n||{start:0,end:0}}else n=null;for(Fi={focusedElem:e,selectionRange:n},Kr=!1,x=t;x!==null;)if(t=x,e=t.child,(t.subtreeFlags&1028)!==0&&e!==null)e.return=t,x=e;else for(;x!==null;){t=x;try{var y=t.alternate;if((t.flags&1024)!==0)switch(t.tag){case 0:case 11:case 15:break;case 1:if(y!==null){var b=y.memoizedProps,H=y.memoizedState,h=t.stateNode,u=h.getSnapshotBeforeUpdate(t.elementType===t.type?b:Te(t.type,b),H);h.__reactInternalSnapshotBeforeUpdate=u}break;case 3:var d=t.stateNode.containerInfo;d.nodeType===1?d.textContent="":d.nodeType===9&&d.documentElement&&d.removeChild(d.documentElement);break;case 5:case 6:case 4:case 17:break;default:throw Error(v(163))}}catch(m){W(t,t.return,m)}if(e=t.sibling,e!==null){e.return=t.return,x=e;break}x=t.return}return y=Ls,Ls=!1,y}function Hn(e,t,n){var r=t.updateQueue;if(r=r!==null?r.lastEffect:null,r!==null){var a=r=r.next;do{if((a.tag&e)===e){var i=a.destroy;a.destroy=void 0,i!==void 0&&Zi(t,n,i)}a=a.next}while(a!==r)}}function xa(e,t){if(t=t.updateQueue,t=t!==null?t.lastEffect:null,t!==null){var n=t=t.next;do{if((n.tag&e)===e){var r=n.create;n.destroy=r()}n=n.next}while(n!==t)}}function Ji(e){var t=e.ref;if(t!==null){var n=e.stateNode;switch(e.tag){case 5:e=n;break;default:e=n}typeof t=="function"?t(e):t.current=e}}function kc(e){var t=e.alternate;t!==null&&(e.alternate=null,kc(t)),e.child=null,e.deletions=null,e.sibling=null,e.tag===5&&(t=e.stateNode,t!==null&&(delete t[He],delete t[Kn],delete t[Oi],delete t[uh],delete t[ch])),e.stateNode=null,e.return=null,e.dependencies=null,e.memoizedProps=null,e.memoizedState=null,e.pendingProps=null,e.stateNode=null,e.updateQueue=null}function Sc(e){return e.tag===5||e.tag===3||e.tag===4}function As(e){e:for(;;){for(;e.sibling===null;){if(e.return===null||Sc(e.return))return null;e=e.return}for(e.sibling.return=e.return,e=e.sibling;e.tag!==5&&e.tag!==6&&e.tag!==18;){if(e.flags&2||e.child===null||e.tag===4)continue e;e.child.return=e,e=e.child}if(!(e.flags&2))return e.stateNode}}function eo(e,t,n){var r=e.tag;if(r===5||r===6)e=e.stateNode,t?n.nodeType===8?n.parentNode.insertBefore(e,t):n.insertBefore(e,t):(n.nodeType===8?(t=n.parentNode,t.insertBefore(e,n)):(t=n,t.appendChild(e)),n=n._reactRootContainer,n!=null||t.onclick!==null||(t.onclick=Qr));else if(r!==4&&(e=e.child,e!==null))for(eo(e,t,n),e=e.sibling;e!==null;)eo(e,t,n),e=e.sibling}function to(e,t,n){var r=e.tag;if(r===5||r===6)e=e.stateNode,t?n.insertBefore(e,t):n.appendChild(e);else if(r!==4&&(e=e.child,e!==null))for(to(e,t,n),e=e.sibling;e!==null;)to(e,t,n),e=e.sibling}var G=null,Re=!1;function Ze(e,t,n){for(n=n.child;n!==null;)Ec(e,t,n),n=n.sibling}function Ec(e,t,n){if(Fe&&typeof Fe.onCommitFiberUnmount=="function")try{Fe.onCommitFiberUnmount(pa,n)}catch{}switch(n.tag){case 5:J||Kt(n,t);case 6:var r=G,a=Re;G=null,Ze(e,t,n),G=r,Re=a,G!==null&&(Re?(e=G,n=n.stateNode,e.nodeType===8?e.parentNode.removeChild(n):e.removeChild(n)):G.removeChild(n.stateNode));break;case 18:G!==null&&(Re?(e=G,n=n.stateNode,e.nodeType===8?ai(e.parentNode,n):e.nodeType===1&&ai(e,n),Un(e)):ai(G,n.stateNode));break;case 4:r=G,a=Re,G=n.stateNode.containerInfo,Re=!0,Ze(e,t,n),G=r,Re=a;break;case 0:case 11:case 14:case 15:if(!J&&(r=n.updateQueue,r!==null&&(r=r.lastEffect,r!==null))){a=r=r.next;do{var i=a,o=i.destroy;i=i.tag,o!==void 0&&((i&2)!==0||(i&4)!==0)&&Zi(n,t,o),a=a.next}while(a!==r)}Ze(e,t,n);break;case 1:if(!J&&(Kt(n,t),r=n.stateNode,typeof r.componentWillUnmount=="function"))try{r.props=n.memoizedProps,r.state=n.memoizedState,r.componentWillUnmount()}catch(l){W(n,t,l)}Ze(e,t,n);break;case 21:Ze(e,t,n);break;case 22:n.mode&1?(J=(r=J)||n.memoizedState!==null,Ze(e,t,n),J=r):Ze(e,t,n);break;default:Ze(e,t,n)}}function Ms(e){var t=e.updateQueue;if(t!==null){e.updateQueue=null;var n=e.stateNode;n===null&&(n=e.stateNode=new Th),t.forEach(function(r){var a=Fh.bind(null,e,r);n.has(r)||(n.add(r),r.then(a,a))})}}function ze(e,t){var n=t.deletions;if(n!==null)for(var r=0;r<n.length;r++){var a=n[r];try{var i=e,o=t,l=o;e:for(;l!==null;){switch(l.tag){case 5:G=l.stateNode,Re=!1;break e;case 3:G=l.stateNode.containerInfo,Re=!0;break e;case 4:G=l.stateNode.containerInfo,Re=!0;break e}l=l.return}if(G===null)throw Error(v(160));Ec(i,o,a),G=null,Re=!1;var s=a.alternate;s!==null&&(s.return=null),a.return=null}catch(c){W(a,t,c)}}if(t.subtreeFlags&12854)for(t=t.child;t!==null;)zc(t,e),t=t.sibling}function zc(e,t){var n=e.alternate,r=e.flags;switch(e.tag){case 0:case 11:case 14:case 15:if(ze(t,e),Me(e),r&4){try{Hn(3,e,e.return),xa(3,e)}catch(b){W(e,e.return,b)}try{Hn(5,e,e.return)}catch(b){W(e,e.return,b)}}break;case 1:ze(t,e),Me(e),r&512&&n!==null&&Kt(n,n.return);break;case 5:if(ze(t,e),Me(e),r&512&&n!==null&&Kt(n,n.return),e.flags&32){var a=e.stateNode;try{On(a,"")}catch(b){W(e,e.return,b)}}if(r&4&&(a=e.stateNode,a!=null)){var i=e.memoizedProps,o=n!==null?n.memoizedProps:i,l=e.type,s=e.updateQueue;if(e.updateQueue=null,s!==null)try{l==="input"&&i.type==="radio"&&i.name!=null&&Gs(a,i),zi(l,o);var c=zi(l,i);for(o=0;o<s.length;o+=2){var f=s[o],g=s[o+1];f==="style"?Zs(a,g):f==="dangerouslySetInnerHTML"?Xs(a,g):f==="children"?On(a,g):so(a,f,g,c)}switch(l){case"input":bi(a,i);break;case"textarea":Ks(a,i);break;case"select":var p=a._wrapperState.wasMultiple;a._wrapperState.wasMultiple=!!i.multiple;var w=i.value;w!=null?Xt(a,!!i.multiple,w,!1):p!==!!i.multiple&&(i.defaultValue!=null?Xt(a,!!i.multiple,i.defaultValue,!0):Xt(a,!!i.multiple,i.multiple?[]:"",!1))}a[Kn]=i}catch(b){W(e,e.return,b)}}break;case 6:if(ze(t,e),Me(e),r&4){if(e.stateNode===null)throw Error(v(162));a=e.stateNode,i=e.memoizedProps;try{a.nodeValue=i}catch(b){W(e,e.return,b)}}break;case 3:if(ze(t,e),Me(e),r&4&&n!==null&&n.memoizedState.isDehydrated)try{Un(t.containerInfo)}catch(b){W(e,e.return,b)}break;case 4:ze(t,e),Me(e);break;case 13:ze(t,e),Me(e),a=e.child,a.flags&8192&&(i=a.memoizedState!==null,a.stateNode.isHidden=i,!i||a.alternate!==null&&a.alternate.memoizedState!==null||(Bo=I())),r&4&&Ms(e);break;case 22:if(f=n!==null&&n.memoizedState!==null,e.mode&1?(J=(c=J)||f,ze(t,e),J=c):ze(t,e),Me(e),r&8192){if(c=e.memoizedState!==null,(e.stateNode.isHidden=c)&&!f&&(e.mode&1)!==0)for(x=e,f=e.child;f!==null;){for(g=x=f;x!==null;){switch(p=x,w=p.child,p.tag){case 0:case 11:case 14:case 15:Hn(4,p,p.return);break;case 1:Kt(p,p.return);var y=p.stateNode;if(typeof y.componentWillUnmount=="function"){r=p,n=p.return;try{t=r,y.props=t.memoizedProps,y.state=t.memoizedState,y.componentWillUnmount()}catch(b){W(r,n,b)}}break;case 5:Kt(p,p.return);break;case 22:if(p.memoizedState!==null){Hs(g);continue}}w!==null?(w.return=p,x=w):Hs(g)}f=f.sibling}e:for(f=null,g=e;;){if(g.tag===5){if(f===null){f=g;try{a=g.stateNode,c?(i=a.style,typeof i.setProperty=="function"?i.setProperty("display","none","important"):i.display="none"):(l=g.stateNode,s=g.memoizedProps.style,o=s!=null&&s.hasOwnProperty("display")?s.display:null,l.style.display=Qs("display",o))}catch(b){W(e,e.return,b)}}}else if(g.tag===6){if(f===null)try{g.stateNode.nodeValue=c?"":g.memoizedProps}catch(b){W(e,e.return,b)}}else if((g.tag!==22&&g.tag!==23||g.memoizedState===null||g===e)&&g.child!==null){g.child.return=g,g=g.child;continue}if(g===e)break e;for(;g.sibling===null;){if(g.return===null||g.return===e)break e;f===g&&(f=null),g=g.return}f===g&&(f=null),g.sibling.return=g.return,g=g.sibling}}break;case 19:ze(t,e),Me(e),r&4&&Ms(e);break;case 21:break;default:ze(t,e),Me(e)}}function Me(e){var t=e.flags;if(t&2){try{e:{for(var n=e.return;n!==null;){if(Sc(n)){var r=n;break e}n=n.return}throw Error(v(160))}switch(r.tag){case 5:var a=r.stateNode;r.flags&32&&(On(a,""),r.flags&=-33);var i=As(e);to(e,i,a);break;case 3:case 4:var o=r.stateNode.containerInfo,l=As(e);eo(e,l,o);break;default:throw Error(v(161))}}catch(s){W(e,e.return,s)}e.flags&=-3}t&4096&&(e.flags&=-4097)}function _h(e,t,n){x=e,Tc(e,t,n)}function Tc(e,t,n){for(var r=(e.mode&1)!==0;x!==null;){var a=x,i=a.child;if(a.tag===22&&r){var o=a.memoizedState!==null||Lr;if(!o){var l=a.alternate,s=l!==null&&l.memoizedState!==null||J;l=Lr;var c=J;if(Lr=o,(J=s)&&!c)for(x=a;x!==null;)o=x,s=o.child,o.tag===22&&o.memoizedState!==null?Fs(a):s!==null?(s.return=o,x=s):Fs(a);for(;i!==null;)x=i,Tc(i,t,n),i=i.sibling;x=a,Lr=l,J=c}$s(e,t,n)}else(a.subtreeFlags&8772)!==0&&i!==null?(i.return=a,x=i):$s(e,t,n)}}function $s(e){for(;x!==null;){var t=x;if((t.flags&8772)!==0){var n=t.alternate;try{if((t.flags&8772)!==0)switch(t.tag){case 0:case 11:case 15:J||xa(5,t);break;case 1:var r=t.stateNode;if(t.flags&4&&!J)if(n===null)r.componentDidMount();else{var a=t.elementType===t.type?n.memoizedProps:Te(t.type,n.memoizedProps);r.componentDidUpdate(a,n.memoizedState,r.__reactInternalSnapshotBeforeUpdate)}var i=t.updateQueue;i!==null&&ws(t,i,r);break;case 3:var o=t.updateQueue;if(o!==null){if(n=null,t.child!==null)switch(t.child.tag){case 5:n=t.child.stateNode;break;case 1:n=t.child.stateNode}ws(t,o,n)}break;case 5:var l=t.stateNode;if(n===null&&t.flags&4){n=l;var s=t.memoizedProps;switch(t.type){case"button":case"input":case"select":case"textarea":s.autoFocus&&n.focus();break;case"img":s.src&&(n.src=s.src)}}break;case 6:break;case 4:break;case 12:break;case 13:if(t.memoizedState===null){var c=t.alternate;if(c!==null){var f=c.memoizedState;if(f!==null){var g=f.dehydrated;g!==null&&Un(g)}}}break;case 19:case 17:case 21:case 22:case 23:case 25:break;default:throw Error(v(163))}J||t.flags&512&&Ji(t)}catch(p){W(t,t.return,p)}}if(t===e){x=null;break}if(n=t.sibling,n!==null){n.return=t.return,x=n;break}x=t.return}}function Hs(e){for(;x!==null;){var t=x;if(t===e){x=null;break}var n=t.sibling;if(n!==null){n.return=t.return,x=n;break}x=t.return}}function Fs(e){for(;x!==null;){var t=x;try{switch(t.tag){case 0:case 11:case 15:var n=t.return;try{xa(4,t)}catch(s){W(t,n,s)}break;case 1:var r=t.stateNode;if(typeof r.componentDidMount=="function"){var a=t.return;try{r.componentDidMount()}catch(s){W(t,a,s)}}var i=t.return;try{Ji(t)}catch(s){W(t,i,s)}break;case 5:var o=t.return;try{Ji(t)}catch(s){W(t,o,s)}}}catch(s){W(t,t.return,s)}if(t===e){x=null;break}var l=t.sibling;if(l!==null){l.return=t.return,x=l;break}x=t.return}}var Ch=Math.ceil,sa=Ye.ReactCurrentDispatcher,Wo=Ye.ReactCurrentOwner,xe=Ye.ReactCurrentBatchConfig,R=0,j=null,B=null,K=0,de=0,Yt=mt(0),V=0,er=null,Pt=0,ka=0,Io=0,Fn=null,ie=null,Bo=0,un=1/0,We=null,ua=!1,no=null,ct=null,Ar=!1,at=null,ca=0,Nn=0,ro=null,Wr=-1,Ir=0;function re(){return(R&6)!==0?I():Wr!==-1?Wr:Wr=I()}function dt(e){return(e.mode&1)===0?1:(R&2)!==0&&K!==0?K&-K:hh.transition!==null?(Ir===0&&(Ir=cu()),Ir):(e=C,e!==0||(e=window.event,e=e===void 0?16:vu(e.type)),e)}function Pe(e,t,n,r){if(50<Nn)throw Nn=0,ro=null,Error(v(185));tr(e,n,r),((R&2)===0||e!==j)&&(e===j&&((R&2)===0&&(ka|=n),V===4&&nt(e,K)),ue(e,r),n===1&&R===0&&(t.mode&1)===0&&(un=I()+500,wa&&vt()))}function ue(e,t){var n=e.callbackNode;f0(e,t);var r=Gr(e,e===j?K:0);if(r===0)n!==null&&Vl(n),e.callbackNode=null,e.callbackPriority=0;else if(t=r&-r,e.callbackPriority!==t){if(n!=null&&Vl(n),t===1)e.tag===0?dh(Ns.bind(null,e)):Fu(Ns.bind(null,e)),lh(function(){(R&6)===0&&vt()}),n=null;else{switch(du(r)){case 1:n=fo;break;case 4:n=su;break;case 16:n=jr;break;case 536870912:n=uu;break;default:n=jr}n=$c(n,Rc.bind(null,e))}e.callbackPriority=t,e.callbackNode=n}}function Rc(e,t){if(Wr=-1,Ir=0,(R&6)!==0)throw Error(v(327));var n=e.callbackNode;if(tn()&&e.callbackNode!==n)return null;var r=Gr(e,e===j?K:0);if(r===0)return null;if((r&30)!==0||(r&e.expiredLanes)!==0||t)t=da(e,r);else{t=r;var a=R;R|=2;var i=Cc();(j!==e||K!==t)&&(We=null,un=I()+500,zt(e,t));do try{Ah();break}catch(l){_c(e,l)}while(!0);Ro(),sa.current=i,R=a,B!==null?t=0:(j=null,K=0,t=V)}if(t!==0){if(t===2&&(a=Pi(e),a!==0&&(r=a,t=ao(e,a))),t===1)throw n=er,zt(e,0),nt(e,r),ue(e,I()),n;if(t===6)nt(e,r);else{if(a=e.current.alternate,(r&30)===0&&!Ph(a)&&(t=da(e,r),t===2&&(i=Pi(e),i!==0&&(r=i,t=ao(e,i))),t===1))throw n=er,zt(e,0),nt(e,r),ue(e,I()),n;switch(e.finishedWork=a,e.finishedLanes=r,t){case 0:case 1:throw Error(v(345));case 2:xt(e,ie,We);break;case 3:if(nt(e,r),(r&130023424)===r&&(t=Bo+500-I(),10<t)){if(Gr(e,0)!==0)break;if(a=e.suspendedLanes,(a&r)!==r){re(),e.pingedLanes|=e.suspendedLanes&a;break}e.timeoutHandle=Di(xt.bind(null,e,ie,We),t);break}xt(e,ie,We);break;case 4:if(nt(e,r),(r&4194240)===r)break;for(t=e.eventTimes,a=-1;0<r;){var o=31-Ce(r);i=1<<o,o=t[o],o>a&&(a=o),r&=~i}if(r=a,r=I()-r,r=(120>r?120:480>r?480:1080>r?1080:1920>r?1920:3e3>r?3e3:4320>r?4320:1960*Ch(r/1960))-r,10<r){e.timeoutHandle=Di(xt.bind(null,e,ie,We),r);break}xt(e,ie,We);break;case 5:xt(e,ie,We);break;default:throw Error(v(329))}}}return ue(e,I()),e.callbackNode===n?Rc.bind(null,e):null}function ao(e,t){var n=Fn;return e.current.memoizedState.isDehydrated&&(zt(e,t).flags|=256),e=da(e,t),e!==2&&(t=ie,ie=n,t!==null&&io(t)),e}function io(e){ie===null?ie=e:ie.push.apply(ie,e)}function Ph(e){for(var t=e;;){if(t.flags&16384){var n=t.updateQueue;if(n!==null&&(n=n.stores,n!==null))for(var r=0;r<n.length;r++){var a=n[r],i=a.getSnapshot;a=a.value;try{if(!Le(i(),a))return!1}catch{return!1}}}if(n=t.child,t.subtreeFlags&16384&&n!==null)n.return=t,t=n;else{if(t===e)break;for(;t.sibling===null;){if(t.return===null||t.return===e)return!0;t=t.return}t.sibling.return=t.return,t=t.sibling}}return!0}function nt(e,t){for(t&=~Io,t&=~ka,e.suspendedLanes|=t,e.pingedLanes&=~t,e=e.expirationTimes;0<t;){var n=31-Ce(t),r=1<<n;e[n]=-1,t&=~r}}function Ns(e){if((R&6)!==0)throw Error(v(327));tn();var t=Gr(e,0);if((t&1)===0)return ue(e,I()),null;var n=da(e,t);if(e.tag!==0&&n===2){var r=Pi(e);r!==0&&(t=r,n=ao(e,r))}if(n===1)throw n=er,zt(e,0),nt(e,t),ue(e,I()),n;if(n===6)throw Error(v(345));return e.finishedWork=e.current.alternate,e.finishedLanes=t,xt(e,ie,We),ue(e,I()),null}function Uo(e,t){var n=R;R|=1;try{return e(t)}finally{R=n,R===0&&(un=I()+500,wa&&vt())}}function Lt(e){at!==null&&at.tag===0&&(R&6)===0&&tn();var t=R;R|=1;var n=xe.transition,r=C;try{if(xe.transition=null,C=1,e)return e()}finally{C=r,xe.transition=n,R=t,(R&6)===0&&vt()}}function Vo(){de=Yt.current,M(Yt)}function zt(e,t){e.finishedWork=null,e.finishedLanes=0;var n=e.timeoutHandle;if(n!==-1&&(e.timeoutHandle=-1,oh(n)),B!==null)for(n=B.return;n!==null;){var r=n;switch(Eo(r),r.tag){case 1:r=r.type.childContextTypes,r!=null&&Zr();break;case 3:ln(),M(le),M(ee),Mo();break;case 5:Ao(r);break;case 4:ln();break;case 13:M(N);break;case 19:M(N);break;case 10:_o(r.type._context);break;case 22:case 23:Vo()}n=n.return}if(j=e,B=e=ht(e.current,null),K=de=t,V=0,er=null,Io=ka=Pt=0,ie=Fn=null,St!==null){for(t=0;t<St.length;t++)if(n=St[t],r=n.interleaved,r!==null){n.interleaved=null;var a=r.next,i=n.pending;if(i!==null){var o=i.next;i.next=a,r.next=o}n.pending=r}St=null}return e}function _c(e,t){do{var n=B;try{if(Ro(),Nr.current=la,oa){for(var r=D.memoizedState;r!==null;){var a=r.queue;a!==null&&(a.pending=null),r=r.next}oa=!1}if(Ct=0,q=U=D=null,$n=!1,Qn=0,Wo.current=null,n===null||n.return===null){V=1,er=t,B=null;break}e:{var i=e,o=n.return,l=n,s=t;if(t=K,l.flags|=32768,s!==null&&typeof s=="object"&&typeof s.then=="function"){var c=s,f=l,g=f.tag;if((f.mode&1)===0&&(g===0||g===11||g===15)){var p=f.alternate;p?(f.updateQueue=p.updateQueue,f.memoizedState=p.memoizedState,f.lanes=p.lanes):(f.updateQueue=null,f.memoizedState=null)}var w=Es(o);if(w!==null){w.flags&=-257,zs(w,o,l,i,t),w.mode&1&&Ss(i,c,t),t=w,s=c;var y=t.updateQueue;if(y===null){var b=new Set;b.add(s),t.updateQueue=b}else y.add(s);break e}else{if((t&1)===0){Ss(i,c,t),qo();break e}s=Error(v(426))}}else if($&&l.mode&1){var H=Es(o);if(H!==null){(H.flags&65536)===0&&(H.flags|=256),zs(H,o,l,i,t),zo(sn(s,l));break e}}i=s=sn(s,l),V!==4&&(V=2),Fn===null?Fn=[i]:Fn.push(i),i=o;do{switch(i.tag){case 3:i.flags|=65536,t&=-t,i.lanes|=t;var h=dc(i,s,t);vs(i,h);break e;case 1:l=s;var u=i.type,d=i.stateNode;if((i.flags&128)===0&&(typeof u.getDerivedStateFromError=="function"||d!==null&&typeof d.componentDidCatch=="function"&&(ct===null||!ct.has(d)))){i.flags|=65536,t&=-t,i.lanes|=t;var m=hc(i,l,t);vs(i,m);break e}}i=i.return}while(i!==null)}Lc(n)}catch(k){t=k,B===n&&n!==null&&(B=n=n.return);continue}break}while(!0)}function Cc(){var e=sa.current;return sa.current=la,e===null?la:e}function qo(){(V===0||V===3||V===2)&&(V=4),j===null||(Pt&268435455)===0&&(ka&268435455)===0||nt(j,K)}function da(e,t){var n=R;R|=2;var r=Cc();(j!==e||K!==t)&&(We=null,zt(e,t));do try{Lh();break}catch(a){_c(e,a)}while(!0);if(Ro(),R=n,sa.current=r,B!==null)throw Error(v(261));return j=null,K=0,V}function Lh(){for(;B!==null;)Pc(B)}function Ah(){for(;B!==null&&!i0();)Pc(B)}function Pc(e){var t=Mc(e.alternate,e,de);e.memoizedProps=e.pendingProps,t===null?Lc(e):B=t,Wo.current=null}function Lc(e){var t=e;do{var n=t.alternate;if(e=t.return,(t.flags&32768)===0){if(n=Eh(n,t,de),n!==null){B=n;return}}else{if(n=zh(n,t),n!==null){n.flags&=32767,B=n;return}if(e!==null)e.flags|=32768,e.subtreeFlags=0,e.deletions=null;else{V=6,B=null;return}}if(t=t.sibling,t!==null){B=t;return}B=t=e}while(t!==null);V===0&&(V=5)}function xt(e,t,n){var r=C,a=xe.transition;try{xe.transition=null,C=1,Mh(e,t,n,r)}finally{xe.transition=a,C=r}return null}function Mh(e,t,n,r){do tn();while(at!==null);if((R&6)!==0)throw Error(v(327));n=e.finishedWork;var a=e.finishedLanes;if(n===null)return null;if(e.finishedWork=null,e.finishedLanes=0,n===e.current)throw Error(v(177));e.callbackNode=null,e.callbackPriority=0;var i=n.lanes|n.childLanes;if(g0(e,i),e===j&&(B=j=null,K=0),(n.subtreeFlags&2064)===0&&(n.flags&2064)===0||Ar||(Ar=!0,$c(jr,function(){return tn(),null})),i=(n.flags&15990)!==0,(n.subtreeFlags&15990)!==0||i){i=xe.transition,xe.transition=null;var o=C;C=1;var l=R;R|=4,Wo.current=null,Rh(e,n),zc(n,e),th(Fi),Kr=!!Hi,Fi=Hi=null,e.current=n,_h(n,e,a),o0(),R=l,C=o,xe.transition=i}else e.current=n;if(Ar&&(Ar=!1,at=e,ca=a),i=e.pendingLanes,i===0&&(ct=null),u0(n.stateNode,r),ue(e,I()),t!==null)for(r=e.onRecoverableError,n=0;n<t.length;n++)a=t[n],r(a.value,{componentStack:a.stack,digest:a.digest});if(ua)throw ua=!1,e=no,no=null,e;return(ca&1)!==0&&e.tag!==0&&tn(),i=e.pendingLanes,(i&1)!==0?e===ro?Nn++:(Nn=0,ro=e):Nn=0,vt(),null}function tn(){if(at!==null){var e=du(ca),t=xe.transition,n=C;try{if(xe.transition=null,C=16>e?16:e,at===null)var r=!1;else{if(e=at,at=null,ca=0,(R&6)!==0)throw Error(v(331));var a=R;for(R|=4,x=e.current;x!==null;){var i=x,o=i.child;if((x.flags&16)!==0){var l=i.deletions;if(l!==null){for(var s=0;s<l.length;s++){var c=l[s];for(x=c;x!==null;){var f=x;switch(f.tag){case 0:case 11:case 15:Hn(8,f,i)}var g=f.child;if(g!==null)g.return=f,x=g;else for(;x!==null;){f=x;var p=f.sibling,w=f.return;if(kc(f),f===c){x=null;break}if(p!==null){p.return=w,x=p;break}x=w}}}var y=i.alternate;if(y!==null){var b=y.child;if(b!==null){y.child=null;do{var H=b.sibling;b.sibling=null,b=H}while(b!==null)}}x=i}}if((i.subtreeFlags&2064)!==0&&o!==null)o.return=i,x=o;else e:for(;x!==null;){if(i=x,(i.flags&2048)!==0)switch(i.tag){case 0:case 11:case 15:Hn(9,i,i.return)}var h=i.sibling;if(h!==null){h.return=i.return,x=h;break e}x=i.return}}var u=e.current;for(x=u;x!==null;){o=x;var d=o.child;if((o.subtreeFlags&2064)!==0&&d!==null)d.return=o,x=d;else e:for(o=u;x!==null;){if(l=x,(l.flags&2048)!==0)try{switch(l.tag){case 0:case 11:case 15:xa(9,l)}}catch(k){W(l,l.return,k)}if(l===o){x=null;break e}var m=l.sibling;if(m!==null){m.return=l.return,x=m;break e}x=l.return}}if(R=a,vt(),Fe&&typeof Fe.onPostCommitFiberRoot=="function")try{Fe.onPostCommitFiberRoot(pa,e)}catch{}r=!0}return r}finally{C=n,xe.transition=t}}return!1}function Ds(e,t,n){t=sn(n,t),t=dc(e,t,1),e=ut(e,t,1),t=re(),e!==null&&(tr(e,1,t),ue(e,t))}function W(e,t,n){if(e.tag===3)Ds(e,e,n);else for(;t!==null;){if(t.tag===3){Ds(t,e,n);break}else if(t.tag===1){var r=t.stateNode;if(typeof t.type.getDerivedStateFromError=="function"||typeof r.componentDidCatch=="function"&&(ct===null||!ct.has(r))){e=sn(n,e),e=hc(t,e,1),t=ut(t,e,1),e=re(),t!==null&&(tr(t,1,e),ue(t,e));break}}t=t.return}}function $h(e,t,n){var r=e.pingCache;r!==null&&r.delete(t),t=re(),e.pingedLanes|=e.suspendedLanes&n,j===e&&(K&n)===n&&(V===4||V===3&&(K&130023424)===K&&500>I()-Bo?zt(e,0):Io|=n),ue(e,t)}function Ac(e,t){t===0&&((e.mode&1)===0?t=1:(t=wr,wr<<=1,(wr&130023424)===0&&(wr=4194304)));var n=re();e=Ge(e,t),e!==null&&(tr(e,t,n),ue(e,n))}function Hh(e){var t=e.memoizedState,n=0;t!==null&&(n=t.retryLane),Ac(e,n)}function Fh(e,t){var n=0;switch(e.tag){case 13:var r=e.stateNode,a=e.memoizedState;a!==null&&(n=a.retryLane);break;case 19:r=e.stateNode;break;default:throw Error(v(314))}r!==null&&r.delete(t),Ac(e,n)}var Mc;Mc=function(e,t,n){if(e!==null)if(e.memoizedProps!==t.pendingProps||le.current)oe=!0;else{if((e.lanes&n)===0&&(t.flags&128)===0)return oe=!1,Sh(e,t,n);oe=(e.flags&131072)!==0}else oe=!1,$&&(t.flags&1048576)!==0&&Nu(t,ta,t.index);switch(t.lanes=0,t.tag){case 2:var r=t.type;Or(e,t),e=t.pendingProps;var a=rn(t,ee.current);en(t,n),a=Ho(null,t,r,e,a,n);var i=Fo();return t.flags|=1,typeof a=="object"&&a!==null&&typeof a.render=="function"&&a.$$typeof===void 0?(t.tag=1,t.memoizedState=null,t.updateQueue=null,se(r)?(i=!0,Jr(t)):i=!1,t.memoizedState=a.state!==null&&a.state!==void 0?a.state:null,Po(t),a.updater=ba,t.stateNode=a,a._reactInternals=t,qi(t,r,e,n),t=Ki(null,t,r,!0,i,n)):(t.tag=0,$&&i&&So(t),ne(null,t,a,n),t=t.child),t;case 16:r=t.elementType;e:{switch(Or(e,t),e=t.pendingProps,a=r._init,r=a(r._payload),t.type=r,a=t.tag=Dh(r),e=Te(r,e),a){case 0:t=Gi(null,t,r,e,n);break e;case 1:t=_s(null,t,r,e,n);break e;case 11:t=Ts(null,t,r,e,n);break e;case 14:t=Rs(null,t,r,Te(r.type,e),n);break e}throw Error(v(306,r,""))}return t;case 0:return r=t.type,a=t.pendingProps,a=t.elementType===r?a:Te(r,a),Gi(e,t,r,a,n);case 1:return r=t.type,a=t.pendingProps,a=t.elementType===r?a:Te(r,a),_s(e,t,r,a,n);case 3:e:{if(mc(t),e===null)throw Error(v(387));r=t.pendingProps,i=t.memoizedState,a=i.element,Uu(e,t),aa(t,r,null,n);var o=t.memoizedState;if(r=o.element,i.isDehydrated)if(i={element:r,isDehydrated:!1,cache:o.cache,pendingSuspenseBoundaries:o.pendingSuspenseBoundaries,transitions:o.transitions},t.updateQueue.baseState=i,t.memoizedState=i,t.flags&256){a=sn(Error(v(423)),t),t=Cs(e,t,r,n,a);break e}else if(r!==a){a=sn(Error(v(424)),t),t=Cs(e,t,r,n,a);break e}else for(he=st(t.stateNode.containerInfo.firstChild),pe=t,$=!0,_e=null,n=Iu(t,null,r,n),t.child=n;n;)n.flags=n.flags&-3|4096,n=n.sibling;else{if(an(),r===a){t=Ke(e,t,n);break e}ne(e,t,r,n)}t=t.child}return t;case 5:return Vu(t),e===null&&Bi(t),r=t.type,a=t.pendingProps,i=e!==null?e.memoizedProps:null,o=a.children,Ni(r,a)?o=null:i!==null&&Ni(r,i)&&(t.flags|=32),gc(e,t),ne(e,t,o,n),t.child;case 6:return e===null&&Bi(t),null;case 13:return vc(e,t,n);case 4:return Lo(t,t.stateNode.containerInfo),r=t.pendingProps,e===null?t.child=on(t,null,r,n):ne(e,t,r,n),t.child;case 11:return r=t.type,a=t.pendingProps,a=t.elementType===r?a:Te(r,a),Ts(e,t,r,a,n);case 7:return ne(e,t,t.pendingProps,n),t.child;case 8:return ne(e,t,t.pendingProps.children,n),t.child;case 12:return ne(e,t,t.pendingProps.children,n),t.child;case 10:e:{if(r=t.type._context,a=t.pendingProps,i=t.memoizedProps,o=a.value,L(na,r._currentValue),r._currentValue=o,i!==null)if(Le(i.value,o)){if(i.children===a.children&&!le.current){t=Ke(e,t,n);break e}}else for(i=t.child,i!==null&&(i.return=t);i!==null;){var l=i.dependencies;if(l!==null){o=i.child;for(var s=l.firstContext;s!==null;){if(s.context===r){if(i.tag===1){s=Ve(-1,n&-n),s.tag=2;var c=i.updateQueue;if(c!==null){c=c.shared;var f=c.pending;f===null?s.next=s:(s.next=f.next,f.next=s),c.pending=s}}i.lanes|=n,s=i.alternate,s!==null&&(s.lanes|=n),Ui(i.return,n,t),l.lanes|=n;break}s=s.next}}else if(i.tag===10)o=i.type===t.type?null:i.child;else if(i.tag===18){if(o=i.return,o===null)throw Error(v(341));o.lanes|=n,l=o.alternate,l!==null&&(l.lanes|=n),Ui(o,n,t),o=i.sibling}else o=i.child;if(o!==null)o.return=i;else for(o=i;o!==null;){if(o===t){o=null;break}if(i=o.sibling,i!==null){i.return=o.return,o=i;break}o=o.return}i=o}ne(e,t,a.children,n),t=t.child}return t;case 9:return a=t.type,r=t.pendingProps.children,en(t,n),a=ke(a),r=r(a),t.flags|=1,ne(e,t,r,n),t.child;case 14:return r=t.type,a=Te(r,t.pendingProps),a=Te(r.type,a),Rs(e,t,r,a,n);case 15:return pc(e,t,t.type,t.pendingProps,n);case 17:return r=t.type,a=t.pendingProps,a=t.elementType===r?a:Te(r,a),Or(e,t),t.tag=1,se(r)?(e=!0,Jr(t)):e=!1,en(t,n),cc(t,r,a),qi(t,r,a,n),Ki(null,t,r,!0,e,n);case 19:return wc(e,t,n);case 22:return fc(e,t,n)}throw Error(v(156,t.tag))};function $c(e,t){return lu(e,t)}function Nh(e,t,n,r){this.tag=e,this.key=n,this.sibling=this.child=this.return=this.stateNode=this.type=this.elementType=null,this.index=0,this.ref=null,this.pendingProps=t,this.dependencies=this.memoizedState=this.updateQueue=this.memoizedProps=null,this.mode=r,this.subtreeFlags=this.flags=0,this.deletions=null,this.childLanes=this.lanes=0,this.alternate=null}function be(e,t,n,r){return new Nh(e,t,n,r)}function jo(e){return e=e.prototype,!(!e||!e.isReactComponent)}function Dh(e){if(typeof e=="function")return jo(e)?1:0;if(e!=null){if(e=e.$$typeof,e===co)return 11;if(e===ho)return 14}return 2}function ht(e,t){var n=e.alternate;return n===null?(n=be(e.tag,t,e.key,e.mode),n.elementType=e.elementType,n.type=e.type,n.stateNode=e.stateNode,n.alternate=e,e.alternate=n):(n.pendingProps=t,n.type=e.type,n.flags=0,n.subtreeFlags=0,n.deletions=null),n.flags=e.flags&14680064,n.childLanes=e.childLanes,n.lanes=e.lanes,n.child=e.child,n.memoizedProps=e.memoizedProps,n.memoizedState=e.memoizedState,n.updateQueue=e.updateQueue,t=e.dependencies,n.dependencies=t===null?null:{lanes:t.lanes,firstContext:t.firstContext},n.sibling=e.sibling,n.index=e.index,n.ref=e.ref,n}function Br(e,t,n,r,a,i){var o=2;if(r=e,typeof e=="function")jo(e)&&(o=1);else if(typeof e=="string")o=5;else e:switch(e){case Ot:return Tt(n.children,a,i,t);case uo:o=8,a|=8;break;case gi:return e=be(12,n,t,a|2),e.elementType=gi,e.lanes=i,e;case mi:return e=be(13,n,t,a),e.elementType=mi,e.lanes=i,e;case vi:return e=be(19,n,t,a),e.elementType=vi,e.lanes=i,e;case Vs:return Sa(n,a,i,t);default:if(typeof e=="object"&&e!==null)switch(e.$$typeof){case Bs:o=10;break e;case Us:o=9;break e;case co:o=11;break e;case ho:o=14;break e;case Je:o=16,r=null;break e}throw Error(v(130,e==null?e:typeof e,""))}return t=be(o,n,t,a),t.elementType=e,t.type=r,t.lanes=i,t}function Tt(e,t,n,r){return e=be(7,e,r,t),e.lanes=n,e}function Sa(e,t,n,r){return e=be(22,e,r,t),e.elementType=Vs,e.lanes=n,e.stateNode={isHidden:!1},e}function hi(e,t,n){return e=be(6,e,null,t),e.lanes=n,e}function pi(e,t,n){return t=be(4,e.children!==null?e.children:[],e.key,t),t.lanes=n,t.stateNode={containerInfo:e.containerInfo,pendingChildren:null,implementation:e.implementation},t}function Oh(e,t,n,r,a){this.tag=t,this.containerInfo=e,this.finishedWork=this.pingCache=this.current=this.pendingChildren=null,this.timeoutHandle=-1,this.callbackNode=this.pendingContext=this.context=null,this.callbackPriority=0,this.eventTimes=Xa(0),this.expirationTimes=Xa(-1),this.entangledLanes=this.finishedLanes=this.mutableReadLanes=this.expiredLanes=this.pingedLanes=this.suspendedLanes=this.pendingLanes=0,this.entanglements=Xa(0),this.identifierPrefix=r,this.onRecoverableError=a,this.mutableSourceEagerHydrationData=null}function Go(e,t,n,r,a,i,o,l,s){return e=new Oh(e,t,n,l,s),t===1?(t=1,i===!0&&(t|=8)):t=0,i=be(3,null,null,t),e.current=i,i.stateNode=e,i.memoizedState={element:r,isDehydrated:n,cache:null,transitions:null,pendingSuspenseBoundaries:null},Po(i),e}function Wh(e,t,n){var r=3<arguments.length&&arguments[3]!==void 0?arguments[3]:null;return{$$typeof:Dt,key:r==null?null:""+r,children:e,containerInfo:t,implementation:n}}function Hc(e){if(!e)return ft;e=e._reactInternals;e:{if(Mt(e)!==e||e.tag!==1)throw Error(v(170));var t=e;do{switch(t.tag){case 3:t=t.stateNode.context;break e;case 1:if(se(t.type)){t=t.stateNode.__reactInternalMemoizedMergedChildContext;break e}}t=t.return}while(t!==null);throw Error(v(171))}if(e.tag===1){var n=e.type;if(se(n))return Hu(e,n,t)}return t}function Fc(e,t,n,r,a,i,o,l,s){return e=Go(n,r,!0,e,a,i,o,l,s),e.context=Hc(null),n=e.current,r=re(),a=dt(n),i=Ve(r,a),i.callback=t??null,ut(n,i,a),e.current.lanes=a,tr(e,a,r),ue(e,r),e}function Ea(e,t,n,r){var a=t.current,i=re(),o=dt(a);return n=Hc(n),t.context===null?t.context=n:t.pendingContext=n,t=Ve(i,o),t.payload={element:e},r=r===void 0?null:r,r!==null&&(t.callback=r),e=ut(a,t,o),e!==null&&(Pe(e,a,o,i),Fr(e,a,o)),o}function ha(e){if(e=e.current,!e.child)return null;switch(e.child.tag){case 5:return e.child.stateNode;default:return e.child.stateNode}}function Os(e,t){if(e=e.memoizedState,e!==null&&e.dehydrated!==null){var n=e.retryLane;e.retryLane=n!==0&&n<t?n:t}}function Ko(e,t){Os(e,t),(e=e.alternate)&&Os(e,t)}function Ih(){return null}var Nc=typeof reportError=="function"?reportError:function(e){console.error(e)};function Yo(e){this._internalRoot=e}za.prototype.render=Yo.prototype.render=function(e){var t=this._internalRoot;if(t===null)throw Error(v(409));Ea(e,t,null,null)};za.prototype.unmount=Yo.prototype.unmount=function(){var e=this._internalRoot;if(e!==null){this._internalRoot=null;var t=e.containerInfo;Lt(function(){Ea(null,e,null,null)}),t[je]=null}};function za(e){this._internalRoot=e}za.prototype.unstable_scheduleHydration=function(e){if(e){var t=fu();e={blockedOn:null,target:e,priority:t};for(var n=0;n<tt.length&&t!==0&&t<tt[n].priority;n++);tt.splice(n,0,e),n===0&&mu(e)}};function Xo(e){return!(!e||e.nodeType!==1&&e.nodeType!==9&&e.nodeType!==11)}function Ta(e){return!(!e||e.nodeType!==1&&e.nodeType!==9&&e.nodeType!==11&&(e.nodeType!==8||e.nodeValue!==" react-mount-point-unstable "))}function Ws(){}function Bh(e,t,n,r,a){if(a){if(typeof r=="function"){var i=r;r=function(){var c=ha(o);i.call(c)}}var o=Fc(t,r,e,0,null,!1,!1,"",Ws);return e._reactRootContainer=o,e[je]=o.current,jn(e.nodeType===8?e.parentNode:e),Lt(),o}for(;a=e.lastChild;)e.removeChild(a);if(typeof r=="function"){var l=r;r=function(){var c=ha(s);l.call(c)}}var s=Go(e,0,!1,null,null,!1,!1,"",Ws);return e._reactRootContainer=s,e[je]=s.current,jn(e.nodeType===8?e.parentNode:e),Lt(function(){Ea(t,s,n,r)}),s}function Ra(e,t,n,r,a){var i=n._reactRootContainer;if(i){var o=i;if(typeof a=="function"){var l=a;a=function(){var s=ha(o);l.call(s)}}Ea(t,o,e,a)}else o=Bh(n,t,e,a,r);return ha(o)}hu=function(e){switch(e.tag){case 3:var t=e.stateNode;if(t.current.memoizedState.isDehydrated){var n=Rn(t.pendingLanes);n!==0&&(go(t,n|1),ue(t,I()),(R&6)===0&&(un=I()+500,vt()))}break;case 13:Lt(function(){var r=Ge(e,1);if(r!==null){var a=re();Pe(r,e,1,a)}}),Ko(e,1)}};mo=function(e){if(e.tag===13){var t=Ge(e,134217728);if(t!==null){var n=re();Pe(t,e,134217728,n)}Ko(e,134217728)}};pu=function(e){if(e.tag===13){var t=dt(e),n=Ge(e,t);if(n!==null){var r=re();Pe(n,e,t,r)}Ko(e,t)}};fu=function(){return C};gu=function(e,t){var n=C;try{return C=e,t()}finally{C=n}};Ri=function(e,t,n){switch(t){case"input":if(bi(e,n),t=n.name,n.type==="radio"&&t!=null){for(n=e;n.parentNode;)n=n.parentNode;for(n=n.querySelectorAll("input[name="+JSON.stringify(""+t)+'][type="radio"]'),t=0;t<n.length;t++){var r=n[t];if(r!==e&&r.form===e.form){var a=va(r);if(!a)throw Error(v(90));js(r),bi(r,a)}}}break;case"textarea":Ks(e,n);break;case"select":t=n.value,t!=null&&Xt(e,!!n.multiple,t,!1)}};tu=Uo;nu=Lt;var Uh={usingClientEntryPoint:!1,Events:[rr,Ut,va,Js,eu,Uo]},Sn={findFiberByHostInstance:kt,bundleType:0,version:"18.3.1",rendererPackageName:"react-dom"},Vh={bundleType:Sn.bundleType,version:Sn.version,rendererPackageName:Sn.rendererPackageName,rendererConfig:Sn.rendererConfig,overrideHookState:null,overrideHookStateDeletePath:null,overrideHookStateRenamePath:null,overrideProps:null,overridePropsDeletePath:null,overridePropsRenamePath:null,setErrorHandler:null,setSuspenseHandler:null,scheduleUpdate:null,currentDispatcherRef:Ye.ReactCurrentDispatcher,findHostInstanceByFiber:function(e){return e=iu(e),e===null?null:e.stateNode},findFiberByHostInstance:Sn.findFiberByHostInstance||Ih,findHostInstancesForRefresh:null,scheduleRefresh:null,scheduleRoot:null,setRefreshHandler:null,getCurrentFiber:null,reconcilerVersion:"18.3.1-next-f1338f8080-20240426"};if(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__<"u"&&(En=__REACT_DEVTOOLS_GLOBAL_HOOK__,!En.isDisabled&&En.supportsFiber))try{pa=En.inject(Vh),Fe=En}catch{}var En;me.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED=Uh;me.createPortal=function(e,t){var n=2<arguments.length&&arguments[2]!==void 0?arguments[2]:null;if(!Xo(t))throw Error(v(200));return Wh(e,t,null,n)};me.createRoot=function(e,t){if(!Xo(e))throw Error(v(299));var n=!1,r="",a=Nc;return t!=null&&(t.unstable_strictMode===!0&&(n=!0),t.identifierPrefix!==void 0&&(r=t.identifierPrefix),t.onRecoverableError!==void 0&&(a=t.onRecoverableError)),t=Go(e,1,!1,null,null,n,!1,r,a),e[je]=t.current,jn(e.nodeType===8?e.parentNode:e),new Yo(t)};me.findDOMNode=function(e){if(e==null)return null;if(e.nodeType===1)return e;var t=e._reactInternals;if(t===void 0)throw typeof e.render=="function"?Error(v(188)):(e=Object.keys(e).join(","),Error(v(268,e)));return e=iu(t),e=e===null?null:e.stateNode,e};me.flushSync=function(e){return Lt(e)};me.hydrate=function(e,t,n){if(!Ta(t))throw Error(v(200));return Ra(null,e,t,!0,n)};me.hydrateRoot=function(e,t,n){if(!Xo(e))throw Error(v(405));var r=n!=null&&n.hydratedSources||null,a=!1,i="",o=Nc;if(n!=null&&(n.unstable_strictMode===!0&&(a=!0),n.identifierPrefix!==void 0&&(i=n.identifierPrefix),n.onRecoverableError!==void 0&&(o=n.onRecoverableError)),t=Fc(t,null,e,1,n??null,a,!1,i,o),e[je]=t.current,jn(e),r)for(e=0;e<r.length;e++)n=r[e],a=n._getVersion,a=a(n._source),t.mutableSourceEagerHydrationData==null?t.mutableSourceEagerHydrationData=[n,a]:t.mutableSourceEagerHydrationData.push(n,a);return new za(t)};me.render=function(e,t,n){if(!Ta(t))throw Error(v(200));return Ra(null,e,t,!1,n)};me.unmountComponentAtNode=function(e){if(!Ta(e))throw Error(v(40));return e._reactRootContainer?(Lt(function(){Ra(null,null,e,!1,function(){e._reactRootContainer=null,e[je]=null})}),!0):!1};me.unstable_batchedUpdates=Uo;me.unstable_renderSubtreeIntoContainer=function(e,t,n,r){if(!Ta(n))throw Error(v(200));if(e==null||e._reactInternals===void 0)throw Error(v(38));return Ra(e,t,n,!1,r)};me.version="18.3.1-next-f1338f8080-20240426"});var Ic=De((Ep,Wc)=>{"use strict";function Oc(){if(!(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__>"u"||typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE!="function"))try{__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(Oc)}catch(e){console.error(e)}}Oc(),Wc.exports=Dc()});var Uc=De(Qo=>{"use strict";var Bc=Ic();Qo.createRoot=Bc.createRoot,Qo.hydrateRoot=Bc.hydrateRoot;var zp});var Jc=De(Ca=>{"use strict";var Kh=Oe(),Yh=Symbol.for("react.element"),Xh=Symbol.for("react.fragment"),Qh=Object.prototype.hasOwnProperty,Zh=Kh.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,Jh={key:!0,ref:!0,__self:!0,__source:!0};function Zc(e,t,n){var r,a={},i=null,o=null;n!==void 0&&(i=""+n),t.key!==void 0&&(i=""+t.key),t.ref!==void 0&&(o=t.ref);for(r in t)Qh.call(t,r)&&!Jh.hasOwnProperty(r)&&(a[r]=t[r]);if(e&&e.defaultProps)for(r in t=e.defaultProps,t)a[r]===void 0&&(a[r]=t[r]);return{$$typeof:Yh,type:e,key:i,ref:o,props:a,_owner:Zh.current}}Ca.Fragment=Xh;Ca.jsx=Zc;Ca.jsxs=Zc});var $t=De((Pp,ed)=>{"use strict";ed.exports=Jc()});var bd=ce(Uc(),1);var fd=ce(Oe());var Kc=ce(Oe(),1),tl={value:"instrument-serif",label:"Instrument Serif",stack:'"Instrument Serif", Georgia, serif',google:"Instrument+Serif"},nl={value:"newsreader",label:"Newsreader",stack:'"Newsreader", Georgia, serif',google:"Newsreader:wght@200..700"},rl={value:"geist",label:"Geist",stack:'"Geist", system-ui, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif',google:"Geist:wght@100..900"},Jo=e=>Math.min(1,Math.max(0,e));function Vc(e,t){if(typeof e!="string")return t;let n=e.trim().match(/^#([\da-f]{3}|[\da-f]{6})$/i);if(!n)return t;let r=n[1].toLowerCase();return`#${r.length===3?r.replace(/./g,a=>a+a):r}`}function el(e){let[t,n,r]=[1,3,5].map(f=>Number.parseInt(e.slice(f,f+2),16)/255),a=Math.max(t,n,r),i=Math.min(t,n,r),o=(a+i)/2,l=a-i;if(l===0)return{h:0,s:0,l:o};let s=l/(1-Math.abs(2*o-1));return{h:((a===t?(n-r)/l%6:a===n?(r-t)/l+2:(t-n)/l+4)*60+360)%360,s,l:o}}function qh({h:e,s:t,l:n}){let r=(1-Math.abs(2*n-1))*t,a=r*(1-Math.abs(e/60%2-1)),i=n-r/2,[o,l,s]=e<60?[r,a,0]:e<120?[a,r,0]:e<180?[0,r,a]:e<240?[0,a,r]:e<300?[a,0,r]:[r,0,a];return[o+i,l+i,s+i].map(c=>Math.round(Jo(c)*255))}function jh(e){return`#${qh(e).map(t=>t.toString(16).padStart(2,"0")).join("")}`}function qc(e,t){let n=el(e),r=el(t);return{hue:r.h-n.h,saturation:n.s>.01?Math.min(3,r.s/n.s):1,lightness:n.l>.01?Math.min(3,r.l/n.l):1}}function jc(e,t){return t.find(n=>n.value===e)??t[0]}function Gc(e,t,n){return t.includes(e)?e:n}function Zo(e,[t,n,r]){return Number.isFinite(e)?Math.min(r,Math.max(t,e)):n}function Gh(e){let t=[...new Set(e.map(n=>n.google).filter(n=>!!n))];if(t.length)return`https://fonts.googleapis.com/css2?${t.map(n=>`family=${n}`).join("&")}&display=swap`}function Yc(e){let{headingFont:t,bodyFont:n,headingWeight:r,bodyWeight:a,primaryColor:i,headingSize:o,bodySize:l,headingLetterSpacing:s,...c}=e;return[{headingFont:t,bodyFont:n,headingWeight:r,bodyWeight:a,primaryColor:i,headingSize:o,bodySize:l,headingLetterSpacing:s},c]}function Xc(e,t){let{headingFont:n,bodyFont:r,headingWeight:a,bodyWeight:i,primaryColor:o,headingSize:l,bodySize:s,headingLetterSpacing:c}=t;return(0,Kc.useMemo)(()=>{let f=jc(n,e.headingFonts),g=jc(r,e.bodyFonts),p=Vc(o,e.primaryColor),w=p===e.primaryColor,y=qc(e.primaryColor,p),b=d=>{if(w)return d;let m=el(Vc(d,d));return jh({h:(m.h+y.hue+360)%360,s:Jo(m.s*y.saturation),l:Jo(m.l*y.lightness)})},H=d=>{if(w)return d;let m=d.match(/^rgba?\(\s*([\d.]+)[\s,]+([\d.]+)[\s,]+([\d.]+)\s*(?:[,/]\s*([\d.]+%?)\s*)?\)$/i);if(!m)return d;let k=`#${[m[1],m[2],m[3]].map(F=>Math.round(Number(F)).toString(16).padStart(2,"0")).join("")}`,[S,E,z]=[1,3,5].map(F=>Number.parseInt(b(k).slice(F,F+2),16));return m[4]===void 0?`rgb(${S}, ${E}, ${z})`:`rgba(${S}, ${E}, ${z}, ${m[4]})`},h=(d=e.primaryColor)=>{if(w)return"none";let m=qc(d,b(d));return[`hue-rotate(${m.hue.toFixed(2)}deg)`,`saturate(${Math.max(0,m.saturation).toFixed(3)})`,`brightness(${Math.min(2,Math.max(.2,m.lightness)).toFixed(3)})`].join(" ")},u={heading:f.stack,body:g.stack,headingWeight:Gc(a,e.headingWeights,e.headingWeight),bodyWeight:Gc(i,e.bodyWeights,e.bodyWeight),primary:p,headingSize:Zo(l,e.headingSize),bodySize:Zo(s,e.bodySize),headingLetterSpacing:Zo(c,e.headingLetterSpacing),retone:b,retoneRgba:H,filter:h};return{css:e.css(u),fontHref:Gh([f,g]),inlineStyles:e.inlineStyles?.(u)}},[e,n,r,a,i,o,l,s,c])}var ir="threeui-page-typography",_a="threeui-page-typography-fonts",Qc="threeui-page-customization",Rp=`<script>
window.addEventListener("message", function (event) {
  var detail = event.data;
  if (!detail || detail.type !== "${Qc}") return;
  var head = document.head;
  if (!head) return;

  var link = document.getElementById("${_a}");
  if (detail.fontHref) {
    if (!link) {
      link = document.createElement("link");
      link.id = "${_a}";
      link.rel = "stylesheet";
      head.appendChild(link);
    }
    if (link.getAttribute("href") !== detail.fontHref) link.href = detail.fontHref;
  } else if (link) {
    link.remove();
  }

  var style = document.getElementById("${ir}");
  if (!detail.css) {
    if (style) style.remove();
    return;
  }
  if (!style) {
    style = document.createElement("style");
    style.id = "${ir}";
  }
  if (style.textContent !== detail.css) style.textContent = detail.css;
  head.appendChild(style);
});
<\/script>`;function al(e,t){e?.contentWindow?.postMessage({type:Qc,css:t?.css??"",fontHref:t?.fontHref},"*")}function il(e,t){let n=e?.contentDocument;if(!n?.head)return;let r=n.getElementById(_a);if(t?.fontHref){let i=r??n.createElement("link");i.id=_a,i.rel="stylesheet",i.getAttribute("href")!==t.fontHref&&(i.href=t.fontHref),r||n.head.append(i)}else r?.remove();if(!t?.css){n.getElementById(ir)?.remove();return}let a=n.getElementById(ir)??n.createElement("style");a.id=ir,a.textContent!==t.css&&(a.textContent=t.css),n.head.append(a);for(let i of t.inlineStyles??[])for(let o of n.querySelectorAll(i.selector))for(let[l,s]of Object.entries(i.styles))o.style.setProperty(l,s)}var hn=ce(Oe(),1);var ol=ce($t(),1),ep="allow-downloads allow-forms allow-modals allow-popups allow-same-origin allow-scripts",tp="allow-downloads allow-forms allow-modals allow-popups allow-scripts",td="threeui-background-presentation";function nd(e,t,n){let r=e?.contentDocument;if(!r)return;if(r.getElementById(td)?.remove(),r.querySelectorAll("[data-threeui-background-layer]").forEach(o=>{o.removeAttribute("data-threeui-background-layer"),o.removeAttribute("data-threeui-background-fill")}),!t){r.documentElement.removeAttribute("data-threeui-presentation");return}let a=r.querySelector(t);if(!a)return;a.setAttribute("data-threeui-background-layer",""),a.setAttribute("data-threeui-background-fill",""),n&&r.querySelectorAll(n).forEach(o=>{o.setAttribute("data-threeui-background-layer","")}),r.documentElement.setAttribute("data-threeui-presentation","background");let i=r.createElement("style");i.id=td,i.textContent=`
    html[data-threeui-presentation="background"],
    html[data-threeui-presentation="background"] body {
      width: 100% !important;
      height: 100% !important;
      min-height: 100% !important;
      overflow: hidden !important;
    }
    html[data-threeui-presentation="background"] body * {
      visibility: hidden !important;
      pointer-events: none !important;
    }
    html[data-threeui-presentation="background"] [data-threeui-background-layer],
    html[data-threeui-presentation="background"] [data-threeui-background-layer] * {
      visibility: visible !important;
    }
    html[data-threeui-presentation="background"] [data-threeui-background-fill] {
      position: fixed !important;
      inset: 0 !important;
      width: 100vw !important;
      height: 100vh !important;
      max-width: none !important;
      max-height: none !important;
      margin: 0 !important;
      transform: none !important;
    }
  `,r.head.appendChild(i),e.contentWindow?.requestAnimationFrame(()=>{e.contentWindow?.dispatchEvent(new Event("resize"))})}function rd({applyScene:e,backgroundCanvasSelector:t,backgroundVisualSelector:n,className:r="",customization:a,sourceUrl:i,srcDoc:o,style:l,title:s}){let[c,f]=(0,hn.useState)(!1),g=(0,hn.useRef)(null);return(0,hn.useEffect)(()=>{il(g.current,a),al(g.current,a),nd(g.current,t,n),g.current&&e?.(g.current)},[e,t,n,a]),(0,ol.jsx)("div",{className:`threeui-background landing-page-frame${r?` ${r}`:""}`,"data-state":c?"ready":"loading",style:{position:"relative",overflow:"hidden",background:"#080808",pointerEvents:"auto",...l},children:(0,ol.jsx)("iframe",{ref:g,title:s,...o?{srcDoc:o}:{src:i},sandbox:o?tp:ep,loading:"eager",onLoad:p=>{il(p.currentTarget,a),al(p.currentTarget,a),nd(p.currentTarget,t,n),e?.(p.currentTarget),f(!0)},style:{position:"absolute",inset:0,display:"block",width:"100%",height:"100%",border:0,background:"#080808",opacity:t&&!c?0:1,pointerEvents:t&&!c?"none":"auto"}})})}var np=e=>Number(e.toFixed(3));var wt=e=>`calc(${np(e)} * var(--u))`;function ad(e,t){let[n,r,a]=[1,3,5].map(i=>Number.parseInt(e.slice(i,i+2),16));return`rgba(${n}, ${r}, ${a}, ${t})`}var id={value:"lexend",label:"Lexend",stack:"'Lexend', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif"};var od={headingFonts:[id,tl,nl,rl],bodyFonts:[id,rl,nl,tl],headingWeights:["200","300","400","500","600"],headingWeight:"300",bodyWeights:["200","300","400","500"],bodyWeight:"300",primaryColor:"#ffffff",headingSize:[40,63,92],bodySize:[12,16.5,24],headingLetterSpacing:[-.06,-.006,.12],css:e=>`
:root {
  --ink: ${e.primary};
  --ink-soft: ${ad(e.primary,.62)};
  --ink-faint: ${ad(e.primary,.44)};
}
body { font-family: ${e.body}; font-weight: ${e.bodyWeight}; }
.headline, .ghost {
  font-family: ${e.heading};
}
.headline {
  font-weight: ${e.headingWeight};
  font-size: ${wt(e.headingSize)};
  line-height: ${wt(e.headingSize*65/63)};
  letter-spacing: ${e.headingLetterSpacing}em;
}
.lede {
  font-weight: ${e.bodyWeight};
  font-size: ${wt(e.bodySize)};
  line-height: ${wt(e.bodySize*22/16.5)};
}
@media (max-width: 900px) {
  .headline {
    font-size: ${wt(e.headingSize*62/63)};
    line-height: ${wt(e.headingSize*66/63)};
  }
  .lede {
    font-size: ${wt(e.bodySize*19/16.5)};
    line-height: ${wt(e.bodySize*27/16.5)};
  }
}
`};var ld=`<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Sylva \u2014 Into the living world</title>
<meta name="description" content="Restoring wild places through patient design, native planting, and a deeper kind of stewardship.">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 22 24'%3E%3Crect width='22' height='24' fill='%234a4d44'/%3E%3Cpath fill='%23fff' d='M11 1.3c-2.1 0-3.95 1.2-4.75 2.95C3.95 4.55 2.3 6.25 2.3 8.35c0 2.3 1.9 4.2 4.3 4.2h8.8c2.4 0 4.3-1.9 4.3-4.2 0-2.1-1.65-3.8-4-4.1C14.95 2.5 13.1 1.3 11 1.3Z'/%3E%3Cpath fill='%23fff' d='M9.6 12.55h2.8v4.2c1.35.3 2.45 1.15 3.15 2.4-1.35.4-2.4.15-3.15-.4v4.15H9.6v-4.15c-.75.55-1.8.8-3.15.4.7-1.25 1.8-2.1 3.15-2.4v-4.2Z'/%3E%3C/svg%3E">
<script>document.documentElement.className += " js";<\/script>
<style>
  @font-face{
    font-family:'Lexend';
    src:url('inner-green-assets/lexend-latin.woff2') format('woff2');
    font-weight:100 900; font-style:normal; font-display:swap;
    unicode-range:U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD;
  }

  /* \u2500\u2500 design unit: 1u === 1px on the 1600 \xD7 880 reference frame \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  :root{
    --u: calc(100vw / 1600);

    --ink:            #ffffff;
    --ink-soft:       rgba(255,255,255,.62);
    --ink-faint:      rgba(255,255,255,.44);
    --rule:           rgba(255,255,255,.055);

    --card:           #f2f3ef;
    --card-ink:       #23261f;
    --card-label:     #7c8177;

    --ease: cubic-bezier(.22,.61,.36,1);
    --ease-out: cubic-bezier(.16,1,.3,1);
  }
  @media (min-width:1900px){ :root{ --u: calc(1900px / 1600); } }

  *,*::before,*::after{ box-sizing:border-box; margin:0; padding:0; }

  html{ background:#383b34; }
  body{
    font-family:'Lexend',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
    font-weight:300;
    color:var(--ink);
    background:#383b34;
    overflow-x:hidden;
    -webkit-font-smoothing:antialiased;
    -moz-osx-font-smoothing:grayscale;
  }

  /* \u2500\u2500 hero shell \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  .hero{
    position:relative;
    width:100%;
    height:100svh;
    min-height:calc(880 * var(--u));
    overflow:hidden;
    isolation:isolate;
    /* the reference screen reads a near-flat #4a4d44 corner to corner \u2014
       all the modelling comes from the light pool the root sits in */
    background:
      radial-gradient(64% 52% at 27% 84%, rgba(232,238,222,.085) 0%, rgba(232,238,222,0) 72%),
      radial-gradient(70% 60% at 92% 8%,  rgba(24,28,20,.10) 0%, rgba(24,28,20,0) 68%),
      #4a4d44;
  }
  /* The floor of light the root stands in. Sampled off the reference: the
     background climbs from 73 luma at the nav to ~128 at y 850, brightest
     around the middle of the bottom edge. */
  .hero::after{
    content:'';
    position:absolute; inset:0;
    background:
      radial-gradient(72% 44% at 50% 117%, rgba(238,243,231,.50) 0%, rgba(238,243,231,.21) 42%, rgba(238,243,231,.04) 72%, rgba(238,243,231,0) 88%),
      linear-gradient(180deg, rgba(238,243,231,0) 54%, rgba(238,243,231,.03) 78%, rgba(238,243,231,.085) 100%);
    pointer-events:none; z-index:0;
  }

  /* The whole composition lives on a centred 1600 \xD7 880 stage.
     Centred with margins rather than a transform on purpose: a transform would
     open a stacking context and trap every child below #scene. */
  .stage{
    position:absolute; left:50%; top:50%;
    margin-left:calc(-800 * var(--u));
    margin-top:calc(-440 * var(--u));
    width:calc(1600 * var(--u));
    height:calc(880 * var(--u));
  }

  /* \u2500\u2500 column guides (z 1) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  .guides{ position:absolute; inset:calc(-40 * var(--u)) 0; z-index:1; pointer-events:none; }
  .guides i{
    position:absolute; top:0; bottom:0; width:1px;
    background:linear-gradient(180deg, rgba(255,255,255,0) 0%, var(--rule) 12%, var(--rule) 78%, rgba(255,255,255,0) 100%);
  }

  /* \u2500\u2500 ghost wordmark (z 1) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  .ghost{
    position:absolute; z-index:1;
    left:calc(6 * var(--u)); bottom:calc(-64 * var(--u));
    font-size:calc(310 * var(--u));
    line-height:.78;
    font-weight:400;
    letter-spacing:calc(30 * var(--u));
    color:rgba(255,255,255,.055);
    white-space:nowrap; user-select:none; pointer-events:none;
  }

  /* \u2500\u2500 three.js canvas (z 3 \u2014 above card 1, below everything else) \u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  #scene{
    position:absolute; inset:0; z-index:3;
    width:100%; height:100%;
    pointer-events:none;
    opacity:0; transition:opacity .7s var(--ease);
  }
  .is-ready #scene{ opacity:1; }

  /* \u2500\u2500 nav: a floating dock (z 5) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
     A centred capsule of pills that magnify as the pointer nears them, over
     a rim highlight that tracks where the pointer is \u2014 the dock idiom from
     ascii-page-transition, in this page's palette and unit system.
     The wrapper does the centring so the capsule itself is free to carry the
     pointer-parallax transform; putting both on one element means whichever
     is written last wins and the dock jumps out of centre. */
  .dock-wrap{
    position:absolute; z-index:5;
    top:calc(38 * var(--u)); left:0; right:0;
    display:flex; justify-content:center;
    pointer-events:none;
  }
  .dock{
    pointer-events:auto;
    display:flex; align-items:flex-start; gap:calc(3 * var(--u));
    height:calc(46 * var(--u));
    padding:calc(5 * var(--u));
    border-radius:calc(14 * var(--u));
    border:1px solid rgba(255,255,255,.11);
    /* No backdrop-filter. It sits over a canvas that repaints every frame,
       so the backdrop has to be re-sampled and re-blurred every frame too \u2014
       measured at ~20 fps off the whole page, and the radius made no
       difference because the cost is the extra pass, not the blur. A
       translucent panel with a lit top edge reads the same at this size. */
    background:
      linear-gradient(180deg, rgba(255,255,255,.055), rgba(255,255,255,0) 42%),
      rgba(34,40,31,.74);
    box-shadow:0 calc(8 * var(--u)) calc(22 * var(--u)) rgba(10,14,8,.30),
               inset 0 1px rgba(255,255,255,.06);
    isolation:isolate;
  }
  /* Anchored at the top so growth runs downward, out of the headline's way \u2014
     a dock that grew from its centre would push into the nav's own row. */
  .dock-item{
    position:relative; z-index:6;
    display:inline-flex; align-items:center; justify-content:center;
    flex:none;
    height:calc(36 * var(--u));
    gap:calc(8 * var(--u));
    padding:0 calc(13 * var(--u));
    transform-origin:50% 0;
    border:1px solid transparent;
    border-radius:calc(10 * var(--u));
    background:rgba(255,255,255,.04);
    color:var(--ink-faint);
    text-decoration:none; cursor:pointer;
    font-family:inherit;
    font-size:calc(11 * var(--u)); font-weight:500;
    letter-spacing:calc(1.5 * var(--u)); text-transform:uppercase;
    white-space:nowrap;
    will-change:width,height,transform;
    transition:color .18s var(--ease), border-color .2s var(--ease), background .2s var(--ease);
  }
  /* A magnified pill hangs below the capsule, so it needs to be its own
     opaque tile \u2014 a translucent white wash at that size reads as a milky
     rectangle stuck to the bar rather than as a key lifting off it. */
  .dock-item[data-near="true"]{
    z-index:7;
    color:var(--ink);
    border-color:rgba(255,255,255,.19);
    background:rgba(31,37,28,.94);
    box-shadow:0 calc(7 * var(--u)) calc(16 * var(--u)) rgba(10,14,8,.30);
  }
  .dock-item .glyph{
    width:calc(14 * var(--u)); height:calc(14 * var(--u)); flex:none;
    opacity:.66; transition:opacity .18s var(--ease);
  }
  .dock-item .glyph svg{
    display:block; width:100%; height:100%;
    fill:none; stroke:currentColor; stroke-width:1.25;
    stroke-linecap:round; stroke-linejoin:round;
  }
  .dock-item[data-near="true"] .glyph{ opacity:1; }

  /* the mark is the dock's anchor: a solid pale tile, the one opaque thing
     in a bar made of glass */
  .dock-mark{
    width:calc(36 * var(--u)); padding:0;
    background:#eef1e7; border-color:#eef1e7; color:#23261f;
    overflow:hidden;
  }
  .dock-mark svg{ width:58%; height:58%; display:block; fill:currentColor; }
  /* the near state paints .dock-item white, which on the pale mark tile
     would be a white glyph on a white ground */
  .dock-mark[data-near="true"]{ background:#fff; border-color:#fff; color:#1b1e18; }

  /* the current section wears the cards' paper, so the nav and the cards
     read as the same material */
  .dock-item.is-active{
    background:var(--card); border-color:var(--card); color:var(--card-ink);
    box-shadow:0 calc(6 * var(--u)) calc(16 * var(--u)) rgba(12,17,9,.24);
  }
  .dock-item.is-active .glyph{ opacity:.8; }
  .dock-item--enter{ color:var(--ink); background:rgba(255,255,255,.075); }

  /* \u2500\u2500 specular rim \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
     A conic gradient masked down to the border, whose start angle points at
     the pointer and whose opacity falls off with distance. It is the reason
     the glass reads as a lit edge rather than as a flat translucent box. */
  [data-spec]{ --spec-angle:2.4rad; --spec-bright:0; }
  [data-spec]::after{
    content:''; position:absolute; inset:-1px; z-index:5;
    padding:1px; border-radius:inherit; pointer-events:none;
    opacity:var(--spec-bright);
    background:conic-gradient(from var(--spec-angle) at 50% 50%,
      rgba(240,246,232,0) 0deg, rgba(240,246,232,.08) 14deg, rgba(240,246,232,.95) 28deg,
      rgba(240,246,232,.16) 46deg, rgba(240,246,232,0) 68deg, rgba(240,246,232,0) 180deg,
      rgba(240,246,232,.08) 194deg, rgba(240,246,232,.95) 208deg, rgba(240,246,232,.16) 226deg,
      rgba(240,246,232,0) 248deg, rgba(240,246,232,0) 360deg);
    -webkit-mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
            mask:linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite:xor; mask-composite:exclude;
  }
  .dock{ position:relative; }

  /* \u2500\u2500 hero copy (z 4) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  .headline{
    position:absolute; z-index:4;
    left:calc(46 * var(--u)); top:calc(202 * var(--u));
    font-size:calc(63 * var(--u)); line-height:calc(65 * var(--u));
    font-weight:300; letter-spacing:calc(-0.4 * var(--u));
    color:var(--ink);
  }
  /* No overflow clip: cropping a 63u face to wipe it in cuts the descenders
     of "Step" and "living" at the moment they land. The padding stays even
     though the clip is gone \u2014 it set the two lines' metrics, and removing it
     would shift line two. */
  .headline span{ display:block; padding-bottom:.04em; }
  .headline span i{ display:inline-block; font-style:normal; }

  .lede{
    position:absolute; z-index:4;
    left:calc(520 * var(--u)); top:calc(196 * var(--u));
    width:calc(208 * var(--u));
    font-size:calc(16.5 * var(--u)); line-height:calc(22 * var(--u));
    font-weight:300; color:var(--ink-soft);
  }

  /* \u2500\u2500 liquid-metal controls \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
     The original five-pass WebGL2 renderer now mounts directly in this
     document. Its canvas, sizing, glass plate, shader constants and input
     model are unchanged; only the iframe boundary has been removed. */
  .pill-clip{
    position:absolute; z-index:4;
    left:calc(644 * var(--u)); top:calc(360 * var(--u));
    width:calc(410 * var(--u)); height:calc(270 * var(--u));
    margin:calc(-135 * var(--u)) 0 0 calc(-205 * var(--u));
    clip-path:inset(calc(72 * var(--u)) calc(60 * var(--u))
                    calc(26 * var(--u)) calc(60 * var(--u)) round calc(62 * var(--u)));
  }
  .pill{
    position:absolute; inset:0; --mr:calc(150 * var(--u));
    display:grid; place-items:center;
  }

  .liquid-stage{
    --lu:calc(var(--h) / 516);
    --bh:var(--h);
    --pad:calc(900 * var(--lu));
    position:relative;
    width:max-content; height:max-content;
    padding:var(--pad);
    display:grid; place-items:center;
    touch-action:manipulation;
    font-family:'Lexend','Inter',-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif;
    font-optical-sizing:auto;
    -webkit-font-smoothing:antialiased;
  }
  .liquid-stage--explore{ --h:calc(60.156 * var(--u)); }
  .liquid-stage--play{ --h:calc(88.2288 * var(--u)); }

  .liquid-plate{
    position:absolute;
    inset:var(--pad);
    border-radius:999px;
    background:
      linear-gradient(180deg, rgba(255,255,255,.085), rgba(255,255,255,.014) 44%, rgba(255,255,255,0) 64%),
      rgba(10,12,10,.42);
    box-shadow:
      0 calc(var(--h) * 0.08) calc(var(--h) * 0.18) rgba(0,0,0,.38),
      0 calc(var(--h) * 0.24) calc(var(--h) * 0.50) rgba(0,0,0,.28),
      0 calc(var(--h) * 0.48) calc(var(--h) * 0.96) rgba(0,0,0,.16),
      inset 0 1px 0 rgba(255,255,255,.13),
      inset 0 calc(var(--h) * -0.02) calc(var(--h) * 0.05) rgba(255,255,255,.05);
    transition:box-shadow .38s cubic-bezier(.22,.61,.36,1),
               background .38s cubic-bezier(.22,.61,.36,1);
  }
  .liquid-stage.hot .liquid-plate{
    background:
      linear-gradient(180deg, rgba(255,255,255,.105), rgba(255,255,255,.02) 44%, rgba(255,255,255,0) 64%),
      rgba(8,10,8,.50);
    box-shadow:
      0 calc(var(--h) * 0.10) calc(var(--h) * 0.22) rgba(0,0,0,.44),
      0 calc(var(--h) * 0.32) calc(var(--h) * 0.66) rgba(0,0,0,.34),
      0 calc(var(--h) * 0.66) calc(var(--h) * 1.32) rgba(0,0,0,.20),
      inset 0 1px 0 rgba(255,255,255,.17),
      inset 0 calc(var(--h) * -0.02) calc(var(--h) * 0.05) rgba(255,255,255,.06);
  }
  .liquid-fx{ position:absolute; inset:0; width:100%; height:100%; display:block; }

  .liquid-button{
    position:relative;
    height:var(--bh);
    border:0; background:none;
    border-radius:999px;
    display:flex; align-items:center; justify-content:center;
    color:#fff;
    font-family:inherit; font-weight:500; line-height:1; letter-spacing:0;
    cursor:pointer; -webkit-tap-highlight-color:transparent; outline:none;
  }
  .liquid-button:focus-visible{
    outline:calc(4 * var(--lu)) solid rgba(255,255,255,.55);
    outline-offset:calc(10 * var(--lu));
  }
  .liquid-button .ico{ display:block; flex:none; overflow:visible; }
  .liquid-button .lbl{ display:block; transform:translateY(calc(2 * var(--lu))); }
  .liquid-button--explore{
    padding:0 calc(224 * var(--lu)) 0 calc(95 * var(--lu));
    gap:calc(112 * var(--lu));
    font-size:calc(140 * var(--lu));
  }
  .liquid-button--explore .ico{
    width:calc(150 * var(--lu)); height:calc(150 * var(--lu));
  }
  .liquid-button--play{
    width:var(--bh); height:var(--bh); padding:0;
  }
  .liquid-button--play .ico{
    width:calc(176 * var(--lu)); height:calc(176 * var(--lu));
    margin-left:calc(14 * var(--lu));
  }
  .liquid-button--play .lbl{ display:none; }
  .liquid-stage.press .liquid-plate{
    background:
      linear-gradient(180deg, rgba(255,255,255,.07), rgba(255,255,255,.01) 44%, rgba(255,255,255,0) 64%),
      rgba(7,9,7,.55);
    box-shadow:
      0 calc(var(--h) * 0.04) calc(var(--h) * 0.11) rgba(0,0,0,.46),
      0 calc(var(--h) * 0.13) calc(var(--h) * 0.32) rgba(0,0,0,.36),
      0 calc(var(--h) * 0.27) calc(var(--h) * 0.62) rgba(0,0,0,.22),
      inset 0 1px 0 rgba(255,255,255,.10);
    transition-duration:.10s;
  }

  /* \u2500\u2500 play button (z 4) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  .play-wrap{
    position:absolute; z-index:4; pointer-events:none;
    left:calc(187 * var(--u)); top:calc(431 * var(--u));
    width:calc(170 * var(--u)); height:calc(170 * var(--u));
  }
  .play-wrap > *{ pointer-events:auto; }
  .play-clip{
    position:absolute; left:50%; top:50%;
    width:calc(396 * var(--u)); height:calc(396 * var(--u));
    margin:calc(-198 * var(--u)) 0 0 calc(-198 * var(--u));
    clip-path:inset(calc(131 * var(--u)) calc(106 * var(--u))
                    calc(73 * var(--u)) calc(106 * var(--u)) round calc(92 * var(--u)));
  }
  .play-glass{ position:absolute; inset:0; display:grid; place-items:center; }
  .play-ring{
    position:absolute; inset:0; pointer-events:none;
    border:1px solid rgba(255,255,255,.17); border-radius:50%;
  }
  .play-ring::after{
    content:''; position:absolute; inset:calc(-1 * var(--u));
    border:1px solid rgba(255,255,255,.32); border-radius:50%;
    opacity:0; transform:scale(.86);
    transition:opacity .7s var(--ease), transform .9s var(--ease-out);
  }
  .play-clip:hover ~ .play-ring::after,
  .play-clip:focus-within ~ .play-ring::after{ opacity:1; transform:scale(1.06); }

  /* \u2500\u2500 stats (z 4) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  .stat{ position:absolute; z-index:4; display:flex; align-items:flex-start; gap:calc(9 * var(--u)); }
  .stat--a{ left:calc(1250 * var(--u)); top:calc(216 * var(--u)); }
  .stat--b{ left:calc(1346 * var(--u)); top:calc(326 * var(--u)); }
  .stat .mark{ width:calc(32 * var(--u)); height:calc(32 * var(--u)); flex:none; margin-top:calc(2 * var(--u)); color:rgba(255,255,255,.34); }
  .stat .mark svg{ width:100%; height:100%; display:block; }
  .stat dt{ font-size:calc(13.5 * var(--u)); font-weight:300; color:var(--ink-soft); line-height:calc(19 * var(--u)); }
  .stat dt, .stat dd{ text-shadow:0 calc(2 * var(--u)) calc(16 * var(--u)) rgba(10,14,8,.6); }
  .stat .mark svg{ filter:drop-shadow(0 calc(2 * var(--u)) calc(10 * var(--u)) rgba(10,14,8,.6)); }
  .stat dd{ font-size:calc(13.5 * var(--u)); font-weight:600; color:var(--ink); line-height:calc(21 * var(--u)); }

  /* \u2500\u2500 cards \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  .card{
    position:absolute;
    background:var(--card); border-radius:calc(46 * var(--u));
    box-shadow:0 calc(30 * var(--u)) calc(70 * var(--u)) rgba(16,21,13,.30);
    transition:box-shadow .8s var(--ease);
  }
  /* No z-index here on purpose. z-index:auto keeps the card out of its own
     stacking context, so the body paints under #scene (the moss drapes over
     its shoulder) while .knob, at z 4, still sits in front of the moss. */
  .card--about{
    left:calc(890 * var(--u)); top:calc(200 * var(--u));
    width:calc(330 * var(--u)); height:calc(305 * var(--u));
  }
  .card--stove{
    z-index:4; will-change:transform;
    left:calc(1237 * var(--u)); top:calc(482 * var(--u));
    width:calc(328 * var(--u)); height:calc(310 * var(--u));
  }
  .card .label{
    position:absolute; left:calc(38 * var(--u));
    font-size:calc(15.5 * var(--u)); font-weight:300; color:var(--card-label);
  }
  .card h2{
    position:absolute; left:calc(38 * var(--u));
    font-size:calc(26.2 * var(--u)); line-height:calc(27 * var(--u));
    font-weight:400; letter-spacing:calc(-0.5 * var(--u)); color:var(--card-ink);
  }
  .card--about .label{ top:calc(152 * var(--u)); }
  .card--about h2{ top:calc(177 * var(--u)); width:calc(142 * var(--u)); }
  .card--stove .label{ top:calc(45 * var(--u)); }
  .card--stove h2{ top:calc(70 * var(--u)); }
  /* Both cards carry a plate. The Field Note reads downward \u2014 label, title,
     then the photograph \u2014 so its window sits at the foot of the card; the
     Ethos card reads the other way up, so its window is at the head and the
     copy sits under it. Same frame, mirrored. */
  .card figure{
    position:absolute; left:calc(14 * var(--u)); right:calc(14 * var(--u));
    border-radius:calc(34 * var(--u)); overflow:hidden;
    isolation:isolate; background:#263025;
  }
  .card--stove figure{ bottom:calc(14 * var(--u)); height:calc(158 * var(--u)); }
  .card--about figure{ top:calc(14 * var(--u)); height:calc(122 * var(--u)); }
  /* The plate is its own depth plane. It travels against the card and the
     moss, so the landscape feels like a small window rather than a
     photograph glued to the surface. */
  .portal-media{
    position:absolute; inset:calc(-9 * var(--u)); z-index:1; display:block;
    will-change:transform,clip-path;
    transform:
      perspective(900px)
      translate3d(calc(var(--px,0) * -11px),calc(var(--py,0) * -7px),0)
      rotateY(calc(var(--px,0) * -1.4deg))
      rotateX(calc(var(--py,0) * .9deg));
    transform-origin:50% 50%;
  }
  .portal-media img{
    width:100%; height:100%; object-fit:cover; display:block;
    transform:scale(1.08);
    filter:saturate(.92) contrast(1.03);
    transition:transform 1.25s var(--ease-out),filter .8s var(--ease);
  }
  .card:hover .portal-media img{ transform:scale(1.13); filter:saturate(1.04) contrast(1.04); }
  .pixel-reveal{
    position:absolute; inset:0; z-index:3; width:100%; height:100%;
    pointer-events:none; opacity:0; mix-blend-mode:screen;
  }
  /* The white scan rides the clip edge, so its centre has to travel the
     media element's box, not the figure's \u2014 .portal-media is overscanned by
     9u on every side to give the parallax rotation somewhere to go. Offsetting
     by that 9u in calc() rather than by a translate percentage keeps the
     glow on the edge at every breakpoint, whatever size the plate is. */
  .card figure::after{
    content:''; position:absolute; z-index:2;
    filter:blur(calc(2 * var(--u))); opacity:0; pointer-events:none;
    top:0; bottom:0; width:26%; left:calc(-13% - 9 * var(--u));
    background:linear-gradient(90deg,transparent,rgba(229,244,209,.2) 42%,rgba(252,255,246,.72) 54%,transparent);
  }

  .knob-float{
    position:absolute; z-index:4; pointer-events:none;
    left:calc(1142 * var(--u)); top:calc(427 * var(--u));
    width:calc(58 * var(--u)); height:calc(58 * var(--u));
  }
  .knob-float > *{ pointer-events:auto; }
  .knob--about{ left:0; top:0; }
  .card .knob, .knob--about{
    position:absolute; z-index:4; right:calc(20 * var(--u)); bottom:calc(20 * var(--u));
    width:calc(58 * var(--u)); height:calc(58 * var(--u));
    border:0; border-radius:50%; cursor:pointer;
    background:#fbfcf8; display:grid; place-items:center;
    box-shadow:0 calc(6 * var(--u)) calc(16 * var(--u)) rgba(16,21,13,.18);
    transition:transform .5s var(--ease-out), background .4s var(--ease);
  }
  .knob--about{ right:auto; bottom:auto; width:calc(58 * var(--u)); height:calc(58 * var(--u)); }
  .card--stove .knob{ width:calc(54 * var(--u)); height:calc(54 * var(--u)); right:calc(26 * var(--u)); bottom:calc(26 * var(--u)); }
  .card .knob svg, .knob--about svg{ width:calc(19 * var(--u)); height:calc(19 * var(--u)); display:block; color:#3f453a; }
  .card .knob:hover, .knob--about:hover{ transform:scale(1.1) rotate(8deg); background:#fff; }
  .card:hover{ box-shadow:0 calc(38 * var(--u)) calc(84 * var(--u)) rgba(16,21,13,.36); }

  /* \u2500\u2500 scroll cue (z 4) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  .scroll{
    position:absolute; z-index:4;
    left:calc(846 * var(--u)); top:calc(690 * var(--u));
    display:flex; align-items:center; gap:calc(12 * var(--u));
    writing-mode:vertical-rl;
    font-size:calc(11 * var(--u)); font-weight:400;
    letter-spacing:calc(4.4 * var(--u));
    color:rgba(255,255,255,.5);
    text-transform:uppercase; text-decoration:none;
  }
  .scroll .track{ position:relative; width:1px; height:calc(56 * var(--u)); background:rgba(255,255,255,.18); overflow:hidden; }
  .scroll .track::after{
    content:''; position:absolute; inset:0 0 auto; height:40%;
    background:rgba(255,255,255,.75);
    animation:trickle 2.6s var(--ease) infinite;
  }
  @keyframes trickle{
    0%   { transform:translateY(-105%); opacity:0; }
    22%  { opacity:1; }
    78%  { opacity:1; }
    100% { transform:translateY(255%); opacity:0; }
  }

  /* \u2500\u2500 entrance: everything is wiped in behind a mask \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
     Transform is reserved for the pointer parallax, so the reveal is done
     with clip-path. Once the intro has run, .intro-done drops the clip
     entirely \u2014 a live clip-path would open a stacking context on the About
     card and trap its knob under the moss. */
  .js .mask{ clip-path:inset(100% 0 0 0 round var(--mr,0px)); }
  .is-ready .mask{
    clip-path:inset(0 0 0 0 round var(--mr,0px));
    transition:clip-path 1.05s var(--ease-out) var(--d,0ms);
  }
  .js .mask-circle{ clip-path:circle(0% at 50% 50%); }
  .is-ready .mask-circle{
    clip-path:circle(76% at 50% 50%);
    transition:clip-path 1.1s var(--ease-out) var(--d,0ms);
  }
  .js .fade{ opacity:0; }
  .is-ready .fade{ opacity:1; transition:opacity 1.3s var(--ease) var(--d,0ms); }

  .intro-done .mask, .intro-done .mask-circle{ clip-path:none; transition:none; }

  .card{ --mr:calc(46 * var(--u)); }

  /* the dock drops in tile by tile; the capsule itself only fades, because
     a clip on it would cut the pills off as they magnify past its edge */
  .js .dock{ opacity:0; }
  .is-ready .dock{ opacity:1; transition:opacity .8s var(--ease) 80ms; }
  .js .dock-item{ clip-path:inset(0 0 105% 0); }
  .is-ready .dock-item{
    clip-path:inset(0 0 -30% 0);
    transition:clip-path .9s var(--ease-out) var(--d,0ms),
               color .18s var(--ease), border-color .2s var(--ease), background .2s var(--ease);
  }
  .intro-done .dock-item{ clip-path:none; }

  /* A short rise under a fade rather than a full-height wipe: with nothing
     cropping it, a 105% travel would start line one sitting on top of line
     two. .headline itself carries the pointer parallax, so the transform has
     to go on the inner <i>. */
  .js .headline span i{ opacity:0; transform:translateY(calc(16 * var(--u))); }
  .is-ready .headline span i{
    opacity:1; transform:none;
    transition:opacity 1.05s var(--ease) var(--d,0ms),
               transform 1.25s var(--ease-out) var(--d,0ms);
  }

  /* Each plate resolves like a low-bandwidth botanical transmission: a
     stepped clip exposes the photograph while sampled pixel-dots gather along
     the advancing edge (the dots themselves are painted by canvas).
     Both plates scan across, the Ethos one a beat ahead of the Field Note. */
  .js .portal-media{ clip-path:inset(0 100% 0 0 round calc(25 * var(--u))); }
  .is-ready .card--about .portal-media{ animation:portal-cut 1.45s steps(12,end) .92s both; }
  .is-ready .card--stove .portal-media{ animation:portal-cut 1.45s steps(12,end) 1.08s both; }
  .is-ready .card--about figure::after{ animation:portal-scan 1.45s steps(12,end) .92s both; }
  .is-ready .card--stove figure::after{ animation:portal-scan 1.45s steps(12,end) 1.08s both; }
  .intro-done .portal-media{ clip-path:none; animation:none; }
  @keyframes portal-cut{
    from{ clip-path:inset(0 100% 0 0 round calc(25 * var(--u))); }
    to{ clip-path:inset(0 0 0 0 round calc(25 * var(--u))); }
  }
  /* The glow travels by animating its own offset, not by a translate
     percentage. A translate is a percentage of the glow's width, so the
     distance it covers depends on the plate's proportions \u2014 it overshot by
     a quarter of the card here and rode ahead of the edge the whole way.
     In calc() the travel is exactly the media box: 100% of the plate plus
     the 9u of overscan at each end, at every breakpoint. */
  @keyframes portal-scan{
    0%{ left:calc(-13% - 9 * var(--u)); opacity:0; }
    10%{ opacity:.75; }
    88%{ opacity:.55; }
    100%{ left:calc(87% + 9 * var(--u)); opacity:0; }
  }

  /* No clip on the canvas: the root draws itself in behind the survey pulse,
     and a CSS wipe on top of that would be two reveals fighting each other.
     The fade is only here to cover the first compiled frame. */
  .is-ready #scene{ transition:opacity .45s var(--ease); }

  /* \u2500\u2500 pointer parallax \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
     --px / --py are written on .hero once per frame (-1\u20261). Each layer
     declares how far it rides (--pd, px at full deflection) and how much
     it turns (--pr, degrees), which is what gives the plane its depth. */
  .par{
    transform:
      perspective(1400px)
      translate3d(calc(var(--px,0) * var(--pd,0) * -1px),
                  calc(var(--py,0) * var(--pd,0) * -0.62px),
                  0)
      rotateY(calc(var(--px,0) * var(--pr,0) * 1deg))
      rotateX(calc(var(--py,0) * var(--pr,0) * -0.7deg));
  }
  /* the floating knob turns about the About card's centre, not its own,
     so it stays glued to the corner it belongs to */
  .knob-float{ transform-origin:calc(-87 * var(--u)) calc(-74.5 * var(--u)); }
  .card--about{ transform-origin:50% 50%; }

  /* \u2500\u2500 keyboard focus \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  a:focus-visible, button:focus-visible{
    outline:2px solid rgba(255,255,255,.85);
    outline-offset:calc(4 * var(--u));
    border-radius:calc(6 * var(--u));
  }
  .card .knob:focus-visible, .knob--about:focus-visible, .play:focus-visible{ outline-color:rgba(28,34,22,.9); }

  @media (prefers-reduced-motion:reduce){
    .mask,.mask-circle,.fade,#scene,
    .dock,.dock-item,
    .headline span i{ opacity:1 !important; clip-path:none !important; transform:none !important; transition:none !important; }
    .par{ transform:none !important; }
    .portal-media{ clip-path:none !important; animation:none !important; transform:none !important; }
    .pixel-reveal,.card figure::after{ display:none !important; }
    .portal-media img{ transform:none !important; transition:none !important; }
    .scroll .track::after{ animation:none; }
    #scene{ transition:none; }
  }

  /* \u2500\u2500 narrow screens: one column, the moss becomes a band between the
        copy and the cards (760 design units wide) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  @media (max-width:900px){
    :root{ --u: calc(100vw / 760); }
    .hero{ height:auto; min-height:100svh; }
    .stage{
      position:relative; left:auto; top:auto; margin:0;
      width:100%; height:calc(1625 * var(--u));
    }
    .hero::after{
      background:
        radial-gradient(90% 30% at 50% 74%, rgba(238,243,231,.40) 0%, rgba(238,243,231,.14) 46%, rgba(238,243,231,0) 82%),
        linear-gradient(180deg, rgba(238,243,231,0) 62%, rgba(238,243,231,.05) 100%);
    }
    .guides i:nth-child(3){ display:none; }
    .guides i:nth-child(1){ left:calc(253 * var(--u)) !important; }
    .guides i:nth-child(2){ left:calc(506 * var(--u)) !important; }

    /* one column: the labels come off and the dock keeps only its glyphs,
       because at this scale the type would be four pixels tall */
    /* Floored with max(), not left on the design unit alone: this breakpoint
       runs from 900px down to 320px, so a pure --u dock is a 24px bar with
       12px targets on a phone. The floor only bites at the small end. */
    .dock-wrap{ top:calc(30 * var(--u)); }
    .dock{
      height:max(56px, calc(58 * var(--u)));
      padding:max(6px, calc(6 * var(--u)));
      gap:max(4px, calc(4 * var(--u)));
      border-radius:max(17px, calc(18 * var(--u)));
    }
    .dock-item{
      height:max(44px, calc(46 * var(--u)));
      width:max(44px, calc(46 * var(--u)));
      padding:0; border-radius:max(12px, calc(13 * var(--u)));
    }
    .dock-item span:not(.glyph){ display:none; }
    .dock-item .glyph{ width:max(19px, calc(20 * var(--u))); height:max(19px, calc(20 * var(--u))); }
    .dock-mark svg{ width:52%; height:52%; }
    .knob-float{ left:calc(644 * var(--u)); top:calc(1218 * var(--u)); transform-origin:calc(-264 * var(--u)) calc(-43 * var(--u)); }
    .headline{ left:calc(34 * var(--u)); top:calc(128 * var(--u)); font-size:calc(62 * var(--u)); line-height:calc(66 * var(--u)); }
    .lede{ left:calc(34 * var(--u)); top:calc(288 * var(--u)); width:calc(400 * var(--u)); font-size:calc(19 * var(--u)); line-height:calc(27 * var(--u)); }
    /* one column: the frame keeps its aspect, re-anchored to the left rail */
    .pill-clip{
      left:calc(34 * var(--u)); top:calc(430 * var(--u));
      width:calc(506 * var(--u)); height:calc(334 * var(--u));
      margin:calc(-167 * var(--u)) 0 0 calc(-79 * var(--u));
      clip-path:inset(calc(93 * var(--u)) calc(74 * var(--u)) calc(1 * var(--u)) calc(74 * var(--u)) round calc(76 * var(--u)));
    }
    .liquid-stage--explore{ --h:calc(74.4152 * var(--u)); }
    .play-wrap{ display:none; }

    .stat{ gap:calc(11 * var(--u)); }
    .stat .mark{ width:calc(36 * var(--u)); height:calc(36 * var(--u)); }
    .stat dt{ font-size:calc(16 * var(--u)); line-height:calc(22 * var(--u)); }
    .stat dd{ font-size:calc(16.5 * var(--u)); line-height:calc(24 * var(--u)); }
    .stat--a{ left:calc(34 * var(--u));  top:calc(540 * var(--u)); }
    .stat--b{ left:calc(396 * var(--u)); top:calc(540 * var(--u)); }

    .card{ border-radius:calc(40 * var(--u)); }
    .card--about{ left:calc(34 * var(--u)); top:calc(1050 * var(--u)); width:calc(692 * var(--u)); height:calc(250 * var(--u)); }
    .card--about .label{ top:calc(96 * var(--u)); }
    .card--about h2{ top:calc(124 * var(--u)); width:calc(400 * var(--u)); font-size:calc(32 * var(--u)); line-height:calc(36 * var(--u)); }
    .card--stove{ left:calc(34 * var(--u)); top:calc(1324 * var(--u)); width:calc(692 * var(--u)); height:calc(268 * var(--u)); }
    .card--stove h2{ font-size:calc(32 * var(--u)); }
    /* one column: both plates become a thumbnail on the card's outer edge,
       the Ethos one still anchored to the top */
    .card--stove figure{ left:auto; right:calc(16 * var(--u)); bottom:calc(16 * var(--u)); width:calc(300 * var(--u)); height:calc(150 * var(--u)); }
    .card--about figure{ left:auto; right:calc(16 * var(--u)); top:calc(16 * var(--u)); width:calc(224 * var(--u)); height:calc(218 * var(--u)); }
    .card .knob{ right:calc(24 * var(--u)); bottom:calc(24 * var(--u)); }
    .card--stove .knob{ right:calc(30 * var(--u)); bottom:calc(30 * var(--u)); }

    .scroll{ left:calc(702 * var(--u)); top:calc(470 * var(--u)); }
    .ghost{ font-size:calc(184 * var(--u)); letter-spacing:calc(14 * var(--u)); bottom:calc(660 * var(--u)); left:calc(-10 * var(--u)); }
  }
</style>
</head>
<body>

<main class="hero" id="hero">
  <canvas id="scene"></canvas>

  <div class="dock-wrap">
    <nav class="dock par-dock" style="--pd:5" data-spec aria-label="Primary">
      <a class="dock-item dock-mark" data-dock data-spec data-burst href="#" style="--d:120ms" aria-label="Sylva \u2014 home">
        <svg viewBox="0 0 22 24" aria-hidden="true">
          <path d="M11 1.3c-2.1 0-3.95 1.2-4.75 2.95C3.95 4.55 2.3 6.25 2.3 8.35c0 2.3 1.9 4.2 4.3 4.2h8.8c2.4 0 4.3-1.9 4.3-4.2 0-2.1-1.65-3.8-4-4.1C14.95 2.5 13.1 1.3 11 1.3Z"/>
          <path d="M9.6 12.55h2.8v4.2c1.35.3 2.45 1.15 3.15 2.4-1.35.4-2.4.15-3.15-.4v4.15H9.6v-4.15c-.75.55-1.8.8-3.15.4.7-1.25 1.8-2.1 3.15-2.4v-4.2Z"/>
        </svg>
      </a>
      <a class="dock-item is-active" data-dock data-spec data-burst href="#" style="--d:180ms">
        <span class="glyph" aria-hidden="true">
          <svg viewBox="0 0 16 16"><path d="M8 14V9"/><path d="M8 9c0-2.4 1.7-4.3 4-4.3.2 2.6-1.6 4.6-4 4.3Z"/><path d="M8 10.5C7.9 8.4 6.4 6.8 4.4 6.8 4.3 8.9 5.9 10.6 8 10.5Z"/></svg>
        </span>
        <span>Grove</span>
      </a>
      <a class="dock-item" data-dock data-spec data-burst href="#" style="--d:230ms">
        <span class="glyph" aria-hidden="true">
          <svg viewBox="0 0 16 16"><path d="M1.6 12.4c2.4-3.4 4.3-5.1 5.7-5.1 2 0 3 3.6 5 3.6 1.1 0 1.9-.5 2.4-1.4"/><path d="M4.3 6.2C5.5 4.4 6.6 3.5 7.6 3.5c1.5 0 2.2 2.4 3.7 2.4"/></svg>
        </span>
        <span>Habitats</span>
      </a>
      <a class="dock-item" data-dock data-spec data-burst href="#" style="--d:280ms">
        <span class="glyph" aria-hidden="true">
          <svg viewBox="0 0 16 16"><path d="M4 2.4h5.3L12 5.1v8.5H4z"/><path d="M9.2 2.4V5h2.7"/><path d="M6 8.4h4M6 10.8h2.8"/></svg>
        </span>
        <span>Journal</span>
      </a>
      <a class="dock-item dock-item--enter" data-dock data-spec data-burst href="#" style="--d:330ms">
        <span class="glyph" aria-hidden="true">
          <svg viewBox="0 0 16 16"><path d="M6.6 2.5h5.1a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H6.6"/><path d="M2.6 8h6.6"/><path d="m7 5.6 2.4 2.4L7 10.4"/></svg>
        </span>
        <span>Enter</span>
      </a>
    </nav>
  </div>

  <div class="stage" id="stage">

    <div class="guides fade" style="--d:900ms" aria-hidden="true">
      <i style="left:calc(405 * var(--u))"></i>
      <i style="left:calc(748 * var(--u))"></i>
      <i style="left:calc(1091 * var(--u))"></i>
    </div>

    <div class="ghost fade" style="--d:1150ms" aria-hidden="true">SYLVA</div>

    <!-- card 1 sits *behind* the canvas so the moss drapes over its shoulder -->
    <article class="card card--about mask" style="--d:760ms; --pd:10; --pr:2.2">
      <figure class="portal" data-delay="920">
        <span class="portal-media"><img src="inner-green-assets/card-ethos.jpg" alt="A cushion of moss grown over lichen-crusted stones" loading="eager" decoding="async"></span>
        <canvas class="pixel-reveal" aria-hidden="true"></canvas>
      </figure>
      <p class="label">Our Ethos</p>
      <h2>Let the wild lead.</h2>
    </article>

    <!-- the About knob rides *outside* the card: the card has to stay a plain
         painted box under #scene, so anything that must sit in front of the
         moss lives here instead, sharing the card's parallax origin -->
    <span class="knob-float" style="--pd:10; --pr:2.2">
      <button class="knob knob--about mask-circle" style="--d:1100ms" aria-label="Read about Sylva">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 21v-7"/><path d="M12 14c0-3.3 2.4-6 5.5-6 .3 3.6-2.2 6.4-5.5 6Z"/>
          <path d="M12 16c-.1-2.9-2.2-5.2-4.9-5.2C6.8 13.7 9 16 12 16Z"/>
        </svg>
      </button>
    </span>

    <h1 class="headline" style="--pd:18; --pr:1.2">
      <span><i style="--d:260ms">Step into</i></span>
      <span><i style="--d:360ms">the living world</i></span>
    </h1>

    <p class="lede mask" style="--d:480ms; --pd:14; --pr:1">We restore wild places through patient design, native planting, and a deeper kind of stewardship.</p>

    <div class="pill-clip">
      <div class="pill mask" style="--d:600ms; --pd:15; --pr:1.4">
        <div class="liquid-stage liquid-stage--explore" data-liquid-metal="explore">
          <div class="liquid-plate plate" aria-hidden="true"></div>
          <canvas class="liquid-fx" aria-hidden="true"></canvas>
          <button class="liquid-button liquid-button--explore btn" type="button">
            <svg class="ico" viewBox="0 0 115 115" aria-hidden="true">
              <g stroke="currentColor" stroke-width="11" stroke-linecap="round">
                <path d="M14 34.5 H101"/>
                <path d="M14 57.5 H101"/>
                <path d="M14 80.5 H68"/>
              </g>
            </svg>
            <span class="lbl">Explore the work</span>
          </button>
        </div>
      </div>
    </div>

    <span class="play-wrap" style="--pd:20">
      <span class="play-clip">
        <span class="play-glass mask-circle" style="--d:900ms">
          <span class="liquid-stage liquid-stage--play" data-liquid-metal="play">
            <span class="liquid-plate plate" aria-hidden="true"></span>
            <canvas class="liquid-fx" aria-hidden="true"></canvas>
            <button class="liquid-button liquid-button--play btn" type="button" aria-label="Play the film">
              <svg class="ico" viewBox="0 0 24 24" aria-hidden="true">
                <path d="M8 5.2v13.6L19 12z" fill="currentColor"/>
              </svg>
            </button>
          </span>
        </span>
      </span>
      <span class="play-ring mask-circle" style="--d:840ms" aria-hidden="true"></span>
    </span>

    <dl class="stat stat--a mask" style="--d:700ms; --pd:12">
      <span class="mark" aria-hidden="true">
        <svg viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round">
          <circle cx="15" cy="15" r="10.5" stroke-dasharray="0.6 3.6"/>
          <circle cx="15" cy="15" r="5.6" stroke-dasharray="0.6 3.2"/>
          <circle cx="15" cy="15" r="1.1" fill="currentColor" stroke="none"/>
        </svg>
      </span>
      <div><dt>Canopy restored</dt><dd>282 ha</dd></div>
    </dl>

    <dl class="stat stat--b mask" style="--d:770ms; --pd:13">
      <span class="mark" aria-hidden="true">
        <svg viewBox="0 0 30 30" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round">
          <g id="rays">
            <path d="M15 3.5v5"/><path d="M15 21.5v5"/><path d="M3.5 15h5"/><path d="M21.5 15h5"/>
            <path d="M6.9 6.9l3.5 3.5"/><path d="M19.6 19.6l3.5 3.5"/><path d="M23.1 6.9l-3.5 3.5"/><path d="M10.4 19.6l-3.5 3.5"/>
          </g>
          <circle cx="15" cy="15" r="3.6"/>
        </svg>
      </span>
      <div><dt>Native species</dt><dd>43 mapped</dd></div>
    </dl>

    <article class="card card--stove mask" style="--d:880ms; --pd:22; --pr:2.4">
      <p class="label">Field Note 07</p>
      <h2>After the Rain</h2>
      <figure class="portal" data-delay="1080">
        <span class="portal-media"><img src="inner-green-assets/card-ecostove.jpg" alt="Moss-covered boulders in a misty grove" loading="eager" decoding="async"></span>
        <canvas class="pixel-reveal" aria-hidden="true"></canvas>
      </figure>
      <button class="knob" aria-label="Open field note: After the Rain">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 21v-7"/><path d="M12 14c0-3.3 2.4-6 5.5-6 .3 3.6-2.2 6.4-5.5 6Z"/>
          <path d="M12 16c-.1-2.9-2.2-5.2-4.9-5.2C6.8 13.7 9 16 12 16Z"/>
        </svg>
      </button>
    </article>

    <a class="scroll mask" style="--d:1040ms; --pd:9" href="#">Discover<span class="track"></span></a>

  </div>
</main>

<script src="inner-green-assets/three.min.js"><\/script>
<script>
(function () {
  'use strict';

  function mountLiquidMetal(host) {
    const hostWindow = globalThis;
    const document = {
      body: host,
      getElementById(id) {
        if (id === 'stage') return host;
        if (id === 'fx') return host.querySelector('.liquid-fx');
        if (id === 'btn') return host.querySelector('.liquid-button');
        return null;
      },
      querySelector(selector) { return host.querySelector(selector); }
    };
    const window = {
      devicePixelRatio: hostWindow.devicePixelRatio,
      addEventListener: hostWindow.addEventListener.bind(hostWindow)
    };

/* =====================================================================
   Liquid metal \u2014 a dispersion shader.

   A scalar field V is painted through a soft plateau: dark below it, blown
   white inside, dark above.  The plateau is evaluated once per spectral
   wavelength at a slightly different height in V, so the plateau's lower
   edge fringes warm (red turns on first) and its upper edge fringes cool
   (red turns off first).  Fringe width falls out as dispersion / |grad V|,
   which is why the same shader gives razor-thin rainbow lines where the
   field is pinched and huge navy-to-cyan washes where it is not.

   V itself is built as a family of parallel curves \u2014 one swooping valley
   repeated up the button, at a density that varies along its length \u2014 so
   the ribbons stay laminar rather than turbulent.  See the shader body.
   ===================================================================== */

const VERT = \`#version 300 es
in vec2 position; void main(){ gl_Position = vec4(position,0.,1.); }\`;

const HEAD = \`#version 300 es
precision highp float;
out vec4 o;

uniform vec2  uC;        // pill centre, device px
uniform vec2  uHalf;     // pill half-extent, device px
uniform float uT;        // seconds
uniform float uHover;    // 0..1
uniform float uPress;    // 0..1, eased
uniform vec4  uRip[3];   // xy centre (button heights, +y down), z start, w live
uniform vec4  uRipK;     // speed, ring width, decay, amplitude
uniform vec4  uRipK2;    // facet depth, facet count, crest sharpness, emission
uniform vec4  uPtr;      // xy trailing cursor, z strength, w normalised speed
uniform vec4  uPtrK;     // radius, base amplitude, speed amplitude, rim lift

#define PI 3.14159265

float sdPill(vec2 p, vec2 b, float r){
  vec2 q = abs(p) - b + r;
  return min(max(q.x,q.y),0.) + length(max(q,0.)) - r;
}

/* Expanding ring from each press, in button-height units.  Three slots so a
   quick double-tap overlaps instead of cutting the first one off.

   Two things keep it from reading as a water ripple: the wavefront is
   faceted rather than circular \u2014 its radius is modulated by angle, and the
   facets rotate as it travels \u2014 and the crest profile is a cusp rather than
   a gaussian, so it lands as a crease in sheet metal instead of a soft swell. */
float ripple(vec2 p, float t){
  float sum = 0.;
  for(int i = 0; i < 3; i++){
    if(uRip[i].w < 0.5) continue;
    float age = t - uRip[i].z;
    if(age < 0. || age > 4.) continue;
    vec2  rp = p - uRip[i].xy;
    float facet = 1. + uRipK2.x * cos(uRipK2.y * atan(rp.y, rp.x) + age * 2.1 + float(i) * 2.4);
    float x = (length(rp) - age * uRipK.x * facet) / uRipK.y;
    sum += exp(-pow(abs(x) + 1e-4, uRipK2.z)) * exp(-age * uRipK.z);
  }
  return sum;
}

/* A soft well under the cursor.  It lags behind the real pointer and swells
   with speed, so moving across the button drags the metal rather than sliding
   a static blob over it. */
float pointerW(vec2 p){
  if(uPtr.z < 0.001) return 0.;
  float d = length(p - uPtr.xy) / uPtrK.x;
  return exp(-d*d) * uPtr.z;
}
/* Displacing the sample point, not the field value, is what makes this read as
   liquid: the bands bulge and stretch around the cursor like a lens instead of
   just getting brighter under it. */
vec2 pointerWarp(vec2 p){
  float w = pointerW(p);
  if(w <= 0.) return vec2(0.);
  return normalize(p - uPtr.xy + vec2(1e-5)) * w * (uPtrK.y + uPtrK.z * uPtr.w);
}
\`;

/* ---- the travelling rim, in its own pass so the blur below never touches it */
const FRAG_RIM = HEAD + \`
uniform float uBw;       // stroke half-width, device px
uniform float uE[8];     // base, hot, chroma-across, chroma-along, speed,
                         // topBias, press lift, ripple lift

/* Arc-length position around the pill, 0..1, starting at the right-hand
   extreme and running counter-clockwise.  Straight runs and caps are measured
   in real length so a highlight travels at a constant speed all the way
   round instead of stalling on the caps. */
float perim(vec2 d, float a, float r){
  float P = 4.*a + 2.*PI*r;
  float s;
  if(d.x >= a){                                   // right cap
    float th = atan(d.y, d.x - a); if(th < 0.) th += 2.*PI;
    s = (th <= PI*0.5) ? r*th : P - r*(2.*PI - th);
  } else if(d.x <= -a){                           // left cap
    float th = atan(d.y, d.x + a); if(th < 0.) th += 2.*PI;
    s = r*PI*0.5 + 2.*a + r*(th - PI*0.5);
  } else if(d.y >= 0.){                           // top run
    s = r*PI*0.5 + (a - d.x);
  } else {                                        // bottom run
    s = r*PI*1.5 + 2.*a + (d.x + a);
  }
  return s / P;
}
// periodic bump, so a highlight wraps cleanly at s = 0
float pb(float u, float w){ u = fract(u); float x = min(u, 1.-u); return exp(-(x*x)/(w*w)); }

// travelling brightness around the rim \u2014 three lobes at different speeds and
// widths, which never quite re-align, so the light keeps re-pooling
float rimHot(float s, float t){
  float v = uE[0];
  v += 0.62 * pb(s - t*uE[4],             0.075);
  v += 0.44 * pb(s + t*uE[4]*0.63 + 0.41, 0.135);
  v += 0.30 * pb(s - t*uE[4]*0.34 + 0.73, 0.200);
  return v;
}
// soft band riding the pill edge, offset per channel to fringe across the stroke
float rimBand(float sd, float off){ return 1. - smoothstep(0., uBw*1.05, abs(sd + uBw*0.55 + off)); }

void main(){
  vec2  d  = gl_FragCoord.xy - uC;
  float sd = sdPill(d, uHalf, uHalf.y);
  if(sd > uBw*2.5 || sd < -uBw*3.5){ o = vec4(0.); return; }

  /* Each channel is offset both *across* the stroke and *along* it, so the rim
     fringes red-outside / cyan-inside and its hue also drifts as a highlight
     slides past \u2014 the two together are what read as metal rather than as a
     moving white dot. */
  float a = max(uHalf.x - uHalf.y, 0.);
  float s = perim(d, a, uHalf.y);
  float top = mix(1., 0.5 + 0.5 * (d.y / uHalf.y), uE[5]);

  // pressing lifts the whole outline, and each ripple flares it again as the
  // ring sweeps past \u2014 so the rim reports the press twice, once as a step and
  // once as a wave running round the edge
  // \u2026and the stretch of outline nearest the cursor picks up a little too
  vec2  p   = vec2(d.x, -d.y) / (uHalf.y * 2.);
  float lift = 1. + uPress * uE[6] + ripple(p, uT) * uE[7]
             + pointerW(p) * uPtrK.w;

  o = vec4(vec3(
    rimBand(sd,  uE[2]) * rimHot(s + uE[3], uT),
    rimBand(sd,  0.   ) * rimHot(s,         uT),
    rimBand(sd, -uE[2]) * rimHot(s - uE[3], uT)
  ) * uE[1] * top * lift, 1.);
}\`;

const FRAG_SCENE = HEAD + \`
uniform float uP[21];    // tunables

float h21(vec2 p){
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}
float vn(vec2 p){
  vec2 i = floor(p), f = fract(p);
  f = f*f*(3.-2.*f);
  float a = h21(i), b = h21(i+vec2(1,0)), c = h21(i+vec2(0,1)), d = h21(i+vec2(1,1));
  return mix(mix(a,b,f.x), mix(c,d,f.x), f.y) * 2. - 1.;
}
// normalised to roughly -1..1; low gain keeps the first octave dominant, which
// is what keeps the ribbons big and smooth instead of turbulent
float fbm(vec2 p, float g){
  float s = 0., a = 1., n = 0.;
  for(int i=0;i<4;i++){ s += a*vn(p); n += a; p = p*2.03 + 11.7; a *= g; }
  return s / n;
}
float fbm(vec2 p){ return fbm(p, 0.5); }

/* p is in button-height units, +y down, origin at the pill centre.

   The bands in the reference are a *family of parallel curves*: one swooping
   valley repeated up the button, dense where the light is pinched and pulled
   wide open where it is not.  So the field is built that way explicitly \u2014

       V = (y - valley(x)) * density(x)

   \u2014 rather than hoping 2-D noise happens to produce it.  Level sets of V are
   all vertical translates of the same valley curve, which is what makes the
   ribbons laminar and near-parallel; a density that varies along x is what makes
   them crowd into razor fringes at one end and open into a broad wash at the
   other.  A soft plateau over V then paints them, sampled once per
   wavelength at slightly offset heights, so every edge opens into a prism of
   width dispersion / |grad V|.                                             */

// smooth 1-D wiggle that drifts slowly with time
float wig(float x, float t, float seed){
  return vn(vec2(x,          t*0.150 + seed)) * 0.60
       + vn(vec2(x*2.07 + 4., t*0.105 + seed)) * 0.27
       + vn(vec2(x*4.30 - 7., t*0.080 + seed)) * 0.13;
}

float valleyAt(vec2 p, float t){ return wig(p.x*uP[0], t, 0.0) * uP[1]; }
float densAt  (vec2 p, float t){ return uP[2] * exp(uP[3] * wig(p.x*uP[4] + 9.0, t, 2.7)); }

float surface(vec2 p, float t){
  float V = (p.y - valleyAt(p,t)) * densAt(p,t);
  V += uP[5] * fbm(p*vec2(0.8, 1.7)*uP[6] + vec2(t*0.05, -t*0.03), uP[17]);
  return V - uP[7];
}
// One plateau per unit of V \u2014 so the density is literally bands per button height.
// A plateau rather than a step is what puts warm on the low edge and cool on
// the high edge of every ribbon.
float tone(float v){
  float u = fract(v);
  float e = uP[9], W = uP[10] * 0.5;
  return smoothstep(0.5-W-e, 0.5-W, u) * (1. - smoothstep(0.5+W, 0.5+W+e, u));
}
vec3 spec(float t){ return clamp(vec3(1.5) - abs(4.*t - vec3(3.,2.,1.)), 0., 1.); }

void main(){
  vec2  d  = gl_FragCoord.xy - uC;
  float sd = sdPill(d, uHalf, uHalf.y);
  float pill = 1. - smoothstep(-1., 1., sd);
  float S = uHalf.y * 2.;                 // button height, device px
  float t = uT;

  // rgb is premultiplied by the mask and alpha carries it, so the blur that
  // follows can normalise and keep a clean edge instead of a dark vignette
  if(uHover <= 0.0015 || pill <= 0.0015){ o = vec4(0., 0., 0., pill); return; }

  vec2  p = vec2(d.x, -d.y) / S;          // gl_FragCoord is y-up
  vec2  q = p + pointerWarp(p);           // the cursor drags the sheet

  // self-refraction: bend the lookup along the field's own slope, which piles
  // iso-lines up into folds instead of leaving them evenly spaced
  float h0 = surface(q, t);
  vec2  gp = vec2(dFdx(h0), -dFdy(h0)) * S;          // grad in p-units
  float V  = surface(q - gp * uP[8] / max(uP[2], .001), t);

  // gradient-aligned filaments: fast variation across the iso-lines, slow
  // along them, so the fine detail reads as drawn-out fibres of light
  vec2  gd = normalize(gp + vec2(1e-5));
  V += uP[13] * fbm(vec2(dot(q,gd)*uP[14], dot(q, vec2(-gd.y,gd.x))*uP[14]*0.04) + vec2(0., t*0.06));

  // press ripple: displacing the field rather than adding light means the
  // bands themselves bow outwards as the ring passes, which is what sells it
  // as a disturbance *in* the metal instead of a decal over it
  float rip  = ripple(p, t);
  float well = pointerW(p);
  V += rip * uRipK.w;

  // Real dispersion is not linear in wavelength \u2014 the blue end bends far more
  // than the red (Cauchy).  Skewing the sample offsets the same way is what
  // gives the reference its broad cool wash against a tight warm edge.
  const int N = 21;
  float mid = 1. - pow(0.5, uP[12]);
  vec3 col = vec3(0.), wsum = vec3(0.);
  for(int i=0;i<N;i++){
    float k = float(i)/float(N-1);
    vec3  w = spec(k);
    col  += w * tone(V + ((1. - pow(1. - k, uP[12])) - mid) * uP[11]);
    wsum += w;
  }
  col /= wsum;
  col = pow(col, vec3(uP[15]));

  // light envelope \u2014 the ribbons only exist where the sheet is lit, and the
  // dark upper region is bounded by the same valley curve the bands follow
  float lit = smoothstep(uP[18], uP[19], q.y - valleyAt(q, t));
  lit *= mix(1., lit, 0.55);                     // deepen the unlit crescent
  col *= uP[16] * lit;

  // the crest runs hotter, and carries a little light of its own so it stays
  // legible through the softening blur and across the unlit part of the pill
  col = col * (1. + rip * 1.15 + well * 0.60);

  o = vec4(col * pill * uHover, pill);
}\`;

/* Downsample; optionally adding a second source (used to fold the rim into
   the bloom input).  Alpha rides along so the metal's coverage mask survives
   the blur chain. */
const FRAG_DOWN = \`#version 300 es
precision highp float;
out vec4 o;
uniform sampler2D uTex, uTex2;
uniform vec2 uDstTexel;   // 1 / destination size  (maps dest fragCoord -> uv)
uniform vec2 uSrcTexel;   // 1 / source size       (tap spacing)
uniform float uAdd;       // 1 to include uTex2
void main(){
  vec2 uv = gl_FragCoord.xy * uDstTexel;
  // Taps sit a quarter of a *destination* texel out, so for a 2x reduction
  // they land exactly on the four source texel centres.  Spacing them by a
  // whole source texel instead \u2014 as this did originally \u2014 skips every other
  // pixel, and any fine detail in the field folds down into low-frequency
  // moir\xE9 that no amount of subsequent blurring can remove.
  vec2 e = uDstTexel * 0.25;
  vec4 s = texture(uTex, uv + vec2(-e.x,-e.y)) + texture(uTex, uv + vec2( e.x,-e.y))
         + texture(uTex, uv + vec2(-e.x, e.y)) + texture(uTex, uv + vec2( e.x, e.y));
  s *= 0.25;
  if(uAdd > 0.5){
    vec4 r = texture(uTex2, uv + vec2(-e.x,-e.y)) + texture(uTex2, uv + vec2( e.x,-e.y))
           + texture(uTex2, uv + vec2(-e.x, e.y)) + texture(uTex2, uv + vec2( e.x, e.y));
    s.rgb += r.rgb * 0.25;
  }
  o = s;
}\`;

const FRAG_BLUR = \`#version 300 es
precision highp float;
out vec4 o;
uniform sampler2D uTex; uniform vec2 uTexel; uniform vec2 uDir; uniform float uR;
void main(){
  vec2 uv = gl_FragCoord.xy * uTexel;
  vec2 st = uTexel * uDir * uR;
  vec4 s = texture(uTex, uv) * 0.1964;
  s += (texture(uTex, uv + st*1.4118) + texture(uTex, uv - st*1.4118)) * 0.2969;
  s += (texture(uTex, uv + st*3.2941) + texture(uTex, uv - st*3.2941)) * 0.0944;
  s += (texture(uTex, uv + st*5.1765) + texture(uTex, uv - st*5.1765)) * 0.0104;
  o = s;
}\`;

const FRAG_COMP = HEAD + \`
uniform sampler2D uSoft, uRim, uGlow;
uniform vec2  uRes;
uniform float uGlowGain, uGlowIn, uOccl, uDim, uPunch;

void main(){
  vec2 uv = gl_FragCoord.xy / uRes;
  vec3 glow = texture(uGlow, uv).rgb;

  vec2  d    = gl_FragCoord.xy - uC;
  float sd   = sdPill(d, uHalf, uHalf.y);
  float pill = 1. - smoothstep(-1., 1., sd);

  // normalised blur: dividing by the blurred coverage keeps the softened metal
  // full strength right up to the edge instead of fading into the mask
  vec4 m = texture(uSoft, uv);

  // Scrim, applied *after* the blur: knock the metal back through the middle
  // where the label sits, leaving the top and bottom at full brightness.  Doing
  // this before the blur would smear the protection away at high blur values.
  float veil = 1. - smoothstep(0.46, 0.88, abs(d.y) / uHalf.y);

  // Blurring flattens the tonal range into a wash; putting the contrast back
  // with a power curve \u2014 after the blur, so it costs no smoothness \u2014 is what
  // makes it read as poured metal rather than a soft glow.  Highlights keep
  // their level while the mid-tones drop away.
  vec3 metal = pow(max(m.rgb / max(m.a, 1e-3), 0.), vec3(uPunch));

  vec3 core = metal * pill * mix(1., uDim, veil) + texture(uRim, uv).rgb;

  // The ripple's own light is added here, after the blur, so the crease stays
  // a hard line.  Its displacement of the field still rides inside the
  // softened metal \u2014 the sheet bows, and the crest glints along the fold.
  float rip = ripple(vec2(d.x, -d.y) / (uHalf.y * 2.), uT);
  core += vec3(rip * rip) * uRipK2.w * pill * mix(1., 0.42, veil);

  // The button occludes its own bloom over the patch where its shadow falls,
  // so the drop shadow keeps its contrast even when the face is blown out.
  float sdSh = sdPill(d + vec2(0., uHalf.y * 0.62), uHalf * 0.94, uHalf.y * 0.94);
  float occl = uOccl * exp(-max(sdSh, 0.) / (uHalf.y * 0.75));

  // Bloom spills mostly outward; a little of it is allowed back inside so the
  // hot rim bleeds onto the face, as it does on the reference component.
  vec3 rgb = core + glow * uGlowGain * mix(1., uGlowIn, pill) * (1. - occl * (1. - pill));

  // premultiplied \u2014 the page's ambient pool and the button's drop shadow are
  // CSS underneath, and this layer adds light on top of them
  float a = clamp(max(rgb.r, max(rgb.g, rgb.b)), 0., 1.);
  o = vec4(min(rgb, vec3(1.)), a);
}\`;

/* --------------------------------------------------------------- */
const cv = document.getElementById('fx');
const gl = cv.getContext('webgl2', {alpha:true, antialias:false, premultipliedAlpha:true, powerPreference:'high-performance'});
const stage = document.getElementById('stage');
const btn   = document.getElementById('btn');
const plate = document.querySelector('.plate');

// the metal field \u2014 uP[0..20]
const P = window.__P = {
  valFreq:   0.50,   // 0  x-frequency of the valley curve
  valAmp:    0.55,   // 1  valley depth, in button heights (bounded so the
                     //    ribbon can never drift entirely off the pill)
  dens:      2.40,   // 2  band density \u2014 bands per button height
  densVar:   2.20,   // 3  how much the density swings along x (exponential)
  densFreq:  0.32,   // 4  x-frequency of the density variation
  wobAmp:    0.12,   // 5  organic 2-D wobble, in field units
  wobFreq:   1.60,   // 6  its frequency
  lift:      0.05,   // 7  phase offset of the band family
  refract:   0.18,   // 8  self-refraction \u2014 folds the iso-lines
  edge:      0.04,   // 9  softness of the plateau edges
  width:     0.46,   // 10 plateau width, as a fraction of one band period
  disp:      0.30,   // 11 spectral dispersion, in band periods
  skew:      1.50,   // 12 dispersion skew \u2014 >1 spreads the blue end
  // The filaments were 20 cycles per button height \u2014 finer than the softening
  // buffer can carry, so they aliased into stripes instead of reading as
  // fibres.  At this blur they contribute nothing but that, so they are off.
  fineAmp:   0.0,    // 13 filament amplitude
  fineFreq:  9.0,    // 14 filament frequency across the iso-lines
  gamma:     1.00,   // 15 tone gamma
  gain:      1.90,   // 16 overall gain
  octGain:   0.32,   // 17 fbm octave gain \u2014 low keeps the wobble big
  litLo:    -0.26,   // 18 distance below the valley where light begins
  litHi:     0.10,   // 19 \u2026and where it is full
  dim:       0.44    // 20 how far the metal is knocked back under the label
};
const PKEYS = Object.keys(P);

// the animated rim \u2014 uE[0..5]
const E = window.__E = {
  base:   0.20,      // 0 floor brightness, so the whole outline stays drawn
  hot:    0.82,      // 1 gain on the travelling highlights
  chromA: 0.42,      // 2 chromatic offset across the stroke, device px
  chromS: 0.030,     // 3 chromatic offset along the perimeter, in laps
  speed:  0.070,     // 4 laps per second of the leading highlight
  top:    0.35,      // 5 how much the rim stays biased to the top edge
  press:  0.85,      // 6 how far the outline brightens while held
  ripple: 1.60       // 7 extra flare as a ripple crest crosses the outline
};
const EKEYS = Object.keys(E);

// composite / JS-side only
const C = window.__C = {
  glow:   host.dataset.liquidMetal === 'play' ? 1.28 : 1.95,      // outer-glow gain
  glowR:  host.dataset.liquidMetal === 'play' ? 0.94 : 1.30,      // outer-glow radius
  glowIn: 0.30,      // how much bloom is allowed back inside the pill
  occl:   0.62,      // how much the drop shadow eats the bloom beneath it
  soften: 0.24,      // blur on the metal, in button heights \u2014 the "molten" knob
  punch:  1.50       // contrast curve on the softened metal; 1 = off
};

// disturbances \u2014 all distances in button heights, times in seconds
const R = window.__R = {
  // press ripple
  speed:  1.85,      // how fast the ring expands
  width:  0.20,      // ring thickness
  decay:  1.35,      // e-fold fade
  amp:    1.35,      // how far it displaces the metal field
  facet:  0.18,      // depth of the faceting on the wavefront
  lobes:  6.0,       // how many facets
  sharp:  1.15,      // crest profile: 2 = gaussian swell, ~1 = hard crease
  emit:   0.45,      // light the crest carries of its own
  // cursor well
  ptrRad:  0.55,     // radius of the well
  ptrAmp:  0.32,     // how far the sheet is dragged when the cursor is still
  ptrFast: 0.40,     // extra drag at full speed
  ptrRim:  0.80,     // how much the nearest rim brightens
  ptrLag:  0.0016,   // trail: fraction of the gap left after 1s (lower = snappier)
  ptrVref: 4.5       // cursor speed, in button heights/sec, that counts as "fast"
};

if(!gl){
  document.body.innerHTML = '<p style="color:#888;font:14px system-ui">WebGL2 is required for this page.</p>';
} else {

function sh(type, src){
  const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s);
  if(!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) + '\\n' + src);
  return s;
}
function prog(fs){
  const p = gl.createProgram();
  gl.attachShader(p, sh(gl.VERTEX_SHADER, VERT));
  gl.attachShader(p, sh(gl.FRAGMENT_SHADER, fs));
  gl.bindAttribLocation(p, 0, 'position');
  gl.linkProgram(p);
  if(!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));
  const u = {};
  const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for(let i=0;i<n;i++){ const info = gl.getActiveUniform(p,i); u[info.name.replace('[0]','')] = gl.getUniformLocation(p, info.name); }
  return {p, u};
}
const pScene = prog(FRAG_SCENE), pRim = prog(FRAG_RIM),
      pDown  = prog(FRAG_DOWN),  pBlur = prog(FRAG_BLUR), pComp = prog(FRAG_COMP);

const vao = gl.createVertexArray(); gl.bindVertexArray(vao);
const vbo = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
gl.enableVertexAttribArray(0); gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

const hasFloat = !!gl.getExtension('EXT_color_buffer_half_float');
function makeTarget(){
  const tex = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  const fbo = gl.createFramebuffer();
  gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
  gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
  return {tex, fbo, w:0, h:0};
}
function sizeTarget(t, w, h){
  if(t.w === w && t.h === h) return;
  t.w = w; t.h = h;
  gl.bindTexture(gl.TEXTURE_2D, t.tex);
  if(hasFloat) gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA16F, w, h, 0, gl.RGBA, gl.HALF_FLOAT, null);
  else         gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA8,   w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
}
const T_core = makeTarget(), T_rim = makeTarget(),   // full res
      T_s1   = makeTarget(), T_s2  = makeTarget(),   // half res: metal softening
      T_a    = makeTarget(), T_b   = makeTarget();   // 1/DOWN: bloom

let W = 0, H = 0, DPR = 1, BW = 0, BH = 0, CX = 0, CY = 0;
// The bloom buffer is downsampled to keep the button ~129 texels tall at any
// size, so one set of blur radii gives a glow of the same *relative* extent
// whether this renders at 52px or as a hero.
let DOWN = 4;
const GLOW_TEX = 129;
let needResize = true;

function resize(){
  const r  = stage.getBoundingClientRect();
  const br = btn.getBoundingClientRect();
  DPR = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.max(2, Math.round(r.width  * DPR));
  const h = Math.max(2, Math.round(r.height * DPR));
  if(w !== W || h !== H){ W = w; H = h; cv.width = W; cv.height = H; }
  BW = br.width  * DPR; BH = br.height * DPR;
  CX = (br.left - r.left) * DPR + BW/2;
  CY = H - ((br.top - r.top) * DPR + BH/2);     // gl_FragCoord is y-up
  sizeTarget(T_core, W, H); sizeTarget(T_rim, W, H);
  const hw = Math.max(2, Math.ceil(W/2)), hh = Math.max(2, Math.ceil(H/2));
  sizeTarget(T_s1, hw, hh); sizeTarget(T_s2, hw, hh);
  DOWN = Math.max(1, Math.min(4, Math.round(BH / GLOW_TEX)));
  const dw = Math.max(2, Math.ceil(W/DOWN)), dh = Math.max(2, Math.ceil(H/DOWN));
  sizeTarget(T_a, dw, dh); sizeTarget(T_b, dw, dh);
  needResize = false;
}
new ResizeObserver(() => { needResize = true; }).observe(stage);

function drawTo(t){
  gl.bindFramebuffer(gl.FRAMEBUFFER, t ? t.fbo : null);
  gl.viewport(0, 0, t ? t.w : W, t ? t.h : H);
  gl.drawArrays(gl.TRIANGLES, 0, 3);
}

const uArr = new Float32Array(PKEYS.length);
const eArr = new Float32Array(EKEYS.length);
let hover = 0, hoverTarget = 0, clock = 0, last = performance.now();

// three ripple slots, reused round-robin so rapid taps overlap
const RIP = [0,1,2].map(() => ({x:0, y:0, t:-99, on:0}));
const ripArr = new Float32Array(12);
let ripNext = 0, press = 0, pressTarget = 0;

// the cursor well: a target the metal chases, plus how fast it is being moved
const ptr = {x:0, y:0}, ptrS = {x:0, y:0};
let ptrAmt = 0, ptrSpeed = 0;

function addRipple(x, y){
  const r = RIP[ripNext];
  ripNext = (ripNext + 1) % RIP.length;
  r.x = x; r.y = y; r.t = clock; r.on = 1;
}
// pointer position -> button-height units from the pill centre, +y down
function localPt(e){
  const b = btn.getBoundingClientRect(), s = b.height;
  return [(e.clientX - (b.left + b.width/2)) / s,
          (e.clientY - (b.top  + b.height/2)) / s];
}

const calm = matchMedia('(prefers-reduced-motion: reduce)');
let drawn = null;                  // signature of the last frame actually drawn

/* HOST ADAPTATION \u2014 idle frame cap.
   The authored scene owns its page and can afford to run all twenty passes
   every frame forever, because the rim keeps travelling even at rest. Here
   two of these sit on top of a hero that is already rendering 190k blades of
   moss, and measured together they were halving the whole page: 50 fps with
   them, 92 without.
   Nothing is removed \u2014 the cap only applies while the button is genuinely
   idle, and the rim's travel is 0.07 laps a second, so 30 Hz is far more than
   it needs. The moment a pointer, a press, a focus or a ripple is in play it
   goes back to running every frame, because that is when the metal has to
   track the cursor. */
const IDLE_HZ = 30;
let lastDraw = 0;

function frame(now){
  const dtRaw = (now - last) / 1000; last = now;
  const dt = Math.min(dtRaw, 1/20);
  if(!calm.matches) clock += dt;

  // asymmetric ease: quick to bloom, a touch quicker to die
  const k = hoverTarget > hover ? 1 - Math.pow(0.0012, dt) : 1 - Math.pow(0.00012, dt);
  hover += (hoverTarget - hover) * k;
  if(Math.abs(hoverTarget - hover) < 0.0008) hover = hoverTarget;

  // press snaps on and lets go slowly
  const pk = pressTarget > press ? 1 - Math.pow(1e-9, dt) : 1 - Math.pow(0.004, dt);
  press += (pressTarget - press) * pk;
  if(Math.abs(pressTarget - press) < 0.002) press = pressTarget;

  for(let i = 0; i < RIP.length; i++){
    const r = RIP[i];
    if(r.on && clock - r.t > 4) r.on = 0;
    ripArr[i*4] = r.x; ripArr[i*4+1] = r.y; ripArr[i*4+2] = r.t; ripArr[i*4+3] = r.on;
  }
  const ripLive = RIP.some(r => r.on);

  // the well trails the cursor and swells with how fast it is being dragged
  const lag = 1 - Math.pow(R.ptrLag, dt);
  const dx = (ptr.x - ptrS.x) * lag, dy = (ptr.y - ptrS.y) * lag;
  ptrS.x += dx; ptrS.y += dy;
  const inst = Math.min(Math.hypot(dx, dy) / Math.max(dt, 1e-3) / R.ptrVref, 1);
  ptrSpeed += (inst - ptrSpeed) * (1 - Math.pow(inst > ptrSpeed ? 0.001 : 0.02, dt));
  const wantWell = (on.over || on.press) ? 1 : 0;
  ptrAmt += (wantWell - ptrAmt) * (1 - Math.pow(0.004, dt));
  if(Math.abs(wantWell - ptrAmt) < 0.002) ptrAmt = wantWell;

  if(needResize) resize();

  // The rim keeps travelling even at rest, so the only truly static case is
  // reduced motion with nothing in flight.
  const sig = (calm.matches && !ripLive && ptrAmt < 0.002)
    ? \`\${hover}|\${press}|\${W}|\${H}\` : null;
  if(sig !== null && sig === drawn){ requestAnimationFrame(frame); return; }
  drawn = sig;

  const idle = !on.over && !on.press && !on.focus && !ripLive
            && hover < 0.002 && press < 0.002 && ptrAmt < 0.002;
  if(idle && now - lastDraw < 1000 / IDLE_HZ){ requestAnimationFrame(frame); return; }
  lastDraw = now;

  for(let i = 0; i < uArr.length; i++) uArr[i] = P[PKEYS[i]];
  for(let i = 0; i < eArr.length; i++) eArr[i] = E[EKEYS[i]];
  const bw = Math.max(1.5, 3.2 * (BH/516));      // stroke half-width, device px

  // 1. metal + travelling rim, masked to the pill
  gl.useProgram(pScene.p);
  gl.uniform2f(pScene.u.uC, CX, CY);
  gl.uniform2f(pScene.u.uHalf, BW/2, BH/2);
  gl.uniform1f(pScene.u.uT, clock);
  gl.uniform1f(pScene.u.uHover, hover);
  gl.uniform1f(pScene.u.uPress, press);
  gl.uniform4fv(pScene.u.uRip, ripArr);
  gl.uniform4f(pScene.u.uRipK, R.speed, R.width, R.decay, R.amp);
  gl.uniform4f(pScene.u.uRipK2, R.facet, R.lobes, R.sharp, R.emit);
  gl.uniform4f(pScene.u.uPtr, ptrS.x, ptrS.y, ptrAmt, ptrSpeed);
  gl.uniform4f(pScene.u.uPtrK, R.ptrRad, R.ptrAmp, R.ptrFast, R.ptrRim);
  gl.uniform1fv(pScene.u.uP, uArr);
  drawTo(T_core);

  // 2. rim, kept out of the softening blur so the outline stays razor thin
  gl.useProgram(pRim.p);
  gl.uniform2f(pRim.u.uC, CX, CY);
  gl.uniform2f(pRim.u.uHalf, BW/2, BH/2);
  gl.uniform1f(pRim.u.uT, clock);
  gl.uniform1f(pRim.u.uBw, bw);
  gl.uniform1f(pRim.u.uPress, press);
  gl.uniform4fv(pRim.u.uRip, ripArr);
  gl.uniform4f(pRim.u.uRipK, R.speed, R.width, R.decay, R.amp);
  gl.uniform4f(pRim.u.uRipK2, R.facet, R.lobes, R.sharp, R.emit);
  gl.uniform4f(pRim.u.uPtr, ptrS.x, ptrS.y, ptrAmt, ptrSpeed);
  gl.uniform4f(pRim.u.uPtrK, R.ptrRad, R.ptrAmp, R.ptrFast, R.ptrRim);
  gl.uniform1fv(pRim.u.uE, eArr);
  drawTo(T_rim);

  // 3. soften the metal \u2014 half-res box down, then a separable gaussian.  This
  //    is what turns the prismatic ribbons molten rather than etched.
  gl.useProgram(pDown.p);
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, T_core.tex);
  gl.uniform1i(pDown.u.uTex, 0);
  gl.uniform1f(pDown.u.uAdd, 0);
  gl.uniform2f(pDown.u.uDstTexel, 1/T_s1.w, 1/T_s1.h);
  gl.uniform2f(pDown.u.uSrcTexel, 1/W, 1/H);
  drawTo(T_s1);

  gl.useProgram(pBlur.p);
  gl.uniform1i(pBlur.u.uTex, 0);
  gl.uniform2f(pBlur.u.uTexel, 1/T_s1.w, 1/T_s1.h);
  // Target sigma in half-res texels, tied to the button so it scales with any
  // size.  One very wide 9-tap pass leaves visible comb ghosts \u2014 the taps end
  // up further apart than the sigma they are meant to describe \u2014 so the blur
  // is split into passes whose radii add in quadrature.
  const sigTex = C.soften * (BH * 0.5) * 0.95;
  if(sigTex > 0.1){
    const iters = Math.min(4, Math.max(1, Math.ceil(sigTex / 3.0)));
    gl.uniform1f(pBlur.u.uR, sigTex / Math.sqrt(iters) / 1.95);
    for(let i = 0; i < iters; i++){
      gl.bindTexture(gl.TEXTURE_2D, T_s1.tex); gl.uniform2f(pBlur.u.uDir, 1, 0); drawTo(T_s2);
      gl.bindTexture(gl.TEXTURE_2D, T_s2.tex); gl.uniform2f(pBlur.u.uDir, 0, 1); drawTo(T_s1);
    }
  }

  // 4. bloom, fed by the softened metal plus the crisp rim
  gl.useProgram(pDown.p);
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, T_s1.tex);
  gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, T_rim.tex);
  gl.uniform1i(pDown.u.uTex, 0);
  gl.uniform1i(pDown.u.uTex2, 1);
  gl.uniform1f(pDown.u.uAdd, 1);
  gl.uniform2f(pDown.u.uDstTexel, 1/T_a.w, 1/T_a.h);
  gl.uniform2f(pDown.u.uSrcTexel, 1/T_s1.w, 1/T_s1.h);
  drawTo(T_a);

  gl.useProgram(pBlur.p);
  gl.activeTexture(gl.TEXTURE0);
  gl.uniform1i(pBlur.u.uTex, 0);
  gl.uniform2f(pBlur.u.uTexel, 1/T_a.w, 1/T_a.h);
  const rs = C.glowR * (BH / DOWN) / GLOW_TEX;
  for(const r of [1.0, 2.3, 5.2, 9.0].map(v => v * rs)){
    gl.uniform1f(pBlur.u.uR, r);
    gl.bindTexture(gl.TEXTURE_2D, T_a.tex); gl.uniform2f(pBlur.u.uDir, 1, 0); drawTo(T_b);
    gl.bindTexture(gl.TEXTURE_2D, T_b.tex); gl.uniform2f(pBlur.u.uDir, 0, 1); drawTo(T_a);
  }

  // 5. composite
  gl.useProgram(pComp.p);
  gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, T_s1.tex);  gl.uniform1i(pComp.u.uSoft, 0);
  gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_2D, T_rim.tex); gl.uniform1i(pComp.u.uRim, 1);
  gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, T_a.tex);   gl.uniform1i(pComp.u.uGlow, 2);
  gl.uniform2f(pComp.u.uRes, W, H);
  gl.uniform2f(pComp.u.uC, CX, CY);
  gl.uniform2f(pComp.u.uHalf, BW/2, BH/2);
  gl.uniform1f(pComp.u.uT, clock);
  gl.uniform4fv(pComp.u.uRip, ripArr);
  gl.uniform4f(pComp.u.uRipK, R.speed, R.width, R.decay, R.amp);
  gl.uniform4f(pComp.u.uRipK2, R.facet, R.lobes, R.sharp, R.emit);
  gl.uniform1f(pComp.u.uGlowGain, C.glow);
  gl.uniform1f(pComp.u.uGlowIn, C.glowIn);
  gl.uniform1f(pComp.u.uOccl, C.occl);
  gl.uniform1f(pComp.u.uDim, P.dim);
  gl.uniform1f(pComp.u.uPunch, C.punch);
  drawTo(null);

  requestAnimationFrame(frame);
}

/* ---------------- interaction ----------------
   Hover, press and focus all light the metal; press additionally throws a
   ripple from wherever it landed.  Works for mouse, touch and keyboard. */
const on = {over:false, press:false, focus:false};
const sync = () => {
  hoverTarget = (on.over || on.press || on.focus) ? 1 : 0;
  pressTarget = on.press ? 1 : 0;
  document.body.classList.toggle('hot', hoverTarget > 0.5);
  document.body.classList.toggle('press', on.press);
};

btn.addEventListener('pointerenter', e => {
  if(e.pointerType !== 'mouse') return;
  // land the well where the cursor actually entered, not where it last was
  [ptr.x, ptr.y] = localPt(e);
  ptrS.x = ptr.x; ptrS.y = ptr.y; ptrSpeed = 0;
  on.over = true; sync();
});
btn.addEventListener('pointerleave', e => { if(e.pointerType === 'mouse'){ on.over = false; sync(); } });

// the cursor drags the metal; tracked on the window so a press can slide off
// the button, but only measured while the button is actually engaged
window.addEventListener('pointermove', e => {
  if(!on.over && !on.press) return;
  [ptr.x, ptr.y] = localPt(e);
}, {passive:true});

btn.addEventListener('pointerdown', e => {
  [ptr.x, ptr.y] = localPt(e);
  on.press = true; sync();
  addRipple(ptr.x, ptr.y);
});
window.addEventListener('pointerup',     () => { on.press = false; sync(); });
window.addEventListener('pointercancel', () => { on.press = false; sync(); });
// only keyboard focus keeps it lit \u2014 a mouse click shouldn't leave the button
// glowing after the pointer has moved away
btn.addEventListener('focus', () => {
  on.focus = btn.matches(':focus-visible'); sync();
});
btn.addEventListener('blur', () => { on.focus = false; sync(); });

// keyboard activation gets the same treatment, rippling from the centre
btn.addEventListener('keydown', e => {
  if(e.key !== 'Enter' && e.key !== ' ' || e.repeat) return;
  on.press = true; sync(); addRipple(0, 0);
});
btn.addEventListener('keyup', e => {
  if(e.key !== 'Enter' && e.key !== ' ') return;
  on.press = false; sync();
});

resize();
requestAnimationFrame(frame);

// tiny console hooks for tuning
window.__set = (o = {}, e = {}, c = {}, r = {}) => {
  Object.assign(P, o); Object.assign(E, e); Object.assign(C, c); Object.assign(R, r);
  drawn = null;
};
window.__hover  = v => { on.over = !!v; sync(); };
window.__press  = v => { on.press = !!v; sync(); if(v) addRipple(0, 0); };
window.__ripple = (x = 0, y = 0) => addRipple(x, y);
window.__seek   = v => { clock = v; drawn = null; };
}

  }

  const hosts = globalThis.document.querySelectorAll('[data-liquid-metal]');
  for (let i = 0; i < hosts.length; i++) mountLiquidMetal(hosts[i]);
})();
<\/script>
<script>
/* ====================================================================== *
 * The moss root is grown, not photographed.
 *
 * Everything the old build shipped as two transparent PNGs (4.6 MB) is now
 * geometry: a tapered tube swept along a measured centreline, a second tube
 * that loops over it to make the arch, a handful of recursive offshoots, and
 * ~130 000 instanced blades of moss planted on whatever part of that surface
 * faces the light. The silhouette landmarks \u2014 crest at 25% width, valley at
 * 50%, apex at 73%, the hollow under it \u2014 are lifted straight off the
 * original artwork's alpha channel, so the composition it was laid out
 * against is unchanged.
 *
 * Being procedural also means the scene no longer needs a texture upload, so
 * it now runs from file:// as well as it does from a server.
 * ====================================================================== */
(function () {
  'use strict';

  var REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* \u2500\u2500 pointer parallax \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
     Every layer that carries a --pd gets .par; the loop writes the eased
     pointer position onto .hero once a frame and CSS does the rest, so this
     works whether or not the WebGL scene came up.

     The ghost wordmark and the column guides sit this one out on purpose:
     they are the furthest plane, their travel would be a few pixels, and
     promoting two near-full-stage boxes to composited layers cost more
     frames than the effect was worth. */
  var PARALLAX = '.dock,.headline,.lede,.pill,.play-wrap,' +
                 '.stat--a,.stat--b,.card--about,.knob-float,.card--stove,.scroll';

  var pointer = { x: 0, y: 0 }, smooth = { x: 0, y: 0 };
  var heroEl = document.getElementById('hero');
  var lastX = null, lastY = null;
  var ticking = false, parOn = false;

  /* one rAF for the whole page: it eases the pointer, publishes it, and
     renders the GL scene if there is one */
  function startTick() {
    if (ticking) return;
    ticking = true;
    (function loop() { requestAnimationFrame(loop); tick(); })();
  }

  var lastTick = 0;
  function tick() {
    var now = performance.now();
    var dtUI = lastTick ? Math.min((now - lastTick) / 1000, 0.05) : 0.016;
    lastTick = now;
    drawDock(dtUI);
    drawSpec(dtUI);
    aimMoved = false;
    if (parOn) {
      smooth.x += (pointer.x - smooth.x) * 0.055;
      smooth.y += (pointer.y - smooth.y) * 0.055;
      /* three decimals is finer than a pixel of travel, and rounding lets the
         writes stop entirely once the pointer settles \u2014 no style invalidation
         on an idle page */
      var nx = Math.round(smooth.x * 1000) / 1000, ny = Math.round(smooth.y * 1000) / 1000;
      if (nx !== lastX || ny !== lastY) {
        lastX = nx; lastY = ny;
        heroEl.style.setProperty('--px', nx);
        heroEl.style.setProperty('--py', ny);
      }
    }
    if (renderer && clock) renderFrame();
  }

  function startParallax() {
    startTick();
    if (REDUCED || parOn) return;
    parOn = true;
    var nodes = document.querySelectorAll(PARALLAX);
    for (var i = 0; i < nodes.length; i++) nodes[i].classList.add('par');

    window.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch') return;
      pointer.x = (e.clientX / window.innerWidth) * 2 - 1;
      pointer.y = (e.clientY / window.innerHeight) * 2 - 1;
      /* the GL camera is framed on .hero, not on the window \u2014 on the narrow
         layout the hero is the taller of the two, so the pointer has to be
         put back into the canvas's own box or the moss parts in the wrong place */
      var r = hero.getBoundingClientRect();
      ndc.x =  ((e.clientX - r.left) / r.width) * 2 - 1;
      ndc.y = -((e.clientY - r.top) / r.height) * 2 + 1;
    }, { passive: true });

    window.addEventListener('pointerleave', function () {
      pointer.x = pointer.y = 0; ndc.x = 10;
    });
  }

  var canvas   = document.getElementById('scene');
  var hero     = document.getElementById('hero');
  var stageEl  = document.getElementById('stage');
  var NARROW   = window.matchMedia('(max-width: 900px)');

  /* \u2500\u2500 where the two roots sit on the 1600 \xD7 880 reference frame \u2500\u2500\u2500\u2500\u2500\u2500\u2500
     Unchanged from the artwork build: the near root's box is the old
     moss-arch.png's box, the far one is moss-ridge.png's, so every landmark
     lands exactly where the layout was drawn around it. */
  var ARCH   = { w: 1900, left: -180, top: 306, aspect: 2800 / 1377 };
  var ARCH_N = { w: 1120, left: -290, top: 555, aspect: 2800 / 1377 };
  var FAR    = { w: 1150, left:  -40, top: 320, aspect: 1600 /  757, z: -260 };
  var FAR_N  = { w:  780, left: -110, top: 600, aspect: 1600 /  757, z: -260 };

  var renderer, scene, camera;
  var nearGroup, farGroup, motes, shadowMesh, glowMesh;
  var W = 1, H = 1, DIST = 1400;
  var poleTex = null;
  var scanning = false, scanT = 0, scanMax = 3000;
  var SCAN_DUR = 3.4;
  var clock = null;
  var readyStarted = false;

  /* \u2500\u2500 plate transmission \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
     Sample the actual photograph into a tiny grid and carry those colours
     along the stepped clip edge. The canvas exists for this one entrance
     only; after the reveal it stops painting and the live image takes over.

     The dot front, the white scan and the CSS clip all have to sit on the
     same line, which means reproducing the CSS progression exactly rather
     than approximating it: floor(t * STEPS) / STEPS, linear \u2014 an eased
     curve here put the dots a third of a plate ahead of the edge they are
     supposed to be gathering on. The clip is applied to .portal-media,
     which is overscanned past the figure by 9u so the parallax rotation has
     somewhere to go, so the front has to be converted out of that box and
     into the canvas's before it is painted. */
  var CUT_STEPS = 12, CUT_MS = 1450;
  var portalStarted = false;

  function startPortalReveal() {
    if (REDUCED || portalStarted) return;
    portalStarted = true;
    var figs = document.querySelectorAll('.portal');
    for (var i = 0; i < figs.length; i++) revealPortal(figs[i]);
  }

  function revealPortal(fig) {
    var img = fig.querySelector('img');
    var canvasEl = fig.querySelector('.pixel-reveal');
    var media = fig.querySelector('.portal-media');
    if (!img || !canvasEl || !media) return;

    var delay = parseFloat(fig.getAttribute('data-delay')) || 1080;

    function launch() {
      setTimeout(function () {
        var box = canvasEl.getBoundingClientRect();
        if (!box.width || !box.height) return;

        var dpr = Math.min(window.devicePixelRatio || 1, 2);
        canvasEl.width = Math.max(1, Math.round(box.width * dpr));
        canvasEl.height = Math.max(1, Math.round(box.height * dpr));
        var ctx = canvasEl.getContext('2d');
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

        var cols = 52;
        var rows = Math.max(18, Math.round(cols * box.height / box.width));

        var sample = document.createElement('canvas');
        sample.width = cols; sample.height = rows;
        var sg = sample.getContext('2d', { willReadFrequently:true });
        var rgba = null;
        try {
          sg.drawImage(img, 0, 0, cols, rows);
          rgba = sg.getImageData(0, 0, cols, rows).data;
        } catch (err) {
          /* file:// can make canvas pixels unreadable; the reveal still runs
             with the page's pale-moss transmission colour. */
        }

        /* layout offsets, not bounding rects \u2014 .portal-media carries a live
           transform and its rect would drift with the pointer */
        var over = -media.offsetLeft;
        var span = media.offsetWidth;
        var reach = box.width;

        canvasEl.style.opacity = '1';
        var startedAt = performance.now();

        function paint(now) {
          var t = Math.min(1, (now - startedAt) / CUT_MS);
          var stepped = Math.floor(t * CUT_STEPS) / CUT_STEPS;
          var front = (stepped * span - over) / reach;
          var tailFade = t < .88 ? 1 : (1 - t) / .12;
          ctx.clearRect(0, 0, box.width, box.height);

          for (var y = 0; y < rows; y++) {
            for (var x = 0; x < cols; x++) {
              var an = (x + .5) / cols;
              var delta = an - front;
              /* symmetric about the front: an asymmetric band puts the
                 pattern's centre of mass ahead of the edge it belongs to */
              if (delta < -.16 || delta > .16) continue;

              var band = 1 - Math.abs(delta) / .16;
              var pulse = .68 + .32 * Math.sin(x * 2.71 + y * 1.93 + t * 26);
              var alpha = Math.max(0, band * pulse * tailFade);
              if (alpha < .08) continue;

              var r = 220, g = 238, b = 202;
              if (rgba) {
                var q = (y * cols + x) * 4;
                r = Math.min(255, rgba[q] * 1.18 + 20);
                g = Math.min(255, rgba[q + 1] * 1.18 + 24);
                b = Math.min(255, rgba[q + 2] * 1.12 + 14);
              }

              var px = (x + .5) * box.width / cols;
              var py = (y + .5) * box.height / rows;
              var jitter = (1 - band) * 5;
              px += Math.sin(y * 3.17 + x) * jitter;
              py += Math.cos(x * 2.41 - y) * jitter;
              var radius = (.55 + band * 1.25) * Math.max(.75, reach / 300);

              ctx.fillStyle = 'rgba(' + Math.round(r) + ',' + Math.round(g) + ',' + Math.round(b) + ',' + (alpha * .92) + ')';
              ctx.beginPath();
              ctx.arc(px, py, radius, 0, Math.PI * 2);
              ctx.fill();
            }
          }

          if (t < 1) requestAnimationFrame(paint);
          else {
            ctx.clearRect(0, 0, box.width, box.height);
            canvasEl.style.opacity = '0';
          }
        }
        requestAnimationFrame(paint);
      }, delay);
    }

    if (img.complete && img.naturalWidth) launch();
    else img.addEventListener('load', launch, { once:true });
  }

  /* \u2500\u2500 the dock \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
     Proximity magnification over a rim highlight that points back at the
     pointer. Both are springs, both run off the page's single rAF, and both
     switch off for a coarse pointer \u2014 a dock that magnifies on touch just
     reads as broken, because there is no hover to anticipate the tap.

     Every layout read happens inside the frame, never in the pointer
     handler: the items resize as they grow, so their rects have to be
     re-read, and doing that per pointermove forces a synchronous layout
     several times a frame. The handler only records where the pointer is. */
  var DOCK = { root: null, items: [], on: false, live: false, key: false, dirty: false, u: 1 };
  var SPEC = { items: [], on: false, dirty: false };
  var aimX = 0, aimY = 0, aimSeen = false, aimMoved = false;

  function fineHover() {
    return !REDUCED && window.matchMedia('(hover:hover) and (pointer:fine)').matches;
  }

  function measureDock() {
    if (!DOCK.root) return;
    DOCK.on = fineHover();
    DOCK.u = stageEl.getBoundingClientRect().width / (NARROW.matches ? 760 : 1600);
    for (var i = 0; i < DOCK.items.length; i++) {
      var st = DOCK.items[i];
      st.el.style.width = st.el.style.height = st.el.style.transform = '';
      st.el.dataset.near = 'false';
      st.v = st.vel = st.target = 0;
    }
    for (i = 0; i < DOCK.items.length; i++) {
      var r = DOCK.items[i].el.getBoundingClientRect();
      DOCK.items[i].w = r.width;
      DOCK.items[i].h = r.height;
    }
    DOCK.live = false;
    DOCK.dirty = true;
    aimMoved = aimSeen;
  }

  function dockRest() {
    DOCK.live = false;
    DOCK.dirty = true;
    for (var i = 0; i < DOCK.items.length; i++) {
      DOCK.items[i].target = 0;
      DOCK.items[i].el.dataset.near = 'false';
    }
  }

  function drawDock(dt) {
    if (!DOCK.root || !DOCK.on) return;

    /* Targets are only recomputed when the pointer actually MOVES.
       Re-deriving them every frame from a stale position oscillates: the
       capsule is centred, so a growing pill shifts the whole bar sideways,
       which slides a different pill under a stationary cursor, which grows
       instead, which shifts it back.
       And whichever input moved last owns the dock, or the pointer's last
       position re-targets over keyboard focus and focus never takes. */
    if (aimSeen && aimMoved && !DOCK.key) {
      var rr = DOCK.root.getBoundingClientRect();
      /* the catch box reaches well below the bar, because that is where the
         pills grow to and the pointer has to be able to follow them */
      if (aimX > rr.left - 48 && aimX < rr.right + 48 && aimY > rr.top - 44 && aimY < rr.bottom + 104) {
        for (var i = 0; i < DOCK.items.length; i++) {
          var st = DOCK.items[i], r = st.el.getBoundingClientRect();
          var prox = clamp01(1 - Math.abs(aimX - (r.left + r.width * 0.5)) / (128 * DOCK.u));
          st.target = prox * prox * (3 - 2 * prox);
          st.el.dataset.near = st.target > 0.08 ? 'true' : 'false';
        }
        DOCK.live = true;
        DOCK.dirty = true;
      } else if (DOCK.live) dockRest();
    }

    if (!DOCK.dirty) return;
    var moving = false;
    for (i = 0; i < DOCK.items.length; i++) {
      st = DOCK.items[i];
      st.vel += (st.target - st.v) * 190 * dt;
      st.vel *= Math.exp(-23 * dt);
      st.v += st.vel * dt;
      if (Math.abs(st.target - st.v) < 0.001 && Math.abs(st.vel) < 0.004) { st.v = st.target; st.vel = 0; }
      else moving = true;

      var v = Math.min(Math.max(st.v, 0), 1.08);
      var mark = st.el.classList.contains('dock-mark');
      var ew = mark ? 14 * DOCK.u : Math.min(18 * DOCK.u, st.w * 0.24);
      var eh = mark ? 14 * DOCK.u : 16 * DOCK.u;
      st.el.style.width = (st.w + ew * v).toFixed(2) + 'px';
      st.el.style.height = (st.h + eh * v).toFixed(2) + 'px';
      st.el.style.transform = 'translateY(' + (v * 3.5 * DOCK.u).toFixed(2) + 'px)';
    }
    if (!moving) DOCK.dirty = false;
  }

  function drawSpec(dt) {
    if (!SPEC.on) return;

    if (aimSeen && aimMoved) {
      for (var i = 0; i < SPEC.items.length; i++) {
        var st = SPEC.items[i], r = st.el.getBoundingClientRect();
        var cx = r.left + r.width * 0.5, cy = r.top + r.height * 0.5;
        var dx = Math.max(r.left - aimX, 0, aimX - r.right);
        var dy = Math.max(r.top - aimY, 0, aimY - r.bottom);
        var d = Math.sqrt(dx * dx + dy * dy);
        /* inside the box there is no direction to point at, so bias off the
           corner and let the offset from centre steer it */
        st.tAng = d === 0
          ? Math.atan2(2 / Math.max(r.height, 1), -2 / Math.max(r.width, 1)) +
            ((aimX - cx) / Math.max(r.width * 0.5, 1)) * 0.30 +
            ((cy - aimY) / Math.max(r.height * 0.5, 1)) * 0.15
          : Math.atan2(cy - aimY, aimX - cx);
        var raw = clamp01(1 - d / (st.reach * DOCK.u));
        st.tBr = Math.max(raw * raw * (3 - 2 * raw), st.focused ? 0.9 : 0);
      }
      SPEC.dirty = true;
    }

    if (!SPEC.dirty) return;
    var moving = false;
    for (i = 0; i < SPEC.items.length; i++) {
      st = SPEC.items[i];
      var diff = ((st.tAng - st.ang + Math.PI * 3) % (Math.PI * 2)) - Math.PI;
      st.ang += diff * (1 - Math.exp(-dt * 8));
      st.br += (st.tBr - st.br) * (1 - Math.exp(-dt * 9));
      if (Math.abs(diff) < 0.001 && Math.abs(st.tBr - st.br) < 0.002) { st.ang = st.tAng; st.br = st.tBr; }
      else moving = true;
      st.el.style.setProperty('--spec-angle', st.ang.toFixed(4) + 'rad');
      st.el.style.setProperty('--spec-bright', (clamp01(st.br) * 0.92).toFixed(3));
    }
    if (!moving) SPEC.dirty = false;
  }

  function initDock() {
    var root = document.querySelector('.dock');
    if (!root) return;
    DOCK.root = root;
    DOCK.items = [].map.call(root.querySelectorAll('[data-dock]'), function (el) {
      return { el: el, w: 0, h: 0, v: 0, vel: 0, target: 0 };
    });
    SPEC.items = [].map.call(document.querySelectorAll('[data-spec]'), function (el) {
      return { el: el, ang: 2.4, tAng: 2.4, br: 0, tBr: 0, focused: false,
               reach: el.classList.contains('dock') ? 250 : 185 };
    });
    SPEC.on = fineHover();

    measureDock();
    /* the labels set the pill widths, so the base measure is wrong until the
       real face has landed */
    if (document.fonts && document.fonts.ready) document.fonts.ready.then(measureDock);
    window.addEventListener('resize', measureDock);

    window.addEventListener('pointermove', function (e) {
      if (e.pointerType === 'touch') return;
      aimX = e.clientX; aimY = e.clientY; aimSeen = true; aimMoved = true; DOCK.key = false;
      DOCK.dirty = SPEC.dirty = true;
    }, { passive: true });

    window.addEventListener('pointerleave', function () {
      aimSeen = false;
      dockRest();
      for (var i = 0; i < SPEC.items.length; i++) SPEC.items[i].tBr = SPEC.items[i].focused ? 0.9 : 0;
      SPEC.dirty = true;
    });

    /* keyboard gets the same magnification, centred on the focused pill */
    root.addEventListener('focusin', function (e) {
      var item = e.target.closest('[data-dock]');
      if (!item || !DOCK.on) return;
      var idx = DOCK.items.map(function (st) { return st.el; }).indexOf(item);
      DOCK.items.forEach(function (st, i) {
        st.target = i === idx ? 1 : Math.abs(i - idx) === 1 ? 0.24 : 0;
        st.el.dataset.near = st.target > 0.08 ? 'true' : 'false';
      });
      DOCK.live = false; DOCK.key = true; DOCK.dirty = true;
    });
    root.addEventListener('focusout', function () {
      requestAnimationFrame(function () {
        if (!root.contains(document.activeElement)) { DOCK.key = false; dockRest(); }
      });
    });
    for (var i = 0; i < SPEC.items.length; i++) (function (st) {
      st.el.addEventListener('focusin', function () { st.focused = true; SPEC.dirty = true; });
      st.el.addEventListener('focusout', function () { st.focused = false; SPEC.dirty = true; });
    })(SPEC.items[i]);

    /* the current section moves with the click, and the pill throws a
       handful of pollen \u2014 the page already has an emitter for that */
    root.addEventListener('click', function (e) {
      var item = e.target.closest('[data-dock]');
      if (!item) return;
      e.preventDefault();
      if (!item.classList.contains('dock-mark')) {
        for (var i = 0; i < DOCK.items.length; i++) DOCK.items[i].el.classList.remove('is-active');
        item.classList.add('is-active');
      }
      burstAt(e.clientX, e.clientY);
    });
  }

  function ready() {
    if (readyStarted) return;
    readyStarted = true;
    /* The pre-intro styles come from .js on <html>, set while the head was
       parsing, and this runs in the same task as the rest of the script \u2014 so
       nothing has forced the browser to compute them yet. Without a recalc
       here it computes once, sees the finished state, and every transition is
       skipped. */
    void document.body.offsetHeight;
    document.body.classList.add('is-ready');
    startParallax();
    startPortalReveal();
    initDock();
    /* the wipes are done \u2014 drop the clips so nothing keeps a stacking
       context alive (the About knob has to stay above the moss) */
    setTimeout(function () { document.body.classList.add('intro-done'); }, REDUCED ? 0 : 2900);
  }

  /* pointer in NDC, read by the moss shaders through a plane raycast */
  var ndc = { x: 10, y: 10 };

  if (!window.THREE) { ready(); return; }

  /* ================================================================== *
   * deterministic noise \u2014 the same meadow grows on every reload
   * ================================================================== */
  var rng = (function () {
    var a = 0x3f9a1c7b;
    return function () {
      a |= 0; a = (a + 0x6d2b79f5) | 0;
      var t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  })();
  function rand(lo, hi) { return lo + (hi - lo) * rng(); }
  function sstep(a, b, x) { var t = Math.min(Math.max((x - a) / (b - a), 0), 1); return t * t * (3 - 2 * t); }
  function clamp01(x) { return x < 0 ? 0 : (x > 1 ? 1 : x); }

  /* integer hash, not sin(): the lattice is only ever queried at whole
     coordinates, and Math.sin here cost more than everything else the
     builder does put together */
  function hash2(x, y) {
    var n = Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263);
    n = Math.imul(n ^ (n >>> 13), 1274126177);
    return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
  }
  function vnoise(x, y) {
    var ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy;
    var ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
    var a = hash2(ix, iy), b = hash2(ix + 1, iy), c = hash2(ix, iy + 1), d = hash2(ix + 1, iy + 1);
    var t = a + (b - a) * ux;
    return t + ((c + (d - c) * ux) - t) * uy;
  }
  /* rotate each octave as well as scaling it, so the lattice never resolves */
  function fbm2(x, y) {
    var s = 0, amp = 0.5, nx, ny;
    for (var i = 0; i < 4; i++) {
      s += amp * vnoise(x, y);
      nx = 0.80 * x + 0.60 * y; ny = -0.60 * x + 0.80 * y;
      x = nx * 2.07 + 3.1; y = ny * 2.07 - 1.7; amp *= 0.5;
    }
    return s / 0.9375;                                   /* ~[0,1] */
  }

  /* ================================================================== *
   * limbs \u2014 a tube swept along a measured centreline, its upper flank
   * pushed out by however deep the moss lies there
   * ================================================================== */
  var UP = new THREE.Vector3(0, 1, 0);
  var TAU = Math.PI * 2;
  var BOXW = 10;                                          /* each root's box is 10 local units wide */

  /* fractional artwork coords -> local space, origin at the box centre */
  function makeP(aspect) {
    var bh = BOXW / aspect;
    return function (fx, fy, z) {
      return new THREE.Vector3((fx - 0.5) * BOXW, (0.5 - fy) * bh, z || 0);
    };
  }

  function transportFrames(curve, segs) {
    var pts = [], tans = [], nrms = [], i;
    for (i = 0; i <= segs; i++) {
      pts.push(curve.getPointAt(i / segs));
      tans.push(curve.getTangentAt(i / segs).normalize());
    }
    var ref = Math.abs(tans[0].y) < 0.9 ? UP : new THREE.Vector3(1, 0, 0);
    nrms.push(new THREE.Vector3().crossVectors(tans[0], ref).normalize());
    for (i = 1; i <= segs; i++) {
      var axis = new THREE.Vector3().crossVectors(tans[i - 1], tans[i]);
      var n = nrms[i - 1].clone();
      if (axis.lengthSq() > 1e-12) {
        axis.normalize();
        n.applyAxisAngle(axis, Math.acos(Math.min(1, Math.max(-1, tans[i - 1].dot(tans[i])))));
      }
      nrms.push(n.normalize());
    }
    return { pts: pts, tans: tans, nrms: nrms };
  }

  /* How mossy a point on the bark is. Driven by how far the surface faces the
     light rather than by the tube's own parameters \u2014 the arch turns through
     the vertical, and any "up" defined on the cross-section goes degenerate
     there. Two noise fields ride on top: a fine one that frays the moss line
     so it never reads as a stripe, and a slow one that opens bald patches of
     bare wood. Both are sampled in world space, so neighbouring limbs share
     the same weather. */
  function mossCap(p, n, steep) {
    /* On a limb lying flat the camera-facing flank has to stay bark: the
       reference's moss line sits ~25\xB0 above horizontal and everything below
       it is pale wood. Weight n.z any harder than that and the cushion wraps
       right around the limb.
       On a limb standing UP there is no upward face at all \u2014 every
       cross-section normal is horizontal \u2014 so the criterion has to roll over
       to "faces the light", or the arch's legs come out bald. */
    var upness = n.y + n.z * (0.10 + 0.42 * steep) - n.x * (0.05 + 0.45 * steep);
    /* Two scales on the moss line. The fine one keeps it from reading as a
       painted stripe; the coarse one is what makes moss send tongues down the
       flank and lets bare wood push up through the cushion. */
    var fray = fbm2(p.x * 2.30 + 4.4, p.z * 2.30 - p.y * 1.90) - 0.5;
    var tongue = fbm2(p.x * 0.95 + 21.0, p.z * 0.95 - p.y * 0.80) - 0.5;
    var patch = fbm2(p.x * 0.52 + 9.3, p.z * 0.52 + p.y * 0.44);
    var c = sstep(0.16, 0.70, upness + fray * 0.40 + tongue * 0.52);
    /* no floor under the patch term: the cushion has to go properly bald in
       places or the bark never gets to be seen, and the bark is half of what
       makes the root read as wood rather than topiary */
    return c * sstep(0.10, 0.50, patch);
  }
  /* Lumpiness of the cushion itself. Moss is never a smooth offset \u2014 without
     this the tube reads as an extruded pipe with a green stripe painted on
     it, whatever the fur does on top. Two scales: broad cushions, and a
     finer bobble inside them. */
  function mossLump(p) {
    return 0.66 + 0.48 * fbm2(p.x * 2.4 - 2.2, p.z * 2.4 + p.y * 2.0)
                + 0.18 * fbm2(p.x * 7.3 + 5.1, p.z * 7.3 - p.y * 4.4) - 0.09;
  }

  /* A limb's thickness is read off the artwork, not invented: \`rt\` is the
     half-height of the moss-plus-wood band measured column by column out of
     the original PNG's alpha, in local units. Splitting it 0.52 bark / 0.88
     cushion reproduces the reference's section \u2014 moss over roughly the top
     45% of the band, bare wood under it. */
  function table(vals) {
    return function (t) {
      var x = clamp01(t) * (vals.length - 1);
      var i = Math.min(vals.length - 2, Math.floor(x));
      return vals[i] + (vals[i + 1] - vals[i]) * (x - i);
    };
  }

  function makeLimb(P, pts, opt) {
    var v3 = pts.map(function (q) { return P(q[0], q[1], q[2]); });
    var curve = new THREE.CatmullRomCurve3(v3, false, 'centripetal', 0.5);
    var rw = opt.rw, moss = opt.moss;
    if (opt.rt) {
      var rt = table(opt.rt);
      rw = function (t) { return rt(t) * 0.52 * knot(t, 0.05, 0.024); };
      moss = function (t) { return rt(t) * 0.88; };
    }
    return {
      curve: curve,
      segs: opt.segs,
      radial: opt.radial,
      rw: rw,
      moss: moss,
      blade: opt.blade || function (t) { return moss(t) * 0.055 + 0.014; },
      sink: opt.sink || 0,
      vScale: opt.vScale,
      fr: transportFrames(curve, opt.segs),
      len: curve.getLength()
    };
  }

  var _fp = new THREE.Vector3(), _ft = new THREE.Vector3(), _fn = new THREE.Vector3(), _fb = new THREE.Vector3();
  function limbFrame(L, t) {
    var f = clamp01(t) * L.segs;
    var i = Math.min(L.segs - 1, Math.floor(f)), a = f - i;
    _fp.copy(L.fr.pts[i]).lerp(L.fr.pts[i + 1], a);
    /* Control points traced off the artwork sit on the MIDLINE of the
       silhouette, but the silhouette is asymmetric \u2014 bare wood below, wood
       plus cushion above. The tube's own axis is half a cushion lower. */
    if (L.sink) _fp.y -= L.moss(t) * L.sink;
    _ft.copy(L.fr.tans[i]).lerp(L.fr.tans[i + 1], a).normalize();
    _fn.copy(L.fr.nrms[i]).lerp(L.fr.nrms[i + 1], a);
    _fn.addScaledVector(_ft, -_fn.dot(_ft)).normalize();
    _fb.crossVectors(_ft, _fn).normalize();
  }

  /* the finished surface: bark radius plus the moss cushion sitting on it */
  function limbSurface(L, t, th, outP, outN) {
    limbFrame(L, t);
    var steep = Math.min(1, Math.abs(_ft.y) * 1.15);
    var c = Math.cos(th), s = Math.sin(th);
    outN.set(_fn.x * c + _fb.x * s, _fn.y * c + _fb.y * s, _fn.z * c + _fb.z * s).normalize();
    var rw = L.rw(t);
    outP.copy(_fp).addScaledVector(outN, rw);
    var cap = mossCap(outP, outN, steep);
    var d = rw + L.moss(t) * cap * mossLump(outP);
    outP.copy(_fp).addScaledVector(outN, d);
    return cap;
  }

  /* ---- mesh: build the (segs+1) \xD7 (radial+1) grid, then take the normal
          from the grid itself so the displacement is lit, not the tube ---- */
  function tessellate(L, bag) {
    var S = L.segs, R = L.radial;
    var base = bag.pos.length / 3;
    var grid = new Float32Array((S + 1) * (R + 1) * 3);
    var gnrm = new Float32Array((S + 1) * (R + 1) * 3);
    var caps = new Float32Array((S + 1) * (R + 1));
    var p = new THREE.Vector3(), n = new THREE.Vector3();
    var i, j, k;

    for (i = 0; i <= S; i++) {
      for (j = 0; j <= R; j++) {
        var cap = limbSurface(L, i / S, (j / R) * TAU, p, n);
        k = (i * (R + 1) + j) * 3;
        grid[k] = p.x; grid[k + 1] = p.y; grid[k + 2] = p.z;
        caps[i * (R + 1) + j] = cap;
      }
    }

    var a = new THREE.Vector3(), b = new THREE.Vector3(), du = new THREE.Vector3(), dv = new THREE.Vector3();
    function get(i2, j2, out) {
      i2 = Math.min(S, Math.max(0, i2));
      j2 = (j2 + R) % R;                                  /* \u03B8 wraps \u2014 no seam in the normals */
      var q = (i2 * (R + 1) + j2) * 3;
      return out.set(grid[q], grid[q + 1], grid[q + 2]);
    }

    for (i = 0; i <= S; i++) {
      for (j = 0; j <= R; j++) {
        get(i + 1, j, a); get(i - 1, j, b); du.subVectors(a, b);
        get(i, j + 1, a); get(i, j - 1, b); dv.subVectors(a, b);
        n.crossVectors(dv, du);
        if (n.lengthSq() < 1e-12) { limbSurface(L, i / S, (j / R) * TAU, p, n); } else n.normalize();
        k = (i * (R + 1) + j) * 3;
        bag.pos.push(grid[k], grid[k + 1], grid[k + 2]);
        bag.nor.push(n.x, n.y, n.z);
        /* u is a triangle wave so the bark noise mirrors instead of seaming */
        bag.inf.push(1 - Math.abs(2 * (j / R) - 1), (i / S) * L.vScale, caps[i * (R + 1) + j]);
        gnrm[k] = n.x; gnrm[k + 1] = n.y; gnrm[k + 2] = n.z;
      }
    }
    for (i = 0; i < S; i++) for (j = 0; j < R; j++) {
      var q0 = base + i * (R + 1) + j, q1 = q0 + R + 1;
      bag.idx.push(q0, q1, q0 + 1, q1, q1 + 1, q0 + 1);
    }
    /* the fur is planted straight onto this, so hand it over */
    L.grid = grid; L.gnrm = gnrm; L.gcaps = caps; L.S = S; L.R = R;
  }

  /* ---- blades: planted straight onto the shell grid the tessellator just
          built. Rejection-sampling the surface function instead meant three
          more evaluations of two fBm fields per accepted blade, which at this
          density was 1.3 s of blocked main thread \u2014 right on top of the
          entrance animation. Sampling the grid is O(1) per blade, and it also
          guarantees the fur sits exactly on the surface that gets drawn.
          Cells are drawn in proportion to area x moss, so density follows the
          cushion rather than the tube's parameterisation. ---- */
  function plantBlades(L, count, bag) {
    var S = L.S, R = L.R, grid = L.grid, gn = L.gnrm, caps = L.gcaps;
    if (!grid) return 0;
    var cells = S * R, cdf = new Float64Array(cells), total = 0;
    var ax, ay, az, bx, by, bz, cx, cy, cz, i, j, k;

    for (i = 0; i < S; i++) for (j = 0; j < R; j++) {
      var q00 = (i * (R + 1) + j) * 3, q10 = q00 + 3, q01 = ((i + 1) * (R + 1) + j) * 3;
      ax = grid[q10] - grid[q00]; ay = grid[q10 + 1] - grid[q00 + 1]; az = grid[q10 + 2] - grid[q00 + 2];
      bx = grid[q01] - grid[q00]; by = grid[q01 + 1] - grid[q00 + 1]; bz = grid[q01 + 2] - grid[q00 + 2];
      cx = ay * bz - az * by; cy = az * bx - ax * bz; cz = ax * by - ay * bx;
      var area = Math.sqrt(cx * cx + cy * cy + cz * cz);
      var cap = 0.25 * (caps[i * (R + 1) + j] + caps[i * (R + 1) + j + 1] +
                        caps[(i + 1) * (R + 1) + j] + caps[(i + 1) * (R + 1) + j + 1]);
      total += area * cap * cap;
      cdf[i * R + j] = total;
    }
    if (total <= 0) return 0;

    var planted = 0;
    for (var b = 0; b < count; b++) {
      /* binary search the area-weighted cell distribution */
      var target = rng() * total, lo = 0, hi = cells - 1;
      while (lo < hi) { var mid = (lo + hi) >> 1; if (cdf[mid] < target) lo = mid + 1; else hi = mid; }
      i = (lo / R) | 0; j = lo - i * R;
      var u = rng(), v = rng();

      var i0 = i * (R + 1) + j, i1 = i0 + 1, i2 = i0 + R + 1, i3 = i2 + 1;
      var w0 = (1 - u) * (1 - v), w1 = u * (1 - v), w2 = (1 - u) * v, w3 = u * v;
      var cap2 = caps[i0] * w0 + caps[i1] * w1 + caps[i2] * w2 + caps[i3] * w3;
      if (cap2 < 0.05) continue;

      var p0 = i0 * 3, p1 = i1 * 3, p2 = i2 * 3, p3 = i3 * 3;
      var px = grid[p0] * w0 + grid[p1] * w1 + grid[p2] * w2 + grid[p3] * w3;
      var py = grid[p0 + 1] * w0 + grid[p1 + 1] * w1 + grid[p2 + 1] * w2 + grid[p3 + 1] * w3;
      var pz = grid[p0 + 2] * w0 + grid[p1 + 2] * w1 + grid[p2 + 2] * w2 + grid[p3 + 2] * w3;
      /* the grid normal is the CUSHION's normal, lumps and all \u2014 standing the
         fur on the smooth cross-section normal instead throws away every bump
         the displacement just built */
      var nx = gn[p0] * w0 + gn[p1] * w1 + gn[p2] * w2 + gn[p3] * w3;
      var ny = gn[p0 + 1] * w0 + gn[p1 + 1] * w1 + gn[p2 + 1] * w2 + gn[p3 + 1] * w3;
      var nz = gn[p0 + 2] * w0 + gn[p1 + 2] * w1 + gn[p2 + 2] * w2 + gn[p3 + 2] * w3;
      var nl = Math.sqrt(nx * nx + ny * ny + nz * nz) || 1;

      bag.off.push(px, py, pz);
      bag.nrm.push(nx / nl, ny / nl, nz / nl);
      /* One blade in sixteen is a long hair. Uniform-length fur cuts a hard
         edge against the background; the strays are what make the silhouette
         read as moss rather than a hedge trimmed with shears. */
      var stray = rng() < 0.06 ? rand(1.4, 1.9) : 1.0;
      bag.rnd.push(
        rng() * TAU,                                       /* yaw          */
        L.blade((i + v) / S) * (0.45 + 0.60 * cap2) * (0.58 + 0.50 * rng()) * stray,
        (rng() - 0.5) * 1.15,                              /* lean         */
        rng()                                              /* per-blade tone */
      );
      /* two scales of clumping: broad cushions, and the tufts inside them */
      bag.aux.push(fbm2(px * 0.85 + 17.0, pz * 0.85 - py * 0.7) * 0.62 +
                   fbm2(px * 5.60 - 3.3, pz * 5.60 + py * 2.1) * 0.38);
      planted++;
    }
    return planted;
  }

  /* ---- offshoots: a short recursive fork, two generations deep. The root
          is a root, not a tree, so these stay stubby \u2014 they exist to break
          the tube's silhouette, not to build a canopy. ---- */
  function growOffshoot(list, start, dir, len, r0, gen) {
    var side = new THREE.Vector3().crossVectors(dir, UP);
    if (side.lengthSq() < 1e-6) side.set(1, 0, 0);
    side.normalize();
    var up = new THREE.Vector3().crossVectors(side, dir).normalize();
    var bow = gen === 0 ? rand(0.10, 0.46) : rand(-0.34, 0.42);
    var kink = rand(-0.26, 0.26);

    function node(f, u2, k) {
      return start.clone()
        .addScaledVector(dir, len * f)
        .addScaledVector(up, len * u2)
        .addScaledVector(side, len * k);
    }
    var pts = [start.clone(), node(0.32, bow * 0.30, kink * 0.70), node(0.68, bow * 0.85, kink * 0.24), node(1.0, bow, kink * 0.44)];
    var curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal', 0.5);
    var r1 = r0 * 0.52;
    var L = {
      curve: curve, segs: gen === 0 ? 16 : 11, radial: gen === 0 ? 9 : 7,
      /* draw the last few percent down to a point: tubes are open-ended, and
         a twig that simply stops shows a flat hollow cap hanging in the air */
      rw: function (t) { return (r0 + (r1 - r0) * t) * (1 - 0.86 * sstep(0.90, 1.0, t)); },
      moss: function (t) { return (r0 + (r1 - r0) * t) * 0.95 * (1 - 0.55 * t); },
      blade: function (t) { return (r0 + (r1 - r0) * t) * 0.30 * (1 - 0.55 * t) + 0.035; },
      vScale: len * 7.0
    };
    L.fr = transportFrames(curve, L.segs);
    L.len = curve.getLength();
    list.push(L);

    if (gen >= 1) return;
    var kids = Math.round(rand(1, 2));
    for (var i = 0; i < kids; i++) {
      var tt = 0.34 + (i / Math.max(kids, 1)) * 0.5 + rand(-0.06, 0.06);
      var pt = curve.getPointAt(Math.min(tt, 0.98));
      var tan = curve.getTangentAt(Math.min(tt, 0.98)).normalize();
      var ax = new THREE.Vector3().crossVectors(tan, UP);
      if (ax.lengthSq() < 1e-6) ax.set(1, 0, 0);
      ax.normalize().applyAxisAngle(tan, rng() * TAU);
      var kdir = tan.clone().applyAxisAngle(ax, rand(0.45, 1.05)).addScaledVector(UP, 0.16).normalize();
      growOffshoot(list, pt, kdir, len * rand(0.50, 0.74), (r0 + (r1 - r0) * tt) * rand(0.58, 0.78), gen + 1);
    }
  }

  /* ================================================================== *
   * the two roots, traced off the artwork's alpha channel
   * ================================================================== */
  var knot = function (t, a, b) {
    return 1 + a * Math.sin(t * 23.0 + 1.3) + b * Math.sin(t * 57.0 + 0.4) + b * 0.5 * Math.sin(t * 103.0 + 2.2);
  };

  function buildNearRoot() {
    var P = makeP(ARCH.aspect);
    var limbs = [];

    /* the long snaking root: enters left low, crests at 25%, drops into the
       valley at 50%, then runs out through the right edge */
    limbs.push(makeLimb(P, [
      [-0.075, 0.845, -0.62],
      [ 0.000, 0.790, -0.38],
      [ 0.107, 0.695,  0.04],
      [ 0.196, 0.588,  0.28],
      [ 0.250, 0.566,  0.34],
      [ 0.304, 0.603,  0.22],
      [ 0.411, 0.733, -0.10],
      [ 0.500, 0.779, -0.28],
      [ 0.585, 0.742, -0.05],
      [ 0.696, 0.661,  0.20],
      [ 0.750, 0.672,  0.14],
      [ 0.850, 0.640, -0.08],
      [ 0.930, 0.626, -0.30],
      [ 1.030, 0.634, -0.55],
      [ 1.090, 0.638, -0.70]
    ], {
      segs: 300, radial: 26, vScale: 30,
      /* half-band, local units, sampled every 10% of the run */
      rt: [0.575, 0.590, 0.630, 0.680, 0.695, 0.615, 0.580, 0.480, 0.550, 0.550, 0.520], sink: 0.5
    }));

    /* the arch: lifts off the root at 55%, crowns at 73% with a deep moss
       cushion, then plants its leg through the root and off the bottom */
    /* The arch is not one bent tube. Measured column by column, the crown is
       0.88 units wide and 1.90 tall with a 0.86 \xD7 0.94 eye punched under it \u2014
       that is two steep legs fused at the top, not a hoop. Built as two limbs
       that interpenetrate at the peak, which is also how the reference reads:
       different bark and a different moss line on each side. */
    var legRw   = table([0.30, 0.28, 0.26, 0.25, 0.24, 0.23, 0.22]);
    var legMoss = table([0.24, 0.24, 0.23, 0.22, 0.21, 0.20, 0.19]);
    limbs.push(makeLimb(P, [
      [0.532, 0.860,  0.20],
      [0.572, 0.700,  0.28],
      [0.612, 0.540,  0.34],
      [0.652, 0.390,  0.33],
      [0.690, 0.263,  0.26],
      [0.722, 0.180,  0.15],
      [0.752, 0.163,  0.02]
    ], {
      segs: 130, radial: 20, vScale: 22,
      rw:   function (t) { return legRw(t) * knot(t, 0.05, 0.022); },
      moss: legMoss
    }));

    var legR   = table([0.23, 0.25, 0.27, 0.30, 0.33, 0.36, 0.40]);
    var legRm  = table([0.19, 0.20, 0.21, 0.22, 0.24, 0.25, 0.26]);
    limbs.push(makeLimb(P, [
      [0.706, 0.176, -0.02],
      [0.740, 0.158,  0.02],
      [0.772, 0.245, -0.08],
      [0.797, 0.400, -0.18],
      [0.816, 0.570, -0.22],
      [0.836, 0.760, -0.18],
      [0.858, 0.950, -0.08],
      [0.888, 1.180,  0.04]
    ], {
      segs: 150, radial: 20, vScale: 22,
      rw:   function (t) { return legR(t) * knot(t, 0.05, 0.022); },
      moss: legRm
    }));

    return limbs;
  }

  function buildFarRoot() {
    var P = makeP(FAR.aspect);
    return [makeLimb(P, [
      [-0.060, 0.880, -0.35],
      [ 0.100, 0.762, -0.05],
      [ 0.210, 0.698,  0.22],
      [ 0.300, 0.570,  0.30],
      [ 0.410, 0.467,  0.18],
      [ 0.500, 0.500, -0.05],
      [ 0.600, 0.622, -0.22],
      [ 0.720, 0.748, -0.26],
      [ 0.800, 0.788, -0.08],
      [ 0.900, 0.660,  0.14],
      [ 0.990, 0.454,  0.28]
    ], {
      segs: 220, radial: 20, vScale: 26,
      rt: [0.760, 0.900, 0.900, 0.960, 0.925, 0.950, 1.020, 1.020, 0.990, 1.100, 1.300], sink: 0.5
    })];
  }

  /* ================================================================== *
   * shaders
   * ================================================================== */
  var LIGHT_GLSL = [
    'uniform vec3 uKeyDir, uKeyCol, uFillDir, uFillCol, uAmbCol, uHazeCol;',
    'uniform float uHaze, uFog, uMaskOn, uHazeLift;',
    'uniform vec4 uMask;',
    'vec3 litSurface(vec3 N, vec3 albedo, float ao){',
    '  float k = max(dot(N, uKeyDir), 0.0);',
    '  float f = max(dot(N, uFillDir), 0.0);',
    '  float sky = 0.5 + 0.5 * N.y;',
    '  return albedo * (uKeyCol * (0.09 + 1.05 * k) + uFillCol * (0.04 + 0.34 * f) + uAmbCol * (0.35 + 0.65 * sky)) * ao;',
    '}',
    /* Aerial perspective: the reference reads noticeably paler and less
       saturated at the crown than down in the light pool, so lift toward the
       lit-air tone as the form climbs.
       Weighted by the surface's own luminance, because a flat mix puts a
       floor under every shadow \u2014 that one change is the difference between
       moss with 9-to-67 of tonal range and moss with 22-to-37. Distant
       geometry gets uHazeLift near 1 and does lift its darks, which is what
       air actually does at that range. */
    'vec3 aerial(vec3 c, float h){',
    '  float amt = clamp(uFog + uHaze * smoothstep(0.05, 0.95, h), 0.0, 1.0);',
    '  float gain = smoothstep(0.003, 0.075, dot(c, vec3(0.30, 0.59, 0.11)));',
    '  return mix(c, uHazeCol, amt * mix(uHazeLift, 1.0, gain));',
    '}',
    /* \u2500\u2500 survey pulse \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
       A wavefront expands from one point on the left of the frame and the
       root only exists behind it, so the branch is drawn in as the pulse
       passes over it. \`lag\` holds the solid a beat behind the wireframe,
       which is what makes the mesh read as a scan rather than as a wipe. The
       front is wobbled by a couple of long sines so it never reads as a
       clean circle sweeping the screen. */
    'uniform vec3 uScanO;',
    'uniform float uScanR, uScanOn;',
    'bool unscanned(vec3 w, float lag){',
    '  if (uScanOn < 0.5) return false;',
    '  float wob = sin(w.y * 0.011 + w.x * 0.007) * 36.0 + sin(w.z * 0.021 + w.y * 0.013) * 17.0;',
    '  return distance(w, uScanO) > uScanR - lag + wob;',
    '}',
    /* the far ridge has to dissolve before it reaches the cards, and into the
       floor light below it \u2014 the same two masks the artwork build carried */
    'float maskAt(vec3 lp, float boxH){',
    '  if (uMaskOn < 0.5) return 1.0;',
    '  float e = 1.0 - smoothstep(uMask.x, uMask.y, lp.x);',
    '  float l = smoothstep(uMask.z, uMask.w, lp.y / boxH + 0.5);',
    '  return clamp(e * l, 0.0, 1.0);',
    '}'
  ].join('\\n');

  var NOISE_GLSL = [
    'vec2 hash22(vec2 p){',
    '  p = vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)));',
    '  return -1.0 + 2.0 * fract(sin(p) * 43758.5453123);',
    '}',
    /* gradient noise, not value noise: value noise puts its extrema on the
       lattice, which on a tube shows up as blobs in rows */
    'float gnoise(vec2 p){',
    '  vec2 i = floor(p), f = fract(p);',
    '  vec2 u = f * f * (3.0 - 2.0 * f);',
    '  return mix(mix(dot(hash22(i + vec2(0,0)), f - vec2(0,0)),',
    '                 dot(hash22(i + vec2(1,0)), f - vec2(1,0)), u.x),',
    '             mix(dot(hash22(i + vec2(0,1)), f - vec2(0,1)),',
    '                 dot(hash22(i + vec2(1,1)), f - vec2(1,1)), u.x), u.y);',
    '}',
    'const mat2 ROT = mat2(0.80, 0.60, -0.60, 0.80);',
    'float gfbm(vec2 p){ float a = 0.5, s = 0.0; for (int i = 0; i < 5; i++){ s += a * gnoise(p); p = ROT * p * 2.03; a *= 0.5; } return s; }',
    'float ridged(vec2 p){ float a = 0.5, s = 0.0; for (int i = 0; i < 4; i++){ s += a * (1.0 - abs(gnoise(p) * 2.0)); p = ROT * p * 2.11; a *= 0.5; } return s; }'
  ].join('\\n');

  var WIND_GLSL = [
    'uniform float uTime;',
    'uniform float uWind;',
    'vec3 windOffset(vec3 p){',
    '  float ph = p.x * 0.42 + p.y * 0.30 + p.z * 0.70;',
    '  float a = 0.030 * uWind;',
    '  return vec3((sin(uTime * 0.58 + ph) + 0.45 * sin(uTime * 1.37 + ph * 2.3)) * a,',
    '              sin(uTime * 0.79 + ph * 1.7) * a * 0.42,',
    '              sin(uTime * 0.51 + ph * 0.9) * a * 0.55);',
    '}'
  ].join('\\n');

  /* ---- bark + moss cushion ---- */
  function barkMaterial(cfg) {
    return new THREE.ShaderMaterial({
      uniforms: cfg.uniforms,
      extensions: { derivatives: true },
      vertexShader: WIND_GLSL + [
        'attribute vec3 inf;',
        'varying vec3 vN; varying vec3 vW; varying vec3 vInf; varying float vH; varying vec3 vL;',
        'uniform float uBoxH;',
        'void main(){',
        '  vInf = inf;',
        '  vN = normalize(normal);',
        '  vec3 p = position + windOffset(position) * (0.35 + 0.65 * inf.z);',
        '  vL = p;',
        '  vH = clamp(p.y / uBoxH + 0.5, 0.0, 1.0);',
        '  vec4 wp = modelMatrix * vec4(p, 1.0);',
        '  vW = wp.xyz;',
        '  gl_Position = projectionMatrix * viewMatrix * wp;',
        '}'
      ].join('\\n'),
      fragmentShader: NOISE_GLSL + LIGHT_GLSL + [
        'precision highp float;',
        'uniform float uAlpha; uniform float uBoxH;',
        'varying vec3 vN; varying vec3 vW; varying vec3 vInf; varying float vH; varying vec3 vL;',

        /* Bark grain is strongly anisotropic \u2014 features run ten times longer
           along the limb than around it, so squash the domain in v first. */
        'vec2 barkDomain(vec2 uv){ return vec2(uv.x * 7.0, uv.y * 0.62); }',
        'float barkHeight(vec2 uv){',
        '  vec2 q = barkDomain(uv);',
        '  vec2 w = vec2(gfbm(q * 0.5), gfbm(q * 0.5 + 9.1));',
        '  vec2 p = q + w * 0.60;',                        /* meander the fissures */
        '  float ridge = ridged(p);',
        '  float plate = smoothstep(-0.25, 0.45, gfbm(q * 0.34));',
        '  float crack = smoothstep(0.30, 0.86, ridged(p * 1.9 + 4.0));',
        '  float fine  = gfbm(p * 5.5) * 0.5 + 0.5;',
        '  return (ridge - 0.5) * 1.85 * mix(0.35, 1.0, plate) - crack * 0.42 + fine * 0.20;',
        '}',
        /* bump-map an unparametrised surface from screen-space derivatives */
        'vec3 bumped(vec3 N, vec3 p, float h, float k){',
        '  vec3 dpx = dFdx(p), dpy = dFdy(p);',
        '  float dhx = dFdx(h) * k, dhy = dFdy(h) * k;',
        '  vec3 r1 = cross(dpy, N), r2 = cross(N, dpx);',
        '  float det = dot(dpx, r1);',
        '  vec3 grad = sign(det) * (dhx * r1 + dhy * r2);',
        '  return normalize(abs(det) * N - grad);',
        '}',

        'void main(){',
        '  if (unscanned(vW, 520.0)) discard;',
        '  vec2 uv = vInf.xy;',
        '  float cap = vInf.z;',
        '  float m = smoothstep(0.05, 0.42, cap);',
        '  vec3 N = normalize(vN);',

        '  float h = barkHeight(uv);',
        '  N = bumped(N, vW, h, mix(0.26, 0.06, m));',

        '  vec2 q = barkDomain(uv);',
        '  float grain  = gfbm(q * 1.25) * 0.5 + 0.5;',
        '  float mottle = gfbm(q * 0.28 + 21.0) * 0.5 + 0.5;',
        '  float crack  = smoothstep(0.30, 0.86, ridged(q * 1.9 + 4.0));',

        /* Old rain-forest wood: silvered grey where the light rakes it,
           near-black in the splits, with a slow drift into damp umber. */
        '  vec3 silver = mix(vec3(0.020, 0.019, 0.018), vec3(0.290, 0.283, 0.264), grain);',
        '  vec3 umber  = mix(vec3(0.024, 0.019, 0.016), vec3(0.175, 0.140, 0.110), grain);',
        '  vec3 wood   = mix(silver, umber, mottle * 0.78);',
        '  wood *= 1.0 - 0.70 * crack;',

        /* the cushion: two greens, mottled, darkest where it packs deepest */
        '  float mo = gfbm(vec2(vW.x * 2.6, vW.z * 2.6 + vW.y * 1.9)) * 0.5 + 0.5;',
        '  vec3 moss = mix(vec3(0.0204, 0.0311, 0.0050), vec3(0.0914, 0.1392, 0.0227), mo);',
        '  moss *= 0.80 + 0.42 * cap;',

        '  vec3 col = mix(wood, moss, m);',
        /* a pale lichen crust where the wood shows and faces up */
        '  float lich = smoothstep(0.56, 0.84, gfbm(q * 0.62 + 31.0) * 0.5 + 0.5);',
        '  lich *= (1.0 - m) * smoothstep(-0.10, 0.70, N.y) * smoothstep(0.15, 0.50, h);',
        '  col = mix(col, vec3(0.162, 0.176, 0.132), lich * 0.78);',

        /* Contact shadow along the moss line. The cushion overhangs the bark
           it sits on, and without this the two materials meet on a clean
           edge that reads as a paint mask rather than as one thing growing
           on another. */
        '  float contact = smoothstep(0.0, 0.16, cap) * (1.0 - smoothstep(0.16, 0.60, cap));',
        '  col *= 1.0 - 0.48 * contact;',
        '  float ao = mix(0.30, 1.02, smoothstep(-0.40, 0.62, h)) * mix(1.0, 0.86, m);',
        '  vec3 lit = litSurface(N, col, ao);',

        '  vec3 V = normalize(cameraPosition - vW);',
        '  lit += col * uAmbCol * pow(1.0 - max(dot(N, V), 0.0), 4.0) * 0.85;',
        '  float spec = pow(max(dot(reflect(-uKeyDir, N), V), 0.0), 20.0);',
        '  lit += uKeyCol * spec * 0.045 * (1.0 - m) * ao;',

        '  float a = uAlpha * maskAt(vL, uBoxH);',
        '  if (a < 0.004) discard;',
        '  gl_FragColor = vec4(aerial(lit, vH), a);',
        '  #include <tonemapping_fragment>',
        '  #include <encodings_fragment>',
        '}'
      ].join('\\n'),
      transparent: cfg.transparent === true,
      depthWrite: cfg.depthWrite !== false,
      side: THREE.DoubleSide
    });
  }

  /* ---- the fur ---- */
  function grassMaterial(cfg) {
    return new THREE.ShaderMaterial({
      uniforms: cfg.uniforms,
      side: THREE.DoubleSide,
      transparent: cfg.transparent === true,
      depthWrite: cfg.depthWrite !== false,
      vertexShader: WIND_GLSL + [
        'attribute vec3 offset;',
        'attribute vec3 nrm;',
        'attribute vec4 rnd;',
        'attribute float aux;',
        'uniform vec3 uMouse;',
        'uniform float uMouseR;',
        'uniform float uBoxH;',
        'varying float vT; varying float vShade; varying float vDark;',
        'varying float vTone; varying float vH; varying vec3 vN; varying vec3 vW; varying vec3 vL;',

        'void main(){',
        '  float t = uv.y; vT = t;',
        '  float len = rnd.y;',

        /* a local basis around the surface normal, rolled by the blade's yaw */
        '  vec3 ref = abs(nrm.y) < 0.95 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);',
        '  vec3 T0 = normalize(cross(nrm, ref));',
        '  vec3 B0 = cross(nrm, T0);',
        '  float ca = cos(rnd.x), sa = sin(rnd.x);',
        '  vec3 widthDir = T0 * ca + B0 * sa;',
        '  vec3 leanDir  = T0 * -sa + B0 * ca;',

        '  float bend = t * t;',
        '  float gust = (sin(uTime * 1.75 + offset.x * 1.6 + rnd.x) * 0.12',
        '             +  sin(uTime * 0.85 + offset.x * 0.55) * 0.07) * uWind;',

        '  vec3 world = offset + windOffset(offset)',
        '             + nrm * (t * len)',
        '             + widthDir * (position.x * len * 0.62)',
        '             + leanDir * (rnd.z * 0.42 * len) * bend',
        '             + (T0 * gust + B0 * gust * 0.6) * bend * len * 1.6;',

        /* the cursor parts the fur: push tangentially, press down along n */
        '  vec3 toB = offset - uMouse;',
        '  float infl = smoothstep(uMouseR, 0.0, length(toB * vec3(1.0, 1.0, 0.30)));',
        '  infl *= infl;',
        '  vec3 push = toB - nrm * dot(toB, nrm);',
        '  float pl = length(push);',
        '  push = pl > 0.0001 ? push / pl : T0;',
        /* Scaled by the blade's own length, not by a constant: a fixed push
           is several times the height of a moss blade and combs the pile
           into streaks instead of parting it. */
        '  world += push * infl * bend * len * 2.2;',
        '  world -= nrm * infl * bend * len * 1.0;',
        '  vDark = infl;',

        '  vShade = (0.66 + 0.34 * rnd.w) * (0.82 + 0.18 * sin(rnd.x * 2.0));',
        '  vShade *= 0.46 + 0.54 * clamp(nrm.y * 0.5 + 0.62, 0.0, 1.0);',
        '  vTone = smoothstep(0.16, 0.86, aux);',
        '  vN = normalize(mix(nrm, normalize(leanDir * rnd.z + nrm), 0.35));',
        '  vL = world;',
        '  vH = clamp(world.y / uBoxH + 0.5, 0.0, 1.0);',
        '  vec4 wp = modelMatrix * vec4(world, 1.0);',
        '  vW = wp.xyz;',
        '  gl_Position = projectionMatrix * viewMatrix * wp;',
        '}'
      ].join('\\n'),
      fragmentShader: LIGHT_GLSL + [
        'precision highp float;',
        'uniform float uAlpha; uniform float uBoxH;',
        'varying float vT; varying float vShade; varying float vDark;',
        'varying float vTone; varying float vH; varying vec3 vN; varying vec3 vW; varying vec3 vL;',
        'void main(){',
        '  if (unscanned(vW, 520.0)) discard;',
        /* Linear-space colours; the output pass handles the sRGB transfer.
           Channel ratios are solved backwards from the reference screen: its
           moss sits at hue 77\xB0, saturation 56%, value 23%, which is a good
           deal more yellow and a good deal deeper than the green a shader
           reaches for on its own. */
        '  vec3 deep = vec3(0.0126, 0.0192, 0.0031);',
        '  vec3 mid  = vec3(0.0488, 0.0744, 0.0121);',
        '  vec3 tip  = vec3(0.1222, 0.1860, 0.0304);',
        '  vec3 tipHi = vec3(0.2600, 0.3900, 0.0640);',
        '  vec3 col = mix(deep, mid, smoothstep(0.0, 0.62, vT));',
        '  col = mix(col, tip, smoothstep(0.38, 1.0, vT) * (0.35 + 0.65 * vTone));',
        /* slow drifts of colour so the pile never reads as flat velvet */
        '  col *= 0.62 + 0.72 * vTone;',
        '  col *= vShade;',
        '  col *= 1.0 - vDark * 0.55;',
        '  vec3 N = normalize(vN);',
        /* self-shadowing inside the pile: the deeper down a blade you look,
           the less sky reaches it. Without this the fur reads as astroturf
           however good the colours are. */
        '  vec3 lit = litSurface(N, col, mix(0.40, 1.10, smoothstep(0.0, 0.88, vT)) * (0.70 + 0.52 * vTone));',
        /* The sunlit crown is added AFTER the pile shading. Fold it into the
           albedo instead and it comes back out at the same value as
           everything else \u2014 which is exactly the flat 22-to-37 range the
           render was stuck at. Only the last quarter of a blade is in the
           open, and it is the whole top decile of the reference's histogram. */
        '  lit += tipHi * smoothstep(0.68, 1.0, vT) * vTone',
        '       * (0.30 + 0.70 * max(dot(N, uKeyDir), 0.0)) * 0.95;',
        /* low sun burning through the blade */
        '  vec3 V = normalize(cameraPosition - vW);',
        '  lit += col * uKeyCol * pow(max(dot(V, -uKeyDir), 0.0), 2.2) * 0.55 * vT;',
        '  float a = uAlpha * maskAt(vL, uBoxH);',
        '  if (a < 0.004) discard;',
        '  gl_FragColor = vec4(aerial(lit, vH), a);',
        '  #include <tonemapping_fragment>',
        '  #include <encodings_fragment>',
        '}'
      ].join('\\n')
    });
  }

  /* ---- ferns: the reference plants them at the ends and in the crooks ---- */
  function fernGeometry() {
    var pos = [], uv = [], idx = [];
    var PAIRS = 13, SEG = 3;
    function rachis(s, out) { out.set(0, s * (1.06 - 0.44 * s * s), 0.36 * s * s); return out; }
    var a = new THREE.Vector3(), b = new THREE.Vector3();

    for (var i = 1; i <= PAIRS; i++) {
      var s = i / (PAIRS + 0.6);
      rachis(s, a);
      var pl = 0.36 * Math.pow(Math.sin(Math.PI * Math.pow(s, 0.62)), 0.75) * (1 - 0.18 * s);
      for (var side = -1; side <= 1; side += 2) {
        var base = pos.length / 3;
        for (var k = 0; k <= SEG; k++) {
          var f = k / SEG;
          /* pinnae sweep forward and droop as they run out */
          var w = 0.088 * pl * Math.pow(Math.sin(Math.PI * Math.min(f * 1.25, 1)), 0.7) * (1 - 0.35 * f);
          rachis(s + f * pl * 0.34, b);
          var x = side * f * pl;
          var y = b.y - 0.22 * pl * f * f;
          var z = b.z + 0.06 * pl * f;
          pos.push(x, y - w, z, x, y + w, z);
          uv.push(f, 0, f, 1);
        }
        for (var k2 = 0; k2 < SEG; k2++) {
          var q = base + k2 * 2;
          idx.push(q, q + 1, q + 2, q + 1, q + 3, q + 2);
        }
      }
    }
    /* the stipe */
    var st = pos.length / 3;
    for (var j = 0; j <= 8; j++) {
      var s2 = j / 8;
      rachis(s2, a);
      pos.push(-0.011 * (1 - 0.6 * s2), a.y, a.z, 0.011 * (1 - 0.6 * s2), a.y, a.z);
      uv.push(0.5, 0, 0.5, 1);
    }
    for (var j2 = 0; j2 < 8; j2++) {
      var q2 = st + j2 * 2;
      idx.push(q2, q2 + 1, q2 + 2, q2 + 1, q2 + 3, q2 + 2);
    }

    var g = new THREE.InstancedBufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    g.setIndex(idx);
    var tmp = new THREE.BufferGeometry();
    tmp.setAttribute('position', g.getAttribute('position'));
    tmp.setIndex(idx); tmp.computeVertexNormals();
    g.setAttribute('normal', tmp.getAttribute('normal'));
    return g;
  }

  function fernMaterial(cfg) {
    return new THREE.ShaderMaterial({
      uniforms: cfg.uniforms,
      side: THREE.DoubleSide,
      vertexShader: WIND_GLSL + [
        'attribute vec3 iPos;',
        'attribute vec4 iQuat;',
        'attribute vec2 iRnd;',
        'uniform float uBoxH;',
        'varying vec2 vUv; varying vec3 vN; varying vec3 vW; varying float vH; varying float vTint; varying vec3 vL;',
        'vec3 qrot(vec4 q, vec3 v){ return v + 2.0 * cross(q.xyz, cross(q.xyz, v) + q.w * v); }',
        'void main(){',
        '  vUv = uv; vTint = iRnd.y;',
        '  vec3 local = qrot(iQuat, position * iRnd.x);',
        '  vN = normalize(qrot(iQuat, normal));',
        /* the frond bows from its stipe, so the sway has to climb with the
           vertex\\'s own height up the rachis, not act on the whole instance */
        '  float sway = sin(uTime * 1.15 + iRnd.y * 6.28) * 0.055 * uWind;',
        '  local += vec3(sway, 0.0, sway * 0.45) * clamp(position.y, 0.0, 1.2) * iRnd.x;',
        '  vec3 p = iPos + windOffset(iPos) + local;',
        '  vL = p;',
        '  vH = clamp(p.y / uBoxH + 0.5, 0.0, 1.0);',
        '  vec4 wp = modelMatrix * vec4(p, 1.0);',
        '  vW = wp.xyz;',
        '  gl_Position = projectionMatrix * viewMatrix * wp;',
        '}'
      ].join('\\n'),
      fragmentShader: LIGHT_GLSL + [
        'precision highp float;',
        'uniform float uAlpha; uniform float uBoxH;',
        'varying vec2 vUv; varying vec3 vN; varying vec3 vW; varying float vH; varying float vTint; varying vec3 vL;',
        'void main(){',
        '  if (unscanned(vW, 520.0)) discard;',
        '  vec3 N = normalize(vN);',
        '  if (!gl_FrontFacing) N = -N;',
        '  vec3 V = normalize(cameraPosition - vW);',
        '  vec3 base = mix(vec3(0.0270, 0.0450, 0.0099), vec3(0.0690, 0.1150, 0.0253), vTint);',
        '  base *= 0.80 + 0.30 * smoothstep(0.0, 0.8, vUv.x);',
        '  vec3 lit = litSurface(N, base, 0.9);',
        /* fronds are thin \u2014 light comes through them */
        '  lit += base * uKeyCol * pow(max(dot(V, -uKeyDir), 0.0), 2.0) * 1.05;',
        '  float a = uAlpha * maskAt(vL, uBoxH);',
        '  if (a < 0.004) discard;',
        '  gl_FragColor = vec4(aerial(lit, vH), a);',
        '  #include <tonemapping_fragment>',
        '  #include <encodings_fragment>',
        '}'
      ].join('\\n')
    });
  }

  /* ---- the survey mesh ----
          Ring-and-spar lines lifted straight off the shell grid: every Nth
          cross-section, plus a handful of lines running the length of each
          limb. Drawn with depthTest off so the whole cage shows through
          itself, which is what makes it read as a scan of the branch rather
          than as an outline drawn on it. Disposed once the pulse is past. */
  var wireMeshes = [];

  function buildWire(L, out) {
    if (!L.grid) return;
    var S = L.S, R = L.R, g = L.grid, i, j, a, b;
    var ringEvery = Math.max(2, Math.round(S / 52));
    var longEvery = Math.max(2, Math.round(R / 9));
    for (i = 0; i <= S; i += ringEvery) {
      for (j = 0; j < R; j++) {
        a = (i * (R + 1) + j) * 3; b = a + 3;
        out.push(g[a], g[a + 1], g[a + 2], g[b], g[b + 1], g[b + 2]);
      }
    }
    for (j = 0; j < R; j += longEvery) {
      for (i = 0; i < S; i++) {
        a = (i * (R + 1) + j) * 3; b = ((i + 1) * (R + 1) + j) * 3;
        out.push(g[a], g[a + 1], g[a + 2], g[b], g[b + 1], g[b + 2]);
      }
    }
  }

  function wireMaterial() {
    return new THREE.ShaderMaterial({
      uniforms: { uScanO: uScanO, uScanR: uScanR, uWire: uWire, uTime: uTime },
      transparent: true, depthWrite: false, depthTest: false,
      blending: THREE.AdditiveBlending,
      vertexShader: [
        'varying vec3 vW;',
        'void main(){',
        '  vec4 wp = modelMatrix * vec4(position, 1.0);',
        '  vW = wp.xyz;',
        '  gl_Position = projectionMatrix * viewMatrix * wp;',
        '}'
      ].join('\\n'),
      fragmentShader: [
        'precision highp float;',
        'uniform vec3 uScanO;',
        'uniform float uScanR, uWire, uTime;',
        'varying vec3 vW;',
        'void main(){',
        '  float d = distance(vW, uScanO);',
        /* a bright ring exactly on the wavefront, over a dim cage that
           lingers behind it and then fades out with uWire */
        '  float rim   = exp(-pow((d - uScanR) / 135.0, 2.0));',
        '  float trail = smoothstep(uScanR, uScanR - 950.0, d);',
        '  float a = (rim * 1.60 + trail * 0.34) * uWire;',
        '  if (a < 0.004) discard;',
        /* survey ticks running out along the beam */
        '  a *= 0.66 + 0.34 * sin(d * 0.045 - uTime * 7.0);',
        '  vec3 col = mix(vec3(0.30, 0.72, 0.46), vec3(0.86, 1.00, 0.90), rim);',
        '  gl_FragColor = vec4(col, clamp(a, 0.0, 1.0));',
        '}'
      ].join('\\n')
    });
  }

  /* ---- the tiny white flowers scattered through the moss ---- */
  var flowerTex = null;
  function makeFlowerTexture() {
    if (flowerTex) return flowerTex;
    /* A spray, not a bloom. One five-petal flower at this size renders as a
       little asterisk; the reference's whites are clusters of florets, so
       the texture carries the whole cluster and each instance is one spray. */
    var c = document.createElement('canvas'); c.width = c.height = 64;
    var g = c.getContext('2d');
    var FLORETS = [
      [32, 22, 7.4], [22, 33, 6.0], [42, 33, 6.2], [27, 44, 5.0],
      [39, 45, 5.4], [32, 33, 4.4], [46, 22, 4.2], [18, 22, 4.0]
    ];
    for (var f = 0; f < FLORETS.length; f++) {
      var cx = FLORETS[f][0], cy = FLORETS[f][1], r = FLORETS[f][2];
      g.save(); g.translate(cx, cy); g.rotate(f * 1.31);
      for (var p = 0; p < 5; p++) {
        g.save(); g.rotate((p / 5) * TAU);
        g.fillStyle = 'rgba(255,255,251,' + (0.72 + 0.28 * (r / 7.4)) + ')';
        g.beginPath(); g.ellipse(0, -r * 0.55, r * 0.34, r * 0.55, 0, 0, TAU); g.fill();
        g.restore();
      }
      g.fillStyle = '#f0e7bd';
      g.beginPath(); g.arc(0, 0, r * 0.24, 0, TAU); g.fill();
      g.restore();
    }
    flowerTex = new THREE.CanvasTexture(c);
    if ('sRGBEncoding' in THREE) flowerTex.encoding = THREE.sRGBEncoding;
    flowerTex.minFilter = THREE.LinearMipmapLinearFilter;
    flowerTex.generateMipmaps = true;
    return flowerTex;
  }

  function flowerMaterial(cfg) {
    return new THREE.ShaderMaterial({
      uniforms: cfg.uniforms,
      transparent: true, depthWrite: false, side: THREE.DoubleSide,
      vertexShader: WIND_GLSL + [
        'attribute vec3 iPos;',
        'attribute vec2 iRnd;',
        'uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',
        'void main(){',
        '  vUv = uv;',
        '  vec3 p = iPos + windOffset(iPos) * 1.6;',
        '  p += vec3(sin(uTime * 1.5 + iRnd.y * 6.28), 0.0, 0.0) * 0.020 * uWind;',
        '  vL = p;',
        '  vH = clamp(p.y / uBoxH + 0.5, 0.0, 1.0);',
        /* Billboard: offset the quad in VIEW space so it always faces the lens.
           The offset has to be converted out of the group\\'s local scale first \u2014
           the modelView transform has already been applied to the anchor. */
        '  vW = (modelMatrix * vec4(p, 1.0)).xyz;',
        '  vec4 mv = modelViewMatrix * vec4(p, 1.0);',
        '  float ws = length(modelMatrix[0].xyz);',
        '  mv.xy += position.xy * iRnd.x * ws;',
        '  gl_Position = projectionMatrix * mv;',
        '}'
      ].join('\\n'),
      fragmentShader: LIGHT_GLSL + [
        'precision highp float;',
        'uniform sampler2D uMap;',
        'uniform float uAlpha; uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',
        'void main(){',
        '  if (unscanned(vW, 520.0)) discard;',
        '  vec4 t = texture2D(uMap, vUv);',
        '  if (t.a < 0.14) discard;',
        '  vec3 col = t.rgb * t.rgb * (uKeyCol * 0.62 + uAmbCol * 0.9);',
        '  gl_FragColor = vec4(aerial(col, vH), t.a * uAlpha * maskAt(vL, uBoxH));',
        '  #include <tonemapping_fragment>',
        '  #include <encodings_fragment>',
        '}'
      ].join('\\n')
    });
  }

  /* ================================================================== *
   * assembly
   * ================================================================== */
  var uTime  = { value: 0 };
  var uWind  = { value: REDUCED ? 0.0 : 1.0 };
  var uMouseNear = { value: new THREE.Vector3(9999, 9999, 9999) };
  var uMouseFar  = { value: new THREE.Vector3(9999, 9999, 9999) };
  /* the survey pulse \u2014 shared by every material so one write moves them all */
  var uScanO  = { value: new THREE.Vector3(-900, -260, 240) };
  var uScanR  = { value: 0 };
  var uScanOn = { value: 0 };
  var uWire   = { value: 0 };

  var KEY  = new THREE.Vector3(-0.30, 0.92, 0.28).normalize();
  var FILL = new THREE.Vector3( 0.12, -0.86, 0.50).normalize();

  function lightUniforms(extra) {
    var u = {
      uTime: uTime, uWind: uWind,
      uKeyDir:  { value: KEY.clone() },
      uKeyCol:  { value: new THREE.Color(1.14, 1.06, 0.88) },
      uFillDir: { value: FILL.clone() },
      /* the pale pool on the floor of the hero, bouncing back up */
      uFillCol: { value: new THREE.Color(0.78, 0.78, 0.62) },
      uAmbCol:  { value: new THREE.Color(0.086, 0.090, 0.080) },
      /* Aerial perspective goes toward LIT air, not toward the background:
         the far ridge in the reference is paler than the page behind it, and
         so are the near crowns. Keep the amount small on the near root or the
         moss greys out (its saturation is the first thing to go). */
      uHazeCol: { value: new THREE.Color(0.176, 0.195, 0.145) },
      uHaze:    { value: 0.14 },
      uHazeLift:{ value: 0.20 },
      uFog:     { value: 0.0 },
      uAlpha:   { value: 1.0 },
      uBoxH:    { value: BOXW / ARCH.aspect },
      uMask:    { value: new THREE.Vector4(0, 1, 0, 1) },
      uMaskOn:  { value: 0 },
      uScanO:   uScanO,
      uScanR:   uScanR,
      uScanOn:  uScanOn,
      uMouse:   { value: uMouseNear.value },
      uMouseR:  { value: 1.5 }
    };
    for (var k in extra) if (extra.hasOwnProperty(k)) u[k] = extra[k];
    return u;
  }

  /* the blade: four rungs pinched to a point, instanced a hundred thousand times */
  function bladeGeometry() {
    var SEGS = 3, verts = [], uvs = [], idx = [], i;
    for (i = 0; i <= SEGS; i++) {
      var t = i / SEGS, w = 0.5 * (1 - t * t);
      verts.push(-w, t, 0, w, t, 0);
      uvs.push(0, t, 1, t);
    }
    verts[verts.length - 6] = 0; verts[verts.length - 3] = 0;
    for (i = 0; i < SEGS; i++) {
      var a = i * 2, b = a + 1, c = a + 2, d = a + 3;
      idx.push(a, b, c, b, d, c);
    }
    var g = new THREE.InstancedBufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(verts, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
    g.setIndex(idx);
    return g;
  }

  /* one root: bark shell + fur + ferns + flowers, all under a single group */
  function assembleRoot(limbs, opt) {
    var group = new THREE.Group();
    var uni = lightUniforms({
      uBoxH:   { value: BOXW / opt.aspect },
      uHaze:   { value: opt.haze },
      uFog:    { value: opt.fog },
      uHazeCol:{ value: new THREE.Color().fromArray(opt.hazeCol || [0.176, 0.195, 0.145]) },
      uHazeLift:{ value: opt.hazeLift === undefined ? 0.20 : opt.hazeLift },
      uAlpha:  { value: opt.alpha },
      uMask:   { value: new THREE.Vector4(opt.mask ? opt.mask[0] : 0, opt.mask ? opt.mask[1] : 1,
                                          opt.mask ? opt.mask[2] : 0, opt.mask ? opt.mask[3] : 1) },
      uMaskOn: { value: opt.mask ? 1 : 0 },
      uMouse:  { value: opt.mouse.value },
      uMouseR: { value: opt.mouseR }
    });
    var soft = !!opt.mask || opt.alpha < 1;

    /* ---- shell ---- */
    var bag = { pos: [], nor: [], inf: [], idx: [] };
    for (var i = 0; i < limbs.length; i++) tessellate(limbs[i], bag);
    var geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.Float32BufferAttribute(bag.pos, 3));
    geo.setAttribute('normal', new THREE.Float32BufferAttribute(bag.nor, 3));
    geo.setAttribute('inf', new THREE.Float32BufferAttribute(bag.inf, 3));
    geo.setIndex(bag.idx);
    var shell = new THREE.Mesh(geo, barkMaterial({
      uniforms: uni, transparent: soft, depthWrite: true
    }));
    shell.frustumCulled = false;
    shell.renderOrder = opt.order;
    group.add(shell);

    /* ---- fur ---- */
    var fur = { off: [], nrm: [], rnd: [], aux: [] };
    var total = 0;
    for (i = 0; i < limbs.length; i++) total += limbs[i].len;
    for (i = 0; i < limbs.length; i++) {
      plantBlades(limbs[i], Math.round(opt.blades * limbs[i].len / total), fur);
    }
    var bg = bladeGeometry();
    bg.setAttribute('offset', new THREE.InstancedBufferAttribute(new Float32Array(fur.off), 3));
    bg.setAttribute('nrm',    new THREE.InstancedBufferAttribute(new Float32Array(fur.nrm), 3));
    bg.setAttribute('rnd',    new THREE.InstancedBufferAttribute(new Float32Array(fur.rnd), 4));
    bg.setAttribute('aux',    new THREE.InstancedBufferAttribute(new Float32Array(fur.aux), 1));
    bg.instanceCount = fur.off.length / 3;
    var grass = new THREE.Mesh(bg, grassMaterial({
      uniforms: uni, transparent: soft, depthWrite: true
    }));
    grass.frustumCulled = false;
    grass.renderOrder = opt.order + 0.1;
    group.add(grass);

    /* ---- ferns and flowers, seated on the same surface as the fur.
            Main limbs only: a fern on a twig that stands off the root reads
            as a frond hanging in mid-air. ---- */
    var host = limbs.slice(0, opt.mainLimbs || limbs.length);
    /* A frond keeps its outline as it fades, while the cushion behind it
       fades to a smooth gradient \u2014 so a fern planted in the ridge's dissolve
       zone reads as one hanging in mid-air. Plant nothing out there. */
    var plantMaxX = opt.mask ? opt.mask[0] + 0.25 : 1e9;
    var fP = [], fQ = [], fR = [], wP = [], wR = [];
    var p = new THREE.Vector3(), n = new THREE.Vector3();
    var q = new THREE.Quaternion(), face = new THREE.Vector3();
    var guard, k;

    for (k = 0, guard = 0; k < opt.ferns && guard < opt.ferns * 60; guard++) {
      var Lf = host[Math.floor(rng() * host.length)];
      var t = rng(), th = rng() * TAU;
      if (limbSurface(Lf, t, th, p, n) < 0.55) continue;
      if (p.x > plantMaxX) continue;
      if (n.y < 0.25) continue;
      face.copy(n).addScaledVector(UP, 0.18)
        .addScaledVector(new THREE.Vector3(rand(-0.62, 0.62), rand(-0.20, 0.05), rand(0.15, 0.75)), 1).normalize();
      q.setFromUnitVectors(UP, face);
      q.multiply(new THREE.Quaternion().setFromAxisAngle(UP, rng() * TAU));
      fP.push(p.x, p.y, p.z);
      fQ.push(q.x, q.y, q.z, q.w);
      fR.push(rand(opt.fernSize[0], opt.fernSize[1]), rng());
      k++;
    }

    for (k = 0, guard = 0; k < opt.flowers && guard < opt.flowers * 60; guard++) {
      var Lw = host[Math.floor(rng() * host.length)];
      /* clumps, not a sprinkle: pick a seed then jitter around it */
      var t0 = rng(), th0 = rng() * TAU;
      for (var c2 = 0; c2 < 9 && k < opt.flowers; c2++) {
        var tt = clamp01(t0 + rand(-0.008, 0.008));
        var tth = th0 + rand(-0.24, 0.24);
        if (limbSurface(Lw, tt, tth, p, n) < 0.45 || p.x > plantMaxX) continue;
        p.addScaledVector(n, rand(0.02, 0.16));
        wP.push(p.x, p.y, p.z);
        wR.push(rand(opt.flowerSize[0], opt.flowerSize[1]), rng());
        k++;
      }
    }

    if (fP.length) {
      var fg = fernGeometry();
      fg.setAttribute('iPos',  new THREE.InstancedBufferAttribute(new Float32Array(fP), 3));
      fg.setAttribute('iQuat', new THREE.InstancedBufferAttribute(new Float32Array(fQ), 4));
      fg.setAttribute('iRnd',  new THREE.InstancedBufferAttribute(new Float32Array(fR), 2));
      fg.instanceCount = fP.length / 3;
      var fern = new THREE.Mesh(fg, fernMaterial({ uniforms: uni }));
      fern.frustumCulled = false;
      fern.renderOrder = opt.order + 0.2;
      group.add(fern);
    }

    if (wP.length) {
      var wg = new THREE.InstancedBufferGeometry();
      wg.setAttribute('position', new THREE.Float32BufferAttribute([-0.5,-0.5,0, 0.5,-0.5,0, 0.5,0.5,0, -0.5,0.5,0], 3));
      wg.setAttribute('uv', new THREE.Float32BufferAttribute([0,0, 1,0, 1,1, 0,1], 2));
      wg.setIndex([0,1,2, 0,2,3]);
      wg.setAttribute('iPos', new THREE.InstancedBufferAttribute(new Float32Array(wP), 3));
      wg.setAttribute('iRnd', new THREE.InstancedBufferAttribute(new Float32Array(wR), 2));
      wg.instanceCount = wP.length / 3;
      var fm = flowerMaterial({ uniforms: uni });
      fm.uniforms.uMap = { value: makeFlowerTexture() };
      var blooms = new THREE.Mesh(wg, fm);
      blooms.frustumCulled = false;
      blooms.renderOrder = opt.order + 0.3;
      group.add(blooms);
    }

    if (opt.wire) {
      var wpos = [];
      for (i = 0; i < limbs.length; i++) buildWire(limbs[i], wpos);
      if (wpos.length) {
        var wgeo = new THREE.BufferGeometry();
        wgeo.setAttribute('position', new THREE.Float32BufferAttribute(wpos, 3));
        var wmesh = new THREE.LineSegments(wgeo, wireMaterial());
        wmesh.frustumCulled = false;
        wmesh.renderOrder = 8;
        group.add(wmesh);
        wireMeshes.push(wmesh);
      }
    }

    /* the shell grids were scratch for the fur \u2014 ~0.7 MB of typed array per
       root that nothing reads again */
    for (i = 0; i < limbs.length; i++) { limbs[i].grid = limbs[i].gnrm = limbs[i].gcaps = null; }

    group.userData = { uni: uni, blades: bg.instanceCount };
    return group;
  }

  /* \u2500\u2500 soft radial sprite \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  function radialTexture(size, stops) {
    var c = document.createElement('canvas'); c.width = c.height = size;
    var g = c.getContext('2d');
    var grad = g.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    stops.forEach(function (s) { grad.addColorStop(s[0], s[1]); });
    g.fillStyle = grad; g.fillRect(0, 0, size, size);
    var t = new THREE.CanvasTexture(c);
    t.minFilter = THREE.LinearFilter;
    if ('sRGBEncoding' in THREE) t.encoding = THREE.sRGBEncoding;
    return t;
  }

  /* ================================================================== *
   * build
   * ================================================================== */
  function build() {
    var narrow = NARROW.matches;
    var small = narrow || (window.innerWidth * window.innerHeight) < 620000;
    var BLADES_NEAR = small ? 70000 : 190000;
    var BLADES_FAR  = small ? 20000 :  60000;

    var q = /[?&]blades=(\\d+)/.exec(location.search);
    if (q) { BLADES_NEAR = +q[1]; BLADES_FAR = Math.round(+q[1] * 0.21); }

    renderer = new THREE.WebGLRenderer({ canvas: canvas, alpha: true, antialias: !small });
    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, small ? 1.6 : 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.30;
    if ('sRGBEncoding' in THREE) renderer.outputEncoding = THREE.sRGBEncoding;

    scene = new THREE.Scene();
    camera = new THREE.PerspectiveCamera(40, 1, 10, 8000);
    camera.position.set(0, 0, DIST);

    /* ---- near root ---- */
    var nearLimbs = buildNearRoot();
    var mainCount = nearLimbs.length;
    /* a scatter of stubby offshoots, so the tubes never read as hoses */
    var hp = new THREE.Vector3(), hn = new THREE.Vector3();
    var extra = [];
    for (var i = 0; i < 14; i++) {
      var r = rng();
      var src = nearLimbs[r < 0.62 ? 0 : (r < 0.82 ? 1 : 2)];
      var t = rand(0.04, 0.96), th = rng() * TAU;
      limbSurface(src, t, th, hp, hn);
      if (hn.y < -0.35) continue;
      limbFrame(src, t);
      var dir = hn.clone().multiplyScalar(rand(0.5, 1.2))
        .addScaledVector(_ft, rand(-0.6, 1.5))
        .addScaledVector(UP, rand(-0.5, 0.55)).normalize();
      hp.addScaledVector(hn, -src.rw(t) * 0.55);
      growOffshoot(extra, hp.clone(), dir, rand(0.28, 0.72), src.rw(t) * rand(0.22, 0.40), 0);
    }
    nearLimbs = nearLimbs.concat(extra);

    nearGroup = assembleRoot(nearLimbs, {
      aspect: ARCH.aspect, haze: 0.15, fog: 0.0, alpha: 1.0, order: 2,
      blades: BLADES_NEAR, ferns: small ? 26 : 46, flowers: small ? 120 : 260,
      fernSize: [0.22, 0.50], flowerSize: [0.055, 0.118], mainLimbs: mainCount, wire: true,
      mouse: uMouseNear, mouseR: 1.20
    });
    scene.add(nearGroup);
    if (!small) bf = buildButterfly(nearGroup, nearLimbs, nearGroup.userData.uni);

    /* ---- far ridge: same builder, pushed back and washed into the air.
            It dissolves before it reaches the cards (local x 0.5 \u2192 4.0) and
            into the floor light below it (lower 0/42% of its box) \u2014 the same
            two masks the artwork build carried in its own shader. ---- */
    farGroup = assembleRoot(buildFarRoot(), {
      aspect: FAR.aspect, haze: 0.16, fog: 0.26, alpha: 1.0, order: 0,
      /* dimmer air than the near root's: at 0.46 of the pale tone the ridge
         lost its silhouette entirely and read as a smudge on the background */
      hazeCol: [0.150, 0.164, 0.120], hazeLift: 0.92,
      blades: BLADES_FAR, ferns: small ? 8 : 16, flowers: small ? 40 : 90,
      fernSize: [0.26, 0.56], flowerSize: [0.034, 0.062],
      mask: [0.4, 3.4, 0.0, 0.42], wire: true,
      mouse: uMouseFar, mouseR: 1.4
    });
    scene.add(farGroup);

    buildAmbient();
    layout();
    window.addEventListener('resize', layout);
    clock = new THREE.Clock();

    /* Hold the pulse for a page nobody is looking at: a background tab gets
       no rAF, so the scan would never advance and the hero would still be
       empty when it was finally opened. */
    if (!REDUCED && !document.hidden) { uScanOn.value = 1; uScanR.value = 0; scanning = true; }

    /* Paint once here rather than waiting on the loop. A tab that is opened
       in the background never gets a rAF, so the hero would sit empty until
       it was looked at \u2014 and the first frame is also the one the entrance
       wipe is revealing. */
    renderFrame();
    startTick();
  }

  /* everything that needs no geometry \u2014 shadow, light pool, pollen */
  function buildAmbient() {
    var geo = new THREE.PlaneGeometry(1, 1, 1, 1);

    shadowMesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
      map: radialTexture(256, [[0, 'rgba(12,16,10,0.62)'], [0.45, 'rgba(12,16,10,0.26)'], [1, 'rgba(12,16,10,0)']]),
      transparent: true, depthWrite: false, depthTest: false
    }));
    shadowMesh.renderOrder = 1;
    shadowMesh.position.z = -70;
    scene.add(shadowMesh);

    glowMesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
      map: radialTexture(256, [[0, 'rgba(226,236,212,0.30)'], [0.42, 'rgba(214,226,200,0.10)'], [1, 'rgba(214,226,200,0)']]),
      transparent: true, depthWrite: false, depthTest: false,
      blending: THREE.AdditiveBlending
    }));
    glowMesh.renderOrder = -1;
    glowMesh.position.z = -320;
    scene.add(glowMesh);

    /* ---- drifting pollen --------------------------------------------
       Enough of it to read as air rather than as a handful of sprites, which
       means the drift has to leave the CPU: every mote is animated from
       uTime in the vertex shader, so the per-frame cost is one uniform write
       no matter how many there are. Sizes follow a power law \u2014 a few big
       soft ones near the lens, a great many specks behind them \u2014 and they
       depth-test against the moss so the ones behind the root are hidden. */
    var COUNT = (NARROW.matches || (window.innerWidth * window.innerHeight) < 620000) ? 1500 : 4200;
    var pos = new Float32Array(COUNT * 3);
    var seed = new Float32Array(COUNT * 4);
    for (var i = 0; i < COUNT; i++) {
      pos[i * 3]     = (Math.random() - 0.5) * 3400;
      pos[i * 3 + 1] = (Math.random() - 0.5) * 1500;
      pos[i * 3 + 2] = -380 + Math.random() * 1000;
      seed[i * 4]     = Math.random() * 6.283;                     /* phase   */
      seed[i * 4 + 1] = 0.25 + Math.random() * 0.9;                /* speed   */
      seed[i * 4 + 2] = 0.4 + Math.random() * 1.4;                 /* sway    */
      seed[i * 4 + 3] = 0.70 + 1.05 * Math.pow(Math.random(), 2.2); /* size    */
    }
    var pg = new THREE.BufferGeometry();
    pg.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    pg.setAttribute('seed', new THREE.BufferAttribute(seed, 4));

    poleTex = radialTexture(64, [[0, 'rgba(255,255,255,1)'], [0.35, 'rgba(236,244,224,0.5)'], [1, 'rgba(236,244,224,0)']]);
    motes = new THREE.Points(pg, new THREE.ShaderMaterial({
      uniforms: {
        uTime: uTime,
        uMap: { value: poleTex },
        uSize: { value: 9 },
        uScale: { value: 440 }
      },
      transparent: true, depthWrite: false, depthTest: true,
      blending: THREE.AdditiveBlending,
      vertexShader: [
        'attribute vec4 seed;',
        'uniform float uTime, uSize, uScale;',
        'varying float vFade;',
        'void main(){',
        '  float ph = seed.x, sp = seed.y, am = seed.z;',
        '  vec3 p = position;',
        '  p.x += sin(uTime * sp * 0.35 + ph) * 34.0 * am;',
        /* one long rise, wrapped \u2014 the band fade hides the wrap */
        '  float climb = mod(uTime * 11.0 * sp + ph * 60.0, 1500.0) - 750.0;',
        '  p.y += climb;',
        '  p.z += cos(uTime * sp * 0.28 + ph) * 24.0 * am;',
        '  vec4 mv = modelViewMatrix * vec4(p, 1.0);',
        '  gl_PointSize = uSize * seed.w * (uScale / max(-mv.z, 1.0));',
        '  float edge = 1.0 - abs(climb) / 750.0;',
        '  float twinkle = 0.55 + 0.45 * sin(uTime * (0.7 + sp * 1.6) + ph * 3.1);',
        '  vFade = clamp(edge * 3.0, 0.0, 1.0) * twinkle;',
        '  gl_Position = projectionMatrix * mv;',
        '}'
      ].join('\\n'),
      fragmentShader: [
        'precision highp float;',
        'uniform sampler2D uMap;',
        'varying float vFade;',
        'void main(){',
        '  vec4 t = texture2D(uMap, gl_PointCoord);',
        '  gl_FragColor = vec4(t.rgb, t.a * vFade * 0.52);',
        '}'
      ].join('\\n')
    }));
    motes.frustumCulled = false;
    motes.renderOrder = 6;
    scene.add(motes);

    buildCursorSpray();
  }

  /* \u2500\u2500 the trail the pointer lifts off the moss \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
     Emission is by DISTANCE rather than by time, and spread along the
     segment the pointer covered since the last frame: a fast sweep lays a
     trail instead of stacking a clump where the cursor happened to land,
     and a pointer that has stopped trickles instead of pumping.
     Each grain carries its own origin, velocity and birth stamp, so the CPU
     only writes when one is respawned out of the ring \u2014 the flight itself is
     integrated in the vertex shader, same as the ambient pollen. */
  var SPRAY_N = 620, SPRAY_LIFE = 1.6;
  var spray = null, sprayPos, sprayVel, sprayBirth, sprayRnd;
  var sprayHead = 0, sprayIdle = 0, sprayDirty = false;
  var sprayPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), -240);
  var sprayAt = new THREE.Vector3(), sprayLast = new THREE.Vector3(9999, 0, 0);
  var sprayStep = new THREE.Vector3();

  function buildCursorSpray() {
    if (REDUCED) return;
    sprayPos = new Float32Array(SPRAY_N * 3);
    sprayVel = new Float32Array(SPRAY_N * 3);
    sprayBirth = new Float32Array(SPRAY_N);
    sprayRnd = new Float32Array(SPRAY_N * 2);
    for (var i = 0; i < SPRAY_N; i++) sprayBirth[i] = -999;

    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(sprayPos, 3));
    g.setAttribute('aVel', new THREE.BufferAttribute(sprayVel, 3));
    g.setAttribute('aBirth', new THREE.BufferAttribute(sprayBirth, 1));
    g.setAttribute('aRnd', new THREE.BufferAttribute(sprayRnd, 2));

    spray = new THREE.Points(g, new THREE.ShaderMaterial({
      uniforms: {
        uTime: uTime, uMap: { value: poleTex },
        uSize: { value: 13 }, uScale: { value: 440 }, uLife: { value: SPRAY_LIFE }
      },
      transparent: true, depthWrite: false, depthTest: false,
      blending: THREE.AdditiveBlending,
      vertexShader: [
        'attribute vec3 aVel;',
        'attribute float aBirth;',
        'attribute vec2 aRnd;',
        'uniform float uTime, uSize, uScale, uLife;',
        'varying float vA;',
        'void main(){',
        '  float age = uTime - aBirth;',
        '  if (age < 0.0 || age > uLife) { vA = 0.0; gl_PointSize = 0.0; gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }',
        '  float u = age / uLife;',
        /* drag on the launch velocity, a slow lift, and a little wander */
        '  vec3 p = position + aVel * age * (1.0 - 0.34 * u)',
        '         + vec3(sin(aRnd.y * 6.28 + age * 2.6) * 22.0 * u, 46.0 * age, 0.0);',
        '  vec4 mv = modelViewMatrix * vec4(p, 1.0);',
        '  gl_PointSize = uSize * aRnd.x * (uScale / max(-mv.z, 1.0)) * (0.45 + 0.55 * (1.0 - u));',
        '  vA = smoothstep(0.0, 0.09, u) * (1.0 - smoothstep(0.40, 1.0, u));',
        '  gl_Position = projectionMatrix * mv;',
        '}'
      ].join('\\n'),
      fragmentShader: [
        'precision highp float;',
        'uniform sampler2D uMap;',
        'varying float vA;',
        'void main(){',
        '  vec4 t = texture2D(uMap, gl_PointCoord);',
        '  gl_FragColor = vec4(t.rgb, t.a * vA * 0.85);',
        '}'
      ].join('\\n')
    }));
    spray.frustumCulled = false;
    spray.renderOrder = 7;
    scene.add(spray);
  }

  function spawnSpray(p, boost) {
    var k = boost || 1;
    var i = sprayHead; sprayHead = (sprayHead + 1) % SPRAY_N;
    var o = i * 3;
    sprayPos[o]     = p.x + rand(-15, 15) * k;
    sprayPos[o + 1] = p.y + rand(-15, 15) * k;
    sprayPos[o + 2] = p.z + rand(-45, 45);
    sprayVel[o]     = rand(-38, 38) * k;
    sprayVel[o + 1] = (rand(2, 64) + 22 * (k - 1)) * k;
    sprayVel[o + 2] = rand(-26, 26) * k;
    sprayBirth[i]   = uTime.value;
    sprayRnd[i * 2]     = rand(0.50, 1.15);
    sprayRnd[i * 2 + 1] = rng();
    sprayDirty = true;
  }

  function flushSpray() {
    if (!spray || !sprayDirty) return;
    var at = spray.geometry.attributes;
    at.position.needsUpdate = at.aVel.needsUpdate = at.aBirth.needsUpdate = at.aRnd.needsUpdate = true;
    sprayDirty = false;
  }

  /* a pill that has been pressed throws a handful of pollen off itself \u2014
     the dock calls this, and it reuses the cursor emitter's pool */
  var burstNdc = { x: 0, y: 0 }, burstAtV = new THREE.Vector3();
  function burstAt(clientX, clientY) {
    if (!spray || !camera || REDUCED) return;
    var r = hero.getBoundingClientRect();
    burstNdc.x =  ((clientX - r.left) / r.width) * 2 - 1;
    burstNdc.y = -((clientY - r.top) / r.height) * 2 + 1;
    raycaster.setFromCamera(burstNdc, camera);
    if (!raycaster.ray.intersectPlane(sprayPlane, burstAtV)) return;
    for (var i = 0; i < 52; i++) spawnSpray(burstAtV, 2.5);
    flushSpray();
  }

  function emitSpray(dt) {
    if (!spray) return;
    if (!mouseLive || !raycaster.ray.intersectPlane(sprayPlane, sprayAt)) {
      sprayLast.x = 9999;                       /* re-entering should not lay a streak */
      return;
    }
    if (sprayLast.x > 9000) { sprayLast.copy(sprayAt); return; }

    var d = sprayAt.distanceTo(sprayLast);
    var n = Math.min(14, Math.floor(d / 7));
    for (var k = 1; k <= n; k++) {
      sprayStep.lerpVectors(sprayLast, sprayAt, k / n);
      spawnSpray(sprayStep);
    }
    if (n > 0) { sprayLast.copy(sprayAt); sprayIdle = 0; }
    else {
      sprayIdle += dt;
      if (sprayIdle > 0.055) { spawnSpray(sprayAt); sprayIdle = 0; }
    }

    flushSpray();
  }

  /* \u2500\u2500 butterfly \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
     Lifted from sakura-branch-hero: the wings are modelled to their real
     outline rather than alpha-cut from a texture, the scale pattern is baked
     once into (span, chord) rather than evaluated per fragment, and the
     flight is a cycle \u2014 cruise, approach, settle on a nominated perch with
     the wings held open, take off, round again.

     Two things are different here. The blue is a morpho's structural
     colour; this one is a swallowtail's yellow-green, so the face and edge
     hues are re-solved while the angle-dependence that makes it read as
     diffraction rather than paint is kept. And it lives inside nearGroup, so
     it is modelled in the root's own local units and rides the branch's
     placement, scale and parallax for free \u2014 including the perch, which is
     a point on the moss rather than on a blossom. */
  var bf = null;

  function wingGeometry(hind) {
    var NS = 30, NU = 10, pos = [], uv = [], idx = [], i, j;
    for (i = 0; i < NS; i++) {
      var sp = i / (NS - 1), lead, chord, span;
      if (!hind) {
        span  = 0.95;
        lead  = 0.10 + 0.32 * sp - 0.14 * sp * sp;
        chord = (0.56 + 0.46 * sp) * Math.pow(Math.max(0, 1 - Math.pow(sp, 2.6)), 0.55);
      } else {
        span  = 0.78;
        lead  = -0.06 - 0.26 * sp;
        chord = (0.54 + 0.48 * sp) * Math.pow(Math.max(0, 1 - Math.pow(sp, 2.2)), 0.55);
        chord *= 1 + 0.035 * Math.cos(sp * 22.0);
      }
      /* both pairs hinge on the thorax, so both roots have to be short or the
         wing floats beside the body instead of growing out of it */
      chord *= 0.26 + 0.74 * sstep(0, 0.32, sp);
      chord = Math.max(chord, 0.014);
      for (j = 0; j < NU; j++) {
        var u = j / (NU - 1);
        var cam = 0.030 * Math.sin(Math.PI * u) * (1 - 0.35 * sp);
        pos.push(0.018 + sp * span, cam, lead - chord * u);
        uv.push(sp, u);
      }
    }
    for (i = 0; i < NS - 1; i++) for (j = 0; j < NU - 1; j++) {
      var a = i * NU + j, b = a + NU;
      idx.push(a, b, a + 1, b, b + 1, a + 1);
    }
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
    g.setIndex(idx); g.computeVertexNormals();
    return g;
  }

  /* Baked once: the pattern is a pure function of (span, chord), so a dozen
     noise octaves per fragment per frame was paying over and over for a
     constant. R rows, G grain, B mottle, A shimmer. */
  function wingTexture() {
    var N = 256, cv = document.createElement('canvas'); cv.width = cv.height = N;
    var ctx = cv.getContext('2d'), img = ctx.createImageData(N, N), d = img.data;
    function h2(x, y) {
      var a = Math.sin(x * 127.1 + y * 311.7) * 43758.5453123;
      var b = Math.sin(x * 269.5 + y * 183.3) * 43758.5453123;
      return [(a - Math.floor(a)) * 2 - 1, (b - Math.floor(b)) * 2 - 1];
    }
    function gn(x, y) {
      var ix = Math.floor(x), iy = Math.floor(y), fx = x - ix, fy = y - iy;
      var ux = fx * fx * (3 - 2 * fx), uy = fy * fy * (3 - 2 * fy);
      var g00 = h2(ix, iy), g10 = h2(ix + 1, iy), g01 = h2(ix, iy + 1), g11 = h2(ix + 1, iy + 1);
      var a = g00[0] * fx + g00[1] * fy, b = g10[0] * (fx - 1) + g10[1] * fy;
      var c = g01[0] * fx + g01[1] * (fy - 1), e = g11[0] * (fx - 1) + g11[1] * (fy - 1);
      var top = a + (b - a) * ux, bot = c + (e - c) * ux;
      return top + (bot - top) * uy;
    }
    function fb(x, y, oct) {
      var sum = 0, amp = 0.5;
      for (var i = 0; i < oct; i++) {
        sum += amp * gn(x, y);
        var nx = 0.8 * x + 0.6 * y, ny = -0.6 * x + 0.8 * y;
        x = nx * 2.03; y = ny * 2.03; amp *= 0.5;
      }
      return sum;
    }
    var b255 = function (v) { return Math.max(0, Math.min(255, Math.round((v * 0.5 + 0.5) * 255))); };
    for (var yi = 0; yi < N; yi++) {
      var u = yi / (N - 1);
      for (var xi = 0; xi < N; xi++) {
        var sp = xi / (N - 1), o = (yi * N + xi) * 4;
        d[o]     = b255(fb(u * 70.0, sp * 16.0, 4));
        d[o + 1] = b255(gn(u * 165.0, sp * 52.0));
        d[o + 2] = b255(fb(sp * 4.5, u * 3.0, 3));
        d[o + 3] = b255(fb(sp * 6.5 + 4.0, u * 4.5, 3));
      }
    }
    ctx.putImageData(img, 0, 0);
    var t = new THREE.CanvasTexture(cv);
    t.flipY = false;
    t.wrapS = t.wrapT = THREE.ClampToEdgeWrapping;
    return t;
  }

  function wingMaterial(hind, bend, tex, uni) {
    return new THREE.ShaderMaterial({
      uniforms: {
        uKeyDir: uni.uKeyDir, uKeyCol: uni.uKeyCol, uAmbCol: uni.uAmbCol,
        uBend: bend, uHind: { value: hind ? 1 : 0 }, uTex: { value: tex }
      },
      side: THREE.DoubleSide,
      extensions: { derivatives: true },
      vertexShader: [
        'uniform float uBend;',
        'varying vec2 vUv; varying vec3 vN; varying vec3 vW;',
        'void main(){',
        '  vUv = uv;',
        /* the tip lags the stroke \u2014 a rigid flapping plate reads as paper */
        '  vec3 p = position;',
        '  float s = uv.x;',
        '  p.y += uBend * s * s;',
        '  p.z += uBend * s * s * (uv.y - 0.45) * 0.35;',
        '  vN = normalize(normalMatrix * normal);',
        '  vec4 wp = modelMatrix * vec4(p, 1.0);',
        '  vW = wp.xyz;',
        '  gl_Position = projectionMatrix * viewMatrix * wp;',
        '}'
      ].join('\\n'),
      fragmentShader: [
        'precision highp float;',
        'uniform vec3 uKeyDir, uKeyCol, uAmbCol;',
        'uniform float uHind;',
        'uniform sampler2D uTex;',
        'varying vec2 vUv; varying vec3 vN; varying vec3 vW;',
        'void main(){',
        '  float s = vUv.x, u = vUv.y;',
        '  vec3 N = normalize(vN);',
        '  if (!gl_FrontFacing) N = -N;',
        '  vec3 V = normalize(cameraPosition - vW);',
        /* Structural colour, not pigment: the hue swings with viewing angle \u2014
           a hot chartreuse square on, sliding to deep green at a glance.
           Albedo runs past 1 on purpose; it is HDR into ACES. */
        '  float facing = abs(dot(N, V));',
        /* Kept well under 1: on the cherry bough this ran HDR into ACES on
           purpose, but that scene was a sunset. Here the same numbers clip to
           cream and the green never arrives. */
        '  vec3 face = vec3(0.330, 0.560, 0.042);',
        '  vec3 edge = vec3(0.062, 0.190, 0.014);',
        '  vec3 wing = mix(edge, face, pow(facing, 0.65));',
        '  wing *= 0.62 + 0.72 * smoothstep(0.02, 0.46, s) * (1.0 - 0.34 * smoothstep(0.45, 1.0, u));',
        /* scales lie in overlapping rows running out from the base */
        '  vec4 tx = texture2D(uTex, vUv);',
        '  float rows = tx.r, grain = tx.g, mottle = tx.b, shim = tx.a;',
        '  wing *= 0.78 + 0.44 * mottle;',
        /* the hue swings green to yellow across the disc rather than merely
           brightening \u2014 that swing is what reads as diffraction */
        '  wing = mix(wing * vec3(0.46, 1.14, 0.30), wing * vec3(1.34, 1.06, 0.16), shim);',
        '  vec3 dark  = vec3(0.030, 0.026, 0.014);',
        '  vec3 cream = vec3(0.520, 0.500, 0.290);',
        '  vec3 amber = vec3(0.400, 0.270, 0.045);',
        /* the wide sooty border down the whole distal edge */
        '  float border = max(smoothstep(0.60, 0.74, s), smoothstep(0.78, 0.94, u));',
        '  vec3 c = mix(wing, dark, border);',
        /* veins: pale tan over the wing, lost inside the border */
        '  float vp = pow(u, 0.72) * 5.2 + s * 0.55 + (mottle - 0.5) * 0.22;',
        '  float vk = abs(fract(vp) - 0.5) * 2.0;',
        '  float aa = fwidth(vp) * 2.0 + 0.045;',
        '  float vw = 0.050 * (1.0 - 0.42 * s);',
        '  float vein = 1.0 - smoothstep(vw, vw + aa, vk);',
        '  c = mix(c, vec3(0.430, 0.400, 0.180), vein * 0.26 * (1.0 - border * 0.85));',
        /* lunules set into the border: cream on the forewing, amber behind */
        '  float lunBand = exp(-pow((border - 0.58) / 0.20, 2.0));',
        '  float edgeT = u * 0.62 + s * 0.58;',
        '  float lun = exp(-pow((fract(edgeT * 7.0) - 0.5) * 4.2, 2.0));',
        '  c = mix(c, mix(cream, amber, uHind), border * lunBand * lun * 0.90);',
        /* the big apical blazes, forewing only */
        '  float ap1 = exp(-pow((s - 0.86) / 0.085, 2.0)) * exp(-pow((u - 0.15) / 0.100, 2.0));',
        '  float ap2 = exp(-pow((s - 0.66) / 0.070, 2.0)) * exp(-pow((u - 0.07) / 0.075, 2.0));',
        '  c = mix(c, cream, (1.0 - uHind) * clamp(ap1 + ap2 * 0.75, 0.0, 1.0) * 0.42);',
        '  c *= 0.88 + 0.25 * rows;',
        '  c *= 0.935 + 0.13 * grain;',
        /* the very edge is a fringe of loose scales, paler and duller */
        '  float rim = clamp(smoothstep(0.93, 1.0, s) + smoothstep(0.955, 1.0, u), 0.0, 1.0);',
        '  c = mix(c, vec3(0.230, 0.215, 0.150), rim * 0.55);',
        '  float wrap = dot(N, uKeyDir) * 0.5 + 0.5;',
        '  vec3 lit = c * (uKeyCol * (0.34 + 1.05 * wrap) + uAmbCol * (0.5 + 0.5 * N.y) * 1.5);',
        /* light burning through the membrane from behind */
        '  float back = pow(max(dot(V, -uKeyDir), 0.0), 2.4);',
        '  lit += mix(vec3(0.86, 0.78, 0.20), vec3(0.34, 0.60, 0.12), border) * back * 0.42;',
        '  float sheen = pow(max(dot(reflect(-uKeyDir, N), V), 0.0), 26.0);',
        '  lit += vec3(0.86, 0.96, 0.52) * sheen * 0.34 * (1.0 - border);',
        '  gl_FragColor = vec4(lit, 1.0);',
        '  #include <tonemapping_fragment>',
        '  #include <encodings_fragment>',
        '}'
      ].join('\\n')
    });
  }

  function buildButterfly(host, limbs, uni) {
    var group = new THREE.Group();
    var bend = { fore: { value: 0 }, hind: { value: 0 } };
    var tex = wingTexture();
    var foreG = wingGeometry(false), hindG = wingGeometry(true);
    var foreM = wingMaterial(false, bend.fore, tex, uni), hindM = wingMaterial(true, bend.hind, tex, uni);

    var wR1 = new THREE.Mesh(foreG, foreM), wL1 = new THREE.Mesh(foreG, foreM);
    var wR2 = new THREE.Mesh(hindG, hindM), wL2 = new THREE.Mesh(hindG, hindM);
    wL1.scale.x = -1; wL2.scale.x = -1;
    wR1.position.set(0.012, 0.012, 0); wL1.position.copy(wR1.position);
    wR2.position.set(0.010, 0.000, 0); wL2.position.copy(wR2.position);
    group.add(wR1, wL1, wR2, wL2);

    /* ---- body ---- */
    var bodyMat = new THREE.ShaderMaterial({
      uniforms: { uKeyDir: uni.uKeyDir, uKeyCol: uni.uKeyCol, uAmbCol: uni.uAmbCol },
      vertexShader: [
        'varying vec3 vN; varying vec3 vW; varying vec3 vP;',
        'void main(){',
        '  vN = normalize(normalMatrix * normal); vP = position;',
        '  vec4 wp = modelMatrix * vec4(position, 1.0); vW = wp.xyz;',
        '  gl_Position = projectionMatrix * viewMatrix * wp;',
        '}'
      ].join('\\n'),
      fragmentShader: NOISE_GLSL + [
        'precision highp float;',
        'uniform vec3 uKeyDir, uKeyCol, uAmbCol;',
        'varying vec3 vN; varying vec3 vW; varying vec3 vP;',
        'void main(){',
        '  vec3 N = normalize(vN);',
        /* the thorax is furred, the abdomen banded */
        '  float band = 0.5 + 0.5 * sin(vP.z * 150.0);',
        '  float furry = smoothstep(-0.02, 0.10, vP.z);',
        '  vec3 base = mix(vec3(0.020, 0.019, 0.011), vec3(0.070, 0.064, 0.030), band * (1.0 - furry * 0.5));',
        '  float fleck = smoothstep(0.86, 0.99, sin(vP.z * 120.0) * sin(atan(vP.y, vP.x) * 7.0) * 0.5 + 0.5);',
        '  base = mix(base, vec3(0.46, 0.44, 0.24), fleck * 0.75);',
        '  float fur = gfbm(vec2(atan(vP.y, vP.x) * 9.0, vP.z * 70.0)) * 0.5 + 0.5;',
        '  base *= mix(1.0, 0.62 + 0.85 * fur, furry);',
        '  float d = max(dot(N, uKeyDir), 0.0);',
        '  vec3 col = base * (uKeyCol * (0.24 + 1.35 * d) + uAmbCol * (0.5 + 0.5 * N.y) * 1.8);',
        '  vec3 V = normalize(cameraPosition - vW);',
        '  col += uKeyCol * pow(max(dot(reflect(-uKeyDir, N), V), 0.0), 22.0) * 0.05;',
        '  gl_FragColor = vec4(col, 1.0);',
        '  #include <tonemapping_fragment>',
        '  #include <encodings_fragment>',
        '}'
      ].join('\\n')
    });

    (function () {
      var N = 30, R = 9, pos = [], idx = [], i, j;
      for (i = 0; i <= N; i++) {
        var a = i / N;
        var r = 0.014 + 0.026 * Math.sin(Math.PI * Math.pow(a, 0.80));
        r += 0.020 * Math.exp(-Math.pow((a - 0.70) / 0.14, 2));
        r += 0.013 * Math.exp(-Math.pow((a - 0.97) / 0.05, 2));
        var z = -0.55 + a * 0.72;
        for (j = 0; j <= R; j++) {
          var th = (j / R) * TAU;
          pos.push(Math.cos(th) * r, Math.sin(th) * r * 0.90, z);
        }
      }
      for (i = 0; i < N; i++) for (j = 0; j < R; j++) {
        var q = i * (R + 1) + j, w = q + R + 1;
        idx.push(q, w, q + 1, w, w + 1, q + 1);
      }
      var g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      g.setIndex(idx); g.computeVertexNormals();
      group.add(new THREE.Mesh(g, bodyMat));

      /* tegulae \u2014 the scaled shoulder pads that weld wing to thorax */
      [1, -1].forEach(function (sx) {
        var teg = new THREE.Mesh(new THREE.SphereGeometry(0.052, 12, 9), bodyMat);
        teg.position.set(0.030 * sx, 0.026, 0.020);
        teg.scale.set(1.15, 0.62, 1.5);
        teg.rotation.z = -0.35 * sx;
        group.add(teg);
      });

      /* antennae: thin, swept back, clubbed at the tip */
      var antMat = new THREE.MeshBasicMaterial({ color: 0x171208 });
      [1, -1].forEach(function (sx) {
        var c = new THREE.QuadraticBezierCurve3(
          new THREE.Vector3(0.010 * sx, 0.020, 0.150),
          new THREE.Vector3(0.062 * sx, 0.075, 0.300),
          new THREE.Vector3(0.105 * sx, 0.110, 0.430));
        group.add(new THREE.Mesh(new THREE.TubeGeometry(c, 12, 0.0042, 5, false), antMat));
        var club = new THREE.Mesh(new THREE.SphereGeometry(0.013, 8, 6), antMat);
        club.position.copy(c.getPointAt(1)); club.scale.z = 1.9;
        group.add(club);
      });
    })();

    /* a good deal smaller than it was on the cherry bough \u2014 that scene framed
       one branch, this one frames a whole root */
    group.scale.setScalar(0.205);
    group.renderOrder = 5;
    group.traverse(function (o) { o.frustumCulled = false; });
    host.add(group);

    /* ---- the perch: the top of the root's crest ---- */
    var L = limbs[0];
    var pp = new THREE.Vector3(), pn = new THREE.Vector3();
    var probeP = new THREE.Vector3(), probeN = new THREE.Vector3();
    var perchT = 0.29, bestY = -2, perchTh = 0;
    for (var i = 0; i < 64; i++) {
      var th = i / 64 * TAU;
      limbSurface(L, perchT, th, probeP, probeN);
      /* the top, but turned a little toward the lens so open wings show */
      var score = probeN.y + probeN.z * 0.42;
      if (score > bestY) { bestY = score; perchTh = th; pp.copy(probeP); pn.copy(probeN); }
    }
    var perch = pp.clone().addScaledVector(pn, 0.16);   /* clear of the moss pile */

    var st = {
      pos: perch.clone().add(new THREE.Vector3(-1.0, 1.1, 0.5)),
      vel: new THREE.Vector3(0.5, 0, 0),
      acc: new THREE.Vector3(),
      tgt: new THREE.Vector3(),
      mode: 'cruise', timer: 4.0, settle: 0, bank: 0, flap: 0
    };
    /* Local units, and the frame's left edge is at x = -4: a butterfly that
       wanders off the side or drops behind the moss may as well not be there,
       so the box is cut to the air directly above the crest. */
    var BOX = { x0: perch.x - 1.5, x1: perch.x + 2.1, y0: perch.y - 0.10, y1: perch.y + 1.35,
                z0: perch.z - 0.25, z1: perch.z + 0.95 };

    function pickTarget() {
      st.tgt.set(rand(BOX.x0 + 0.3, BOX.x1 - 0.3), rand(perch.y + 0.35, BOX.y1 - 0.2), rand(BOX.z0 + 0.2, BOX.z1 - 0.15));
    }
    pickTarget();

    /* display pose: dorsal surface square to the camera, head up \u2014 the whole
       point of the landing is that the open wings are seen */
    var landQ = new THREE.Quaternion();
    (function () {
      var camLocal = new THREE.Vector3(0, 0, DIST);
      host.worldToLocal(camLocal);
      var dorsal = camLocal.sub(perch).normalize();
      var fwd = new THREE.Vector3(0, 1, 0).addScaledVector(dorsal, -dorsal.y).normalize();
      var right = new THREE.Vector3().crossVectors(dorsal, fwd).normalize();
      landQ.setFromRotationMatrix(new THREE.Matrix4().makeBasis(right, dorsal, fwd));
      landQ.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), -0.10));
      landQ.multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), 0.14));
    })();

    /* The pointer is already carried into this group's local space every
       frame for the moss (uMouseNear), so the butterfly can read the same
       value \u2014 no extra raycast, and it is in the units it flies in. */
    var SPOOK_R = 0.62;                 /* about one and a half wingspans */
    var spook = 0, toM = new THREE.Vector3(), away = new THREE.Vector3(0, 1, 0);
    var tmp = new THREE.Vector3(), prevVel = new THREE.Vector3();
    var vRight = new THREE.Vector3(), vUp = new THREE.Vector3(), vFwd = new THREE.Vector3();
    var basis = new THREE.Matrix4(), flightQ = new THREE.Quaternion(), qTmp = new THREE.Quaternion();
    var AX_X = new THREE.Vector3(1, 0, 0), AX_Z = new THREE.Vector3(0, 0, 1);

    function contain(out) {
      var k = 2.2, m = 0.30;
      if (st.pos.x < BOX.x0 + m) out.x += k * (BOX.x0 + m - st.pos.x);
      if (st.pos.x > BOX.x1 - m) out.x -= k * (st.pos.x - BOX.x1 + m);
      if (st.pos.y < BOX.y0 + m) out.y += k * (BOX.y0 + m - st.pos.y);
      if (st.pos.y > BOX.y1 - m) out.y -= k * (st.pos.y - BOX.y1 + m);
      if (st.pos.z < BOX.z0 + m) out.z += k * (BOX.z0 + m - st.pos.z);
      if (st.pos.z > BOX.z1 - m) out.z -= k * (st.pos.z - BOX.z1 + m);
    }

    return function update(dt, t) {
      /* ---- how close is the cursor, and from where ----
         z is weighted down because the pointer is resolved on one plane and
         the butterfly is not on it; what matters is whether the cursor is
         over the animal on screen. */
      var m = uMouseNear.value, near = 0;
      if (m.x < 999) {
        toM.set(m.x - st.pos.x, m.y - st.pos.y, (m.z - st.pos.z) * 0.30);
        near = clamp01(1 - toM.length() / SPOOK_R);
        near *= near;
      }
      /* snaps on, lets go slowly \u2014 a startled insect does not calm instantly */
      spook += (near - spook) * (1 - Math.pow(near > spook ? 1e-7 : 0.22, dt));

      st.timer -= dt;
      if (st.mode === 'cruise') { if (st.timer <= 0) { st.mode = 'approach'; st.timer = 14; } }
      else if (st.mode === 'approach') { if (st.pos.distanceTo(perch) < 0.12 || st.timer <= 0) { st.mode = 'landed'; st.timer = rand(7.0, 10.0); } }
      else if (st.mode === 'landed') {
        /* the whole point of a perched insect is that it will not stay put */
        if (st.timer <= 0 || spook > 0.30) {
          st.mode = 'takeoff'; st.timer = 2.2;
          if (spook > 0.30) {
            /* leave in the opposite direction, not back across the cursor */
            away.copy(st.pos).sub(m).setZ(0).normalize();
            st.tgt.set(
              Math.min(BOX.x1 - 0.3, Math.max(BOX.x0 + 0.3, st.pos.x + away.x * 1.5)),
              Math.min(BOX.y1 - 0.2, perch.y + 0.9),
              Math.min(BOX.z1 - 0.15, Math.max(BOX.z0 + 0.2, st.pos.z + 0.4)));
          }
        }
      }
      else if (st.mode === 'takeoff') { if (st.timer <= 0) { st.mode = 'cruise'; st.timer = rand(5.0, 8.5); pickTarget(); } }

      var landing = st.mode === 'landed';
      st.settle += ((landing ? 1 : 0) - st.settle) * Math.min(1, dt * (landing ? 3.4 : 4.5));
      st.settle = Math.min(st.settle, 1 - spook);

      /* quick asymmetric stroke in flight, a slow display at rest */
      var beat = 8.6 + Math.sin(t * 0.7) * 0.9 + (0.34 - (8.6 + Math.sin(t * 0.7) * 0.9)) * st.settle;
      beat *= 1 + spook * 1.15;
      st.flap += dt * beat * TAU;
      var raw = Math.sin(st.flap);
      var shaped = (raw < 0 ? -1 : 1) * Math.pow(Math.abs(raw), 0.72);
      /* resting wings flare open as the cursor closes \u2014 the flick a butterfly
         gives just before it goes */
      var flyPhi = 20 + 48 * shaped, restPhi = 15 + 7 * shaped + spook * 30;
      var phi = (flyPhi + (restPhi - flyPhi) * st.settle) * Math.PI / 180;
      var flapVel = Math.cos(st.flap) * beat;

      wR1.rotation.z = phi;  wL1.rotation.z = -phi;
      wR2.rotation.z = phi * 0.95 - 0.03;
      wL2.rotation.z = -(phi * 0.95 - 0.03);
      bend.fore.value = -flapVel * 0.010;
      bend.hind.value = -flapVel * 0.013;

      var goal = st.mode === 'approach' ? perch : st.tgt;
      tmp.copy(goal).sub(st.pos);
      var dist = tmp.length();
      var speed = Math.min(1.5, 0.22 + dist * 1.1);
      var desired = tmp.normalize().multiplyScalar(speed);

      /* butterflies do not fly straight lines \u2014 but fade the wander out on
         final approach or it circles the perch forever without touching it */
      var wander = st.mode === 'approach' ? Math.min(1, dist * 0.8) : 1;
      desired.x += (Math.sin(t * 3.1) + 0.6 * Math.sin(t * 7.7 + 1.1)) * 0.20 * wander;
      desired.y += (Math.sin(t * 1.9 + 1.7) + 0.55 * Math.sin(t * 4.6)) * 0.40 * wander;
      desired.z += Math.sin(t * 2.7 + 3.4) * 0.24 * wander;
      if (st.mode === 'takeoff') { desired.y += 0.7; desired.z += 0.35; }
      /* and in the air it simply keeps its distance */
      if (spook > 0.002) {
        away.copy(st.pos).sub(m); away.z *= 0.30;
        if (away.lengthSq() > 1e-6) desired.addScaledVector(away.normalize(), spook * 2.3);
      }
      contain(desired);

      prevVel.copy(st.vel);
      st.vel.lerp(desired, 1 - Math.pow(0.03, dt));
      st.acc.copy(st.vel).sub(prevVel).divideScalar(Math.max(dt, 1e-4));
      st.pos.addScaledVector(st.vel, dt);
      if (st.settle > 0.001) {
        st.pos.lerp(perch, Math.min(1, dt * 6.0 * st.settle));
        st.vel.multiplyScalar(1 - Math.min(1, dt * 6.0 * st.settle));
      }

      vFwd.copy(st.vel);
      if (vFwd.lengthSq() < 1e-6) vFwd.set(0, 0, 1);
      vFwd.normalize();
      vRight.crossVectors(vFwd, UP);
      if (vRight.lengthSq() < 1e-6) vRight.set(1, 0, 0);
      vRight.normalize();
      vUp.crossVectors(vRight, vFwd).normalize();

      var lateral = vRight.dot(st.acc);
      st.bank += (Math.max(-1.15, Math.min(1.15, -lateral * 0.40)) - st.bank) * Math.min(1, dt * 5.0);

      basis.makeBasis(vRight, vUp, vFwd);
      flightQ.setFromRotationMatrix(basis);
      qTmp.setFromAxisAngle(AX_Z, st.bank + Math.sin(t * 0.83) * 0.30 + Math.sin(st.flap) * 0.05
                                  + Math.sin(t * 21.0) * spook * 0.16);
      flightQ.multiply(qTmp);
      qTmp.setFromAxisAngle(AX_X, Math.sin(st.flap) * 0.10 - 0.06);
      flightQ.multiply(qTmp);

      group.quaternion.copy(flightQ).slerp(landQ, st.settle);
      group.position.copy(st.pos);
      group.position.y += Math.sin(st.flap - 0.9) * 0.022 * (1 - st.settle);
    };
  }

  /* \u2500\u2500 size the scene in stage-pixel space \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
     At a 1600 px viewport one world unit is one CSS pixel at z = 0, so the
     root can be pinned to the same stage coordinates the copy is laid out
     on. Each root is modelled in its own 10-unit-wide box and scaled into
     place around a pinned landmark, exactly as the artwork was. */
  function layout() {
    W = hero.clientWidth; H = hero.clientHeight;
    renderer.setSize(W, H, false);
    camera.fov = 2 * Math.atan((H / 2) / DIST) * 180 / Math.PI;
    camera.aspect = W / H;
    camera.updateProjectionMatrix();

    var narrow = NARROW.matches;
    var s = stageEl.getBoundingClientRect();
    var h = hero.getBoundingClientRect();
    var u = s.width / (narrow ? 760 : 1600);
    var ox = s.left - h.left, oy = s.top - h.top;
    function wx(px) { return ox + px * u - W / 2; }
    function wy(py) { return H / 2 - (oy + py * u); }

    var A = narrow ? ARCH_N : ARCH, F = narrow ? FAR_N : FAR;
    /* wider than the stage: grow the roots to cover, pinned at a landmark */
    var cover = Math.max(1, W / s.width);

    function place(group, box, pinFx, pinFy, z) {
      var boxH = box.w / box.aspect;
      var scale = box.w * u * cover / BOXW;
      var k = (DIST - z) / DIST;                          /* undo the perspective shrink */
      var lx = (pinFx - 0.5) * BOXW, ly = (0.5 - pinFy) * (BOXW / box.aspect);
      var px = wx(box.left + pinFx * box.w), py = wy(box.top + pinFy * boxH);
      group.scale.setScalar(scale * k);
      group.position.set((px - lx * scale) * k, (py - ly * scale) * k, z);
      return { x: px, y: py, s: scale, boxH: boxH * u * cover };
    }

    /* the near root pins at the arch's apex; the far one at its crest */
    place(nearGroup, A, 0.732, 0.06, 0);
    place(farGroup,  F, 0.410, 0.32, F.z);

    var aw = A.w * u * cover, ah = aw / A.aspect;
    var cx = wx(A.left + 0.5 * A.w), cy = wy(A.top + 0.5 * (A.w / A.aspect));

    shadowMesh.scale.set(aw * 1.02, ah * 0.72, 1);
    shadowMesh.position.set(cx, cy - ah * 0.40, -70);

    glowMesh.scale.set(aw * 1.15, ah * 1.5, 1);
    glowMesh.position.set(cx - aw * 0.06, cy - ah * 0.18, -320);

    /* mimic three's own sizeAttenuation: gl_PointSize = size * (scale / -z)
       with scale = half the drawing buffer height */
    /* The pulse leaves from the low left of the frame, in front of the root,
       and has to reach the far corner \u2014 resolved here because both depend on
       where layout() has just put everything. */
    nearGroup.updateMatrixWorld(true);
    uScanO.value.set(-5.2, -0.9, 1.8);
    nearGroup.localToWorld(uScanO.value);
    scanMax = Math.hypot(W, H) * 1.3 + 900;

    motes.material.uniforms.uSize.value = Math.max(5, 9 * u);
    var half = renderer.getDrawingBufferSize(new THREE.Vector2()).y * 0.5;
    motes.material.uniforms.uScale.value = half;
    if (spray) {
      spray.material.uniforms.uScale.value = half;
      spray.material.uniforms.uSize.value = Math.max(7, 13 * u);
    }
  }

  /* \u2500\u2500 cursor \u2192 the plane the root stands in, in each root's own space \u2500\u2500 */
  var raycaster = new THREE.Raycaster();
  var crownPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
  var hitWorld = new THREE.Vector3();
  var tmpLocal = new THREE.Vector3();
  var mouseLive = false;

  function updateMouse(dt) {
    if (ndc.x > 2 || REDUCED) { mouseLive = false; }
    else {
      raycaster.setFromCamera(ndc, camera);
      mouseLive = !!raycaster.ray.intersectPlane(crownPlane, hitWorld);
    }
    [[nearGroup, uMouseNear], [farGroup, uMouseFar]].forEach(function (pair) {
      var g = pair[0], u2 = pair[1];
      if (!g) return;
      if (!mouseLive) { u2.value.set(9999, 9999, 9999); return; }
      tmpLocal.copy(hitWorld);
      g.worldToLocal(tmpLocal);
      if (u2.value.x > 999) u2.value.copy(tmpLocal);
      else u2.value.lerp(tmpLocal, 1 - Math.pow(0.0002, dt));
    });
  }

  /* \u2500\u2500 frame \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  var frames = 0;
  function renderFrame() {
    var dt = Math.min(clock.getDelta(), 0.05);
    if (!REDUCED) uTime.value += dt;

    camera.position.x = -smooth.x * 26;
    camera.position.y =  smooth.y * 16;
    camera.lookAt(camera.position.x * 0.42, camera.position.y * 0.42, 0);

    if (!REDUCED) {
      nearGroup.rotation.y = smooth.x * 0.055;
      nearGroup.rotation.x = smooth.y * 0.026;
      nearGroup.rotation.z = Math.sin(uTime.value * 0.22) * 0.0022;
      farGroup.rotation.y  = smooth.x * 0.030;
    }

    if (scanning) {
      scanT += dt / SCAN_DUR;
      var e = Math.min(1, scanT);
      uScanR.value = (1 - Math.pow(1 - e, 1.35)) * scanMax;
      /* the cage snaps on, rides the front, then burns off behind it */
      uWire.value = Math.min(1, e / 0.06) * (1 - sstep(0.72, 1.0, e));
      if (e >= 1) {
        scanning = false;
        uScanOn.value = 0;
        uWire.value = 0;
        for (var wi = 0; wi < wireMeshes.length; wi++) {
          var wm = wireMeshes[wi];
          if (wm.parent) wm.parent.remove(wm);
          wm.geometry.dispose(); wm.material.dispose();
        }
        wireMeshes.length = 0;
      }
    }

    if (bf && !REDUCED) bf(dt, uTime.value);

    updateMouse(dt);
    emitSpray(dt);

    renderer.render(scene, camera);
    if (++frames === 2) window.__ready = true;
  }

  /* \u2500\u2500 boot \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
  /* Kick the entrance off first. Growing the roots and compiling the
     shaders costs a few hundred ms of main thread, and doing that before
     the first wipe paints leaves the whole intro frozen on its opening
     frame \u2014 so hand the browser two frames to start animating. */
  ready();
  requestAnimationFrame(function () { requestAnimationFrame(function () {
    try { build(); }
    catch (err) { console.error(err); }
  }); });

  /* never leave the page invisible if something stalls */
  setTimeout(ready, 4000);
})();
<\/script>
</body>
</html>
`;var Pa=ce(Oe(),1);var sp=ce($t(),1);var sd=`<style data-threeui-sylva-sakura-sunset>
html,
body {
  background: #3c2c36 !important;
}

/* The backdrop carries one pool of light and nothing else \u2014 the same way the
   authored world reads a near-flat field corner to corner. No sun, no bands:
   the boughs and the blossom are the subject, and everything that models them
   comes from the light they sit in. */
.hero {
  background:
    radial-gradient(66% 56% at 26% 90%, rgba(255, 226, 212, 0.125) 0%, rgba(255, 226, 212, 0) 74%),
    radial-gradient(74% 64% at 92% 2%, rgba(18, 10, 18, 0.30) 0%, rgba(18, 10, 18, 0) 72%),
    #3c2c36 !important;
}

/* the floor of light the boughs hang over */
.hero::after {
  background:
    radial-gradient(76% 48% at 44% 118%, rgba(255, 218, 208, 0.28) 0%, rgba(255, 208, 200, 0.095) 44%, rgba(255, 202, 196, 0) 86%),
    linear-gradient(180deg, rgba(255, 214, 206, 0) 56%, rgba(255, 210, 202, 0.030) 78%, rgba(255, 214, 206, 0.078) 100%) !important;
}
</style>`,ud=`<style data-threeui-sylva-maple-autumn>
html,
body {
  background: #313a41 !important;
}

/* The same near-flat field the authored world uses, in the cold half of the
   year: a slate dusk with one pool of low light in it. Red leaf wants a cool
   ground behind it \u2014 on a warm field the whole frame goes to rust. */
.hero {
  background:
    radial-gradient(66% 56% at 26% 90%, rgba(255, 216, 176, 0.115) 0%, rgba(255, 216, 176, 0) 74%),
    radial-gradient(74% 64% at 92% 2%, rgba(10, 15, 20, 0.30) 0%, rgba(10, 15, 20, 0) 72%),
    #313a41 !important;
}

/* the floor of light the boughs hang over */
.hero::after {
  background:
    radial-gradient(76% 48% at 44% 118%, rgba(255, 206, 158, 0.24) 0%, rgba(255, 194, 150, 0.08) 44%, rgba(255, 188, 146, 0) 86%),
    linear-gradient(180deg, rgba(255, 206, 160, 0) 56%, rgba(255, 200, 156, 0.028) 78%, rgba(255, 206, 160, 0.070) 100%) !important;
}
</style>`,ll=`  /* Both tree variants grow the same world out of the authored root's own
     systems \u2014 swept limbs, bark, moss cushion, fur, ferns, scattered leaf or
     flower, wind, scan, pointer, butterfly \u2014 at the same close range. What
     changes between them is the leaf on the twigs, the palette they are lit
     in, and the field behind them; the wood underneath is one thing. */
  var BOUGH_SEGS   = [200, 44, 28, 18, 12];
  var BOUGH_RADIAL = [26, 16, 11, 8, 6];

  function boughLimb(pts, r0, r1, depth, flare) {
    var curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal', 0.5);
    var segs = BOUGH_SEGS[depth] || 12, radial = BOUGH_RADIAL[depth] || 6;
    var taper = flare || 1.0;
    /* every limb draws its last few percent down to a point: tubes are open
       ended, and a twig that simply stops shows a hollow cap in the air */
    var rw = function (t) {
      var r = r1 + (r0 - r1) * Math.pow(1 - t, taper);
      return r * knot(t, 0.030, 0.013) * (1 - 0.92 * sstep(0.90, 1.0, t));
    };
    /* The cushion sits ON the bough rather than around it, and thins with the
       wood: moss packs deep in the old crotches where rain sits and is gone
       by the time a twig is pencil thin. */
    var moss = function (t) { return rw(t) * (0.50 - 0.28 * t) * (depth === 0 ? 1.0 : 0.58); };
    var L = {
      curve: curve, segs: segs, radial: radial,
      rw: rw, moss: moss,
      blade: function (t) { return moss(t) * 0.145 + 0.016; },
      sink: 0
    };
    L.fr = transportFrames(curve, segs);
    L.len = curve.getLength();
    L.vScale = Math.max(10, L.len * 7.0);
    /* blossom breaks from young wood \u2014 the flower pass reads this so a bough
       does not come out flowering along its bark like fungus */
    L.young = depth >= 1 ? 1 : 0;
    return L;
  }

  function growBranch(list, start, dir, len, r0, depth, maxDepth) {
    var side = new THREE.Vector3().crossVectors(dir, UP);
    if (side.lengthSq() < 1e-6) side.set(1, 0, 0);
    side.normalize();
    var up = new THREE.Vector3().crossVectors(side, dir).normalize();
    /* Young cherry wood leaves the fork climbing and eases over as it thins,
       so the outer third of a spray hangs under its own blossom. */
    var lift = rand(0.12, 0.26) - depth * 0.05;
    var sway = rand(-0.30, 0.30);
    function node(f, u2, k) {
      return start.clone().addScaledVector(dir, len * f)
        .addScaledVector(up, len * u2).addScaledVector(side, len * k);
    }
    var L = boughLimb([
      start.clone(),
      node(0.34, lift * 0.46, sway * 0.34),
      node(0.69, lift * 0.98, sway * 0.82),
      node(1.00, lift * 0.72, sway)
    ], r0, r0 * 0.56, depth);
    list.push(L);
    if (depth >= maxDepth) return;

    var kids = depth <= 1 ? 3 : (rng() < 0.58 ? 3 : 2);
    for (var i = 0; i < kids; i++) {
      var tt = Math.min(0.99, 0.42 + (i / kids) * 0.58 + rand(-0.05, 0.05));
      var pt = L.curve.getPointAt(tt);
      var tan = L.curve.getTangentAt(tt).normalize();
      var ax = new THREE.Vector3().crossVectors(tan, UP);
      if (ax.lengthSq() < 1e-6) ax.set(1, 0, 0);
      ax.normalize().applyAxisAngle(tan, rng() * TAU);
      var kdir = tan.clone().applyAxisAngle(ax, rand(0.42, 1.00));
      /* every fork still reaches for the light, or a spray grows sideways
         into a bush instead of up into a branch */
      kdir.addScaledVector(UP, 0.16 - depth * 0.03).normalize();
      growBranch(list, pt, kdir, len * rand(0.56, 0.74),
                       r0 * 0.56 * rand(0.62, 0.84), depth + 1, maxDepth);
    }
  }

  /* Twigs are seated on the bough's own surface, the same way the authored
     build seats its stub offshoots \u2014 a spray that starts on the axis reads as
     a wire pushed through the branch once the cushion is on. */
  function sproutTwigs(list, host, count, len, r0, maxDepth) {
    var hp = new THREE.Vector3(), hn = new THREE.Vector3();
    for (var i = 0, guard = 0; i < count && guard < count * 40; guard++) {
      var t = clamp01(0.04 + 0.92 * ((i + rand(-0.45, 1.45)) / count));
      var th = rng() * TAU;
      limbSurface(host, t, th, hp, hn);
      if (hn.y < -0.32) continue;                   /* not off the underside */
      limbFrame(host, t);
      var dir = hn.clone().multiplyScalar(rand(0.75, 1.25))
        .addScaledVector(UP, rand(0.10, 0.52))
        .addScaledVector(_ft, rand(-0.95, 1.15)).normalize();
      hp.addScaledVector(hn, -host.rw(t) * 0.5);
      growBranch(list, hp.clone(), dir, len * rand(0.55, 1.42),
                       r0 * rand(0.68, 1.30), 1, maxDepth);
      i++;
    }
  }

  function buildBoughs() {
    var P = makeP(ARCH.aspect);
    var narrow = NARROW.matches;
    var limbs = [];
    /* the near bough: enters low left, crests at 40%, and runs out of frame
       on the right \u2014 the authored root's own path, read as cherry wood */
    var boughA = boughLimb(narrow ? [
      /* a tall frame wants the boughs raked across it, or the composition
         sits in a band with empty sky above and below */
      P(-0.26, 1.18, -0.42), P(0.00, 1.04, -0.16), P(0.26, 0.90, 0.08),
      P(0.52, 0.79, 0.20), P(0.78, 0.71, 0.10), P(1.12, 0.66, -0.30)
    ] : [
      P(-0.18, 1.05, -0.42), P(0.02, 0.99, -0.16), P(0.22, 0.92, 0.08),
      P(0.43, 0.88, 0.20), P(0.64, 0.87, 0.12), P(0.86, 0.90, -0.08),
      P(1.16, 0.96, -0.38)
    ], 0.42, 0.25, 0);
    /* the far bough: crosses the other way and sits back, so the two read as
       one tree seen from under it rather than as a pair of pipes */
    var boughB = boughLimb(narrow ? [
      P(-0.22, 0.74, -0.66), P(0.06, 0.60, -0.50), P(0.34, 0.46, -0.36),
      P(0.62, 0.33, -0.40), P(0.94, 0.22, -0.62)
    ] : [
      P(-0.16, 0.78, -0.66), P(0.10, 0.68, -0.50), P(0.36, 0.56, -0.36),
      P(0.62, 0.44, -0.40), P(0.86, 0.34, -0.54), P(1.14, 0.26, -0.76)
    ], 0.235, 0.13, 0);
    /* a limb climbing out of the top right corner, to close the frame */
    var boughC = boughLimb(narrow ? [
      P(1.08, 1.12, 0.16), P(0.94, 0.98, 0.24), P(0.82, 0.84, 0.20),
      P(0.74, 0.68, 0.06), P(0.70, 0.52, -0.14)
    ] : [
      P(0.30, 0.94, 0.16), P(0.37, 0.78, 0.24), P(0.47, 0.63, 0.20),
      P(0.60, 0.50, 0.06), P(0.76, 0.40, -0.14)
    ], 0.165, 0.078, 0);
    limbs.push(boughA, boughB, boughC);

    sproutTwigs(limbs, boughA, 15, 0.94, 0.070, 4);
    sproutTwigs(limbs, boughB, 10, 0.76, 0.050, 4);
    sproutTwigs(limbs, boughC, 8, 0.64, 0.039, 3);
    return limbs;
  }

  /* the far layer: a stand of small trees on the horizon, hazed back into the
     sky so the near boughs have depth behind them */
  function buildGrove() {
    var P = makeP(FAR.aspect);
    var limbs = [];
    var TREES = [[-0.04, 0.46, -0.5], [0.27, 0.60, 0.2], [0.56, 0.40, -0.3],
                 [0.82, 0.54, 0.1], [1.07, 0.44, -0.4]];
    for (var i = 0; i < TREES.length; i++) {
      var t = TREES[i], s = t[1];
      var base = P(t[0], 1.04 + (i % 2) * 0.03, t[2]);
      var top  = P(t[0] + (i - 2) * 0.008, 1.02 - 0.22 * s, t[2] + 0.1);
      var trunk = boughLimb([base, base.clone().lerp(top, 0.42),
                              base.clone().lerp(top, 0.76), top], 0.10 * s, 0.042 * s, 1);
      limbs.push(trunk);
      /* a stand reads as a stand only if no two crowns are the same width,
         and a crown reads as a crown only if its limbs leave the trunk at
         different heights \u2014 level spokes come out as a lollipop */
      var spread = 0.60 + (i % 3) * 0.17;
      for (var k = 0; k < 6; k++) {
        var a = (k / 6) * TAU + i * 0.7;
        var from = trunk.curve.getPointAt(0.72 + (k % 3) * 0.14);
        growBranch(limbs, from,
          new THREE.Vector3(Math.cos(a) * 0.82, 0.34 + (k % 2) * 0.40, Math.sin(a) * 0.46).normalize(),
          spread * 0.50 * s, 0.034 * s, 2, 3);
      }
    }
    return limbs;
  }`,ap=`  /* One palmate five-lobe silhouette, traced once and shared by the leaves on
     the twigs and the ones coming down: three lobes forward, two out to the
     sides, with a deep sinus cut between each pair. Half of it is authored and
     the other half is that half mirrored \u2014 a maple leaf is symmetric, and two
     hand-traced halves never quite are. */
  var MAPLE_HALF = [
    [0.00, -1.00], [0.21, -0.64], [0.52, -0.72], [0.45, -0.32],
    [0.84, -0.24], [0.50, 0.06], [0.70, 0.36], [0.31, 0.31],
    [0.15, 0.60], [0.05, 0.98]
  ];

  function mapleOutline(g, r) {
    var pts = [], i;
    for (i = 0; i < MAPLE_HALF.length; i++) pts.push([MAPLE_HALF[i][0] * r, MAPLE_HALF[i][1] * r]);
    for (i = MAPLE_HALF.length - 1; i >= 0; i--) pts.push([-MAPLE_HALF[i][0] * r, MAPLE_HALF[i][1] * r]);
    /* Drawn as a closed quadratic spline rather than as segments: straight
       lines between the lobe tips and the sinuses come out as a paper star at
       the size these are seen, and a maple lobe is a curve on both sides. */
    var n = pts.length;
    function mid(a, b) { return [(a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5]; }
    var m = mid(pts[n - 1], pts[0]);
    g.beginPath();
    g.moveTo(m[0], m[1]);
    for (i = 0; i < n; i++) {
      var cur = pts[i], nxt = pts[(i + 1) % n];
      m = mid(cur, nxt);
      g.quadraticCurveTo(cur[0], cur[1], m[0], m[1]);
    }
    g.closePath();
  }`,ip=`  /* one petal, for the fall through the frame and for the trail the pointer
     lifts off the cushion */
  function fallingSprite() {
    var c = document.createElement('canvas'); c.width = c.height = 64;
    var g = c.getContext('2d');
    g.translate(32, 32);
    var r = 27;
    var grad = g.createLinearGradient(0, -r, 0, r);
    grad.addColorStop(0, 'rgba(255, 248, 246, 0.98)');
    grad.addColorStop(0.55, 'rgba(255, 198, 212, 0.94)');
    grad.addColorStop(1, 'rgba(244, 146, 172, 0.74)');
    g.fillStyle = grad;
    /* narrow at the stem, broad at the shoulders, notched at the tip \u2014 the
       notch is the whole silhouette of a cherry petal */
    g.beginPath();
    g.moveTo(0, r);
    g.bezierCurveTo(-r * 0.70, r * 0.42, -r * 0.82, -r * 0.44, -r * 0.30, -r * 0.92);
    g.quadraticCurveTo(0, -r * 0.62, r * 0.30, -r * 0.92);
    g.bezierCurveTo(r * 0.82, -r * 0.44, r * 0.70, r * 0.42, 0, r);
    g.fill();
    var t = new THREE.CanvasTexture(c);
    t.minFilter = THREE.LinearFilter;
    if ('sRGBEncoding' in THREE) t.encoding = THREE.sRGBEncoding;
    return t;
  }`,op=`  /* one maple leaf, for the fall through the frame and for the trail the
     pointer lifts off the cushion */
  function fallingSprite() {
    var c = document.createElement('canvas'); c.width = c.height = 96;
    var g = c.getContext('2d');
    g.translate(48, 50);
    var r = 42;
    var grad = g.createLinearGradient(0, -r, 0, r);
    grad.addColorStop(0, 'rgba(255, 206, 122, 0.98)');
    grad.addColorStop(0.48, 'rgba(226, 104, 52, 0.96)');
    grad.addColorStop(1, 'rgba(158, 46, 38, 0.88)');
    g.fillStyle = grad;
    mapleOutline(g, r);
    g.fill();
    var t = new THREE.CanvasTexture(c);
    t.minFilter = THREE.LinearFilter;
    if ('sRGBEncoding' in THREE) t.encoding = THREE.sRGBEncoding;
    return t;
  }`,cd=`<style data-threeui-sylva-sequoia-mist>
html,
body {
  background: #5f6d63 !important;
}

/* A redwood grove is read through its air, not against a night sky: the field
   is a pale drift of fog with the light coming down through it, and the same
   haze the scene mixes its distance into. Everything reads as a silhouette
   standing in front of the fog rather than a lit thing on a dark ground. */
.hero {
  background:
    radial-gradient(70% 60% at 34% 12%, rgba(226, 234, 220, 0.30) 0%, rgba(226, 234, 220, 0) 72%),
    radial-gradient(76% 66% at 88% 96%, rgba(30, 40, 32, 0.26) 0%, rgba(30, 40, 32, 0) 74%),
    #5f6d63 !important;
}

/* the shaft of light the boughs hang in */
.hero::after {
  background:
    radial-gradient(60% 74% at 40% -12%, rgba(238, 244, 230, 0.30) 0%, rgba(232, 240, 224, 0.09) 46%, rgba(228, 238, 220, 0) 84%),
    linear-gradient(180deg, rgba(226, 236, 218, 0.055) 0%, rgba(226, 236, 218, 0) 46%, rgba(24, 32, 26, 0.055) 100%) !important;
}
</style>`,lp=`  /* one shed sprig, for the drift through the frame and for the trail the
     pointer lifts off the cushion \u2014 the same ordered needle rank as the crown,
     at the size one sprig is actually read at */
  function fallingSprite() {
    var c = document.createElement('canvas'); c.width = c.height = 96;
    var g = c.getContext('2d');
    g.translate(48, 48);
    var grad = g.createLinearGradient(0, 36, 0, -36);
    grad.addColorStop(0, 'rgb(74, 96, 56)');
    grad.addColorStop(1, 'rgb(158, 182, 112)');
    g.strokeStyle = 'rgb(84, 78, 52)';
    g.lineCap = 'round';
    g.lineWidth = 2.4;
    g.beginPath(); g.moveTo(0, 34); g.lineTo(0, -30); g.stroke();
    for (var i = 0; i < 11; i++) {
      var f = i / 10, y = 32 - 60 * f;
      var taper = 1 - 0.7 * Math.max(0, (f - 0.74) / 0.26);
      var len = 26 * taper, wid = 2.8 * taper;
      for (var sgn = -1; sgn <= 1; sgn += 2) {
        g.save();
        g.translate(0, y);
        g.rotate(sgn * 0.86);
        g.beginPath();
        g.moveTo(-wid * 0.5, 0);
        g.quadraticCurveTo(-wid * 0.24, -len * 0.6, 0, -len);
        g.quadraticCurveTo(wid * 0.24, -len * 0.6, wid * 0.5, 0);
        g.closePath();
        g.fillStyle = grad;
        g.fill();
        g.restore();
      }
    }
    var t = new THREE.CanvasTexture(c);
    t.minFilter = THREE.LinearFilter;
    if ('sRGBEncoding' in THREE) t.encoding = THREE.sRGBEncoding;
    return t;
  }`;function sl(e,t,n,r){if(!e.includes(t))throw new Error(`Sylva ${r} adapter no longer matches the canonical scene.`);return e.replace(t,n)}function dd(e){return[["  function build() {",`${ll}

${ip}

  function build() {`,"bough builders"],["var nearLimbs = buildNearRoot();","var nearLimbs = buildBoughs();","near bough composition"],["assembleRoot(buildFarRoot(), {","assembleRoot(buildGrove(), {","far grove composition"],["var BLADES_NEAR = small ? 70000 : 190000;","var BLADES_NEAR = small ? 140000 : 260000;","deep near cushion"],["var BLADES_FAR  = small ? 20000 :  60000;","var BLADES_FAR  = small ? 9000 :  22000;","thin far cushion"],["for (var i = 0; i < 14; i++) {","for (var i = 0; i < 0; i++) {","no stub offshoots"],["        if (limbSurface(Lw, tt, tth, p, n) < 0.45 || p.x > plantMaxX) continue;",`        limbSurface(Lw, tt, tth, p, n);
        if (p.x > plantMaxX) continue;`,"blossom on every face of a twig"],["      var Lw = host[Math.floor(rng() * host.length)];",`      var Lw = host[Math.floor(rng() * host.length)];
      /* blossom breaks from young wood; a flowering trunk reads as fungus */
      if (!Lw.young && rng() < 0.93) continue;`,"blossom on young wood"],["      for (var c2 = 0; c2 < 9 && k < opt.flowers; c2++) {","      for (var c2 = 0; c2 < 5 && k < opt.flowers; c2++) {","flowers spaced along one spray"],[`        var tt = clamp01(t0 + rand(-0.008, 0.008));
        var tth = th0 + rand(-0.24, 0.24);`,`        var tt = clamp01(t0 + rand(-0.50, 0.50));
        var tth = th0 + rand(-3.14, 3.14);`,"blossom strung along the twig instead of balled at one point"],["p.addScaledVector(n, rand(0.02, 0.16));","p.addScaledVector(n, rand(0.01, 0.07));","blossom seated on thin wood"],[`    var c = document.createElement('canvas'); c.width = c.height = 64;
    var g = c.getContext('2d');
    var FLORETS = [
      [32, 22, 7.4], [22, 33, 6.0], [42, 33, 6.2], [27, 44, 5.0],
      [39, 45, 5.4], [32, 33, 4.4], [46, 22, 4.2], [18, 22, 4.0]
    ];
    for (var f = 0; f < FLORETS.length; f++) {
      var cx = FLORETS[f][0], cy = FLORETS[f][1], r = FLORETS[f][2];
      g.save(); g.translate(cx, cy); g.rotate(f * 1.31);
      for (var p = 0; p < 5; p++) {
        g.save(); g.rotate((p / 5) * TAU);
        g.fillStyle = 'rgba(255,255,251,' + (0.72 + 0.28 * (r / 7.4)) + ')';
        g.beginPath(); g.ellipse(0, -r * 0.55, r * 0.34, r * 0.55, 0, 0, TAU); g.fill();
        g.restore();
      }
      g.fillStyle = '#f0e7bd';
      g.beginPath(); g.arc(0, 0, r * 0.24, 0, TAU); g.fill();
      g.restore();
    }`,`    var c = document.createElement('canvas'); c.width = c.height = 128;
    var g = c.getContext('2d');
    /* One instance is a spray of open blossom, drawn at twice the original
       resolution because a cherry petal is read by the notch in its tip and
       at 64 px that notch is gone by the second mip. */
    var BLOOMS = [[64, 64, 56, 0.0]];
    function petal(r) {
      g.beginPath();
      g.moveTo(0, 0);
      g.bezierCurveTo(-r * 0.52, -r * 0.30, -r * 0.46, -r * 0.86, -r * 0.16, -r);
      g.quadraticCurveTo(0, -r * 0.78, r * 0.16, -r);
      g.bezierCurveTo(r * 0.46, -r * 0.86, r * 0.52, -r * 0.30, 0, 0);
      g.fill();
    }
    for (var f = 0; f < BLOOMS.length; f++) {
      var cx = BLOOMS[f][0], cy = BLOOMS[f][1], r = BLOOMS[f][2];
      g.save(); g.translate(cx, cy); g.rotate(BLOOMS[f][3]);
      /* deeper pink at the throat, near-white at the rim \u2014 the gradient is
         what keeps a five-petal sprite from reading as a paper cut-out */
      var grad = g.createRadialGradient(0, 0, r * 0.10, 0, 0, r);
      grad.addColorStop(0, 'rgba(250, 188, 202, 0.98)');
      grad.addColorStop(0.45, 'rgba(255, 220, 228, 0.96)');
      grad.addColorStop(1, 'rgba(255, 248, 250, 0.94)');
      g.fillStyle = grad;
      for (var p = 0; p < 5; p++) { g.save(); g.rotate((p / 5) * TAU); petal(r * 0.96); g.restore(); }
      g.fillStyle = 'rgba(232, 158, 176, 0.62)';
      g.beginPath(); g.arc(0, 0, r * 0.17, 0, TAU); g.fill();
      /* stamens: filaments out of the throat, each tipped with an anther \u2014
         at this range a plain dot in the middle reads as a printed sticker */
      g.strokeStyle = 'rgba(252, 206, 176, 0.80)';
      g.lineWidth = Math.max(1, r * 0.030);
      for (p = 0; p < 11; p++) {
        var sa = (p / 11) * TAU + f, sr = r * (0.30 + 0.16 * ((p % 3) / 2));
        g.beginPath(); g.moveTo(0, 0); g.lineTo(Math.cos(sa) * sr, Math.sin(sa) * sr); g.stroke();
        g.fillStyle = 'rgba(255, 226, 164, 0.96)';
        g.beginPath(); g.arc(Math.cos(sa) * sr, Math.sin(sa) * sr, r * 0.055, 0, TAU); g.fill();
      }
      g.restore();
    }`,"Sakura blossom sprite"],[`        'attribute vec3 iPos;',
        'attribute vec2 iRnd;',
        'uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',
        'void main(){',
        '  vUv = uv;',`,`        'attribute vec3 iPos;',
        'attribute vec2 iRnd;',
        'uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',
        'varying float vRnd;',
        'void main(){',
        '  vUv = uv;',
        '  vRnd = iRnd.y;',`,"per-spray variation carried to the blossom"],[`'uniform sampler2D uMap;',
        'uniform float uAlpha; uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',`,`'uniform sampler2D uMap;',
        'uniform float uAlpha; uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',
        'varying float vRnd;',`,"per-spray variation read by the blossom"],[`        '  vec4 t = texture2D(uMap, vUv);',
        '  if (t.a < 0.14) discard;',`,`        /* every instance turned the same way reads as printed wallpaper */
        '  float fc = cos(vRnd * 6.2832), fs = sin(vRnd * 6.2832);',
        '  vec2 fuv = vUv - 0.5;',
        '  fuv = vec2(fuv.x * fc - fuv.y * fs, fuv.x * fs + fuv.y * fc) + 0.5;',
        '  vec4 t = texture2D(uMap, fuv);',
        '  if (t.a < 0.14) discard;',`,"each blossom faces its own way"],["'  vec3 col = t.rgb * t.rgb * (uKeyCol * 0.62 + uAmbCol * 0.9);',",`/* Sprays differ: some open white in the light, some still deep pink in
           the shade of the crown. One tone for all of them is what makes a
           canopy read as cotton wool. */
        '  vec3 tone = mix(vec3(1.04, 0.86, 0.91), vec3(1.00, 1.00, 1.02), vRnd);',
        '  vec3 col = t.rgb * t.rgb * tone * (uKeyCol * 0.54 + uAmbCol * 1.10) * (0.66 + 0.56 * vRnd);',
        /* petals are thin enough to pass the low sun straight through */
        '  vec3 V = normalize(cameraPosition - vW);',
        '  col += uKeyCol * pow(max(dot(V, -uKeyDir), 0.0), 3.0) * 0.20 * t.a * (0.5 + 0.9 * vRnd);',`,"blossom lit through by the low sun"],["    return c * sstep(0.10, 0.50, patch);","    return c * sstep(0.30, 0.72, patch);","patchy cushion, bare bark between"],["'  vec3 silver = mix(vec3(0.020, 0.019, 0.018), vec3(0.290, 0.283, 0.264), grain);',","'  vec3 silver = mix(vec3(0.030, 0.023, 0.024), vec3(0.310, 0.266, 0.258), grain);',","cherry bark greys"],["'  vec3 umber  = mix(vec3(0.024, 0.019, 0.016), vec3(0.175, 0.140, 0.110), grain);',","'  vec3 umber  = mix(vec3(0.038, 0.022, 0.018), vec3(0.262, 0.158, 0.120), grain);',","cherry bark reds"],["'  wood *= 1.0 - 0.70 * crack;',",`'  wood *= 1.0 - 0.70 * crack;',
        /* cherry is read by its lenticels: short dark dashes banding ACROSS
           the limb, where every other feature in this bark runs along it */
        '  float lent = smoothstep(0.58, 0.96, gfbm(vec2(uv.x * 2.4, uv.y * 24.0)) * 0.5 + 0.5);',
        '  wood *= 1.0 - 0.44 * lent;',`,"cherry lenticels"],["'  vec3 moss = mix(vec3(0.0204, 0.0311, 0.0050), vec3(0.0914, 0.1392, 0.0227), mo);',","'  vec3 moss = mix(vec3(0.0340, 0.0282, 0.0112), vec3(0.1360, 0.1140, 0.0372), mo);',","ochre cushion on the bark shell"],["'  col = mix(col, vec3(0.162, 0.176, 0.132), lich * 0.78);',","'  col = mix(col, vec3(0.198, 0.176, 0.156), lich * 0.70);',","lichen crust palette"],[`'  vec3 deep = vec3(0.0126, 0.0192, 0.0031);',
        '  vec3 mid  = vec3(0.0488, 0.0744, 0.0121);',
        '  vec3 tip  = vec3(0.1222, 0.1860, 0.0304);',
        '  vec3 tipHi = vec3(0.2600, 0.3900, 0.0640);',`,`'  vec3 deep = vec3(0.0300, 0.0248, 0.0100);',
        '  vec3 mid  = vec3(0.1150, 0.0960, 0.0320);',
        '  vec3 tip  = vec3(0.2520, 0.2160, 0.0680);',
        '  vec3 tipHi = vec3(0.5100, 0.4420, 0.1420);',`,"ochre moss in the fur"],["'  vec3 base = mix(vec3(0.0270, 0.0450, 0.0099), vec3(0.0690, 0.1150, 0.0253), vTint);',","'  vec3 base = mix(vec3(0.0380, 0.0250, 0.0100), vec3(0.0980, 0.0640, 0.0220), vTint);',","ochre fronds"],["      var Lf = host[Math.floor(rng() * host.length)];",`      /* fronds seat on the old boughs only: one on a twig reads as a
         frond hanging in mid-air */
      var Lf = host[Math.floor(rng() * Math.min(host.length, 3))];`,"fronds on the boughs"],[`  var KEY  = new THREE.Vector3(-0.30, 0.92, 0.28).normalize();
  var FILL = new THREE.Vector3( 0.12, -0.86, 0.50).normalize();`,`  /* dusk after the sun has gone: a soft high key that still models the
     cushion, and a cool bounce off the air on the near side */
  var KEY  = new THREE.Vector3(-0.26, 0.90,  0.34).normalize();
  var FILL = new THREE.Vector3( 0.16, -0.82,  0.52).normalize();`,"soft dusk directions"],["uKeyCol:  { value: new THREE.Color(1.14, 1.06, 0.88) },","uKeyCol:  { value: new THREE.Color(1.28, 1.03, 0.90) },","sunset key light"],["uFillCol: { value: new THREE.Color(0.78, 0.78, 0.62) },","uFillCol: { value: new THREE.Color(0.74, 0.60, 0.70) },","dusk sky fill"],["uAmbCol:  { value: new THREE.Color(0.086, 0.090, 0.080) },","uAmbCol:  { value: new THREE.Color(0.150, 0.112, 0.132) },","dusk ambient"],["uHazeCol: { value: new THREE.Color(0.176, 0.195, 0.145) },","uHazeCol: { value: new THREE.Color(0.300, 0.216, 0.240) },","sunset haze"],["renderer.toneMappingExposure = 1.30;","renderer.toneMappingExposure = 1.32;","dusk exposure"],["aspect: ARCH.aspect, haze: 0.15, fog: 0.0, alpha: 1.0, order: 2,","aspect: ARCH.aspect, haze: 0.17, fog: 0.0, alpha: 1.0, order: 2,","near air"],[`      blades: BLADES_NEAR, ferns: small ? 26 : 46, flowers: small ? 120 : 260,
      fernSize: [0.22, 0.50], flowerSize: [0.055, 0.118], mainLimbs: mainCount, wire: true,`,`      blades: BLADES_NEAR, ferns: small ? 14 : 26, flowers: small ? 4800 : 7800,
      fernSize: [0.16, 0.36], flowerSize: [0.170, 0.300], mainLimbs: 0, wire: true,`,"near tree in full blossom"],["aspect: FAR.aspect, haze: 0.16, fog: 0.26, alpha: 1.0, order: 0,","aspect: FAR.aspect, haze: 0.26, fog: 0.82, alpha: 1.0, order: 0,","far grove pushed into the air"],["hazeCol: [0.150, 0.164, 0.120], hazeLift: 0.92,","hazeCol: [0.300, 0.220, 0.246], hazeLift: 0.94,","far sunset haze"],[`      blades: BLADES_FAR, ferns: small ? 8 : 16, flowers: small ? 40 : 90,
      fernSize: [0.26, 0.56], flowerSize: [0.034, 0.062],
      mask: [0.4, 3.4, 0.0, 0.42], wire: true,`,`      blades: BLADES_FAR, ferns: 0, flowers: small ? 3000 : 7000,
      fernSize: [0.26, 0.56], flowerSize: [0.055, 0.105],
      mask: [4.6, 5.6, -0.14, 0.20], wire: true,`,"far grove in blossom"],[`  var ARCH   = { w: 1900, left: -180, top: 306, aspect: 2800 / 1377 };
  var ARCH_N = { w: 1120, left: -290, top: 555, aspect: 2800 / 1377 };
  var FAR    = { w: 1150, left:  -40, top: 320, aspect: 1600 /  757, z: -260 };
  var FAR_N  = { w:  780, left: -110, top: 600, aspect: 1600 /  757, z: -260 };`,`  /* framed on the boughs at the authored close range: the frame is
     branch and blossom, with the grove sitting low behind it */
  var ARCH   = { w: 1500, left:   50, top:  262, aspect: 2800 / 1377 };
  var ARCH_N = { w: 1680, left:  -99, top:  500, aspect: 2800 / 1377 };
  var FAR    = { w: 1240, left:  180, top:  392, aspect: 1600 /  757, z: -260 };
  var FAR_N  = { w:  920, left:  280, top:  902, aspect: 1600 /  757, z: -260 };`,"framing boxes"],["place(nearGroup, A, 0.732, 0.06, 0);","place(nearGroup, A, 0.500, 0.500, 0);","tree framing"],["place(farGroup,  F, 0.410, 0.32, F.z);","place(farGroup,  F, 0.500, 0.500, F.z);","grove framing"],["map: radialTexture(256, [[0, 'rgba(12,16,10,0.62)'], [0.45, 'rgba(12,16,10,0.26)'], [1, 'rgba(12,16,10,0)']]),","map: radialTexture(256, [[0, 'rgba(28,12,26,0.55)'], [0.45, 'rgba(28,12,26,0.22)'], [1, 'rgba(28,12,26,0)']]),","dusk ground shadow"],[`    shadowMesh.scale.set(aw * 1.02, ah * 0.72, 1);
    shadowMesh.position.set(cx, cy - ah * 0.40, -70);`,`    shadowMesh.scale.set(aw * 2.10, ah * 0.44, 1);
    shadowMesh.position.set(cx, cy - ah * 0.98, -70);`,"ground haze instead of a disc on the sky"],[`    glowMesh.scale.set(aw * 1.15, ah * 1.5, 1);
    glowMesh.position.set(cx - aw * 0.06, cy - ah * 0.18, -320);`,`    /* the sky already carries the sun and its bloom; a second glow plane
       in front of it only draws its own edge across the horizon */
    glowMesh.visible = false;`,"sun bloom left to the sky"],["'  lit += col * uAmbCol * pow(1.0 - max(dot(N, V), 0.0), 4.0) * 0.85;',","'  lit += (col * uAmbCol * 0.85 + uKeyCol * 0.030) * pow(1.0 - max(dot(N, V), 0.0), 4.0);',","sun rim along the bark"],[`'  vec3 face = vec3(0.330, 0.560, 0.042);',
        '  vec3 edge = vec3(0.062, 0.190, 0.014);',`,`'  vec3 face = vec3(0.620, 0.330, 0.090);',
        '  vec3 edge = vec3(0.150, 0.058, 0.030);',`,"amber swallowtail"],["'  wing = mix(wing * vec3(0.46, 1.14, 0.30), wing * vec3(1.34, 1.06, 0.16), shim);',","'  wing = mix(wing * vec3(1.18, 0.72, 0.34), wing * vec3(1.42, 0.98, 0.28), shim);',","amber diffraction"],["'  lit += mix(vec3(0.86, 0.78, 0.20), vec3(0.34, 0.60, 0.12), border) * back * 0.42;',","'  lit += mix(vec3(0.98, 0.66, 0.26), vec3(0.50, 0.22, 0.12), border) * back * 0.42;',","sun through the wing"],["poleTex = radialTexture(64, [[0, 'rgba(255,255,255,1)'], [0.35, 'rgba(236,244,224,0.5)'], [1, 'rgba(236,244,224,0)']]);","poleTex = fallingSprite();","petal sprite"],["var COUNT = (NARROW.matches || (window.innerWidth * window.innerHeight) < 620000) ? 1500 : 4200;","var COUNT = (NARROW.matches || (window.innerWidth * window.innerHeight) < 620000) ? 220 : 520;","petal count"],[`      transparent: true, depthWrite: false, depthTest: true,
      blending: THREE.AdditiveBlending,`,`      transparent: true, depthWrite: false, depthTest: true,
      blending: THREE.NormalBlending,`,"petals blend as petals, not as sparks"],[`        'attribute vec4 seed;',
        'uniform float uTime, uSize, uScale;',
        'varying float vFade;',`,`        'attribute vec4 seed;',
        'uniform float uTime, uSize, uScale;',
        'varying float vFade;',
        'varying float vSpin;',
        'varying float vFlip;',`,"petal spin and tumble varyings"],["'  p.x += sin(uTime * sp * 0.35 + ph) * 34.0 * am;',",`/* A petal does not fall, it flutters: one slow swing carries it across
           the frame and a second, faster one wobbles inside that swing. */
        '  p.x += sin(uTime * sp * 0.30 + ph) * 96.0 * am + sin(uTime * sp * 1.15 + ph * 2.7) * 26.0 * am;',
        '  p.z += sin(uTime * sp * 0.41 + ph * 1.9) * 44.0 * am;',`,"petal flutter"],["'  float climb = mod(uTime * 11.0 * sp + ph * 60.0, 1500.0) - 750.0;',","'  float climb = 750.0 - mod(uTime * 15.0 * sp + ph * 90.0, 1500.0);',","petals fall, and slowly"],["'  float twinkle = 0.55 + 0.45 * sin(uTime * (0.7 + sp * 1.6) + ph * 3.1);',",`'  vSpin = uTime * (0.34 + sp * 0.85) + ph * 2.4;',
        '  vFlip = uTime * (0.55 + sp * 1.25) + ph * 3.7;',
        '  float twinkle = 0.88 + 0.12 * sin(uTime * (0.7 + sp * 1.6) + ph * 3.1);',`,"petal spin and tumble"],[`        'uniform sampler2D uMap;',
        'varying float vFade;',
        'void main(){',
        '  vec4 t = texture2D(uMap, gl_PointCoord);',
        '  gl_FragColor = vec4(t.rgb, t.a * vFade * 0.52);',`,`        'uniform sampler2D uMap;',
        'varying float vFade;',
        'varying float vSpin;',
        'varying float vFlip;',
        'void main(){',
        /* A point sprite can only be turned in the fragment, so spin its
           lookup rather than the quad \u2014 and narrow the lookup as the petal
           turns edge-on, which is the whole of why a real one reads as a
           thin thing tumbling rather than a disc sliding down the frame. */
        '  float cs = cos(vSpin), sn = sin(vSpin);',
        '  vec2 uv = gl_PointCoord - 0.5;',
        '  uv = vec2(uv.x * cs - uv.y * sn, uv.x * sn + uv.y * cs);',
        '  uv.x /= max(0.24, abs(cos(vFlip)));',
        '  uv += 0.5;',
        '  if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) discard;',
        '  vec4 t = texture2D(uMap, uv);',
        '  gl_FragColor = vec4(t.rgb, t.a * vFade * 0.94);',`,"spinning petals"],["uSize: { value: 9 },","uSize: { value: 46 },","petal size"],["motes.material.uniforms.uSize.value = Math.max(5, 9 * u);","motes.material.uniforms.uSize.value = Math.max(24, 54 * u);","petal size on resize"],["'  vec3 col = mix(vec3(0.30, 0.72, 0.46), vec3(0.86, 1.00, 0.90), rim);',","'  vec3 col = mix(vec3(0.92, 0.38, 0.46), vec3(1.00, 0.88, 0.66), rim);',","scan-light palette"]].reduce((n,[r,a,i])=>sl(n,r,a,i),e)}function hd(e){return[["  function build() {",`${ll}

${lp}

  function build() {`,"bough builders"],["var nearLimbs = buildNearRoot();","var nearLimbs = buildBoughs();","near bough composition"],["assembleRoot(buildFarRoot(), {","assembleRoot(buildGrove(), {","far grove composition"],["var BLADES_NEAR = small ? 70000 : 190000;","var BLADES_NEAR = small ? 140000 : 260000;","deep near cushion"],["var BLADES_FAR  = small ? 20000 :  60000;","var BLADES_FAR  = small ? 9000 :  22000;","thin far cushion"],["for (var i = 0; i < 14; i++) {","for (var i = 0; i < 0; i++) {","no stub offshoots"],["        if (limbSurface(Lw, tt, tth, p, n) < 0.45 || p.x > plantMaxX) continue;",`        limbSurface(Lw, tt, tth, p, n);
        if (p.x > plantMaxX) continue;`,"foliage on every face of a twig"],["      var Lw = host[Math.floor(rng() * host.length)];",`      var Lw = host[Math.floor(rng() * host.length)];
      /* foliage breaks from young wood; a leafing trunk reads as fungus */
      if (!Lw.young && rng() < 0.93) continue;`,"foliage on young wood"],["      for (var c2 = 0; c2 < 9 && k < opt.flowers; c2++) {","      for (var c2 = 0; c2 < 7 && k < opt.flowers; c2++) {","sprays packed along one twig"],[`        var tt = clamp01(t0 + rand(-0.008, 0.008));
        var tth = th0 + rand(-0.24, 0.24);`,`        var tt = clamp01(t0 + rand(-0.50, 0.50));
        var tth = th0 + rand(-3.14, 3.14);`,"sprays strung along the twig instead of balled at one point"],["p.addScaledVector(n, rand(0.02, 0.16));","p.addScaledVector(n, rand(0.01, 0.07));","spray seated on thin wood"],[`    var c = document.createElement('canvas'); c.width = c.height = 64;
    var g = c.getContext('2d');
    var FLORETS = [
      [32, 22, 7.4], [22, 33, 6.0], [42, 33, 6.2], [27, 44, 5.0],
      [39, 45, 5.4], [32, 33, 4.4], [46, 22, 4.2], [18, 22, 4.0]
    ];
    for (var f = 0; f < FLORETS.length; f++) {
      var cx = FLORETS[f][0], cy = FLORETS[f][1], r = FLORETS[f][2];
      g.save(); g.translate(cx, cy); g.rotate(f * 1.31);
      for (var p = 0; p < 5; p++) {
        g.save(); g.rotate((p / 5) * TAU);
        g.fillStyle = 'rgba(255,255,251,' + (0.72 + 0.28 * (r / 7.4)) + ')';
        g.beginPath(); g.ellipse(0, -r * 0.55, r * 0.34, r * 0.55, 0, 0, TAU); g.fill();
        g.restore();
      }
      g.fillStyle = '#f0e7bd';
      g.beginPath(); g.arc(0, 0, r * 0.24, 0, TAU); g.fill();
      g.restore();
    }`,`    var c = document.createElement('canvas'); c.width = c.height = 192;
    var g = c.getContext('2d');
    /* One instance is one conifer spray, and a conifer spray is an ordered
       thing: needles of one length set at one angle at an even pitch up the
       twig, in two ranks \u2014 a shorter back rank and a full front rank \u2014 so the
       twig reads as round rather than as a flat comb. Drawn at 192 so a needle
       is still a tapered blade with a vein up it rather than a hairline by the
       second mip. */
    g.translate(96, 96);
    var reach = 84;

    function needle(x, y, len, wid, ang, fill, vein) {
      g.save();
      g.translate(x, y);
      g.rotate(ang);
      g.beginPath();
      g.moveTo(-wid * 0.5, 0);
      g.quadraticCurveTo(-wid * 0.24, -len * 0.60, 0, -len);
      g.quadraticCurveTo(wid * 0.24, -len * 0.60, wid * 0.5, 0);
      g.closePath();
      g.fillStyle = fill;
      g.fill();
      if (vein) {
        g.strokeStyle = vein;
        g.lineWidth = Math.max(0.6, wid * 0.16);
        g.beginPath();
        g.moveTo(0, -len * 0.10);
        g.lineTo(0, -len * 0.78);
        g.stroke();
      }
      g.restore();
    }

    var front = g.createLinearGradient(0, reach, 0, -reach);
    front.addColorStop(0, 'rgb(34, 58, 34)');
    front.addColorStop(0.55, 'rgb(58, 96, 52)');
    front.addColorStop(1, 'rgb(122, 158, 86)');
    var back = g.createLinearGradient(0, reach, 0, -reach);
    back.addColorStop(0, 'rgb(20, 36, 22)');
    back.addColorStop(1, 'rgb(46, 74, 42)');

    /* the twig itself, tapering into the leader */
    g.strokeStyle = 'rgb(62, 62, 42)';
    g.lineCap = 'round';
    g.lineWidth = 3.2;
    g.beginPath();
    g.moveTo(0, reach * 0.94);
    g.lineTo(0, -reach * 0.86);
    g.stroke();

    var N = 19, PITCH = reach * 1.72 / N;
    for (var rank = 0; rank < 2; rank++) {
      for (var i = 0; i < N; i++) {
        var f = i / (N - 1);
        var y = reach * 0.86 - PITCH * i;
        /* one length through the middle of the spray, drawn down only over the
           last fifth so the spray ends in a point instead of a cut edge */
        var taper = 1 - 0.74 * Math.max(0, (f - 0.78) / 0.22) * Math.max(0, (f - 0.78) / 0.22);
        var len = reach * (rank ? 0.33 : 0.50) * taper * (0.94 + 0.12 * ((i % 3) / 2));
        var wid = (rank ? 2.6 : 3.4) * taper;
        var ang = (rank ? 1.02 : 0.82) + (i % 2 ? 0.03 : -0.03);
        needle(0, y, len, wid, ang, rank ? back : front, rank ? null : 'rgba(178, 206, 140, 0.30)');
        needle(0, y, len, wid, -ang, rank ? back : front, rank ? null : 'rgba(178, 206, 140, 0.30)');
      }
    }`,"sequoia foliage spray"],[`        'attribute vec3 iPos;',
        'attribute vec2 iRnd;',
        'uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',
        'void main(){',
        '  vUv = uv;',`,`        'attribute vec3 iPos;',
        'attribute vec2 iRnd;',
        'uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',
        'varying float vRnd;',
        'void main(){',
        '  vUv = uv;',
        '  vRnd = iRnd.y;',`,"per-spray variation carried to the foliage"],[`'uniform sampler2D uMap;',
        'uniform float uAlpha; uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',`,`'uniform sampler2D uMap;',
        'uniform float uAlpha; uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',
        'varying float vRnd;',`,"per-spray variation read by the foliage"],[`        '  vec4 t = texture2D(uMap, vUv);',
        '  if (t.a < 0.14) discard;',`,`        /* every instance turned the same way reads as printed wallpaper */
        '  float fc = cos(vRnd * 6.2832), fs = sin(vRnd * 6.2832);',
        '  vec2 fuv = vUv - 0.5;',
        '  fuv = vec2(fuv.x * fc - fuv.y * fs, fuv.x * fs + fuv.y * fc) + 0.5;',
        '  vec4 t = texture2D(uMap, fuv);',
        '  if (t.a < 0.14) discard;',`,"each blossom faces its own way"],["'  vec3 col = t.rgb * t.rgb * (uKeyCol * 0.62 + uAmbCol * 0.9);',",`/* Sprays differ: the ones in the shaft are half sunlight, the ones behind
           them are almost black-green. One tone across a crown reads as felt. */
        '  vec3 tone = mix(vec3(0.68, 0.82, 0.60), vec3(1.06, 1.04, 0.84), vRnd);',
        '  vec3 col = t.rgb * t.rgb * tone * (uKeyCol * 0.62 + uAmbCol * 1.25) * (0.72 + 0.46 * vRnd);',
        /* a needle is thin enough to pass the fog light straight through */
        '  vec3 V = normalize(cameraPosition - vW);',
        '  col += uKeyCol * pow(max(dot(V, -uKeyDir), 0.0), 3.0) * 0.20 * t.a * (0.5 + 0.9 * vRnd);',`,"foliage lit through by the fog light"],["    return c * sstep(0.10, 0.50, patch);","    return c * sstep(0.30, 0.72, patch);","patchy cushion, bare bark between"],["'  vec3 silver = mix(vec3(0.020, 0.019, 0.018), vec3(0.290, 0.283, 0.264), grain);',","'  vec3 silver = mix(vec3(0.030, 0.020, 0.016), vec3(0.206, 0.130, 0.096), grain);',","redwood bark greys"],["'  vec3 umber  = mix(vec3(0.024, 0.019, 0.016), vec3(0.175, 0.140, 0.110), grain);',","'  vec3 umber  = mix(vec3(0.036, 0.016, 0.011), vec3(0.224, 0.092, 0.056), grain);',","redwood bark cinnamon"],[`    sproutTwigs(limbs, boughA, 15, 0.94, 0.070, 4);
    sproutTwigs(limbs, boughB, 10, 0.76, 0.050, 4);
    sproutTwigs(limbs, boughC, 8, 0.64, 0.039, 3);`,`    sproutTwigs(limbs, boughA, 24, 0.66, 0.046, 5);
    sproutTwigs(limbs, boughB, 16, 0.54, 0.034, 5);
    sproutTwigs(limbs, boughC, 12, 0.46, 0.027, 4);`,"finer wood: a redwood forks smaller and more often than a cherry"],["'vec2 barkDomain(vec2 uv){ return vec2(uv.x * 7.0, uv.y * 0.62); }',","'vec2 barkDomain(vec2 uv){ return vec2(uv.x * 5.4, uv.y * 0.30); }',","fibrous bark: the grain runs twice as long on a redwood"],["'  vec3 moss = mix(vec3(0.0204, 0.0311, 0.0050), vec3(0.0914, 0.1392, 0.0227), mo);',","'  vec3 moss = mix(vec3(0.0176, 0.0290, 0.0128), vec3(0.0700, 0.1140, 0.0460), mo);',","moss cushion on the bark shell"],["'  col = mix(col, vec3(0.162, 0.176, 0.132), lich * 0.78);',","'  col = mix(col, vec3(0.198, 0.176, 0.156), lich * 0.70);',","lichen crust palette"],[`'  vec3 deep = vec3(0.0126, 0.0192, 0.0031);',
        '  vec3 mid  = vec3(0.0488, 0.0744, 0.0121);',
        '  vec3 tip  = vec3(0.1222, 0.1860, 0.0304);',
        '  vec3 tipHi = vec3(0.2600, 0.3900, 0.0640);',`,`'  vec3 deep = vec3(0.0148, 0.0250, 0.0116);',
        '  vec3 mid  = vec3(0.0560, 0.0940, 0.0410);',
        '  vec3 tip  = vec3(0.1120, 0.1840, 0.0760);',
        '  vec3 tipHi = vec3(0.2380, 0.3760, 0.1460);',`,"forest moss in the fur"],["'  vec3 base = mix(vec3(0.0270, 0.0450, 0.0099), vec3(0.0690, 0.1150, 0.0253), vTint);',","'  vec3 base = mix(vec3(0.0210, 0.0350, 0.0140), vec3(0.0560, 0.0930, 0.0330), vTint);',","forest fronds"],["      var Lf = host[Math.floor(rng() * host.length)];",`      /* fronds seat on the old boughs only: one on a twig reads as a
         frond hanging in mid-air */
      var Lf = host[Math.floor(rng() * Math.min(host.length, 3))];`,"fronds on the boughs"],[`  var KEY  = new THREE.Vector3(-0.30, 0.92, 0.28).normalize();
  var FILL = new THREE.Vector3( 0.12, -0.86, 0.50).normalize();`,`  /* dusk after the sun has gone: a soft high key that still models the
     cushion, and a cool bounce off the air on the near side */
  var KEY  = new THREE.Vector3(-0.26, 0.90,  0.34).normalize();
  var FILL = new THREE.Vector3( 0.16, -0.82,  0.52).normalize();`,"soft dusk directions"],["uKeyCol:  { value: new THREE.Color(1.14, 1.06, 0.88) },","uKeyCol:  { value: new THREE.Color(1.12, 1.16, 1.06) },","sunset key light"],["uFillCol: { value: new THREE.Color(0.78, 0.78, 0.62) },","uFillCol: { value: new THREE.Color(0.62, 0.70, 0.64) },","dusk sky fill"],["uAmbCol:  { value: new THREE.Color(0.086, 0.090, 0.080) },","uAmbCol:  { value: new THREE.Color(0.196, 0.222, 0.196) },","dusk ambient"],["uHazeCol: { value: new THREE.Color(0.176, 0.195, 0.145) },","uHazeCol: { value: new THREE.Color(0.520, 0.570, 0.508) },","sunset haze"],["renderer.toneMappingExposure = 1.30;","renderer.toneMappingExposure = 1.32;","dusk exposure"],["aspect: ARCH.aspect, haze: 0.15, fog: 0.0, alpha: 1.0, order: 2,","aspect: ARCH.aspect, haze: 0.17, fog: 0.0, alpha: 1.0, order: 2,","near air"],[`      blades: BLADES_NEAR, ferns: small ? 26 : 46, flowers: small ? 120 : 260,
      fernSize: [0.22, 0.50], flowerSize: [0.055, 0.118], mainLimbs: mainCount, wire: true,`,`      blades: BLADES_NEAR, ferns: small ? 14 : 26, flowers: small ? 2800 : 5200,
      fernSize: [0.16, 0.36], flowerSize: [0.300, 0.520], mainLimbs: 0, wire: true,`,"near boughs in full foliage"],["aspect: FAR.aspect, haze: 0.16, fog: 0.26, alpha: 1.0, order: 0,","aspect: FAR.aspect, haze: 0.30, fog: 0.90, alpha: 1.0, order: 0,","far grove pushed into the air"],["hazeCol: [0.150, 0.164, 0.120], hazeLift: 0.92,","hazeCol: [0.545, 0.596, 0.532], hazeLift: 0.98,","far sunset haze"],[`      blades: BLADES_FAR, ferns: small ? 8 : 16, flowers: small ? 40 : 90,
      fernSize: [0.26, 0.56], flowerSize: [0.034, 0.062],
      mask: [0.4, 3.4, 0.0, 0.42], wire: true,`,`      blades: BLADES_FAR, ferns: 0, flowers: small ? 2000 : 4400,
      fernSize: [0.26, 0.56], flowerSize: [0.130, 0.240],
      mask: [4.6, 5.6, -0.14, 0.20], wire: true,`,"far grove in foliage"],[`  var ARCH   = { w: 1900, left: -180, top: 306, aspect: 2800 / 1377 };
  var ARCH_N = { w: 1120, left: -290, top: 555, aspect: 2800 / 1377 };
  var FAR    = { w: 1150, left:  -40, top: 320, aspect: 1600 /  757, z: -260 };
  var FAR_N  = { w:  780, left: -110, top: 600, aspect: 1600 /  757, z: -260 };`,`  /* framed on the boughs at the authored close range: the frame is
     branch and blossom, with the grove sitting low behind it */
  var ARCH   = { w: 1500, left:   50, top:  262, aspect: 2800 / 1377 };
  var ARCH_N = { w: 1680, left:  -99, top:  500, aspect: 2800 / 1377 };
  var FAR    = { w: 1240, left:  180, top:  392, aspect: 1600 /  757, z: -260 };
  var FAR_N  = { w:  920, left:  280, top:  902, aspect: 1600 /  757, z: -260 };`,"framing boxes"],["place(nearGroup, A, 0.732, 0.06, 0);","place(nearGroup, A, 0.500, 0.500, 0);","tree framing"],["place(farGroup,  F, 0.410, 0.32, F.z);","place(farGroup,  F, 0.500, 0.500, F.z);","grove framing"],["map: radialTexture(256, [[0, 'rgba(12,16,10,0.62)'], [0.45, 'rgba(12,16,10,0.26)'], [1, 'rgba(12,16,10,0)']]),","map: radialTexture(256, [[0, 'rgba(26,34,28,0.42)'], [0.45, 'rgba(26,34,28,0.17)'], [1, 'rgba(26,34,28,0)']]),","dusk ground shadow"],[`    shadowMesh.scale.set(aw * 1.02, ah * 0.72, 1);
    shadowMesh.position.set(cx, cy - ah * 0.40, -70);`,`    shadowMesh.scale.set(aw * 2.10, ah * 0.44, 1);
    shadowMesh.position.set(cx, cy - ah * 0.98, -70);`,"ground haze instead of a disc on the sky"],[`    glowMesh.scale.set(aw * 1.15, ah * 1.5, 1);
    glowMesh.position.set(cx - aw * 0.06, cy - ah * 0.18, -320);`,`    /* the sky already carries the sun and its bloom; a second glow plane
       in front of it only draws its own edge across the horizon */
    glowMesh.visible = false;`,"sun bloom left to the sky"],["'  lit += col * uAmbCol * pow(1.0 - max(dot(N, V), 0.0), 4.0) * 0.85;',","'  lit += (col * uAmbCol * 0.85 + uKeyCol * 0.030) * pow(1.0 - max(dot(N, V), 0.0), 4.0);',","sun rim along the bark"],[`'  vec3 face = vec3(0.330, 0.560, 0.042);',
        '  vec3 edge = vec3(0.062, 0.190, 0.014);',`,`'  vec3 face = vec3(0.620, 0.330, 0.090);',
        '  vec3 edge = vec3(0.150, 0.058, 0.030);',`,"amber swallowtail"],["'  wing = mix(wing * vec3(0.46, 1.14, 0.30), wing * vec3(1.34, 1.06, 0.16), shim);',","'  wing = mix(wing * vec3(1.18, 0.72, 0.34), wing * vec3(1.42, 0.98, 0.28), shim);',","amber diffraction"],["'  lit += mix(vec3(0.86, 0.78, 0.20), vec3(0.34, 0.60, 0.12), border) * back * 0.42;',","'  lit += mix(vec3(0.98, 0.66, 0.26), vec3(0.50, 0.22, 0.12), border) * back * 0.42;',","sun through the wing"],["poleTex = radialTexture(64, [[0, 'rgba(255,255,255,1)'], [0.35, 'rgba(236,244,224,0.5)'], [1, 'rgba(236,244,224,0)']]);","poleTex = fallingSprite();","sprig sprite"],["var COUNT = (NARROW.matches || (window.innerWidth * window.innerHeight) < 620000) ? 1500 : 4200;","var COUNT = (NARROW.matches || (window.innerWidth * window.innerHeight) < 620000) ? 180 : 420;","sprig count"],[`      transparent: true, depthWrite: false, depthTest: true,
      blending: THREE.AdditiveBlending,`,`      transparent: true, depthWrite: false, depthTest: true,
      blending: THREE.NormalBlending,`,"sprigs blend as foliage, not as sparks"],[`        'attribute vec4 seed;',
        'uniform float uTime, uSize, uScale;',
        'varying float vFade;',`,`        'attribute vec4 seed;',
        'uniform float uTime, uSize, uScale;',
        'varying float vFade;',
        'varying float vSpin;',
        'varying float vFlip;',`,"sprig spin and tumble varyings"],["'  p.x += sin(uTime * sp * 0.35 + ph) * 34.0 * am;',",`/* A petal does not fall, it flutters: one slow swing carries it across
           the frame and a second, faster one wobbles inside that swing. */
        '  p.x += sin(uTime * sp * 0.30 + ph) * 96.0 * am + sin(uTime * sp * 1.15 + ph * 2.7) * 26.0 * am;',
        '  p.z += sin(uTime * sp * 0.41 + ph * 1.9) * 44.0 * am;',`,"sprig flutter"],["'  float climb = mod(uTime * 11.0 * sp + ph * 60.0, 1500.0) - 750.0;',","'  float climb = 750.0 - mod(uTime * 13.0 * sp + ph * 90.0, 1500.0);',","sprigs fall, and slowly"],["'  float twinkle = 0.55 + 0.45 * sin(uTime * (0.7 + sp * 1.6) + ph * 3.1);',",`'  vSpin = uTime * (0.34 + sp * 0.85) + ph * 2.4;',
        '  vFlip = uTime * (0.55 + sp * 1.25) + ph * 3.7;',
        '  float twinkle = 0.88 + 0.12 * sin(uTime * (0.7 + sp * 1.6) + ph * 3.1);',`,"sprig spin and tumble"],[`        'uniform sampler2D uMap;',
        'varying float vFade;',
        'void main(){',
        '  vec4 t = texture2D(uMap, gl_PointCoord);',
        '  gl_FragColor = vec4(t.rgb, t.a * vFade * 0.52);',`,`        'uniform sampler2D uMap;',
        'varying float vFade;',
        'varying float vSpin;',
        'varying float vFlip;',
        'void main(){',
        /* A point sprite can only be turned in the fragment, so spin its
           lookup rather than the quad \u2014 and narrow the lookup as the petal
           turns edge-on, which is the whole of why a real one reads as a
           thin thing tumbling rather than a disc sliding down the frame. */
        '  float cs = cos(vSpin), sn = sin(vSpin);',
        '  vec2 uv = gl_PointCoord - 0.5;',
        '  uv = vec2(uv.x * cs - uv.y * sn, uv.x * sn + uv.y * cs);',
        '  uv.x /= max(0.24, abs(cos(vFlip)));',
        '  uv += 0.5;',
        '  if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) discard;',
        '  vec4 t = texture2D(uMap, uv);',
        '  gl_FragColor = vec4(t.rgb, t.a * vFade * 0.94);',`,"tumbling sprigs"],["uSize: { value: 9 },","uSize: { value: 30 },","sprig size"],["motes.material.uniforms.uSize.value = Math.max(5, 9 * u);","motes.material.uniforms.uSize.value = Math.max(16, 36 * u);","sprig size on resize"],["'  vec3 col = mix(vec3(0.30, 0.72, 0.46), vec3(0.86, 1.00, 0.90), rim);',","'  vec3 col = mix(vec3(0.44, 0.72, 0.42), vec3(0.92, 1.00, 0.88), rim);',","scan-light palette"]].reduce((n,[r,a,i])=>sl(n,r,a,i),e)}function pd(e){return[["  function build() {",`${ll}

${ap}

${op}

  function build() {`,"bough builders"],["var nearLimbs = buildNearRoot();","var nearLimbs = buildBoughs();","near bough composition"],["assembleRoot(buildFarRoot(), {","assembleRoot(buildGrove(), {","far grove composition"],["var BLADES_NEAR = small ? 70000 : 190000;","var BLADES_NEAR = small ? 140000 : 260000;","deep near cushion"],["var BLADES_FAR  = small ? 20000 :  60000;","var BLADES_FAR  = small ? 9000 :  22000;","thin far cushion"],["for (var i = 0; i < 14; i++) {","for (var i = 0; i < 0; i++) {","no stub offshoots"],["        if (limbSurface(Lw, tt, tth, p, n) < 0.45 || p.x > plantMaxX) continue;",`        limbSurface(Lw, tt, tth, p, n);
        if (p.x > plantMaxX) continue;`,"leaf on every face of a twig"],["      var Lw = host[Math.floor(rng() * host.length)];",`      var Lw = host[Math.floor(rng() * host.length)];
      /* leaf breaks from young wood; a leafing trunk reads as fungus */
      if (!Lw.young && rng() < 0.93) continue;`,"leaf on young wood"],["      for (var c2 = 0; c2 < 9 && k < opt.flowers; c2++) {","      for (var c2 = 0; c2 < 4 && k < opt.flowers; c2++) {","leaves spaced along one spray"],[`        var tt = clamp01(t0 + rand(-0.008, 0.008));
        var tth = th0 + rand(-0.24, 0.24);`,`        var tt = clamp01(t0 + rand(-0.50, 0.50));
        var tth = th0 + rand(-3.14, 3.14);`,"leaves strung along the twig instead of balled at one point"],["p.addScaledVector(n, rand(0.02, 0.16));","p.addScaledVector(n, rand(0.02, 0.12));","leaf seated on thin wood"],[`    var c = document.createElement('canvas'); c.width = c.height = 64;
    var g = c.getContext('2d');
    var FLORETS = [
      [32, 22, 7.4], [22, 33, 6.0], [42, 33, 6.2], [27, 44, 5.0],
      [39, 45, 5.4], [32, 33, 4.4], [46, 22, 4.2], [18, 22, 4.0]
    ];
    for (var f = 0; f < FLORETS.length; f++) {
      var cx = FLORETS[f][0], cy = FLORETS[f][1], r = FLORETS[f][2];
      g.save(); g.translate(cx, cy); g.rotate(f * 1.31);
      for (var p = 0; p < 5; p++) {
        g.save(); g.rotate((p / 5) * TAU);
        g.fillStyle = 'rgba(255,255,251,' + (0.72 + 0.28 * (r / 7.4)) + ')';
        g.beginPath(); g.ellipse(0, -r * 0.55, r * 0.34, r * 0.55, 0, 0, TAU); g.fill();
        g.restore();
      }
      g.fillStyle = '#f0e7bd';
      g.beginPath(); g.arc(0, 0, r * 0.24, 0, TAU); g.fill();
      g.restore();
    }`,`    var c = document.createElement('canvas'); c.width = c.height = 128;
    var g = c.getContext('2d');
    /* One instance is one maple leaf. The gradient runs from a hot rim to a
       darker heart rather than the other way round: a leaf is thinnest at its
       lobe tips, so that is where the low light comes through it. */
    g.translate(64, 66);
    var r = 58;
    var grad = g.createRadialGradient(0, r * 0.22, r * 0.06, 0, 0, r);
    grad.addColorStop(0, 'rgba(192, 76, 48, 0.98)');
    grad.addColorStop(0.42, 'rgba(222, 112, 56, 0.97)');
    grad.addColorStop(0.78, 'rgba(238, 158, 80, 0.96)');
    grad.addColorStop(1, 'rgba(248, 206, 130, 0.94)');
    g.fillStyle = grad;
    mapleOutline(g, r);
    g.fill();
    /* the veins: one up each lobe out of the petiole, thinning as they go */
    g.strokeStyle = 'rgba(255, 214, 150, 0.34)';
    g.lineCap = 'round';
    var VEINS = [[0, -1.00], [0.44, -0.72], [-0.44, -0.72], [0.78, -0.24], [-0.78, -0.24]];
    for (var v = 0; v < VEINS.length; v++) {
      g.lineWidth = Math.max(1, r * (v === 0 ? 0.030 : 0.022));
      g.beginPath();
      g.moveTo(0, r * 0.52);
      g.quadraticCurveTo(VEINS[v][0] * r * 0.30, VEINS[v][1] * r * 0.10,
                         VEINS[v][0] * r * 0.86, VEINS[v][1] * r * 0.86);
      g.stroke();
    }
    /* the petiole, so a leaf never reads as a cut-out shape floating free */
    g.strokeStyle = 'rgba(176, 96, 52, 0.72)';
    g.lineWidth = Math.max(1, r * 0.036);
    g.beginPath(); g.moveTo(0, r * 0.52); g.lineTo(0, r * 1.02); g.stroke();`,"maple leaf sprite"],[`        'attribute vec3 iPos;',
        'attribute vec2 iRnd;',
        'uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',
        'void main(){',
        '  vUv = uv;',`,`        'attribute vec3 iPos;',
        'attribute vec2 iRnd;',
        'uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',
        'varying float vRnd;',
        'void main(){',
        '  vUv = uv;',
        '  vRnd = iRnd.y;',`,"per-leaf variation carried to the leaf"],[`'uniform sampler2D uMap;',
        'uniform float uAlpha; uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',`,`'uniform sampler2D uMap;',
        'uniform float uAlpha; uniform float uBoxH;',
        'varying vec2 vUv; varying float vH; varying vec3 vL; varying vec3 vW;',
        'varying float vRnd;',`,"per-leaf variation read by the leaf"],[`        '  vec4 t = texture2D(uMap, vUv);',
        '  if (t.a < 0.14) discard;',`,`        /* every instance turned the same way reads as printed wallpaper */
        '  float fc = cos(vRnd * 6.2832), fs = sin(vRnd * 6.2832);',
        '  vec2 fuv = vUv - 0.5;',
        '  fuv = vec2(fuv.x * fc - fuv.y * fs, fuv.x * fs + fuv.y * fc) + 0.5;',
        '  vec4 t = texture2D(uMap, fuv);',
        '  if (t.a < 0.14) discard;',`,"each blossom faces its own way"],["'  vec3 col = t.rgb * t.rgb * (uKeyCol * 0.62 + uAmbCol * 0.9);',",`/* No two leaves turn at the same time: some are still hot red, some
           already gone to gold. One tone across a crown reads as plastic. */
        '  vec3 tone = mix(vec3(0.78, 0.30, 0.22), vec3(1.16, 1.02, 0.58), pow(vRnd, 0.62));',
        '  vec3 col = t.rgb * t.rgb * tone * (uKeyCol * 0.60 + uAmbCol * 1.05) * (0.70 + 0.50 * vRnd);',
        /* a leaf is thin enough to pass the low light straight through */
        '  vec3 V = normalize(cameraPosition - vW);',
        '  col += uKeyCol * pow(max(dot(V, -uKeyDir), 0.0), 3.0) * 0.20 * t.a * (0.5 + 0.9 * vRnd);',`,"leaf lit through from behind"],["    return c * sstep(0.10, 0.50, patch);","    return c * sstep(0.30, 0.72, patch);","patchy cushion, bare bark between"],["'  vec3 silver = mix(vec3(0.020, 0.019, 0.018), vec3(0.290, 0.283, 0.264), grain);',","'  vec3 silver = mix(vec3(0.028, 0.026, 0.024), vec3(0.296, 0.278, 0.256), grain);',","maple bark greys"],["'  vec3 umber  = mix(vec3(0.024, 0.019, 0.016), vec3(0.175, 0.140, 0.110), grain);',","'  vec3 umber  = mix(vec3(0.034, 0.026, 0.020), vec3(0.236, 0.176, 0.126), grain);',","maple bark browns"],["'  vec3 moss = mix(vec3(0.0204, 0.0311, 0.0050), vec3(0.0914, 0.1392, 0.0227), mo);',","'  vec3 moss = mix(vec3(0.0268, 0.0306, 0.0120), vec3(0.1080, 0.1240, 0.0398), mo);',","moss cushion on the bark shell"],["'  col = mix(col, vec3(0.162, 0.176, 0.132), lich * 0.78);',","'  col = mix(col, vec3(0.198, 0.176, 0.156), lich * 0.70);',","lichen crust palette"],[`'  vec3 deep = vec3(0.0126, 0.0192, 0.0031);',
        '  vec3 mid  = vec3(0.0488, 0.0744, 0.0121);',
        '  vec3 tip  = vec3(0.1222, 0.1860, 0.0304);',
        '  vec3 tipHi = vec3(0.2600, 0.3900, 0.0640);',`,`'  vec3 deep = vec3(0.0230, 0.0268, 0.0104);',
        '  vec3 mid  = vec3(0.0900, 0.1040, 0.0330);',
        '  vec3 tip  = vec3(0.1800, 0.2060, 0.0640);',
        '  vec3 tipHi = vec3(0.3600, 0.4160, 0.1120);',`,"green-gold moss in the fur"],["'  vec3 base = mix(vec3(0.0270, 0.0450, 0.0099), vec3(0.0690, 0.1150, 0.0253), vTint);',","'  vec3 base = mix(vec3(0.0300, 0.0330, 0.0128), vec3(0.0780, 0.0880, 0.0290), vTint);',","green-gold fronds"],["      var Lf = host[Math.floor(rng() * host.length)];",`      /* fronds seat on the old boughs only: one on a twig reads as a
         frond hanging in mid-air */
      var Lf = host[Math.floor(rng() * Math.min(host.length, 3))];`,"fronds on the boughs"],[`  var KEY  = new THREE.Vector3(-0.30, 0.92, 0.28).normalize();
  var FILL = new THREE.Vector3( 0.12, -0.86, 0.50).normalize();`,`  /* dusk after the sun has gone: a soft high key that still models the
     cushion, and a cool bounce off the air on the near side */
  var KEY  = new THREE.Vector3(-0.26, 0.90,  0.34).normalize();
  var FILL = new THREE.Vector3( 0.16, -0.82,  0.52).normalize();`,"soft dusk directions"],["uKeyCol:  { value: new THREE.Color(1.14, 1.06, 0.88) },","uKeyCol:  { value: new THREE.Color(1.36, 1.06, 0.76) },","sunset key light"],["uFillCol: { value: new THREE.Color(0.78, 0.78, 0.62) },","uFillCol: { value: new THREE.Color(0.50, 0.62, 0.76) },","dusk sky fill"],["uAmbCol:  { value: new THREE.Color(0.086, 0.090, 0.080) },","uAmbCol:  { value: new THREE.Color(0.108, 0.130, 0.150) },","dusk ambient"],["uHazeCol: { value: new THREE.Color(0.176, 0.195, 0.145) },","uHazeCol: { value: new THREE.Color(0.222, 0.258, 0.288) },","sunset haze"],["renderer.toneMappingExposure = 1.30;","renderer.toneMappingExposure = 1.32;","dusk exposure"],["aspect: ARCH.aspect, haze: 0.15, fog: 0.0, alpha: 1.0, order: 2,","aspect: ARCH.aspect, haze: 0.17, fog: 0.0, alpha: 1.0, order: 2,","near air"],[`      blades: BLADES_NEAR, ferns: small ? 26 : 46, flowers: small ? 120 : 260,
      fernSize: [0.22, 0.50], flowerSize: [0.055, 0.118], mainLimbs: mainCount, wire: true,`,`      blades: BLADES_NEAR, ferns: small ? 14 : 26, flowers: small ? 2600 : 5000,
      fernSize: [0.16, 0.36], flowerSize: [0.230, 0.420], mainLimbs: 0, wire: true,`,"near boughs in full leaf"],["aspect: FAR.aspect, haze: 0.16, fog: 0.26, alpha: 1.0, order: 0,","aspect: FAR.aspect, haze: 0.26, fog: 0.82, alpha: 1.0, order: 0,","far grove pushed into the air"],["hazeCol: [0.150, 0.164, 0.120], hazeLift: 0.92,","hazeCol: [0.224, 0.260, 0.290], hazeLift: 0.94,","far sunset haze"],[`      blades: BLADES_FAR, ferns: small ? 8 : 16, flowers: small ? 40 : 90,
      fernSize: [0.26, 0.56], flowerSize: [0.034, 0.062],
      mask: [0.4, 3.4, 0.0, 0.42], wire: true,`,`      blades: BLADES_FAR, ferns: 0, flowers: small ? 1600 : 3600,
      fernSize: [0.26, 0.56], flowerSize: [0.100, 0.190],
      mask: [4.6, 5.6, -0.14, 0.20], wire: true,`,"far grove in leaf"],[`  var ARCH   = { w: 1900, left: -180, top: 306, aspect: 2800 / 1377 };
  var ARCH_N = { w: 1120, left: -290, top: 555, aspect: 2800 / 1377 };
  var FAR    = { w: 1150, left:  -40, top: 320, aspect: 1600 /  757, z: -260 };
  var FAR_N  = { w:  780, left: -110, top: 600, aspect: 1600 /  757, z: -260 };`,`  /* framed on the boughs at the authored close range: the frame is
     branch and blossom, with the grove sitting low behind it */
  var ARCH   = { w: 1500, left:   50, top:  262, aspect: 2800 / 1377 };
  var ARCH_N = { w: 1680, left:  -99, top:  500, aspect: 2800 / 1377 };
  var FAR    = { w: 1240, left:  180, top:  392, aspect: 1600 /  757, z: -260 };
  var FAR_N  = { w:  920, left:  280, top:  902, aspect: 1600 /  757, z: -260 };`,"framing boxes"],["place(nearGroup, A, 0.732, 0.06, 0);","place(nearGroup, A, 0.500, 0.500, 0);","tree framing"],["place(farGroup,  F, 0.410, 0.32, F.z);","place(farGroup,  F, 0.500, 0.500, F.z);","grove framing"],["map: radialTexture(256, [[0, 'rgba(12,16,10,0.62)'], [0.45, 'rgba(12,16,10,0.26)'], [1, 'rgba(12,16,10,0)']]),","map: radialTexture(256, [[0, 'rgba(14,20,26,0.55)'], [0.45, 'rgba(14,20,26,0.22)'], [1, 'rgba(14,20,26,0)']]),","dusk ground shadow"],[`    shadowMesh.scale.set(aw * 1.02, ah * 0.72, 1);
    shadowMesh.position.set(cx, cy - ah * 0.40, -70);`,`    shadowMesh.scale.set(aw * 2.10, ah * 0.44, 1);
    shadowMesh.position.set(cx, cy - ah * 0.98, -70);`,"ground haze instead of a disc on the sky"],[`    glowMesh.scale.set(aw * 1.15, ah * 1.5, 1);
    glowMesh.position.set(cx - aw * 0.06, cy - ah * 0.18, -320);`,`    /* the sky already carries the sun and its bloom; a second glow plane
       in front of it only draws its own edge across the horizon */
    glowMesh.visible = false;`,"sun bloom left to the sky"],["'  lit += col * uAmbCol * pow(1.0 - max(dot(N, V), 0.0), 4.0) * 0.85;',","'  lit += (col * uAmbCol * 0.85 + uKeyCol * 0.030) * pow(1.0 - max(dot(N, V), 0.0), 4.0);',","sun rim along the bark"],[`'  vec3 face = vec3(0.330, 0.560, 0.042);',
        '  vec3 edge = vec3(0.062, 0.190, 0.014);',`,`'  vec3 face = vec3(0.620, 0.330, 0.090);',
        '  vec3 edge = vec3(0.150, 0.058, 0.030);',`,"amber swallowtail"],["'  wing = mix(wing * vec3(0.46, 1.14, 0.30), wing * vec3(1.34, 1.06, 0.16), shim);',","'  wing = mix(wing * vec3(1.18, 0.72, 0.34), wing * vec3(1.42, 0.98, 0.28), shim);',","amber diffraction"],["'  lit += mix(vec3(0.86, 0.78, 0.20), vec3(0.34, 0.60, 0.12), border) * back * 0.42;',","'  lit += mix(vec3(0.98, 0.66, 0.26), vec3(0.50, 0.22, 0.12), border) * back * 0.42;',","sun through the wing"],["poleTex = radialTexture(64, [[0, 'rgba(255,255,255,1)'], [0.35, 'rgba(236,244,224,0.5)'], [1, 'rgba(236,244,224,0)']]);","poleTex = fallingSprite();","leaf sprite"],["var COUNT = (NARROW.matches || (window.innerWidth * window.innerHeight) < 620000) ? 1500 : 4200;","var COUNT = (NARROW.matches || (window.innerWidth * window.innerHeight) < 620000) ? 140 : 340;","leaf count"],[`      transparent: true, depthWrite: false, depthTest: true,
      blending: THREE.AdditiveBlending,`,`      transparent: true, depthWrite: false, depthTest: true,
      blending: THREE.NormalBlending,`,"leaves blend as leaves, not as sparks"],[`        'attribute vec4 seed;',
        'uniform float uTime, uSize, uScale;',
        'varying float vFade;',`,`        'attribute vec4 seed;',
        'uniform float uTime, uSize, uScale;',
        'varying float vFade;',
        'varying float vSpin;',
        'varying float vFlip;',`,"leaf spin and tumble varyings"],["'  p.x += sin(uTime * sp * 0.35 + ph) * 34.0 * am;',",`/* A petal does not fall, it flutters: one slow swing carries it across
           the frame and a second, faster one wobbles inside that swing. */
        '  p.x += sin(uTime * sp * 0.30 + ph) * 96.0 * am + sin(uTime * sp * 1.15 + ph * 2.7) * 26.0 * am;',
        '  p.z += sin(uTime * sp * 0.41 + ph * 1.9) * 44.0 * am;',`,"leaf flutter"],["'  float climb = mod(uTime * 11.0 * sp + ph * 60.0, 1500.0) - 750.0;',","'  float climb = 750.0 - mod(uTime * 11.0 * sp + ph * 90.0, 1500.0);',","leaves fall, and slowly"],["'  float twinkle = 0.55 + 0.45 * sin(uTime * (0.7 + sp * 1.6) + ph * 3.1);',",`'  vSpin = uTime * (0.26 + sp * 0.62) + ph * 2.4;',
        '  vFlip = uTime * (0.55 + sp * 1.25) + ph * 3.7;',
        '  float twinkle = 0.88 + 0.12 * sin(uTime * (0.7 + sp * 1.6) + ph * 3.1);',`,"leaf spin and tumble"],[`        'uniform sampler2D uMap;',
        'varying float vFade;',
        'void main(){',
        '  vec4 t = texture2D(uMap, gl_PointCoord);',
        '  gl_FragColor = vec4(t.rgb, t.a * vFade * 0.52);',`,`        'uniform sampler2D uMap;',
        'varying float vFade;',
        'varying float vSpin;',
        'varying float vFlip;',
        'void main(){',
        /* A point sprite can only be turned in the fragment, so spin its
           lookup rather than the quad \u2014 and narrow the lookup as the petal
           turns edge-on, which is the whole of why a real one reads as a
           thin thing tumbling rather than a disc sliding down the frame. */
        '  float cs = cos(vSpin), sn = sin(vSpin);',
        '  vec2 uv = gl_PointCoord - 0.5;',
        '  uv = vec2(uv.x * cs - uv.y * sn, uv.x * sn + uv.y * cs);',
        '  uv.x /= max(0.24, abs(cos(vFlip)));',
        '  uv += 0.5;',
        '  if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) discard;',
        '  vec4 t = texture2D(uMap, uv);',
        '  gl_FragColor = vec4(t.rgb, t.a * vFade * 0.94);',`,"tumbling leaves"],["uSize: { value: 9 },","uSize: { value: 62 },","leaf size"],["motes.material.uniforms.uSize.value = Math.max(5, 9 * u);","motes.material.uniforms.uSize.value = Math.max(30, 70 * u);","leaf size on resize"],["'  vec3 col = mix(vec3(0.30, 0.72, 0.46), vec3(0.86, 1.00, 0.90), rim);',","'  vec3 col = mix(vec3(0.96, 0.52, 0.18), vec3(1.00, 0.90, 0.60), rim);',","scan-light palette"]].reduce((n,[r,a,i])=>sl(n,r,a,i),e)}var wd=ce(Oe()),up=["living-green","sakura-sunset","maple-autumn","sequoia-mist"],gd="/landing-pages/inner-green-3d.html",md="inner-green-assets/",cp=`${gd.replace(/[^/]+$/,"")}${md}`,dp={"sakura-sunset":{edge:"255, 236, 243",lift:"255, 240, 246",panel:"48, 33, 43",drop:"20, 10, 18",nearPanel:"53, 35, 46",mark:"#f3e9ee",markInk:"#33222c",plate:"58, 40, 51"},"maple-autumn":{edge:"228, 240, 246",lift:"232, 244, 250",panel:"33, 41, 47",drop:"8, 14, 18",nearPanel:"37, 46, 53",mark:"#e8eff2",markInk:"#23303a",plate:"34, 46, 54"},"sequoia-mist":{edge:"236, 244, 232",lift:"238, 246, 232",panel:"38, 48, 40",drop:"16, 24, 18",nearPanel:"43, 54, 44",mark:"#eef3e8",markInk:"#26302a",plate:"48, 60, 50"}};function hp(e){return`<style data-threeui-sylva-hero-chrome>
/* \u2500\u2500 nav: the authored glass, retoned to the field behind it \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
.dock {
  border-color: rgba(${e.edge}, 0.13) !important;
  background:
    linear-gradient(180deg, rgba(${e.lift}, 0.06), rgba(${e.lift}, 0) 42%),
    rgba(${e.panel}, 0.76) !important;
  box-shadow: 0 calc(8 * var(--u)) calc(22 * var(--u)) rgba(${e.drop}, 0.34),
              inset 0 1px rgba(${e.lift}, 0.07) !important;
}

.dock-item[data-near="true"] {
  border-color: rgba(${e.edge}, 0.20) !important;
  background: rgba(${e.nearPanel}, 0.94) !important;
  box-shadow: 0 calc(7 * var(--u)) calc(16 * var(--u)) rgba(${e.drop}, 0.32) !important;
}

.dock-mark {
  background: ${e.mark} !important;
  border-color: ${e.mark} !important;
  color: ${e.markInk} !important;
}

.dock-mark[data-near="true"] {
  background: #fff !important;
  border-color: #fff !important;
  color: ${e.markInk} !important;
}

.dock-item--enter { background: rgba(${e.lift}, 0.085) !important; }

/* \u2500\u2500 the two native controls \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
   The frosted plate cannot go on the clip elements themselves: their clip is
   cut to the button's whole bloom, so the blur would read as a slab twice the
   button's size. It cannot go inside them either \u2014 clip-path makes a backdrop
   root, so a child's backdrop-filter would have nothing behind it to sample.

   So each plate is its own layer outside the reveal clip, sized one unit past
   the native 202 x 60 Explore control and the 88-unit Play control. The small
   overshoot lets the frost meet the button edge instead of stopping inside it. */
.pill-glass {
  position: absolute;
  z-index: 4;
  left: calc(644 * var(--u));
  top: calc(360 * var(--u));
  width: calc(204 * var(--u));
  height: calc(62 * var(--u));
  margin: calc(-31 * var(--u)) 0 0 calc(-102 * var(--u));
  border-radius: 999px;
  pointer-events: none;
  -webkit-backdrop-filter: blur(calc(13 * var(--u))) saturate(1.16);
  backdrop-filter: blur(calc(13 * var(--u))) saturate(1.16);
  background: rgba(${e.plate}, 0.22);
}

.play-wrap::before {
  content: "";
  position: absolute;
  z-index: -1;
  left: 50%;
  top: 50%;
  width: calc(90 * var(--u));
  height: calc(90 * var(--u));
  margin: calc(-45 * var(--u)) 0 0 calc(-45 * var(--u));
  border-radius: 50%;
  -webkit-backdrop-filter: blur(calc(13 * var(--u))) saturate(1.16);
  backdrop-filter: blur(calc(13 * var(--u))) saturate(1.16);
  background: rgba(${e.plate}, 0.22);
}
</style>`}var pp={"sakura-sunset":{style:sd,apply:dd},"maple-autumn":{style:ud,apply:pd},"sequoia-mist":{style:cd,apply:hd}};function fp(e){let t=pp[e],n=ld.replaceAll(md,cp).replace("</head>",`${t.style}${hp(dp[e])}</head>`).replace('<div class="pill-clip">',`<span class="pill-glass" aria-hidden="true"></span>
    <div class="pill-clip">`);if(!n.includes("pill-glass"))throw new Error("Sylva hero chrome no longer matches the authored page.");return t.apply(n)}var gp={"living-green":"Sylva \u2014 Into the living world","sakura-sunset":"Sylva \u2014 Sakura Sunset","maple-autumn":"Sylva \u2014 Maple Autumn","sequoia-mist":"Sylva \u2014 Sequoia Mist"};function vd({variant:e="living-green",...t}){let n=up.includes(e)?e:"living-green",[r,a]=Yc(t),i=Xc(od,r),o=(0,fd.useMemo)(()=>n==="living-green"?void 0:fp(n),[n]);return(0,wd.createElement)(rd,{...a,key:n,customization:i,title:gp[n],sourceUrl:gd,srcDoc:o})}var La=ce($t(),1);function mp(e){let t=e.contentDocument;if(!t?.querySelector("#hero"))return;t.getElementById("login-presentation")?.remove();let n=t.createElement("style");n.id="login-presentation",n.textContent=`
    html,body { width:100%; height:100%; overflow:hidden; }
    .hero { height:100vh; min-height:0; }
    .dock-wrap, .stage > * { visibility:hidden!important; pointer-events:none!important; }
  `,t.head.append(n),t.querySelectorAll(".dock-wrap, .stage > *").forEach(r=>{r.setAttribute("inert",""),r.setAttribute("aria-hidden","true")}),e.title="\u82D4\u85D3\u3001\u82B1\u6735\u4E0E\u8774\u8776\u7684\u7EFF\u8272\u573A\u666F",e.tabIndex=-1,document.documentElement.classList.add("scene-loaded"),e.contentWindow?.dispatchEvent(new Event("resize"))}function vp(){return(0,La.jsx)("div",{className:"shader-frame",children:(0,La.jsx)(vd,{variant:"living-green",headingFont:"lexend",bodyFont:"lexend",headingWeight:"300",bodyWeight:"300",primaryColor:"#ffffff",headingSize:63,bodySize:16.5,headingLetterSpacing:-.006,applyScene:mp})})}var yd=document.getElementById("login-background");yd&&(0,bd.createRoot)(yd).render((0,La.jsx)(vp,{}));export{vp as Scene};
/*! For license information please see background.js.LEGAL.txt */
