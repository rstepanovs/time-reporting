import type { CurrentUser } from "@/auth/api";
import type { CalendarDay, NonWorkingDay } from "@/calendar/api";
import type { Customer } from "@/customers/api";
import type { BillingItem, Project, ProjectMember } from "@/projects/api";
import type {
  MonthCalendar,
  MonthHours,
  TimesheetOption,
  TimesheetRow,
  TimesheetWeek,
  YearHours,
} from "@/timesheets/api";

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
  customer: {
    id: testCustomer.id,
    name: testCustomer.name,
    is_active: true,
    currency: testCustomer.currency,
  },
  name: "Website Revamp",
  description: "Redesign the public marketing site.",
  is_active: true,
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
  user_id: testWorker.id,
  name: testWorker.name,
  email: testWorker.email,
  role: testWorker.role,
  is_active: true,
  added_at: "2026-02-02T08:00:00Z",
};

// 2026-09-14 is a Monday.
export const TEST_WEEK_START = "2026-09-14";

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
};

export const testTimesheetWeek: TimesheetWeek = {
  user: { id: testWorker.id, name: testWorker.name, email: testWorker.email },
  week_start: TEST_WEEK_START,
  can_edit: true,
  days: testCalendarDays,
  rows: [testTimesheetRow],
};

// A two-week slice of September 2026 (real months span up to 6 weeks; the dashboard doesn't
// assume any particular length). Week of Sep 7 is fully booked; week of Sep 14 is the "current"
// week (today is 2026-09-15): Sep 14 is fully booked, Sep 15 (today) and Sep 17-18 aren't yet,
// and Sep 16 is the custom non-working day already used by testCalendarDays.
export const testMonthCalendar: MonthCalendar = {
  user: { id: testWorker.id, name: testWorker.name, email: testWorker.email },
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
  user: { id: testWorker.id, name: testWorker.name, email: testWorker.email },
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
