import type { AuditEvent, AuditEventPage } from "@/audit/api";
import type { CurrentUser } from "@/auth/api";
import type { CalendarDay, NonWorkingDay } from "@/calendar/api";
import type { Customer } from "@/customers/api";
import type {
  ExpenseAttachment,
  ExpenseOption,
  ExpenseReport,
  ExpenseReportSummary,
} from "@/expenses/api";
import type { BillingItem, Project, ProjectMember } from "@/projects/api";
import type { Backup, BackupList, SystemConfig, SystemStatus } from "@/system/api";
import type {
  BillingPeriodListItem,
  BillingPeriodPage,
  MonthCalendar,
  MonthHours,
  MonthTimeSummary,
  ProjectBillingPeriod,
  TeamMonthOverview,
  TimesheetOption,
  TimesheetRow,
  TimesheetWeek,
  TimesheetWeekSummary,
  WeeklyHours,
  YearHours,
} from "@/timesheets/api";

export const testManager: CurrentUser = {
  id: "3f0c8a52-6a55-4f5e-9d0e-6a1c1f1f2b10",
  name: "Ada Lovelace",
  email: "ada@example.com",
  roles: ["manager"],
  is_active: true,
  last_login_at: "2026-09-14T08:00:00Z",
  created_at: "2026-09-01T08:00:00Z",
  updated_at: "2026-09-01T08:00:00Z",
};

export const testEmployee: CurrentUser = {
  ...testManager,
  id: "7b1a2c3d-4e5f-6789-0abc-def123456789",
  name: "Wendy Employee",
  email: "wendy@example.com",
  roles: [],
};

export const testAdmin: CurrentUser = {
  ...testManager,
  id: "a1d2e3f4-5678-4abc-9def-0123456789ab",
  name: "Alice Admin",
  email: "alice@example.com",
  roles: ["admin", "manager"],
};

export const testAdminOnly: CurrentUser = {
  ...testAdmin,
  id: "a1d2e3f4-5678-4abc-9def-0123456789ac",
  name: "Ann Admin-Only",
  email: "ann@example.com",
  roles: ["admin"],
};

export const testAccountant: CurrentUser = {
  ...testManager,
  id: "a1d2e3f4-5678-4abc-9def-0123456789ad",
  name: "Andy Accountant",
  email: "andy@example.com",
  roles: ["accountant"],
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
  customer: {
    id: testCustomer.id,
    name: testCustomer.name,
    is_active: true,
    currency: testCustomer.currency,
  },
  name: "Website Revamp",
  description: "Redesign the public marketing site.",
  is_active: true,
  normal_working_hours: "8.00",
  manager: null,
  created_at: "2026-02-01T08:00:00Z",
  updated_at: "2026-02-01T08:00:00Z",
};

export const testBillingItem: BillingItem = {
  id: "b1a1a1a1-1111-1111-1111-111111111111",
  project_id: testProject.id,
  preset: "normal_hours",
  name: "Normal working hours",
  description: null,
  unit: "hour",
  unit_rate: "90.00",
  markup_percent: null,
  position: 1,
  is_active: true,
  created_at: "2026-02-01T08:00:00Z",
  updated_at: "2026-02-01T08:00:00Z",
};

export const testCustomBillingItem: BillingItem = {
  id: "b2a2a2a2-2222-2222-2222-222222222222",
  project_id: testProject.id,
  preset: null,
  name: "On-call standby",
  description: "Weekend on-call",
  unit: "amount",
  unit_rate: null,
  markup_percent: "10.00",
  position: 7,
  is_active: true,
  created_at: "2026-02-01T08:00:00Z",
  updated_at: "2026-02-01T08:00:00Z",
};

export const testProjectMember: ProjectMember = {
  user_id: testEmployee.id,
  name: testEmployee.name,
  email: testEmployee.email,
  roles: testEmployee.roles,
  is_active: true,
  added_at: "2026-02-02T08:00:00Z",
};

// 2026-09-14 is a Monday.
export const TEST_WEEK_START = "2026-09-14";

export const testSystemStatus: SystemStatus = {
  backend_version: "1.2.3",
  git_sha: "abc123def456",
  database: {
    server_version: "17.4",
    size_bytes: 52_428_800,
    connection_count: 3,
    current_revision: "0010_add_audit_events",
    head_revision: "0010_add_audit_events",
    migrations_pending: false,
  },
  tables: [
    { name: "users", estimated_rows: 5 },
    { name: "customers", estimated_rows: 3 },
  ],
  started_at: "2026-09-15T08:00:00Z",
  uptime_seconds: 93_784,
  last_backup_at: "2026-09-16T02:00:00Z",
};

