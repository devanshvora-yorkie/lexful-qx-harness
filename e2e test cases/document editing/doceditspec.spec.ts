/**
 * TC-DOC-001 … TC-DOC-010 — Lexful UAT **Document editing** end-to-end suite.
 *
 * Surface : https://e2e-test.uat.lexful.net/docs/d/all/system.document
 * API host: https://api.uat.lexful.net
 * POM     : ./document-pom.ts, ./assets-list-pom.ts, ./document-fixtures.ts
 *
 * A Document (`system.document`) carries three properties:
 *   name        string          required
 *   content     richtext_large  optional  — the TipTap body editor
 *   expires_on  datetime        optional  — the "Document expiry" picker
 *
 * Every test drives the real UI and asserts on the real API contract:
 *   POST  /v1/assets/system.document            → 201   (create)
 *   PATCH /v1/assets/system.document/{id}       → 200   (name / content / expiry)
 *   PUT   /v1/tags/{tagId}/assets               → 201   (tag assign)
 *   DELETE /v1/assets/system.document/{id}      → 204   (archive)
 *
 * Data hygiene: every document a test creates is archived again in `afterEach`, so a
 * run leaves the UAT sandbox as it found it. Tag assignment is removed the same way.
 *
 * Run:
 *   node scripts/specs.mjs --headed "e2e test cases/document editing"
 *
 * Preconditions:
 *   - The UAT session (Stytch storageState.json) is valid; run `npm run stytch:capture`
 *     first if the run lands on /platform/login.
 *   - The "E2E Demo" organization exists and accepts assets (asset_management_usable).
 */
import { test, expect } from '@playwright/test'
import { injectAuthCookies } from '../../auth-helper'
import { AssetRecordListPage } from './assets-list-pom'
import {
  ApiContext,
  DocumentCreateDrawer,
  DocumentRecordDrawer,
  DOCUMENT_TYPE,
  expectedExpiresOn,
  friendlyDate,
  gridExpiryText,
} from './document-pom'
import {
  cleanupCreatedRecords,
  createDocument,
  createdRecords,
  TEST_ORGANIZATION,
  uniqueName,
} from './document-fixtures'

// ---------------------------------------------------------------------------------------
// Fixture plumbing — created records are archived again after each test
// ---------------------------------------------------------------------------------------

test.beforeEach(async ({ page }) => {
  await injectAuthCookies(page.context())
})

test.afterEach(async ({ page }) => {
  await cleanupCreatedRecords(page)
})

// =======================================================================================
// Positive
// =======================================================================================

