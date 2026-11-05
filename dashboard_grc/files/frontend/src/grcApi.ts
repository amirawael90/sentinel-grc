import { ApiError, getToken } from './api/client'

async function authorizedFetch(path: string): Promise<Response> {
  const headers = new Headers()
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(path, { headers })
  if (!response.ok) {
    let detail = response.statusText
    try {
      detail = (await response.json()).detail || detail
    } catch {
      // ignore
    }
    throw new ApiError(response.status, detail)
  }
  return response
}

/** Fetch a protected file (PDF, CSV) and return a temporary URL the browser can show or download. */
export async function fetchBlobUrl(path: string): Promise<string> {
  const response = await authorizedFetch(path)
  return URL.createObjectURL(await response.blob())
}

export async function downloadFile(path: string, filename: string): Promise<void> {
  const url = await fetchBlobUrl(path)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
