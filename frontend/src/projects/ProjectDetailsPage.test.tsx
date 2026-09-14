import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import {
  addProjectMember,
  getProject,
  listProjectMembers,
  ProjectNotFoundError,
  removeProjectMember,
  updateProject,
} from "@/projects/api";
import { searchUserDirectory } from "@/users/api";
import { testProject, testProjectMember, testUser, testWorker } from "@/test/fixtures";
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
}));

vi.mock("@/users/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/users/api")>()),
  searchUserDirectory: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getProject).mockResolvedValue(testProject);
  vi.mocked(listProjectMembers).mockResolvedValue([testProjectMember]);
  vi.mocked(searchUserDirectory).mockResolvedValue([]);
});

describe("ProjectDetailsPage", () => {
  it("renders the project and its members", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    renderApp(`/projects/${testProject.id}`);

    await screen.findByRole("heading", { name: testProject.name });
    expect(screen.getByText(testProject.customer.name)).toBeTruthy();
    expect(screen.getByText(testProject.description!)).toBeTruthy();
    expect(screen.getByText(testProjectMember.name)).toBeTruthy();
    expect(screen.getByText(testProjectMember.email)).toBeTruthy();
  });

  it("hides write controls from a worker", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testWorker);
    renderApp(`/projects/${testProject.id}`);

    await screen.findByRole("heading", { name: testProject.name });
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Archive" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove" })).toBeNull();
    expect(screen.queryByRole("combobox", { name: "Add a member" })).toBeNull();
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

  it("shows a not-found state for an unknown project", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    vi.mocked(getProject).mockRejectedValue(new ProjectNotFoundError());
    renderApp(`/projects/${testProject.id}`);

    await screen.findByRole("heading", { name: "Project not found" });
    expect(screen.getByRole("link", { name: "Back to projects" })).toBeTruthy();
  });
});
