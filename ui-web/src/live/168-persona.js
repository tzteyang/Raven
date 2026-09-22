/* -- personas: the rpc source ----------------------------------------
   The island talks to DS.persona and knows nothing about transport; this file
   only knows how to read the library over /rpc. Installing onto the same name
   is what swaps the fixture wall for what is really on disk.

   One call, not a second surface: a Persona IS a stored artifact, so the wall
   reads the same listing the playbook page does and narrows it in the island.
   Giving personas their own list method would let the two answers disagree
   about the same file. */
DS.persona = {
  list: () => rpc.call('playbooks.list', {}).then((r) => (r && r.playbooks) || []),
};
