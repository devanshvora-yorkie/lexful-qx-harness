import { expect, type APIRequestContext, type APIResponse, type Page, type Response } from '@playwright/test';
import { injectAuthCookies } from '../../../../auth-helper';

/**
 * Common POM for LEX-2293 "Relationships" (asset related items).
 * Shared constants, API helpers and drawer navigation. Module locators live in ./related-items-pom.ts.
 *
 * Seed fixtures are the UAT assets observed in FEATURE.md (run LEX-2293-20261021T070045Z-e067).
 * The shared tenant only ever links these two assets, and every test clears them before and after.
 */

export const BASE_URL = 'https://e2e-test.uat.lexful.net';
export const API_BASE = 'https://api.uat.lexful.net';
export const ACCOUNT_ID = '01a0ee54-00c2-7054-ae8b-a4cb9e1b7d8b';

export type AssetTypeName = 'system.contact' | 'system.configuration';
export type GroupLabel = 'Assets' | 'Contacts' | 'Documents' | 'Passwords';

export interface AssetRef {
  type: AssetTypeName;
  id: string;
  name: string;
}

export const CONTACT: AssetRef = {
  type: 'system.contact',
  id: '01a0ee77-584e-7753-b690-c62f2b81c24b',
  name: 'Adipiscing Tempor',
};

export const CONFIG: AssetRef = {
  type: 'system.configuration',
  id: '01a0ee77-49ba-76fa-a179-f6615203a7ff',
  name: 'AAA Culpa Device',
};

export interface RelatedItem {
  id: string;
  asset_id: string;
  asset_name: string;
  asset_type: string;
  description: string | null;
  created_at: string;
  created_by: string;
  is_source: boolean;
  asset_organization_id?: string;
  asset_organization_name?: string;
}

export const RELATED_HEADERS = {
  'content-type': 'application/json',
  'x-account-id': ACCOUNT_ID,
};

export function relatedUrl(asset: AssetRef): string {
  return `${API_BASE}/v1/assets/${asset.type}/${asset.id}/related`;
}

/** Asset drawer URL, same encoding the app uses (see FEATURE.md section 1). */
export function drawerUrl(asset: AssetRef): string {
  const drawer = encodeURIComponent(JSON.stringify([{ type: asset.type, id: asset.id }]));
  return `${BASE_URL}/docs/d/all/${asset.type}?drawer=${drawer}`;
}

/** page.waitForResponse predicate for the related endpoint of one asset. */
export function relatedResponse(asset: AssetRef, method: string, status?: number) {
  return (response: Response): boolean =>
    response.request().method() === method &&
    response.url() === relatedUrl(asset) &&
    (status === undefined || response.status() === status);
}

/**
 * Direct API calls against the related endpoints. page.request shares the browser
 * context cookies, so this works after injectAuthCookies().
 */
export class RelatedItemsApi {
  constructor(private readonly request: APIRequestContext) {}

  get(asset: AssetRef): Promise<APIResponse> {
    return this.request.get(relatedUrl(asset), { headers: RELATED_HEADERS });
  }

  put(asset: AssetRef, body: unknown): Promise<APIResponse> {
    return this.request.put(relatedUrl(asset), { headers: RELATED_HEADERS, data: body });
  }

  patch(asset: AssetRef, body: unknown): Promise<APIResponse> {
    return this.request.patch(relatedUrl(asset), { headers: RELATED_HEADERS, data: body });
  }

  del(asset: AssetRef, ids: string[]): Promise<APIResponse> {
    return this.request.delete(relatedUrl(asset), { headers: RELATED_HEADERS, data: ids });
  }

  /** Current relationship rows for an asset. Asserts the GET is 200. */
  async items(asset: AssetRef): Promise<RelatedItem[]> {
    const res = await this.get(asset);
    expect(res.status()).toBe(200);
    return (await res.json()).items as RelatedItem[];
  }

  /** Links CONFIG from CONTACT via the API (PUT 201) and returns the created row. */
  async seedLink(description?: string): Promise<RelatedItem> {
    const row = description === undefined ? { asset_id: CONFIG.id } : { asset_id: CONFIG.id, description };
    const res = await this.put(CONTACT, [row]);
    expect(res.status()).toBe(201);
    const created = ((await res.json()).items as RelatedItem[]).find((i) => i.asset_id === CONFIG.id);
    expect(created, 'PUT response contains the CONFIG link').toBeDefined();
    return created as RelatedItem;
  }

  /** Cleanup: removes every relationship on the asset (shared UAT). Not an assertion path. */
  async clear(asset: AssetRef = CONTACT): Promise<void> {
    const items = await this.items(asset);
    if (items.length === 0) return;
    const res = await this.del(asset, items.map((i) => i.id));
    expect(res.status()).toBe(204);
  }
}

export class RelatedItemsCommonPOM {
  constructor(readonly page: Page) {}

  get api(): RelatedItemsApi {
    return new RelatedItemsApi(this.page.request);
  }

  /** Session cookies from runs/<run>/auth-state.json (AUTH_STATE). Never calls /auth/password per test. */
  async authenticate(): Promise<void> {
    await injectAuthCookies(this.page.context());
  }

  /** Open the asset drawer by URL. domcontentloaded only: networkidle is banned. */
  async gotoDrawer(asset: AssetRef): Promise<void> {
    await this.page.goto(drawerUrl(asset), { waitUntil: 'domcontentloaded', timeout: 15000 });
  }

  relationshipsTab() {
    return this.page.getByRole('tab', { name: 'Relationships', exact: true });
  }

  /** Opens the drawer, clicks Relationships, and returns the GET 200 response for that asset. */
  async openRelationshipsTab(asset: AssetRef): Promise<Response> {
    await this.gotoDrawer(asset);
    const tab = this.relationshipsTab();
    await tab.waitFor({ state: 'visible', timeout: 15000 });
    const [response] = await Promise.all([
      this.page.waitForResponse(relatedResponse(asset, 'GET', 200)),
      tab.click(),
    ]);
    await expect(tab).toHaveAttribute('aria-selected', 'true');
    return response;
  }
}
