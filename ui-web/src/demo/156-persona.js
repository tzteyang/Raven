/* ══ module 3b1: digital personas ═════════════════════════════════
   The renderer is the persona island (ui-web/src/features/persona/): the wall
   of saved Personas and the one button that starts a conversation on one.
   What lives here is the shell face -- the two verbs the rail and Escape call
   -- and the fixture wall, so the page is explorable with no engine behind it.

   The fixtures are wire-shaped (snake_case, exactly what playbooks.list
   answers), because the island is the same code in both modes and a fixture in
   the island's own shape would hide a mapping bug until live. */

function openPersona() { RavenIslands.persona.open(); }
function closePersona() { RavenIslands.persona.close(); }
function drawPersona() {
  /* A language flip re-renders #personaBody with the new catalogue. */
  RavenIslands.persona.redraw();
}

const PERSONA_FIXTURE = [
  {
    name: 'travel-concierge',
    description: 'Turns a destination, dates, a budget, companions and a pace into a six-part brief you can walk',
    artifact_kind: 'harness',
    coordinator: true,
    workers: [
      { label: 'destination-intel', agent: 'Raven-Research' },
      { label: 'route-planner', agent: 'Raven-Research' },
      { label: 'brief-editor', agent: 'Raven-Design' },
      { label: 'booking-monitor', agent: 'Raven-OnCall' },
    ],
    origin: 'user',
    disabled: false,
    error: '',
  },
  {
    name: 'skeptical-fact-checker',
    description: 'Finds a primary source for every claim, and says so plainly when there is none',
    artifact_kind: 'harness',
    coordinator: true,
    workers: [{ label: 'evidence', agent: 'Raven-Research' }],
    origin: 'user',
    disabled: false,
    error: '',
  },
];

DS.persona = { list: () => Promise.resolve(PERSONA_FIXTURE) };