export const testSystemConfig: SystemConfig = {
  // Deliberately distinct from AppLayout's hardcoded "Time Reporting" header title, so tests can
  // tell the two apart.
  app_name: "Time Reporting (staging)",
  debug: false,
  cors_origins: ["http://localhost:5173"],
  access_token_expire_minutes: 60,
  auth_cookie_secure: true,
  holiday_country: "DE",
  holiday_subdivision: "BE",
  daily_working_hours: "8.00",
  backup_dir: "/var/backups/time-reporting",
  backup_retention_count: 14,
  backup_timeout_seconds: 300,
  attachment_dir: "attachments",
  attachment_max_bytes: 10_485_760,
};

export const testBackup: Backup = {
  name: "time-reporting-20260916T020000Z-0010_add_audit_events.dump",
  created_at: "2026-09-16T02:00:00Z",
  revision: "0010_add_audit_events",
  size_bytes: 52_428_800,
  attachments_size_bytes: null,
};

export const testBackupList: BackupList = {
  backups: [testBackup],
  last_backup_at: testBackup.created_at,
};

export const testNonWorkingDay: NonWorkingDay = {
  id: "d1a1a1a1-1111-1111-1111-111111111111",
  day: "2026-09-16",
  name: "Custom Holiday",
  kind: "company_day_off",
};

export const testCalendarDays: CalendarDay[] = [
  { day: "2026-09-14", is_weekend: false, non_working_day: null },
  { day: "2026-09-15", is_weekend: false, non_working_day: null },
  { day: "2026-09-16", is_weekend: false, non_working_day: testNonWorkingDay },
  { day: "2026-09-17", is_weekend: false, non_working_day: null },
  { day: "2026-09-18", is_weekend: false, non_working_day: null },
  { day: "2026-09-19", is_weekend: true, non_working_day: null },
  { day: "2026-09-20", is_weekend: true, non_working_day: null },
];

export const testTimesheetRow: TimesheetRow = {
  project: {
    id: testProject.id,
    customer: {
      id: testCustomer.id,
      name: testCustomer.name,
      is_active: true,
      currency: testCustomer.currency,
    },
    name: testProject.name,
    is_active: true,
    normal_working_hours: "8.00",
  },
  billing_item: {
    id: testBillingItem.id,
    project_id: testProject.id,
    preset: "normal_hours",
    name: "Normal working hours",
    unit: "hour",
    unit_rate: "90.00",
    markup_percent: null,
    position: 1,
    is_active: true,
  },
  is_open: true,
  entries: [{ date: "2026-09-14", quantity: "8.00", note: null }],
  comment: null,
  locked_dates: [],
};

export const testTimesheetWeek: TimesheetWeek = {
  user: { id: testEmployee.id, name: testEmployee.name, email: testEmployee.email },
  week_start: TEST_WEEK_START,
  status: "draft",
  submitted_at: null,
  reviewed_at: null,
  reviewed_by_name: null,
  return_comment: null,
  can_edit: true,
  can_submit: true,
  can_review: false,
  days: testCalendarDays,
  rows: [testTimesheetRow],
};

export const testExpenseBillingItem: ExpenseOption["billing_items"][number] = {
  id: "b2a2a2a2-2222-2222-2222-222222222222",
  project_id: testProject.id,
  preset: null,
  name: "On-call standby",
  unit: "amount",
  unit_rate: null,
  markup_percent: "10.00",
  position: 7,
  is_active: true,
};

export const testExpenseOption: ExpenseOption = {
  project: {
    id: testProject.id,
    customer: {
      id: testCustomer.id,
      name: testCustomer.name,
      is_active: true,
      currency: testCustomer.currency,
    },
    name: testProject.name,
    is_active: true,
  },
  billing_items: [testExpenseBillingItem],
};

export const testExpenseAttachment: ExpenseAttachment = {
  id: "e3a3a3a3-3333-3333-3333-333333333333",
  file_name: "receipt.pdf",
  content_type: "application/pdf",
  size_bytes: 204_800,
  uploaded_by_name: testEmployee.name,
  created_at: "2026-09-14T09:00:00Z",
};