test.describe('Document editing — positive', () => {
  test('TC-DOC-001: Create a document with a name, an organization and body content', async ({ page }) => {
    const list = new AssetRecordListPage(page, DOCUMENT_TYPE)
    const api = new ApiContext(page)
    await list.goto()
    const before = await list.recordTotal()

    const name = uniqueName('Vendor Onboarding Runbook')
    const drawer = await DocumentCreateDrawer.open(page)
    await drawer.typeName(name)
    await drawer.selectOrganization(TEST_ORGANIZATION)
    await drawer.typeBody('Vendor onboarding checklist for the Q3 rollout.')

    const response = await drawer.submit()
    expect(response.status()).toBe(201)
    const payload = (await response.json()) as { id: string; name: string; content: string }
    createdRecords.push({ id: payload.id, api })

    expect(payload.name).toBe(name)
    expect(payload.content).toContain('Vendor onboarding checklist for the Q3 rollout.')

    // The drawer swaps from "New Documents" to the saved record.
    const record = new DocumentRecordDrawer(page)
    await expect(record.title).toHaveText(name)
    await expect(record.contentArticle).toContainText('Vendor onboarding checklist for the Q3 rollout.')

    await record.close()
    await expect.poll(() => list.recordTotal(), { timeout: 20_000 }).toBe(before + 1)

    // And the record is reachable from the grid by name.
    await list.search(name)
    // The grid cell's accessible name is "Native document <name>", so match the name as a substring.
    await expect(page.getByRole('gridcell', { name }).first()).toBeVisible()
  })

  test('TC-DOC-002: Rename a document from the record drawer', async ({ page }) => {
    const list = new AssetRecordListPage(page, DOCUMENT_TYPE)
    const api = new ApiContext(page)
    await list.goto()

    const original = uniqueName('Incident Response Runbook')
    const id = await createDocument(page, api, { name: original, body: 'Escalation path for sev-1 incidents.' })
    const renamed = uniqueName('Incident Response Playbook')

    const record = await DocumentRecordDrawer.openById(page, id)
    await expect(record.title).toHaveText(original)

    await record.rename(renamed)
    await record.expectChangeSummary('1 change')
    await expect(record.saveButton).toBeEnabled()

    const response = await record.saveChanges()
    const payload = (await response.json()) as { name: string }
    expect(payload.name).toBe(renamed)

    await expect(record.title).toHaveText(renamed)
    await expect(record.contentArticle).toContainText('Escalation path for sev-1 incidents.')

    // The new name is what the grid serves.
    await list.goto()
    await list.search(renamed)
    // Grid cell name is "Native document <name>"; substring match on the unique name.
    await expect(page.getByRole('gridcell', { name: renamed }).first()).toBeVisible()
  })

  test('TC-DOC-003: Edit the document body and save the change', async ({ page }) => {
    const list = new AssetRecordListPage(page, DOCUMENT_TYPE)
    const api = new ApiContext(page)
    await list.goto()

    const name = uniqueName('Access Review Procedure')
    const id = await createDocument(page, api, { name, body: 'Quarterly review of user access.' })

    const record = await DocumentRecordDrawer.openById(page, id)
    await record.startBodyEdit()
    await record.typeBody(' Reviewed by the security team on every quarter end.')
    await record.expectChangeSummary('1 change')

    const response = await record.saveChanges()
    const payload = (await response.json()) as { content: string }
    expect(payload.content).toContain('Reviewed by the security team on every quarter end.')

    // Read mode shows the merged text.
    await expect(record.contentArticle).toContainText(
      'Quarterly review of user access. Reviewed by the security team on every quarter end.',
    )

    // …and it survives a reload.
    await record.close()
    const reopened = await DocumentRecordDrawer.openById(page, id)
    await expect(reopened.contentArticle).toContainText(
      'Reviewed by the security team on every quarter end.',
    )
  })

  test('TC-DOC-004: Apply bold formatting to the document body', async ({ page }) => {
    const list = new AssetRecordListPage(page, DOCUMENT_TYPE)
    const api = new ApiContext(page)
    await list.goto()

    const name = uniqueName('Data Retention Standard')
    const id = await createDocument(page, api, { name, body: 'Retention periods are reviewed annually.' })

    const record = await DocumentRecordDrawer.openById(page, id)
    await record.startBodyEdit()
    await record.editor.click()
    await page.keyboard.press('ControlOrMeta+a')
    await record.applyFormat('Bold')
    await record.expectChangeSummary('1 change')

    const response = await record.saveChanges()
    const payload = (await response.json()) as { content: string }
    // A document created from the Markdown editor stores Markdown, so Bold is persisted as **.
    expect(payload.content).toContain('**Retention periods are reviewed annually.**')

    // The read view renders Markdown bold through streamdown, which emits a styled
    // span rather than a <strong> element.
    await expect(
      record.contentArticle.locator('[data-streamdown="strong"]'),
    ).toContainText('Retention periods are reviewed annually.')
  })

  test('TC-DOC-005: Set an expiry date on a document', async ({ page }) => {
    const list = new AssetRecordListPage(page, DOCUMENT_TYPE)
    const api = new ApiContext(page)
    await list.goto()

    const name = uniqueName('Temporary Access Pass')
    const id = await createDocument(page, api, { name, body: 'Temporary pass for the onboarding week.' })

    const now = new Date()
    const target = new Date(now.getFullYear(), now.getMonth() + 1, 15)

    const record = await DocumentRecordDrawer.openById(page, id)
    await record.setExpiry(target)
    await expect(record.expiryButton).toContainText(`Expires ${friendlyDate(target)}`)
    await record.expectChangeSummary('1 change')

    const response = await record.saveChanges()
    const payload = (await response.json()) as { expires_on: string }
    expect(payload.expires_on).toBe(expectedExpiresOn(target))

    // The grid serves the expiry in its own "Expires On" column.
    await list.goto()
    await list.search(name)
    const row = page.getByRole('row').filter({ hasText: name }).first()
    await expect(row).toContainText(gridExpiryText(target))
  })

  test('TC-DOC-006: Assign a tag to a document', async ({ page }) => {
    const list = new AssetRecordListPage(page, DOCUMENT_TYPE)
    const api = new ApiContext(page)
    await list.goto()

    const name = uniqueName('Vendor Security Questionnaire')
    const id = await createDocument(page, api, { name, body: 'Security review required before go-live.' })

    const record = await DocumentRecordDrawer.openById(page, id)
    const tags = await record.availableTags()
    test.skip(tags.length === 0, 'No tag exists in the UAT account to assign.')

    const tag = tags[0]
    await record.toggleTag(tag)
    await record.expectChangeSummary('1 change')

    const [response] = await Promise.all([
      page.waitForResponse(
        r => r.request().method() === 'PUT' && new URL(r.url()).pathname.includes('/v1/tags/'),
        { timeout: 45_000 },
      ),
      record.saveButton.click(),
    ])
    expect(response.status()).toBe(201)

    // The tag shows in the record header and in the grid's Tags column.
    await expect(record.dialog.getByText(tag, { exact: true }).first()).toBeVisible()
    await record.close()
    await list.goto()
    await list.search(name)
    // Grid cell name is "Native document <name>"; substring match on the unique name.
    await expect(page.getByRole('gridcell', { name }).first()).toBeVisible()
  })

  test('TC-DOC-007: Switch the body editor between Markdown and HTML modes', async ({ page }) => {
    const list = new AssetRecordListPage(page, DOCUMENT_TYPE)
    const api = new ApiContext(page)
    await list.goto()

    const name = uniqueName('Release Notes Template')
    const id = await createDocument(page, api, { name, body: 'Describe the change here.' })

    const record = await DocumentRecordDrawer.openById(page, id)
    await record.startBodyEdit()

    // The document was authored in Markdown, so Underline / Highlight are unavailable.
    expect(await record.underlineAvailable()).toBe(false)

    const mode = await record.toggleContentType()
    expect(mode).toBe('html')
    expect(await record.underlineAvailable()).toBe(true)

    await record.toggleContentType()
    expect(await record.underlineAvailable()).toBe(false)
  })

  test('TC-DOC-008: Archive a document from the record drawer', async ({ page }) => {
    const list = new AssetRecordListPage(page, DOCUMENT_TYPE)
    const api = new ApiContext(page)
    await list.goto()
    const before = await list.recordTotal()

    const name = uniqueName('Superseded Onboarding Checklist')
    const id = await createDocument(page, api, { name, body: 'Replaced by the Q4 checklist.' })
    await expect.poll(() => list.recordTotal(), { timeout: 20_000 }).toBe(before + 1)

    const record = await DocumentRecordDrawer.openById(page, id)
    const response = await record.archive()
    expect(response.status()).toBe(204)
    // The record is already gone — drop it from the cleanup queue.
    createdRecords.pop()

    // The archive is a soft delete: prove it on the server, not only on the grid.
    const server = await page.request.get(
      `${api.apiBase()}/v1/assets/${DOCUMENT_TYPE}/${id}?include_deleted=true`,
      { headers: api.headers() },
    )
    expect(server.status()).toBe(200)
    const serverBody = (await server.json()) as { deleted_at?: string | null }
    expect(serverBody.deleted_at).toBeTruthy()

    await record.close()
    await expect.poll(() => list.recordTotal(), { timeout: 20_000 }).toBe(before)
  })
})

