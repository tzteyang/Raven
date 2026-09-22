/* What the persona wall reads. A Persona is a stored Harness carrying a
 * coordinator seat: the durable identity a conversation runs as, rather than
 * a graph a turn dispatches. The wire shape is `playbooks.list`'s row, narrowed
 * here to the fields the wall shows, so a row growing a field the page does not
 * draw is not a change this page has to make.
 */

export interface PersonaRow {
  name: string
  description: string
  artifact_kind: 'legacy' | 'workflow' | 'harness' | 'composite'
  coordinator: boolean
  workers: { label: string; agent: string }[]
  origin: string
  disabled: boolean
  error: string
}

export interface PersonaSource {
  list(): Promise<PersonaRow[]>
}