export const testExpenseReport: ExpenseReport = {
  id: "e1a1a1a1-1111-1111-1111-111111111111",
  project: testExpenseOption.project,
  user: { id: testEmployee.id, name: testEmployee.name, email: testEmployee.email },
  period_start: "2026-09-01",
  period_end: "2026-09-30",
  status: "draft",
  submitted_at: null,
  reviewed_at: null,
  reviewed_by_name: null,
  return_comment: null,
  locked_at: null,
  can_edit: true,
  can_submit: true,
  can_review: false,
  is_locked: false,
  total: "120.00",
  lines: [
    {
      id: "e2a2a2a2-2222-2222-2222-222222222222",
      expense_date: "2026-09-14",
      billing_item: testExpenseBillingItem,
      amount: "120.00",
      description: "Client dinner",
      vendor: "Trattoria Milano",
      document_no: "INV-1042",
    },
  ],
  attachments: [testExpenseAttachment],
};

export const testExpenseReportSummary: ExpenseReportSummary = {
  id: testExpenseReport.id,
  project: testExpenseReport.project,
  user: testExpenseReport.user,
  period_start: testExpenseReport.period_start,
  period_end: testExpenseReport.period_end,
  status: testExpenseReport.status,
  submitted_at: testExpenseReport.submitted_at,
  total: testExpenseReport.total,
  line_count: testExpenseReport.lines.length,
};

// A two-week slice of September 2026 (real months span up to 6 weeks; the dashboard doesn't
// assume any particular length). Week of Sep 7 is fully booked; week of Sep 14 is the "current"
// week (today is 2026-09-15): Sep 14 is fully booked, Sep 15 (today) and Sep 17-18 aren't yet,
// and Sep 16 is the custom non-working day already used by testCalendarDays.
export const testMonthCalendar: MonthCalendar = {
  user: { id: testEmployee.id, name: testEmployee.name, email: testEmployee.email },
  year: 2026,
  month: 9,
  weeks: [
    {
      week_start: "2026-09-07",
      iso_week: 37,
      expected_hours: "40.00",
      hours: "40.00",
      days: [
        {
          calendar_day: { day: "2026-09-07", is_weekend: false, non_working_day: null },
          in_month: true,
          is_working_day: true,
          expected_hours: "8.00",
          hours: "8.00",
        },
        {
          calendar_day: { day: "2026-09-08", is_weekend: false, non_working_day: null },
          in_month: true,
          is_working_day: true,
          expected_hours: "8.00",
          hours: "8.00",
        },
        {
          calendar_day: { day: "2026-09-09", is_weekend: false, non_working_day: null },
          in_month: true,
          is_working_day: true,
          expected_hours: "8.00",
          hours: "8.00",
        },
        {
          calendar_day: { day: "2026-09-10", is_weekend: false, non_working_day: null },
          in_month: true,
          is_working_day: true,
          expected_hours: "8.00",
          hours: "8.00",
        },
        {
          calendar_day: { day: "2026-09-11", is_weekend: false, non_working_day: null },
          in_month: true,
          is_working_day: true,
          expected_hours: "8.00",
          hours: "8.00",
        },
        {
          calendar_day: { day: "2026-09-12", is_weekend: true, non_working_day: null },
          in_month: true,
          is_working_day: false,
          expected_hours: "0.00",
          hours: "0.00",
        },
        {
          calendar_day: { day: "2026-09-13", is_weekend: true, non_working_day: null },
          in_month: true,
          is_working_day: false,
          expected_hours: "0.00",
          hours: "0.00",
        },
      ],
    },
    {
      week_start: TEST_WEEK_START,
      iso_week: 38,
      expected_hours: "32.00",
      hours: "6.00",
      days: [
        {
          calendar_day: { day: "2026-09-14", is_weekend: false, non_working_day: null },
          in_month: true,
          is_working_day: true,
          expected_hours: "8.00",
          hours: "6.00",
        },
        {
          calendar_day: { day: "2026-09-15", is_weekend: false, non_working_day: null },
          in_month: true,
          is_working_day: true,
          expected_hours: "8.00",
          hours: "0.00",
        },
        {
          calendar_day: { day: "2026-09-16", is_weekend: false, non_working_day: testNonWorkingDay },
          in_month: true,
          is_working_day: false,
          expected_hours: "0.00",
          hours: "0.00",
        },
        {
          calendar_day: { day: "2026-09-17", is_weekend: false, non_working_day: null },
          in_month: true,
          is_working_day: true,
          expected_hours: "8.00",
          hours: "0.00",
        },
        {
          calendar_day: { day: "2026-09-18", is_weekend: false, non_working_day: null },
          in_month: true,
          is_working_day: true,
          expected_hours: "8.00",
          hours: "0.00",
        },
        {
          calendar_day: { day: "2026-09-19", is_weekend: true, non_working_day: null },
          in_month: true,
          is_working_day: false,
          expected_hours: "0.00",
          hours: "0.00",
        },
        {
          calendar_day: { day: "2026-09-20", is_weekend: true, non_working_day: null },
          in_month: true,
          is_working_day: false,
          expected_hours: "0.00",
          hours: "0.00",
        },
      ],
    },
  ],
  expected_hours: "72.00",
  expected_hours_to_date: "56.00",
  hours: "46.00",
};

