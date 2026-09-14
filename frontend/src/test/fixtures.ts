import type { CurrentUser } from "@/auth/api";
import type { Customer } from "@/customers/api";
import type { Project, ProjectMember } from "@/projects/api";

export const testUser: CurrentUser = {
  id: "3f0c8a52-6a55-4f5e-9d0e-6a1c1f1f2b10",
  name: "Ada Lovelace",
  email: "ada@example.com",
  role: "project_manager",
  is_active: true,
  last_login_at: "2026-09-14T08:00:00Z",
  created_at: "2026-09-01T08:00:00Z",
  updated_at: "2026-09-01T08:00:00Z",
};

export const testWorker: CurrentUser = {
  ...testUser,
  id: "7b1a2c3d-4e5f-6789-0abc-def123456789",
  name: "Wendy Worker",
  email: "wendy@example.com",
  role: "worker",
};

export const testAdmin: CurrentUser = {
  ...testUser,
  id: "a1d2e3f4-5678-4abc-9def-0123456789ab",
  name: "Alice Admin",
  email: "alice@example.com",
  role: "admin",
};

export const testCustomer: Customer = {
  id: "c1a1a1a1-1111-1111-1111-111111111111",
  name: "Acme Corporation",
  legal_name: "Acme Corporation GmbH",
  tax_id: "DE123456789",
  billing_email: "billing@acme.example",
  billing_address: {
    line1: "Unter den Linden 10",
    line2: null,
    city: "Berlin",
    region: null,
    postal_code: "10117",
    country: "DE",
  },
  billing_period: { interval_count: 1, interval_unit: "month", anchor_date: "2026-01-01" },
  currency: "EUR",
  payment_terms_days: 30,
  notes: null,
  is_active: true,
  created_at: "2026-01-01T08:00:00Z",
  updated_at: "2026-01-01T08:00:00Z",
};

export const testProject: Project = {
  id: "p1a1a1a1-1111-1111-1111-111111111111",
  customer: { id: testCustomer.id, name: testCustomer.name, is_active: true },
  name: "Website Revamp",
  description: "Redesign the public marketing site.",
  is_active: true,
  created_at: "2026-02-01T08:00:00Z",
  updated_at: "2026-02-01T08:00:00Z",
};

export const testProjectMember: ProjectMember = {
  user_id: testWorker.id,
  name: testWorker.name,
  email: testWorker.email,
  role: testWorker.role,
  is_active: true,
  added_at: "2026-02-02T08:00:00Z",
};
