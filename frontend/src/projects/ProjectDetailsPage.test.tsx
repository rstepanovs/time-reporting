import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import {
  addProjectBillingItem,
  addProjectMember,
  BillingItemConflictError,
  deleteProjectBillingItem,
  getProject,
  listProjectBillingItems,
  listProjectMembers,
  ProjectNotFoundError,
  removeProjectMember,
  updateProject,
  updateProjectBillingItem,
} from "@/projects/api";
import { searchUserDirectory } from "@/users/api";
import {
  testAdmin,
  testBillingItem,
  testProject,
  testProjectMember,
  testUser,
  testWorker,
} from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/projects/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/projects/api")>()),
  getProject: vi.fn(),
  listProjectMembers: vi.fn(),
  updateProject: vi.fn(),
  addProjectMember: vi.fn(),
  removeProjectMember: vi.fn(),
  listProjectBillingItems: vi.fn(),
  addProjectBillingItem: vi.fn(),
  updateProjectBillingItem: vi.fn(),
  deleteProjectBillingItem: vi.fn(),
}));

vi.mock("@/users/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/users/api")>()),
  searchUserDirectory: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getProject).mockResolvedValue(testProject);
  vi.mocked(listProjectMembers).mockResolvedValue([testProjectMember]);
  vi.mocked(listProjectBillingItems).mockResolvedValue([testBillingItem]);
  vi.mocked(searchUserDirectory).mockResolvedValue([]);
});

