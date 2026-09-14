import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getRemovalImpact, type RemovalImpact, RemovalBlockedError, removeEntity } from "@/admin/api";
import { RemoveEntityModal } from "@/admin/RemoveEntityModal";
import { theme } from "@/theme";

vi.mock("@/admin/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/admin/api")>()),
  getRemovalImpact: vi.fn(),
  removeEntity: vi.fn(),
}));

function renderModal(onRemoved = vi.fn()) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <MantineProvider theme={theme} env="test">
      <Notifications />
      <QueryClientProvider client={queryClient}>
        <RemoveEntityModal
          entity="customers"
          id="c1"
          name="Acme"
          opened
          onClose={vi.fn()}
          onRemoved={onRemoved}
        />
      </QueryClientProvider>
    </MantineProvider>,
  );
  return { onRemoved };
}

const unblockedImpact: RemovalImpact = {
  is_active: true,
  can_delete_permanently: true,
  blockers: [],
  effects: [],
};

beforeEach(() => {
  vi.resetAllMocks();
});

describe("RemoveEntityModal", () => {
  it("archives by default", async () => {
    vi.mocked(getRemovalImpact).mockResolvedValue(unblockedImpact);
    vi.mocked(removeEntity).mockResolvedValue("archived");
    const { onRemoved } = renderModal();

    await screen.findByText("Delete permanently");
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));

    await waitFor(() => expect(removeEntity).toHaveBeenCalledWith("customers", "c1", {
      permanent: false,
    }));
    await waitFor(() => expect(onRemoved).toHaveBeenCalledWith("archived"));
  });

  it("deletes permanently when the checkbox is checked", async () => {
    vi.mocked(getRemovalImpact).mockResolvedValue(unblockedImpact);
    vi.mocked(removeEntity).mockResolvedValue("deleted");
    renderModal();

    await screen.findByText("Delete permanently");
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(await screen.findByRole("button", { name: "Delete permanently" }));

    await waitFor(() =>
      expect(removeEntity).toHaveBeenCalledWith("customers", "c1", { permanent: true }),
    );
  });

  it("disables the checkbox and shows the reason when blocked", async () => {
    vi.mocked(getRemovalImpact).mockResolvedValue({
      is_active: true,
      can_delete_permanently: false,
      blockers: [{ kind: "projects", count: 2 }],
      effects: [],
    });
    renderModal();

    await screen.findByText("Delete permanently");
    expect((screen.getByRole("checkbox") as HTMLInputElement).disabled).toBe(true);
    expect(await screen.findByText(/Has 2 projects/)).toBeTruthy();
  });

  it("shows the effects warning only once permanent delete is selected", async () => {
    vi.mocked(getRemovalImpact).mockResolvedValue({
      is_active: true,
      can_delete_permanently: true,
      blockers: [],
      effects: [{ kind: "project_members", count: 3 }],
    });
    renderModal();

    await screen.findByText("Delete permanently");
    expect(screen.queryByText(/Also removes/)).toBeNull();

    fireEvent.click(screen.getByRole("checkbox"));

    expect(await screen.findByText(/Also removes 3 project members/)).toBeTruthy();
  });

  it("shows the blockers from a 409 response returned by the server", async () => {
    vi.mocked(getRemovalImpact).mockResolvedValue(unblockedImpact);
    vi.mocked(removeEntity).mockRejectedValue(
      new RemovalBlockedError([{ kind: "projects", count: 1 }]),
    );
    renderModal();

    await screen.findByText("Delete permanently");
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(await screen.findByRole("button", { name: "Delete permanently" }));

    expect(await screen.findByText(/Has 1 project\. Delete or reassign/)).toBeTruthy();
  });
});