export const testMonthHoursCurrent: MonthHours = {
  year: 2026,
  month: 9,
  is_current: true,
  working_days: 11,
  expected_hours: "88.00",
  expected_hours_to_date: "56.00",
  totals: {
    normal_hours: "46.00",
    overtime_hours: "0.00",
    travel_hours: "0.00",
    other_hours: "0.00",
    total_hours: "46.00",
  },
  projects: [
    {
      project: testTimesheetRow.project,
      totals: {
        normal_hours: "46.00",
        overtime_hours: "0.00",
        travel_hours: "0.00",
        other_hours: "0.00",
        total_hours: "46.00",
      },
    },
  ],
};

export const testMonthHoursPast: MonthHours = {
  year: 2026,
  month: 8,
  is_current: false,
  working_days: 21,
  expected_hours: "168.00",
  expected_hours_to_date: "168.00",
  totals: {
    normal_hours: "160.00",
    overtime_hours: "8.00",
    travel_hours: "4.00",
    other_hours: "0.00",
    total_hours: "172.00",
  },
  projects: [
    {
      project: testTimesheetRow.project,
      totals: {
        normal_hours: "160.00",
        overtime_hours: "8.00",
        travel_hours: "4.00",
        other_hours: "0.00",
        total_hours: "172.00",
      },
    },
  ],
};

export const testYearHours: YearHours = {
  user: { id: testEmployee.id, name: testEmployee.name, email: testEmployee.email },
  year: 2026,
  months: [testMonthHoursCurrent, testMonthHoursPast],
  expected_hours: "256.00",
  expected_hours_to_date: "224.00",
  totals: {
    normal_hours: "206.00",
    overtime_hours: "8.00",
    travel_hours: "4.00",
    other_hours: "0.00",
    total_hours: "218.00",
  },
};

// Matches testMonthHoursCurrent's hours (46h booked of 88 expected, 56 to date) plus benefits.
export const testMonthTimeSummary: MonthTimeSummary = {
  user: { id: testEmployee.id, name: testEmployee.name, email: testEmployee.email },
  year: 2026,
  month: 9,
  is_current: true,
  working_days: 11,
  expected_hours: "88.00",
  expected_hours_to_date: "56.00",
  hours: {
    normal_hours: "46.00",
    overtime_hours: "0.00",
    travel_hours: "0.00",
    other_hours: "0.00",
    total_hours: "46.00",
  },
  per_diem_days: "2.00",
  expenses: [{ currency: "EUR", amount: "120.00" }],
};

// Matches testMonthHoursPast's hours (172h of 168 expected); no benefits this month.
export const testMonthTimeSummaryPrevious: MonthTimeSummary = {
  user: { id: testEmployee.id, name: testEmployee.name, email: testEmployee.email },
  year: 2026,
  month: 8,
  is_current: false,
  working_days: 21,
  expected_hours: "168.00",
  expected_hours_to_date: "168.00",
  hours: {
    normal_hours: "160.00",
    overtime_hours: "8.00",
    travel_hours: "4.00",
    other_hours: "0.00",
    total_hours: "172.00",
  },
  per_diem_days: "0.00",
  expenses: [],
};

