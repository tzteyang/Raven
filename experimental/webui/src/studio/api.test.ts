/* Employee downloads accept ZIP packages, surface server errors, and release the browser's temporary URL. */

import { afterEach, beforeEach, expect, test, vi } from 'vitest'

import { exportLive } from './api'
import { T } from './copy'

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('fetch', vi.fn())
  vi.stubGlobal('URL', class extends URL {
    static createObjectURL = vi.fn(() => 'blob:employee-package')
    static revokeObjectURL = vi.fn()
  })
})

afterEach(() => {
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

test('downloads the named employee ZIP with the session cookie and releases its URL after the browser starts it', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response('employee package', {
    headers: { 'Content-Type': 'application/zip', 'Content-Disposition': 'attachment; filename="agency-v2.zip"' },
  }))
  let saved: HTMLAnchorElement | undefined
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) {
    saved = this
    expect(document.body.contains(this)).toBe(true)
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
  })

  await exportLive('session/id')

  expect(fetch).toHaveBeenCalledWith('/api/studio/live/session%2Fid/export', { credentials: 'same-origin' })
  expect(saved?.download).toBe('agency-v2.zip')
  expect(saved?.href).toBe('blob:employee-package')
  expect(saved?.isConnected).toBe(false)
  expect(URL.createObjectURL).toHaveBeenCalledOnce()
  expect(URL.revokeObjectURL).not.toHaveBeenCalled()
  vi.runOnlyPendingTimers()
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:employee-package')
})

test.each([404, 409, 200])('shows a JSON error instead of downloading it, including status %s', async (status) => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ error: 'No saved employee' }), {
    status, headers: { 'Content-Type': 'application/json' },
  }))
  await expect(exportLive('session')).rejects.toThrow('No saved employee')
  expect(URL.createObjectURL).not.toHaveBeenCalled()
})

test('rejects an HTML response from an expired login instead of saving it as a package', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response('<form>Sign in</form>', { headers: { 'Content-Type': 'text/html' } }))
  await expect(exportLive('session')).rejects.toThrow(T.exportInvalid)
  expect(URL.createObjectURL).not.toHaveBeenCalled()
})

test('keeps a safe filename when the response does not name a package', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response('employee package', {
    headers: { 'Content-Type': 'application/zip', 'Content-Disposition': 'attachment; filename="../../agent.zip"' },
  }))
  let name: string | undefined
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (this: HTMLAnchorElement) { name = this.download })
  await exportLive('session')
  expect(name).toBe('employee.zip')
})

test('releases the URL and removes the temporary link when the browser cannot start the download', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response('employee package', { headers: { 'Content-Type': 'application/zip' } }))
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => { throw new Error('Download blocked') })
  await expect(exportLive('session')).rejects.toThrow('Download blocked')
  expect(document.querySelector('a[download]')).toBeNull()
  vi.runOnlyPendingTimers()
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:employee-package')
})
