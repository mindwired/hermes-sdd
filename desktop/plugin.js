import {
  host,
  useValue,
  useQuery,
  useMutation,
  useQueryClient,
  Button,
  Input,
  Badge,
  Loader,
  ErrorState,
  EmptyState,
  ROUTES_AREA,
  SIDEBAR_NAV_AREA,
  STATUSBAR_AREAS,
  PALETTE_AREA
} from '@hermes/plugin-sdk'
import { useState } from 'react'
import { jsx, jsxs, Fragment } from 'react/jsx-runtime'

let pluginCtx = null

function rootPath() {
  return host.state.cwd.get() || ''
}

async function callOperation(operation, root, target = null, payload = {}, options = {}) {
  return pluginCtx.rest('/operation', {
    method: 'POST',
    body: { operation, root, target, payload, options }
  })
}

function useSnapshot(root) {
  return useQuery({
    queryKey: ['sdd', 'snapshot', root],
    enabled: Boolean(root),
    retry: false,
    refetchInterval: 15000,
    queryFn: () => pluginCtx.rest(`/snapshot?root=${encodeURIComponent(root)}`)
  })
}

function Stat({ label, value, detail }) {
  return jsxs('div', {
    className: 'rounded-md border border-(--ui-stroke-secondary) p-3',
    children: [
      jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: label }),
      jsx('div', { className: 'mt-1 text-lg font-semibold', children: String(value ?? '—') }),
      detail ? jsx('div', { className: 'mt-1 text-xs text-(--ui-text-quaternary)', children: detail }) : null
    ]
  })
}

function TaskRow({ task, root, refresh }) {
  const [busy, setBusy] = useState(false)
  async function transition(status) {
    setBusy(true)
    try {
      let payload = { status }
      if (status === 'done') {
        payload = {
          status,
          summary: 'Implementation complete; verification pending',
          evidence: { type: 'manual', result: 'verification pending', passed: false }
        }
      }
      await callOperation('transition', root, task.id, payload)
      await refresh()
    } catch (error) {
      host.notifyError(error, 'Could not update SDD task')
    } finally {
      setBusy(false)
    }
  }
  async function copyContext() {
    setBusy(true)
    try {
      const result = await pluginCtx.rest(`/context?root=${encodeURIComponent(root)}&task_id=${encodeURIComponent(task.id)}`)
      await navigator.clipboard.writeText(result.text || '')
      host.notify({ kind: 'success', message: `Copied ${result.estimated_tokens || 'bounded'} token context for ${task.id}` })
    } catch (error) {
      host.notifyError(error, 'Could not create context pack')
    } finally {
      setBusy(false)
    }
  }
  return jsxs('div', {
    className: 'flex flex-wrap items-start justify-between gap-3 rounded-md border border-(--ui-stroke-secondary) p-3',
    children: [
      jsxs('div', {
        className: 'min-w-0 flex-1',
        children: [
          jsx('div', { className: 'font-medium', children: `${task.id} — ${task.title}` }),
          jsx('div', { className: 'mt-1 text-xs text-(--ui-text-tertiary)', children: task.objective || '' }),
          task.status === 'done' && (!task.evidence_ids || task.evidence_ids.length === 0)
            ? jsx('div', { className: 'mt-1 text-xs text-(--ui-text-tertiary)', children: 'Implementation complete; verification pending' })
            : null,
          jsxs('div', { className: 'mt-2 flex gap-2', children: [jsx(Badge, { variant: 'outline', children: task.status }), jsx(Badge, { variant: 'outline', children: task.risk })] })
        ]
      }),
      jsxs('div', {
        className: 'flex flex-wrap gap-2',
        children: [
          jsx(Button, { variant: 'outline', size: 'sm', disabled: busy, onClick: copyContext, children: 'Copy context' }),
          task.status === 'pending' ? jsx(Button, { size: 'sm', disabled: busy, onClick: () => transition('in_progress'), children: 'Start' }) : null,
          task.status === 'in_progress' ? jsx(Button, { size: 'sm', disabled: busy, onClick: () => transition('done'), children: 'Implementation complete' }) : null,
          task.status === 'done' && (!task.evidence_ids || task.evidence_ids.length === 0)
            ? jsx(Button, { variant: 'outline', size: 'sm', disabled: busy, onClick: () => transition('done'), children: 'Record verification' })
            : null
        ]
      })
    ]
  })
}