describe("ProjectDetailsPage", () => {
  it("renders the project, its members and its billing items", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    renderApp(`/projects/${testProject.id}`);

    await screen.findByRole("heading", { name: testProject.name });
    expect(screen.getByText(testProject.customer.name)).toBeTruthy();
    expect(screen.getByText(testProject.description!)).toBeTruthy();
    expect(screen.getByText(testProjectMember.name)).toBeTruthy();
    expect(screen.getByText(testProjectMember.email)).toBeTruthy();
    // Billing items load once the project itself has (a separate, later-mounted query).
    await screen.findByText(testBillingItem.name);
    expect(screen.getByText("Default")).toBeTruthy();
    // testBillingItem: unit "hour", unit_rate "90.00", project's customer currency "EUR".
    expect(screen.getByText("90.00 EUR / hour")).toBeTruthy();
  });

  it("hides write controls from a worker", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    renderApp(`/projects/${testProject.id}`);

    await screen.findByRole("heading", { name: testProject.name });
    // A worker can still read billing items, just not act on them; wait for them to render
    // before asserting the write controls are absent, so the page has settled.
    await screen.findByText(testBillingItem.name);
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Archive" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Add a member" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add billing item" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Actions" })).toBeNull();
  });

  it("lets a manager add a member", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    const candidate = {
      id: "new-member-id",
      name: "New Member",
      email: "new-member@example.com",
      role: "worker" as const,
    };
    vi.mocked(searchUserDirectory).mockResolvedValue([candidate]);
    vi.mocked(addProjectMember).mockResolvedValue({
      user_id: candidate.id,
      name: candidate.name,
      email: candidate.email,
      role: candidate.role,
      is_active: true,
      added_at: "2026-03-01T08:00:00Z",
    });
    renderApp(`/projects/${testProject.id}`);
    await screen.findByRole("heading", { name: testProject.name });

    const combobox = screen.getByRole("combobox", { name: "Add a member" });
    fireEvent.click(combobox);
    fireEvent.change(combobox, { target: { value: "New" } });
    fireEvent.click(await screen.findByRole("option", { name: /New Member/ }));
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() => {
      expect(addProjectMember).toHaveBeenCalledWith(testProject.id, candidate.id);
    });
  });

  it("lets a manager remove a member after confirming", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    vi.mocked(removeProjectMember).mockResolvedValue();
    renderApp(`/projects/${testProject.id}`);
    await screen.findByRole("heading", { name: testProject.name });

    fireEvent.click(screen.getByRole("button", { name: "Remove" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Remove" }));

    await waitFor(() => {
      expect(removeProjectMember).toHaveBeenCalledWith(testProject.id, testProjectMember.user_id);
    });
  });

  it("shows 'None' when the project has no manager", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    renderApp(`/projects/${testProject.id}`);

    await screen.findByRole("heading", { name: testProject.name });
    expect(screen.getByText("Manager: None")).toBeTruthy();
  });

  it("shows the project's manager when assigned", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    vi.mocked(getProject).mockResolvedValue({
      ...testProject,
      manager: { id: "mgr-1", name: "Mark Manager", email: "mark@example.com", is_active: true },
    });
    renderApp(`/projects/${testProject.id}`);

    await screen.findByRole("heading", { name: testProject.name });
    expect(screen.getByText("Manager: Mark Manager (mark@example.com)")).toBeTruthy();
  });

  it("lets a manager assign a project manager", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    const candidate = {
      id: "mgr-1",
      name: "Mark Manager",
      email: "mark@example.com",
      role: "project_manager" as const,
    };
    vi.mocked(searchUserDirectory).mockResolvedValue([candidate]);
    vi.mocked(updateProject).mockResolvedValue({
      ...testProject,
      manager: { id: candidate.id, name: candidate.name, email: candidate.email, is_active: true },
    });
    renderApp(`/projects/${testProject.id}`);
    await screen.findByRole("heading", { name: testProject.name });

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    const combobox = within(dialog).getByRole("combobox", { name: /^manager/i });
    fireEvent.click(combobox);
    fireEvent.change(combobox, { target: { value: "Mark" } });
    fireEvent.click(await screen.findByRole("option", { name: /Mark Manager/ }));
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(updateProject).toHaveBeenCalledWith(testProject.id, { manager_id: candidate.id });
    });
  });

  it("lets a manager change normal working hours per day", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    vi.mocked(updateProject).mockResolvedValue({
      ...testProject,
      normal_working_hours: "6.00",
    });
    renderApp(`/projects/${testProject.id}`);
    await screen.findByRole("heading", { name: testProject.name });

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(
      within(dialog).getByRole("textbox", { name: /^normal working hours per day/i }),
      { target: { value: "6" } },
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(updateProject).toHaveBeenCalledWith(testProject.id, { normal_working_hours: 6 });
    });
  });

  it("archives the project after confirming", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    vi.mocked(updateProject).mockResolvedValue({ ...testProject, is_active: false });
    renderApp(`/projects/${testProject.id}`);
    await screen.findByRole("heading", { name: testProject.name });

    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Confirm" }));

    await waitFor(() => {
      expect(updateProject).toHaveBeenCalledWith(testProject.id, { is_active: false });
    });
  });

  it("lets a manager add a billing item, swapping the rate field for a markup field by unit", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    vi.mocked(addProjectBillingItem).mockResolvedValue({
      ...testBillingItem,
      id: "new-item-id",
      preset: null,
      name: "On-call standby",
      unit: "amount",
    });
    renderApp(`/projects/${testProject.id}`);
    await screen.findByRole("heading", { name: testProject.name });

    fireEvent.click(screen.getByRole("button", { name: "Add billing item" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("textbox", { name: "Rate" })).toBeTruthy();
    expect(within(dialog).queryByRole("textbox", { name: "Markup" })).toBeNull();

    fireEvent.click(within(dialog).getByRole("combobox", { name: "Unit" }));
    fireEvent.click(await screen.findByRole("option", { name: "Expense at cost" }));
    expect(within(dialog).queryByRole("textbox", { name: "Rate" })).toBeNull();

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Name" }), {
      target: { value: "On-call standby" },
    });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Markup" }), {
      target: { value: "10" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add billing item" }));

    await waitFor(() => {
      expect(addProjectBillingItem).toHaveBeenCalledWith(testProject.id, {
        name: "On-call standby",
        unit: "amount",
        description: null,
        unit_rate: null,
        markup_percent: 10,
      });
    });
  });

  it("lets a manager edit a billing item's rate", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    vi.mocked(updateProjectBillingItem).mockResolvedValue({
      ...testBillingItem,
      unit_rate: "95.00",
    });
    renderApp(`/projects/${testProject.id}`);
    await screen.findByRole("heading", { name: testProject.name });

    fireEvent.click(await screen.findByRole("button", { name: "Actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Rate" }), {
      target: { value: "95" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(updateProjectBillingItem).toHaveBeenCalledWith(testProject.id, testBillingItem.id, {
        unit_rate: 95,
      });
    });
  });

  it("shows archived billing items only once the switch is toggled", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    renderApp(`/projects/${testProject.id}`);
    await screen.findByRole("heading", { name: testProject.name });
    expect(listProjectBillingItems).toHaveBeenCalledWith(testProject.id, false);

    fireEvent.click(screen.getByRole("switch", { name: "Show archived" }));

    await waitFor(() => {
      expect(listProjectBillingItems).toHaveBeenCalledWith(testProject.id, true);
    });
  });

  it("offers permanently deleting a billing item only to an admin", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser); // a project manager
    renderApp(`/projects/${testProject.id}`);
    await screen.findByRole("heading", { name: testProject.name });

    fireEvent.click(await screen.findByRole("button", { name: "Actions" }));
    await screen.findByRole("menuitem", { name: "Edit" });
    expect(screen.queryByRole("menuitem", { name: /Delete permanently/ })).toBeNull();
  });

  it("lets an admin permanently delete a billing item", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
    vi.mocked(deleteProjectBillingItem).mockResolvedValue();
    renderApp(`/projects/${testProject.id}`);
    await screen.findByRole("heading", { name: testProject.name });

    fireEvent.click(await screen.findByRole("button", { name: "Actions" }));
    fireEvent.click(await screen.findByRole("menuitem", { name: /Delete permanently/ }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete permanently" }));

    await waitFor(() => {
      expect(deleteProjectBillingItem).toHaveBeenCalledWith(testProject.id, testBillingItem.id);
    });
  });

  it("shows a conflict error when adding a duplicate billing item name", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    vi.mocked(addProjectBillingItem).mockRejectedValue(new BillingItemConflictError());
    renderApp(`/projects/${testProject.id}`);
    await screen.findByRole("heading", { name: testProject.name });

    fireEvent.click(screen.getByRole("button", { name: "Add billing item" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Name" }), {
      target: { value: "Normal working hours" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add billing item" }));

    await screen.findByText(new BillingItemConflictError().message);
  });

  it("shows a not-found state for an unknown project", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    vi.mocked(getProject).mockRejectedValue(new ProjectNotFoundError());
    renderApp(`/projects/${testProject.id}`);

    await screen.findByRole("heading", { name: "Project not found" });
    expect(screen.getByRole("link", { name: "Back to projects" })).toBeTruthy();
  });
});
