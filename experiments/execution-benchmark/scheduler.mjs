// The graph is supplied by the experiment, not inferred from a model in this prototype.
export function schedule(nodes, mode) {
  const remaining=new Map(nodes.map((n,index)=>[n.id,{...n,index}])),done=new Set(),ordered=[];
  if(remaining.size!==nodes.length)throw Error('Duplicate graph node');
  for(const node of nodes)for(const dep of node.dependsOn||[])if(!remaining.has(dep))throw Error(`Unknown prerequisite: ${dep}`);
  while(remaining.size){
    const ready=[...remaining.values()].filter(n=>(n.dependsOn||[]).every(id=>done.has(id)));
    if(!ready.length)throw Error('Cyclic execution graph');
    ready.sort((a,b)=>mode==='stateful'?(b.priority-a.priority||a.index-b.index):a.index-b.index);
    const next=ready[0];ordered.push(next);done.add(next.id);remaining.delete(next.id);
  }
  return ordered;
}