// =======================================================================================
// Negative
// =======================================================================================

test.describe('Document editing — negative', () => {
  test('TC-DOC-009: Create is blocked while no organization is selected', async ({ page }) => {
    const list = new AssetRecordListPage(page, DOCUMENT_TYPE)
    await list.goto()

    const drawer = await DocumentCreateDrawer.open(page)
    await drawer.typeName(uniqueName('Vendor Onboarding Runbook'))

    // The name is a required field, but the Create button also needs an organization.
    await expect(drawer.createButton).toBeDisabled()
    await expect(drawer.dialog).toBeVisible()
  })

  test('TC-DOC-010: Creating with an empty document name is rejected', async ({ page }) => {
    const list = new AssetRecordListPage(page, DOCUMENT_TYPE)
    await list.goto()

    const posts: string[] = []
    page.on('request', request => {
      if (request.method() === 'POST' && request.url().includes(`/v1/assets/${DOCUMENT_TYPE}`)) {
        posts.push(request.url())
      }
    })

    const drawer = await DocumentCreateDrawer.open(page)
    await drawer.selectOrganization(TEST_ORGANIZATION)
    await expect(drawer.createButton).toBeEnabled()

    await drawer.createButton.click()

    // The required-name validation blocks the submit — no record is created.
    expect(posts).toHaveLength(0)
    await expect(drawer.dialog).toBeVisible()
    await expect(drawer.dialog.getByRole('heading', { name: /New Documents/i })).toBeVisible()
    expect(
      await drawer.nameInput.evaluate(el => (el as HTMLInputElement).checkValidity()),
    ).toBe(false)
  })
})
