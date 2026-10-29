/**
 * LEX-3554 — move records between organizations.
 *
 * Page object and API helpers for the Move dialog. Selectors come from the live UAT walk
 * (explore/flow.md steps 1-21). API calls mirror the walked requests.
 *
 * Account and organization IDs are the UAT sandbox values seen in the walk:
 *   E2E Demo              01a0ee54-00c2-7054-ae8b-a4cb9e1b7d8b (account id = primary org)
 *   Adipiscing Aliqua     01a0ee75-1ca6-7246-98c4-55ecccd61500
 *   Adipiscing Foundation 01a0ee75-1aa8-72f7-b4a4-49e156596c06
 */
import { expect, type APIResponse, type Page } from '@playwright/test'

export const APP_URL = 'https://e2e-test.uat.lexful.net'
export const API_URL = 'https://api.uat.lexful.net'
export const ACCOUNT_ID = '01a0ee54-00c2-7054-ae8b-a4cb9e1b7d8b'
export const ORG_ADIPISCING_ALIQUA = { id: '01a0ee75-1ca6-7246-98c4-55ecccd61500', name: 'Adipiscing Aliqua Academy' }
export const ORG_ADIPISCING_FOUNDATION = { id: '01a0ee75-1aa8-72f7-b4a4-49e156596c06', name: 'Adipiscing Foundation' }

export const PASSWORDS_URL = `${APP_URL}/docs/d/all/system.password`
export const DOCUMENTS_URL = `${APP_URL}/docs/d/all/system.document`

export interface AssetRow {
  id: string
  name: string
  organization_id: string
  organization_name: string
}

export interface PreviewRow {
  id: string
  name: string
  reason: string | null
  reason_code: string | null
}

function escapeRe(text: string): RegExp {
  return new RegExp('^' + text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
}

function apiHeaders(json = false): Record<string, string> {
  const headers: Record<string, string> = { 'X-Account-Id': ACCOUNT_ID }
  if (json) headers['Content-Type'] = 'application/json'
  return headers
}

/** Read the first page of assets of one type through the API the Assets list uses. */
export async function listAssets(page: Page, assetType: 'system.password' | 'system.document'): Promise<AssetRow[]> {
  const res = await page.request.get(
    `${API_URL}/v1/assets/${assetType}?limit=100&sort=name%2Cid&order=ASC`,
    { headers: apiHeaders() },
  )
  expect(res.status()).toBe(200)
  const body = (await res.json()) as { items: AssetRow[] }
  return body.items
}

export async function getAsset(page: Page, assetType: string, id: string): Promise<AssetRow> {
  const res = await page.request.get(`${API_URL}/v1/assets/${assetType}/${id}`, { headers: apiHeaders() })
  expect(res.status()).toBe(200)
  return (await res.json()) as AssetRow
}

/** Preview a move. Read only. Returns the parsed rows. */
export async function previewMove(
  page: Page,
  assetType: string,
  ids: string[],
  organizationId: string,
): Promise<{ status: number; rows: PreviewRow[] }> {
  const res: APIResponse = await page.request.post(`${API_URL}/v1/assets/jobs/move/preview`, {
    headers: apiHeaders(true),
    data: { asset_ids: ids, asset_type: assetType, organization_id: organizationId },
  })
  const status = res.status()
  if (status !== 200) return { status, rows: [] }
  return { status, rows: (await res.json()) as PreviewRow[] }
}

/** Pick the first asset the preview says is eligible for the destination organization. */
export async function pickEligibleAsset(
  page: Page,
  assetType: 'system.password' | 'system.document',
  destination: { id: string },
): Promise<AssetRow> {
  // Some UAT documents have a whitespace-only name. The palette cannot find them by name, so skip them.
  const candidates = (await listAssets(page, assetType)).filter(
    (asset) => asset.organization_id !== destination.id && asset.name.trim().length > 0,
  )
  for (const asset of candidates.slice(0, 20)) {
    const preview = await previewMove(page, assetType, [asset.id], destination.id)
    if (preview.status === 200 && preview.rows[0]?.reason_code === null) return asset
  }
  throw new Error(`No eligible ${assetType} record found to move to ${destination.id}`)
}

/** Move one record back to its original organization through the API, then wait for the list to reflect it. */
export async function moveAssetBack(
  page: Page,
  assetType: string,
  id: string,
  organizationId: string,
): Promise<void> {
  const res = await page.request.post(`${API_URL}/v1/assets/jobs/move`, {
    headers: apiHeaders(true),
    data: { asset_ids: [id], asset_type: assetType, organization_id: organizationId },
  })
  expect(res.status()).toBe(202)
  await expect
    .poll(async () => (await getAsset(page, assetType, id)).organization_id, { timeout: 30000 })
    .toBe(organizationId)
}

/** Open the Ctrl-K palette, search the exact record name, and click its match. */
export async function openRecordFromPalette(page: Page, name: string): Promise<void> {
  const search = page.getByRole('combobox', { name: 'Search assets' })
  // The header button can be clicked before the SPA hydrates, so retry the open until the box appears.
  await expect(async () => {
    await page.getByRole('button', { name: 'Search... Ctrl K' }).click()
    await expect(search).toBeVisible({ timeout: 2000 })
  }).toPass({ timeout: 20000 })
  await search.fill(name)
  await page.getByRole('option', { name: escapeRe(name) }).first().click()
}

/** Navigate to a list. UAT sometimes answers with a CloudFront 403 page; reload until the app shell renders. */
export async function gotoApp(page: Page, url: string): Promise<void> {
  for (let attempt = 1; attempt <= 3; attempt++) {
    await page.goto(url, { waitUntil: 'domcontentloaded' })
    const blocked = page.getByRole('heading', { name: '403 ERROR' })
    const shell = page.getByRole('heading', { level: 1 })
    await expect(blocked.or(shell).first()).toBeVisible({ timeout: 15000 })
    if (!(await blocked.isVisible())) return
  }
  throw new Error(`CloudFront 403 persisted for ${url} after 3 navigations`)
}

export class MovePage {
  constructor(private readonly page: Page) {}

  /** The Move dialog for one record. `heading` is e.g. "Move 1 password". */
  dialog(noun: 'password' | 'document') {
    return this.page
      .getByRole('dialog')
      .filter({ has: this.page.getByRole('heading', { level: 2, name: `Move 1 ${noun}` }) })
  }

  destinationField(noun: 'password' | 'document') {
    return this.dialog(noun).getByRole('combobox')
  }

  submitButton(noun: 'password' | 'document') {
    return this.dialog(noun).getByRole('button', { name: `Move ${noun}`, exact: true })
  }

  cancelButton(noun: 'password' | 'document') {
    return this.dialog(noun).getByRole('button', { name: 'Cancel', exact: true })
  }

  /** Open the record drawer's "More actions" menu and choose Move. */
  async openMoveFromDrawer(): Promise<void> {
    await this.page.getByRole('button', { name: 'More actions', exact: true }).last().click()
    await this.page.getByRole('menuitem', { name: 'Move…', exact: true }).click()
  }

  /** Choose a destination by its visible name. */
  async chooseDestination(noun: 'password' | 'document', organizationName: string): Promise<void> {
    await this.destinationField(noun).click()
    await this.page
      .getByRole('listbox', { name: 'Suggestions' })
      .getByRole('option', { name: organizationName, exact: true })
      .click()
  }
}
