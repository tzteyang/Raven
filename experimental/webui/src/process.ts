/* A playbook node's process as /api/node serves it: the steps its sub-agent
   took (tool calls, messages, thoughts, stderr, questions and approvals), its
   prompt, its output and the judge's verdict, and the helpers the node card
   and the process panel draw it with. The server reads the record's
   transcript once a node has finished, the sub-harness's ACP frame journal
   while it runs, and the worker log's model calls for an in-process node. */

export type StepKind = 'tool' | 'message' | 'thought' | 'input' | 'stderr' | 'permission' | 'question' | 'error' | 'plan'

export interface ProcessStep {
  kind: StepKind
  /** Epoch ms, or null when the source keeps no clock (an in-process node's model calls). */
  time: number | null
  text?: string
  /** The full length of a text step; `text` may be cut shorter. */
  length?: number
  level?: 'info' | 'warning' | 'error'
  id?: string
  name?: string
  title?: string
  tool_kind?: string | null
  args?: string
  input?: string
  status?: string
  result?: string
  result_length?: number
  ended?: number | null
}

export interface Verdict {
  outcome: string
  reason: string
}

export type ProcessSource = 'transcript' | 'journal' | 'provider' | 'none'

export interface ProcessCounts {
  tools: number
  failed: number
  running: number
  messages: number
  thoughts: number
  thought_chars: number
  errors: number
}

export interface NodeProcess {
  dag: string
  node: string
  subagent: string | null
  summary: string | null
  status: string
  started_at: number | null
  ended_at: number | null
  error: string | null
  /** "acp" for an external sub-harness, "in-process" for a node Raven runs itself, null when neither left a trace. */
  lane: 'acp' | 'in-process' | null
  source: ProcessSource
  available: Record<Exclude<ProcessSource, 'none'>, boolean>
  attempt: number | null
  attempts: number[]
  title: string | null
  stop_reason: string | null
  counts: ProcessCounts
  last: string | null
  /** When the latest dated step happened (epoch ms), or null when the source keeps no clock. */
  last_at: number | null
  /** Early steps left out of `steps` to keep the reply small. */
  omitted: number
  verdicts: Verdict[]
  prompt_source: string | null
  prompt_length: number
  output_length: number
  /** Absent in a summary reply. */
  steps?: ProcessStep[]
  prompt?: string | null
  output?: string | null
}

export const SOURCE_LABEL: Record<ProcessSource, string> = {
  transcript: 'record transcript',
  journal: 'frame journal',
  provider: 'worker log',
  none: 'no trace yet',
}

export const SOURCE_HINT: Record<ProcessSource, string> = {
  transcript: "The node's provider-shaped transcript, kept in the record's agent home once the node finished",
  journal: "The sub-harness's ACP frames under the run's state root; the only source that grows while it runs",
  provider: "The in-process node's model calls in the worker log; the latest call carries the conversation so far",
  none: 'Nothing of this node has been written yet',
}

export const plural = (count: number, word: string): string => `${count} ${word}${count === 1 ? '' : 's'}`

const cut = (text: string, limit: number): string => (text.length > limit ? `${text.slice(0, limit - 3)}...` : text)

/** The node card's one-line tally: "running · 12 tool calls · last: web_search: ...". */
export function tally(status: string, process: Pick<NodeProcess, 'counts' | 'last'> | null, limit = 90): string {
  const parts = [status]
  if (process) {
    const { counts } = process
    parts.push(plural(counts.tools, 'tool call'))
    if (counts.failed) parts.push(`${counts.failed} failed`)
    if (status === 'running' && process.last) parts.push(`last: ${cut(process.last, limit)}`)
  }
  return parts.join(' · ')
}

/** How long an interrupted node ran: to its own last dated step when that is later than the run's last event. */
export function ranFor(startedAt: number | null, frozenEnd: number | null, lastAt: number | null | undefined): number | null {
  if (startedAt === null) return null
  const end = Math.max(frozenEnd ?? -Infinity, lastAt ?? -Infinity)
  return Number.isFinite(end) ? Math.max(0, end - startedAt) : null
}

/** Whether a node's process can still grow, so its panel keeps polling. */
export const growing = (status: string): boolean => status === 'running' || status === 'pending'

export type ToolState = 'running' | 'done' | 'failed' | 'pending' | 'unknown' | 'interrupted'

/** A tool call's state; one still open when its run stopped (`over`) reads as interrupted. */
export function toolState(step: ProcessStep, over = false): ToolState {
  if (over && (step.status === 'running' || step.status === 'pending')) return 'interrupted'
  switch (step.status) {
    case 'running':
      return 'running'
    case 'pending':
      return 'pending'
    case 'completed':
      return 'done'
    case 'failed':
    case 'cancelled':
      return 'failed'
    default:
      return 'unknown'
  }
}

/** A tool call as its name and the rest of the line: the title past the name, else the arguments. */
export function toolLine(step: ProcessStep): { name: string; detail: string } {
  const name = step.name || step.title || 'tool'
  const title = step.title ?? ''
  if (title.startsWith(`${name}: `)) return { name, detail: title.slice(name.length + 2) }
  if (title && title !== name) return { name, detail: title }
  return { name, detail: step.args ?? '' }
}

/** When a step happened: "+m:ss" from the node's start, else the clock time, else nothing. */
export function when(time: number | null | undefined, started: number | null | undefined): string {
  if (time == null) return ''
  if (started != null && time >= started - 1000) {
    const seconds = Math.max(0, Math.round((time - started) / 1000))
    const hours = Math.floor(seconds / 3600)
    const minutes = Math.floor((seconds % 3600) / 60)
    const rest = String(seconds % 60).padStart(2, '0')
    return hours ? `+${hours}:${String(minutes).padStart(2, '0')}:${rest}` : `+${minutes}:${rest}`
  }
  return new Date(time).toLocaleTimeString()
}

const grouped = new Intl.NumberFormat('en-US')

/** A thought's fold label, saying how much of it the reply carries when it was cut. */
export function thoughtLabel(step: ProcessStep): string {
  const length = step.length ?? step.text?.length ?? 0
  return `Thought · ${grouped.format(length)} chars`
}

export const wasCut = (step: ProcessStep): boolean => (step.length ?? 0) > (step.text?.length ?? 0)

/** The first line of a text step, for a folded preview. */
export function firstLine(text: string | undefined, limit = 140): string {
  const line = (text ?? '').trim().split('\n').find((row) => row.trim()) ?? ''
  return cut(line.trim(), limit)
}

/** How a question or approval the sub-harness raised was answered. */
export function answerLabel(step: ProcessStep): string {
  const status = step.status ?? ''
  if (step.kind === 'permission') return status === 'selected' ? 'approved' : status === 'asked' ? 'waiting' : status
  if (step.kind === 'question') return status === 'decline' ? 'no one answered' : status === 'asked' ? 'waiting' : status
  return status
}

/** The sources a reader can switch between, in the order the panel offers them. */
export function sources(process: Pick<NodeProcess, 'available'>): Exclude<ProcessSource, 'none'>[] {
  return (['transcript', 'journal', 'provider'] as const).filter((source) => process.available[source])
}

export const grouping = (count: number): string => grouped.format(count)

/** How often a running node's process is re-read: the live view's own cadence while a trial runs. */
export const PROCESS_POLL = 3000
