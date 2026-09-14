import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getRemovalImpact } from "@/admin/api";
import { fetchCurrentUser } from "@/auth/api";
import {
  createCustomer,
  type Customer,
  type CustomerPage,
  listCustomers,
  updateCustomer,
} from "@/customers/api";
import { testAdmin, testCustomer } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/customers/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/customers/api")>()),
  listCustomers: vi.fn(),
  createCustomer: vi.fn(),
  updateCustomer: vi.fn(),
}));

vi.mock("@/admin/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/admin/api")>()),
  getRemovalImpact: vi.fn(),
}));

const archivedCustomer: Customer = { ...testCustomer, id: "c2", name: "Archived Co", is_active: false };

function page(items = [testCustomer]): CustomerPage {
  return { items, total: items.length, limit: 20, offset: 0 };
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
  vi.mocked(listCustomers).mockResolvedValue(page());
  vi.mocked(getRemovalImpact).mockResolvedValue({
    is_active: true,
    can_delete_permanently: true,
    blockers: [],
    effects: [],
  });
});

describe("AdminCustomersPage", () => {
  it("renders the customer list", async () => {
    renderApp("/admin/customers");

    await screen.findByText(testCustomer.name);
    expect(screen.getByText(testCustomer.legal_name!)).toBeTruthy();
    expect(screen.getByText(testCustomer.currency)).toBeTruthy();
    expect(screen.getByText("Every 1 month")).toBeTruthy();
  });

  it("searches with a debounce", async () => {
    renderApp("/admin/customers");
    await screen.findByText(testCustomer.name);
    vi.mocked(listCustomers).mockClear();

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "acme" } });

    await waitFor(() =>
      expect(listCustomers).toHaveBeenCalledWith(expect.objectContaining({ search: "acme" })),
    );
  });

  it("creates a customer", async () => {
    vi.mocked(createCustomer).mockResolvedValue({ ...testCustomer, id: "new-id" });
    renderApp("/admin/customers");
    await screen.findByText(testCustomer.name);

    fireEvent.click(screen.getByRole("button", { name: "New customer" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^name/i), { target: { value: "New Co" } });
    fireEvent.change(within(dialog).getByLabelText(/^address line 1/i), {
      target: { value: "1 Street" },
    });
    fireEvent.change(within(dialog).getByLabelText(/^city/i), { target: { value: "Berlin" } });
    fireEvent.change(within(dialog).getByLabelText(/^country/i), { target: { value: "DE" } });
    fireEvent.change(within(dialog).getByLabelText(/^anchor date/i), {
      target: { value: "2026-01-01" },
    });
    fireEvent.change(within(dialog).getByLabelText(/^currency/i), { target: { value: "EUR" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create customer" }));

    await waitFor(() => expect(createCustomer).toHaveBeenCalled());
    const body = vi.mocked(createCustomer).mock.calls[0]![0];
    expect(body.name).toBe("New Co");
    expect(body.billing_address.country).toBe("DE");
    expect(body.currency).toBe("EUR");
  });

  it("edit sends null for a cleared optional field", async () => {
    vi.mocked(updateCustomer).mockResolvedValue(testCustomer);
    renderApp("/admin/customers");
    const row = (await screen.findByText(testCustomer.name)).closest("tr")!;

    fireEvent.click(within(row).getByRole("button", { name: "Actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^legal name/i), { target: { value: "" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() =>
      expect(updateCustomer).toHaveBeenCalledWith(
        testCustomer.id,
        expect.objectContaining({ legal_name: null }),
      ),
    );
    const body = vi.mocked(updateCustomer).mock.calls[0]![1];
    expect(body.name).toBeUndefined();
  });

  it("shows a Restore action for an archived customer", async () => {
    vi.mocked(listCustomers).mockResolvedValue(page([archivedCustomer]));
    vi.mocked(updateCustomer).mockResolvedValue({ ...archivedCustomer, is_active: true });
    renderApp("/admin/customers");
    const row = (await screen.findByText(archivedCustomer.name)).closest("tr")!;

    fireEvent.click(within(row).getByRole("button", { name: "Actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Restore" }));

    await waitFor(() =>
      expect(updateCustomer).toHaveBeenCalledWith(archivedCustomer.id, { is_active: true }),
    );
  });

  it("opens the remove dialog from the row menu", async () => {
    renderApp("/admin/customers");
    const row = (await screen.findByText(testCustomer.name)).closest("tr")!;

    fireEvent.click(within(row).getByRole("button", { name: "Actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Remove…" }));

    expect(await screen.findByRole("heading", { name: "Remove customer" })).toBeTruthy();
  });
});
