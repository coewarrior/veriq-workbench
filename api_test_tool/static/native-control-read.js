// Full control results are private files. Terminal text is never the result protocol.
async function nativeReadControl(tools, command, file) {
  const quote = value => "'" + String(value).replace(/'/g, "'\\''") + "'";
  let offset = 0, content = '';
  while (true) {
    const args = [...command, 'native-control-read', '--file', file, '--offset', String(offset)];
    let execution = await tools.exec_command({cmd:args.map(quote).join(' '), max_output_tokens:12000, yield_time_ms:10000});
    let output = execution.output;
    while (execution.session_id && execution.exit_code == null) {
      execution = await tools.write_stdin({session_id:execution.session_id, chars:'', max_output_tokens:12000, yield_time_ms:1000});
      output += execution.output;
    }
    if (execution.exit_code !== 0) throw new Error('Original control receipt unavailable; do not replay the operation');
    const frames = output.split('\n').filter(line => line.startsWith('NATIVE_CONTROL_PART:'));
    if (frames.length !== 1) throw new Error('Control receipt frame missing or ambiguous; do not replay');
    const part = JSON.parse(frames[0].slice('NATIVE_CONTROL_PART:'.length));
    if (part.file !== file || part.offset !== offset || typeof part.text !== 'string' ||
        part.next !== offset + part.text.length || (!part.eof && part.next <= offset))
      throw new Error('Control receipt sequence changed; preserve original files');
    content += part.text;
    if (part.eof) return JSON.parse(content);
    offset = part.next;
  }
}
