import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import {
  addExpenseAttachment,
  AttachmentTooLargeError,
  approveExpenseReport,
  deleteExpenseAttachment,
  deleteExpenseReport,
  getExpenseReport,
  listExpenseOptions,
  returnExpenseReport,
  saveExpenseReportLines,
  submitExpenseReport,
} from "@/expenses/api";
import { testEmployee, testExpenseOption, testExpenseReport, testManager } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/expenses/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/expenses/api")>()),
  getExpenseReport: vi.fn(),
  listExpenseOptions: vi.fn(),
  saveExpenseReportLines: vi.fn(),
  submitExpenseReport: vi.fn(),
  approveExpenseReport: vi.fn(),
  returnExpenseReport: vi.fn(),
  deleteExpenseReport: vi.fn(),
  addExpenseAttachment: vi.fn(),
  deleteExpenseAttachment: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(getExpenseReport).mockResolvedValue(testExpenseReport);
  vi.mocked(listExpenseOptions).mockResolvedValue([testExpenseOption]);
});

describe("ExpenseReportPage", () => {
  it("renders the report's lines, total and attachments", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    renderApp(`/expenses/${testExpenseReport.id}`);

    await screen.findByDisplayValue("Client dinner");
    expect(screen.getByText("120.00 EUR")).toBeTruthy();
    expect(screen.getByText("receipt.pdf")).toBeTruthy();
  });

  it("edits an existing line and saves", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    vi.mocked(saveExpenseReportLines).mockResolvedValue(testExpenseReport);
    renderApp(`/expenses/${testExpenseReport.id}`);
    await screen.findByDisplayValue("Client dinner");

    fireEvent.change(screen.getByRole("textbox", { name: "Description" }), {
      target: { value: "Updated dinner" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(saveExpenseReportLines).toHaveBeenCalledWith(
        testExpenseReport.id,
        [
          {
            line_id: testExpenseReport.lines[0].id,
            billing_item_id: testExpenseReport.lines[0].billing_item.id,
            expense_date: testExpenseReport.lines[0].expense_date,
            amount: testExpenseReport.lines[0].amount,
            description: "Updated dinner",
            vendor: testExpenseReport.lines[0].vendor,
            document_no: testExpenseReport.lines[0].document_no,
          },
        ],
        [],
      );
    });
  });

  it("adds a new line and saves", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    vi.mocked(saveExpenseReportLines).mockResolvedValue(testExpenseReport);
    renderApp(`/expenses/${testExpenseReport.id}`);
    await screen.findByDisplayValue("Client dinner");

    fireEvent.click(screen.getByRole("button", { name: "Add line" }));
    const descriptionFields = screen.getAllByRole("textbox", { name: "Description" });
    fireEvent.change(descriptionFields[descriptionFields.length - 1], {
      target: { value: "Taxi" },
    });
    const amountFields = screen.getAllByRole("textbox", { name: "Amount" });
    fireEvent.change(amountFields[amountFields.length - 1], { target: { value: "42" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(saveExpenseReportLines).toHaveBeenCalledWith(
        testExpenseReport.id,
        expect.arrayContaining([
          expect.objectContaining({ line_id: null, description: "Taxi", amount: "42" }),
        ]),
        [],
      );
    });
  });

  it("removes a line and saves", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    vi.mocked(saveExpenseReportLines).mockResolvedValue({ ...testExpenseReport, lines: [] });
    renderApp(`/expenses/${testExpenseReport.id}`);
    await screen.findByDisplayValue("Client dinner");

    fireEvent.click(screen.getByRole("button", { name: "Delete line Client dinner" }));
    expect(screen.queryByDisplayValue("Client dinner")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(saveExpenseReportLines).toHaveBeenCalledWith(
        testExpenseReport.id,
        [],
        [testExpenseReport.lines[0].id],
      );
    });
  });

  it("uploads and deletes an attachment", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    vi.mocked(addExpenseAttachment).mockResolvedValue({
      id: "new-attachment",
      file_name: "invoice.pdf",
      content_type: "application/pdf",
      size_bytes: 100,
      uploaded_by_name: testEmployee.name,
      created_at: "2026-09-14T10:00:00Z",
    });
    renderApp(`/expenses/${testExpenseReport.id}`);
    await screen.findByDisplayValue("Client dinner");

    const file = new File(["content"], "invoice.pdf", { type: "application/pdf" });
    fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, {
      target: { files: [file] },
    });

    await waitFor(() => {
      expect(addExpenseAttachment).toHaveBeenCalledWith({
        reportId: testExpenseReport.id,
        file,
      });
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete receipt.pdf" }));

    await waitFor(() => {
      expect(deleteExpenseAttachment).toHaveBeenCalledWith(testExpenseReport.attachments[0].id);
    });
  });

  it("surfaces an oversize-attachment error", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    vi.mocked(addExpenseAttachment).mockRejectedValue(
      new AttachmentTooLargeError("This file is too large"),
    );
    renderApp(`/expenses/${testExpenseReport.id}`);
    await screen.findByDisplayValue("Client dinner");

    const file = new File(["content"], "big.pdf", { type: "application/pdf" });
    fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, {
      target: { files: [file] },
    });

    await screen.findByText("This file is too large");
  });

  it("renders a locked report read-only", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    vi.mocked(getExpenseReport).mockResolvedValue({
      ...testExpenseReport,
      status: "approved",
      is_locked: true,
      can_edit: false,
      can_submit: false,
    });
    renderApp(`/expenses/${testExpenseReport.id}`);

    await screen.findByText("Sent to billing");
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
    expect(screen.queryByRole("textbox", { name: "Description" })).toBeNull();
  });

  it("submits after confirmation", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    vi.mocked(submitExpenseReport).mockResolvedValue({
      ...testExpenseReport,
      status: "submitted",
      can_edit: false,
      can_submit: false,
    });
    renderApp(`/expenses/${testExpenseReport.id}`);
    await screen.findByDisplayValue("Client dinner");

    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Submit" }));

    await waitFor(() => {
      expect(submitExpenseReport).toHaveBeenCalledWith(testExpenseReport.id);
    });
  });

  it("a manager can approve a submitted report", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(getExpenseReport).mockResolvedValue({
      ...testExpenseReport,
      status: "submitted",
      can_edit: false,
      can_submit: false,
      can_review: true,
    });
    vi.mocked(approveExpenseReport).mockResolvedValue({
      ...testExpenseReport,
      status: "approved",
      can_review: false,
    });
    renderApp(`/expenses/${testExpenseReport.id}`);
    await screen.findByText("Client dinner");

    fireEvent.click(screen.getByRole("button", { name: "Approve" }));

    await waitFor(() => {
      expect(approveExpenseReport).toHaveBeenCalledWith(testExpenseReport.id);
    });
  });

  it("shows Approve on the viewer's own report when the server allows self-review", async () => {
    // company.allow_self_review lets a manager approve their own report; the button is gated
    // purely on the server's can_review flag, not a client-side ownership check.
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(getExpenseReport).mockResolvedValue({
      ...testExpenseReport,
      user: { id: testManager.id, name: testManager.name, email: testManager.email },
      status: "submitted",
      can_edit: false,
      can_submit: false,
      can_review: true,
    });
    renderApp(`/expenses/${testExpenseReport.id}`);
    await screen.findByText("Client dinner");

    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
  });

  it("a manager must enter a comment before returning a report", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(getExpenseReport).mockResolvedValue({
      ...testExpenseReport,
      status: "submitted",
      can_edit: false,
      can_submit: false,
      can_review: true,
    });
    renderApp(`/expenses/${testExpenseReport.id}`);
    await screen.findByText("Client dinner");

    fireEvent.click(screen.getByRole("button", { name: "Return…" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("button", { name: "Return" }).hasAttribute("disabled")).toBe(
      true,
    );

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Comment" }), {
      target: { value: "Please attach a receipt" },
    });
    vi.mocked(returnExpenseReport).mockResolvedValue({
      ...testExpenseReport,
      status: "returned",
      return_comment: "Please attach a receipt",
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Return" }));

    await waitFor(() => {
      expect(returnExpenseReport).toHaveBeenCalledWith({
        reportId: testExpenseReport.id,
        comment: "Please attach a receipt",
      });
    });
  });

  it("deletes a draft report", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    vi.mocked(deleteExpenseReport).mockResolvedValue(undefined);
    renderApp(`/expenses/${testExpenseReport.id}`);
    await screen.findByDisplayValue("Client dinner");

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => {
      expect(deleteExpenseReport).toHaveBeenCalledWith(testExpenseReport.id);
    });
  });

  it("asks for confirmation before discarding unsaved changes when leaving", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testEmployee);
    renderApp(`/expenses/${testExpenseReport.id}`);
    await screen.findByDisplayValue("Client dinner");

    fireEvent.change(screen.getByRole("textbox", { name: "Description" }), {
      target: { value: "Changed" },
    });
    fireEvent.click(screen.getByRole("button", { name: "← Back to expenses" }));

    await screen.findByRole("heading", { name: "Discard unsaved changes?" });
  });
});
