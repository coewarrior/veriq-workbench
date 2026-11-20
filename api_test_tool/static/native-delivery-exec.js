// Coordinator only: one invocation matches the event, acknowledges, then audits.
// No browser work, business replay, model-written result text or receipt polling.
const quote = value => "'" + String(value).replace(/'/g, "'\\''") + "'";
async function command(args) {
  let r = await tools.exec_command({cmd: [...config.command, ...args].map(quote).join(' '),
    yield_time_ms: 10000, max_output_tokens: 16000});
  let output = r.output;
  while (r.session_id && r.exit_code == null) {
    r = await tools.write_stdin({session_id:r.session_id,chars:'',yield_time_ms:1000,max_output_tokens:16000});
    output += r.output;
  }
  if (r.exit_code !== 0) throw new Error(output.slice(-3000));
  return JSON.parse(output);
}
if (!input || input.task_id !== config.task_id || input.node_id !== config.node_id || !input.event_id)
  throw new Error('Incoming handoff does not match original assignment');
const generated = await command(['native-ack-script', '--assignment-file', config.assignment_file,
  '--binding-file', config.directory + '/binding.json', '--event-json', JSON.stringify(input)]);
let ack;
const AF = Object.getPrototypeOf(async function(){}).constructor;
await new AF('tools','text','ALL_TOOLS',generated.script)(tools,value=>{ack=value;},ALL_TOOLS);
const ackFile = config.directory + '/coordinator-ack-' + Date.now() + '.json';
await tools.apply_patch('*** Begin Patch\n*** Add File: ' + ackFile + '\n+'
  + JSON.stringify(ack,null,2).replace(/\n/g,'\n+') + '\n*** End Patch');
const outputFile = config.output_file || config.directory + '/delivery-' + Date.now() + '.json';
const delivered = await command(['native-cycle-audit','--binding-file',config.directory+'/binding.json',
  '--ack-file',ackFile,'--output-file',outputFile]);
// This is already the deliverable. Display it directly; do not reconstruct it.
text(delivered);
