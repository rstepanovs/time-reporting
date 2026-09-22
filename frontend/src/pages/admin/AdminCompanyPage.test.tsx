import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import {
  CompanyLogoTooLargeError,
  getCompanySettings,
  setCompanyLogo,
  updateCompanySettings,
} from "@/company/api";
import { testAdmin, testCompanySettings } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/company/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/company/api")>()),
  getCompanySettings: vi.fn(),
  updateCompanySettings: vi.fn(),
  setCompanyLogo: vi.fn(),
  clearCompanyLogo: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
  vi.mocked(getCompanySettings).mockResolvedValue(testCompanySettings);
});

describe("AdminCompanyPage", () => {
  it("renders the company's settings", async () => {
    renderApp("/admin/company");

    await screen.findByDisplayValue(testCompanySettings.legal_name);
    expect(screen.getByDisplayValue(testCompanySettings.org_number)).toBeTruthy();
    expect(screen.getByDisplayValue(testCompanySettings.iban)).toBeTruthy();
  });

  it("saves changes to the form", async () => {
    vi.mocked(updateCompanySettings).mockResolvedValue({
      ...testCompanySettings,
      legal_name: "New Legal Name",
    });
    renderApp("/admin/company");
    await screen.findByDisplayValue(testCompanySettings.legal_name);

    fireEvent.change(screen.getByLabelText(/^legal name/i), {
      target: { value: "New Legal Name" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(updateCompanySettings).toHaveBeenCalledWith(
        expect.objectContaining({ legal_name: "New Legal Name" }),
      );
    });
    await screen.findByText("Company settings saved");
  });

  it("saves the customer numbering fields", async () => {
    vi.mocked(updateCompanySettings).mockResolvedValue(testCompanySettings);
    renderApp("/admin/company");
    await screen.findByDisplayValue(testCompanySettings.legal_name);

    fireEvent.change(screen.getByLabelText(/customer number prefix/i), {
      target: { value: "CUST-" },
    });
    fireEvent.change(screen.getByLabelText(/next customer number/i), {
      target: { value: "7" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(updateCompanySettings).toHaveBeenCalledWith(
        expect.objectContaining({ customer_number_prefix: "CUST-", next_customer_number: 7 }),
      );
    });
  });

  it("toggles self-review", async () => {
    vi.mocked(updateCompanySettings).mockResolvedValue({
      ...testCompanySettings,
      allow_self_review: true,
    });
    renderApp("/admin/company");
    await screen.findByDisplayValue(testCompanySettings.legal_name);

    fireEvent.click(screen.getByRole("switch", { name: /allow self-review/i }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => {
      expect(updateCompanySettings).toHaveBeenCalledWith(
        expect.objectContaining({ allow_self_review: true }),
      );
    });
  });

  it("uploads a logo", async () => {
    vi.mocked(setCompanyLogo).mockResolvedValue({ ...testCompanySettings, has_logo: true });
    renderApp("/admin/company");
    await screen.findByDisplayValue(testCompanySettings.legal_name);

    const file = new File(["content"], "logo.png", { type: "image/png" });
    fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, {
      target: { files: [file] },
    });

    await waitFor(() => {
      expect(setCompanyLogo).toHaveBeenCalledWith(file);
    });
    await screen.findByText("Logo updated");
  });

  it("surfaces an oversize-logo error", async () => {
    vi.mocked(setCompanyLogo).mockRejectedValue(
      new CompanyLogoTooLargeError("Logo is over the size limit"),
    );
    renderApp("/admin/company");
    await screen.findByDisplayValue(testCompanySettings.legal_name);

    const file = new File(["content"], "big.png", { type: "image/png" });
    fireEvent.change(document.querySelector<HTMLInputElement>('input[type="file"]')!, {
      target: { files: [file] },
    });

    await screen.findByText("Logo is over the size limit");
  });
});