// 6 ISO weeks ending with the current one (2026-09-14, matching TEST_WEEK_START and its 6h booked
// in testMonthCalendar).
export const testWeeklyHours: WeeklyHours = {
  user: { id: testEmployee.id, name: testEmployee.name, email: testEmployee.email },
  weeks: [
    {
      week_start: "2026-08-10",
      iso_year: 2026,
      iso_week: 33,
      is_current: false,
      expected_hours: "40.00",
      expected_hours_to_date: "40.00",
      totals: {
        normal_hours: "32.00",
        overtime_hours: "0.00",
        travel_hours: "0.00",
        other_hours: "0.00",
        total_hours: "32.00",
      },
    },
    {
      week_start: "2026-08-17",
      iso_year: 2026,
      iso_week: 34,
      is_current: false,
      expected_hours: "40.00",
      expected_hours_to_date: "40.00",
      totals: {
        normal_hours: "36.00",
        overtime_hours: "0.00",
        travel_hours: "0.00",
        other_hours: "0.00",
        total_hours: "36.00",
      },
    },
    {
      week_start: "2026-08-24",
      iso_year: 2026,
      iso_week: 35,
      is_current: false,
      expected_hours: "40.00",
      expected_hours_to_date: "40.00",
      totals: {
        normal_hours: "40.00",
        overtime_hours: "0.00",
        travel_hours: "0.00",
        other_hours: "0.00",
        total_hours: "40.00",
      },
    },
    {
      week_start: "2026-08-31",
      iso_year: 2026,
      iso_week: 36,
      is_current: false,
      expected_hours: "40.00",
      expected_hours_to_date: "40.00",
      totals: {
        normal_hours: "16.00",
        overtime_hours: "0.00",
        travel_hours: "4.00",
        other_hours: "0.00",
        total_hours: "20.00",
      },
    },
    {
      week_start: "2026-09-07",
      iso_year: 2026,
      iso_week: 37,
      is_current: false,
      expected_hours: "40.00",
      expected_hours_to_date: "40.00",
      totals: {
        normal_hours: "36.00",
        overtime_hours: "2.00",
        travel_hours: "0.00",
        other_hours: "0.00",
        total_hours: "38.00",
      },
    },
    {
      week_start: TEST_WEEK_START,
      iso_year: 2026,
      iso_week: 38,
      is_current: true,
      expected_hours: "32.00",
      expected_hours_to_date: "16.00",
      totals: {
        normal_hours: "6.00",
        overtime_hours: "0.00",
        travel_hours: "0.00",
        other_hours: "0.00",
        total_hours: "6.00",
      },
    },
  ],
  projects: [
    {
      project: testTimesheetRow.project,
      totals: {
        normal_hours: "166.00",
        overtime_hours: "2.00",
        travel_hours: "4.00",
        other_hours: "0.00",
        total_hours: "172.00",
      },
    },
  ],
};

export const testTimesheetWeekSummary: TimesheetWeekSummary = {
  user: { id: testEmployee.id, name: testEmployee.name, email: testEmployee.email },
  week_start: TEST_WEEK_START,
  status: "submitted",
  submitted_at: "2026-09-14T09:00:00Z",
  total_hours: "40.00",
};

export const testTimesheetOption: TimesheetOption = {
  project: testTimesheetRow.project,
  billing_items: [
    testTimesheetRow.billing_item,
    {
      id: "b3a3a3a3-3333-3333-3333-333333333333",
      project_id: testProject.id,
      preset: "overtime_hours",
      name: "Overtime working hours",
      unit: "hour",
      unit_rate: "135.00",
      markup_percent: null,
      position: 2,
      is_active: true,
    },
  ],
};

const zeroHours = {
  normal_hours: "0.00",
  overtime_hours: "0.00",
  travel_hours: "0.00",
  other_hours: "0.00",
  total_hours: "0.00",
};

export const testNotReadyBillingPeriod: ProjectBillingPeriod = {
  project_id: testProject.id,
  period_start: "2026-09-01",
  period_end: "2026-09-30",
  status: "not_ready",
  sent_at: null,
  sent_by: null,
  blocking_weeks: 1,
  blocking_reports: 0,
  weeks_in_scope: 1,
  hours: { ...zeroHours, normal_hours: "19.00", total_hours: "19.00" },
  per_diem_days: "0",
  expenses: [],
};