function SddPage() {
  const cwd = useValue(host.state.cwd)
  const queryClient = useQueryClient()
  const { data, isLoading, error, refetch } = useSnapshot(cwd)
  const [goal, setGoal] = useState('')
  const initialize = useMutation({
    mutationFn: () => callOperation('init', cwd, null, { mode: 'auto', goal, name: cwd.split(/[\\/]/).pop() }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['sdd', 'snapshot', cwd] }),
    onError: (failure) => host.notifyError(failure, 'Could not initialize SDD')
  })
  const validate = useMutation({
    mutationFn: () => callOperation('validate', cwd, null, { record: true }),
    onSuccess: (result) => {
      host.notify({ kind: result.ok ? 'success' : 'warning', message: `SDD health ${result.score}` })
      queryClient.invalidateQueries({ queryKey: ['sdd', 'snapshot', cwd] })
    },
    onError: (failure) => host.notifyError(failure, 'Could not validate SDD')
  })

  if (!cwd) return jsx(EmptyState, { title: 'No project folder', description: 'Open a project directory to use SDD.' })
  if (isLoading) return jsx(Loader, {})
  if (error) {
    return jsxs('div', {
      className: 'flex h-full flex-col gap-4 overflow-auto p-5',
      children: [
        jsx(ErrorState, { title: 'No SDD project in this folder', error }),
        jsx('div', { className: 'text-sm text-(--ui-text-tertiary)', children: cwd }),
        jsx(Input, { value: goal, onChange: (event) => setGoal(event.target.value), placeholder: 'Project goal' }),
        jsx(Button, { disabled: initialize.isPending, onClick: () => initialize.mutate(), children: initialize.isPending ? 'Initializing…' : 'Initialize .sdd' })
      ]
    })
  }

  const counts = data.task_counts || {}
  const total = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0)
  const wave = data.next?.wave || []
  return jsxs('div', {
    className: 'flex h-full flex-col gap-4 overflow-auto p-5 text-sm',
    children: [
      jsxs('div', {
        className: 'flex flex-wrap items-start justify-between gap-3',
        children: [
          jsxs('div', { children: [jsx('h1', { className: 'text-xl font-semibold', children: data.project?.name || 'SDD' }), jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: cwd })] }),
          jsxs('div', { className: 'flex gap-2', children: [jsx(Button, { variant: 'outline', onClick: () => refetch(), children: 'Refresh' }), jsx(Button, { variant: 'outline', disabled: validate.isPending, onClick: () => validate.mutate(), children: 'Validate' })] })
        ]
      }),
      jsxs('div', {
        className: 'grid grid-cols-2 gap-3 xl:grid-cols-4',
        children: [
          jsx(Stat, { label: 'Health', value: data.health?.score, detail: JSON.stringify(data.health?.counts || {}) }),
          jsx(Stat, { label: 'Mode', value: data.project?.mode, detail: data.state?.status }),
          jsx(Stat, { label: 'Milestones', value: data.milestone_count, detail: data.state?.active_milestone || 'none' }),
          jsx(Stat, { label: 'Tasks', value: total, detail: JSON.stringify(counts) })
        ]
      }),
      jsxs('section', { children: [jsx('h2', { className: 'mb-2 font-semibold', children: 'Next safe wave' }), wave.length ? jsx('div', { className: 'flex flex-col gap-2', children: wave.map((task) => jsx(TaskRow, { task, root: cwd, refresh: refetch }, task.id)) }) : jsx('div', { className: 'text-(--ui-text-tertiary)', children: 'No dependency-ready task.' })] }),
      jsxs('section', { children: [jsx('h2', { className: 'mb-2 font-semibold', children: 'Active milestone' }), jsx('div', { className: 'flex flex-col gap-2', children: (data.active_tasks || []).map((task) => jsx(TaskRow, { task, root: cwd, refresh: refetch }, task.id)) })] }),
      jsxs('section', { children: [jsx('h2', { className: 'mb-2 font-semibold', children: 'Roadmap' }), jsx('div', { className: 'flex flex-col gap-2', children: (data.roadmap || []).map((item) => jsxs('div', { className: 'flex justify-between gap-3 rounded-md border border-(--ui-stroke-secondary) p-3', children: [jsxs('div', { children: [jsx('div', { className: 'font-medium', children: `${item.id} — ${item.title}` }), jsx('div', { className: 'text-xs text-(--ui-text-tertiary)', children: item.objective || '' })] }), jsx(Badge, { variant: 'outline', children: item.status })] }, item.id)) })] })
    ]
  })
}

function SddStatus() {
  const cwd = useValue(host.state.cwd)
  const { data } = useSnapshot(cwd)
  return jsx('button', {
    type: 'button',
    className: 'px-1.5 text-[0.6875rem] text-(--ui-text-tertiary)',
    onClick: () => host.navigate('/sdd'),
    children: data ? `SDD ${data.health?.score ?? '—'} · ${data.state?.active_milestone || 'idle'}` : 'SDD'
  })
}

export default {
  id: 'sdd',
  name: 'Spec-driven development',
  register(ctx) {
    pluginCtx = ctx
    ctx.registerMany([
      { id: 'page', area: ROUTES_AREA, data: { path: '/sdd' }, render: () => jsx(SddPage, {}) },
      { id: 'nav', area: SIDEBAR_NAV_AREA, data: { path: '/sdd', label: 'SDD', codicon: 'checklist' } },
      { id: 'status', area: STATUSBAR_AREAS.right, order: 118, render: () => jsx(SddStatus, {}) },
      { id: 'open', area: PALETTE_AREA, data: { id: 'sdd.open', label: 'Open SDD Project', keywords: ['spec', 'plan', 'roadmap'], run: () => host.navigate('/sdd') } }
    ])
  }
}
