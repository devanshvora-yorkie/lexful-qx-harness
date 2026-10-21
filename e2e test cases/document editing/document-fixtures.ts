import type { Page } from '@playwright/test'
import { ApiContext, DOCUMENT_TYPE } from './document-pom'
import { accountHeader, primeAccount } from './document-session'

export const TEST_ORGANIZATION = 'E2E Demo'

export const createdRecords: { id: string; api: ApiContext }[] = []

export function uniqueName(label: string) {
  return `${label} ${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`
}

export async function createDocument(
  page: Page,
  api: ApiContext,
  fields: { name: string; body?: string },
) {
  await primeAccount(page)
  const response = await page.request.post(`${api.apiBase()}/v1/assets/${DOCUMENT_TYPE}`, {
    headers: api.headers(),
    data: {
      name: fields.name,
      content: fields.body ?? '',
      organization_id: '01a0ee54-00c2-7054-ae8b-a4cb9e1b7d8b',
      visibility: 'inherit',
    },
  })
  if (!response.ok()) {
    throw new Error(`Create document failed HTTP ${response.status()}: ${await response.text()}`)
  }
  const payload = (await response.json()) as { id: string }
  createdRecords.push({ id: payload.id, api })
  return payload.id
}

/** Archive every document this worker created. An empty DELETE body must not send Content-Type. */
export async function cleanupCreatedRecords(page: Page) {
  const failures: string[] = []
  while (createdRecords.length) {
    const record = createdRecords.pop()
    if (!record) break
    try {
      const response = await page.request.delete(
        `${record.api.apiBase()}/v1/assets/${DOCUMENT_TYPE}/${record.id}`,
        { headers: { 'X-Account-Id': accountHeader() } },
      )
      if (response.status() !== 204 && response.status() !== 404) {
        failures.push(`${record.id} HTTP ${response.status()}`)
      }
    } catch (error) {
      failures.push(`${record.id} ${error instanceof Error ? error.message : String(error)}`)
    }
  }
  if (failures.length) {
    throw new Error(`Could not archive created documents: ${failures.join('; ')}`)
  }
}