export const testReadyBillingPeriod: ProjectBillingPeriod = {
  project_id: "p2a2a2a2-2222-2222-2222-222222222222",
  period_start: "2026-08-01",
  period_end: "2026-08-31",
  status: "ready",
  sent_at: null,
  sent_by: null,
  blocking_weeks: 0,
  blocking_reports: 0,
  weeks_in_scope: 4,
  hours: { ...zeroHours, normal_hours: "160.00", total_hours: "160.00" },
  per_diem_days: "0",
  expenses: [],
};

export const testBillingPeriodListItem: BillingPeriodListItem = {
  project_id: testReadyBillingPeriod.project_id,
  project_name: "Platform Migration",
  customer_name: testCustomer.name,
  period_start: testReadyBillingPeriod.period_start,
  period_end: testReadyBillingPeriod.period_end,
  sent_at: "2026-09-02T09:00:00Z",
  sent_by_id: testManager.id,
  sent_by_name: testManager.name,
};

export const testBillingPeriodPage: BillingPeriodPage = {
  items: [testBillingPeriodListItem],
  total: 1,
  limit: 20,
  offset: 0,
};

export const testAuditEvent: AuditEvent = {
  id: "9c1e2f3a-4b5c-6d7e-8f90-1a2b3c4d5e6f",
  occurred_at: "2026-09-16T10:00:00Z",
  actor_id: testAdmin.id,
  actor_name: testAdmin.name,
  action: "billing_period.reopened",
  entity_type: "billing_period",
  entity_id: `${testReadyBillingPeriod.project_id}:${testReadyBillingPeriod.period_start}`,
  summary: "Reopened Platform Migration's September 2026 billing period",
  details: { project_name: "Platform Migration", period_start: testReadyBillingPeriod.period_start },
};

export const testAuditEventPage: AuditEventPage = {
  items: [testAuditEvent],
  total: 1,
  limit: 20,
  offset: 0,
};

export const testTeamMonthOverview: TeamMonthOverview = {
  year: 2026,
  month: 9,
  weeks: ["2026-08-31", "2026-09-07", "2026-09-14", "2026-09-21", "2026-09-28"],
  counts: {
    awaiting_approval: 1,
    returned: 0,
    not_submitted: 3,
    approved: 1,
  },
  projects: [
    {
      project: testTimesheetRow.project,
      members: [
        {
          user: { id: testEmployee.id, name: testEmployee.name, email: testEmployee.email },
          is_member: true,
          project_hours: "19.00",
          total_hours_in_month: "19.00",
          expected_hours_to_date: "88.00",
          weeks: testTeamMonthOverviewWeeks(),
          warning: "under_expected_hours",
        },
      ],
      billing: testNotReadyBillingPeriod,
    },
    {
      project: {
        id: testReadyBillingPeriod.project_id,
        customer: testTimesheetRow.project.customer,
        name: "Platform Migration",
        is_active: true,
        normal_working_hours: "8.00",
      },
      members: [
        {
          user: { id: testManager.id, name: testManager.name, email: testManager.email },
          is_member: true,
          project_hours: "160.00",
          total_hours_in_month: "160.00",
          expected_hours_to_date: "88.00",
          weeks: testTeamMonthOverviewWeeks(),
          warning: null,
        },
      ],
      billing: testReadyBillingPeriod,
    },
  ],
};

function testTeamMonthOverviewWeeks() {
  return [
    {
      week_start: "2026-08-31",
      iso_year: 2026,
      iso_week: 36,
      status: "approved" as const,
      project_hours: "5.00",
      total_hours: "5.00",
      expected_hours: "8.00",
    },
    {
      week_start: "2026-09-07",
      iso_year: 2026,
      iso_week: 37,
      status: "approved" as const,
      project_hours: "40.00",
      total_hours: "40.00",
      expected_hours: "40.00",
    },
    {
      week_start: "2026-09-14",
      iso_year: 2026,
      iso_week: 38,
      status: "submitted" as const,
      project_hours: "19.00",
      total_hours: "19.00",
      expected_hours: "40.00",
    },
    {
      week_start: "2026-09-21",
      iso_year: 2026,
      iso_week: 39,
      status: "draft" as const,
      project_hours: "0.00",
      total_hours: "0.00",
      expected_hours: "40.00",
    },
    {
      week_start: "2026-09-28",
      iso_year: 2026,
      iso_week: 40,
      status: "draft" as const,
      project_hours: "0.00",
      total_hours: "0.00",
      expected_hours: "16.00",
    },
  ];
}
